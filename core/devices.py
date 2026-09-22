"""List connected Android devices via `adb devices -l`.

Output format (one header line, then one line per device):

    List of devices attached
    R58N123ABCD            device usb:1-1 product:blueline model:Pixel_3 device:blueline transport_id:1

Pure Python, no Qt imports.
"""

from __future__ import annotations

import platform
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class Device:
    serial: str
    state: str  # "device", "unauthorized", "offline", ...
    model: str | None = None

    @property
    def display_name(self) -> str:
        return f"{self.model} ({self.serial})" if self.model else self.serial


def list_devices(adb_path: str) -> list[Device]:
    """Return the list of currently attached devices. Devices in a
    non-"device" state (unauthorized/offline) are still returned so the UI
    can show why they can't be installed to."""
    try:
        proc = subprocess.run(
            [adb_path, "devices", "-l"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []

    if proc.returncode != 0:
        return []

    devices: list[Device] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("List of devices"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        serial, state = parts[0], parts[1]
        model = None
        for token in parts[2:]:
            if token.startswith("model:"):
                model = token.split(":", 1)[1]
                break
        devices.append(Device(serial=serial, state=state, model=model))

    return devices
