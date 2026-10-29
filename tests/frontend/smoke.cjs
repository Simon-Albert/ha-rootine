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
      warnings: [{ key: "protect", reason: "cold_forecast", value: 2 }],
    },
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
        return { response: { items: [{ id: "1", ts: new Date().toISOString(), task: "water", source: "button", undone: false, note: null }] } };
      },
    };
    const card = document.createElement("rootine-card");
    card.setConfig({ mode: "overview" });
    card.hass = hass;
    document.body.appendChild(card);
    await new Promise((r) => setTimeout(r, 50));
    const out = { overview: card.shadowRoot.textContent };
    card.shadowRoot.querySelector("[data-done='water']").click();
    card.shadowRoot.querySelector("[data-filter='all']").click();
    out.allText = card.shadowRoot.textContent;
    card.shadowRoot.querySelector("[data-details]").click();
    await new Promise((r) => setTimeout(r, 200));
    out.dialog = card.shadowRoot.querySelector(".dialog")?.textContent;
    out.hasChart = !!card.shadowRoot.querySelector("svg.chart path");
    out.xss = !!card.shadowRoot.querySelector("script");
    card.shadowRoot.querySelector("[data-postpone]").click();
    out.calls = calls;
    const single = document.createElement("rootine-card");
    single.setConfig({ entity: "sensor.kaffee_care_status" });
    single.hass = hass;
    document.body.appendChild(single);
    out.single = single.shadowRoot.textContent;
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
  if (result.xss) fail("markdown not escaped");
  const done = result.calls.find((c) => c[1] === "mark_done");
  if (!done || done[2].task !== "water") fail("mark_done not called");
  if (!result.calls.find((c) => c[1] === "postpone")) fail("postpone not called");
  if (!/Kaffee/.test(result.single)) fail("single card");
  console.log("card smoke test ok");
})();
