"""Unit + real-keytool integration tests for core.keystore.

Creates a throwaway keystore with the real `keytool -genkeypair` (found via
core.toolchain, same as the app would) so these tests exercise the actual
parsing logic against real keytool output, not a guessed format.
"""

from __future__ import annotations

import subprocess

import pytest

from core import keystore, toolchain

STOREPASS = "testpass123"
ALIAS = "myalias"


@pytest.fixture(scope="module")
def keytool_path() -> str:
    java = toolchain.find_java()
    if not java.found:
        pytest.skip("No Java found on this machine — cannot test real keytool")
    kt = toolchain.find_keytool(java.path)
    if not kt.found:
        pytest.skip("No keytool found alongside java on this machine")
    return kt.path


@pytest.fixture()
def real_keystore(tmp_path, keytool_path):
    ks_path = tmp_path / "test.jks"
    subprocess.run(
        [
            keytool_path,
            "-genkeypair",
            "-keystore", str(ks_path),
            "-storepass", STOREPASS,
            "-keypass", STOREPASS,
            "-alias", ALIAS,
            "-keyalg", "RSA",
            "-keysize", "2048",
            "-validity", "365",
            "-dname", "CN=Test, OU=Test, O=Test, L=Test, S=Test, C=US",
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
        check=True,
    )
    return str(ks_path)


def test_list_aliases_with_correct_password(keytool_path, real_keystore):
    result = keystore.list_aliases(keytool_path, real_keystore, STOREPASS)

    assert result.ok
    assert result.aliases == [ALIAS]


def test_list_aliases_with_wrong_password(keytool_path, real_keystore):
    result = keystore.list_aliases(keytool_path, real_keystore, "wrong-password")

    assert not result.ok
    assert result.error == "wrong_password"


def test_verify_alias_success(keytool_path, real_keystore):
    result = keystore.verify_alias(keytool_path, real_keystore, STOREPASS, ALIAS)

    assert result.ok
    assert result.aliases == [ALIAS]


def test_verify_alias_no_such_alias(keytool_path, real_keystore):
    result = keystore.verify_alias(keytool_path, real_keystore, STOREPASS, "does-not-exist")

    assert not result.ok
    assert result.error == "no_such_alias"


def test_verify_alias_wrong_password(keytool_path, real_keystore):
    result = keystore.verify_alias(keytool_path, real_keystore, "wrong-password", ALIAS)

    assert not result.ok
    assert result.error == "wrong_password"


def test_list_aliases_nonexistent_keystore_file(keytool_path, tmp_path):
    missing = str(tmp_path / "does_not_exist.jks")
    result = keystore.list_aliases(keytool_path, missing, STOREPASS)

    assert not result.ok
    assert result.error == "other"
