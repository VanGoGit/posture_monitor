"""Поиск и выбор камер."""

from __future__ import annotations

import sys
from dataclasses import dataclass

from platform_utils import open_camera


@dataclass(frozen=True)
class CameraDevice:
    index: int
    name: str

    @property
    def label(self) -> str:
        return f"{self.name} (#{self.index})"


def _directshow_names() -> list[str]:
    if sys.platform != "win32":
        return []
    try:
        from pygrabber.dshow_graph import FilterGraph

        return FilterGraph().get_input_devices()
    except Exception:
        return []


def _probe_camera(index: int) -> bool:
    cap = open_camera(index)
    if not cap.isOpened():
        cap.release()
        return False
    ok, _ = cap.read()
    cap.release()
    return ok


def list_cameras(max_index: int = 10) -> list[CameraDevice]:
    dshow_names = _directshow_names()
    found: list[CameraDevice] = []

    for index in range(max_index):
        if not _probe_camera(index):
            continue
        if index < len(dshow_names) and dshow_names[index].strip():
            name = dshow_names[index].strip()
        else:
            name = f"Камера {index}"
        found.append(CameraDevice(index=index, name=name))

    return found


def find_device(devices: list[CameraDevice], index: int) -> CameraDevice | None:
    return next((d for d in devices if d.index == index), None)
