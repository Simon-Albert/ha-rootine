"""Rain since the task was last done (7.7) and classification of water events (7.6)."""

from __future__ import annotations

from datetime import date, datetime, timedelta

RAIN_DAYS_KEPT = 60
DEFAULT_THRESHOLD_MM = 5.0
CLASSIFY_THRESHOLD_MM = 2.0


def add_reading(
    rain_days: dict[str, float], base: float | None, day: date, value: float
) -> tuple[dict[str, float], float]:
    """Add one reading of a daily-total rain sensor (state_class total_increasing).

    Rain of a local date is the sum of the positive increments whose timestamp falls on that
    date. A lower value is a reset (new base, no rain); many sensors reset at midnight UTC,
    not at local midnight, and show the previous day's total until then. The first reading
    after a start is only a base. Returns the updated days and the new base.
    """
    if base is None or value <= base:
        return rain_days, value
    updated = dict(rain_days)
    key = day.isoformat()
    updated[key] = round(updated.get(key, 0.0) + value - base, 3)
    for old in sorted(updated)[:-RAIN_DAYS_KEPT]:
        del updated[old]
    return updated, value


def prefill_from_history(history: list[dict] | None) -> dict[str, float]:
    """Daily totals from an attribute like Rain Warner's daily_history ([{date, mm}]).

    Approximation: those days are UTC days, not local days.
    """
    result: dict[str, float] = {}
    for item in history or []:
        try:
            result[date.fromisoformat(str(item["date"])).isoformat()] = float(item["mm"])
        except (KeyError, TypeError, ValueError):
            continue
    return dict(sorted(result.items())[-RAIN_DAYS_KEPT:])


def effective_rain(
    rain_days: dict[str, float],
    today: date,
    last_done: datetime,
    rain_at_done: float | None,
) -> float:
    """Rain of yesterday and today, only the part after last_done."""
    total = 0.0
    done_day = last_done.date()
    for day in (today - timedelta(days=1), today):
        if day < done_day:
            continue
        value = rain_days.get(day.isoformat(), 0.0)
        if day == done_day:
            value = max(0.0, value - (rain_at_done or 0.0))
        total += value
    return total


def rain_resets(
    rain_days: dict[str, float],
    today: date,
    last_done: datetime,
    rain_at_done: float | None,
    threshold: float = DEFAULT_THRESHOLD_MM,
) -> bool:
    return effective_rain(rain_days, today, last_done, rain_at_done) >= threshold


def recent_rain(rain_days: dict[str, float], today: date) -> float:
    """Today plus yesterday, for classifying a water event (7.6)."""
    return rain_days.get(today.isoformat(), 0.0) + rain_days.get(
        (today - timedelta(days=1)).isoformat(), 0.0
    )


def classify_water_event(*, valve_match: bool, rain_today_and_yesterday: float) -> str:
    """valve > rain > sensor (7.6)."""
    if valve_match:
        return "valve"
    if rain_today_and_yesterday >= CLASSIFY_THRESHOLD_MM:
        return "rain"
    return "sensor"
