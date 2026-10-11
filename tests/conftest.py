"""Общие фикстуры: тесты не должны трогать настоящие файлы пользователя."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("POSTURE_MONITOR_DATA_DIR", str(tmp_path_factory.mktemp("data")))
