"""Konstanten für Rootine."""

from __future__ import annotations

DOMAIN = "rootine"
VERSION = "1.1.1"  # keep in sync with manifest.json
SUBENTRY_PLANT = "plant"

# Haupteintrag (Optionen)
CONF_RAIN_ENTITY = "rain_entity"
CONF_RAIN_THRESHOLD = "rain_threshold"
CONF_DEFAULT_LOCATION = "default_location"
CONF_WEATHER_ENTITY = "weather_entity"
CONF_OUTDOOR_TEMP_ENTITY = "outdoor_temp_entity"
DEFAULT_RAIN_THRESHOLD = 5.0

# Pflanzen-Subentry (data)
CONF_NAME = "name"
CONF_TASKS = "tasks"
CONF_MOISTURE_ENTITY = "moisture_entity"
CONF_TEMPERATURE_ENTITY = "temperature_entity"
CONF_BATTERY_ENTITY = "battery_entity"
CONF_VALVE_ENTITY = "valve_entity"
CONF_MOISTURE_METHOD = "moisture_method"
CONF_VALVE_COUNTS = "valve_counts_as_watering"
CONF_SEED = "seed"  # Startwerte für den Store (Steckbrief, Standort, zuletzt erledigt)
TASK_KEY = "key"
TASK_KIND = "kind"
TASK_NAME = "name"
TASK_SCHEDULE = "schedule_text"
TASK_MODE = "mode"

# Orte
LOCATION_OUTDOOR = "outdoor"
LOCATION_INDOOR = "indoor"
LOCATIONS = (LOCATION_OUTDOOR, LOCATION_INDOOR)

# Aufgaben
TASK_WATER = "water"
TASK_FERTILIZE = "fertilize"

# Ereignis
EVENT_TASK_DONE = "rootine_task_done"

TASK_CUSTOM = "custom"

# Warnings (keys in PlantRuntime.warnings, also used in get_due and the to-do list)
WARN_PROTECT = "protect"
WARN_TOO_WET = "too_wet"
WARN_SENSOR = "sensor_check"

# Quellen für „zuletzt erledigt“
SOURCE_BUTTON = "button"
SOURCE_TODO = "todo"
SOURCE_SERVICE = "service"
SOURCE_DATE_EDIT = "date_edit"
SOURCE_SETUP = "setup"
SOURCE_SENSOR = "sensor"
SOURCE_VALVE = "valve"
SOURCE_RAIN = "rain"

STORE_KEY = DOMAIN
STORE_VERSION = 1
STORE_SAVE_DELAY = 10
LOG_LIMIT = 200

# Steckbrief-Felder im Formular (Formularname -> Feldname der Logik)
PROFILE_FORM_FIELDS = {
    "common_name": "common_name",
    "species": "species",
    "cultivar": "cultivar",
    "rootstock": "rootstock",
    "pot": "pot",
    "acquired": "acquired",
    "care_watering": "care.watering",
    "care_sunlight": "care.sunlight",
    "care_soil": "care.soil",
    "care_pruning": "care.pruning",
    "care_fertilization": "care.fertilization",
    "notes": "notes",
}


def signal_plant(entry_id: str, subentry_id: str) -> str:
    return f"{DOMAIN}_{entry_id}_{subentry_id}"


def signal_hub(entry_id: str) -> str:
    return f"{DOMAIN}_{entry_id}_hub"
