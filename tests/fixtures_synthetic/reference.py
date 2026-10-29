"""Independent oracle for the synthetic fixtures (tests/fixtures_synthetic/).

Plain, slow, obvious re-implementations of plan section 7, deliberately sharing no code with
custom_components/rootine. The tests hold the printed results as constants; if the integration
disagrees, find out which side is wrong before changing a constant.

    python -I tests/fixtures_synthetic/reference.py
"""

from __future__ import annotations

import csv
import datetime as dt
import statistics
from pathlib import Path

HERE = Path(__file__).parent
GRID = dt.timedelta(minutes=15)
CARRY_MAX = dt.timedelta(hours=36)


def load_moisture(name: str) -> list[tuple[dt.datetime, float | None]]:
    rows = []
    with open(HERE / f"{name}_moisture.csv", newline="") as f:  # plant_a / plant_b
        for r in csv.DictReader(f):
            t = dt.datetime.fromisoformat(r["timestamp"])
            try:
                rows.append((t, float(r["state"])))
            except ValueError:  # unavailable / unknown
                rows.append((t, None))
    return rows


def valid(rows):
    return [(t, v) for t, v in rows if v is not None]


def value_at(rows, t):
    """Carry-forward: last valid value at or before t, at most CARRY_MAX old."""
    last = None
    for x, v in rows:
        if x > t:
            break
        last = (x, v)
    if last is None or t - last[0] > CARRY_MAX:
        return None
    return last[1]


def evaluation(rows, t, method):
    if method == "raw":
        return value_at(rows, t)
    points = [value_at(rows, t - i * GRID) for i in range(96)]  # (t-24h, t]
    points = [p for p in points if p is not None]
    if len(points) < 80:
        return None
    return statistics.median(points) if method == "median_24h" else max(points)


def threshold_crossings(rows, start, end, threshold, method):
    out, prev, t = [], None, start
    while t < end:
        v = evaluation(rows, t, method)
        below = v is not None and v < threshold
        if prev is not None and below != prev:
            out.append(t.strftime("%d.%m. %H:%M") + ("↓" if below else "↑"))
        prev, t = below, t + GRID
    return out


def water_inputs(rows):
    rows = valid(rows)
    events = []
    for i in range(1, len(rows)):
        t, v = rows[i]
        step = v - rows[i - 1][1]
        start = t - dt.timedelta(hours=3)
        window = [x[1] for x in rows[: i + 1] if x[0] >= start]
        before = [x[1] for x in rows[:i] if x[0] < start]
        if before:
            window.append(before[-1])
        rise = v - min(window)
        if step >= 10 or rise >= 12:
            if events and (t - events[-1]).total_seconds() < 6 * 3600:
                continue
            events.append(t)
    return events


def big_drops(rows, limit=15):
    rows = valid(rows)
    return [rows[i][0] for i in range(1, len(rows)) if rows[i - 1][1] - rows[i][1] >= limit]


def valve_events(channel: int):
    with open(HERE / f"valve_{channel}.csv", newline="") as f:
        rows = [(dt.datetime.fromisoformat(r["timestamp"]), r["state"]) for r in csv.DictReader(f)]
    runs = []
    for i, (t, s) in enumerate(rows):
        if s == "on" and i > 0 and rows[i - 1][1] == "off":
            end = next((t2 for t2, s2 in rows[i + 1 :] if s2 != "on"), t)
            runs.append((t, end))
    events: list[list[dt.datetime]] = []
    for a, b in runs:
        if events and (a - events[-1][1]).total_seconds() < 600:
            events[-1][1] = b
        else:
            events.append([a, b])
    return [e[0] for e in events]


def rain_mode_cherry():
    with open(HERE / "rain_daily.csv", newline="") as f:
        rain = {dt.date.fromisoformat(r["date"]): float(r["mm"]) for r in csv.DictReader(f)}
    last = dt.datetime(2030, 4, 1, 20, 0)
    rain_at_done = rain[last.date()]  # sensor is set to the full day total at 00:05
    interval, resets, statuses = 3, [], {}
    day = dt.date(2030, 4, 2)
    while day <= dt.date(2030, 4, 29):
        effective = 0.0
        for d in (day - dt.timedelta(days=1), day):
            if d < last.date():
                continue
            effective += rain.get(d, 0.0) - (rain_at_done if d == last.date() else 0.0)
        if effective >= 5.0:
            resets.append((day, round(effective, 2)))
            last, rain_at_done = dt.datetime.combine(day, dt.time(0, 5)), rain[day]
        next_due = last.date() + dt.timedelta(days=interval)
        days = (next_due - day).days
        statuses[day] = (
            "ok" if days > 1 else "soon" if days == 1 else "due" if days == 0 else "overdue",
            days,
        )
        day += dt.timedelta(days=1)
    return resets, statuses


def too_wet_spans(rows, threshold, start, end, hysteresis=3, min_hours=48):
    """Warning after median_24h >= threshold for min_hours; ends below threshold - hysteresis."""
    spans, above_since, active_since, t = [], None, None, start
    while t < end:
        v = evaluation(rows, t, "median_24h")
        if active_since is None:
            if v is not None and v >= threshold:
                above_since = above_since or t
                if t - above_since >= dt.timedelta(hours=min_hours):
                    active_since = t
            else:
                above_since = None
        elif v is None or v < threshold - hysteresis:
            spans.append((active_since, t))
            active_since, above_since = None, None
        t += dt.timedelta(hours=1)
    if active_since is not None:
        spans.append((active_since, None))
    return spans


