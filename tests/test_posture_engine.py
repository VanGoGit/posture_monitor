"""Тесты алгоритма осанки."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from config import Settings
from posture_engine import (
    LEFT_EAR,
    LEFT_HIP,
    LEFT_SHOULDER,
    RIGHT_EAR,
    RIGHT_HIP,
    RIGHT_SHOULDER,
    PostureMetrics,
    PostureState,
    angle_from_vertical,
    compute_metrics,
    evaluate_posture,
)

W, H = 1000, 1000


def make_landmarks(points: dict[int, tuple[float, float]], visibility: float = 0.9) -> list:
    """33 точки MediaPipe; заданные — в пикселях кадра W×H, остальные невидимы."""
    landmarks = [SimpleNamespace(x=0.0, y=0.0, visibility=0.0) for _ in range(33)]
    for idx, (x, y) in points.items():
        landmarks[idx] = SimpleNamespace(x=x / W, y=y / H, visibility=visibility)
    return landmarks


def upright_body(*, lean_px: float = 0.0) -> dict[int, tuple[float, float]]:
    """Ровная фигура; lean_px смещает плечи и уши вбок (наклон корпуса)."""
    return {
        LEFT_HIP: (450, 800),
        RIGHT_HIP: (550, 800),
        LEFT_SHOULDER: (400 + lean_px, 400),
        RIGHT_SHOULDER: (600 + lean_px, 400),
        LEFT_EAR: (420 + lean_px, 250),
        RIGHT_EAR: (580 + lean_px, 250),
    }


def test_angle_from_vertical_straight_up():
    assert angle_from_vertical((100, 200), (100, 50)) == 0.0


def test_angle_from_vertical_tilted():
    angle = angle_from_vertical((100, 200), (150, 200))
    assert angle == pytest.approx(90.0)


def test_angle_from_vertical_degenerate():
    assert angle_from_vertical((5, 5), (5, 5)) == 0.0


def test_compute_metrics_upright_back_is_near_zero():
    metrics = compute_metrics(make_landmarks(upright_body()), W, H)

    assert metrics.back_angle == pytest.approx(0.0, abs=0.01)
    assert metrics.neck_angle is not None
    assert metrics.neck_angle < 10


def test_compute_metrics_back_angle_grows_with_lean():
    straight = compute_metrics(make_landmarks(upright_body()), W, H)
    leaning = compute_metrics(make_landmarks(upright_body(lean_px=100)), W, H)

    assert straight.back_angle is not None and leaning.back_angle is not None
    assert leaning.back_angle > straight.back_angle + 10


def test_back_alarm_triggers_after_calibration():
    """Регрессия: раньше угол спины считался от 180° и порог не достигался никогда."""
    settings = Settings(delta_degrees=5, bad_posture_seconds=0.0)
    settings.baseline_neck = compute_metrics(make_landmarks(upright_body()), W, H).neck_angle
    settings.baseline_back = compute_metrics(make_landmarks(upright_body()), W, H).back_angle

    leaning = compute_metrics(make_landmarks(upright_body(lean_px=100)), W, H)
    state, _ = evaluate_posture(settings, leaning, bad_since=None, now=100.0)

    assert state.alarm_active is True


def test_compute_metrics_ignores_invisible_points():
    metrics = compute_metrics(make_landmarks(upright_body(), visibility=0.1), W, H)

    assert metrics == PostureMetrics(neck_angle=None, back_angle=None)
    assert not metrics.is_valid


def test_compute_metrics_one_side_visible():
    points = {k: v for k, v in upright_body().items() if k in (LEFT_SHOULDER, LEFT_EAR, LEFT_HIP)}
    metrics = compute_metrics(make_landmarks(points), W, H)

    assert metrics.neck_angle is not None
    assert metrics.back_angle is not None


def test_evaluate_posture_not_calibrated():
    state, bad_since = evaluate_posture(
        Settings(), PostureMetrics(neck_angle=30.0), bad_since=None, now=10.0
    )

    assert state.posture_ok is None
    assert bad_since is None


def test_evaluate_posture_ok_when_calibrated_and_within_threshold():
    settings = Settings(baseline_neck=10.0, baseline_back=5.0, delta_degrees=10)
    metrics = PostureMetrics(neck_angle=15.0, back_angle=8.0)

    state, bad_since = evaluate_posture(settings, metrics, bad_since=None, now=10.0)

    assert state == PostureState(posture_ok=True, alarm_active=False, bad_elapsed=0.0)
    assert bad_since is None


def test_evaluate_posture_starts_timer():
    settings = Settings(baseline_neck=10.0, delta_degrees=5, bad_posture_seconds=2.0)

    state, bad_since = evaluate_posture(
        settings, PostureMetrics(neck_angle=30.0), bad_since=None, now=50.0
    )

    assert state.posture_ok is False
    assert state.alarm_active is False
    assert bad_since == 50.0


def test_evaluate_posture_alarm_after_delay():
    settings = Settings(
        baseline_neck=10.0,
        baseline_back=5.0,
        delta_degrees=5,
        bad_posture_seconds=2.0,
    )
    metrics = PostureMetrics(neck_angle=30.0, back_angle=8.0)

    state, bad_since = evaluate_posture(settings, metrics, bad_since=97.0, now=100.0)

    assert state.posture_ok is False
    assert state.alarm_active is True
    assert bad_since == 97.0


def test_evaluate_posture_waiting_before_delay():
    settings = Settings(
        baseline_neck=10.0,
        baseline_back=5.0,
        delta_degrees=5,
        bad_posture_seconds=5.0,
    )
    metrics = PostureMetrics(neck_angle=30.0, back_angle=8.0)

    state, bad_since = evaluate_posture(settings, metrics, bad_since=998.0, now=1000.0)

    assert state.posture_ok is False
    assert state.alarm_active is False
    assert state.bad_elapsed == 2.0
    assert bad_since == 998.0
