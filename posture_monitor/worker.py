"""Фоновый поток захвата камеры и детекции позы.

Обмен с GUI идёт только через очереди: GUI шлёт команды, поток — результаты.
У потока своя копия настроек, поэтому общего изменяемого состояния нет.
"""

from __future__ import annotations

import contextlib
import logging
import queue
import threading
import time
from dataclasses import dataclass, replace
from typing import Any

import cv2

from .config import Settings
from .platform_utils import open_camera
from .posture_engine import FrameResult, PoseEngine, evaluate_posture
from .video_renderer import render_frame

log = logging.getLogger(__name__)

CAMERA_RETRY_SECONDS = 2.0
MAX_READ_FAILURES = 30


# --- Команды GUI → поток ---


@dataclass(frozen=True)
class ResetBadPosture:
    """Сбросить таймер плохой осанки (после калибровки)."""


@dataclass(frozen=True)
class SwitchCamera:
    index: int


@dataclass(frozen=True)
class UpdateSettings:
    settings: Settings


WorkerCommand = ResetBadPosture | SwitchCamera | UpdateSettings


# --- Сообщения поток → GUI ---


@dataclass(frozen=True)
class CameraWaiting:
    """Камера недоступна, поток пытается переподключиться."""


@dataclass(frozen=True)
class CameraSwitchFailed:
    index: int


WorkerMessage = FrameResult | CameraWaiting | CameraSwitchFailed


class CameraWorker(threading.Thread):
    def __init__(
        self,
        engine: PoseEngine,
        settings: Settings,
        result_queue: queue.Queue[WorkerMessage],
        command_queue: queue.Queue[WorkerCommand],
        stop_event: threading.Event,
    ) -> None:
        super().__init__(daemon=True, name="CameraWorker")
        self._engine = engine
        self._settings = replace(settings)
        self._result_queue = result_queue
        self._command_queue = command_queue
        self._stop_event = stop_event
        self._bad_since: float | None = None
        self._waiting_sent = False
        self._read_failures = 0

    def _post(self, message: WorkerMessage) -> None:
        with contextlib.suppress(queue.Full):
            self._result_queue.put_nowait(message)

    def _open_camera(self, index: int) -> Any:
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

    @staticmethod
    def _release_camera(cap: Any) -> None:
        if cap is not None:
            cap.release()

    def _notify_waiting(self) -> None:
        if self._waiting_sent:
            return
        self._waiting_sent = True
        self._post(CameraWaiting())

    def _notify_connected(self) -> None:
        self._waiting_sent = False

    def _try_switch_camera(self, cap: Any, new_index: int) -> Any:
        new_cap = self._open_camera(new_index)
        if new_cap is None:
            log.warning("Не удалось открыть камеру #%s", new_index)
            self._post(CameraSwitchFailed(new_index))
            self._notify_waiting()
            return cap

        self._release_camera(cap)
        self._settings.camera_index = new_index
        self._bad_since = None
        self._notify_connected()
        return new_cap

    def _drain_commands(self, cap: Any) -> Any:
        while True:
            try:
                cmd = self._command_queue.get_nowait()
            except queue.Empty:
                break

            if isinstance(cmd, ResetBadPosture):
                self._bad_since = None
            elif isinstance(cmd, SwitchCamera):
                cap = self._try_switch_camera(cap, cmd.index)
            elif isinstance(cmd, UpdateSettings):
                # Индекс камеры меняется только через SwitchCamera.
                self._settings = replace(cmd.settings, camera_index=self._settings.camera_index)
        return cap

    def run(self) -> None:
        cap = self._open_camera(self._settings.camera_index)
        if cap is None:
            self._notify_waiting()

        last_retry = 0.0

        try:
            while not self._stop_event.is_set():
                cap = self._drain_commands(cap)

                if cap is None:
                    now = time.monotonic()
                    if now - last_retry >= CAMERA_RETRY_SECONDS:
                        cap = self._open_camera(self._settings.camera_index)
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
                        log.warning("Камера перестала отдавать кадры, переподключение")
                        self._release_camera(cap)
                        cap = None
                        self._read_failures = 0
                        self._notify_waiting()
                    time.sleep(0.05)
                    continue

                self._read_failures = 0
                self._process_frame(cv2.flip(frame, 1))
        except Exception:
            log.exception("Сбой в потоке камеры")
        finally:
            self._release_camera(cap)

    def _process_frame(self, frame: Any) -> None:
        settings = self._settings
        metrics, landmarks = self._engine.process(frame)
        posture, self._bad_since = evaluate_posture(
            settings, metrics, bad_since=self._bad_since, now=time.monotonic()
        )

        rendered = render_frame(
            frame,
            landmarks,
            show_skeleton=settings.show_skeleton,
            alarm_active=posture.alarm_active,
        )

        self._notify_connected()
        self._post(
            FrameResult(frame=rendered, metrics=metrics, landmarks=landmarks, posture=posture)
        )