def cold_episodes(name, temp_min, hysteresis=1.0):
    """Replay convention: the sensor shows the hourly minimum at the start of each hour."""
    with open(HERE / f"{name}_temperature_hourly.csv", newline="") as f:
        rows = [
            (dt.datetime.fromisoformat(r["hour_start"]), float(r["min"])) for r in csv.DictReader(f)
        ]
    episodes, since = [], None
    for t, v in rows:
        if since is None and v < temp_min:
            since = t
        elif since is not None and v >= temp_min + hysteresis:
            episodes.append((since, t))
            since = None
    if since is not None:
        episodes.append((since, None))
    return episodes


def classify(events, valve_starts, rain):
    """7.6: valve run from 60 min before to 5 min after, else rain (today + yesterday) >= 2 mm."""
    out = []
    for t in events:
        if any(
            t - dt.timedelta(minutes=60) <= v <= t + dt.timedelta(minutes=5) for v in valve_starts
        ):
            kind = "valve"
        elif rain.get(t.date(), 0.0) + rain.get(t.date() - dt.timedelta(days=1), 0.0) >= 2.0:
            kind = "rain"
        else:
            kind = "sensor"
        out.append((t.strftime("%d.%m. %H:%M"), kind))
    return out


def rain_from_gauge():
    """Rain per local date from the cumulative gauge: sum of rises; a fall is a reset."""
    days: dict[dt.date, float] = {}
    previous = None
    with open(HERE / "rain_sensor.csv", newline="") as f:
        for r in csv.DictReader(f):
            t, value = dt.datetime.fromisoformat(r["timestamp"]), float(r["state"])
            if previous is not None and value > previous:
                days[t.date()] = round(days.get(t.date(), 0.0) + value - previous, 3)
            previous = value
    return days


if __name__ == "__main__":
    a = load_moisture("plant_a")
    b = load_moisture("plant_b")
    tz = b[0][0].tzinfo
    with open(HERE / "rain_daily.csv", newline="") as f:
        rain = {dt.date.fromisoformat(r["date"]): float(r["mm"]) for r in csv.DictReader(f)}

    print("7.4 Bewertungswert, plant_b 11.04.-14.04.")
    start = dt.datetime(2030, 4, 11, 0, 0, tzinfo=tz)
    end = dt.datetime(2030, 4, 14, 23, 20, tzinfo=tz)
    for thr in (55, 45):
        for method in ("raw", "median_24h", "max_24h"):
            print(f"  {thr} % {method:11} {threshold_crossings(b, start, end, thr, method)}")

    print("Regen aus dem Zaehler (Ruecksetzung um Mitternacht UTC), pro Ortsdatum")
    gauge = rain_from_gauge()
    print("  ", {d.strftime("%d.%m."): mm for d, mm in sorted(gauge.items())})
    print("   gleich rain_daily.csv:", gauge == {d: mm for d, mm in rain.items() if mm})

    print("7.5/7.6 Wassereintraege mit Einordnung")
    print("  plant_a", classify(water_inputs(a), valve_events(2), rain))
    print("  plant_b", classify(water_inputs(b), valve_events(1), rain))

    print("7.6.1 Ventil-Ereignisse")
    for ch in (1, 2):
        print(f"  Kanal {ch}", [t.strftime("%d.%m. %H:%M:%S") for t in valve_events(ch)])

    print("7.7 Regen-Modus (ganzjaehrig: 3, zuletzt 01.04. 20:00)")
    resets, statuses = rain_mode_cherry()
    print("  Ruecksetzungen", [(d.strftime("%d.%m."), mm) for d, mm in resets])
    print(
        "  Status",
        {d.strftime("%d.%m."): s for d, s in statuses.items() if d.day in (5, 7, 10, 13, 18, 20)},
    )

    print("7.8 Plausibilitaet (Abfall >= 15)")
    for name, rows in (("plant_a", a), ("plant_b", b)):
        print(f"  {name}", [t.strftime("%d.%m. %H:%M") for t in big_drops(rows)])

    def longest_gap(rows):
        v = valid(rows)
        return max((v[i][0] - v[i - 1][0]).total_seconds() / 3600 for i in range(1, len(v)))

    print("Laengste Luecke ohne Aenderung (h)", round(longest_gap(a), 1), round(longest_gap(b), 1))

    def fmt(spans):
        return [
            (x.strftime("%d.%m. %H:%M"), y.strftime("%d.%m. %H:%M") if y else "offen")
            for x, y in spans
        ]

    print("7.10 Kaelte (temp_min 5, Hysterese 1)")
    print("  plant_a", fmt(cold_episodes("plant_a", 5.0)))

    print("7.11 Zu nass (median_24h >= 95 fuer 48 h, Ende unter 92)")
    wet_start = dt.datetime(2030, 4, 1, 12, 0, tzinfo=tz)
    wet_end = dt.datetime(2030, 4, 30, 9, 0, tzinfo=tz)
    for name, rows in (("plant_a", a), ("plant_b", b)):
        print(f"  {name}", fmt(too_wet_spans(rows, 95, wet_start, wet_end)))
