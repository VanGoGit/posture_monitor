"""Детекция позы и оценка осанки через MediaPipe Tasks."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

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
    frame: object  # np.ndarray, typed loosely to avoid circular import noise
    metrics: PostureMetrics
    landmarks: list | None
    posture: PostureState


def angle_from_vertical(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    dist = math.hypot(dx, dy)
    if dist == 0:
        return 0.0
    cos_theta = max(-1.0, min(1.0, -dy / dist))
    return math.degrees(math.acos(cos_theta))


def _landmark_point(landmark, w: int, h: int) -> tuple[float, float]:
    return landmark.x * w, landmark.y * h


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
        self._frame_ts = 0

    def close(self) -> None:
        self._landmarker.close()

    def process(self, frame_bgr) -> tuple[PostureMetrics, list | None]:
        h, w = frame_bgr.shape[:2]
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = Image(image_format=ImageFormat.SRGB, data=rgb)

        self._frame_ts += 33
        result = self._landmarker.detect_for_video(mp_image, self._frame_ts)

        if not result.pose_landmarks:
            return PostureMetrics(), None

        landmarks = result.pose_landmarks[0]
        metrics = self._compute_metrics(landmarks, w, h)
        return metrics, landmarks

    def _compute_metrics(self, landmarks, w: int, h: int) -> PostureMetrics:
        neck_angles: list[float] = []
        for shoulder_idx, ear_idx in (
            (LEFT_SHOULDER, LEFT_EAR),
            (RIGHT_SHOULDER, RIGHT_EAR),
        ):
            shoulder = landmarks[shoulder_idx]
            ear = landmarks[ear_idx]
            if shoulder.visibility >= VISIBILITY_MIN and ear.visibility >= VISIBILITY_MIN:
                p1 = _landmark_point(shoulder, w, h)
                p2 = _landmark_point(ear, w, h)
                neck_angles.append(angle_from_vertical(p1, p2))

        neck_angle = sum(neck_angles) / len(neck_angles) if neck_angles else None

        back_angle = None
        points = []
        for idx in (LEFT_SHOULDER, RIGHT_SHOULDER, LEFT_HIP, RIGHT_HIP):
            lm = landmarks[idx]
            if lm.visibility >= VISIBILITY_MIN:
                points.append((idx, _landmark_point(lm, w, h)))

        shoulders = [p for i, p in points if i in (LEFT_SHOULDER, RIGHT_SHOULDER)]
        hips = [p for i, p in points if i in (LEFT_HIP, RIGHT_HIP)]
        if shoulders and hips:
            mid_shoulder = (
                sum(p[0] for p in shoulders) / len(shoulders),
                sum(p[1] for p in shoulders) / len(shoulders),
            )
            mid_hip = (
                sum(p[0] for p in hips) / len(hips),
                sum(p[1] for p in hips) / len(hips),
            )
            back_angle = angle_from_vertical(mid_shoulder, mid_hip)

        return PostureMetrics(neck_angle=neck_angle, back_angle=back_angle)


def evaluate_posture(
    settings: Settings,
    metrics: PostureMetrics,
    *,
    bad_since: float | None,
) -> tuple[PostureState, float | None]:
    """Возвращает состояние осанки и обновлённый bad_since."""
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

    since = bad_since if bad_since is not None else time.time()
    elapsed = time.time() - since
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
