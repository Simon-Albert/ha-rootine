"""Generate the synthetic test fixtures in tests/fixtures_synthetic/.

Deterministic (fixed seed), no real measurements. The data reproduce the patterns that matter for
the logic: sun-driven daily swing, multi-day drying, watering jumps, slow and fast rise after rain,
a pulled sensor, reporting gaps up to 31 h, short unavailable phases, valve bursts and test runs
without effect, multi-day drizzle, frost nights and a rain gauge that resets at midnight UTC.
All times and amounts are invented.

    python -I scripts/make_synthetic_fixtures.py
"""

from __future__ import annotations

import csv
import math
import random
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

UTC = ZoneInfo("UTC")

SEED = 20300417
TZ = ZoneInfo("Europe/Berlin")
START = datetime(2030, 4, 1, 0, 0, tzinfo=TZ)
END = datetime(2030, 4, 30, 23, 59, tzinfo=TZ)
OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures_synthetic"


def at(day: int, hour: int, minute: int = 0, second: int = 0) -> datetime:
    return datetime(2030, 4, day, hour, minute, second, tzinfo=TZ)


# --- weather ---------------------------------------------------------------------------------

RAIN_MM = {2: 0.1, 3: 12.8, 8: 0.5, 9: 8.7, 18: 1.6, 19: 3.9}
for _day, _mm in zip(range(10, 18), (0.5, 0.9, 0.2, 0.6, 0.4, 0.7, 0.9, 0.2), strict=True):
    RAIN_MM[_day] = _mm  # drizzle: many small days, never enough on two consecutive days
CLOUDY = {3, 4, 5, 9, 10, 16, 19, 22, 24}  # no sun dip on these days
# local hours in which a day's rain falls (two steps per hour); other days at a random hour
RAIN_HOURS = {3: (13, 14, 15, 16), 8: (1,), 9: (11, 12, 13, 14), 18: (20, 21), 19: (14, 15, 16)}


def sunny(t: datetime) -> bool:
    return t.day not in CLOUDY


def sun_dip(t: datetime, amplitude: float) -> float:
    if not sunny(t):
        return 0.0
    hour = t.hour + t.minute / 60
    return -amplitude * math.exp(-(((hour - 13.5) / 2.2) ** 2))


# --- moisture model --------------------------------------------------------------------------


class Plant:
    def __init__(self, name: str, level: float, amplitude: float, drying: float) -> None:
        self.name = name
        self.level = level
        self.amplitude = amplitude
        self.drying = drying  # points per hour on normal days
        self.offset = 0.0  # pulled sensor
        self.extra_decline = 0.0
        self.jumps: dict[datetime, float] = {}  # time -> new level (absolute) or +delta
        self.flat: list[tuple[datetime, datetime, float]] = []  # windows with own drying rate
        self.forced: set[datetime] = set()  # extra report times
        self.unavailable: list[datetime] = []

    def drying_at(self, t: datetime) -> float:
        for start, end, rate in self.flat:
            if start <= t < end:
                return rate
        return self.drying if sunny(t) else self.drying * 0.4

    def dip_at(self, t: datetime) -> float:
        for start, end, _rate in self.flat:
            if start <= t < end:
                return 0.0
        return sun_dip(t, self.amplitude)


def simulate(plant: Plant, rng: random.Random) -> list[tuple[datetime, str]]:
    rows: list[tuple[datetime, str]] = []
    last: int | None = None
    next_report = START
    t = START
    unavailable = sorted(plant.unavailable)
    while t <= END:
        if t in plant.jumps:
            change = plant.jumps[t]
            if change == "pull":
                plant.offset, plant.extra_decline = -31.0, 1.4
            elif isinstance(change, tuple):  # ("set", level)
                plant.level = change[1]
            elif change == "reinsert":
                plant.offset, plant.extra_decline, plant.level = 0.0, 0.0, 100.0
            else:
                plant.level = min(100.0, plant.level + change)
        plant.level = max(5.0, plant.level - plant.drying_at(t) / 60)
        plant.offset -= plant.extra_decline / 60
        observed = max(0.0, min(100.0, plant.level + plant.offset + plant.dip_at(t)))
        report_now = t >= next_report or t in plant.forced
        if unavailable and t >= unavailable[0]:
            gap = unavailable.pop(0)
            rows.append((gap + timedelta(seconds=rng.randint(1, 30)), "unavailable"))
            back = gap + timedelta(seconds=rng.randint(40, 240))
            rows.append((back, str(last if last is not None else round(observed))))
        if report_now:
            value = round(observed)
            if value != last:
                ts = t + timedelta(
                    seconds=rng.randint(8, 49) if t in plant.forced else rng.randint(0, 59)
                )
                rows.append((ts, str(value)))
                last = value
            next_report = t + timedelta(minutes=rng.randint(10, 50))
        t += timedelta(minutes=1)
    rows.sort(key=lambda r: r[0])
    return rows


