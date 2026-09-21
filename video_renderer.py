"""Отрисовка скелета и предупреждений на кадре камеры."""

from __future__ import annotations

import cv2
import numpy as np

from posture_engine import (
    LEFT_EAR,
    LEFT_SHOULDER,
    PostureMetrics,
    RIGHT_EAR,
    RIGHT_SHOULDER,
    VISIBILITY_MIN,
    _landmark_point,
)

POSE_CONNECTIONS = (
    (0, 1), (1, 2), (2, 3), (3, 7),
    (0, 4), (4, 5), (5, 6), (6, 8),
    (9, 10),
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),
    (11, 23), (12, 24), (23, 24),
    (23, 25), (24, 26), (25, 27), (26, 28),
    (27, 29), (28, 30), (29, 31), (30, 32),
)

COLOR_SKELETON = (80, 200, 120)
COLOR_JOINT = (100, 220, 140)
COLOR_NECK = (100, 255, 255)
COLOR_BACK = (255, 200, 80)
COLOR_ALARM = (55, 55, 240)


def draw_skeleton(frame: np.ndarray, landmarks) -> None:
    h, w = frame.shape[:2]
    points: list[tuple[int, int] | None] = []

    for lm in landmarks:
        if lm.visibility >= VISIBILITY_MIN:
            x, y = _landmark_point(lm, w, h)
            points.append((int(x), int(y)))
        else:
            points.append(None)

    for i, j in POSE_CONNECTIONS:
        if points[i] is not None and points[j] is not None:
            cv2.line(frame, points[i], points[j], COLOR_SKELETON, 2, cv2.LINE_AA)

    for pt in points:
        if pt is not None:
            cv2.circle(frame, pt, 3, COLOR_JOINT, -1, cv2.LINE_AA)


def draw_posture_lines(frame: np.ndarray, landmarks) -> None:
    h, w = frame.shape[:2]

    for shoulder_idx, ear_idx in ((LEFT_SHOULDER, LEFT_EAR), (RIGHT_SHOULDER, RIGHT_EAR)):
        s, e = landmarks[shoulder_idx], landmarks[ear_idx]
        if s.visibility >= VISIBILITY_MIN and e.visibility >= VISIBILITY_MIN:
            p1 = tuple(int(v) for v in _landmark_point(s, w, h))
            p2 = tuple(int(v) for v in _landmark_point(e, w, h))
            cv2.line(frame, p1, p2, COLOR_NECK, 3, cv2.LINE_AA)
            cv2.circle(frame, p1, 5, COLOR_NECK, -1, cv2.LINE_AA)
            cv2.circle(frame, p2, 5, COLOR_NECK, -1, cv2.LINE_AA)

    shoulders, hips = [], []
    for idx in (LEFT_SHOULDER, RIGHT_SHOULDER):
        lm = landmarks[idx]
        if lm.visibility >= VISIBILITY_MIN:
            shoulders.append(_landmark_point(lm, w, h))
    for idx in (23, 24):
        lm = landmarks[idx]
        if lm.visibility >= VISIBILITY_MIN:
            hips.append(_landmark_point(lm, w, h))

    if shoulders and hips:
        mid_s = (
            int(sum(p[0] for p in shoulders) / len(shoulders)),
            int(sum(p[1] for p in shoulders) / len(shoulders)),
        )
        mid_h = (
            int(sum(p[0] for p in hips) / len(hips)),
            int(sum(p[1] for p in hips) / len(hips)),
        )
        cv2.line(frame, mid_s, mid_h, COLOR_BACK, 3, cv2.LINE_AA)
        cv2.circle(frame, mid_s, 5, COLOR_BACK, -1, cv2.LINE_AA)
        cv2.circle(frame, mid_h, 5, COLOR_BACK, -1, cv2.LINE_AA)


def render_frame(
    frame: np.ndarray,
    landmarks,
    metrics: PostureMetrics,
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
