"""RootineManager: state, listeners, recomputation and mutations (plan 6.5)."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, State, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    EventStateChangedData,
    async_track_state_change_event,
    async_track_time_change,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util
from homeassistant.util.ulid import ulid_now

from .const import (
    CONF_BATTERY_ENTITY,
    CONF_DEFAULT_LOCATION,
    CONF_MOISTURE_ENTITY,
    CONF_MOISTURE_METHOD,
    CONF_NAME,
    CONF_OUTDOOR_TEMP_ENTITY,
    CONF_RAIN_ENTITY,
    CONF_RAIN_THRESHOLD,
    CONF_SEED,
    CONF_TASKS,
    CONF_TEMPERATURE_ENTITY,
    CONF_VALVE_COUNTS,
    CONF_VALVE_ENTITY,
    CONF_WEATHER_ENTITY,
    DEFAULT_RAIN_THRESHOLD,
    EVENT_TASK_DONE,
    LOCATION_INDOOR,
    LOCATION_OUTDOOR,
    LOG_LIMIT,
    SOURCE_DATE_EDIT,
    SOURCE_RAIN,
    SOURCE_SETUP,
    SOURCE_VALVE,
    STORE_SAVE_DELAY,
    SUBENTRY_PLANT,
    TASK_KEY,
    TASK_KIND,
    TASK_MODE,
    TASK_NAME,
    TASK_SCHEDULE,
    TASK_WATER,
    WARN_PROTECT,
    WARN_SENSOR,
    WARN_TOO_WET,
    signal_hub,
    signal_plant,
)
from .logic import climate, moisture, rain, valve
from .logic.due import DueResult, DueStatus, TaskConfig, TaskState, compute_due, worst_status
from .logic.profile import PlantSettings, Profile, photo_url
from .logic.schedule import ScheduleError, TaskKind, WaterMode, parse_schedule
from .logic.texts import TextItem, item_text, summary_text, task_verb
from .photo import PhotoUnresolvable, async_photo_url
from .store import (
    RootineStore,
    profile_from_dict,
    profile_to_dict,
    settings_from_dict,
    settings_to_dict,
    state_from_dict,
    state_to_dict,
)

_LOGGER = logging.getLogger(__name__)

SAMPLE_KEEP = timedelta(hours=48)
# A sensor that keeps reporting the same value only fires state_reported, not state_changed.
# Confirm such a value at most once per hour so the carry-forward never expires while the
# sensor is alive.
CONFIRM_EVERY = timedelta(hours=1)
VALVE_KEEP = timedelta(hours=48)
FORECAST_MAX_AGE = climate.FORECAST_MAX_AGE
WARNING_ORDER = (WARN_PROTECT, WARN_TOO_WET, WARN_SENSOR)
_WARNING_STATUS = {
    WARN_PROTECT: DueStatus.PROTECT,
    WARN_TOO_WET: DueStatus.TOO_WET,
    WARN_SENSOR: DueStatus.CHECK_SENSOR,
}
# statuses that need attention; counted by the hub sensor and get_due alike
URGENT = frozenset({"protect", "overdue", "due", "too_wet", "check_sensor"})
# get_due order (plan 8.4): protect, overdue, due, too_wet, sensor_check, soon
_ITEM_RANK = {"protect": 0, "overdue": 1, "due": 2, "too_wet": 3, "check_sensor": 4, "soon": 5}


@dataclass
class PlantRuntime:
    subentry_id: str
    name: str
    config: Mapping[str, Any]
    tasks: list[TaskConfig]
    profile: Profile
    settings: PlantSettings
    states: dict[str, TaskState]
    log: list[dict[str, Any]] = field(default_factory=list)
    results: dict[str, DueResult] = field(default_factory=dict)
    # sensor tracking
    samples: list[tuple[datetime, float]] = field(default_factory=list)
    last_event: datetime | None = None
    anomaly: dict[str, Any] = field(default_factory=lambda: {"active": False})
    wet: moisture.WetState = field(default_factory=moisture.WetState)
    protect: climate.Protect = field(default_factory=climate.Protect)
    acked: set[str] = field(default_factory=set)
    unavailable_since: datetime | None = None
    valve_transitions: list[tuple[datetime, str]] = field(default_factory=list)
    # derived on every recompute
    moisture_value: float | None = None
    raw_moisture: float | None = None
    battery: float | None = None
    current_temp: float | None = None
    forecast_min: float | None = None
    forecast_max: float | None = None
    warnings: dict[str, dict[str, Any]] = field(default_factory=dict)
    photo_url: str | None = None  # resolved URL of profile.photo (see photo.py)

    def task(self, key: str) -> TaskConfig:
        return next(t for t in self.tasks if t.key == key)

    def has_task(self, key: str) -> bool:
        return any(t.key == key for t in self.tasks)

    @property
    def moisture_entity(self) -> str | None:
        return self.config.get(CONF_MOISTURE_ENTITY)

    @property
    def method(self) -> str:
        return self.config.get(CONF_MOISTURE_METHOD, "median_24h")

    @property
    def outdoor(self) -> bool:
        return self.settings.location == LOCATION_OUTDOOR

    @property
    def status(self) -> DueStatus:
        statuses = [r.status for r in self.results.values()]
        statuses += [_WARNING_STATUS[key] for key in self.warnings]
        return worst_status(statuses)


def tasks_from_config(raw_tasks: list[dict[str, Any]]) -> list[TaskConfig]:
    tasks = []
    for raw in raw_tasks:
        try:
            schedule = parse_schedule(raw[TASK_SCHEDULE])
        except ScheduleError:
            _LOGGER.warning("Invalid schedule for task %s, treating it as paused", raw[TASK_KEY])
            schedule = parse_schedule("")
        tasks.append(
            TaskConfig(
                key=raw[TASK_KEY],
                kind=TaskKind(raw[TASK_KIND]),
                name=raw[TASK_NAME],
                schedule=schedule,
                mode=WaterMode(raw.get(TASK_MODE, WaterMode.TIMER)),
            )
        )
    return tasks


def report_name(task: TaskConfig) -> str:
    """Task name for the German report texts, independent of the UI language."""
    return {TaskKind.WATER: "Gießen", TaskKind.FERTILIZE: "Düngen"}.get(task.kind, task.name)


def _as_float(state: State | None) -> float | None:
    if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
        return None
    try:
        return float(state.state)
    except ValueError:
        return None


class RootineManager:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._store = RootineStore(hass)
        self._raw: dict[str, Any] = {"plants": {}, "rain_days": {}}
        self.plants: dict[str, PlantRuntime] = {}
        self.rain_days: dict[str, float] = {}
        self._unsub: list[CALLBACK_TYPE] = []
        self._forecast: list[dict[str, Any]] = []
        self._forecast_at: datetime | None = None
        self._outdoor_temp: float | None = None
        self._ready = False

    # --- options -----------------------------------------------------------------------

    @property
    def options(self) -> Mapping[str, Any]:
        return self.entry.options

    @property
    def rain_entity(self) -> str | None:
        return self.options.get(CONF_RAIN_ENTITY)

    def rain_threshold(self, plant: PlantRuntime) -> float:
        if plant.settings.rain_threshold is not None:
            return plant.settings.rain_threshold
        return float(self.options.get(CONF_RAIN_THRESHOLD, DEFAULT_RAIN_THRESHOLD))

    # --- load / unload -----------------------------------------------------------------

    async def async_load(self) -> None:
        self._raw = await self._store.async_load()
        stored = self._raw["plants"]
        self.rain_days = dict(self._raw.get("rain_days", {}))
        now = dt_util.now()
        for subentry_id, subentry in self.entry.subentries.items():
            if subentry.subentry_type != SUBENTRY_PLANT:
                continue
            data = subentry.data
            tasks = tasks_from_config(list(data.get(CONF_TASKS, [])))
            saved = stored.get(subentry_id) or self._seed(data, tasks, now)
            stored_states = saved.get("tasks", {})
            initial = {t[TASK_KEY]: t.get("initial_done") for t in data.get(CONF_TASKS, [])}
            states = {
                task.key: state_from_dict(stored_states[task.key])
                if task.key in stored_states
                else self._initial_state(initial.get(task.key), now)
                for task in tasks
            }
            plant = PlantRuntime(
                subentry_id=subentry_id,
                name=data[CONF_NAME],
                config=data,
                tasks=tasks,
                profile=profile_from_dict(saved.get("profile", {})),
                settings=settings_from_dict(saved.get("settings", {})),
                states=states,
                log=list(saved.get("log", [])),
            )
            self._restore_sensor_state(plant, saved)
            self.plants[subentry_id] = plant
        for gone in set(stored) - set(self.plants):
            del stored[gone]
        self._read_initial_states()
        self._subscribe()
        self._ready = True
        self.recompute_all()
        self._persist()

    @staticmethod
    def _initial_state(raw_day: str | None, now: datetime) -> TaskState:
        """State of a task that was added later (the form gives the last-done date)."""
        day = date.fromisoformat(raw_day) if raw_day else now.date()
        return TaskState(dt_util.start_of_local_day(day).replace(hour=12), SOURCE_SETUP)

    def _seed(self, data: Mapping[str, Any], tasks: list[TaskConfig], now: datetime) -> dict:
        seed = data.get(CONF_SEED, {})
        settings = dict(seed.get("settings", {}))
        settings.setdefault("location", self.options.get(CONF_DEFAULT_LOCATION, LOCATION_OUTDOOR))
        task_states = {}
        log = []
        for task in tasks:
            raw_day = seed.get("last_done", {}).get(task.key)
            day = date.fromisoformat(raw_day) if raw_day else now.date()
            when = dt_util.start_of_local_day(day).replace(hour=12)
            task_states[task.key] = state_to_dict(TaskState(when, SOURCE_SETUP))
            log.append(self._log_entry(task.key, SOURCE_SETUP, None, when))
        return {
            "tasks": task_states,
            "profile": seed.get("profile", {}),
            "settings": settings,
            "log": log,
        }

    def _restore_sensor_state(self, plant: PlantRuntime, saved: dict[str, Any]) -> None:
        cutoff = dt_util.now() - SAMPLE_KEEP
        for raw_ts, value in saved.get("moisture_samples", []):
            ts = dt_util.parse_datetime(raw_ts)
            if ts and ts >= cutoff:
                plant.samples.append((dt_util.as_local(ts), float(value)))
        anomaly = saved.get("anomaly")
        if anomaly:
            plant.anomaly = anomaly
        if saved.get("last_event"):
            plant.last_event = dt_util.parse_datetime(saved["last_event"])
        wet = saved.get("wet")
        if wet:
            since = dt_util.parse_datetime(wet["above_since"]) if wet.get("above_since") else None
            plant.wet = moisture.WetState(bool(wet.get("active")), since)
        plant.acked = set(saved.get("acked", []))

    def _read_initial_states(self) -> None:
        """Pick up current values after a start (no event detection on these)."""
        rain_state = self.hass.states.get(self.rain_entity) if self.rain_entity else None
        value = _as_float(rain_state)
        if value is not None:
            self._record_rain(value)
        self._outdoor_temp = _as_float(self._state(self.options.get(CONF_OUTDOOR_TEMP_ENTITY)))
        for plant in self.plants.values():
            self._read_plant_states(plant)

    def _state(self, entity_id: str | None) -> State | None:
        return self.hass.states.get(entity_id) if entity_id else None

    def _read_plant_states(self, plant: PlantRuntime) -> None:
        cfg = plant.config
        state = self._state(plant.moisture_entity)
        value = _as_float(state)
        if value is not None:
            plant.raw_moisture = value
            if not plant.samples and state is not None:
                plant.samples.append((dt_util.as_local(state.last_updated), value))
        valve_state = self._state(cfg.get(CONF_VALVE_ENTITY))
        if valve_state is not None:
            # the current state is the baseline for off -> on detection
            plant.valve_transitions = [
                (dt_util.as_local(valve_state.last_changed), valve_state.state)
            ]
        plant.battery = _as_float(self._state(cfg.get(CONF_BATTERY_ENTITY)))
        plant.current_temp = _as_float(self._state(cfg.get(CONF_TEMPERATURE_ENTITY)))

    def _subscribe(self) -> None:
        def track(entity_id: str | None, handler) -> None:
            if entity_id:
                self._unsub.append(async_track_state_change_event(self.hass, [entity_id], handler))

        track(self.rain_entity, self._on_rain)
        track(self.options.get(CONF_OUTDOOR_TEMP_ENTITY), self._on_outdoor_temp)
        for plant in self.plants.values():
            sid = plant.subentry_id

            def handler(fn, sid=sid):
                @callback
                def _inner(event: Event[EventStateChangedData]) -> None:
                    if sid in self.plants:
                        fn(self.plants[sid], event.data["new_state"])

                return _inner

            track(plant.moisture_entity, handler(self._on_moisture))
            track(plant.config.get(CONF_VALVE_ENTITY), handler(self._on_valve))
            track(plant.config.get(CONF_TEMPERATURE_ENTITY), handler(self._on_temperature))
            track(plant.config.get(CONF_BATTERY_ENTITY), handler(self._on_battery))
        self._unsub.append(
            async_track_time_change(self.hass, self._midnight, hour=0, minute=0, second=10)
        )
        self._unsub.append(async_track_time_interval(self.hass, self._hourly, timedelta(hours=1)))

    async def async_unload(self) -> None:
        for unsub in self._unsub:
            unsub()
        self._unsub.clear()
        await self.async_save()

    # --- persistence -------------------------------------------------------------------

    def _data(self) -> dict[str, Any]:
        plants = {}
        for sid, plant in self.plants.items():
            plants[sid] = {
                "tasks": {k: state_to_dict(s) for k, s in plant.states.items()},
                "profile": profile_to_dict(plant.profile),
                "settings": settings_to_dict(plant.settings),
                "log": plant.log,
                "moisture_samples": [[t.isoformat(), v] for t, v in plant.samples],
                "anomaly": plant.anomaly,
                "last_event": plant.last_event.isoformat() if plant.last_event else None,
                "wet": {
                    "active": plant.wet.active,
                    "above_since": plant.wet.above_since.isoformat()
                    if plant.wet.above_since
                    else None,
                },
                "acked": sorted(plant.acked),
            }
        self._raw["plants"] = plants
        self._raw["rain_days"] = self.rain_days
        return self._raw

    @callback
    def _persist(self) -> None:
        self._store.schedule_save(STORE_SAVE_DELAY, self._data)

    async def async_save(self) -> None:
        await self._store.async_save(self._data())

    # --- event handlers ----------------------------------------------------------------

    def _record_rain(self, value: float) -> None:
        self.rain_days = rain.record_rain(self.rain_days, dt_util.now().date(), value)

    @callback
    def _on_rain(self, event: Event[EventStateChangedData]) -> None:
        value = _as_float(event.data["new_state"])
        if value is None:
            return
        self._record_rain(value)
        self.recompute_all()
        self._persist()

    @callback
    def _on_outdoor_temp(self, event: Event[EventStateChangedData]) -> None:
        self._outdoor_temp = _as_float(event.data["new_state"])
        self.recompute_all()

    @callback
    def _on_temperature(self, plant: PlantRuntime, new: State | None) -> None:
        plant.current_temp = _as_float(new)
        self._notify(plant)

    @callback
    def _on_battery(self, plant: PlantRuntime, new: State | None) -> None:
        plant.battery = _as_float(new)
        self._notify(plant)

    @callback
    def _on_moisture(self, plant: PlantRuntime, new: State | None) -> None:
        now = dt_util.now()
        value = _as_float(new)
        if value is None:
            plant.unavailable_since = plant.unavailable_since or now
            self._notify(plant)
            return
        plant.unavailable_since = None
        plant.raw_moisture = value
        assert new is not None
        ts = dt_util.as_local(new.last_updated)
        self._ingest_moisture(plant, ts, value)
        self._notify(plant)

    def _ingest_moisture(self, plant: PlantRuntime, ts: datetime, value: float) -> None:
        history = plant.samples
        if history and moisture.is_implausible_drop(history[-1][1], value):
            plant.anomaly = {"active": True, "since": ts.isoformat(), "reason": "drop"}
        trigger = moisture.detect_water_trigger(history, ts, value)
        history.append((ts, value))
        del history[: max(0, len(history) - 2000)]
        cutoff = ts - SAMPLE_KEEP
        while len(history) > 1 and history[1][0] < cutoff:
            history.pop(0)
        if trigger is not None and (
            plant.last_event is None or ts - plant.last_event > moisture.EVENT_MERGE
        ):
            self._water_event(plant, ts)

    def _water_event(self, plant: PlantRuntime, ts: datetime) -> None:
        plant.last_event = ts
        plant.anomaly = {"active": False}
        if not plant.has_task(TASK_WATER):
            return
        events = valve.valve_events(plant.valve_transitions)
        source = rain.classify_water_event(
            valve_match=valve.valve_matches(events, ts),
            rain_today_and_yesterday=rain.recent_rain(self.rain_days, ts.date()),
        )
        self._apply_done(plant, TASK_WATER, source, when=ts)

    @callback
    def _on_valve(self, plant: PlantRuntime, new: State | None) -> None:
        if new is None:
            return
        ts = dt_util.as_local(new.last_changed)
        plant.valve_transitions.append((ts, new.state))
        cutoff = ts - VALVE_KEEP
        older = [t for t in plant.valve_transitions if t[0] < cutoff]
        # keep the last state before the window: it is the baseline for the next off -> on
        plant.valve_transitions = older[-1:] + [
            t for t in plant.valve_transitions if t[0] >= cutoff
        ]
        events = valve.valve_events(plant.valve_transitions)
        # a new event starts exactly now; a run within 10 min of the last one merges into it
        starts_new_event = new.state == "on" and bool(events) and events[-1].start == ts
        if starts_new_event and self._valve_counts(plant) and plant.has_task(TASK_WATER):
            self._apply_done(plant, TASK_WATER, SOURCE_VALVE, when=ts)
        self._notify(plant)

    def _valve_counts(self, plant: PlantRuntime) -> bool:
        default = plant.moisture_entity is None
        return bool(plant.config.get(CONF_VALVE_COUNTS, default))

    async def _midnight(self, _now: datetime) -> None:
        await self.async_refresh_photos()
        self.recompute_all()

    async def _hourly(self, _now: datetime) -> None:
        await self._fetch_forecast()
        self.recompute_all()
        self._persist()

    async def _fetch_forecast(self) -> None:
        entity = self.options.get(CONF_WEATHER_ENTITY)
        wanted = any(p.outdoor and self._has_limits(p) for p in self.plants.values())
        if not entity or not wanted:
            self._forecast = []
            return
        try:
            response = await self.hass.services.async_call(
                "weather",
                "get_forecasts",
                {"entity_id": entity, "type": "hourly"},
                blocking=True,
                return_response=True,
            )
            self._forecast = list(response[entity]["forecast"])
            self._forecast_at = dt_util.now()
        except Exception:
            _LOGGER.debug("Forecast fetch failed", exc_info=True)

    @staticmethod
    def _has_limits(plant: PlantRuntime) -> bool:
        return plant.settings.temp_min is not None or plant.settings.temp_max is not None

    async def async_start(self) -> None:
        """Called once after setup: photos, first forecast, then recompute."""
        await self.async_refresh_photos()
        await self._fetch_forecast()
        self.recompute_all()

    async def async_refresh_photos(self) -> None:
        """Resolve photos again (signed URLs expire); a photo that vanished falls back."""
        for plant in self.plants.values():
            plant.photo_url = None
            if plant.profile.photo:
                try:
                    plant.photo_url = await async_photo_url(self.hass, plant.profile.photo)
                except PhotoUnresolvable:
                    _LOGGER.warning("Photo of %s can no longer be resolved", plant.name)

    def picture(self, plant: PlantRuntime) -> str | None:
        """entity_picture: own photo, else OpenPlantbook image, else none."""
        return plant.photo_url or photo_url(replace(plant.profile, photo=None))

    async def async_set_photo(self, subentry_id: str, media_content_id: str | None) -> None:
        """Set or remove the own photo; raises PhotoUnresolvable instead of falling back."""
        plant = self.plants[subentry_id]
        url = await async_photo_url(self.hass, media_content_id) if media_content_id else None
        plant.profile.photo = media_content_id
        plant.photo_url = url
        self._notify(plant)

    # --- recomputation -----------------------------------------------------------------

    @callback
    def recompute_all(self) -> None:
        if not self._ready:
            return
        for plant in self.plants.values():
            self._recompute(plant)
        self._notify_hub()

    @callback
    def _notify(self, plant: PlantRuntime) -> None:
        self._recompute(plant)
        self._notify_hub()
        self._persist()

    @callback
    def _notify_hub(self) -> None:
        async_dispatcher_send(self.hass, signal_hub(self.entry.entry_id))

    def _recompute(self, plant: PlantRuntime) -> None:
        now = dt_util.now()
        self._check_rain(plant, now)
        self._update_moisture(plant, now)
        self._update_protect(plant, now)
        self._update_warnings(plant, now)
        plant.results = {task.key: self._task_result(plant, task, now) for task in plant.tasks}
        async_dispatcher_send(self.hass, signal_plant(self.entry.entry_id, plant.subentry_id))

    def _check_rain(self, plant: PlantRuntime, now: datetime) -> None:
        if not plant.outdoor:
            return
        for task in plant.tasks:
            if task.kind != TaskKind.WATER or task.mode != WaterMode.RAIN:
                continue
            state = plant.states[task.key]
            if rain.rain_resets(
                self.rain_days,
                now.date(),
                state.last_done,
                state.rain_at_done,
                self.rain_threshold(plant),
            ):
                self._apply_done(plant, task.key, SOURCE_RAIN, when=now)

    def _update_moisture(self, plant: PlantRuntime, now: datetime) -> None:
        if not plant.moisture_entity:
            return
        self._confirm_unchanged_value(plant)
        plant.moisture_value = moisture.evaluate(plant.samples, now, plant.method)
        # too wet always uses the smoothed median (plan 7.11)
        median = (
            plant.moisture_value
            if plant.method == "median_24h"
            else moisture.evaluate(plant.samples, now, "median_24h")
        )
        limit = plant.settings.moisture_max
        if limit is None:
            plant.wet = moisture.WetState()
        else:
            plant.wet = moisture.update_too_wet(plant.wet, median, now, limit)
        threshold = plant.settings.moisture_threshold
        if (
            threshold is not None
            and plant.moisture_value is not None
            and plant.moisture_value < threshold
            and not plant.anomaly.get("active")
        ):
            newest = plant.samples[-1][0] if plant.samples else None
            for task in plant.tasks:
                state = plant.states[task.key]
                # Only a reading taken after the last "done" can latch again.
                if (
                    task.kind == TaskKind.WATER
                    and task.mode == WaterMode.SENSOR
                    and newest is not None
                    and newest > state.last_done
                ):
                    state.sensor_due_latched = True

    def _confirm_unchanged_value(self, plant: PlantRuntime) -> None:
        state = self._state(plant.moisture_entity)
        value = _as_float(state)
        if value is None or state is None or not plant.samples:
            return
        reported = dt_util.as_local(state.last_reported)
        last_ts, last_value = plant.samples[-1]
        if value == last_value and reported - last_ts >= CONFIRM_EVERY:
            plant.samples.append((reported, value))
            cutoff = reported - SAMPLE_KEEP
            while len(plant.samples) > 1 and plant.samples[1][0] < cutoff:
                plant.samples.pop(0)

    def _sensor_stale(self, plant: PlantRuntime, now: datetime) -> bool:
        state = self._state(plant.moisture_entity)
        last = dt_util.as_local(state.last_reported) if state is not None else None
        if last is None and plant.samples:
            last = plant.samples[-1][0]
        return moisture.is_stale(now, last, plant.unavailable_since)

    def _update_protect(self, plant: PlantRuntime, now: datetime) -> None:
        settings = plant.settings
        cfg = plant.config
        own = plant.current_temp if cfg.get(CONF_TEMPERATURE_ENTITY) else None
        outdoor_value = self._outdoor_temp if plant.outdoor else None
        current_cold = own if own is not None else outdoor_value
        forecast_min = forecast_max = None
        if plant.outdoor and self._forecast:
            fresh = self._forecast_at is not None and now - self._forecast_at <= FORECAST_MAX_AGE
            if fresh:
                forecast_min, forecast_max = climate.forecast_extremes(self._forecast, now)
        plant.forecast_min, plant.forecast_max = forecast_min, forecast_max
        plant.protect = climate.evaluate_protect(
            plant.protect,
            temp_min=settings.temp_min,
            temp_max=settings.temp_max,
            current_cold=current_cold,
            current_heat=outdoor_value,  # never the plant sensor head (plan 7.10)
            forecast_min=forecast_min,
            forecast_max=forecast_max,
            outdoor=plant.outdoor,
        )

    def _update_warnings(self, plant: PlantRuntime, now: datetime) -> None:
        warnings: dict[str, dict[str, Any]] = {}
        if plant.protect.active:
            temp = {
                "cold_now": plant.current_temp
                if plant.current_temp is not None
                else self._outdoor_temp,
                "cold_forecast": plant.forecast_min,
                "heat_now": self._outdoor_temp,
                "heat_forecast": plant.forecast_max,
            }.get(plant.protect.reason or "")
            warnings[WARN_PROTECT] = {"reason": plant.protect.reason, "value": temp}
        if plant.wet.active:
            since = plant.wet.above_since
            warnings[WARN_TOO_WET] = {
                "since": since.isoformat() if since else None,
                "days": max(2, (now - since).days) if since else 2,
            }
        if plant.moisture_entity:
            reason = None
            if plant.anomaly.get("active"):
                reason = "drop"
            elif self._sensor_stale(plant, now):
                reason = "stale"
            elif moisture.battery_low(plant.battery):
                reason = "battery_low"
            if reason:
                warnings[WARN_SENSOR] = {"reason": reason}
        plant.warnings = warnings
        plant.acked &= set(warnings)

    def _task_result(self, plant: PlantRuntime, task: TaskConfig, now: datetime) -> DueResult:
        state = plant.states[task.key]
        today = now.date()
        timer = compute_due(today, state, task.schedule)
        if task.kind != TaskKind.WATER or task.mode != WaterMode.SENSOR:
            return timer
        has_plan = bool(task.schedule.periods)
        sensor_trouble = WARN_SENSOR in plant.warnings and (
            plant.warnings[WARN_SENSOR]["reason"] in ("drop", "stale")
        )
        if state.sensor_due_latched and not sensor_trouble:
            return DueResult(DueStatus.DUE, today, 0, None, None, "sensor")
        if timer.status in (DueStatus.DUE, DueStatus.OVERDUE, DueStatus.SOON) and has_plan:
            return timer
        if plant.moisture_value is None or sensor_trouble:
            if has_plan:
                return timer
            return DueResult(DueStatus.UNKNOWN, None, None, None, None, "sensor")
        return DueResult(DueStatus.OK, None, None, None, None, "sensor")

    # --- mutations ---------------------------------------------------------------------

    def _log_entry(
        self, task_key: str, source: str, note: str | None, when: datetime
    ) -> dict[str, Any]:
        return {
            "id": ulid_now(),
            "ts": when.isoformat(),
            "task": task_key,
            "source": source,
            "note": note,
            "undone": False,
        }

    def _append_log(self, plant: PlantRuntime, entry: dict[str, Any]) -> None:
        plant.log.append(entry)
        if len(plant.log) <= LOG_LIMIT:
            return
        # Drop the oldest entries but always keep the newest valid entry of every task.
        keep: set[str] = set()
        for task in plant.tasks:
            valid = [e for e in plant.log if e["task"] == task.key and not e["undone"]]
            if valid:
                keep.add(max(valid, key=lambda e: e["ts"])["id"])
        excess = len(plant.log) - LOG_LIMIT
        trimmed = []
        for item in plant.log:
            if excess > 0 and item["id"] not in keep:
                excess -= 1
                continue
            trimmed.append(item)
        plant.log = trimmed

    def _apply_done(
        self,
        plant: PlantRuntime,
        task_key: str,
        source: str,
        *,
        when: datetime | None = None,
        note: str | None = None,
    ) -> None:
        """Set a task done without notifying (callers notify)."""
        when = dt_util.as_local(when) if when else dt_util.now()
        state = plant.states[task_key]
        state.last_done = when
        state.last_source = source
        state.postponed_days = 0
        state.sensor_due_latched = False
        state.rain_at_done = self.rain_days.get(when.date().isoformat(), 0.0)
        self._append_log(plant, self._log_entry(task_key, source, note, when))
        self.hass.bus.async_fire(
            EVENT_TASK_DONE,
            {
                "plant": plant.name,
                "task": task_key,
                "task_name": plant.task(task_key).name,
                "source": source,
                "when": when.isoformat(),
            },
        )

    @callback
    def mark_done(
        self,
        subentry_id: str,
        task_key: str,
        source: str,
        when: datetime | None = None,
        note: str | None = None,
    ) -> None:
        plant = self.plants[subentry_id]
        self._apply_done(plant, task_key, source, when=when, note=note)
        self._notify(plant)

    @callback
    def set_last_done_date(self, subentry_id: str, task_key: str, day: date) -> None:
        """Correction through the date entity (time 12:00 keeps the date stable)."""
        plant = self.plants[subentry_id]
        when = dt_util.start_of_local_day(day).replace(hour=12)
        self._apply_done(plant, task_key, SOURCE_DATE_EDIT, when=when)
        self._notify(plant)

    @callback
    def postpone(self, subentry_id: str, task_key: str, days: int) -> None:
        plant = self.plants[subentry_id]
        plant.states[task_key].postponed_days += days
        plant.states[task_key].sensor_due_latched = False
        self._notify(plant)

    @callback
    def undo_event(self, subentry_id: str, event_id: str) -> bool:
        plant = self.plants[subentry_id]
        entry = next((e for e in plant.log if e["id"] == event_id), None)
        if entry is None:
            return False
        entry["undone"] = True
        task_key = entry["task"]
        if task_key in plant.states:
            valid = [e for e in plant.log if e["task"] == task_key and not e["undone"]]
            if valid:
                latest = max(valid, key=lambda e: e["ts"])
                state = plant.states[task_key]
                state.last_done = dt_util.as_local(dt_util.parse_datetime(latest["ts"]))
                state.last_source = latest["source"]
        self._notify(plant)
        return True

    @callback
    def acknowledge_sensor(self, subentry_id: str) -> None:
        plant = self.plants[subentry_id]
        plant.anomaly = {"active": False}
        self._notify(plant)

    @callback
    def acknowledge_warning(self, subentry_id: str, warning: str) -> None:
        plant = self.plants[subentry_id]
        if warning in plant.warnings:
            plant.acked.add(warning)
        self._notify(plant)

    @callback
    def set_location(self, subentry_id: str, location: str) -> None:
        plant = self.plants[subentry_id]
        plant.settings.location = location
        if location == LOCATION_INDOOR:
            plant.protect = climate.Protect(
                cold=plant.protect.cold if plant.protect.cold == "cold_now" else None
            )
        self._notify(plant)

    @callback
    def update_settings(self, subentry_id: str, **changes: Any) -> None:
        plant = self.plants[subentry_id]
        for name, value in changes.items():
            setattr(plant.settings, name, value)
        self._notify(plant)

    @callback
    def set_profile(self, subentry_id: str, profile: Profile) -> None:
        plant = self.plants[subentry_id]
        plant.profile = profile
        self._notify(plant)

    # --- reports -----------------------------------------------------------------------

    def expected_unique_ids(self) -> set[str]:
        """Unique IDs of every entity that belongs to the current plants and tasks."""
        ids: set[str] = {f"{self.entry.entry_id}_due_count", f"{self.entry.entry_id}_care"}
        for sid, plant in self.plants.items():
            ids |= {
                f"{sid}_care_status",
                f"{sid}_location",
                f"{sid}_protect",
                f"{sid}_temp_min",
                f"{sid}_temp_max",
            }
            if plant.moisture_entity:
                ids |= {
                    f"{sid}_moisture_eval",
                    f"{sid}_moisture_threshold",
                    f"{sid}_moisture_max",
                    f"{sid}_too_wet",
                    f"{sid}_sensor_check",
                    f"{sid}_sensor_checked",
                }
            for task in plant.tasks:
                for art in ("status", "next_due", "due", "last_done", "done"):
                    ids.add(f"{sid}_{task.key}_{art}")
        return ids

    def _task_item(self, plant: PlantRuntime, task: TaskConfig) -> TextItem | None:
        res = plant.results.get(task.key)
        if res is None or res.status not in (
            DueStatus.DUE,
            DueStatus.OVERDUE,
            DueStatus.SOON,
        ):
            return None
        days = -res.days if res.days is not None and res.days < 0 else 0
        return TextItem(plant.name, task.key, report_name(task), res.status.value, days, res.reason)

    def _warning_item(self, plant: PlantRuntime, key: str) -> TextItem:
        info = plant.warnings[key]
        if key == WARN_PROTECT:
            return TextItem(
                plant.name, key, "", "protect", reason=info["reason"], value=info.get("value")
            )
        if key == WARN_TOO_WET:
            return TextItem(plant.name, key, "", "too_wet", days=info.get("days"))
        return TextItem(plant.name, key, "", "check_sensor", reason=info["reason"])

    def due_items(
        self, *, include_soon: bool = True, days_ahead: int = 0, include_acked: bool = False
    ) -> list[dict[str, Any]]:
        """Items for get_due and the hub sensor, sorted by urgency (plan 8.4)."""
        items: list[dict[str, Any]] = []
        for plant in self.plants.values():
            for key in WARNING_ORDER:
                if key not in plant.warnings or (key in plant.acked and not include_acked):
                    continue
                text_item = self._warning_item(plant, key)
                items.append(
                    {
                        "plant": plant.name,
                        "plant_entity": self.care_entity_id(plant.subentry_id),
                        "task": key,
                        "task_name": key,
                        "report_name": "",
                        "status": text_item.status,
                        "due": None,
                        "days": None,
                        "reason": plant.warnings[key].get("reason"),
                        "location": plant.settings.location,
                        "text": item_text(text_item),
                        "_text": text_item,
                    }
                )
            for task in plant.tasks:
                res = plant.results.get(task.key)
                if res is None:
                    continue
                if res.status == DueStatus.SOON and not include_soon:
                    continue
                within = (
                    days_ahead > 0
                    and res.days is not None
                    and 0 < res.days <= days_ahead
                    and res.status in (DueStatus.OK, DueStatus.SOON)
                )
                if (
                    res.status not in (DueStatus.DUE, DueStatus.OVERDUE, DueStatus.SOON)
                    and not within
                ):
                    continue
                days = -res.days if res.days is not None and res.days < 0 else 0
                text_item = TextItem(
                    plant.name,
                    task.key,
                    report_name(task),
                    res.status.value,
                    days,
                    res.reason,
                    in_days=res.days if within else None,
                )
                items.append(
                    {
                        "plant": plant.name,
                        "plant_entity": self.care_entity_id(plant.subentry_id),
                        "task": task.key,
                        "task_name": task.name,
                        "report_name": report_name(task),
                        "status": res.status.value,
                        "due": res.next_due.isoformat() if res.next_due else None,
                        "days": res.days,
                        "reason": res.reason,
                        "location": plant.settings.location,
                        "text": item_text(text_item),
                        "_text": text_item,
                    }
                )
        items.sort(key=lambda i: (_ITEM_RANK.get(i["status"], 9), i["days"] or 0))
        return items

    def care_entity_id(self, subentry_id: str) -> str | None:
        from homeassistant.helpers import entity_registry as er

        return er.async_get(self.hass).async_get_entity_id(
            "sensor", "rootine", f"{subentry_id}_care_status"
        )

    def due_summary(self, *, include_soon: bool = True, days_ahead: int = 0) -> dict[str, Any]:
        """Count, items and the spoken summary, all from the same selection."""
        items = self.due_items(include_soon=include_soon, days_ahead=days_ahead)
        public = [_public(i) for i in items]
        return {
            "count": sum(1 for i in items if i["status"] in URGENT),
            "items": public,
            "text": summary_text([i["_text"] for i in items]),
        }

    def todo_items(self) -> list[dict[str, Any]]:
        """Open to-do entries: due/overdue tasks and unacknowledged warnings."""
        entries = []
        for plant in self.plants.values():
            for key in WARNING_ORDER:
                if key in plant.warnings and key not in plant.acked:
                    info = plant.warnings[key]
                    since = (
                        info.get("since")
                        or plant.anomaly.get("since")
                        or dt_util.now().date().isoformat()
                    )
                    summary = {
                        WARN_PROTECT: f"{plant.name} reinholen oder schützen",
                        WARN_TOO_WET: f"{plant.name}: Staunässe prüfen",
                        WARN_SENSOR: f"{plant.name}: Sensor prüfen",
                    }[key]
                    entries.append(
                        {
                            "uid": f"{plant.subentry_id}:{key}:{since}",
                            "summary": summary,
                            "due": None,
                            "description": item_text(self._warning_item(plant, key)),
                        }
                    )
            for task in plant.tasks:
                res = plant.results.get(task.key)
                if res and res.status in (DueStatus.DUE, DueStatus.OVERDUE):
                    care = plant.profile.care.get(
                        "watering" if task.kind == TaskKind.WATER else "fertilization", ""
                    )
                    text = item_text(self._task_item(plant, task))  # type: ignore[arg-type]
                    entries.append(
                        {
                            "uid": f"{plant.subentry_id}:{task.key}:{res.next_due}",
                            "summary": f"{plant.name} {task_verb(report_name(task))}",
                            "due": res.next_due,
                            "description": f"{text} {care[:200]}".strip(),
                        }
                    )
        return entries

    def history(self, subentry_id: str, limit: int = 50) -> list[dict[str, Any]]:
        return list(reversed(self.plants[subentry_id].log[-limit:]))


def _public(item: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in item.items() if not k.startswith("_") and k != "report_name"}
