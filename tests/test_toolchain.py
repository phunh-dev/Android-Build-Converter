"""Unit tests for core.toolchain — priority order and not-found handling.

These tests stub out the subprocess call (_run_version_check) so they don't
depend on any real java/adb being installed, keeping them fast and portable.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core import toolchain


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Ensure tests don't pick up the real machine's env vars."""
    for var in ("JAVA_HOME", "ANDROID_HOME", "ANDROID_SDK_ROOT"):
        monkeypatch.delenv(var, raising=False)


def _fake_version_ok(_exe, _args):
    return "openjdk version \"21\""


def _fake_version_fail(_exe, _args):
    return None


def test_find_java_prefers_user_override(tmp_path, monkeypatch):
    override = tmp_path / "custom" / "java.exe"
    override.parent.mkdir()
    override.touch()

    monkeypatch.setattr(toolchain, "_run_version_check", _fake_version_ok)
    monkeypatch.setattr(toolchain.shutil, "which", lambda _name: None)
    monkeypatch.setattr(toolchain, "_candidate_jdk_roots", lambda: [])

    result = toolchain.find_java(user_override=str(override))

    assert result.found
    assert result.path == str(override)


def test_find_java_falls_back_to_java_home(tmp_path, monkeypatch):
    java_home = tmp_path / "jdk17"
    java_bin = java_home / "bin" / toolchain._java_exe_name()
    java_bin.parent.mkdir(parents=True)
    java_bin.touch()

    monkeypatch.setenv("JAVA_HOME", str(java_home))
    monkeypatch.setattr(toolchain, "_run_version_check", _fake_version_ok)
    monkeypatch.setattr(toolchain.shutil, "which", lambda _name: None)
    monkeypatch.setattr(toolchain, "_candidate_jdk_roots", lambda: [])

    result = toolchain.find_java(user_override=None)

    assert result.found
    assert result.path == str(java_bin)


def test_find_java_falls_back_to_path(tmp_path, monkeypatch):
    on_path = tmp_path / "java.exe"
    on_path.touch()

    monkeypatch.setattr(toolchain, "_run_version_check", _fake_version_ok)
    monkeypatch.setattr(toolchain.shutil, "which", lambda _name: str(on_path))
    monkeypatch.setattr(toolchain, "_candidate_jdk_roots", lambda: [])

    result = toolchain.find_java(user_override=None)

    assert result.found
    assert result.path == str(on_path)


def test_find_java_falls_back_to_known_jdk_roots(tmp_path, monkeypatch):
    jbr_root = tmp_path / "Android Studio" / "jbr"
    java_bin = jbr_root / "bin" / toolchain._java_exe_name()
    java_bin.parent.mkdir(parents=True)
    java_bin.touch()

    monkeypatch.setattr(toolchain, "_run_version_check", _fake_version_ok)
    monkeypatch.setattr(toolchain.shutil, "which", lambda _name: None)
    monkeypatch.setattr(toolchain, "_candidate_jdk_roots", lambda: [jbr_root])

    result = toolchain.find_java(user_override=None)

    assert result.found
    assert result.path == str(java_bin)


def test_find_java_skips_broken_candidate_and_uses_next(tmp_path, monkeypatch):
    """A candidate that exists on disk but fails `-version` must be skipped,
    not returned as a false positive."""
    broken = tmp_path / "broken" / "java.exe"
    broken.parent.mkdir()
    broken.touch()
    working_home = tmp_path / "working"
    working_bin = working_home / "bin" / toolchain._java_exe_name()
    working_bin.parent.mkdir(parents=True)
    working_bin.touch()

    calls = {"n": 0}

    def fake_check(exe, _args):
        calls["n"] += 1
        return None if str(exe) == str(broken) else "openjdk version \"21\""

    monkeypatch.setattr(toolchain, "_run_version_check", fake_check)
    monkeypatch.setattr(toolchain.shutil, "which", lambda _name: None)
    monkeypatch.setattr(toolchain, "_candidate_jdk_roots", lambda: [])
    monkeypatch.setenv("JAVA_HOME", str(working_home))

    result = toolchain.find_java(user_override=str(broken))

    assert result.found
    assert result.path == str(working_bin)
    assert calls["n"] >= 2


