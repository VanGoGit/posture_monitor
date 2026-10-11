"""Иконка в системном трее."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from PIL import Image, ImageDraw


def create_tray_icon(size: int = 64) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((6, 6, size - 6, size - 6), fill=(48, 108, 198, 255))
    draw.ellipse((18, 16, size - 18, size - 28), fill=(72, 195, 118, 255))
    return img


class TrayIcon:
    def __init__(
        self,
        *,
        on_show: Callable[[], None],
        on_calibrate: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        self._on_show = on_show
        self._on_calibrate = on_calibrate
        self._on_quit = on_quit
        self._icon: Any = None
        self._thread: threading.Thread | None = None

    def start(self) -> bool:
        """Запускает иконку в отдельном потоке; False, если трей недоступен."""
        try:
            import pystray
        except ImportError:
            return False

        menu = pystray.Menu(
            pystray.MenuItem("Показать", lambda _i, _it: self._on_show()),
            pystray.MenuItem("Калибровка", lambda _i, _it: self._on_calibrate()),
            pystray.MenuItem("Выход", lambda _i, _it: self._on_quit()),
        )
        self._icon = pystray.Icon(
            "posture_monitor",
            create_tray_icon(),
            "Монитор осанки",
            menu,
        )
        self._thread = threading.Thread(target=self._icon.run, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        if self._icon is not None:
            self._icon.stop()
            self._icon = None
