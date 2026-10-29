from datetime import datetime

from custom_components.rootine.logic.climate import Protect, evaluate_protect, forecast_extremes

from ..conftest import TZ

NOW = datetime(2026, 10, 29, 20, 0, tzinfo=TZ)


def step(prev, **kw):
    args = dict(
        temp_min=5.0,
        temp_max=None,
        current_cold=None,
        current_heat=None,
        forecast_min=None,
        forecast_max=None,
        outdoor=True,
    )
    args.update(kw)
    return evaluate_protect(prev, **args)


def test_cold_now_and_hysteresis():
    p = step(Protect(), current_cold=4.0)
    assert (p.cold, p.active, p.reason) == ("cold_now", True, "cold_now")
    p = step(p, current_cold=5.5)
    assert p.cold == "cold_now"  # erst ab 6 °C vorbei
    p = step(p, current_cold=6.0)
    assert not p.active


def test_cold_forecast_outdoor_only():
    assert step(Protect(), forecast_min=2.0).cold == "cold_forecast"
    assert not step(Protect(), forecast_min=2.0, outdoor=False).active


def test_cold_ends_only_when_forecast_ok():
    p = step(Protect(), forecast_min=2.0)
    p = step(p, current_cold=10.0, forecast_min=3.0)
    assert p.cold == "cold_forecast"
    p = step(p, current_cold=10.0, forecast_min=6.0)
    assert not p.active


def test_missing_data_keeps_state():
    p = Protect(cold="cold_now")
    assert step(p).cold == "cold_now"


def test_no_limit_no_protection():
    assert not step(Protect(cold="cold_now"), temp_min=None, current_cold=-5).active


def test_heat_only_from_forecast_or_outdoor():
    p = step(Protect(), temp_min=None, temp_max=32.0, forecast_max=34.0)
    assert p.heat == "heat_forecast"
    p = step(p, temp_min=None, temp_max=32.0, forecast_max=30.0, current_heat=31.5)
    assert p.heat == "heat_forecast"  # 31.5 >= 31
    p = step(p, temp_min=None, temp_max=32.0, forecast_max=30.0, current_heat=30.0)
    assert not p.active
    # the plant sensor is never passed as current_heat: no source, no heat
    assert not step(Protect(), temp_min=None, temp_max=32.0, current_cold=36.0).active
    assert step(Protect(), temp_min=None, temp_max=32.0, current_heat=33.0).heat == "heat_now"


def test_forecast_extremes():
    fc = [
        {"datetime": "2026-10-29T19:00:00+01:00", "temperature": 9},
        {"datetime": "2026-10-29T22:00:00+01:00", "temperature": 3.5},
        {"datetime": "2026-10-30T14:00:00+01:00", "temperature": 14},
        {"datetime": "2026-10-30T21:00:00+01:00", "temperature": 20},  # > 24 h
        {"datetime": "2026-10-29T10:00:00+01:00", "temperature": -9},  # Vergangenheit
        {"datetime": "2026-10-29T23:00:00+01:00"},  # no value
    ]
    assert forecast_extremes(fc, NOW) == (3.5, 14.0)
    assert forecast_extremes([], NOW) == (None, None)
