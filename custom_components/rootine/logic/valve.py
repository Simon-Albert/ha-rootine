"""Group valve runs and match them to a water event (7.6, 7.6.1)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

MERGE_GAP = timedelta(minutes=10)
LEAD = timedelta(minutes=60)  # a run may start up to 60 min before the rise
LAG = timedelta(minutes=5)  # and up to 5 min after it

Transition = tuple[datetime, str]


@dataclass(frozen=True)
class ValveRun:
    start: datetime
    end: datetime | None  # None = still running


def valve_runs(transitions: list[Transition]) -> list[ValveRun]:
    """Runs from state transitions. A run starts only on off -> on.

    Transitions from unavailable/unknown do not count. A run ends with the next state
    that is not on.
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
    """Runs starting less than 10 min after the previous one ended are merged."""
    events: list[ValveRun] = []
    for run in valve_runs(transitions):
        if events and events[-1].end is not None and run.start - events[-1].end < MERGE_GAP:
            events[-1] = ValveRun(events[-1].start, run.end)
        else:
            events.append(run)
    return events


def valve_matches(events: list[ValveRun], water_ts: datetime) -> bool:
    """Did a run start between 60 min before and 5 min after the rise?"""
    return any(water_ts - LEAD <= e.start <= water_ts + LAG for e in events)
