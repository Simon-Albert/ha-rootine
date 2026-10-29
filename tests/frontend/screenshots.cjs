// Renders demo screenshots of the card with made-up data (no real data involved).
// Usage: node tests/frontend/screenshots.cjs <output-dir>
const { chromium } = require("playwright");
const path = require("path");

const leaf = (a, b) => `data:image/svg+xml;utf8,${encodeURIComponent(
  `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'><defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'><stop offset='0' stop-color='${a}'/><stop offset='1' stop-color='${b}'/></linearGradient></defs><rect width='64' height='64' fill='url(#g)'/><path d='M32 52V30M32 36C22 36 16 28 16 20c10 0 16 6 16 16zM32 30c0-10 6-16 16-16 0 10-6 16-16 16z' fill='none' stroke='white' stroke-width='3' stroke-linecap='round' stroke-linejoin='round'/></svg>`)}`;

const plant = (name, state, location, profile, tasks, extra = {}) => ({
  state,
  attributes: { friendly_name: `${name} Pflegestatus`, entity_picture: leaf(...extra.colors), location, profile,
    tasks, warnings: extra.warnings || [], moisture: extra.moisture || null },
});

const states = {
  "sensor.zitrus_care_status": plant("Zitrus", "protect", "outdoor",
    { common_name: "Mandarine", cultivar: "Sorte A", species: "Citrus unshiu", "care.watering": "Gleichmäßig **feucht** halten, Staunässe vermeiden.", notes: "# Notizen\n- Ab 5 °C Nachttemperatur raus\n- Im Winter hell und kühl" },
    { water: { name: "Gießen", status: "due", days: 0 }, fertilize: { name: "Düngen", status: "ok", days: 9 } },
    { colors: ["#43a047", "#1b5e20"], warnings: [{ key: "protect", reason: "cold_forecast", value: 2 }], moisture: { value: 47, raw: 44, threshold: 50, max: 95 } }),
  "sensor.pfirsich_care_status": plant("Pfirsich", "overdue", "outdoor",
    { common_name: "Zwerg-Pfirsich", cultivar: "Sorte B", species: "Prunus persica" },
    { water: { name: "Gießen", status: "overdue", days: -2 }, fertilize: { name: "Düngen", status: "rest", days: null } },
    { colors: ["#ef6c00", "#bf360c"], moisture: { value: 31, raw: 29, threshold: 45, max: null } }),
  "sensor.kirsche_care_status": plant("Kirsche", "soon", "outdoor",
    { common_name: "Süßkirsche", species: "Prunus avium" },
    { water: { name: "Gießen", status: "soon", days: 1 } }, { colors: ["#d81b60", "#880e4f"] }),
  "sensor.kaffee_care_status": plant("Kaffee", "ok", "indoor",
    { common_name: "Kaffeestrauch", species: "Coffea arabica" },
    { water: { name: "Gießen", status: "ok", days: 4 }, fertilize: { name: "Düngen", status: "ok", days: 15 }, milben: { name: "Spinnmilben-Check", status: "ok", days: 6 } },
    { colors: ["#00897b", "#004d40"] }),
  "sensor.zitrus_moisture": { state: "47", attributes: { source_entity: "sensor.raw", threshold: 50 } },
  "sensor.raw": { state: "44", attributes: {} },
};

(async () => {
  const out = process.argv[2] || ".";
  const browser = await chromium.launch();
  for (const theme of ["dark", "light"]) {
    const css = theme === "dark"
      ? "background:#111827;color:#e5e7eb;--primary-color:#38bdf8;--primary-text-color:#e5e7eb;--secondary-text-color:#9ca3af;--ha-card-background:rgba(31,41,55,.72);--card-background-color:#1f2937"
      : "background:#e8eef5;color:#111827;--primary-color:#0284c7;--primary-text-color:#111827;--secondary-text-color:#6b7280;--ha-card-background:rgba(255,255,255,.78);--card-background-color:#ffffff";
    const page = await browser.newPage({ viewport: { width: 980, height: 560 }, deviceScaleFactor: 2 });
    await page.setContent(`<body style="margin:0;padding:18px;font-family:system-ui,sans-serif;${css}"></body>`);
    await page.addScriptTag({ path: path.join(__dirname, "../../custom_components/rootine/frontend/rootine-card.js") });
    await page.evaluate(async (states) => {
      const now = Date.now();
      const hass = { language: "de", states,
        entities: { "sensor.zitrus_care_status": { device_id: "d" }, "sensor.zitrus_moisture": { device_id: "d" } },
        callService: async () => {}, fetchWithAuth: async () => ({ json: async () => ({}) }),
        callWS: async (m) => m.type === "history/history_during_period"
          ? { "sensor.raw": [[60, 40], [57, 34], [55, 30], [52, 24], [50, 19], [47, 12], [45, 6], [44, 0]].map(([v, h]) => ({ s: String(v), lu: now / 1000 - (h + 1) * 3600 * 2.4 + 0 })),
              "sensor.zitrus_moisture": [[61, 40], [58, 34], [56, 28], [53, 22], [51, 16], [49, 10], [47, 3]].map(([v, h]) => ({ s: String(v), lu: now / 1000 - (h + 1) * 3600 * 2.6 })) }
          : { response: { items: [
              { id: "1", ts: new Date(now - 3600e3 * 5).toISOString(), task: "water", source: "valve", undone: false },
              { id: "2", ts: new Date(now - 86400e3 * 3).toISOString(), task: "fertilize", source: "button", undone: false },
              { id: "3", ts: new Date(now - 86400e3 * 6).toISOString(), task: "water", source: "rain", undone: false }] } } };
      const card = document.createElement("rootine-card");
      card.setConfig({ mode: "overview" });
      card.hass = hass;
      document.body.appendChild(card);
      window.__card = card;
    }, states);
    await page.waitForTimeout(150);
    await page.screenshot({ path: path.join(out, `card-overview-${theme}.png`) });
    await page.evaluate(async () => { window.__card._filter = "all"; window.__card._rendered = ""; window.__card._render(); await window.__card._open("sensor.zitrus_care_status"); });
    await page.waitForTimeout(300);
    await page.setViewportSize({ width: 980, height: 900 });
    await page.screenshot({ path: path.join(out, `card-detail-${theme}.png`) });
    await page.close();
  }
  await browser.close();
  console.log("screenshots written");
})();
