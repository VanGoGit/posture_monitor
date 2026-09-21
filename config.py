"""Загрузка и сохранение настроек приложения."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

SETTINGS_PATH = Path(__file__).resolve().parent / "settings.json"

DEFAULT_DELTA_DEGREES = 10
DELTA_MIN = 1
DELTA_MAX = 60
BAD_POSTURE_SECONDS = 2.0


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

    def save(self) -> None:
        SETTINGS_PATH.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load(cls) -> Settings:
        if not SETTINGS_PATH.exists():
            return cls()
        try:
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            return cls(
                delta_degrees=int(data.get("delta_degrees", DEFAULT_DELTA_DEGREES)),
                baseline_neck=data.get("baseline_neck"),
                baseline_back=data.get("baseline_back"),
                camera_index=int(data.get("camera_index", 0)),
                bad_posture_seconds=float(
                    data.get("bad_posture_seconds", BAD_POSTURE_SECONDS)
                ),
                show_skeleton=bool(data.get("show_skeleton", True)),
                enable_sound=bool(data.get("enable_sound", True)),
                enable_notifications=bool(data.get("enable_notifications", True)),
                minimize_to_tray=bool(data.get("minimize_to_tray", False)),
                autostart=bool(data.get("autostart", False)),
            )
        except (json.JSONDecodeError, TypeError, ValueError):
            return cls()
