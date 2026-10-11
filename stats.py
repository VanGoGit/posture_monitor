"""Статистика эпизодов плохой осанки."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from paths import atomic_write_text, data_file

log = logging.getLogger(__name__)


def stats_path() -> Path:
    return data_file("stats.json")


@dataclass
class DayStats:
    events: int = 0
    seconds_bad: float = 0.0


class StatsTracker:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or stats_path()
        self._data: dict[str, dict[str, float | int]] = {}
        self._active_since: float | None = None
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            log.exception("Не удалось прочитать статистику %s", self._path)
            return
        if isinstance(data, dict):
            self._data = data

    def _save(self) -> None:
        try:
            atomic_write_text(self._path, json.dumps(self._data, ensure_ascii=False, indent=2))
        except OSError:
            log.exception("Не удалось сохранить статистику")

    def _today_key(self) -> str:
        return date.today().isoformat()

    def _day(self, key: str) -> DayStats:
        raw = self._data.get(key, {})
        try:
            return DayStats(
                events=int(raw.get("events", 0)),
                seconds_bad=float(raw.get("seconds_bad", 0.0)),
            )
        except (AttributeError, TypeError, ValueError):
            return DayStats()

    def _set_day(self, key: str, stats: DayStats) -> None:
        self._data[key] = {
            "events": stats.events,
            "seconds_bad": round(stats.seconds_bad, 1),
        }

    def on_alarm_start(self, *, now: float) -> None:
        if self._active_since is not None:
            return
        self._active_since = now
        key = self._today_key()
        day = self._day(key)
        day.events += 1
        self._set_day(key, day)
        self._save()

    def on_alarm_end(self, *, now: float) -> None:
        if self._active_since is None:
            return
        elapsed = max(0.0, now - self._active_since)
        self._active_since = None
        key = self._today_key()
        day = self._day(key)
        day.seconds_bad += elapsed
        self._set_day(key, day)
        self._save()

    def today(self) -> DayStats:
        return self._day(self._today_key())

    def last_days(self, count: int = 7) -> list[tuple[str, DayStats]]:
        result: list[tuple[str, DayStats]] = []
        today = date.today()
        for offset in range(count - 1, -1, -1):
            key = (today - timedelta(days=offset)).isoformat()
            result.append((key, self._day(key)))
        return result

    def format_summary(self) -> str:
        today = self.today()
        lines = [
            f"Сегодня: {today.events} срабатываний, {today.seconds_bad:.0f} с в плохой осанке",
            "",
            "Последние 7 дней:",
        ]
        for key, day in self.last_days(7):
            if day.events == 0 and day.seconds_bad == 0:
                lines.append(f"  {key}: —")
            else:
                lines.append(f"  {key}: {day.events} раз, {day.seconds_bad:.0f} с")
        return "\n".join(lines)
