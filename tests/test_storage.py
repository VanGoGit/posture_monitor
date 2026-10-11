"""Тесты хранения настроек и статистики."""

from __future__ import annotations

import json
from datetime import date

from config import Settings
from paths import atomic_write_text, data_file
from stats import StatsTracker


def test_settings_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    original = Settings(delta_degrees=7, baseline_neck=12.5, baseline_back=3.0, enable_sound=False)

    original.save(path)

    assert Settings.load(path) == original


def test_settings_missing_file_gives_defaults(tmp_path):
    assert Settings.load(tmp_path / "nope.json") == Settings()


def test_settings_corrupted_file_gives_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not json", encoding="utf-8")

    assert Settings.load(path) == Settings()


def test_settings_bad_values_fall_back_per_field(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"delta_degrees": "abc", "camera_index": "2", "baseline_neck": 11}),
        encoding="utf-8",
    )

    settings = Settings.load(path)

    assert settings.delta_degrees == Settings().delta_degrees
    assert settings.camera_index == 2
    assert settings.baseline_neck == 11.0


def test_settings_drop_legacy_back_baseline(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"baseline_neck": 8.0, "baseline_back": 178.0}), encoding="utf-8")

    settings = Settings.load(path)

    assert settings.baseline_neck == 8.0
    assert settings.baseline_back is None


def test_atomic_write_leaves_no_temp_files(tmp_path):
    path = tmp_path / "out.json"
    atomic_write_text(path, "1")
    atomic_write_text(path, "2")

    assert path.read_text(encoding="utf-8") == "2"
    assert [p.name for p in tmp_path.iterdir()] == ["out.json"]


def test_data_file_uses_override_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("POSTURE_MONITOR_DATA_DIR", str(tmp_path))

    assert data_file("settings.json") == tmp_path / "settings.json"


def test_stats_counts_episode(tmp_path):
    path = tmp_path / "stats.json"
    tracker = StatsTracker(path)

    tracker.on_alarm_start(now=100.0)
    tracker.on_alarm_start(now=101.0)  # повтор не считается новым эпизодом
    tracker.on_alarm_end(now=112.5)

    today = tracker.today()
    assert today.events == 1
    assert today.seconds_bad == 12.5

    reloaded = StatsTracker(path).today()
    assert reloaded.events == 1
    assert reloaded.seconds_bad == 12.5


def test_stats_end_without_start_is_noop(tmp_path):
    tracker = StatsTracker(tmp_path / "stats.json")
    tracker.on_alarm_end(now=5.0)

    assert tracker.today().events == 0
    assert not (tmp_path / "stats.json").exists()


def test_stats_last_days_ends_today(tmp_path):
    days = StatsTracker(tmp_path / "stats.json").last_days(7)

    assert len(days) == 7
    assert days[-1][0] == date.today().isoformat()


def test_stats_corrupted_file_ignored(tmp_path):
    path = tmp_path / "stats.json"
    path.write_text("[1, 2", encoding="utf-8")

    assert StatsTracker(path).today().events == 0
