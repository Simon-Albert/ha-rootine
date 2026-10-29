"""Gemeinsame Testhilfen: Fixture-Lader (CSV -> Liste (datetime, float | None))."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import voluptuous as vol
from homeassistant.helpers import selector as _selector

# The target is HA 2026.10, whose media selector knows "image_upload". Older HA versions in a local
# development sandbox reject the key; accept it there so the same code can be tested.
if "image_upload" not in _selector.MediaSelectorConfig.__annotations__:
    _original_schema = _selector.MediaSelector.CONFIG_SCHEMA

    def _media_config_schema(config):
        config = dict(config)
        image_upload = vol.Schema(bool)(config.pop("image_upload", False))
        return {**_original_schema(config), "image_upload": image_upload}

    _selector.MediaSelector.CONFIG_SCHEMA = staticmethod(_media_config_schema)

FIXTURES = Path(__file__).parent / "fixtures"  # anonymized real data, local only
SYNTHETIC = Path(__file__).parent / "fixtures_synthetic"  # generated, committed
TZ = ZoneInfo("Europe/Berlin")
INVALID = {"unavailable", "unknown", "", "none"}


def _parse_ts(text: str) -> datetime | None:
    try:
        ts = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return ts.replace(tzinfo=TZ) if ts.tzinfo is None else ts.astimezone(TZ)


def load_series(name: str, directory: Path = FIXTURES) -> list[tuple[datetime, float | None]]:
    """CSV with a timestamp in one column and the state in the last column.

    `unavailable`/`unknown` become None. A missing file skips the test.
    """
    path = directory / name
    if not path.exists():
        if directory == SYNTHETIC:
            raise FileNotFoundError(path)  # generated data must always be present
        pytest.skip(f"Fixture {name} fehlt")
    rows: list[tuple[datetime, float | None]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.reader(handle):
            if len(row) < 2:
                continue
            ts = next((t for t in map(_parse_ts, row[:-1]) if t is not None), None)
            if ts is None:
                continue  # Kopfzeile
            value = row[-1].strip()
            rows.append((ts, None if value.lower() in INVALID else float(value)))
    return sorted(rows, key=lambda r: r[0])


def load_states(name: str, directory: Path = FIXTURES) -> list[tuple[datetime, str]]:
    """Like load_series, but states as text (valves: on/off/unavailable)."""
    path = directory / name
    if not path.exists():
        if directory == SYNTHETIC:
            raise FileNotFoundError(path)  # generated data must always be present
        pytest.skip(f"Fixture {name} fehlt")
    rows: list[tuple[datetime, str]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.reader(handle):
            if len(row) < 2:
                continue
            ts = next((t for t in map(_parse_ts, row[:-1]) if t is not None), None)
            if ts is not None:
                rows.append((ts, row[-1].strip().lower()))
    return sorted(rows, key=lambda r: r[0])
