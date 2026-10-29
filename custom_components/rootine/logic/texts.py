"""Deutsche Kurztexte für Berichte und Sprachansagen (7.9)."""

from __future__ import annotations

from dataclasses import dataclass

_VERBS = {"Gießen": "gießen", "Düngen": "düngen"}


def task_verb(task_name: str) -> str:
    """„Gießen“ -> „gießen“, sonst „<Aufgabe> erledigen“."""
    return _VERBS.get(task_name, f"{task_name} erledigen")


def days_text(days: int) -> str:
    return "1 Tag" if days == 1 else f"{days} Tagen"


def _degrees(value: float) -> str:
    rounded = round(value)
    return f"minus {abs(rounded)} Grad" if rounded < 0 else f"{rounded} Grad"


@dataclass(frozen=True)
class TextItem:
    plant: str
    task: str  # Aufgabenschlüssel oder protect | too_wet | sensor_check
    task_name: str
    status: str  # ok|soon|due|overdue|protect|too_wet|check_sensor
    days: int | None = None  # bei overdue: Tage überfällig (positiv); bei too_wet: Dauer
    reason: str | None = None
    value: float | None = None  # gemessene bzw. erwartete Temperatur
    in_days: int | None = None  # fällig in n Tagen (nur für Vorschau mit days_ahead)


def item_text(item: TextItem) -> str:
    plant = item.plant
    if item.status == "protect":
        return _protect_text(item)
    if item.status == "too_wet":
        if item.days:
            return f"{plant}: seit {days_text(item.days)} sehr nass."
        return f"{plant}: sehr nass."
    if item.status == "check_sensor":
        return _sensor_text(item)
    if item.in_days and item.in_days > 1 and item.status in ("ok", "soon"):
        return f"{plant}: {item.task_name} ist in {item.in_days} Tagen fällig."
    if item.status == "due":
        return f"{plant}: {item.task_name} ist heute fällig."
    if item.status == "soon":
        return f"{plant}: {item.task_name} ist morgen fällig."
    if item.status == "overdue":
        return f"{plant}: {item.task_name} ist seit {days_text(item.days or 1)} überfällig."
    return f"{plant}: {item.task_name} ist in Ordnung."


def _protect_text(item: TextItem) -> str:
    plant, value = item.plant, item.value
    temp = "" if value is None else _degrees(value)
    match item.reason:
        case "cold_now":
            return f"{plant}: zu kalt, gemessen {temp}." if temp else f"{plant}: zu kalt."
        case "cold_forecast":
            word = "Frost" if value is not None and value <= 3 else "Kälte"
            tail = f", heute Nacht bis {temp}" if temp else ""
            return f"{plant}: {word} erwartet{tail}. Reinholen oder schützen."
        case "heat_now":
            return f"{plant}: zu heiß, gemessen {temp}." if temp else f"{plant}: zu heiß."
        case "heat_forecast":
            tail = f", bis {temp}" if temp else ""
            return f"{plant}: Hitze erwartet{tail}. Schatten und genug Wasser."
    return f"{plant}: Schutz nötig."


def _sensor_text(item: TextItem) -> str:
    plant = item.plant
    match item.reason:
        case "drop":
            return f"{plant}: Sensor prüfen, der Wert ist plötzlich stark gefallen."
        case "stale":
            return f"{plant}: Sensor prüfen, er meldet nicht mehr."
        case "battery_low":
            return f"{plant}: Sensor-Batterie schwach."
    return f"{plant}: Sensor prüfen."


def _join(parts: list[str]) -> str:
    return ", ".join(parts)


def summary_text(items: list[TextItem]) -> str:
    """Sammeltext: „Heute zu tun: …. Überfällig: ….“, Warnungen als eigene Sätze."""
    today = [f"{i.plant} {task_verb(i.task_name)}" for i in items if i.status == "due"]
    overdue = [f"{i.plant} {task_verb(i.task_name)}" for i in items if i.status == "overdue"]
    soon = [f"{i.plant} {task_verb(i.task_name)}" for i in items if i.status == "soon"]
    later = [
        f"{i.plant} {task_verb(i.task_name)} (in {i.in_days} Tagen)"
        for i in items
        if i.status == "ok" and i.in_days and i.in_days > 1
    ]
    warnings = [item_text(i) for i in items if i.status in ("protect", "too_wet", "check_sensor")]
    sentences: list[str] = []
    if today:
        sentences.append(f"Heute zu tun: {_join(today)}.")
    if overdue:
        sentences.append(f"Überfällig: {_join(overdue)}.")
    sentences.extend(warnings)
    if soon:
        sentences.append(f"Morgen: {_join(soon)}.")
    if later:
        sentences.append(f"Demnächst: {_join(later)}.")
    return " ".join(sentences) if sentences else "Heute ist nichts zu tun."
