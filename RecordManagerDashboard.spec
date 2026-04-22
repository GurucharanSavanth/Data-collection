# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


project_root = Path(SPECPATH)
app_dir = project_root / "app"
version_file = project_root / "packaging" / "version_info.txt"

hiddenimports = [
    "tkinter",
    "tkinter.ttk",
    "tkinter.filedialog",
    "tkinter.messagebox",
    "tkinter.simpledialog",
]

a = Analysis(
    [str(app_dir / "main.py")],
    pathex=[str(app_dir)],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="RecordManagerDashboard",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=str(version_file),
)
