from datetime import datetime, timedelta

from custom_components.rootine.logic import moisture as m

from ..conftest import TZ

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=TZ)


def hours_ago(h):
    return NOW - timedelta(hours=h)


def test_grid_carry_forward_and_none_skipped():
    samples = [(hours_ago(30), 50.0), (hours_ago(10), None), (hours_ago(5), 40.0)]
    grid = m.grid_values(samples, NOW)
    assert len(grid) == 96
    assert grid[0] == 50.0  # 23h45 zurück, Wert 30 h alt -> noch gültig (<36 h)
    assert grid[-1] == 40.0
    assert None not in grid


def test_grid_max_age():
    grid = m.grid_values([(hours_ago(40), 50.0)], NOW)
    assert grid[0] == 50.0  # 16 h alt
    assert grid[-1] is None  # 40 h alt: über 36 h


def test_evaluate_methods():
    samples = [(hours_ago(30), 60.0), (hours_ago(11.9), 40.0)]
    assert m.evaluate(samples, NOW, "raw") == 40.0
    assert m.evaluate(samples, NOW, "max_24h") == 60.0
    # 12 h bei 60, 12 h bei 40 -> Median zwischen beiden Hälften
    assert m.evaluate(samples, NOW, "median_24h") == 50.0


def test_evaluate_too_little_data():
    assert m.evaluate([(hours_ago(1), 50.0)], NOW) is None
    assert m.evaluate([(hours_ago(1), 50.0)], NOW, "raw") == 50.0
    assert m.evaluate([], NOW, "raw") is None
    assert m.evaluate([(hours_ago(40), 50.0)], NOW, "raw") is None


def series(*pairs, start=datetime(2026, 10, 1, 0, 0, tzinfo=TZ)):
    return [(start + timedelta(minutes=mins), v) for mins, v in pairs]


def test_event_step():
    events = m.detect_water_events(series((0, 36), (60, 36), (120, 73), (180, 74)))
    assert len(events) == 1
    assert (events[0].rule, events[0].before, events[0].after) == ("step", 36, 73)


def test_event_window():
    # 4 Punkte pro Schritt, zusammen +12 in unter 3 h
    events = m.detect_water_events(series((0, 40), (60, 44), (120, 48), (150, 52)))
    assert len(events) == 1
    assert events[0].rule == "window"
    assert events[0].ts == datetime(2026, 10, 1, 2, 30, tzinfo=TZ)


def test_event_window_includes_value_before_window():
    # 30 h kein Wert bei 40 (Carry-forward), dann +6, +6 innerhalb 3 h
    events = m.detect_water_events(series((0, 40), (1800, 46), (1860, 52)))
    assert [e.ts for e in events] == [datetime(2026, 10, 2, 7, 0, tzinfo=TZ)]


def test_no_event_for_slow_rise_and_small_steps():
    assert m.detect_water_events(series((0, 40), (60, 43), (120, 46), (400, 49), (800, 52))) == []


def test_events_merge_within_6h():
    events = m.detect_water_events(series((0, 30), (10, 70), (120, 100), (370, 100), (1000, 50)))
    assert len(events) == 1
    # Abfall dazwischen, neues Ereignis nach > 6 h
    events = m.detect_water_events(series((0, 30), (10, 70), (500, 40), (520, 80)))
    assert len(events) == 2


def test_unavailable_is_ignored():
    events = m.detect_water_events(series((0, 36), (30, None), (60, 73)))
    assert len(events) == 1


def test_drop_and_stale():
    assert m.is_implausible_drop(79, 48)
    assert m.is_implausible_drop(60, 45)
    assert not m.is_implausible_drop(60, 46)
    assert m.is_stale(NOW, hours_ago(37))
    assert not m.is_stale(NOW, hours_ago(31))
    assert m.is_stale(NOW, hours_ago(1), unavailable_since=hours_ago(7))
    assert not m.is_stale(NOW, hours_ago(1), unavailable_since=hours_ago(5))
    assert not m.is_stale(NOW, None)


def test_battery():
    assert m.battery_low(14)
    assert not m.battery_low(15)
    assert not m.battery_low(None)


def test_too_wet_cycle():
    state = m.WetState()
    t = NOW
    state = m.update_too_wet(state, 96, t, 95)
    assert not state.active
    state = m.update_too_wet(state, None, t + timedelta(hours=10), 95)
    assert state.above_since == t
    state = m.update_too_wet(state, 97, t + timedelta(hours=48), 95)
    assert state.active
    # Zwischen max-3 und max: bleibt aktiv, Zeitlauf zurückgesetzt
    state = m.update_too_wet(state, 93, t + timedelta(hours=49), 95)
    assert state.active
    assert state.above_since is None
    state = m.update_too_wet(state, 91, t + timedelta(hours=50), 95)
    assert not state.active


def test_too_wet_reset_by_dip():
    state = m.WetState()
    state = m.update_too_wet(state, 96, NOW, 95)
    state = m.update_too_wet(state, 90, NOW + timedelta(hours=30), 95)
    state = m.update_too_wet(state, 96, NOW + timedelta(hours=31), 95)
    state = m.update_too_wet(state, 96, NOW + timedelta(hours=60), 95)
    assert not state.active
