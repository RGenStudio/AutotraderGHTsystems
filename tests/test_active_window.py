"""Active window helper tests (UTC; default effectively 24h)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from autotrader.active_window import is_within_active_window
from autotrader.config import ActiveWindow, load_yaml_config


def test_yaml_default_active_window_is_24h() -> None:
    cfg = load_yaml_config()
    assert cfg.active_window.timezone == "UTC"
    assert cfg.active_window.weekdays_only is False
    assert cfg.active_window.start == "00:00"
    assert cfg.active_window.end == "24:00"


def test_default_allows_all_utc_hours_every_day() -> None:
    # Monday early / late, Saturday mid — all allowed with 24h default.
    assert is_within_active_window(datetime(2024, 1, 8, 0, 0, tzinfo=UTC)) is True
    assert is_within_active_window(datetime(2024, 1, 8, 15, 0, tzinfo=UTC)) is True
    assert is_within_active_window(datetime(2024, 1, 8, 23, 59, tzinfo=UTC)) is True
    assert is_within_active_window(datetime(2024, 1, 13, 15, 0, tzinfo=UTC)) is True


def test_narrow_window_outside_before_start() -> None:
    window = ActiveWindow(
        timezone="UTC", weekdays_only=True, start="12:00", end="21:00"
    )
    now = datetime(2024, 1, 8, 11, 59, tzinfo=UTC)
    assert is_within_active_window(now, window) is False


def test_narrow_window_at_start_inclusive() -> None:
    window = ActiveWindow(
        timezone="UTC", weekdays_only=True, start="12:00", end="21:00"
    )
    now = datetime(2024, 1, 8, 12, 0, tzinfo=UTC)
    assert is_within_active_window(now, window) is True


def test_narrow_window_at_end_exclusive() -> None:
    window = ActiveWindow(
        timezone="UTC", weekdays_only=True, start="12:00", end="21:00"
    )
    now = datetime(2024, 1, 8, 21, 0, tzinfo=UTC)
    assert is_within_active_window(now, window) is False


def test_weekend_blocked_when_weekdays_only() -> None:
    window = ActiveWindow(
        timezone="UTC", weekdays_only=True, start="12:00", end="21:00"
    )
    now = datetime(2024, 1, 13, 15, 0, tzinfo=UTC)  # Saturday
    assert is_within_active_window(now, window) is False


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


def test_end_24_00_with_nonzero_start() -> None:
    window = ActiveWindow(
        timezone="UTC", weekdays_only=False, start="06:00", end="24:00"
    )
    assert is_within_active_window(datetime(2024, 1, 8, 5, 59, tzinfo=UTC), window) is False
    assert is_within_active_window(datetime(2024, 1, 8, 6, 0, tzinfo=UTC), window) is True
    assert is_within_active_window(datetime(2024, 1, 8, 23, 0, tzinfo=UTC), window) is True


def test_outside_narrow_window_means_no_new_entries() -> None:
    """Policy check: helper False ⇒ callers must skip new entries."""
    window = ActiveWindow(
        timezone="UTC", weekdays_only=True, start="12:00", end="21:00"
    )
    outside = datetime(2024, 1, 8, 22, 0, tzinfo=UTC)
    assert is_within_active_window(outside, window) is False
