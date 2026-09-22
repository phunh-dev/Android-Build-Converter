"""Unit tests for core.devices — adb output parsing."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from core.devices import Device, list_devices


def _fake_completed_process(stdout: str, returncode: int = 0):
    proc = MagicMock()
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = ""
    return proc


def test_list_devices_empty():
    with patch("core.devices.subprocess.run", return_value=_fake_completed_process("List of devices attached\n\n")):
        devices = list_devices("adb")
    assert devices == []


def test_list_devices_parses_serial_state_model():
    output = (
        "List of devices attached\n"
        "R58N123ABCD            device usb:1-1 product:blueline model:Pixel_3 device:blueline transport_id:1\n"
    )
    with patch("core.devices.subprocess.run", return_value=_fake_completed_process(output)):
        devices = list_devices("adb")

    assert devices == [Device(serial="R58N123ABCD", state="device", model="Pixel_3")]
    assert devices[0].display_name == "Pixel_3 (R58N123ABCD)"


def test_list_devices_multiple_devices():
    output = (
        "List of devices attached\n"
        "emulator-5554           device product:sdk_gphone64_x86_64 model:sdk_gphone64_x86_64\n"
        "ABC999                  unauthorized\n"
    )
    with patch("core.devices.subprocess.run", return_value=_fake_completed_process(output)):
        devices = list_devices("adb")

    assert len(devices) == 2
    assert devices[0].serial == "emulator-5554"
    assert devices[0].state == "device"
    assert devices[1].serial == "ABC999"
    assert devices[1].state == "unauthorized"
    assert devices[1].model is None
    assert devices[1].display_name == "ABC999"  # no model -> falls back to serial


def test_list_devices_returns_empty_on_nonzero_exit():
    with patch("core.devices.subprocess.run", return_value=_fake_completed_process("error", returncode=1)):
        devices = list_devices("adb")
    assert devices == []


def test_list_devices_real_adb_on_this_machine():
    """Integration smoke test: the real adb on this machine must at least
    run without error (no devices need be attached)."""
    from core import toolchain

    adb = toolchain.find_adb()
    if not adb.found:
        return  # nothing to test if adb genuinely isn't present
    devices = list_devices(adb.path)
    assert isinstance(devices, list)
