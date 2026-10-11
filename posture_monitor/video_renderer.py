"""Отрисовка скелета и предупреждений на кадре камеры."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import cv2
import numpy as np

from .posture_engine import (
    VISIBILITY_MIN,
    Point,
    back_segment,
    landmark_point,
    neck_segments,
)

# fmt: off
POSE_CONNECTIONS = (
    (0, 1), (1, 2), (2, 3), (3, 7),
    (0, 4), (4, 5), (5, 6), (6, 8),
    (9, 10),
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),
    (11, 23), (12, 24), (23, 24),
    (23, 25), (24, 26), (25, 27), (26, 28),
    (27, 29), (28, 30), (29, 31), (30, 32),
)
# fmt: on

COLOR_SKELETON = (80, 200, 120)
COLOR_JOINT = (100, 220, 140)
COLOR_NECK = (100, 255, 255)
COLOR_BACK = (255, 200, 80)
COLOR_ALARM = (55, 55, 240)


def _px(point: Point) -> tuple[int, int]:
    return int(point[0]), int(point[1])


def draw_skeleton(frame: np.ndarray, landmarks: Sequence[Any]) -> None:
    h, w = frame.shape[:2]
    points: list[tuple[int, int] | None] = [
        _px(landmark_point(lm, w, h)) if lm.visibility >= VISIBILITY_MIN else None
        for lm in landmarks
    ]

    for i, j in POSE_CONNECTIONS:
        p1, p2 = points[i], points[j]
        if p1 is not None and p2 is not None:
            cv2.line(frame, p1, p2, COLOR_SKELETON, 2, cv2.LINE_AA)

    for pt in points:
        if pt is not None:
            cv2.circle(frame, pt, 3, COLOR_JOINT, -1, cv2.LINE_AA)


def _draw_segment(frame: np.ndarray, p1: Point, p2: Point, color: tuple[int, int, int]) -> None:
    a, b = _px(p1), _px(p2)
    cv2.line(frame, a, b, color, 3, cv2.LINE_AA)
    cv2.circle(frame, a, 5, color, -1, cv2.LINE_AA)
    cv2.circle(frame, b, 5, color, -1, cv2.LINE_AA)


def draw_posture_lines(frame: np.ndarray, landmarks: Sequence[Any]) -> None:
    h, w = frame.shape[:2]
    for shoulder, ear in neck_segments(landmarks, w, h):
        _draw_segment(frame, shoulder, ear, COLOR_NECK)
    back = back_segment(landmarks, w, h)
    if back is not None:
        _draw_segment(frame, *back, COLOR_BACK)


def render_frame(
    frame: np.ndarray,
    landmarks: Sequence[Any] | None,
    *,
    show_skeleton: bool,
    alarm_active: bool,
) -> np.ndarray:
    output = frame.copy()

    if landmarks is not None:
        if show_skeleton:
            draw_skeleton(output, landmarks)
        draw_posture_lines(output, landmarks)

    if alarm_active:
        cv2.rectangle(output, (0, 0), (output.shape[1] - 1, output.shape[0] - 1), COLOR_ALARM, 10)

    return output
