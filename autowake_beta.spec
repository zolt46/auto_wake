# -*- mode: python ; coding: utf-8 -*-

import os
import sys

block_cipher = None

spec_path = globals().get("specpath") or os.getcwd()
project_root = os.path.abspath(spec_path)
entry_script = os.path.join(project_root, "autowake_git", "ensure_link.py")
icon_ico_path = os.path.join(project_root, "assets", "icon.ico")
icon_png_path = os.path.join(project_root, "assets", "icon.png")


def _ensure_ico():
    if os.path.exists(icon_ico_path):
        return icon_ico_path
    if not os.path.exists(icon_png_path):
        return None
    try:
        from PIL import Image
    except Exception:
        return icon_png_path
    try:
        img = Image.open(icon_png_path)
        img.save(icon_ico_path, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (32, 32), (16, 16)])
        return icon_ico_path
    except Exception:
        return icon_png_path


icon_path = _ensure_ico()


analysis = Analysis(
    [entry_script],
    pathex=[project_root],
    binaries=[],
    datas=[
        (os.path.join(project_root, "assets", "default_saver.png"), "assets"),
        (os.path.join(project_root, "assets", "notice_default_1.png"), "assets"),
        (os.path.join(project_root, "assets", "notice_default_2.png"), "assets"),
        (os.path.join(project_root, "assets", "icon.png"), "assets"),
        (os.path.join(project_root, "assets", "logo.png"), "assets"),
    ],
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
    icon=icon_path,
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
