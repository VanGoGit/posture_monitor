"""Загрузка и сохранение настроек приложения."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from paths import atomic_write_text, data_file

log = logging.getLogger(__name__)

DEFAULT_DELTA_DEGREES = 10
DELTA_MIN = 1
DELTA_MAX = 60
BAD_POSTURE_SECONDS = 2.0
LEGACY_BACK_BASELINE_MIN = 90.0


def settings_path() -> Path:
    return data_file("settings.json")


@dataclass
class Settings:
    delta_degrees: int = DEFAULT_DELTA_DEGREES
    baseline_neck: float | None = None
    baseline_back: float | None = None
    camera_index: int = 0
    bad_posture_seconds: float = BAD_POSTURE_SECONDS
    show_skeleton: bool = True
    enable_sound: bool = True
    enable_notifications: bool = True
    minimize_to_tray: bool = False
    autostart: bool = False

    def save(self, path: Path | None = None) -> None:
        atomic_write_text(
            path or settings_path(),
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
        )

    @classmethod
    def load(cls, path: Path | None = None) -> Settings:
        path = path or settings_path()
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            log.exception("Не удалось прочитать %s, используются настройки по умолчанию", path)
            return cls()
        if not isinstance(data, dict):
            return cls()

        defaults = cls()
        values: dict[str, Any] = {}
        for field in fields(cls):
            raw = data.get(field.name)
            default = getattr(defaults, field.name)
            values[field.name] = _coerce(raw, default, nullable=field.name.startswith("baseline_"))
        settings = cls(**values)
        # До исправления угла спины эталон хранился как ~180° (вектор был направлен вниз).
        # С таким эталоном контроль спины не работает — требуем перекалибровку.
        if settings.baseline_back is not None and settings.baseline_back > LEGACY_BACK_BASELINE_MIN:
            settings.baseline_back = None
        return settings


def _coerce(raw: object, default: object, *, nullable: bool) -> object:
    """Приводит значение из JSON к типу поля; при ошибке — значение по умолчанию."""
    if raw is None:
        return None if nullable else default
    try:
        if nullable:
            return float(raw)  # type: ignore[arg-type]
        if isinstance(default, bool):
            return bool(raw)
        if isinstance(default, int):
            return int(raw)  # type: ignore[call-overload]
        if isinstance(default, float):
            return float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return raw
