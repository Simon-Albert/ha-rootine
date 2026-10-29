"""Regen seit dem letzten Erledigen (7.7) und Einordnung (7.6)."""

from __future__ import annotations

from datetime import date, datetime, timedelta

RAIN_DAYS_KEPT = 60
DEFAULT_THRESHOLD_MM = 5.0
CLASSIFY_THRESHOLD_MM = 2.0


def record_rain(rain_days: dict[str, float], day: date, value: float) -> dict[str, float]:
    """Tagesmaximum je Datum merken, höchstens 60 Tage behalten."""
    updated = dict(rain_days)
    key = day.isoformat()
    updated[key] = max(updated.get(key, 0.0), value)
    for old in sorted(updated)[:-RAIN_DAYS_KEPT]:
        del updated[old]
    return updated


def effective_rain(
    rain_days: dict[str, float],
    today: date,
    last_done: datetime,
    rain_at_done: float | None,
) -> float:
    """Regen von gestern und heute, nur der Anteil nach last_done."""
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
    """Heute plus gestern, für die Einordnung eines Wassereintrags (7.6)."""
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
