"""Runtime hook: заглушка matplotlib для MediaPipe в frozen-сборке.

MediaPipe импортирует vision.drawing_utils → matplotlib,
хотя приложение рисует скелет самостоятельно через OpenCV.
"""

from __future__ import annotations

import sys
from types import ModuleType


class _StubModule(ModuleType):
    def __getattr__(self, item: str):
        if item.startswith("_"):
            raise AttributeError(item)
        full_name = f"{self.__name__}.{item}"
        module = _StubModule(full_name)
        sys.modules[full_name] = module
        setattr(self, item, module)
        return module


def _install() -> None:
    if "matplotlib" in sys.modules:
        return
    matplotlib = _StubModule("matplotlib")
    pyplot = _StubModule("matplotlib.pyplot")
    matplotlib.pyplot = pyplot
    sys.modules["matplotlib"] = matplotlib
    sys.modules["matplotlib.pyplot"] = pyplot


_install()
