"""Gemeinsame Testhilfen: Fixture-Lader (CSV -> Liste (datetime, float | None))."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

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
    """CSV mit Zeitstempel in einer Spalte und Zustand in der letzten Spalte.

    `unavailable`/`unknown` werden zu None. Fehlt die Datei, wird der Test übersprungen.
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
    """Wie load_series, aber Zustände als Text (Ventile: on/off/unavailable)."""
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
