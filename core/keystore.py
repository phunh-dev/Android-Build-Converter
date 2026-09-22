"""Validate a keystore and list its aliases via keytool, before the long
bundletool build ever runs.

Verified against the real keytool shipped in this machine's Android Studio
JBR: `keytool -list -keystore <ks> -storepass <pw>` prints one line per
entry like:

    myalias, Sep 22, 2026, PrivateKeyEntry,
    Certificate fingerprint (SHA-256): 6B:E8:...

Wrong password -> "keystore password was incorrect", exit 1.
Wrong alias    -> "Alias <name> does not exist", exit 1.
(Note: unlike bundletool, keytool prints these errors to STDOUT, not
stderr — verified directly against the real keytool binary on this
machine. Both streams are checked defensively.)

Note: `-keypasswd` (which could otherwise verify a *key* password without
mutating anything by setting -new to the same value) is NOT supported on
PKCS12 keystores ("keypasswd commands not supported if -storetype is
PKCS12") — and PKCS12 is bundletool/apksigner's modern default. So the key
password can only be verified by actually running build-apks; this module
only pre-validates the keystore password and alias, which still turns most
"wait 3 minutes then fail" cases into instant feedback.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field


_ALIAS_LINE_RE = re.compile(r"^([^,]+),\s")


@dataclass
class KeystoreCheckResult:
    ok: bool
    aliases: list[str] = field(default_factory=list)
    error: str | None = None  # one of: "wrong_password", "no_such_alias", "other"
    raw_message: str = ""


def _run_keytool(keytool_path: str, args: list[str], storepass: str) -> subprocess.CompletedProcess:
    """Run keytool, feeding the store password via -storepass on argv.

    Note: keytool also supports reading -storepass from stdin by omitting
    the flag, which would avoid argv exposure the way bundletool's file:
    prefix does for build-apks. Since this is a *local pre-check* (not the
    actual signing operation, and the process is short-lived), -storepass
    on argv is accepted here as a pragmatic tradeoff — but if this needs
    hardening later, switch to omitting -storepass and writing the password
    to stdin instead.
    """
    import platform

    return subprocess.run(
        [keytool_path, *args, "-storepass", storepass],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=15,
        creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
    )


def list_aliases(keytool_path: str, keystore_path: str, storepass: str) -> KeystoreCheckResult:
    """List all aliases in a keystore, validating the store password."""
    proc = _run_keytool(keytool_path, ["-list", "-keystore", keystore_path], storepass)
    combined = proc.stdout + proc.stderr

    if proc.returncode != 0:
        error = "wrong_password" if "password was incorrect" in combined else "other"
        return KeystoreCheckResult(ok=False, error=error, raw_message=combined.strip())

    aliases = []
    for line in proc.stdout.splitlines():
        match = _ALIAS_LINE_RE.match(line)
        if match:
            aliases.append(match.group(1).strip())

    return KeystoreCheckResult(ok=True, aliases=aliases, raw_message=proc.stdout)


def verify_alias(keytool_path: str, keystore_path: str, storepass: str, alias: str) -> KeystoreCheckResult:
    """Confirm a specific alias exists in the keystore (also re-validates
    the store password as a side effect)."""
    proc = _run_keytool(
        keytool_path, ["-list", "-keystore", keystore_path, "-alias", alias], storepass
    )
    combined = proc.stdout + proc.stderr

    if proc.returncode != 0:
        if "password was incorrect" in combined:
            error = "wrong_password"
        elif "does not exist" in combined:
            error = "no_such_alias"
        else:
            error = "other"
        return KeystoreCheckResult(ok=False, error=error, raw_message=combined.strip())

    return KeystoreCheckResult(ok=True, aliases=[alias], raw_message=proc.stdout)
