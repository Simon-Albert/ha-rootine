# Changelog

## 1.1.0

- **Karte:** Feuchte-Balken mit Gieß-Schwelle, farbiger Statusrand, Zusammenfassung im Kopf („1 überfällig · 2 heute“),
  Diagramm mit automatischem Wertebereich, Datum und Uhrzeit in der Sprache des Nutzers, bessere Lesbarkeit.
- **Blueprints:** „Tägliche Pflege-Erinnerung“ und „Pflanzenbericht per Sprachausgabe“, importierbar mit einem Klick.
- **Formulare:** Hilfetexte zu den wichtigsten Feldern (Regen, Sensoren, Gieß-Schwelle, Grenzwerte).
- README mit Screenshots und Schnellinstallation.

## 1.0.0

- **OpenPlantbook** (optional): Art suchen, Steckbrief vorbefüllen, verknüpfen, neu laden, lösen. Eigene Änderungen
  bleiben beim Neu laden erhalten.
- **Regen-Modus** mit Regenschwelle global und pro Pflanze, Standort draußen/drinnen.
- **Kälte- und Hitzeschutz** mit Sensor, Außentemperatur und stündlicher Wettervorhersage.
- **Sensor-Modus:** geglätteter Feuchtewert, automatische Erkennung von Gießen (Sprung, Ventil, Regen),
  Plausibilitätswarnung, „zu nass“, Batteriewarnung, Knopf „Sensor geprüft“.
- **Aktionen:** `mark_done`, `postpone`, `get_due`, `update_profile`, `set_photo`, `refresh_species`,
  `get_history`, `undo_event`.
- **To-do-Liste** „Pflanzenpflege“ (Abhaken erledigt Aufgaben und quittiert Warnungen), weitere Aufgaben je Pflanze,
  Diagnose, Logbuch.
- **Dashboard-Karte** `custom:rootine-card` mit Foto-Upload, Steckbrief-Bearbeitung, Diagramm und Verlauf.
- Markenbilder, README, Quality-Scale-Selbstcheck.

## 0.1.0

- Gerüst, CI (hassfest, HACS, ruff, pytest).
- Reine Fachlogik (`logic/`): Pläne, Fälligkeit, Bewertungswert, Wassereintrag, Ventile, Regen,
  Kälte-/Hitzeschutz, Steckbrief, Berichtstexte; Fixture-Tests gegen anonymisierte Echtdaten.
- Haupteintrag, Pflanzen als Subentries, Steckbrief mit Foto, Standort, Gießen und Düngen nach Plan.
- Entitäten je Pflanze und Aufgabe, Sammelsensor, Store, Mitternachts-Neuberechnung, Ereignis `rootine_task_done`.