def test_find_java_returns_not_found_when_nothing_exists(monkeypatch):
    monkeypatch.setattr(toolchain, "_run_version_check", _fake_version_fail)
    monkeypatch.setattr(toolchain.shutil, "which", lambda _name: None)
    monkeypatch.setattr(toolchain, "_candidate_jdk_roots", lambda: [])

    result = toolchain.find_java(user_override=None)

    assert not result.found
    assert result.path is None


def test_find_adb_prefers_user_override(tmp_path, monkeypatch):
    override = tmp_path / "adb.exe"
    override.touch()

    monkeypatch.setattr(toolchain, "_run_version_check", _fake_version_ok)
    monkeypatch.setattr(toolchain.shutil, "which", lambda _name: None)
    monkeypatch.setattr(toolchain, "_candidate_sdk_roots", lambda: [])

    result = toolchain.find_adb(user_override=str(override))

    assert result.found
    assert result.path == str(override)


def test_find_adb_falls_back_to_sdk_root(tmp_path, monkeypatch):
    sdk_root = tmp_path / "Sdk"
    adb_bin = sdk_root / "platform-tools" / toolchain._adb_exe_name()
    adb_bin.parent.mkdir(parents=True)
    adb_bin.touch()

    monkeypatch.setattr(toolchain, "_run_version_check", _fake_version_ok)
    monkeypatch.setattr(toolchain.shutil, "which", lambda _name: None)
    monkeypatch.setattr(toolchain, "_candidate_sdk_roots", lambda: [sdk_root])

    result = toolchain.find_adb(user_override=None)

    assert result.found
    assert result.path == str(adb_bin)


def test_find_adb_not_found(monkeypatch):
    monkeypatch.setattr(toolchain, "_run_version_check", _fake_version_fail)
    monkeypatch.setattr(toolchain.shutil, "which", lambda _name: None)
    monkeypatch.setattr(toolchain, "_candidate_sdk_roots", lambda: [])

    result = toolchain.find_adb(user_override=None)

    assert not result.found


def test_find_keytool_next_to_java(tmp_path, monkeypatch):
    java_bin = tmp_path / "bin" / toolchain._java_exe_name()
    java_bin.parent.mkdir(parents=True)
    java_bin.touch()
    keytool_bin = tmp_path / "bin" / toolchain._keytool_exe_name()
    keytool_bin.touch()

    result = toolchain.find_keytool(str(java_bin))

    assert result.found
    assert result.path == str(keytool_bin)


def test_find_keytool_returns_not_found_without_java():
    result = toolchain.find_keytool(None)
    assert not result.found


def test_toolchain_ready_requires_only_java(tmp_path):
    java_bin = tmp_path / "java.exe"
    tc = toolchain.Toolchain(
        java=toolchain.ToolResult(path=str(java_bin), version="21"),
        keytool=toolchain.ToolResult(path=None),
        adb=toolchain.ToolResult(path=None),
    )
    assert tc.ready is True


def test_toolchain_not_ready_without_java():
    tc = toolchain.Toolchain(
        java=toolchain.ToolResult(path=None),
        keytool=toolchain.ToolResult(path=None),
        adb=toolchain.ToolResult(path=None),
    )
    assert tc.ready is False


def test_detect_toolchain_finds_real_java_on_this_machine():
    """Integration-style smoke test against the real machine: this dev box
    has a JBR bundled with Android Studio, so detection must succeed with no
    overrides at all."""
    tc = toolchain.detect_toolchain()
    assert tc.java.found, "Expected to find JBR OpenJDK bundled with Android Studio"
    assert tc.keytool.found
