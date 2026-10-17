"""Active trading window (UTC) — outside window means no new entries."""

from __future__ import annotations

from datetime import UTC, datetime, time

from autotrader.config import ActiveWindow


def _parse_hhmm(value: str) -> time:
    """Parse ``HH:MM`` or ``H:MM`` into a ``time`` (seconds ignored / zero)."""
    parts = value.strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"active window time must be HH:MM, got {value!r}")
    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"active window time out of range: {value!r}")
    return time(hour=hour, minute=minute)


def is_within_active_window(
    now: datetime,
    window: ActiveWindow | None = None,
) -> bool:
    """
    Return True when ``now`` falls inside the configured active window.

    Rules (local-run / project defaults):
    - Times are interpreted in **UTC** (``window.timezone`` must be UTC for now).
    - Default window: weekdays **12:00–21:00** UTC (inclusive start, exclusive end).
    - Outside the window → callers must **not** open new entries.
    """
    cfg = window or ActiveWindow()
    if cfg.timezone.upper() != "UTC":
        raise ValueError(
            f"only UTC active windows are supported in M1 (got {cfg.timezone!r})"
        )

    instant = now if now.tzinfo is not None else now.replace(tzinfo=UTC)
    instant = instant.astimezone(UTC)

    if cfg.weekdays_only and instant.weekday() >= 5:  # Saturday=5, Sunday=6
        return False

    start = _parse_hhmm(cfg.start)
    end = _parse_hhmm(cfg.end)
    if start >= end:
        raise ValueError(
            f"active window start must be before end (got {cfg.start}–{cfg.end})"
        )

    current = instant.timetz().replace(tzinfo=None)
    return start <= current < end
