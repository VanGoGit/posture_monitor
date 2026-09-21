"""Кросс-платформенные утилиты: камера, автозапуск."""

from __future__ import annotations

import sys
from pathlib import Path

import cv2

APP_NAME = "PostureMonitor"


def camera_backend() -> int:
    if sys.platform == "win32":
        return cv2.CAP_DSHOW
    if sys.platform == "darwin":
        return cv2.CAP_AVFOUNDATION
    return cv2.CAP_V4L2


def open_camera(index: int) -> cv2.VideoCapture:
    backend = camera_backend()
    cap = cv2.VideoCapture(index, backend)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    return cap


def _app_root() -> Path:
    return Path(__file__).resolve().parent


def launch_exec_parts() -> list[str]:
    if getattr(sys, "frozen", False):
        return [str(Path(sys.executable).resolve())]
    return [
        str(Path(sys.executable).resolve()),
        str(_app_root() / "posture_monitor.py"),
    ]


def launch_command() -> str:
    return " ".join(f'"{part}"' for part in launch_exec_parts())


def is_autostart_enabled() -> bool:
    if sys.platform == "win32":
        return _windows_autostart_enabled()
    if sys.platform == "darwin":
        return _macos_autostart_path().exists()
    return _linux_autostart_path().exists()


def set_autostart(enabled: bool) -> None:
    if sys.platform == "win32":
        _set_windows_autostart(enabled)
    elif sys.platform == "darwin":
        _set_macos_autostart(enabled)
    else:
        _set_linux_autostart(enabled)


def _windows_autostart_enabled() -> bool:
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_READ,
        ) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except OSError:
        return False


def _set_windows_autostart(enabled: bool) -> None:
    import winreg

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        key_path,
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, launch_command())
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except OSError:
                pass


def _linux_autostart_path() -> Path:
    return Path.home() / ".config" / "autostart" / f"{APP_NAME.lower()}.desktop"


def _set_linux_autostart(enabled: bool) -> None:
    path = _linux_autostart_path()
    if enabled:
        path.parent.mkdir(parents=True, exist_ok=True)
        exec_line = " ".join(launch_exec_parts())
        path.write_text(
            "\n".join(
                [
                    "[Desktop Entry]",
                    "Type=Application",
                    "Name=Posture Monitor",
                    f"Exec={exec_line}",
                    "Terminal=false",
                    "X-GNOME-Autostart-enabled=true",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
    elif path.exists():
        path.unlink()


def _macos_autostart_path() -> Path:
    return (
        Path.home()
        / "Library"
        / "LaunchAgents"
        / f"com.{APP_NAME.lower()}.plist"
    )


def _set_macos_autostart(enabled: bool) -> None:
    path = _macos_autostart_path()
    if enabled:
        path.parent.mkdir(parents=True, exist_ok=True)
        args = launch_exec_parts()
        args_xml = "".join(f"\n    <string>{arg}</string>" for arg in args)
        path.write_text(
            f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.{APP_NAME.lower()}</string>
  <key>ProgramArguments</key>
  <array>{args_xml}
  </array>
  <key>RunAtLoad</key><true/>
</dict>
</plist>
""",
            encoding="utf-8",
        )
    elif path.exists():
        path.unlink()
