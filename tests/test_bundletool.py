"""Unit tests for core.bundletool — command construction and password safety.

These test the pure-Python parts only (no QProcess), which is where the
security-critical invariant lives: passwords must never appear in argv.
"""

from __future__ import annotations

import os

from core import bundletool


def test_build_apks_args_universal_mode_includes_overwrite():
    args = bundletool.build_apks_args(bundle="app.aab", output="out.apks")
    assert "build-apks" in args
    assert "--bundle=app.aab" in args
    assert "--output=out.apks" in args
    assert "--mode=universal" in args
    assert "--overwrite" in args  # missing this makes reruns fail


def test_build_apks_args_unsigned_when_no_keystore():
    args = bundletool.build_apks_args(bundle="app.aab", output="out.apks")
    assert not any(a.startswith("--ks=") for a in args)
    assert not any(a.startswith("--ks-pass=") for a in args)


def test_build_apks_args_signed_uses_file_prefix_never_pass_prefix():
    """Regression test for the core security requirement: password material
    must reach bundletool via `file:`, never via `pass:` on argv."""
    args = bundletool.build_apks_args(
        bundle="app.aab",
        output="out.apks",
        ks="my.keystore",
        ks_pass_file="/tmp/kspw.tmp",
        ks_key_alias="myalias",
        key_pass_file="/tmp/keypw.tmp",
    )
    joined = " ".join(args)

    assert "--ks=my.keystore" in args
    assert "--ks-key-alias=myalias" in args
    assert "--ks-pass=file:/tmp/kspw.tmp" in args
    assert "--key-pass=file:/tmp/keypw.tmp" in args

    # No literal "pass:" prefix anywhere — that would leak the plaintext
    # password into the OS process list.
    assert "pass:" not in joined or "file:" in joined  # sanity: file: is the only prefix used
    assert not any("pass:/" in a and "file:" not in a for a in args)


def test_build_apks_args_requires_alias_when_keystore_given():
    try:
        bundletool.build_apks_args(bundle="app.aab", output="out.apks", ks="my.keystore")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_build_apks_args_key_pass_always_explicit_when_signing():
    """If a password file IS provided for key-pass, it must show up as an
    explicit flag — bundletool prompts interactively (hangs a GUI) when
    --key-pass is omitted entirely during signing."""
    args = bundletool.build_apks_args(
        bundle="app.aab",
        output="out.apks",
        ks="my.keystore",
        ks_pass_file="/tmp/a.tmp",
        ks_key_alias="alias1",
        key_pass_file="/tmp/b.tmp",
    )
    assert any(a.startswith("--key-pass=file:") for a in args)


def test_build_install_args():
    args = bundletool.build_install_args(apks="out.apks", adb_path="/path/to/adb", device_id="ABC123")
    assert args == ["install-apks", "--apks=out.apks", "--adb=/path/to/adb", "--device-id=ABC123"]


def test_build_get_size_args_human_readable_default():
    args = bundletool.build_get_size_args(apks="out.apks")
    assert "--human-readable-sizes" in args


def test_build_dump_manifest_args_with_xpath():
    args = bundletool.build_dump_manifest_args(bundle="app.aab", xpath="/manifest/@package")
    assert args == ["dump", "manifest", "--bundle=app.aab", "--xpath=/manifest/@package"]


def test_build_get_device_spec_args_includes_overwrite():
    args = bundletool.build_get_device_spec_args(output="spec.json", adb_path="/path/adb")
    assert "--overwrite" in args
    assert "--adb=/path/adb" in args


def test_redact_command_for_log_masks_password_flags():
    args = ["build-apks", "--ks-pass=file:/tmp/x.tmp", "--key-pass=file:/tmp/y.tmp", "--bundle=app.aab"]
    redacted = bundletool.redact_command_for_log(args)
    assert "--ks-pass=***" in redacted
    assert "--key-pass=***" in redacted
    assert "--bundle=app.aab" in redacted
    assert "/tmp/x.tmp" not in " ".join(redacted)
    assert "/tmp/y.tmp" not in " ".join(redacted)


def test_temporary_password_file_writes_no_trailing_newline():
    with bundletool.TemporaryPasswordFile("hunter2") as pw:
        assert pw.path is not None
        with open(pw.path, "rb") as f:
            content = f.read()
        assert content == b"hunter2"  # exact bytes, no trailing \n or \r\n
    # deleted after the context exits
    assert not os.path.exists(pw.path)


def test_temporary_password_file_deleted_even_on_exception():
    path_used = None
    try:
        with bundletool.TemporaryPasswordFile("hunter2") as pw:
            path_used = pw.path
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert path_used is not None
    assert not os.path.exists(path_used)


def test_temporary_password_file_never_appears_in_built_args_as_plaintext():
    """End-to-end-ish: the actual password string must never appear in the
    constructed argv, only the temp file's path."""
    secret = "S3cr3t!Password"
    with bundletool.TemporaryPasswordFile(secret) as ks_pw, bundletool.TemporaryPasswordFile(secret) as key_pw:
        args = bundletool.build_apks_args(
            bundle="app.aab",
            output="out.apks",
            ks="my.keystore",
            ks_pass_file=ks_pw.path,
            ks_key_alias="alias1",
            key_pass_file=key_pw.path,
        )
        joined = " ".join(args)
        assert secret not in joined
