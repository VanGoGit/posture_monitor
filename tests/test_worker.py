"""Тесты потока камеры с подменённой камерой и моделью."""

from __future__ import annotations

import queue
import threading
import time

import numpy as np
import pytest

import worker as worker_module
from config import Settings
from posture_engine import FrameResult, PostureMetrics
from worker import (
    CameraSwitchFailed,
    CameraWaiting,
    CameraWorker,
    SwitchCamera,
    UpdateSettings,
)


class FakeCapture:
    def __init__(self, ok: bool = True) -> None:
        self._ok = ok
        self.released = False

    def isOpened(self) -> bool:
        return self._ok

    def read(self):
        time.sleep(0.005)
        return self._ok, np.zeros((48, 64, 3), dtype=np.uint8)

    def release(self) -> None:
        self.released = True


class FakeEngine:
    def process(self, frame):
        return PostureMetrics(neck_angle=30.0, back_angle=1.0), None


def run_worker(monkeypatch, cameras: dict[int, bool], settings: Settings):
    captures: list[FakeCapture] = []

    def fake_open(index: int) -> FakeCapture:
        cap = FakeCapture(cameras.get(index, False))
        captures.append(cap)
        return cap

    monkeypatch.setattr(worker_module, "open_camera", fake_open)
    results: queue.Queue = queue.Queue(maxsize=100)
    commands: queue.Queue = queue.Queue()
    stop = threading.Event()
    w = CameraWorker(FakeEngine(), settings, results, commands, stop)  # type: ignore[arg-type]
    w.start()
    return w, results, commands, stop, captures


def wait_for(results: queue.Queue, kind: type, timeout: float = 2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            item = results.get(timeout=0.05)
        except queue.Empty:
            continue
        if isinstance(item, kind):
            return item
    pytest.fail(f"Не дождались {kind.__name__}")


def stop_worker(w, stop) -> None:
    stop.set()
    w.join(timeout=2)
    assert not w.is_alive()


def test_worker_produces_frames(monkeypatch):
    w, results, _, stop, captures = run_worker(monkeypatch, {0: True}, Settings())
    try:
        item = wait_for(results, FrameResult)
        assert item.metrics.neck_angle == 30.0
        assert item.posture.posture_ok is None  # не откалибровано
    finally:
        stop_worker(w, stop)
    assert captures[0].released


def test_worker_reports_waiting_without_camera(monkeypatch):
    w, results, _, stop, _ = run_worker(monkeypatch, {}, Settings())
    try:
        wait_for(results, CameraWaiting)
    finally:
        stop_worker(w, stop)


def test_worker_switch_to_missing_camera_fails(monkeypatch):
    w, results, commands, stop, _ = run_worker(monkeypatch, {0: True}, Settings())
    try:
        wait_for(results, FrameResult)
        commands.put(SwitchCamera(5))
        failed = wait_for(results, CameraSwitchFailed)
        assert failed.index == 5
    finally:
        stop_worker(w, stop)


def test_worker_applies_settings_update(monkeypatch):
    w, results, commands, stop, _ = run_worker(monkeypatch, {0: True}, Settings())
    try:
        wait_for(results, FrameResult)
        commands.put(
            UpdateSettings(Settings(baseline_neck=10.0, delta_degrees=5, bad_posture_seconds=0.0))
        )
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            item = wait_for(results, FrameResult)
            if item.posture.alarm_active:
                break
        else:
            pytest.fail("Настройки не применились")
    finally:
        stop_worker(w, stop)
