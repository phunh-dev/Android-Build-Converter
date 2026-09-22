"""Build bundletool command lines and run them via QProcess.

Command-line construction is pure Python (`build_*_args`) so it can be unit
tested without Qt and without ever touching a real filesystem. The actual
process execution (`BundletoolRunner`) uses QProcess, which integrates with
Qt's event loop so the GUI never blocks and both stdout/stderr are read on
separate channels — avoiding the pipe-buffer deadlock a naive
subprocess.Popen + single-thread read would risk on a long, bursty-output
command like `build-apks`.

Security note: keystore/key passwords are NEVER passed as `pass:<literal>`
on the command line, because that leaks the plaintext into the OS process
list (Win32_Process.CommandLine / Task Manager's command-line column). They
are always written to a temp file (no trailing newline — bundletool reads
the raw file contents) and passed as `file:<path>`, then deleted in the
caller's `finally` block. See `write_password_file` / `TemporaryPasswordFile`.
"""

from __future__ import annotations

import os
import platform
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, Signal


def build_apks_args(
    *,
    bundle: str,
    output: str,
    mode: str = "universal",
    ks: str | None = None,
    ks_pass_file: str | None = None,
    ks_key_alias: str | None = None,
    key_pass_file: str | None = None,
    device_spec: str | None = None,
    verbose: bool = True,
) -> list[str]:
    """Build the argument list for `bundletool build-apks` (excluding the
    leading `java -jar bundletool.jar`).

    Passwords are taken as *paths to already-written temp files* — this
    function never touches password contents, keeping it safe to log/test.
    """
    args = [
        "build-apks",
        f"--bundle={bundle}",
        f"--output={output}",
        f"--mode={mode}",
        "--overwrite",  # without this, a second run on the same output fails outright
    ]

    if ks:
        if not ks_key_alias:
            raise ValueError("ks_key_alias is required when ks is provided")
        args.append(f"--ks={ks}")
        args.append(f"--ks-key-alias={ks_key_alias}")
        if ks_pass_file:
            args.append(f"--ks-pass=file:{ks_pass_file}")
        # Always pass --key-pass explicitly when signing: if omitted,
        # bundletool prompts interactively on a TTY that doesn't exist in a
        # GUI context, and the process hangs forever.
        if key_pass_file:
            args.append(f"--key-pass=file:{key_pass_file}")

    if device_spec:
        args.append(f"--device-spec={device_spec}")

    if verbose:
        args.append("--verbose")

    return args


def build_install_args(*, apks: str, adb_path: str, device_id: str | None = None) -> list[str]:
    args = ["install-apks", f"--apks={apks}", f"--adb={adb_path}"]
    if device_id:
        args.append(f"--device-id={device_id}")
    return args


def build_get_size_args(*, apks: str, human_readable: bool = True, dimensions: str | None = None) -> list[str]:
    args = ["get-size", "total", f"--apks={apks}"]
    if human_readable:
        args.append("--human-readable-sizes")
    if dimensions:
        args.append(f"--dimensions={dimensions}")
    return args


def build_dump_manifest_args(*, bundle: str, xpath: str | None = None) -> list[str]:
    args = ["dump", "manifest", f"--bundle={bundle}"]
    if xpath:
        args.append(f"--xpath={xpath}")
    return args


def build_get_device_spec_args(*, output: str, adb_path: str, device_id: str | None = None) -> list[str]:
    args = ["get-device-spec", f"--output={output}", f"--adb={adb_path}", "--overwrite"]
    if device_id:
        args.append(f"--device-id={device_id}")
    return args


def build_validate_args(*, bundle: str) -> list[str]:
    return ["validate", f"--bundle={bundle}"]


def redact_command_for_log(args: list[str]) -> list[str]:
    """Return a copy of an argument list with password file flags masked,
    safe to print into the log pane. The password *file path* itself is not
    secret, but we mask the whole flag to avoid ever training a habit of
    echoing secret-adjacent flags verbatim."""
    redacted = []
    for arg in args:
        if arg.startswith("--ks-pass=") or arg.startswith("--key-pass="):
            flag_name = arg.split("=", 1)[0]
            redacted.append(f"{flag_name}=***")
        else:
            redacted.append(arg)
    return redacted


class TemporaryPasswordFile:
    """Context manager: writes a password to a restrictive-permission temp
    file (no trailing newline) and guarantees deletion afterwards.

    Usage:
        with TemporaryPasswordFile(password) as pw_file:
            args = build_apks_args(..., ks_pass_file=pw_file.path, ...)
        # file is deleted here, even if the block raised
    """

    def __init__(self, password: str):
        self._password = password
        self.path: str | None = None

    def __enter__(self) -> "TemporaryPasswordFile":
        fd, path = tempfile.mkstemp(prefix="abc_pw_", suffix=".tmp")
        try:
            # mkstemp already creates the file readable/writable only by the
            # current user on POSIX (mode 0600); on Windows, ACLs default to
            # the owning user's profile, which is the equivalent baseline.
            with os.fdopen(fd, "w", newline="") as f:
                f.write(self._password)  # no trailing newline — see module docstring
        except BaseException:
            os.close(fd) if fd is not None else None
            raise
        self.path = path
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.path and os.path.exists(self.path):
            try:
                os.remove(self.path)
            except OSError:
                pass  # best-effort cleanup; do not mask the original exception


def resource_path(relative: str) -> Path:
    """Resolve a bundled resource (e.g. bundletool.jar) both when running
    from source and when running from a PyInstaller-frozen build."""
    import sys

    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / relative


@dataclass
class ProcessResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False


class BundletoolRunner(QObject):
    """Runs one bundletool subcommand via QProcess, streaming output.

    Signals:
        line_output(str, bool): a line of output, and whether it came from
            stderr (True) or stdout (False).
        finished(int): process exit code.
    """

    line_output = Signal(str, bool)
    finished = Signal(int)

    def __init__(self, java_path: str, jar_path: str, parent: QObject | None = None):
        super().__init__(parent)
        self._java_path = java_path
        self._jar_path = jar_path
        self._process: QProcess | None = None

    def start(self, args: list[str]) -> None:
        process = QProcess(self)
        if platform.system() == "Windows":
            process.setCreateProcessArgumentsModifier(_hide_console_window)

        process.readyReadStandardOutput.connect(self._on_stdout)
        process.readyReadStandardError.connect(self._on_stderr)
        process.finished.connect(self._on_finished)

        full_args = ["-jar", self._jar_path, *args]
        self._process = process
        process.start(self._java_path, full_args)

    def cancel(self) -> None:
        if self._process is None:
            return
        self._process.terminate()
        if not self._process.waitForFinished(3000):
            self._process.kill()

    def _on_stdout(self) -> None:
        if self._process is None:
            return
        data = bytes(self._process.readAllStandardOutput()).decode("utf-8", errors="replace")
        for line in data.splitlines():
            self.line_output.emit(line, False)

    def _on_stderr(self) -> None:
        if self._process is None:
            return
        data = bytes(self._process.readAllStandardError()).decode("utf-8", errors="replace")
        for line in data.splitlines():
            self.line_output.emit(line, True)

    def _on_finished(self, exit_code: int, _exit_status) -> None:
        self.finished.emit(exit_code)


def _hide_console_window(args) -> None:
    """QProcess.CreateProcessArgumentModifier callback: sets CREATE_NO_WINDOW
    so bundletool's java process doesn't flash a console window on Windows."""
    args.flags |= 0x08000000  # CREATE_NO_WINDOW