def plant_a() -> Plant:
    """Pot plant with little sun dip; rain jump, waterlogging, pulled sensor, valve 2."""
    p = Plant("plant_a", level=79.0, amplitude=2.6, drying=0.21)
    p.jumps[at(3, 16, 40)] = ("set", 97.0)  # rain jump to nearly saturated
    p.forced.add(at(3, 16, 40))
    p.flat.append((at(3, 16, 41), at(6, 20, 0), 0.045))  # stays very wet for days
    p.jumps[at(21, 10, 12)] = "pull"  # sensor pulled: big drop, then steady decline like in air
    p.forced.add(at(21, 10, 12))
    p.jumps[at(21, 20, 48)] = "reinsert"  # watered through valve 2, sensor back in the soil
    p.forced.add(at(21, 20, 48))
    p.flat.append((at(26, 23, 0), at(28, 1, 0), 0.0))  # about 30 h without any change
    p.unavailable += [at(d, 3, 27) for d in (3, 8, 13, 17, 23, 29)]
    return p


def plant_b() -> Plant:
    """Sunny spot with strong daily swing; valve 1, slow rain rise, rain jump, real drying."""
    p = Plant("plant_b", level=71.0, amplitude=7.5, drying=0.30)
    p.jumps[at(6, 7, 13)] = 35.0  # valve 1
    p.forced.add(at(6, 7, 14))
    for minute in (0, 15, 30, 45):  # rain: +3.2 every 15 min, +12.8 in under 3 h
        p.jumps[at(9, 14, minute)] = 3.2
        p.forced.add(at(9, 14, minute))
    p.flat.append((at(9, 13, 0), at(9, 16, 0), 0.0))
    p.jumps[at(14, 21, 52)] = 44.0  # valve 1 after several dry days
    p.forced.add(at(14, 21, 52))
    p.jumps[at(19, 16, 22)] = 38.0  # rain jump on a day with 3.9 mm (+1.6 mm the day before)
    p.forced.add(at(19, 16, 22))
    p.flat.append((at(24, 19, 0), at(25, 18, 0), 0.0))  # a full day without any change
    p.unavailable += [at(d, 2, 55) for d in (3, 8, 13, 17, 23, 28)]
    return p


# --- valves ----------------------------------------------------------------------------------


def valve(runs: list[tuple[datetime, int]], restarts: list[datetime]) -> list[tuple[datetime, str]]:
    rows = [(START.replace(hour=0, minute=0, second=3), "off")]
    for start, seconds in runs:
        rows.append((start, "on"))
        rows.append((start + timedelta(seconds=seconds), "off"))
    for restart in restarts:
        rows += [
            (restart, "unavailable"),
            (restart + timedelta(seconds=2), "unknown"),
            (restart + timedelta(seconds=5), "off"),
        ]
    return sorted(rows)


def burst(start: datetime, count: int, rng: random.Random) -> list[tuple[datetime, int]]:
    runs, t = [], start
    for _ in range(count):
        seconds = rng.randint(2, 20)
        runs.append((t, seconds))
        t += timedelta(seconds=seconds + rng.randint(20, 40))
    return runs


# --- temperature -----------------------------------------------------------------------------

COLD = {11: 1.8, 25: 0.9, 30: 2.3}  # frost nights: minimum before sunrise
COOL_MORNING = {20: 3.8}  # short cold spell 07:00-09:00


