"""Детекция позы и оценка осанки через MediaPipe Tasks."""

from __future__ import annotations

import math
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import cv2
from mediapipe.tasks.python.core.base_options import BaseOptions
from mediapipe.tasks.python.vision.core.image import Image, ImageFormat
from mediapipe.tasks.python.vision.core.vision_task_running_mode import (
    VisionTaskRunningMode,
)
from mediapipe.tasks.python.vision.pose_landmarker import (
    PoseLandmarker,
    PoseLandmarkerOptions,
)

from config import Settings

# Индексы landmarks MediaPipe Pose
LEFT_SHOULDER = 11
RIGHT_SHOULDER = 12
LEFT_EAR = 7
RIGHT_EAR = 8
LEFT_HIP = 23
RIGHT_HIP = 24

VISIBILITY_MIN = 0.5

Point = tuple[float, float]


@dataclass
class PostureMetrics:
    neck_angle: float | None = None
    back_angle: float | None = None

    @property
    def display_neck(self) -> str:
        return f"{self.neck_angle:.1f}°" if self.neck_angle is not None else "—"

    @property
    def display_back(self) -> str:
        return f"{self.back_angle:.1f}°" if self.back_angle is not None else "—"

    @property
    def is_valid(self) -> bool:
        return self.neck_angle is not None or self.back_angle is not None


@dataclass
class PostureState:
    posture_ok: bool | None = None
    alarm_active: bool = False
    bad_elapsed: float = 0.0


@dataclass
class FrameResult:
    frame: Any  # np.ndarray
    metrics: PostureMetrics
    landmarks: Sequence[Any] | None
    posture: PostureState


def angle_from_vertical(p1: Point, p2: Point) -> float:
    """Угол (0–180°) вектора p1→p2 относительно направления «вверх» на экране.

    Ось Y изображения направлена вниз, поэтому «вверх» — это отрицательный dy.
    """
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    dist = math.hypot(dx, dy)
    if dist == 0:
        return 0.0
    cos_theta = max(-1.0, min(1.0, -dy / dist))
    return math.degrees(math.acos(cos_theta))


def landmark_point(landmark: Any, w: int, h: int) -> Point:
    return landmark.x * w, landmark.y * h


def _visible(landmark: Any) -> bool:
    return landmark.visibility >= VISIBILITY_MIN


def _midpoint(points: list[Point]) -> Point:
    return (
        sum(p[0] for p in points) / len(points),
        sum(p[1] for p in points) / len(points),
    )


def neck_segments(landmarks: Sequence[Any], w: int, h: int) -> list[tuple[Point, Point]]:
    """Видимые отрезки плечо → ухо (левый и/или правый)."""
    segments = []
    for shoulder_idx, ear_idx in ((LEFT_SHOULDER, LEFT_EAR), (RIGHT_SHOULDER, RIGHT_EAR)):
        shoulder, ear = landmarks[shoulder_idx], landmarks[ear_idx]
        if _visible(shoulder) and _visible(ear):
            segments.append((landmark_point(shoulder, w, h), landmark_point(ear, w, h)))
    return segments


def back_segment(landmarks: Sequence[Any], w: int, h: int) -> tuple[Point, Point] | None:
    """Отрезок середина таза → середина плеч (направлен вверх по спине)."""
    shoulders = [
        landmark_point(landmarks[i], w, h)
        for i in (LEFT_SHOULDER, RIGHT_SHOULDER)
        if _visible(landmarks[i])
    ]
    hips = [
        landmark_point(landmarks[i], w, h) for i in (LEFT_HIP, RIGHT_HIP) if _visible(landmarks[i])
    ]
    if not shoulders or not hips:
        return None
    return _midpoint(hips), _midpoint(shoulders)


def compute_metrics(landmarks: Sequence[Any], w: int, h: int) -> PostureMetrics:
    neck_angles = [angle_from_vertical(s, e) for s, e in neck_segments(landmarks, w, h)]
    neck_angle = sum(neck_angles) / len(neck_angles) if neck_angles else None

    back = back_segment(landmarks, w, h)
    back_angle = angle_from_vertical(*back) if back is not None else None

    return PostureMetrics(neck_angle=neck_angle, back_angle=back_angle)


class PoseEngine:
    def __init__(self, model_path: str) -> None:
        options = PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=model_path),
            running_mode=VisionTaskRunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self._landmarker = PoseLandmarker.create_from_options(options)
        self._last_ts_ms = -1

    def close(self) -> None:
        self._landmarker.close()

    def process(self, frame_bgr: Any) -> tuple[PostureMetrics, Sequence[Any] | None]:
        h, w = frame_bgr.shape[:2]
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = Image(image_format=ImageFormat.SRGB, data=rgb)

        # Реальное время кадра: трекинг MediaPipe учитывает интервалы между кадрами.
        ts_ms = max(int(time.monotonic() * 1000), self._last_ts_ms + 1)
        self._last_ts_ms = ts_ms
        result = self._landmarker.detect_for_video(mp_image, ts_ms)

        if not result.pose_landmarks:
            return PostureMetrics(), None

        landmarks = result.pose_landmarks[0]
        return compute_metrics(landmarks, w, h), landmarks


def evaluate_posture(
    settings: Settings,
    metrics: PostureMetrics,
    *,
    bad_since: float | None,
    now: float,
) -> tuple[PostureState, float | None]:
    """Возвращает состояние осанки и обновлённый bad_since.

    ``now`` и ``bad_since`` — значения монотонных часов (time.monotonic()).
    """
    if settings.baseline_neck is None or not metrics.is_valid:
        return PostureState(posture_ok=None, alarm_active=False, bad_elapsed=0.0), None

    neck_bad = (
        metrics.neck_angle is not None
        and metrics.neck_angle > settings.baseline_neck + settings.delta_degrees
    )
    back_bad = (
        settings.baseline_back is not None
        and metrics.back_angle is not None
        and metrics.back_angle > settings.baseline_back + settings.delta_degrees
    )

    if not neck_bad and not back_bad:
        return PostureState(posture_ok=True, alarm_active=False, bad_elapsed=0.0), None

    since = bad_since if bad_since is not None else now
    elapsed = now - since
    if elapsed >= settings.bad_posture_seconds:
        return (
            PostureState(posture_ok=False, alarm_active=True, bad_elapsed=elapsed),
            since,
        )

    return (
        PostureState(posture_ok=False, alarm_active=False, bad_elapsed=elapsed),
        since,
    )


def calibrate(settings: Settings, metrics: PostureMetrics) -> bool:
    if not metrics.is_valid:
        return False
    if metrics.neck_angle is not None:
        settings.baseline_neck = metrics.neck_angle
    if metrics.back_angle is not None:
        settings.baseline_back = metrics.back_angle
    settings.save()
    return True
