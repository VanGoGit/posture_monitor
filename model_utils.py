"""Загрузка модели Pose Landmarker."""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

MODEL_NAME = "pose_landmarker_lite.task"
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"
)


def _app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _model_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        bundled = Path(sys._MEIPASS) / "models"
        if (bundled / MODEL_NAME).exists():
            return bundled
    return _app_dir() / "models"


def ensure_model() -> Path:
    model_dir = _model_dir()
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_dir / MODEL_NAME
    if model_path.exists() and model_path.stat().st_size > 0:
        return model_path

    print("Скачиваю модель Pose Landmarker (~6 МБ)...")
    tmp_path = model_path.with_suffix(".tmp")
    urllib.request.urlretrieve(MODEL_URL, tmp_path)
    tmp_path.replace(model_path)
    print(f"Модель сохранена: {model_path}")
    return model_path
