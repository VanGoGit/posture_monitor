"""Тесты реакции на тревогу."""

from __future__ import annotations

from alarm_controller import AlarmController
from config import Settings


class Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def start(self) -> None:
        self.calls.append(("siren_start",))

    def stop(self) -> None:
        self.calls.append(("siren_stop",))

    def show(self, title: str, message: str) -> None:
        self.calls.append(("toast_show", title))

    def hide(self) -> None:
        self.calls.append(("toast_hide",))

    def on_alarm_start(self, *, now: float) -> None:
        self.calls.append(("stats_start", now))

    def on_alarm_end(self, *, now: float) -> None:
        self.calls.append(("stats_end", now))

    def names(self) -> list[str]:
        return [c[0] for c in self.calls]


def make() -> tuple[AlarmController, Recorder]:
    rec = Recorder()
    return AlarmController(rec, rec, rec), rec


def test_alarm_start_and_end():
    controller, rec = make()
    settings = Settings()

    controller.update(True, settings, now=1.0)
    controller.update(True, settings, now=2.0)
    controller.update(False, settings, now=5.0)

    names = rec.names()
    assert names.count("stats_start") == 1
    assert names.count("toast_show") == 1
    assert names.count("stats_end") == 1
    assert names.count("toast_hide") == 1
    assert ("stats_end", 5.0) in rec.calls
    assert not controller.active


def test_sound_disabled_keeps_siren_off():
    controller, rec = make()

    controller.update(True, Settings(enable_sound=False), now=1.0)

    assert "siren_start" not in rec.names()
    assert "siren_stop" in rec.names()


def test_notifications_disabled():
    controller, rec = make()

    controller.update(True, Settings(enable_notifications=False), now=1.0)

    assert "toast_show" not in rec.names()
    assert "stats_start" in rec.names()


def test_finish_closes_episode():
    controller, rec = make()
    controller.update(True, Settings(), now=1.0)

    controller.finish(now=9.0)

    assert ("stats_end", 9.0) in rec.calls
    assert not controller.active


def test_no_alarm_no_side_effects_besides_stop():
    controller, rec = make()

    controller.update(False, Settings(), now=1.0)

    assert rec.names() == ["siren_stop"]
