"""Kälte- und Hitzeschutz (7.10)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

HYSTERESIS = 1.0
FORECAST_HOURS = 24
FORECAST_MAX_AGE = timedelta(hours=3)


@dataclass(frozen=True)
class Protect:
    cold: str | None = None  # cold_now | cold_forecast
    heat: str | None = None  # heat_now | heat_forecast

    @property
    def active(self) -> bool:
        return self.cold is not None or self.heat is not None

    @property
    def reason(self) -> str | None:
        return self.cold or self.heat


def forecast_extremes(
    forecast: list[dict[str, Any]], now: datetime, hours: int = FORECAST_HOURS
) -> tuple[float | None, float | None]:
    """Minimum und Maximum der Temperatur in den nächsten `hours` Stunden.

    Einträge mit `datetime` (ISO-String oder datetime) und `temperature`, optional `templow`.
    Der Eintrag der laufenden Stunde zählt mit.
    """
    lows: list[float] = []
    highs: list[float] = []
    for entry in forecast:
        raw = entry.get("datetime")
        temp = entry.get("temperature")
        if raw is None or temp is None:
            continue
        ts = raw if isinstance(raw, datetime) else datetime.fromisoformat(raw)
        if ts.tzinfo is None and now.tzinfo is not None:
            ts = ts.replace(tzinfo=now.tzinfo)
        if not now - timedelta(hours=1) < ts < now + timedelta(hours=hours):
            continue
        highs.append(float(temp))
        low = entry.get("templow")
        lows.append(float(low if low is not None else temp))
    return (min(lows) if lows else None, max(highs) if highs else None)


def evaluate_protect(
    previous: Protect,
    *,
    temp_min: float | None,
    temp_max: float | None,
    current_cold: float | None,
    current_heat: float | None,
    forecast_min: float | None,
    forecast_max: float | None,
    outdoor: bool,
) -> Protect:
    """Ein Schritt der Schutzbewertung.

    current_cold: eigener Temperatursensor (oder Außensensor, falls die Pflanze keinen hat).
    current_heat: nur ein Außensensor, nie der Pflanzensensor (heizt sich in der Sonne auf).
    Vorhersagen gelten nur draußen.
    """
    if not outdoor:
        forecast_min = forecast_max = None
    return Protect(
        cold=_cold(previous.cold, temp_min, current_cold, forecast_min),
        heat=_heat(previous.heat, temp_max, current_heat, forecast_max),
    )


def _cold(
    previous: str | None, limit: float | None, current: float | None, forecast: float | None
) -> str | None:
    if limit is None:
        return None
    if current is not None and current < limit:
        return "cold_now"
    if forecast is not None and forecast < limit:
        return "cold_forecast"
    if previous is None:
        return None
    if current is None and forecast is None:
        return previous
    current_ok = current is None or current >= limit + HYSTERESIS
    forecast_ok = forecast is None or forecast >= limit
    return None if current_ok and forecast_ok else previous


def _heat(
    previous: str | None, limit: float | None, current: float | None, forecast: float | None
) -> str | None:
    if limit is None:
        return None
    if current is not None and current > limit:
        return "heat_now"
    if forecast is not None and forecast > limit:
        return "heat_forecast"
    if previous is None:
        return None
    if current is None and forecast is None:
        return previous
    current_ok = current is None or current < limit - HYSTERESIS
    forecast_ok = forecast is None or forecast <= limit
    return None if current_ok and forecast_ok else previous
