"""Пути приложения и безопасная запись файлов."""

from __future__ import annotations

import contextlib
import os
import shutil
import sys
import tempfile
from pathlib import Path

APP_NAME = "PostureMonitor"


def app_dir() -> Path:
    """Папка с исполняемым файлом (exe) или исходниками."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def user_data_dir() -> Path:
    """Папка для настроек, статистики и логов (переживает перезапуск exe)."""
    override = os.environ.get("POSTURE_MONITOR_DATA_DIR")
    if override:
        base = Path(override)
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / APP_NAME
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME")
        base = (Path(xdg) if xdg else Path.home() / ".config") / APP_NAME.lower()
    base.mkdir(parents=True, exist_ok=True)
    return base


def data_file(name: str) -> Path:
    """Путь к файлу данных; переносит старый файл из папки приложения."""
    path = user_data_dir() / name
    legacy = app_dir() / name
    if not path.exists() and legacy.is_file():
        with contextlib.suppress(OSError):
            shutil.copy2(legacy, path)
    return path


def atomic_write_text(path: Path, text: str) -> None:
    """Записывает файл через временный файл, чтобы сбой не оставил обрывок."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
