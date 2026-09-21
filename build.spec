# -*- mode: python ; coding: utf-8 -*-
"""Сборка exe: py -m PyInstaller build.spec"""

from pathlib import Path

block_cipher = None
root = Path(SPECPATH)
hooks_dir = str(root / "hooks")
model_file = root / "models" / "pose_landmarker_lite.task"

datas = []
if model_file.exists():
    datas.append((str(model_file), "models"))

a = Analysis(
    [str(root / "posture_monitor.py")],
    pathex=[str(root)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "mediapipe.tasks.c",
        "mediapipe.tasks.python.core.mediapipe_c_bindings",
        "mediapipe.tasks.python.core.base_options",
        "mediapipe.tasks.python.vision.core.image",
        "mediapipe.tasks.python.vision.core.vision_task_running_mode",
        "mediapipe.tasks.python.vision.pose_landmarker",
        "mediapipe.tasks.python.components.containers.landmark",
        "customtkinter",
        "PIL",
        "pystray",
        "comtypes",
        "comtypes.client",
    ],
    hookspath=[hooks_dir],
    hooksconfig={},
    runtime_hooks=[str(root / "hooks" / "rthook_matplotlib_stub.py")],
    excludes=["matplotlib", "tkinter.test"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="PostureMonitor",
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
)
