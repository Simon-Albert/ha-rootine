# Changelog

## 1.2.4

**Geändert**

- Der Details-Dialog hat bei jeder Pflanze dieselbe Größe und drei Reiter: Übersicht (Aufgaben, Steckbrief, Diagramm), Pflege (Pflegetexte) und Verlauf (Verschieben, Nachtragen, Verlauf). Lange Texte scrollen nur im Inhalt, der Kopf mit Foto und Name bleibt stehen.

## 1.2.3

**Geändert**

- Jede Pflanzenkarte zeigt genau drei Aufgabenzeilen: Gießen, Düngen und die dringendste weitere Aufgabe (mit „+n“, wenn es mehr gibt). Gibt es nichts, steht dort ein gedimmter Hinweis. So sind alle Karten im Raster gleich hoch, auch bei Pflanzen mit vielen Aufgaben.
- Der Details-Dialog behält beim Nachladen von Verlauf und Diagramm seine Scrollposition.

## 1.2.2

**Geändert**

- Neuer Details-Dialog: Kopfbereich mit großem Foto und Statusfarbe, Aufgaben als Kacheln, Steckbrief, Pflegetexte, Diagramm, Verschieben und Verlauf als eigene Abschnitte. Auf dem Handy öffnet er als Sheet von unten.

## 1.2.1

**Geändert**

- Die Karte zeigt die Düngen-Zeile immer an. Hat eine Pflanze keinen Düngeplan, steht dort „Pause · Düngen · nicht nötig“. So sind alle Pflanzenkarten gleich hoch.

## 1.2.0

**Neu**

- **Einmalige Aufgaben** pro Pflanze: Name und Datum, optional jährlich wiederholen und x Tage vorher erinnern.
  Anlegen, bearbeiten und löschen im Menü der Pflanze oder per `rootine.add_oneoff`, `rootine.update_oneoff`,
  `rootine.remove_oneoff`. Sie erscheinen im Pflegestatus, in der To-do-Liste, in `get_due`, in den Berichtstexten
  und in der Karte. Erledigt landen sie im Verlauf; einmalige verschwinden, jährliche springen aufs nächste Jahr.
  `mark_done`, `postpone` und „Rückgängig“ funktionieren auch für sie.
- **Reparaturhinweise** unter Einstellungen → Reparaturen, wenn ein verknüpfter Sensor, ein Ventil, der Regensensor,
  die Wetter-Entität oder der Außensensor fehlt, umbenannt oder deaktiviert wurde. „Beheben“ führt zu einem Formular
  für die neue Entität; der Hinweis verschwindet von selbst, sobald die Entität wieder da ist.
- **Grenzwerte abschaltbar:** Kälteschutz, Hitzeschutz und „zu nass“ haben je einen Schalter. Beim Ausschalten wird
  der Wert gemerkt, beim Einschalten wieder gesetzt. Wird eine Grenze eingeschaltet, holt Rootine die Vorhersage sofort.
- **Karte:** „Alles gegossen“ in der Übersicht für alle Pflanzen mit fälligem oder überfälligem Gießen, mit Rückfrage,
  die die Pflanzen nennt. Kompaktmodus `layout: compact` mit einer Zeile pro Pflanze für schmale Spalten.
  Einmalige Aufgaben mit eigenem Knopf und im Verlauf.

**Geändert**

- **Regen aus Zuwächsen:** Regen pro Tag ist jetzt die Summe der Anstiege des Sensors, dem Ortsdatum der Messung
  zugeordnet. Ein Rückgang ist eine Rücksetzung, der Wert beim Start nur Ausgangspunkt. Regenmesser mit Tageswechsel
  um Mitternacht UTC zählen damit nach einem Neustart oder einer Meldung kurz nach Mitternacht nicht mehr die ganze
  Vortagssumme als heutigen Regen. Beim ersten Start füllt Rootine aus `daily_history` vor (nach UTC-Tagen, Näherung).
- **Gespeicherte Daten** haben eine Versionsnummer und werden beim Update automatisch umgestellt
  (im Test mit einem nachgebauten gespeicherten Stand von 1.1.0 geprüft).

**Entwicklung**

- Synthetische Testdaten neu erfunden (andere Uhrzeiten, Mengen und Abläufe), dazu ein Regenzähler mit Rücksetzung
  um Mitternacht UTC; Erwartungen neu aus dem Orakel. Tests gegen die Echtdaten liegen nur noch lokal.
- Tests für die OpenPlantbook-Anbindung und die To-do-Liste vervollständigt; alle Code-Kommentare auf Englisch.

## 1.1.1

Korrekturen nach einem Review.

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
