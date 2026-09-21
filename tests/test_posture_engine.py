"""Тесты алгоритма осанки."""

from __future__ import annotations

import time
from unittest.mock import patch

from config import Settings
from posture_engine import (
    PostureMetrics,
    PostureState,
    angle_from_vertical,
    evaluate_posture,
)


def test_angle_from_vertical_straight_up():
    assert angle_from_vertical((100, 200), (100, 50)) == 0.0


def test_angle_from_vertical_tilted():
    angle = angle_from_vertical((100, 200), (150, 200))
    assert 85 <= angle <= 95


def test_evaluate_posture_ok_when_calibrated_and_within_threshold():
    settings = Settings(baseline_neck=10.0, baseline_back=5.0, delta_degrees=10)
    metrics = PostureMetrics(neck_angle=15.0, back_angle=8.0)

    state, bad_since = evaluate_posture(settings, metrics, bad_since=None)

    assert state == PostureState(posture_ok=True, alarm_active=False, bad_elapsed=0.0)
    assert bad_since is None


def test_evaluate_posture_alarm_after_delay():
    settings = Settings(
        baseline_neck=10.0,
        baseline_back=5.0,
        delta_degrees=5,
        bad_posture_seconds=2.0,
    )
    metrics = PostureMetrics(neck_angle=30.0, back_angle=8.0)
    start = time.time() - 3.0

    state, bad_since = evaluate_posture(settings, metrics, bad_since=start)

    assert state.posture_ok is False
    assert state.alarm_active is True
    assert bad_since == start


def test_evaluate_posture_waiting_before_delay():
    settings = Settings(
        baseline_neck=10.0,
        baseline_back=5.0,
        delta_degrees=5,
        bad_posture_seconds=5.0,
    )
    metrics = PostureMetrics(neck_angle=30.0, back_angle=8.0)

    with patch("posture_engine.time.time", return_value=1000.0):
        state, bad_since = evaluate_posture(settings, metrics, bad_since=998.0)

    assert state.posture_ok is False
    assert state.alarm_active is False
    assert state.bad_elapsed == 2.0
    assert bad_since == 998.0
