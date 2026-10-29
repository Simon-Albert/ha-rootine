// Render smoke test for rootine-card.js using the pre-installed Chromium.
// Usage: node tests/frontend/smoke.cjs [screenshot.png]
const { chromium } = require("playwright");
const path = require("path");
const fs = require("fs");

const states = {
  "sensor.satsuma_care_status": {
    state: "overdue",
    attributes: {
      friendly_name: "Satsuma Pflegestatus", entity_picture: "", location: "outdoor",
      profile: { common_name: "Satsuma-Mandarine", cultivar: "Iwasaki", species: "Citrus unshiu",
        "care.watering": "Gleichmäßig **feucht**", notes: "# Notiz\n- Nicht <script>alert(1)</script>" },
      tasks: { water: { name: "Gießen", status: "overdue", days: -2 }, fertilize: { name: "Düngen", status: "rest", days: null } },
      oneoffs: [{ id: "once_a", name: "Umtopfen", due: "2026-10-29", yearly: false, remind_days: 0, status: "due", days: 0 }],
      warnings: [{ key: "protect", reason: "cold_forecast", value: 2 }],
      moisture: { value: 42, raw: 40, threshold: 50, max: 95 },
    },
  },
  "sensor.zitrone_care_status": {
    state: "due",
    attributes: { friendly_name: "Zitrone Pflegestatus", location: "outdoor", profile: {},
      tasks: { water: { name: "Gießen", status: "due", days: 0 }, fertilize: { name: "Düngen", status: "overdue", days: -1 } },
      oneoffs: [], warnings: [] },
  },
  "sensor.kaffee_care_status": {
    state: "ok",
    attributes: { friendly_name: "Kaffee Pflegestatus", location: "indoor", profile: {},
      tasks: { water: { name: "Gießen", status: "ok", days: 4 } }, warnings: [] },
  },
  "sensor.satsuma_moisture": { state: "40", attributes: { source_entity: "sensor.raw", threshold: 50 } },
  "sensor.raw": { state: "38", attributes: {} },
  "select.satsuma_location": { state: "outdoor", attributes: {} },
};

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1000, height: 700 } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  await page.setContent("<body style='background:#1c1c1e;color:#eee;font-family:sans-serif;--primary-color:#03a9f4;--primary-text-color:#eee;--secondary-text-color:#aaa;--card-background-color:#2b2b30'></body>");
  await page.addScriptTag({ path: path.join(__dirname, "../../custom_components/rootine/frontend/rootine-card.js") });
  const result = await page.evaluate(async (states) => {
    const calls = [];
    const now = Date.now();
    const hass = {
      language: "de", states, calls,
      entities: {
        "sensor.satsuma_care_status": { device_id: "d1" }, "sensor.satsuma_moisture": { device_id: "d1" },
        "select.satsuma_location": { device_id: "d1" },
      },
      callService: async (domain, service, data) => calls.push([domain, service, data]),
      callWS: async (msg) => {
        if (msg.type === "history/history_during_period") {
          return { "sensor.raw": [{ s: "60", lu: now / 1000 - 40 * 3600 }, { s: "45", lu: now / 1000 - 10 * 3600 }],
            "sensor.satsuma_moisture": [{ s: "58", lu: now / 1000 - 40 * 3600 }, { s: "44", lu: now / 1000 - 8 * 3600 }] };
        }
        return { response: { items: [
          { id: "1", ts: new Date().toISOString(), task: "water", source: "button", undone: false, note: null },
          { id: "2", ts: new Date().toISOString(), task: "once_old", task_name: "Rückschnitt", source: "service", undone: false, note: null },
        ] } };
      },
    };
    const card = document.createElement("rootine-card");
    card.setConfig({ mode: "overview" });
    card.hass = hass;
    document.body.appendChild(card);
    await new Promise((r) => setTimeout(r, 50));
    const out = { overview: card.shadowRoot.textContent };
    card.shadowRoot.querySelector("[data-done='water']").click();
    await new Promise((r) => setTimeout(r, 20));
    out.doneFeedback = card.shadowRoot.querySelector("[data-done='water']").textContent;
    card.shadowRoot.querySelector("[data-filter='all']").click();
    out.allText = card.shadowRoot.textContent;
    card.shadowRoot.querySelector("[data-details]").click();
    await new Promise((r) => setTimeout(r, 200));
    out.dialog = card.shadowRoot.querySelector(".dialog")?.textContent;
    out.hasChart = !!card.shadowRoot.querySelector("svg.chart path");
    out.xss = !!card.shadowRoot.querySelector("script");
    // editing: background reloads must not wipe what the user typed
    card.shadowRoot.querySelector("[data-edit]").click();
    card.shadowRoot.querySelector("input[name='pot']").value = "Terrakotta 30 cm";
    await card._loadHistory();
    card.hass = { ...hass, states: { ...hass.states } };
    out.typedKept = card.shadowRoot.querySelector("input[name='pot']")?.value;
    card.shadowRoot.querySelector("[data-cancel]").click();
    card.shadowRoot.querySelector("[data-postpone]").click();
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    out.closedByEscape = !card.shadowRoot.querySelector(".dialog");
    out.calls = [...calls];
    // any entity of the plant resolves to its care sensor
    const viaSibling = document.createElement("rootine-card");
    viaSibling.setConfig({ entity: "sensor.satsuma_moisture" });
    viaSibling.hass = hass;
    document.body.appendChild(viaSibling);
    out.sibling = viaSibling.shadowRoot.textContent;
    // failing action shows a toast instead of failing silently
    const failing = document.createElement("rootine-card");
    failing.setConfig({ entity: "sensor.kaffee_care_status" });
    failing.hass = { ...hass, callService: async () => { throw new Error("kaputt"); } };
    document.body.appendChild(failing);
    let toast = null;
    failing.addEventListener("hass-notification", (e) => { toast = e.detail.message; });
    failing.shadowRoot.querySelector("[data-done]").click();
    await new Promise((r) => setTimeout(r, 20));
    out.toast = toast;
    out.buttonReenabled = !failing.shadowRoot.querySelector("[data-done]").disabled;
    const single = document.createElement("rootine-card");
    single.setConfig({ entity: "sensor.kaffee_care_status" });
    single.hass = hass;
    document.body.appendChild(single);
    out.single = single.shadowRoot.textContent;

    // one-time task in the tile, with its own done button
    calls.length = 0;
    out.oneoffShown = /Umtopfen/.test(card.shadowRoot.textContent);
    card.shadowRoot.querySelector("[data-done='once_a']").click();
    await new Promise((r) => setTimeout(r, 20));
    out.oneoffCall = calls.find((c) => c[1] === "mark_done")?.[2];

    // "all watered": asks first and names exactly the plants with due/overdue watering
    calls.length = 0;
    card.shadowRoot.querySelector("[data-allwater]").click();
    out.confirmText = card.shadowRoot.querySelector("[data-confirm]")?.textContent || "";
    out.callsBeforeConfirm = calls.length;
    card.shadowRoot.querySelector("[data-confirm-ok]").click();
    await new Promise((r) => setTimeout(r, 50));
    out.allWaterCalls = calls.filter((c) => c[1] === "mark_done").map((c) => [c[2].entity_id, c[2].task]);
    out.confirmClosed = !card.shadowRoot.querySelector("[data-confirm]");
    const noWater = document.createElement("rootine-card");
    noWater.setConfig({ mode: "overview" });
    noWater.hass = { ...hass, states: { "sensor.kaffee_care_status": hass.states["sensor.kaffee_care_status"] } };
    document.body.appendChild(noWater);
    out.allWaterHidden = !noWater.shadowRoot.querySelector("[data-allwater]");

    // history names one-time tasks
    card.shadowRoot.querySelector("[data-filter='all']").click();
    card.shadowRoot.querySelector("[data-details='sensor.satsuma_care_status']").click();
    await new Promise((r) => setTimeout(r, 100));
    out.historyText = card.shadowRoot.querySelector(".log")?.textContent || "";
    out.taskOptions = [...card.shadowRoot.querySelectorAll("[data-task] option")].map((o) => o.value);
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));

    // compact layout in a narrow column
    const column = document.createElement("div");
    column.style.width = "380px";
    document.body.appendChild(column);
    const compact = document.createElement("rootine-card");
    compact.setConfig({ mode: "overview", layout: "compact" });
    compact.hass = hass;
    column.appendChild(compact);
    await new Promise((r) => setTimeout(r, 50));
    compact.shadowRoot.querySelector("[data-filter='all']").click();
    const rows = [...compact.shadowRoot.querySelectorAll("[data-row]")];
    out.compactRows = rows.map((r) => r.querySelector(".name")?.textContent);
    out.compactFirst = rows[0]?.textContent || "";
    out.compactHasPic = rows.every((r) => r.querySelector(".thumb"));
    const card0 = compact.shadowRoot.querySelector("ha-card");
    out.compactOverflow = card0.scrollWidth - card0.clientWidth;
    out.compactWidth = compact.getBoundingClientRect().width;
    out.compactRowsFit = rows.every((r) => r.getBoundingClientRect().right <= column.getBoundingClientRect().right + 0.5);
    calls.length = 0;
    rows[0].querySelector("[data-done]").click();
    await new Promise((r) => setTimeout(r, 20));
    out.compactDone = calls.find((c) => c[1] === "mark_done")?.[2];
    out.compactDialogAfterButton = !!compact.shadowRoot.querySelector(".dialog");
    rows[0].querySelector(".name").click();
    await new Promise((r) => setTimeout(r, 50));
    out.compactDialog = compact.shadowRoot.querySelector(".dialog")?.textContent || "";
    return out;
  }, states);
  const shot = process.argv[2];
  if (shot) await page.screenshot({ path: shot });
  await browser.close();
  const fail = (m) => { console.error("FAIL:", m); process.exit(1); };
  if (errors.length) fail(errors.join("\n"));
  if (!/Satsuma/.test(result.overview) || /Kaffee/.test(result.overview)) fail("filter 'needs care' wrong");
  if (!/Überfällig/.test(result.overview) || !/Schutz nötig/.test(result.overview)) fail("status/warning missing");
  if (!/Kaffee/.test(result.allText)) fail("filter 'all' wrong");
  if (!/Gleichmäßig/.test(result.dialog) || !result.hasChart) fail("dialog/chart missing");
  if (!/Schwelle 50/.test(result.overview) || !/Bewertung 42/.test(result.overview)) fail("moisture bar missing");
  if (result.xss) fail("markdown not escaped");
  const done = result.calls.find((c) => c[1] === "mark_done");
  if (!done || done[2].task !== "water") fail("mark_done not called");
  if (!result.calls.find((c) => c[1] === "postpone")) fail("postpone not called");
  if (!/Kaffee/.test(result.single)) fail("single card");
  if (result.doneFeedback !== "✓") fail("no feedback after pressing done");
  if (result.typedKept !== "Terrakotta 30 cm") fail(`edit form re-rendered, input lost (${result.typedKept})`);
  if (!result.closedByEscape) fail("escape does not close the dialog");
  if (!/Satsuma-Mandarine/.test(result.sibling)) fail("sibling entity not resolved");
  if (result.toast !== "kaputt" || !result.buttonReenabled) fail("errors are not shown");
  if (!result.oneoffShown || result.oneoffCall?.task !== "once_a") fail("one-time task missing in tile");
  if (!/Satsuma/.test(result.confirmText) || !/Zitrone/.test(result.confirmText) || /Kaffee/.test(result.confirmText))
    fail(`confirmation must name the plants (${result.confirmText})`);
  if (result.callsBeforeConfirm !== 0) fail("all watered acted before confirming");
  const watered = JSON.stringify(result.allWaterCalls.sort());
  if (watered !== JSON.stringify([["sensor.satsuma_care_status", "water"], ["sensor.zitrone_care_status", "water"]]))
    fail(`all watered called ${watered}`);
  if (!result.confirmClosed) fail("confirmation stays open");
  if (!result.allWaterHidden) fail("all watered shown without due watering");
  if (!/Rückschnitt/.test(result.historyText)) fail("history does not name one-time tasks");
  if (!result.taskOptions.includes("once_a")) fail("one-time task not selectable for postpone");
  if (result.compactRows.length !== 3 || result.compactRows[0] !== "Satsuma") fail(`compact rows ${result.compactRows}`);
  if (!result.compactHasPic) fail("compact rows without thumbnail");
  if (!/Schutz nötig|Überfällig/.test(result.compactFirst) || !/Gießen/.test(result.compactFirst))
    fail(`compact row lacks status or next task (${result.compactFirst})`);
  if (result.compactOverflow > 0 || !result.compactRowsFit || result.compactWidth > 380)
    fail(`compact layout scrolls horizontally (${result.compactOverflow}, ${result.compactWidth})`);
  if (result.compactDone?.task !== "water" || result.compactDone?.entity_id !== "sensor.satsuma_care_status")
    fail(`compact button must do the most urgent task (${JSON.stringify(result.compactDone)})`);
  if (result.compactDialogAfterButton) fail("compact button opened the dialog");
  if (!/Satsuma-Mandarine/.test(result.compactDialog)) fail("tapping a compact row does not open the dialog");
  console.log("card smoke test ok");
})();
