"""Ventilläufe gruppieren und einem Wassereintrag zuordnen (7.6, 7.6.1)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

MERGE_GAP = timedelta(minutes=10)
LEAD = timedelta(minutes=60)  # Lauf darf bis 60 min vor dem Anstieg beginnen
LAG = timedelta(minutes=5)  # und bis 5 min danach

Transition = tuple[datetime, str]


@dataclass(frozen=True)
class ValveRun:
    start: datetime
    end: datetime | None  # None = läuft noch


def valve_runs(transitions: list[Transition]) -> list[ValveRun]:
    """Läufe aus Zustandsübergängen. Beginn nur bei off -> on.

    Übergänge aus unavailable/unknown zählen nicht. Ein Lauf endet mit dem nächsten
    Zustand ungleich on.
    """
    runs: list[ValveRun] = []
    previous: str | None = None
    start: datetime | None = None
    for ts, state in sorted(transitions, key=lambda x: x[0]):
        if state == "on":
            if previous == "off" and start is None:
                start = ts
        elif start is not None:
            runs.append(ValveRun(start, ts))
            start = None
        previous = state
    if start is not None:
        runs.append(ValveRun(start, None))
    return runs


def valve_events(transitions: list[Transition]) -> list[ValveRun]:
    """Läufe, die weniger als 10 min nach dem vorherigen Ende beginnen, werden zusammengefasst."""
    events: list[ValveRun] = []
    for run in valve_runs(transitions):
        if events and events[-1].end is not None and run.start - events[-1].end < MERGE_GAP:
            events[-1] = ValveRun(events[-1].start, run.end)
        else:
            events.append(run)
    return events


def valve_matches(events: list[ValveRun], water_ts: datetime) -> bool:
    """Begann ein Lauf zwischen 60 min vor und 5 min nach dem Anstieg?"""
    return any(water_ts - LEAD <= e.start <= water_ts + LAG for e in events)
