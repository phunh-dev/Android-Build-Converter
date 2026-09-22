"""Unit tests for core.workflow — output layout and universal.apk extraction.

Uses a fabricated .apks (a real zip with a fake universal.apk entry) so no
real bundletool run is needed.
"""

from __future__ import annotations

import zipfile

import pytest

from core import workflow


def _make_fake_apks(path, entry_name="universal.apk", content=b"fake apk bytes", extra_entries=None):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(entry_name, content)
        zf.writestr("toc.pb", b"fake toc")
        for name, data in (extra_entries or {}).items():
            zf.writestr(name, data)


def test_output_layout_for_bundle_places_everything_next_to_aab(tmp_path):
    bundle = tmp_path / "myapp.aab"
    bundle.touch()

    layout = workflow.OutputLayout.for_bundle(bundle)

    assert layout.output_dir == tmp_path / "myapp_output"
    assert layout.apks_path == tmp_path / "myapp_output" / "myapp.apks"
    assert layout.apk_path == tmp_path / "myapp_output" / "myapp-universal.apk"
    assert layout.log_path == tmp_path / "myapp_output" / "build-log.txt"


def test_output_layout_ensure_output_dir_creates_directory(tmp_path):
    bundle = tmp_path / "myapp.aab"
    bundle.touch()
    layout = workflow.OutputLayout.for_bundle(bundle)

    assert not layout.output_dir.exists()
    layout.ensure_output_dir()
    assert layout.output_dir.is_dir()


def test_extract_universal_apk_reads_root_entry(tmp_path):
    apks = tmp_path / "app.apks"
    _make_fake_apks(apks, entry_name="universal.apk", content=b"hello apk")

    dest = tmp_path / "out" / "app-universal.apk"
    result = workflow.extract_universal_apk(apks, dest)

    assert result == dest
    assert dest.read_bytes() == b"hello apk"


def test_extract_universal_apk_falls_back_to_any_root_apk(tmp_path):
    """Defensive path: if the exact 'universal.apk' name isn't present,
    fall back to scanning for a root-level .apk entry."""
    apks = tmp_path / "app.apks"
    _make_fake_apks(apks, entry_name="renamed-standalone.apk", content=b"fallback content")

    dest = tmp_path / "out" / "app-universal.apk"
    result = workflow.extract_universal_apk(apks, dest)

    assert result == dest
    assert dest.read_bytes() == b"fallback content"


def test_extract_universal_apk_ignores_nested_apk_entries_for_fallback(tmp_path):
    """A .apk nested under splits/ or standalones/ must not be picked up by
    the fallback — only root-level entries count."""
    apks = tmp_path / "app.apks"
    with zipfile.ZipFile(apks, "w") as zf:
        zf.writestr("splits/base-master.apk", b"split content")
        zf.writestr("toc.pb", b"fake toc")

    dest = tmp_path / "out" / "app-universal.apk"
    with pytest.raises(workflow.UniversalApkNotFoundError):
        workflow.extract_universal_apk(apks, dest)


def test_extract_universal_apk_raises_when_nothing_found(tmp_path):
    apks = tmp_path / "app.apks"
    with zipfile.ZipFile(apks, "w") as zf:
        zf.writestr("toc.pb", b"fake toc")  # no apk entry at all

    dest = tmp_path / "out" / "app-universal.apk"
    with pytest.raises(workflow.UniversalApkNotFoundError):
        workflow.extract_universal_apk(apks, dest)


def test_extract_universal_apk_creates_parent_dirs(tmp_path):
    apks = tmp_path / "app.apks"
    _make_fake_apks(apks)

    dest = tmp_path / "deep" / "nested" / "out.apk"
    workflow.extract_universal_apk(apks, dest)

    assert dest.exists()


def test_cleanup_intermediate_apks_removes_existing_file(tmp_path):
    apks = tmp_path / "app.apks"
    apks.touch()

    workflow.cleanup_intermediate_apks(apks)

    assert not apks.exists()


def test_cleanup_intermediate_apks_noop_when_missing(tmp_path):
    apks = tmp_path / "does_not_exist.apks"
    # Should not raise even though the file was never created.
    workflow.cleanup_intermediate_apks(apks)


def test_check_base_module_size_under_limit(tmp_path):
    apks = tmp_path / "app.apks"
    with zipfile.ZipFile(apks, "w") as zf:
        zf.writestr(workflow.BASE_MASTER_SPLIT_ENTRY, b"x" * 1024)  # 1KB, well under 200MB

    result = workflow.check_base_module_size(apks)

    assert result.error is None
    assert result.size_bytes == 1024
    assert result.over_limit is False
    assert result.limit_mb == 200.0


def test_check_base_module_size_over_limit(tmp_path, monkeypatch):
    """Use a small fake limit to avoid writing an actual 200MB+ test fixture."""
    monkeypatch.setattr(workflow, "PLAY_BASE_MODULE_SIZE_LIMIT_BYTES", 100)
    apks = tmp_path / "app.apks"
    with zipfile.ZipFile(apks, "w") as zf:
        zf.writestr(workflow.BASE_MASTER_SPLIT_ENTRY, b"x" * 200)

    result = workflow.check_base_module_size(apks)

    assert result.error is None
    assert result.size_bytes == 200
    assert result.over_limit is True


def test_check_base_module_size_missing_entry_reports_error(tmp_path):
    """A universal-mode .apks has no splits/base-master.apk entry —
    must report a clear error, not crash or silently say "under limit"."""
    apks = tmp_path / "app.apks"
    with zipfile.ZipFile(apks, "w") as zf:
        zf.writestr("universal.apk", b"fake universal apk")

    result = workflow.check_base_module_size(apks)

    assert result.error is not None
    assert result.size_bytes is None
    assert result.over_limit is False


def test_check_base_module_size_missing_file(tmp_path):
    result = workflow.check_base_module_size(tmp_path / "does_not_exist.apks")
    assert result.error is not None
    assert result.size_bytes is None


def test_full_pipeline_layout_extract_cleanup(tmp_path):
    """End-to-end of the pure-Python parts: given a bundle path, compute the
    layout, extract the apk, and clean up the intermediate .apks — verifying
    the final directory contains exactly the expected artifacts."""
    bundle = tmp_path / "release.aab"
    bundle.touch()
    layout = workflow.OutputLayout.for_bundle(bundle)
    layout.ensure_output_dir()

    _make_fake_apks(layout.apks_path, content=b"real-looking apk bytes")

    workflow.extract_universal_apk(layout.apks_path, layout.apk_path)
    workflow.cleanup_intermediate_apks(layout.apks_path)

    remaining = sorted(p.name for p in layout.output_dir.iterdir())
    assert remaining == ["release-universal.apk"]
    assert layout.apk_path.read_bytes() == b"real-looking apk bytes"
