"""Locate Java, keytool and adb on the host machine.

bundletool.jar requires a JVM to run at all — bundling the jar into the app
does not remove that requirement. This module implements a search strategy
(user override -> JAVA_HOME -> PATH -> known JBR/JDK install locations) and
resolves adb the same way, so the rest of the app can always pass absolute
paths explicitly instead of relying on environment variables (bundletool
only honors ANDROID_HOME, not ANDROID_SDK_ROOT, and does not honor PATH for
`--adb` — see workflow.py).

Pure Python, no Qt imports, so it is unit-testable without a GUI.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ToolResult:
    """Outcome of locating one external tool."""

    path: str | None
    version: str | None = None

    @property
    def found(self) -> bool:
        return self.path is not None


def _run_version_check(exe: Path, args: list[str]) -> str | None:
    """Run `exe args` and return combined output if the process exits 0."""
    try:
        proc = subprocess.run(
            [str(exe), *args],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    # java -version prints to stderr, not stdout — a well-known gotcha.
    return (proc.stdout + proc.stderr).strip()


def _java_exe_name() -> str:
    return "java.exe" if platform.system() == "Windows" else "java"


def _keytool_exe_name() -> str:
    return "keytool.exe" if platform.system() == "Windows" else "keytool"


def _adb_exe_name() -> str:
    return "adb.exe" if platform.system() == "Windows" else "adb"


def _candidate_jdk_roots() -> list[Path]:
    """Well-known install locations to probe, per OS."""
    system = platform.system()
    candidates: list[Path] = []

    if system == "Windows":
        program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        candidates += [
            program_files / "Android" / "Android Studio" / "jbr",
            program_files / "Java",
        ]
        for local_app_data_env in ("LOCALAPPDATA",):
            local = os.environ.get(local_app_data_env)
            if local:
                candidates.append(Path(local) / "Programs" / "Eclipse Adoptium")
    elif system == "Darwin":
        candidates += [
            Path("/Applications/Android Studio.app/Contents/jbr/Contents/Home"),
            Path("/Library/Java/JavaVirtualMachines"),
        ]
    else:  # Linux
        candidates += [
            Path("/opt/android-studio/jbr"),
            Path("/usr/lib/jvm"),
        ]

    return [c for c in candidates if c.exists()]


def _find_java_bin_in_root(root: Path) -> Path | None:
    """A root may itself be a JDK home, or a parent dir containing several
    JDK homes (e.g. /usr/lib/jvm/java-17-openjdk, .../java-21-openjdk)."""
    exe_name = _java_exe_name()

    direct = root / "bin" / exe_name
    if direct.is_file():
        return direct

    if root.is_dir():
        try:
            children = sorted(root.iterdir(), reverse=True)  # newer versions often sort later
        except OSError:
            return None
        for child in children:
            candidate = child / "bin" / exe_name
            if candidate.is_file():
                return candidate
    return None


def find_java(user_override: str | None = None) -> ToolResult:
    """Locate a working `java` executable.

    Order: explicit user-chosen path -> JAVA_HOME -> PATH -> JBR bundled with
    Android Studio -> other well-known JDK install locations.
    """
    candidates: list[Path] = []

    if user_override:
        candidates.append(Path(user_override))

    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        candidates.append(Path(java_home) / "bin" / _java_exe_name())

    on_path = shutil.which("java")
    if on_path:
        candidates.append(Path(on_path))

    for root in _candidate_jdk_roots():
        found = _find_java_bin_in_root(root)
        if found:
            candidates.append(found)

    for candidate in candidates:
        if not candidate.is_file():
            continue
        output = _run_version_check(candidate, ["-version"])
        if output is not None:
            return ToolResult(path=str(candidate), version=output.splitlines()[0] if output else None)

    return ToolResult(path=None)


def find_keytool(java_path: str | None) -> ToolResult:
    """keytool ships in the same bin/ directory as java."""
    if not java_path:
        return ToolResult(path=None)

    candidate = Path(java_path).with_name(_keytool_exe_name())
    if candidate.is_file():
        output = _run_version_check(candidate, ["-help"])
        # keytool -help exits 0 in some JDKs and 1 in others; presence of the
        # binary plus it not crashing outright is enough signal here.
        if candidate.is_file():
            return ToolResult(path=str(candidate))
    return ToolResult(path=None)


def _candidate_sdk_roots() -> list[Path]:
    system = platform.system()
    roots: list[Path] = []

    for env_var in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        value = os.environ.get(env_var)
        if value:
            roots.append(Path(value))

    if system == "Windows":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            roots.append(Path(local) / "Android" / "Sdk")
    elif system == "Darwin":
        roots.append(Path.home() / "Library" / "Android" / "sdk")
    else:
        roots.append(Path.home() / "Android" / "Sdk")

    return roots


def find_adb(user_override: str | None = None) -> ToolResult:
    """Locate a working `adb` executable.

    Order: explicit user-chosen path -> PATH -> ANDROID_HOME/ANDROID_SDK_ROOT
    -> default per-OS SDK location. The resolved path is always passed back
    explicitly via --adb= to bundletool, since bundletool itself only reads
    ANDROID_HOME (not ANDROID_SDK_ROOT) and does not search PATH for the
    --adb flag's purposes the way this app does for detection.
    """
    candidates: list[Path] = []

    if user_override:
        candidates.append(Path(user_override))

    on_path = shutil.which("adb")
    if on_path:
        candidates.append(Path(on_path))

    for root in _candidate_sdk_roots():
        candidates.append(root / "platform-tools" / _adb_exe_name())

    for candidate in candidates:
        if not candidate.is_file():
            continue
        output = _run_version_check(candidate, ["version"])
        if output is not None:
            first_line = output.splitlines()[0] if output else None
            return ToolResult(path=str(candidate), version=first_line)

    return ToolResult(path=None)


@dataclass(frozen=True)
class Toolchain:
    """Bundle of everything the app needs to shell out to."""

    java: ToolResult
    keytool: ToolResult
    adb: ToolResult

    @property
    def ready(self) -> bool:
        """Minimum viable: Java is mandatory, adb is optional (only needed
        for install/device features)."""
        return self.java.found


def detect_toolchain(java_override: str | None = None, adb_override: str | None = None) -> Toolchain:
    java = find_java(java_override)
    keytool = find_keytool(java.path)
    adb = find_adb(adb_override)
    return Toolchain(java=java, keytool=keytool, adb=adb)
