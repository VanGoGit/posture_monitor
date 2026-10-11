"""Поиск и выбор камер."""

from __future__ import annotations

import logging
import sys
from collections.abc import Collection
from dataclasses import dataclass

from platform_utils import open_camera

log = logging.getLogger(__name__)


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

        return list(FilterGraph().get_input_devices())
    except Exception:
        log.warning("Не удалось получить имена камер DirectShow", exc_info=True)
        return []


def _probe_camera(index: int) -> bool:
    cap = open_camera(index)
    if not cap.isOpened():
        cap.release()
        return False
    ok, _ = cap.read()
    cap.release()
    return ok


def list_cameras(
    max_index: int = 10, *, assume_available: Collection[int] = ()
) -> list[CameraDevice]:
    """Перебирает индексы камер.

    ``assume_available`` — индексы, которые уже открыты приложением: повторное
    открытие такой камеры обычно не удаётся, поэтому их не проверяем.
    """
    dshow_names = _directshow_names()
    found: list[CameraDevice] = []

    for index in range(max_index):
        if index not in assume_available and not _probe_camera(index):
            continue
        if index < len(dshow_names) and dshow_names[index].strip():
            name = dshow_names[index].strip()
        else:
            name = f"Камера {index}"
        found.append(CameraDevice(index=index, name=name))

    return found


def find_device(devices: list[CameraDevice], index: int) -> CameraDevice | None:
    return next((d for d in devices if d.index == index), None)