def temperature_rows(rng: random.Random) -> list[tuple[datetime, float, float, float]]:
    rows = []
    t = START
    while t <= END:
        hour = t.hour
        night_low = COLD.get(t.day, 8.0 + (t.day % 5) * 0.8)
        swing = (1 - math.cos(2 * math.pi * (hour - 5) / 24)) / 2  # 0 at 05:00, 1 at 17:00
        value = night_low + swing * 12 + rng.uniform(-0.3, 0.3)
        if t.day in COLD and hour < 5:
            value = night_low + (5 - hour) * 0.6
        if t.day in COLD and 5 <= hour < 9:
            value = night_low + (hour - 5) * 0.7
        if t.day in COOL_MORNING and 7 <= hour < 9:
            value = COOL_MORNING[t.day]
        if t.day == 30 and hour >= 2:
            value = min(value, 3.2)  # stays cold until the end of the data (open episode)
        low = round(value, 1)
        rows.append((t, round(value + 0.4, 2), low, round(value + 0.9, 1)))
        t += timedelta(hours=1)
    return rows


# --- rain gauge --------------------------------------------------------------------------------


def rain_sensor_rows(rng: random.Random) -> list[tuple[datetime, str]]:
    """Cumulative total (total_increasing) that resets at midnight UTC, like many rain gauges.

    Until the reset (02:00 local in summer time) the gauge still shows the previous total, so
    rain between 00:00 and 02:00 local is added on top of yesterday's value. Day 8 rains in
    exactly that window. The amounts per local day match rain_daily.csv.
    """
    events: list[tuple[datetime, float | None]] = []  # None = reset
    day = START.date()
    while day <= END.date():
        if day != START.date():
            midnight_utc = datetime(day.year, day.month, day.day, tzinfo=UTC).astimezone(TZ)
            events.append((midnight_utc + timedelta(seconds=rng.randint(1, 9)), None))
        mm = RAIN_MM.get(day.day, 0)
        if mm:
            hours = RAIN_HOURS.get(day.day, (rng.randint(5, 20),))
            steps = [round(mm / (2 * len(hours)), 2)] * (2 * len(hours))
            steps[-1] = round(mm - sum(steps[:-1]), 2)
            for i, amount in enumerate(steps):
                minute = 10 + 25 * (i % 2)
                ts = datetime(day.year, day.month, day.day, hours[i // 2], minute, tzinfo=TZ)
                events.append((ts + timedelta(seconds=rng.randint(0, 59)), amount))
        day += timedelta(days=1)
    rows, total = [(START + timedelta(seconds=17), "0.00")], 0.0
    for ts, amount in sorted(events, key=lambda e: e[0]):
        total = 0.0 if amount is None else round(total + amount, 2)
        rows.append((ts, f"{total:.2f}"))
    return rows


# --- write -----------------------------------------------------------------------------------


def write(name: str, header: list[str], rows: list[tuple]) -> None:
    with (OUT / name).open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        for row in rows:
            first, *rest = row
            writer.writerow([first.isoformat(), *rest])


def main() -> None:
    rng = random.Random(SEED)
    OUT.mkdir(exist_ok=True)
    write("plant_a_moisture.csv", ["timestamp", "state"], simulate(plant_a(), rng))
    write("plant_b_moisture.csv", ["timestamp", "state"], simulate(plant_b(), rng))
    v1 = [(at(6, 7, 13, 48), 11), *burst(at(14, 21, 51, 41), 6, rng)]  # starts before the jump
    v2 = [
        (at(5, 9, 41, 12), 48),
        *burst(at(14, 21, 52, 40), 4, rng),
        (at(18, 11, 31, 7), 6),  # test runs without effect on the plant
        (at(18, 11, 32, 15), 8),
        (at(18, 11, 46, 2), 4),
        (at(18, 12, 37, 44), 7),
        (at(21, 20, 48, 3), 9),  # real watering
    ]
    restarts = [at(3, 3, 27), at(17, 3, 27)]
    write("valve_1.csv", ["timestamp", "state"], valve(v1, restarts))
    write("valve_2.csv", ["timestamp", "state"], valve(v2, restarts))
    write(
        "plant_a_temperature_hourly.csv",
        ["hour_start", "mean", "min", "max"],
        [(t, mean, low, high) for t, mean, low, high in temperature_rows(rng)],
    )
    with (OUT / "rain_daily.csv").open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["date", "mm"])
        day = START.date()
        while day <= END.date():
            writer.writerow([day.isoformat(), RAIN_MM.get(day.day, 0)])
            day += timedelta(days=1)
    write("rain_sensor.csv", ["timestamp", "state"], rain_sensor_rows(rng))


if __name__ == "__main__":
    main()
