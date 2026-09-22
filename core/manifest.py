"""Read key facts out of an AAB's manifest via `bundletool dump manifest`.

Uses individual --xpath queries rather than parsing the full manifest dump,
since XPath output is a single clean value per call. Manifest attributes
live in the `android` namespace (bundletool binds the prefix for you), while
`package` is unprefixed — verified against bundletool's documented examples:

    dump manifest --bundle=app.aab --xpath=/manifest/@package
    dump manifest --bundle=app.aab --xpath=/manifest/@android:versionCode

Runs synchronously (subprocess.run, not QProcess) since `dump` is fast and
this is invoked on-demand from a button click, not part of the long-running
build. No Qt imports — testable in isolation given a real .aab.
"""

from __future__ import annotations

import platform
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class BundleInfo:
    package: str | None
    version_code: str | None
    version_name: str | None
    min_sdk: str | None
    target_sdk: str | None
    error: str | None = None


_XPATHS = {
    "package": "/manifest/@package",
    "version_code": "/manifest/@android:versionCode",
    "version_name": "/manifest/@android:versionName",
    "min_sdk": "/manifest/uses-sdk/@android:minSdkVersion",
    "target_sdk": "/manifest/uses-sdk/@android:targetSdkVersion",
}


def _dump_xpath(java_path: str, jar_path: str, bundle_path: str, xpath: str) -> str | None:
    try:
        proc = subprocess.run(
            [java_path, "-jar", jar_path, "dump", "manifest", f"--bundle={bundle_path}", f"--xpath={xpath}"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    if proc.returncode != 0:
        return None

    value = proc.stdout.strip()
    return value or None


def read_bundle_info(java_path: str, jar_path: str, bundle_path: str) -> BundleInfo:
    """Fetch package/version/SDK info from an AAB. Individual fields that
    fail to resolve are left as None rather than failing the whole call —
    a bundle missing minSdkVersion (inherited some other way) shouldn't
    block showing the package name."""
    values: dict[str, str | None] = {}
    first_error: str | None = None

    for key, xpath in _XPATHS.items():
        value = _dump_xpath(java_path, jar_path, bundle_path, xpath)
        values[key] = value

    if values.get("package") is None:
        first_error = "Could not read manifest — is this a valid .aab file?"

    return BundleInfo(
        package=values.get("package"),
        version_code=values.get("version_code"),
        version_name=values.get("version_name"),
        min_sdk=values.get("min_sdk"),
        target_sdk=values.get("target_sdk"),
        error=first_error,
    )
