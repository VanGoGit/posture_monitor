"""Реакция на тревогу: звук, уведомление, статистика.

Вынесено из GUI, чтобы логику переходов можно было тестировать без Tk.
"""

from __future__ import annotations

from typing import Protocol

from config import Settings

ALARM_TITLE = "Вы сутулитесь!"
ALARM_MESSAGE = "Выпрямите спину и поднимите голову."


class Siren(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...


class Toast(Protocol):
    def show(self, title: str, message: str) -> None: ...
    def hide(self) -> None: ...


class AlarmStats(Protocol):
    def on_alarm_start(self, *, now: float) -> None: ...
    def on_alarm_end(self, *, now: float) -> None: ...


class AlarmController:
    def __init__(self, siren: Siren, toast: Toast, stats: AlarmStats) -> None:
        self._siren = siren
        self._toast = toast
        self._stats = stats
        self._active = False

    @property
    def active(self) -> bool:
        return self._active

    def update(self, alarm_active: bool, settings: Settings, *, now: float) -> None:
        started = alarm_active and not self._active
        ended = not alarm_active and self._active

        if alarm_active:
            if started:
                self._stats.on_alarm_start(now=now)
                if settings.enable_notifications:
                    self._toast.show(ALARM_TITLE, ALARM_MESSAGE)
            if settings.enable_sound:
                self._siren.start()
            else:
                self._siren.stop()
        else:
            self._siren.stop()
            if ended:
                self._stats.on_alarm_end(now=now)
                self._toast.hide()

        self._active = alarm_active

    def finish(self, *, now: float) -> None:
        """Закрыть текущий эпизод (при выходе из приложения)."""
        if self._active:
            self._stats.on_alarm_end(now=now)
        self._siren.stop()
        self._active = False
