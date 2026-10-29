"""Bewertungswert, Wassereintrag, Plausibilität, Zu-nass (7.4, 7.5, 7.8, 7.11)."""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta

Sample = tuple[datetime, float | None]

GRID_STEP = timedelta(minutes=15)
GRID_POINTS = 96
GRID_MIN_FILLED = 80
MAX_AGE = timedelta(hours=36)

JUMP_STEP = 10.0  # (a) Anstieg zwischen zwei gültigen Werten
JUMP_WINDOW = 12.0  # (b) Anstieg innerhalb des Fensters
JUMP_WINDOW_SPAN = timedelta(hours=3)
EVENT_MERGE = timedelta(hours=6)

DROP_THRESHOLD = 15.0
STALE_AFTER = timedelta(hours=36)
UNAVAILABLE_AFTER = timedelta(hours=6)

TOO_WET_DURATION = timedelta(hours=48)
TOO_WET_HYSTERESIS = 3.0
BATTERY_LOW = 15.0

METHODS = ("median_24h", "max_24h", "raw")


def valid_samples(samples: list[Sample]) -> list[tuple[datetime, float]]:
    """Nur gültige Werte, nach Zeit sortiert. None (unavailable) wird übergangen."""
    return sorted(((t, v) for t, v in samples if v is not None), key=lambda s: s[0])


def grid_values(samples: list[Sample], now: datetime) -> list[float | None]:
    """96 Rasterpunkte (alle 15 min, jüngster = now) mit Carry-forward.

    Ein Rasterpunkt bekommt den zuletzt bekannten gültigen Wert, höchstens 36 h alt.
    Rückgabe in zeitlicher Reihenfolge (ältester zuerst).
    """
    valid = valid_samples(samples)
    values: list[float | None] = []
    index = 0
    last: tuple[datetime, float] | None = None
    for i in range(GRID_POINTS - 1, -1, -1):
        t = now - i * GRID_STEP
        while index < len(valid) and valid[index][0] <= t:
            last = valid[index]
            index += 1
        if last is not None and t - last[0] <= MAX_AGE:
            values.append(last[1])
        else:
            values.append(None)
    return values


def latest_value(samples: list[Sample], now: datetime) -> float | None:
    """Letzter gültiger Rohwert bis now, höchstens 36 h alt."""
    valid = [s for s in valid_samples(samples) if s[0] <= now]
    if not valid or now - valid[-1][0] > MAX_AGE:
        return None
    return valid[-1][1]


def evaluate(samples: list[Sample], now: datetime, method: str = "median_24h") -> float | None:
    """Bewertungswert nach Methode. None, wenn zu wenig Daten (7.4)."""
    if method == "raw":
        return latest_value(samples, now)
    grid = [v for v in grid_values(samples, now) if v is not None]
    if len(grid) < GRID_MIN_FILLED:
        return None
    if method == "max_24h":
        return max(grid)
    return float(statistics.median(grid))


# --- Wassereintrag (7.5) -----------------------------------------------------------------


@dataclass(frozen=True)
class WaterEvent:
    ts: datetime
    rule: str  # "step" (a) | "window" (b)
    before: float
    after: float


def detect_water_trigger(
    history: list[tuple[datetime, float]], t: datetime, v: float
) -> tuple[str, float] | None:
    """Prüft einen neuen gültigen Wert v zur Zeit t gegen die vorherigen gültigen Werte.

    history: gültige Werte vor t, aufsteigend. Gibt (Regel, Vergleichswert) oder None.
    """
    if not history:
        return None
    prev = history[-1][1]
    if v - prev >= JUMP_STEP:
        return "step", prev

    window_start = t - JUMP_WINDOW_SPAN
    candidates = [val for ts, val in history if ts >= window_start]
    # Der letzte Wert vor dem Fenster galt zu Fensterbeginn noch (Carry-forward).
    before_window = [val for ts, val in history if ts < window_start]
    if before_window:
        candidates.append(before_window[-1])
    if candidates:
        low = min(candidates)
        if v - low >= JUMP_WINDOW:
            return "window", low
    return None


def detect_water_events(samples: list[Sample]) -> list[WaterEvent]:
    """Alle Wassereinträge in einer Messreihe. Treffer innerhalb von 6 h gehören zum Ereignis."""
    events: list[WaterEvent] = []
    history: list[tuple[datetime, float]] = []
    last_event: datetime | None = None
    for t, v in valid_samples(samples):
        trigger = detect_water_trigger(history, t, v)
        if trigger is not None and (last_event is None or t - last_event > EVENT_MERGE):
            events.append(WaterEvent(t, trigger[0], trigger[1], v))
            last_event = t
        history.append((t, v))
    return events


# --- Plausibilität (7.8) -----------------------------------------------------------------


def is_implausible_drop(previous: float, value: float) -> bool:
    return previous - value >= DROP_THRESHOLD


def is_stale(
    now: datetime,
    last_reported: datetime | None,
    unavailable_since: datetime | None = None,
) -> bool:
    """Sensor meldet nicht: > 36 h ohne Meldung oder > 6 h durchgehend unavailable."""
    if unavailable_since is not None and now - unavailable_since > UNAVAILABLE_AFTER:
        return True
    return last_reported is not None and now - last_reported > STALE_AFTER


def battery_low(value: float | None) -> bool:
    return value is not None and value < BATTERY_LOW


# --- Zu nass (7.11) ----------------------------------------------------------------------


@dataclass(frozen=True)
class WetState:
    active: bool = False
    above_since: datetime | None = None


def update_too_wet(
    state: WetState, value: float | None, now: datetime, moisture_max: float
) -> WetState:
    """Ein Schritt der Zu-nass-Erkennung mit dem Bewertungswert (median_24h)."""
    if value is None:
        return state
    if value >= moisture_max:
        since = state.above_since or now
        return WetState(state.active or now - since >= TOO_WET_DURATION, since)
    active = state.active and value >= moisture_max - TOO_WET_HYSTERESIS
    return WetState(active, None)
