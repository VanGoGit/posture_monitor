"""Звуковой сигнал при плохой осанке (кросс-платформенный)."""

from __future__ import annotations

import math
import os
import struct
import subprocess
import sys
import tempfile
import threading
import time
import wave


class AlarmSiren:
    def __init__(self, *, freq: int = 1000, chunk_ms: int = 200) -> None:
        self._freq = freq
        self._chunk_ms = chunk_ms
        self._on = threading.Event()
        self._stop_program = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _write_tone_wav(self, path: str) -> None:
        sample_rate = 44100
        samples = int(sample_rate * self._chunk_ms / 1000)
        amplitude = 9000

        with wave.open(path, "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            frames = bytearray()
            for i in range(samples):
                value = int(
                    amplitude * math.sin(2 * math.pi * self._freq * i / sample_rate)
                )
                frames.extend(struct.pack("<h", value))
            wf.writeframes(frames)

    def _beep(self) -> None:
        if sys.platform == "win32":
            import winsound

            winsound.Beep(self._freq, self._chunk_ms)
            return

        path = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                path = tmp.name
            self._write_tone_wav(path)

            if sys.platform == "darwin":
                subprocess.run(
                    ["afplay", path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            else:
                for player in (["paplay", path], ["aplay", "-q", path]):
                    try:
                        subprocess.run(
                            player,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            check=False,
                        )
                        break
                    except FileNotFoundError:
                        continue
                else:
                    print("\a", end="", flush=True)
                    time.sleep(self._chunk_ms / 1000)
        except Exception:
            print("\a", end="", flush=True)
            time.sleep(self._chunk_ms / 1000)
        finally:
            if path and os.path.exists(path):
                os.unlink(path)

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
