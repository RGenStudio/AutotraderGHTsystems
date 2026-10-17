"""Active window helper tests (UTC, weekdays 12:00–21:00 default)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from autotrader.active_window import is_within_active_window
from autotrader.config import ActiveWindow, load_yaml_config


def test_yaml_default_active_window() -> None:
    cfg = load_yaml_config()
    assert cfg.active_window.timezone == "UTC"
    assert cfg.active_window.weekdays_only is True
    assert cfg.active_window.start == "12:00"
    assert cfg.active_window.end == "21:00"


def test_within_window_weekday_midday() -> None:
    # Monday 15:00 UTC
    now = datetime(2024, 1, 8, 15, 0, tzinfo=UTC)
    assert is_within_active_window(now) is True


def test_outside_before_start() -> None:
    now = datetime(2024, 1, 8, 11, 59, tzinfo=UTC)
    assert is_within_active_window(now) is False


def test_at_start_inclusive() -> None:
    now = datetime(2024, 1, 8, 12, 0, tzinfo=UTC)
    assert is_within_active_window(now) is True


def test_at_end_exclusive() -> None:
    now = datetime(2024, 1, 8, 21, 0, tzinfo=UTC)
    assert is_within_active_window(now) is False


def test_weekend_blocked_even_during_hours() -> None:
    # Saturday 15:00 UTC
    now = datetime(2024, 1, 13, 15, 0, tzinfo=UTC)
    assert is_within_active_window(now) is False


def test_naive_datetime_treated_as_utc() -> None:
    now = datetime(2024, 1, 8, 15, 0)  # naive
    assert is_within_active_window(now) is True


def test_custom_window() -> None:
    window = ActiveWindow(
        timezone="UTC",
        weekdays_only=False,
        start="09:00",
        end="10:00",
    )
    assert is_within_active_window(datetime(2024, 1, 13, 9, 30, tzinfo=UTC), window) is True
    assert is_within_active_window(datetime(2024, 1, 13, 10, 0, tzinfo=UTC), window) is False


def test_rejects_non_utc_timezone() -> None:
    window = ActiveWindow(timezone="Asia/Bangkok", start="12:00", end="21:00")
    with pytest.raises(ValueError, match="UTC"):
        is_within_active_window(datetime(2024, 1, 8, 15, 0, tzinfo=UTC), window)


def test_outside_window_means_no_new_entries_documented() -> None:
    """Policy check: helper False ⇒ callers must skip new entries."""
    outside = datetime(2024, 1, 8, 22, 0, tzinfo=UTC)
    assert is_within_active_window(outside) is False
