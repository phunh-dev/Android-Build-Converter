"""Extract the universal APK from a .apks archive and lay out output files.

The requirement is "everything stays in one folder next to the AAB, nothing
scattered". Verified from bundletool's ApkPathManager.class: in
--mode=universal, the APK sits at the ZIP root under the exact name
`universal.apk` (not under splits/ or standalones/), alongside a toc.pb. So a
plain zipfile read is enough — no need to shell out to `extract-apks`.

Pure Python, no Qt imports — testable with a fabricated .apks (just a zip).
"""

from __future__ import annotations

import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path

UNIVERSAL_APK_ENTRY = "universal.apk"
BASE_MASTER_SPLIT_ENTRY = "splits/base-master.apk"

# Google Play rejects an upload if the base module's APK (compressed,
# installed-by-default artifact — the "splits/base-master.apk" entry in a
# split-mode .apks) exceeds this size. Verified against bundletool's
# ModuleSplit$SplitType constants (isBaseModuleSplit / isMasterSplit /
# "master" path segment) — this is the file that maps to Play Console's
# base APK size check.
PLAY_BASE_MODULE_SIZE_LIMIT_BYTES = 200 * 1024 * 1024


class UniversalApkNotFoundError(Exception):
    """Raised when a .apks archive doesn't contain a universal.apk entry at
    the expected location (e.g. it was built in a non-universal mode)."""


@dataclass(frozen=True)
class OutputLayout:
    """Where everything for one conversion job lives, computed from the
    source .aab path."""

    output_dir: Path
    apks_path: Path
    apk_path: Path
    log_path: Path

    @classmethod
    def for_bundle(cls, bundle_path: str | Path) -> "OutputLayout":
        bundle = Path(bundle_path)
        stem = bundle.stem
        output_dir = bundle.parent / f"{stem}_output"
        return cls(
            output_dir=output_dir,
            apks_path=output_dir / f"{stem}.apks",
            apk_path=output_dir / f"{stem}-universal.apk",
            log_path=output_dir / "build-log.txt",
        )

    def ensure_output_dir(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)


def extract_universal_apk(apks_path: str | Path, dest_apk_path: str | Path) -> Path:
    """Pull the universal.apk entry out of a .apks archive and write it to
    dest_apk_path. Falls back to scanning for any top-level *.apk entry if
    the exact expected name isn't found (defensive, in case of a future
    bundletool format change), but raises if nothing suitable exists."""
    apks_path = Path(apks_path)
    dest_apk_path = Path(dest_apk_path)
    dest_apk_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(apks_path) as zf:
        names = zf.namelist()
        entry = UNIVERSAL_APK_ENTRY if UNIVERSAL_APK_ENTRY in names else None

        if entry is None:
            # Defensive fallback: any root-level .apk file.
            fallback_candidates = [
                n for n in names if n.endswith(".apk") and "/" not in n
            ]
            if fallback_candidates:
                entry = fallback_candidates[0]

        if entry is None:
            raise UniversalApkNotFoundError(
                f"No universal.apk entry found in {apks_path.name}. "
                f"Was it built with --mode=universal?"
            )

        with zf.open(entry) as src, open(dest_apk_path, "wb") as dst:
            shutil.copyfileobj(src, dst)

    return dest_apk_path


@dataclass(frozen=True)
class BaseModuleSizeCheck:
    size_bytes: int | None
    over_limit: bool
    error: str | None = None

    @property
    def size_mb(self) -> float | None:
        return self.size_bytes / (1024 * 1024) if self.size_bytes is not None else None

    @property
    def limit_mb(self) -> float:
        return PLAY_BASE_MODULE_SIZE_LIMIT_BYTES / (1024 * 1024)


def check_base_module_size(split_apks_path: str | Path) -> BaseModuleSizeCheck:
    """Read the compressed size of splits/base-master.apk from a
    split-mode (--mode=default) .apks archive and compare it against
    Google Play's 200MB base-APK limit.

    Requires a *split-mode* .apks (not universal) — universal mode fuses
    everything into a single standalone APK with no base-master.apk entry.
    """
    apks_path = Path(split_apks_path)
    try:
        with zipfile.ZipFile(apks_path) as zf:
            try:
                info = zf.getinfo(BASE_MASTER_SPLIT_ENTRY)
            except KeyError:
                return BaseModuleSizeCheck(
                    size_bytes=None,
                    over_limit=False,
                    error=(
                        f"No {BASE_MASTER_SPLIT_ENTRY} entry found — "
                        f"the .apks must be built with --mode=default (split mode), not universal."
                    ),
                )
            size = info.file_size  # uncompressed size of the entry = the actual installed APK's size
    except (OSError, zipfile.BadZipFile) as exc:
        return BaseModuleSizeCheck(size_bytes=None, over_limit=False, error=str(exc))

    return BaseModuleSizeCheck(size_bytes=size, over_limit=size > PLAY_BASE_MODULE_SIZE_LIMIT_BYTES)


def cleanup_intermediate_apks(apks_path: str | Path) -> None:
    """Delete the intermediate .apks file after extraction, if it exists."""
    path = Path(apks_path)
    if path.exists():
        path.unlink()


def open_in_file_manager(path: str | Path) -> None:
    """Open a folder in the OS's file manager (Explorer/Finder/xdg-open)."""
    import platform
    import subprocess

    path = str(path)
    system = platform.system()
    if system == "Windows":
        subprocess.run(["explorer", path])
    elif system == "Darwin":
        subprocess.run(["open", path])
    else:
        subprocess.run(["xdg-open", path])
