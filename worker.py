"""Фоновый поток захвата камеры и детекции позы."""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass, replace

import cv2

from config import Settings
from platform_utils import open_camera
from posture_engine import FrameResult, PoseEngine, evaluate_posture
from video_renderer import render_frame

CAMERA_RETRY_SECONDS = 2.0
MAX_READ_FAILURES = 30


@dataclass
class WorkerCommand:
    kind: str
    value: object = None


class CameraWorker(threading.Thread):
    def __init__(
        self,
        engine: PoseEngine,
        settings: Settings,
        result_queue: queue.Queue,
        command_queue: queue.Queue[WorkerCommand],
        stop_event: threading.Event,
    ) -> None:
        super().__init__(daemon=True)
        self._engine = engine
        self._settings = settings
        self._result_queue = result_queue
        self._command_queue = command_queue
        self._stop_event = stop_event
        self._bad_since: float | None = None
        self._settings_lock = threading.Lock()
        self._waiting_sent = False
        self._read_failures = 0

    def _read_settings(self) -> Settings:
        with self._settings_lock:
            return replace(self._settings)

    def _open_camera(self, index: int):
        cap = open_camera(index)
        if not cap.isOpened():
            cap.release()
            return None
        ok, _ = cap.read()
        if not ok:
            cap.release()
            return None
        self._read_failures = 0
        return cap

    def _release_camera(self, cap) -> None:
        if cap is not None:
            cap.release()

    def _notify_waiting(self) -> None:
        if self._waiting_sent:
            return
        self._waiting_sent = True
        try:
            self._result_queue.put_nowait("status:camera_waiting")
        except queue.Full:
            pass

    def _notify_connected(self) -> None:
        self._waiting_sent = False

    def _try_switch_camera(self, cap, new_index: int):
        new_cap = self._open_camera(new_index)
        if new_cap is None:
            try:
                self._result_queue.put_nowait(f"camera_error:{new_index}")
            except queue.Full:
                pass
            self._notify_waiting()
            return cap

        self._release_camera(cap)
        with self._settings_lock:
            self._settings.camera_index = new_index
        self._bad_since = None
        self._notify_connected()
        return new_cap

    def _drain_commands(self, cap):
        while True:
            try:
                cmd = self._command_queue.get_nowait()
            except queue.Empty:
                break

            if cmd.kind == "reset_bad":
                self._bad_since = None
            elif cmd.kind == "camera":
                cap = self._try_switch_camera(cap, int(cmd.value))
        return cap

    def run(self) -> None:
        settings = self._read_settings()
        cap = self._open_camera(settings.camera_index)
        if cap is None:
            self._notify_waiting()

        last_retry = 0.0

        while not self._stop_event.is_set():
            cap = self._drain_commands(cap)

            if cap is None:
                now = time.time()
                if now - last_retry >= CAMERA_RETRY_SECONDS:
                    settings = self._read_settings()
                    cap = self._open_camera(settings.camera_index)
                    last_retry = now
                    if cap is not None:
                        self._notify_connected()
                    else:
                        self._notify_waiting()
                time.sleep(0.1)
                continue

            ok, frame = cap.read()
            if not ok:
                self._read_failures += 1
                if self._read_failures >= MAX_READ_FAILURES:
                    self._release_camera(cap)
                    cap = None
                    self._read_failures = 0
                    self._notify_waiting()
                time.sleep(0.05)
                continue

            self._read_failures = 0
            frame = cv2.flip(frame, 1)
            settings = self._read_settings()
            metrics, landmarks = self._engine.process(frame)
            posture, self._bad_since = evaluate_posture(
                settings, metrics, bad_since=self._bad_since
            )

            rendered = render_frame(
                frame,
                landmarks,
                metrics,
                show_skeleton=settings.show_skeleton,
                alarm_active=posture.alarm_active,
            )

            self._notify_connected()
            try:
                self._result_queue.put_nowait(
                    FrameResult(
                        frame=rendered,
                        metrics=metrics,
                        landmarks=landmarks,
                        posture=posture,
                    )
                )
            except queue.Full:
                pass

        self._release_camera(cap)
