"""Логирование в файл (в exe без консоли иначе ошибки не видны)."""

from __future__ import annotations

import logging
import sys
import threading
from logging.handlers import RotatingFileHandler
from types import TracebackType

from paths import user_data_dir


def setup_logging() -> None:
    log_path = user_data_dir() / "posture_monitor.log"
    handlers: list[logging.Handler] = [
        RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    ]
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(threadName)s %(name)s: %(message)s",
        handlers=handlers,
    )
    # comtypes (имена камер DirectShow) пишет много служебного INFO.
    logging.getLogger("comtypes").setLevel(logging.WARNING)

    def _excepthook(
        exc_type: type[BaseException], exc: BaseException, tb: TracebackType | None
    ) -> None:
        logging.getLogger("unhandled").critical(
            "Необработанное исключение", exc_info=(exc_type, exc, tb)
        )

    def _thread_excepthook(args: threading.ExceptHookArgs) -> None:
        logging.getLogger("unhandled").critical(
            "Необработанное исключение в потоке %s",
            args.thread.name if args.thread else "?",
            exc_info=args.exc_value or True,
        )

    sys.excepthook = _excepthook
    threading.excepthook = _thread_excepthook
