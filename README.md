# Rootine

Pflegeroutinen für Pflanzen in Home Assistant: **Gießen, Düngen und weitere Aufgaben**, mit oder ohne
Bodensensor, mit Steckbrief und Foto pro Pflanze und optionalen Artdaten aus OpenPlantbook.
Alles läuft lokal, ohne eigene Cloud-Anbindung und ohne zusätzliche Abhängigkeiten.

*English summary: see the bottom of this page.*

## Was Rootine kann

- **Jede Pflanze ist ein Gerät** mit eigenem Steckbrief (Art, Sorte, Unterlage, Topf, Herkunft, Pflegetexte, Notizen),
  eigenem Foto, Standort (draußen/drinnen), Aufgaben, Sensoren, Ventil und Grenzwerten.
- **Drei Gieß-Modi:**
  - *Nach Plan:* saisonale Intervalle, z. B. „März–Oktober alle 6 Tage, sonst alle 8“, mit Winterpause.
  - *Plan + Regen:* genug Regen seit dem letzten Gießen zählt als gegossen (nur draußen).
  - *Nach Sensor:* ein geglätteter Feuchtewert (Median über 24 h) entscheidet. Gießen wird automatisch erkannt
    (Feuchtesprung, Ventillauf oder Regen).
- **Warnungen:** Frost und Hitze (Sensor und stündliche Wettervorhersage), „zu nass“ bei dauerhaft hoher Feuchte,
  „Sensor prüfen“ bei plötzlichem Abfall, ausbleibenden Meldungen oder schwacher Batterie.
- **Knöpfe, Datum, Verschieben, Verlauf:** „Gegossen“, „Gedüngt“, „Erledigt“; „zuletzt“ lässt sich korrigieren;
  falsch erkannte Ereignisse (z. B. Ventil-Testläufe) lassen sich rückgängig machen.
- **To-do-Liste „Pflanzenpflege“**, Sammelsensor „Fällige Pflegeaufgaben“ und die Aktion `rootine.get_due`
  mit fertigen deutschen Sätzen für Sprachansagen.
- **Eigene Dashboard-Karte** mit Foto, Status, Verlauf, Diagramm und Steckbrief-Bearbeitung.

## Installation

1. HACS → Benutzerdefinierte Repositories → `https://github.com/Simon-Albert/ha-rootine`, Typ **Integration**.
2. „Rootine“ herunterladen, Home Assistant neu starten.
3. Einstellungen → Geräte & Dienste → Integration hinzufügen → **Rootine**.
   Optional: Regensensor (Tagessumme), Regenschwelle, Wetter-Entität, Außentemperatur.
4. Am Rootine-Eintrag **Pflanze hinzufügen**.

Die Dashboard-Karte wird von der Integration selbst bereitgestellt. Nach dem ersten Start einmal den Browser neu laden.

## Eine Pflanze anlegen

1. **Name und Standort.** Mit installierter OpenPlantbook-Integration kannst du eine Art suchen. Leer lassen = von Hand.
2. **Steckbrief.** Alles optional, alles später änderbar, auch das Foto (Handy-Kamera oder Bild aus der Medienübersicht).
3. **Sensoren.** Feuchtesensor, Temperatur, Batterie, Bewässerungsventil, alle optional.
4. **Gießen.** Modus, Plan, bei Sensor die Gieß-Schwelle und die Bewertung, „zuletzt gegossen am“.
5. **Düngen.** Plan (leer = kein Düngen) und „zuletzt gedüngt am“.
6. **Grenzwerte.** Kälteschutz, Hitzeschutz, „zu nass ab“, eigene Regenschwelle. Alle optional.

Später: Zahnrad an der Pflanze → Steckbrief, Foto, OpenPlantbook, Sensoren, Gießen, Düngen, Grenzwerte und weitere
Aufgaben (z. B. „Spinnmilben-Check“). Steckbrief, Foto, Standort und Grenzwerte ändern sich sofort, ohne Neuladen.

### Pläne schreiben

Eine Zeile pro Zeitraum, tolerant bei Leerzeichen und Strichen:

```
01.03.–31.10.: 6
01.11.–28.02.: 8
```

```
01.03.–31.08.: 14
01.09.–28.02.: Pause
```

`ganzjährig: 7` gilt das ganze Jahr. Lücken zwischen Zeiträumen bedeuten Pause. „bis 28.02.“ schließt im Schaltjahr den
29.02. ein. Bei Sensor-Pflanzen ist der Plan ein optionales „spätestens alle n Tage“.

### OpenPlantbook

Nur eine Vorbefüllung: Name, wissenschaftlicher Name, Bild und Pflegetexte. Was du von Hand änderst, überschreibt
„Daten neu laden“ nie. Die Feuchtegrenzwerte von OpenPlantbook werden bewusst nicht übernommen, sie passen nicht zur Skala
vieler Bodensensoren.

