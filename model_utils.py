"""Загрузка модели Pose Landmarker."""

from __future__ import annotations

import hashlib
import logging
import sys
import urllib.request
from pathlib import Path

from paths import app_dir

log = logging.getLogger(__name__)

MODEL_NAME = "pose_landmarker_lite.task"
# Фиксированная версия модели (не «latest»), чтобы контрольная сумма не менялась.
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
)
MODEL_SHA256 = "59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a"
DOWNLOAD_TIMEOUT_SECONDS = 30


class ModelDownloadError(RuntimeError):
    pass


def _model_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        bundled = Path(sys._MEIPASS) / "models"
        if (bundled / MODEL_NAME).exists():
            return bundled
    return app_dir() / "models"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_model() -> Path:
    model_dir = _model_dir()
    model_path = model_dir / MODEL_NAME
    if model_path.exists() and model_path.stat().st_size > 0:
        return model_path

    model_dir.mkdir(parents=True, exist_ok=True)
    log.info("Скачиваю модель Pose Landmarker: %s", MODEL_URL)
    tmp_path = model_path.with_suffix(".tmp")
    try:
        with urllib.request.urlopen(MODEL_URL, timeout=DOWNLOAD_TIMEOUT_SECONDS) as resp:
            tmp_path.write_bytes(resp.read())
        actual = _sha256(tmp_path)
        if actual != MODEL_SHA256:
            raise ModelDownloadError(f"Контрольная сумма модели не совпала: {actual}")
        tmp_path.replace(model_path)
    except ModelDownloadError:
        tmp_path.unlink(missing_ok=True)
        raise
    except OSError as exc:
        tmp_path.unlink(missing_ok=True)
        raise ModelDownloadError(f"Не удалось скачать модель: {exc}") from exc

    log.info("Модель сохранена: %s", model_path)
    return model_path
