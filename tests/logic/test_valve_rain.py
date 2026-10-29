from datetime import date, datetime, timedelta

from custom_components.rootine.logic import rain, valve

from ..conftest import TZ

T0 = datetime(2026, 10, 13, 23, 25, tzinfo=TZ)


def tr(*pairs):
    return [(T0 + timedelta(minutes=m), s) for m, s in pairs]


def test_runs_need_off_to_on():
    runs = valve.valve_runs(tr((0, "unavailable"), (1, "on"), (2, "off"), (3, "on"), (4, "off")))
    assert len(runs) == 1  # on aus unavailable zählt nicht
    assert runs[0].start == T0 + timedelta(minutes=3)


def test_runs_end_with_non_on():
    runs = valve.valve_runs(tr((0, "off"), (1, "on"), (2, "unavailable"), (3, "off")))
    assert runs == [valve.ValveRun(T0 + timedelta(minutes=1), T0 + timedelta(minutes=2))]


def test_open_run():
    runs = valve.valve_runs(tr((0, "off"), (1, "on")))
    assert runs[0].end is None


def test_merge_within_10_min():
    seq = tr((0, "off"), (0.0, "on"), (1, "off"), (3, "on"), (4, "off"), (30, "on"), (31, "off"))
    events = valve.valve_events(seq)
    assert [e.start for e in events] == [T0, T0 + timedelta(minutes=30)]
    assert events[0].end == T0 + timedelta(minutes=4)


def test_valve_matching_window():
    ev = valve.valve_events(tr((0, "off"), (1, "on"), (2, "off")))
    start = ev[0].start
    assert valve.valve_matches(ev, start + timedelta(seconds=45))
    assert valve.valve_matches(ev, start + timedelta(minutes=59))
    assert not valve.valve_matches(ev, start + timedelta(minutes=61))
    assert valve.valve_matches(ev, start - timedelta(minutes=4))  # Meldung vor Ventilzustand
    assert not valve.valve_matches(ev, start - timedelta(minutes=6))


def test_classify():
    assert rain.classify_water_event(valve_match=True, rain_today_and_yesterday=9) == "valve"
    assert rain.classify_water_event(valve_match=False, rain_today_and_yesterday=2.0) == "rain"
    assert rain.classify_water_event(valve_match=False, rain_today_and_yesterday=1.99) == "sensor"


def test_effective_rain_window_and_baseline():
    days = {"2026-10-14": 2.0, "2026-10-15": 1.0, "2026-10-16": 4.5}
    done = datetime(2026, 10, 15, 8, tzinfo=TZ)
    # gestern = 15.10. (Tag des Erledigens, minus Basis 0.5), heute = 16.10.
    assert rain.effective_rain(days, date(2026, 10, 16), done, 0.5) == 0.5 + 4.5
    # Tage vor gestern zählen nicht
    old = datetime(2026, 10, 10, 8, tzinfo=TZ)
    assert rain.effective_rain(days, date(2026, 10, 16), old, 0.0) == 1.0 + 4.5
    assert rain.rain_resets(days, date(2026, 10, 16), old, 0.0, 5.0)
    assert not rain.rain_resets(days, date(2026, 10, 15), done, 0.5, 5.0)


def test_rain_before_last_done_ignored():
    days = {"2026-10-15": 9.0}
    done = datetime(2026, 10, 16, 8, tzinfo=TZ)
    assert rain.effective_rain(days, date(2026, 10, 16), done, 0.0) == 0.0


def test_recent_rain():
    assert rain.recent_rain({"2026-10-18": 4.41, "2026-10-17": 1.27}, date(2026, 10, 18)) == 5.68