## Aktionen

| Aktion | Wirkung |
|---|---|
| `rootine.mark_done` | Aufgabe erledigt setzen, optional rückwirkend (`when`) und mit Notiz |
| `rootine.postpone` | Fälligkeit um 1–60 Tage verschieben |
| `rootine.get_due` | **Antwort** mit allen fälligen Aufgaben und Warnungen, inklusive `text` für Sprachausgabe |
| `rootine.update_profile` | Steckbrief-Felder ändern (leerer Text löscht ein Feld) |
| `rootine.set_photo` | Foto setzen; ohne Foto gilt wieder das OpenPlantbook-Bild |
| `rootine.refresh_species` | Artdaten neu laden (`overwrite_manual` überschreibt auch Eigenes) |
| `rootine.get_history` / `rootine.undo_event` | Verlauf lesen, Eintrag rückgängig machen |

Bei jedem Erledigen feuert das Ereignis `rootine_task_done` (`plant`, `task`, `source`, `when`) und erscheint im Logbuch.

## Beispiele

**Morgens um 8 Uhr eine Push-Nachricht, wenn etwas fällig ist:**

```yaml
automation:
  - alias: Pflanzen morgens
    triggers:
      - trigger: time
        at: "08:00:00"
    conditions:
      - condition: numeric_state
        entity_id: sensor.rootine_faellige_pflegeaufgaben
        above: 0
    actions:
      - action: notify.mobile_app_mein_handy
        data:
          title: Pflanzen
          message: "{{ state_attr('sensor.rootine_faellige_pflegeaufgaben', 'text') }}"
```

**Sprachbericht mit `get_due`:**

```yaml
script:
  pflanzenbericht:
    sequence:
      - action: rootine.get_due
        data:
          include_soon: true
        response_variable: due
      - action: tts.speak
        target:
          entity_id: tts.piper
        data:
          media_player_entity_id: media_player.wohnzimmer
          message: "{{ due.text }}"
```

**Auf ein erkanntes Gießen reagieren:**

```yaml
triggers:
  - trigger: event
    event_type: rootine_task_done
    event_data:
      source: valve
```

## Dashboard-Karte

```yaml
type: custom:rootine-card
entity: sensor.satsuma_pflegestatus   # eine Pflanze
```

```yaml
type: custom:rootine-card
mode: overview                        # alle Pflanzen, sortiert nach Dringlichkeit
```

Die Karte zeigt Foto, Status, Warnungen und je Aufgabe einen Knopf. „Details“ öffnet Steckbrief (bearbeitbar), Foto
ändern, 48-Stunden-Diagramm der Bodenfeuchte mit Schwelle, Verschieben, Nachtragen und den Verlauf mit „Rückgängig“.
Sie nutzt Theme-Variablen und passt zu gläsernen Dashboards (`--ha-card-background`, `--ha-card-backdrop-blur`).

## Fotos aufräumen

Rootine speichert nur den Verweis auf das hochgeladene Bild und **löscht nie Bilder**, auch nicht beim Ersetzen oder
beim Löschen einer Pflanze. Aufräumen: Medien → Hochgeladene Bilder.

## Grenzen

- Keine Licht-, Leitfähigkeits- oder Luftfeuchte-Auswertung (kein Ersatz für Plant Monitor in diesem Teil).
- Rootine sendet selbst keine Benachrichtigungen und steuert keine Ventile.
- Hitze wird nie aus dem Pflanzensensor abgeleitet (der Sensorkopf heizt sich in der Sonne auf), nur aus Vorhersage
  oder Außensensor.
- Der Regen-Modus rechnet mit Tagessummen: Regen von gestern und heute seit dem letzten Gießen.

## English summary

Rootine is a HACS custom integration for plant care routines in Home Assistant. Each plant is a device with a profile
(species, cultivar, pot, care notes), its own photo, tasks with seasonal schedules (watering, fertilizing, custom tasks),
and three watering modes: by schedule, schedule plus rain, or by soil-moisture sensor with automatic detection of watering
(moisture jump, valve run or rain). It warns about frost, heat, waterlogging, sensor problems and low batteries, offers a
to-do list, a `rootine.get_due` action with ready-made texts and a dashboard card. OpenPlantbook is an optional source to
pre-fill the profile; every field stays editable. No cloud, no extra dependencies. The UI is German first, English included.
Install through HACS (custom repository, type *Integration*), then add the **Rootine** integration and add plants from it.

## Entwicklung

```bash
uv venv .venv && uv pip install --python .venv/bin/python -r requirements_test.txt
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/pytest
```

Die Karte ist eine einzelne Datei ohne Build-Schritt
(`custom_components/rootine/frontend/rootine-card.js`); der Render-Smoke-Test braucht Node und Playwright und wird
sonst übersprungen.

Lizenz: MIT.
