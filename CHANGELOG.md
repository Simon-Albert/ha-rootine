# Changelog

## 1.1.1

Korrekturen aus dem Test im echten System.

**Behoben**

- **Ventil nach Pause:** Ruhte ein Ventil länger als zwei Tage, wurde der nächste Lauf nicht erkannt.
- **Sensor-Gießen zählt weiter:** Ist Gießen per Sensor fällig, heißt es ab dem Folgetag „seit 2 Tagen überfällig“
  statt jeden Tag „heute fällig“. Der Beginn wird gespeichert und übersteht Neustarts.
- **Nachtragen:** `mark_done` mit einem Zeitpunkt in der Vergangenheit setzt „zuletzt“ nicht mehr zurück.
  „Zuletzt“ ist immer der jüngste gültige Verlaufseintrag (wie bei „Rückgängig“). Eine Korrektur über das Datum
  bleibt möglich; spätere Einträge gelten dann als rückgängig gemacht.
- **Verlauf:** `get_history` ist nach Zeit sortiert, auch über die Zeitumstellung hinweg.
- **Ein Eintrag pro Gießen:** Ventillauf und dadurch ausgelöster Feuchtesprung ergeben nur noch einen Eintrag;
  kommt die Ventilmeldung nach dem Sprung, wird der Eintrag als „Ventil“ eingeordnet.
- **Karte:** Beim Bearbeiten des Steckbriefs gehen Eingaben nicht mehr verloren, wenn Verlauf oder Diagramm nachladen.

**Neu**

- **Foto direkt im Formular aufnehmen oder hochladen** (Bild-Upload im Medien-Selector). Bilder aus anderen
  Medienquellen werden aufgelöst und angezeigt; lässt sich ein Bild nicht anzeigen, lehnt das Formular es mit
  Hinweis ab, statt still auf das OpenPlantbook-Bild zurückzufallen.
- **Weniger Datenbank:** Steckbrief, Verlauf, Aufgaben, Warnungen und Feuchte-Details (Pflegestatus) sowie Listen und
  Text des Sammelsensors werden nicht mehr im Recorder gespeichert.

**Entwicklung**

- Synthetische Testdaten mit eigenem Generator und unabhängigem Orakel; CI testet damit, die anonymisierten
  Echtdaten bleiben lokal. Tests gegen HA 2026.10.4 (`pytest-homeassistant-custom-component==0.13.375`).

## 1.1.0

- **Karte:** Feuchte-Balken mit Gieß-Schwelle, farbiger Statusrand, Zusammenfassung im Kopf („1 überfällig · 2 heute“),
  Diagramm mit automatischem Wertebereich, Datum und Uhrzeit in der Sprache des Nutzers, bessere Lesbarkeit.
- **Blueprints:** „Tägliche Pflege-Erinnerung“ und „Pflanzenbericht per Sprachausgabe“, importierbar mit einem Klick.
- **Formulare:** Hilfetexte zu den wichtigsten Feldern (Regen, Sensoren, Gieß-Schwelle, Grenzwerte).
- README mit Screenshots und Schnellinstallation.
- **Karte bedienbarer:** sofortiges ✓ nach „Gegossen“, Fehler erscheinen als Hinweis statt still zu scheitern,
  Escape schließt den Dialog, jede Entität einer Pflanze funktioniert als `entity`, Größen für Sections-Dashboards.

**Behoben**

- Ein Feuchtesensor, der lange denselben Wert meldet, wurde nach 36 Stunden als „ohne Wert“ behandelt
  (Gießen sprang auf „Unbekannt“). Rootine bestätigt den Wert jetzt über `last_reported`.
- Der Sammeltext nutzte bei englischer HA-Oberfläche englische Aufgabennamen („Kirsche Watering erledigen“).
- `get_due` mit `include_soon: false` nannte im Text trotzdem „Morgen: …“; Vorschau mit `days_ahead`
  liefert jetzt „ist in 3 Tagen fällig“ statt „ist in Ordnung“.
- Hub-Sensor und `get_due` zählen gleich und berücksichtigen auch Schutz-, Nässe- und Sensor-Warnungen.
- „Plan + Regen“ wird nur noch vorgeschlagen, wenn ein Regensensor eingerichtet ist.
- Logbuch zeigt den Aufgabennamen („Gießen erledigt“) statt des Schlüssels; das Ereignis
  `rootine_task_done` enthält zusätzlich `task_name`.
- OpenPlantbook-Bild erscheint im Steckbrief-Formular als Vorschau statt als Link.

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
