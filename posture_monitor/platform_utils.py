"""Кросс-платформенные утилиты: камера, автозапуск."""

from __future__ import annotations

import contextlib
import plistlib
import sys
from pathlib import Path

import cv2

from .paths import APP_NAME, app_dir


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


def launch_exec_parts() -> list[str]:
    if getattr(sys, "frozen", False):
        return [str(Path(sys.executable).resolve())]
    return [
        str(Path(sys.executable).resolve()),
        str(app_dir() / "run.py"),
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


_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _windows_autostart_enabled() -> bool:
    if sys.platform != "win32":  # сужение платформы для mypy
        return False
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            _RUN_KEY,
            0,
            winreg.KEY_READ,
        ) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except OSError:
        return False


def _set_windows_autostart(enabled: bool) -> None:
    if sys.platform != "win32":  # сужение платформы для mypy
        raise OSError("Автозапуск через реестр доступен только в Windows")
    import winreg

    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        _RUN_KEY,
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, launch_command())
        else:
            with contextlib.suppress(OSError):
                winreg.DeleteValue(key, APP_NAME)


def _linux_autostart_path() -> Path:
    return Path.home() / ".config" / "autostart" / f"{APP_NAME.lower()}.desktop"


def _desktop_quote(arg: str) -> str:
    """Кавычки для ключа Exec по спецификации Desktop Entry."""
    # Обратный слеш экранируется дважды: правило строк применяется до правила кавычек.
    escaped = arg.replace("\\", "\\\\\\\\")
    for ch in '"`$':
        escaped = escaped.replace(ch, "\\" + ch)
    return f'"{escaped}"'


def _set_linux_autostart(enabled: bool) -> None:
    path = _linux_autostart_path()
    if enabled:
        path.parent.mkdir(parents=True, exist_ok=True)
        exec_line = " ".join(_desktop_quote(part) for part in launch_exec_parts())
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
    return Path.home() / "Library" / "LaunchAgents" / f"com.{APP_NAME.lower()}.plist"


def _set_macos_autostart(enabled: bool) -> None:
    path = _macos_autostart_path()
    if enabled:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as f:
            plistlib.dump(
                {
                    "Label": f"com.{APP_NAME.lower()}",
                    "ProgramArguments": launch_exec_parts(),
                    "RunAtLoad": True,
                },
                f,
            )
    elif path.exists():
        path.unlink()
