"""Config flow: main entry, options and plant subentries (plan 8.2)."""

from __future__ import annotations

from datetime import date
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from . import openplantbook
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
    DOMAIN,
    LOCATION_OUTDOOR,
    LOCATIONS,
    PROFILE_FORM_FIELDS,
    SUBENTRY_PLANT,
    TASK_CUSTOM,
    TASK_FERTILIZE,
    TASK_KEY,
    TASK_KIND,
    TASK_MODE,
    TASK_NAME,
    TASK_SCHEDULE,
    TASK_WATER,
)
from .logic.oneoff import REMIND_MAX
from .logic.profile import (
    Profile,
    apply_opb,
    from_form,
    get_field,
    parse_opb,
    unlink,
    update_fields,
)
from .logic.schedule import ScheduleError, TaskKind, WaterMode, format_schedule, parse_schedule
from .manager import RootineManager
from .photo import PhotoUnresolvable, async_photo_url
from .store import profile_to_dict

_MULTILINE = selector.TextSelector(selector.TextSelectorConfig(multiline=True))
_TEXT = selector.TextSelector()
_LOCATION = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=list(LOCATIONS),
        translation_key="location",
        mode=selector.SelectSelectorMode.DROPDOWN,
    )
)
# image_upload lets the user take or pick a photo directly in the form (HA 2026.10+)
_PHOTO = selector.MediaSelector(selector.MediaSelectorConfig(accept=["image/*"], image_upload=True))
_METHOD = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=["median_24h", "max_24h", "raw"],
        translation_key="moisture_method",
        mode=selector.SelectSelectorMode.DROPDOWN,
    )
)
_MULTILINE_FIELDS = {
    "care_watering",
    "care_sunlight",
    "care_soil",
    "care_pruning",
    "care_fertilization",
    "notes",
}
SEARCH_AGAIN = "__again__"
SEARCH_NONE = "__none__"


def _number(minimum: float, maximum: float, step: float = 1, unit: str | None = None):
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=step,
            unit_of_measurement=unit,
            mode=selector.NumberSelectorMode.BOX,
        )
    )


def _entity(*domains: str, device_class: str | None = None):
    config: dict[str, Any] = {"domain": list(domains)}
    if device_class:
        config["device_class"] = device_class
    return selector.EntitySelector(selector.EntitySelectorConfig(**config))


def _task_name(language: str, key: str) -> str:
    german = language.startswith("de")
    if key == TASK_WATER:
        return "Gießen" if german else "Watering"
    return "Düngen" if german else "Fertilizing"


def _profile_schema(values: dict[str, str | None]) -> vol.Schema:
    fields: dict[Any, Any] = {}
    for form_name, field_name in PROFILE_FORM_FIELDS.items():
        marker = vol.Optional(form_name, description={"suggested_value": values.get(field_name)})
        fields[marker] = _MULTILINE if form_name in _MULTILINE_FIELDS else _TEXT
    return vol.Schema(fields)


def _form_to_fields(user_input: dict[str, Any]) -> dict[str, str | None]:
    return {
        field: (user_input.get(form) or "").strip() or None
        for form, field in PROFILE_FORM_FIELDS.items()
    }


def _schedule_error(err: ScheduleError) -> tuple[dict[str, str], dict[str, str]]:
    placeholders = {
        "line": str(err.placeholders.get("line", "")),
        "other": str(err.placeholders.get("other", "")),
    }
    return {"base": err.key}, placeholders


def _clean(user_input: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in user_input.items() if v not in (None, "")}


def _options_schema(current: dict[str, Any] | None) -> vol.Schema:
    current = current or {}

    def suggested(key: str) -> dict[str, Any]:
        return {"suggested_value": current.get(key)}

    return vol.Schema(
        {
            vol.Optional(CONF_RAIN_ENTITY, description=suggested(CONF_RAIN_ENTITY)): _entity(
                "sensor", device_class="precipitation"
            ),
            vol.Optional(
                CONF_RAIN_THRESHOLD,
                default=current.get(CONF_RAIN_THRESHOLD, DEFAULT_RAIN_THRESHOLD),
            ): _number(0.1, 100, 0.1, "mm"),
            vol.Optional(CONF_WEATHER_ENTITY, description=suggested(CONF_WEATHER_ENTITY)): _entity(
                "weather"
            ),
            vol.Optional(
                CONF_OUTDOOR_TEMP_ENTITY, description=suggested(CONF_OUTDOOR_TEMP_ENTITY)
            ): _entity("sensor", device_class="temperature"),
            vol.Optional(
                CONF_DEFAULT_LOCATION, default=current.get(CONF_DEFAULT_LOCATION, LOCATION_OUTDOOR)
            ): _LOCATION,
        }
    )


class RootineConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="Rootine", data={}, options=_clean(user_input))
        return self.async_show_form(step_id="user", data_schema=_options_schema(None))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return RootineOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        return {SUBENTRY_PLANT: PlantSubentryFlow}


class RootineOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=_clean(user_input))
        return self.async_show_form(
            step_id="init", data_schema=_options_schema(dict(self.config_entry.options))
        )


def _species_schema(results: dict[str, str], language: str) -> vol.Schema:
    german = language.startswith("de")
    options = [{"value": pid, "label": name} for pid, name in results.items()]
    options.append({"value": SEARCH_AGAIN, "label": "Neu suchen" if german else "Search again"})
    options.append(
        {
            "value": SEARCH_NONE,
            "label": "Ohne OpenPlantbook weiter" if german else "Continue without",
        }
    )
    return vol.Schema(
        {
            vol.Required("species"): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=options,
                    mode=selector.SelectSelectorMode.LIST,
                )
            )
        }
    )


class PlantSubentryFlow(ConfigSubentryFlow):
    """Create (user) and edit (reconfigure) a plant."""

    def __init__(self) -> None:
        self._name = ""
        self._location = LOCATION_OUTDOOR
        self._profile = Profile()
        self._prefilled: dict[str, str | None] = {}
        self._hint = ""
        self._results: dict[str, str] = {}
        self._tasks: list[dict[str, Any]] = []
        self._last_done: dict[str, str] = {}
        self._sensors: dict[str, Any] = {}
        self._structure: dict[str, Any] = {}
        self._settings: dict[str, Any] = {}
        self._edit_key = ""

    # --- create ------------------------------------------------------------------------

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_entry()
        have_opb = openplantbook.is_available(self.hass)
        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            slug = slugify(name)
            if not slug:
                errors["base"] = "invalid_name"
            elif any(s.unique_id == slug for s in entry.subentries.values()):
                errors["base"] = "name_exists"
            else:
                self._name = name
                self._location = user_input["location"]
                term = (user_input.get("search") or "").strip()
                if term and have_opb:
                    return await self._search(term)
                return await self.async_step_profile()
        default_location = entry.options.get(CONF_DEFAULT_LOCATION, LOCATION_OUTDOOR)
        fields: dict[Any, Any] = {
            vol.Required(CONF_NAME): _TEXT,
            vol.Required("location", default=default_location): _LOCATION,
        }
        if have_opb:
            fields[vol.Optional("search")] = _TEXT
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(fields),
            errors=errors,
        )

    async def _search(self, term: str) -> SubentryFlowResult:
        self._results = await openplantbook.async_search(self.hass, term)
        return await self.async_step_species()

    async def async_step_search(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            term = (user_input.get("search") or "").strip()
            if term:
                return await self._search(term)
            return await self.async_step_profile()
        return self.async_show_form(
            step_id="search", data_schema=vol.Schema({vol.Optional("search"): _TEXT})
        )

    async def async_step_species(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            choice = user_input["species"]
            if choice == SEARCH_AGAIN:
                return await self.async_step_search()
            if choice == SEARCH_NONE:
                return await self.async_step_profile()
            data = await openplantbook.async_get(self.hass, choice)
            if data:
                opb = parse_opb(data)
                self._profile = apply_opb(Profile(), opb)
                self._prefilled = {
                    name: opb.get(name)
                    for name in ("common_name", "species", *(f"care.{k}" for k in _CARE))
                }
                low, high = opb.get("hint_temp", (None, None))
                if low is not None or high is not None:
                    self._hint = f"{low}–{high} °C"
            return await self.async_step_profile()
        return self.async_show_form(
            step_id="species",
            data_schema=_species_schema(self._results, self.hass.config.language),
            description_placeholders={"found": str(len(self._results))},
        )

    async def async_step_profile(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            profile = from_form(_form_to_fields(user_input), self._prefilled)
            profile.opb_pid = self._profile.opb_pid
            profile.opb_image_url = self._profile.opb_image_url
            photo = _media_id(user_input.get("photo"))
            if photo and not await self._photo_ok(photo):
                errors["photo"] = "photo_unresolvable"
            else:
                profile.photo = photo
                self._profile = profile
                return await self.async_step_sensors()
        values = {f: get_field(self._profile, f) for f in PROFILE_FORM_FIELDS.values()}
        schema = _profile_schema(values).extend({vol.Optional("photo"): _PHOTO})
        return self.async_show_form(
            step_id="profile",
            data_schema=schema,
            errors=errors,
            description_placeholders={"image": _image_hint(self._profile)},
        )

    async def _photo_ok(self, media_content_id: str) -> bool:
        try:
            await async_photo_url(self.hass, media_content_id)
        except PhotoUnresolvable:
            return False
        return True

    async def async_step_sensors(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            self._sensors = _clean(user_input)
            return await self.async_step_water()
        return self.async_show_form(step_id="sensors", data_schema=_sensors_schema({}))

    async def async_step_water(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        placeholders = _care_placeholders(self._profile, "care.watering")
        has_sensor = CONF_MOISTURE_ENTITY in self._sensors
        has_valve = CONF_VALVE_ENTITY in self._sensors
        if user_input is not None:
            error = _validate_water(user_input, has_sensor)
            if error:
                errors["base"] = error
            else:
                try:
                    text = user_input.get(TASK_SCHEDULE, "")
                    parse_schedule(text)
                except ScheduleError as err:
                    errors, extra = _schedule_error(err)
                    placeholders |= extra
                else:
                    task = self._task(TASK_WATER, TaskKind.WATER, text)
                    task[TASK_MODE] = user_input.get("mode", WaterMode.TIMER.value)
                    self._tasks.append(task)
                    self._last_done[TASK_WATER] = user_input["last_done"]
                    self._structure.update(_water_structure(user_input, has_sensor, has_valve))
                    if user_input.get("moisture_threshold") is not None:
                        self._settings["moisture_threshold"] = int(user_input["moisture_threshold"])
                    return await self.async_step_fertilize()
        default_mode = (
            WaterMode.SENSOR.value
            if has_sensor
            else WaterMode.RAIN.value
            if self._location == LOCATION_OUTDOOR
            and self._get_entry().options.get(CONF_RAIN_ENTITY)
            else WaterMode.TIMER.value
        )
        return self.async_show_form(
            step_id="water",
            data_schema=_water_schema(
                user_input, has_sensor=has_sensor, has_valve=has_valve, default_mode=default_mode
            ),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_fertilize(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        placeholders = _care_placeholders(self._profile, "care.fertilization")
        if user_input is not None:
            text = user_input.get(TASK_SCHEDULE, "")
            try:
                parse_schedule(text)
            except ScheduleError as err:
                errors, extra = _schedule_error(err)
                placeholders |= extra
            else:
                if text.strip():
                    self._tasks.append(self._task(TASK_FERTILIZE, TaskKind.FERTILIZE, text))
                    self._last_done[TASK_FERTILIZE] = user_input["last_done"]
                return await self.async_step_limits()
        return self.async_show_form(
            step_id="fertilize",
            data_schema=_schedule_schema(user_input, with_date=True),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_limits(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        has_sensor = CONF_MOISTURE_ENTITY in self._sensors
        if user_input is not None:
            self._settings.update(_limits_from_input(user_input))
            return self.async_create_entry(
                title=self._name,
                unique_id=slugify(self._name),
                data={
                    CONF_NAME: self._name,
                    CONF_TASKS: self._tasks,
                    **self._sensors,
                    **self._structure,
                    CONF_SEED: {
                        "profile": profile_to_dict(self._profile),
                        "settings": {"location": self._location, **self._settings},
                        "last_done": self._last_done,
                    },
                },
            )
        return self.async_show_form(
            step_id="limits",
            data_schema=_limits_schema(
                {}, has_sensor=has_sensor, outdoor=self._location == "outdoor"
            ),
            description_placeholders={"hint": self._hint or "–"},
        )

    def _task(self, key: str, kind: TaskKind, text: str, name: str | None = None) -> dict[str, Any]:
        return {
            TASK_KEY: key,
            TASK_KIND: kind.value,
            TASK_NAME: name or _task_name(self.hass.config.language, key),
            TASK_SCHEDULE: format_schedule(parse_schedule(text)),
            TASK_MODE: WaterMode.TIMER.value,
        }

    # --- reconfigure -------------------------------------------------------------------

    def _manager(self) -> RootineManager | None:
        return getattr(self._get_entry(), "runtime_data", None)

    def _plant(self):
        manager = self._manager()
        return manager.plants.get(self._reconfigure_subentry_id) if manager else None

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if self._plant() is None:
            return self.async_abort(reason="not_loaded")
        options = [
            "general",
            "profile_edit",
            "photo",
            "openplantbook",
            "sensors_edit",
            "water_edit",
            "fertilize_edit",
            "limits_edit",
            "add_task",
            "edit_task",
            "remove_task",
            "oneoffs",
        ]
        return self.async_show_menu(step_id="reconfigure", menu_options=options)

    async def async_step_general(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        plant = self._plant()
        if plant is None:
            return self.async_abort(reason="not_loaded")
        manager, sid = self._manager(), plant.subentry_id
        subentry = self._get_reconfigure_subentry()
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            slug = slugify(name)
            entry = self._get_entry()
            if not slug:
                errors["base"] = "invalid_name"
            elif any(s.unique_id == slug and sid != i for i, s in entry.subentries.items()):
                errors["base"] = "name_exists"
            else:
                manager.set_location(sid, user_input["location"])
                if name == subentry.data[CONF_NAME]:
                    return self.async_abort(reason="reconfigure_successful")
                return self.async_update_and_abort(
                    entry, subentry, title=name, unique_id=slug, data_updates={CONF_NAME: name}
                )
        return self.async_show_form(
            step_id="general",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default=plant.name): _TEXT,
                    vol.Required("location", default=plant.settings.location): _LOCATION,
                }
            ),
            errors=errors,
        )

    async def async_step_profile_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        plant = self._plant()
        if plant is None:
            return self.async_abort(reason="not_loaded")
        if user_input is not None:
            submitted = _form_to_fields(user_input)
            changes = {
                name: value
                for name, value in submitted.items()
                if value != (get_field(plant.profile, name) or None)
            }
            if changes:
                self._manager().set_profile(
                    plant.subentry_id, update_fields(plant.profile, changes)
                )
            return self.async_abort(reason="reconfigure_successful")
        current = {f: get_field(plant.profile, f) for f in PROFILE_FORM_FIELDS.values()}
        return self.async_show_form(step_id="profile_edit", data_schema=_profile_schema(current))

    async def async_step_photo(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        plant = self._plant()
        if plant is None:
            return self.async_abort(reason="not_loaded")
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await self._manager().async_set_photo(
                    plant.subentry_id, _media_id(user_input.get("photo"))
                )
            except PhotoUnresolvable:
                errors["photo"] = "photo_unresolvable"
            else:
                return self.async_abort(reason="reconfigure_successful")
        current = (
            {"media_content_id": plant.profile.photo, "media_content_type": "image/jpeg"}
            if plant.profile.photo
            else None
        )
        return self.async_show_form(
            step_id="photo",
            data_schema=vol.Schema(
                {vol.Optional("photo", description={"suggested_value": current}): _PHOTO}
            ),
            errors=errors,
        )

    # OpenPlantbook link management (store-only, never reloads)

    async def async_step_openplantbook(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if not openplantbook.is_available(self.hass):
            return self.async_abort(reason="opb_missing")
        return self.async_show_menu(
            step_id="openplantbook", menu_options=["opb_search", "opb_refresh", "opb_unlink"]
        )

    async def async_step_opb_search(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            self._results = await openplantbook.async_search(
                self.hass, user_input.get("search") or ""
            )
            return await self.async_step_opb_pick()
        return self.async_show_form(
            step_id="opb_search", data_schema=vol.Schema({vol.Required("search"): _TEXT})
        )

    async def async_step_opb_pick(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        plant = self._plant()
        if plant is None:
            return self.async_abort(reason="not_loaded")
        if user_input is not None:
            choice = user_input["species"]
            if choice == SEARCH_AGAIN:
                return await self.async_step_opb_search()
            if choice == SEARCH_NONE:
                return self.async_abort(reason="reconfigure_successful")
            data = await openplantbook.async_get(self.hass, choice)
            if not data:
                return self.async_abort(reason="opb_failed")
            profile = apply_opb(plant.profile, parse_opb(data))
            self._manager().set_profile(plant.subentry_id, profile)
            return self.async_abort(reason="reconfigure_successful")
        return self.async_show_form(
            step_id="opb_pick",
            data_schema=_species_schema(self._results, self.hass.config.language),
        )

    async def async_step_opb_refresh(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        plant = self._plant()
        if plant is None:
            return self.async_abort(reason="not_loaded")
        if not plant.profile.opb_pid:
            return self.async_abort(reason="opb_not_linked")
        data = await openplantbook.async_get(self.hass, plant.profile.opb_pid)
        if not data:
            return self.async_abort(reason="opb_failed")
        profile = apply_opb(plant.profile, parse_opb(data))
        self._manager().set_profile(plant.subentry_id, profile)
        return self.async_abort(reason="reconfigure_successful")

    async def async_step_opb_unlink(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        plant = self._plant()
        if plant is None:
            return self.async_abort(reason="not_loaded")
        self._manager().set_profile(plant.subentry_id, unlink(plant.profile))
        return self.async_abort(reason="reconfigure_successful")

    # structure changes (reload through the entry update listener)

    async def async_step_sensors_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        plant = self._plant()
        if plant is None:
            return self.async_abort(reason="not_loaded")
        subentry = self._get_reconfigure_subentry()
        if user_input is not None:
            data = {k: v for k, v in subentry.data.items() if k not in _SENSOR_KEYS}
            data.update(_clean(user_input))
            return self.async_update_and_abort(self._get_entry(), subentry, data=data)
        return self.async_show_form(
            step_id="sensors_edit", data_schema=_sensors_schema(dict(subentry.data))
        )

    async def async_step_water_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        plant = self._plant()
        if plant is None:
            return self.async_abort(reason="not_loaded")
        subentry = self._get_reconfigure_subentry()
        tasks = [dict(t) for t in subentry.data[CONF_TASKS]]
        existing = next(t for t in tasks if t[TASK_KEY] == TASK_WATER)
        has_sensor = bool(plant.moisture_entity)
        has_valve = bool(subentry.data.get(CONF_VALVE_ENTITY))
        errors: dict[str, str] = {}
        placeholders = _care_placeholders(plant.profile, "care.watering")
        if user_input is not None:
            error = _validate_water(user_input, has_sensor, need_date=False)
            if error:
                errors["base"] = error
            else:
                try:
                    text = format_schedule(parse_schedule(user_input.get(TASK_SCHEDULE, "")))
                except ScheduleError as err:
                    errors, extra = _schedule_error(err)
                    placeholders |= extra
                else:
                    existing[TASK_SCHEDULE] = text
                    existing[TASK_MODE] = user_input.get("mode", WaterMode.TIMER.value)
                    if user_input.get("moisture_threshold") is not None:
                        self._manager().update_settings(
                            plant.subentry_id,
                            moisture_threshold=int(user_input["moisture_threshold"]),
                        )
                    data = dict(subentry.data)
                    data[CONF_TASKS] = tasks
                    data.update(_water_structure(user_input, has_sensor, has_valve))
                    return self.async_update_and_abort(self._get_entry(), subentry, data=data)
        current = {
            "mode": existing.get(TASK_MODE, "timer"),
            TASK_SCHEDULE: existing[TASK_SCHEDULE],
            "moisture_threshold": plant.settings.moisture_threshold,
            CONF_MOISTURE_METHOD: subentry.data.get(CONF_MOISTURE_METHOD, "median_24h"),
            CONF_VALVE_COUNTS: subentry.data.get(CONF_VALVE_COUNTS, not has_sensor),
        }
        return self.async_show_form(
            step_id="water_edit",
            data_schema=_water_schema(
                None,
                has_sensor=has_sensor,
                has_valve=has_valve,
                default_mode=current["mode"],
                current=current,
                with_date=False,
            ),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_fertilize_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        return await self._edit_schedule(
            TASK_FERTILIZE, TaskKind.FERTILIZE, "fertilize_edit", user_input
        )

    async def _edit_schedule(
        self, key: str, kind: TaskKind, step_id: str, user_input: dict[str, Any] | None
    ) -> SubentryFlowResult:
        plant = self._plant()
        if plant is None:
            return self.async_abort(reason="not_loaded")
        subentry = self._get_reconfigure_subentry()
        tasks = [dict(t) for t in subentry.data[CONF_TASKS]]
        existing = next((t for t in tasks if t[TASK_KEY] == key), None)
        errors: dict[str, str] = {}
        care_key = "care.watering" if key == TASK_WATER else "care.fertilization"
        placeholders = _care_placeholders(plant.profile, care_key)
        if user_input is not None:
            text = user_input.get(TASK_SCHEDULE, "")
            try:
                schedule_text = format_schedule(parse_schedule(text))
            except ScheduleError as err:
                errors, extra = _schedule_error(err)
                placeholders |= extra
            else:
                if schedule_text:
                    if existing is not None:
                        existing[TASK_SCHEDULE] = schedule_text
                    else:
                        new_task = self._task(key, kind, text)
                        new_task["initial_done"] = dt_util.now().date().isoformat()
                        tasks.append(new_task)
                elif existing is not None:
                    tasks.remove(existing)  # empty plan = no fertilizing
                return self.async_update_and_abort(
                    self._get_entry(), subentry, data_updates={CONF_TASKS: tasks}
                )
        current = existing[TASK_SCHEDULE] if existing else ""
        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(
                {vol.Optional(TASK_SCHEDULE, description={"suggested_value": current}): _MULTILINE}
            ),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_limits_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        plant = self._plant()
        if plant is None:
            return self.async_abort(reason="not_loaded")
        if user_input is not None:
            self._manager().update_settings(
                plant.subentry_id, **_limits_from_input(user_input, reset=_limit_keys(plant))
            )
            return self.async_abort(reason="reconfigure_successful")
        s = plant.settings
        current = {
            "temp_min": s.temp_min,
            "temp_max": s.temp_max,
            "moisture_max": s.moisture_max,
            "rain_threshold": s.rain_threshold,
        }
        return self.async_show_form(
            step_id="limits_edit",
            data_schema=_limits_schema(
                current, has_sensor=bool(plant.moisture_entity), outdoor=plant.outdoor
            ),
            description_placeholders={"hint": _hint_from_profile(plant.profile)},
        )

    # custom tasks

    async def async_step_add_task(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        plant = self._plant()
        if plant is None:
            return self.async_abort(reason="not_loaded")
        subentry = self._get_reconfigure_subentry()
        errors: dict[str, str] = {}
        placeholders = {"care": "–", "line": "", "other": ""}
        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            key = slugify(name)
            tasks = [dict(t) for t in subentry.data[CONF_TASKS]]
            if not key:
                errors["base"] = "invalid_name"
            elif any(t[TASK_KEY] == key for t in tasks) or key in (TASK_WATER, TASK_FERTILIZE):
                errors["base"] = "task_exists"
            else:
                try:
                    text = user_input.get(TASK_SCHEDULE, "")
                    parse_schedule(text)
                except ScheduleError as err:
                    errors, extra = _schedule_error(err)
                    placeholders |= extra
                else:
                    task = self._task(key, TaskKind.CUSTOM, text, name)
                    tasks.append(task)
                    task["initial_done"] = user_input["last_done"]
                    return self.async_update_and_abort(
                        self._get_entry(), subentry, data_updates={CONF_TASKS: tasks}
                    )
        schema = _schedule_schema(user_input, with_date=True).extend(
            {vol.Required(CONF_NAME): _TEXT}
        )
        return self.async_show_form(
            step_id="add_task",
            data_schema=schema,
            errors=errors,
            description_placeholders=placeholders,
        )

    # one-time tasks (store values, never reload)

    async def async_step_oneoffs(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        return self.async_show_menu(
            step_id="oneoffs", menu_options=["add_oneoff", "edit_oneoff", "remove_oneoff"]
        )

    def _save_oneoff(self, user_input: dict[str, Any], oneoff_id: str | None) -> bool:
        name = (user_input.get(CONF_NAME) or "").strip()
        if not name:
            return False
        values = {
            "name": name,
            "due": date.fromisoformat(user_input["due"]),
            "yearly": bool(user_input.get("yearly", False)),
            "remind_days": int(user_input.get("remind_days") or 0),
        }
        manager, sid = self._manager(), self._reconfigure_subentry_id
        if oneoff_id is None:
            manager.add_oneoff(sid, **values)
        else:
            manager.update_oneoff(sid, oneoff_id, **values)
        return True

    async def async_step_add_oneoff(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if self._plant() is None:
            return self.async_abort(reason="not_loaded")
        if user_input is not None and self._save_oneoff(user_input, None):
            return self.async_abort(reason="reconfigure_successful")
        current = user_input or {"due": dt_util.now().date().isoformat()}
        return self.async_show_form(
            step_id="add_oneoff",
            data_schema=self.add_suggested_values_to_schema(_ONEOFF_SCHEMA, current),
            errors={"name": "name_required"} if user_input is not None else {},
        )

    def _oneoff_picker(self) -> vol.Schema:
        plant = self._plant()
        options = [
            {"value": o.id, "label": f"{o.name} ({o.due.strftime('%d.%m.%Y')})"}
            for o in (plant.oneoffs if plant else [])
        ]
        return vol.Schema(
            {
                vol.Required("oneoff"): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=options)
                )
            }
        )

    async def async_step_edit_oneoff(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        plant = self._plant()
        if plant is None:
            return self.async_abort(reason="not_loaded")
        if not plant.oneoffs:
            return self.async_abort(reason="no_oneoffs")
        if user_input is not None:
            self._edit_key = user_input["oneoff"]
            return await self.async_step_edit_oneoff_form()
        return self.async_show_form(step_id="edit_oneoff", data_schema=self._oneoff_picker())

    async def async_step_edit_oneoff_form(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        plant = self._plant()
        item = plant.oneoff(self._edit_key) if plant else None
        if item is None:
            return self.async_abort(reason="no_oneoffs")
        if user_input is not None and self._save_oneoff(user_input, item.id):
            return self.async_abort(reason="reconfigure_successful")
        current = user_input or {
            CONF_NAME: item.name,
            "due": item.due.isoformat(),
            "yearly": item.yearly,
            "remind_days": item.remind_days,
        }
        return self.async_show_form(
            step_id="edit_oneoff_form",
            data_schema=self.add_suggested_values_to_schema(_ONEOFF_SCHEMA, current),
            errors={"name": "name_required"} if user_input is not None else {},
            description_placeholders={"name": item.name},
        )

    async def async_step_remove_oneoff(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        plant = self._plant()
        if plant is None:
            return self.async_abort(reason="not_loaded")
        if not plant.oneoffs:
            return self.async_abort(reason="no_oneoffs")
        if user_input is not None:
            self._manager().remove_oneoff(plant.subentry_id, user_input["oneoff"])
            return self.async_abort(reason="reconfigure_successful")
        return self.async_show_form(step_id="remove_oneoff", data_schema=self._oneoff_picker())

    def _custom_tasks(self) -> list[dict[str, Any]]:
        subentry = self._get_reconfigure_subentry()
        return [t for t in subentry.data[CONF_TASKS] if t[TASK_KIND] == TASK_CUSTOM]

    def _task_picker(self) -> vol.Schema:
        options = [{"value": t[TASK_KEY], "label": t[TASK_NAME]} for t in self._custom_tasks()]
        return vol.Schema(
            {
                vol.Required("task"): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=options)
                )
            }
        )

    async def async_step_edit_task(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if not self._custom_tasks():
            return self.async_abort(reason="no_custom_tasks")
        if user_input is not None:
            self._edit_key = user_input["task"]
            return await self.async_step_edit_task_form()
        return self.async_show_form(step_id="edit_task", data_schema=self._task_picker())

    async def async_step_edit_task_form(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        subentry = self._get_reconfigure_subentry()
        tasks = [dict(t) for t in subentry.data[CONF_TASKS]]
        task = next(t for t in tasks if t[TASK_KEY] == self._edit_key)
        errors: dict[str, str] = {}
        placeholders = {"care": "–", "line": "", "other": ""}
        if user_input is not None:
            try:
                task[TASK_SCHEDULE] = format_schedule(
                    parse_schedule(user_input.get(TASK_SCHEDULE, ""))
                )
            except ScheduleError as err:
                errors, extra = _schedule_error(err)
                placeholders |= extra
            else:
                task[TASK_NAME] = user_input[CONF_NAME].strip() or task[TASK_NAME]
                return self.async_update_and_abort(
                    self._get_entry(), subentry, data_updates={CONF_TASKS: tasks}
                )
        return self.async_show_form(
            step_id="edit_task_form",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default=task[TASK_NAME]): _TEXT,
                    vol.Optional(
                        TASK_SCHEDULE, description={"suggested_value": task[TASK_SCHEDULE]}
                    ): _MULTILINE,
                }
            ),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_remove_task(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if not self._custom_tasks():
            return self.async_abort(reason="no_custom_tasks")
        if user_input is not None:
            subentry = self._get_reconfigure_subentry()
            tasks = [t for t in subentry.data[CONF_TASKS] if t[TASK_KEY] != user_input["task"]]
            return self.async_update_and_abort(
                self._get_entry(), subentry, data_updates={CONF_TASKS: tasks}
            )
        return self.async_show_form(step_id="remove_task", data_schema=self._task_picker())


# --- shared form helpers -------------------------------------------------------------------

_ONEOFF_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): _TEXT,
        vol.Required("due"): selector.DateSelector(),
        vol.Optional("yearly", default=False): selector.BooleanSelector(),
        vol.Optional("remind_days", default=0): _number(0, REMIND_MAX, 1, "d"),
    }
)

_CARE = ("watering", "sunlight", "soil", "pruning", "fertilization")
_SENSOR_KEYS = (
    CONF_MOISTURE_ENTITY,
    CONF_TEMPERATURE_ENTITY,
    CONF_BATTERY_ENTITY,
    CONF_VALVE_ENTITY,
)


def _media_id(value: Any) -> str | None:
    """media_content_id from the media selector (or a plain string)."""
    if isinstance(value, dict):
        return value.get("media_content_id") or None
    return value or None


def _image_hint(profile: Profile) -> str:
    """Markdown preview of the OpenPlantbook image (form descriptions render markdown)."""
    return f"\n\n![]({profile.opb_image_url})" if profile.opb_image_url else ""


def _hint_from_profile(profile: Profile) -> str:
    return "–"


def _care_placeholders(profile: Profile, field: str) -> dict[str, str]:
    return {"care": get_field(profile, field) or "–", "line": "", "other": ""}


def _sensors_schema(current: dict[str, Any]) -> vol.Schema:
    def marker(key: str):
        return vol.Optional(key, description={"suggested_value": current.get(key)})

    return vol.Schema(
        {
            marker(CONF_MOISTURE_ENTITY): _entity("sensor", device_class="moisture"),
            marker(CONF_TEMPERATURE_ENTITY): _entity("sensor", device_class="temperature"),
            marker(CONF_BATTERY_ENTITY): _entity("sensor", device_class="battery"),
            marker(CONF_VALVE_ENTITY): _entity("switch", "valve"),
        }
    )


def _validate_water(
    user_input: dict[str, Any], has_sensor: bool, need_date: bool = True
) -> str | None:
    mode = user_input.get("mode", WaterMode.TIMER.value)
    if mode == WaterMode.SENSOR.value:
        if not has_sensor:
            return "sensor_mode_needs_sensor"
        if user_input.get("moisture_threshold") is None:
            return "threshold_required"
    return None


def _water_structure(
    user_input: dict[str, Any], has_sensor: bool, has_valve: bool
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if has_sensor:
        result[CONF_MOISTURE_METHOD] = user_input.get(CONF_MOISTURE_METHOD, "median_24h")
    if has_valve:
        result[CONF_VALVE_COUNTS] = bool(user_input.get(CONF_VALVE_COUNTS, not has_sensor))
    return result


def _water_schema(
    user_input: dict[str, Any] | None,
    *,
    has_sensor: bool,
    has_valve: bool,
    default_mode: str,
    current: dict[str, Any] | None = None,
    with_date: bool = True,
) -> vol.Schema:
    current = current or {}
    modes = ["timer", "rain"] + (["sensor"] if has_sensor else [])
    fields: dict[Any, Any] = {
        vol.Required("mode", default=default_mode): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=modes,
                translation_key="water_mode",
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Optional(
            TASK_SCHEDULE,
            description={
                "suggested_value": (user_input or {}).get(TASK_SCHEDULE, current.get(TASK_SCHEDULE))
            },
        ): _MULTILINE,
    }
    if has_sensor:
        fields[
            vol.Optional(
                "moisture_threshold",
                description={"suggested_value": current.get("moisture_threshold")},
            )
        ] = _number(0, 100, 1, "%")
        fields[
            vol.Optional(
                CONF_MOISTURE_METHOD, default=current.get(CONF_MOISTURE_METHOD, "median_24h")
            )
        ] = _METHOD
    if has_valve:
        fields[
            vol.Optional(CONF_VALVE_COUNTS, default=current.get(CONF_VALVE_COUNTS, not has_sensor))
        ] = selector.BooleanSelector()
    if with_date:
        fields[vol.Required("last_done", default=dt_util.now().date().isoformat())] = (
            selector.DateSelector()
        )
    return vol.Schema(fields)


def _schedule_schema(user_input: dict[str, Any] | None, *, with_date: bool) -> vol.Schema:
    user_input = user_input or {}
    fields: dict[Any, Any] = {
        vol.Optional(
            TASK_SCHEDULE, description={"suggested_value": user_input.get(TASK_SCHEDULE)}
        ): _MULTILINE
    }
    if with_date:
        fields[vol.Required("last_done", default=dt_util.now().date().isoformat())] = (
            selector.DateSelector()
        )
    return vol.Schema(fields)


def _limits_schema(current: dict[str, Any], *, has_sensor: bool, outdoor: bool) -> vol.Schema:
    def marker(key: str):
        return vol.Optional(key, description={"suggested_value": current.get(key)})

    fields: dict[Any, Any] = {
        marker("temp_min"): _number(-40, 60, 0.5, "°C"),
        marker("temp_max"): _number(-40, 60, 0.5, "°C"),
    }
    if has_sensor:
        fields[marker("moisture_max")] = _number(0, 100, 1, "%")
    if outdoor:
        fields[marker("rain_threshold")] = _number(0.1, 100, 0.1, "mm")
    return vol.Schema(fields)


def _limit_keys(plant) -> tuple[str, ...]:
    """Limits shown for this plant; an empty field clears the limit."""
    keys = ["temp_min", "temp_max"]
    if plant.moisture_entity:
        keys.append("moisture_max")
    if plant.outdoor:
        keys.append("rain_threshold")
    return tuple(keys)


def _limits_from_input(
    user_input: dict[str, Any], *, reset: tuple[str, ...] = ()
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in ("temp_min", "temp_max", "moisture_max", "rain_threshold"):
        value = user_input.get(key)
        if value is None:
            if key in reset:
                result[key] = None
            continue
        result[key] = int(value) if key == "moisture_max" else float(value)
    return result
