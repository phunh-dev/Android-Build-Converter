# PyInstaller spec for Android Build Converter.
#
# Uses a .spec file (not CLI --add-data flags) specifically to avoid the
# classic cross-platform gotcha where --add-data's separator differs
# between Windows (;) and macOS/Linux (:) — the `datas` tuple below is
# plain Python and works identically on any OS running this spec.
#
# Builds in --onedir mode (not --onefile): the bundled jar is 32MB and Qt
# adds ~100MB more, and onefile re-extracts everything to a temp dir on
# every single launch — a measurable startup-time cost for no benefit here.
# onedir also keeps PySide6's LGPL-covered .dll/.so files as separate,
# user-replaceable files, satisfying LGPL's dynamic-linking requirement
# more straightforwardly than onefile's more static-like bundling.

import sys
from pathlib import Path

block_cipher = None

project_root = Path(SPECPATH)

a = Analysis(
    ["main.py"],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        (str(project_root / "resources" / "bundletool.jar"), "resources"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Trim unused Qt modules to reduce build size — this app only
        # needs QtWidgets/QtCore/QtGui, all pulled in via PySide6-Essentials.
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineCore",
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.Qt3DCore",
        "PySide6.Qt3DRender",
        "PySide6.QtNetwork",
        "PySide6.QtMultimedia",
    ],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AndroidBuildConverter",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # --windowed: no console flash on launch
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="AndroidBuildConverter",
)
