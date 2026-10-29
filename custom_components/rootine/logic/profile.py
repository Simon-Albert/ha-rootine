"""Steckbrief: OpenPlantbook und manuelle Einträge zusammenführen (8.11), Foto-URL (8.10)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any

CARE_KEYS = ("watering", "sunlight", "soil", "pruning", "fertilization")
TEXT_FIELDS = ("common_name", "species", "cultivar", "rootstock", "pot", "acquired", "notes")
OPB_FIELDS = ("common_name", "species", *(f"care.{k}" for k in CARE_KEYS))
UPLOAD_PREFIX = "media-source://image_upload/"


@dataclass
class Profile:
    common_name: str | None = None
    species: str | None = None
    cultivar: str | None = None
    rootstock: str | None = None
    pot: str | None = None
    acquired: str | None = None
    care: dict[str, str] = field(default_factory=dict)
    notes: str = ""
    photo: str | None = None
    opb_pid: str | None = None
    opb_image_url: str | None = None
    manual_fields: set[str] = field(default_factory=set)


@dataclass
class PlantSettings:
    location: str = "outdoor"  # outdoor | indoor
    moisture_threshold: int | None = None
    moisture_max: int | None = None
    temp_min: float | None = None
    temp_max: float | None = None
    rain_threshold: float | None = None
    # last value of a limit that was switched off, restored when it is switched on again
    limit_memory: dict[str, float] = field(default_factory=dict)


def get_field(profile: Profile, name: str) -> str | None:
    if name.startswith("care."):
        return profile.care.get(name[5:]) or None
    return getattr(profile, name) or None


def _set_field(profile: Profile, name: str, value: str | None) -> None:
    if name.startswith("care."):
        if value:
            profile.care[name[5:]] = value
        else:
            profile.care.pop(name[5:], None)
    elif name == "notes":
        profile.notes = value or ""
    else:
        setattr(profile, name, value or None)


def parse_opb(data: dict[str, Any]) -> dict[str, Any]:
    """Relevante Felder aus der Antwort von openplantbook.get (8.6)."""
    name = None
    for entry in data.get("common_names") or []:
        if entry.get("language_code") == "de" and entry.get("name"):
            name = entry["name"]
            break
    result: dict[str, Any] = {
        "opb_pid": data.get("pid"),
        "opb_image_url": data.get("image_url"),
        "common_name": name or data.get("alias") or data.get("display_pid"),
        "species": data.get("display_pid"),
    }
    for key in CARE_KEYS:
        if data.get(key):
            result[f"care.{key}"] = data[key]
    result["hint_temp"] = (data.get("min_temp"), data.get("max_temp"))
    return result


def apply_opb(profile: Profile, opb: dict[str, Any], *, overwrite_manual: bool = False) -> Profile:
    """Neu laden / verknüpfen: überschreibt nur nicht-manuelle Felder."""
    new = replace(profile, care=dict(profile.care), manual_fields=set(profile.manual_fields))
    if overwrite_manual:
        new.manual_fields.clear()
    new.opb_pid = opb.get("opb_pid") or new.opb_pid
    new.opb_image_url = opb.get("opb_image_url")
    for name in OPB_FIELDS:
        if name in new.manual_fields:
            continue
        if opb.get(name):
            _set_field(new, name, opb[name])
    return new


def update_fields(profile: Profile, changes: dict[str, str | None]) -> Profile:
    """Teiländerung (rootine.update_profile): Feld setzen, "" oder None löscht. Immer manuell."""
    new = replace(profile, care=dict(profile.care), manual_fields=set(profile.manual_fields))
    for name, value in changes.items():
        _set_field(new, name, value or None)
        new.manual_fields.add(name)
    return new


def from_form(
    submitted: dict[str, str | None], prefilled: dict[str, str | None] | None = None
) -> Profile:
    """Steckbrief aus dem Formular. Geänderte Felder gelten als manuell.

    Von Hand angelegt (kein Vorbefüllen): jedes nicht leere Feld ist manuell, leere
    bleiben offen, damit ein späteres Verknüpfen sie füllen kann.
    """
    profile = Profile()
    prefilled = prefilled or {}
    for name, value in submitted.items():
        _set_field(profile, name, value or None)
        if (value or None) != (prefilled.get(name) or None):
            profile.manual_fields.add(name)
    return profile


def unlink(profile: Profile) -> Profile:
    """OpenPlantbook-Verknüpfung lösen: übrige Felder bleiben und gelten als manuell."""
    new = replace(profile, care=dict(profile.care), manual_fields=set(profile.manual_fields))
    new.opb_pid = None
    new.opb_image_url = None
    for name in (*TEXT_FIELDS, *(f"care.{k}" for k in CARE_KEYS)):
        if get_field(new, name):
            new.manual_fields.add(name)
    return new


_UPLOAD_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def photo_url(profile: Profile) -> str | None:
    """Anzeige-URL: eigenes Foto (Bild-Upload) -> OpenPlantbook-Bild -> None.

    Andere Media-Quellen löst die HA-Schicht auf (media_source) und fällt sonst auf das
    OpenPlantbook-Bild zurück.
    """
    photo = profile.photo
    if photo and photo.startswith(UPLOAD_PREFIX):
        image_id = photo[len(UPLOAD_PREFIX) :]
        if _UPLOAD_ID.match(image_id):
            return f"/api/image/serve/{image_id}/512x512"
    return profile.opb_image_url
