# -*- mode: python ; coding: utf-8 -*-

import os
import sys

block_cipher = None

spec_path = globals().get("specpath") or os.getcwd()
project_root = os.path.abspath(spec_path)
entry_script = os.path.join(project_root, "ensure_link.py")


analysis = Analysis(
    [entry_script],
    pathex=[project_root],
    binaries=[],
    datas=[(os.path.join(project_root, "assets", "default_saver.png"), "assets")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(analysis.pure, analysis.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="autowake_beta",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
