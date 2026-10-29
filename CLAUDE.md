# Rootine – notes for contributors and coding agents

Home Assistant custom integration (HACS), domain `rootine`: care routines for plants (watering,
fertilizing, custom tasks), with or without a soil moisture sensor, profile and photo per plant,
species data optionally from OpenPlantbook.

## Language

- UI texts in `strings.json`, `translations/de.json`, `translations/en.json`. German is the main language,
  short and everyday wording.
- Report texts (`logic/texts.py`) are German and suitable for speech: no emojis, no abbreviations.
- Code, identifiers, comments and commit messages in English.

## Architecture

- `custom_components/rootine/logic/`: pure Python, **no** `homeassistant` imports. Time (`now`, `today`)
  is always passed in. Schedules, due dates, moisture evaluation, watering detection, valves, rain,
  frost/heat protection, profile merging, report texts.
- `manager.py`: runtime state, state listeners, recomputation (midnight, hourly forecast), mutations.
- `store.py`: persistence in `.storage/rootine`.
- Plants are **config subentries** of the single main entry; entities are added with
  `async_add_entities(..., config_subentry_id=...)`.
- Subentry = structure (form, reload). Store = everyday values (profile, photo, location, limits,
  last done, history, samples); changing them never reloads the entry.
- Actions are registered in `async_setup`, not in `async_setup_entry`.
- The dashboard card is a single plain JS file (`frontend/rootine-card.js`), served by the integration.

## Rules

- No real data, entity IDs or personal details in the repository. Real fixtures (`tests/fixtures/*.csv`)
  stay local and are git-ignored; CI uses `tests/fixtures_synthetic/`.
- Expected values in tests come from the oracles (`tests/fixtures_synthetic/reference.py`), never from
  the integration. If they disagree, find out which side is wrong first.
- Every bug gets a failing test first, then the fix.
- No extra runtime dependencies, no own HTTP client; OpenPlantbook only through the
  `openplantbook.search` / `openplantbook.get` actions of the existing integration.
- Only documented HA APIs; no deprecated device-registry APIs (`async_get_device`, `via_device`,
  `DeviceEntry.config_entries`). No blocking I/O in the event loop. No polling except the hourly forecast.
- Rootine never deletes images from the image upload and never switches valves.
- Entities: `_attr_has_entity_name = True`, `translation_key`, stable `unique_id`.

## Commands

```bash
uv venv .venv && uv pip install --python .venv/bin/python -r requirements_test.txt
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/pytest
python -I scripts/make_synthetic_fixtures.py
python -I tests/fixtures_synthetic/reference.py
node tests/frontend/smoke.cjs                  # card render test (needs Playwright)
node tests/frontend/screenshots.cjs images     # README screenshots from made-up demo data
```

## Release

Version in `manifest.json` and `const.py` equals the tag `vX.Y.Z`; GitHub release with short German notes;
`hacs.json` minimum Home Assistant `2026.10.0`.
