"""Статистика эпизодов плохой осанки."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

STATS_PATH = Path(__file__).resolve().parent / "stats.json"


@dataclass
class DayStats:
    events: int = 0
    seconds_bad: float = 0.0


class StatsTracker:
    def __init__(self) -> None:
        self._data: dict[str, dict[str, float | int]] = {}
        self._active_since: float | None = None
        self._load()

    def _load(self) -> None:
        if not STATS_PATH.exists():
            return
        try:
            self._data = json.loads(STATS_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, TypeError):
            self._data = {}

    def _save(self) -> None:
        STATS_PATH.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _today_key(self) -> str:
        return date.today().isoformat()

    def _day(self, key: str) -> DayStats:
        raw = self._data.get(key, {})
        return DayStats(
            events=int(raw.get("events", 0)),
            seconds_bad=float(raw.get("seconds_bad", 0.0)),
        )

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
            f"Сегодня: {today.events} срабатываний, "
            f"{today.seconds_bad:.0f} с в плохой осанке",
            "",
            "Последние 7 дней:",
        ]
        for key, day in self.last_days(7):
            if day.events == 0 and day.seconds_bad == 0:
                lines.append(f"  {key}: —")
            else:
                lines.append(
                    f"  {key}: {day.events} раз, {day.seconds_bad:.0f} с"
                )
        return "\n".join(lines)
