"""Звуковой сигнал при плохой осанке (кросс-платформенный)."""

from __future__ import annotations

import atexit
import contextlib
import logging
import math
import os
import struct
import subprocess
import sys
import tempfile
import threading
import time
import wave

log = logging.getLogger(__name__)


class AlarmSiren:
    def __init__(self, *, freq: int = 1000, chunk_ms: int = 200) -> None:
        self._freq = freq
        self._chunk_ms = chunk_ms
        self._wav_path: str | None = None
        self._player: list[str] | None = None
        self._on = threading.Event()
        self._stop_program = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="AlarmSiren")
        self._thread.start()

    def _write_tone_wav(self, path: str) -> None:
        sample_rate = 44100
        samples = int(sample_rate * self._chunk_ms / 1000)
        amplitude = 9000

        frames = b"".join(
            struct.pack("<h", int(amplitude * math.sin(2 * math.pi * self._freq * i / sample_rate)))
            for i in range(samples)
        )
        with wave.open(path, "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(frames)

    def _tone_file(self) -> str:
        """WAV генерируется один раз и удаляется при выходе."""
        if self._wav_path is None:
            fd, path = tempfile.mkstemp(suffix=".wav", prefix="posture_alarm_")
            os.close(fd)
            self._write_tone_wav(path)
            self._wav_path = path
            atexit.register(self._cleanup)
        return self._wav_path

    def _cleanup(self) -> None:
        if self._wav_path and os.path.exists(self._wav_path):
            with contextlib.suppress(OSError):
                os.unlink(self._wav_path)

    def _player_candidates(self, path: str) -> list[list[str]]:
        if sys.platform == "darwin":
            return [["afplay", path]]
        return [["paplay", path], ["aplay", "-q", path]]

    def _fallback_beep(self) -> None:
        print("\a", end="", flush=True)
        time.sleep(self._chunk_ms / 1000)

    def _beep(self) -> None:
        if sys.platform == "win32":
            import winsound

            winsound.Beep(self._freq, self._chunk_ms)
            return

        try:
            path = self._tone_file()
            candidates = [self._player] if self._player else self._player_candidates(path)
            for player in candidates:
                try:
                    subprocess.run(
                        player,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
                    self._player = player
                    return
                except FileNotFoundError:
                    continue
        except Exception:
            log.exception("Не удалось воспроизвести звук")
        self._fallback_beep()

    def _run(self) -> None:
        while not self._stop_program.is_set():
            if self._on.is_set():
                self._beep()
            else:
                time.sleep(0.05)

    def start(self) -> None:
        self._on.set()

    def stop(self) -> None:
        self._on.clear()

    def shutdown(self) -> None:
        self._on.clear()
        self._stop_program.set()
        self._thread.join(timeout=1.0)
        self._cleanup()
