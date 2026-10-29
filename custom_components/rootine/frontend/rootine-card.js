/*
 * Rootine card – plant care overview and detail dialog.
 * Plain web component, no build step and no dependencies (HACS ships files as they are).
 * Usage:  type: custom:rootine-card
 *         entity: sensor.<plant>_care_status     # one plant
 *         mode: overview                          # or: all plants
 */
const VERSION = "1.1.0";

const T = {
  de: {
    overview: "Pflanzen", needs: "Braucht Pflege", all: "Alle", none: "Alles in Ordnung.",
    status: { ok: "In Ordnung", soon: "Morgen", due: "Heute", overdue: "Überfällig", rest: "Pause",
      unknown: "Unbekannt", protect: "Schutz nötig", too_wet: "Zu nass", check_sensor: "Sensor prüfen" },
    warn: { protect: "Schutz nötig", too_wet: "Zu nass", sensor_check: "Sensor prüfen" },
    reason: { cold_now: "zu kalt", cold_forecast: "Kälte erwartet", heat_now: "zu heiß",
      heat_forecast: "Hitze erwartet", drop: "Wert stark gefallen", stale: "meldet nicht",
      battery_low: "Batterie schwach" },
    done: "Erledigt", water: "Gegossen", fertilize: "Gedüngt", postpone: "Verschieben",
    days: (n) => (n === 0 ? "heute" : n === 1 ? "morgen" : n < 0 ? `seit ${-n} Tg.` : `in ${n} Tg.`),
    details: "Details", close: "Schließen", edit: "Bearbeiten", save: "Speichern", cancel: "Abbrechen",
    photo: "Foto ändern", history: "Verlauf", undo: "Rückgängig", undone: "rückgängig",
    backfill: "Nachtragen", task: "Aufgabe", date: "Datum", location: "Standort",
    outdoor: "Draußen", indoor: "Drinnen", notes: "Notizen", care: "Pflege",
    fields: { common_name: "Name der Art", species: "Wissenschaftlicher Name", cultivar: "Sorte",
      rootstock: "Unterlage", pot: "Topf", acquired: "Herkunft", "care.watering": "Gießen",
      "care.sunlight": "Licht", "care.soil": "Erde", "care.pruning": "Schnitt",
      "care.fertilization": "Düngen", notes: "Notizen" },
    chart: "Bodenfeuchte, 48 h", raw: "Rohwert", eval: "Bewertung", threshold: "Schwelle",
    sources: { button: "Knopf", todo: "To-do", service: "Aktion", date_edit: "Datum", sensor: "Sensor",
      valve: "Ventil", rain: "Regen", setup: "Einrichtung" },
    noEntity: "Bitte eine Pflanze (entity) oder mode: overview angeben.",
    uploadFailed: "Das Foto konnte nicht hochgeladen werden.",
  },
  en: {
    overview: "Plants", needs: "Needs care", all: "All", none: "All good.",
    status: { ok: "OK", soon: "Tomorrow", due: "Today", overdue: "Overdue", rest: "Resting",
      unknown: "Unknown", protect: "Protect", too_wet: "Too wet", check_sensor: "Check sensor" },
    warn: { protect: "Protection needed", too_wet: "Too wet", sensor_check: "Check sensor" },
    reason: { cold_now: "too cold", cold_forecast: "cold expected", heat_now: "too hot",
      heat_forecast: "heat expected", drop: "value dropped", stale: "not reporting",
      battery_low: "battery low" },
    done: "Done", water: "Watered", fertilize: "Fertilized", postpone: "Postpone",
    days: (n) => (n === 0 ? "today" : n === 1 ? "tomorrow" : n < 0 ? `${-n}d overdue` : `in ${n}d`),
    details: "Details", close: "Close", edit: "Edit", save: "Save", cancel: "Cancel",
    photo: "Change photo", history: "History", undo: "Undo", undone: "undone",
    backfill: "Add past entry", task: "Task", date: "Date", location: "Location",
    outdoor: "Outdoor", indoor: "Indoor", notes: "Notes", care: "Care",
    fields: { common_name: "Common name", species: "Species", cultivar: "Cultivar",
      rootstock: "Rootstock", pot: "Pot", acquired: "Acquired", "care.watering": "Watering",
      "care.sunlight": "Sunlight", "care.soil": "Soil", "care.pruning": "Pruning",
      "care.fertilization": "Fertilizing", notes: "Notes" },
    chart: "Soil moisture, 48 h", raw: "Raw", eval: "Evaluated", threshold: "Threshold",
    sources: { button: "Button", todo: "To-do", service: "Action", date_edit: "Date", sensor: "Sensor",
      valve: "Valve", rain: "Rain", setup: "Setup" },
    noEntity: "Please set a plant (entity) or mode: overview.",
    uploadFailed: "The photo could not be uploaded.",
  },
};

const RANK = ["protect", "overdue", "due", "too_wet", "check_sensor", "soon", "ok", "rest", "unknown"];
const COLORS = {
  protect: "#3b82f6", overdue: "#ef4444", due: "#f59e0b", too_wet: "#06b6d4",
  check_sensor: "#a855f7", soon: "#eab308", ok: "#22c55e", rest: "#94a3b8", unknown: "#94a3b8",
};
const PROFILE_FIELDS = ["common_name", "species", "cultivar", "rootstock", "pot", "acquired",
  "care.watering", "care.sunlight", "care.soil", "care.pruning", "care.fertilization", "notes"];

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

/** Minimal, safe markdown: headings, bold, italic, lists, line breaks. Input is escaped first. */
function markdown(text) {
  const lines = esc(text).split("\n");
  let html = "", list = false;
  for (const raw of lines) {
    let line = raw
      .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
      .replace(/(^|\W)_(.+?)_(?=\W|$)/g, "$1<i>$2</i>");
    const item = /^\s*[-*]\s+(.*)/.exec(line);
    if (item) {
      if (!list) { html += "<ul>"; list = true; }
      html += `<li>${item[1]}</li>`;
      continue;
    }
    if (list) { html += "</ul>"; list = false; }
    const head = /^(#{1,3})\s+(.*)/.exec(line);
    html += head ? `<h${head[1].length + 2}>${head[2]}</h${head[1].length + 2}>` : line ? `<p>${line}</p>` : "";
  }
  return html + (list ? "</ul>" : "");
}

const STYLE = `
:host { display: block; }
ha-card { display: block; }
ha-card { padding: 12px; overflow: hidden; background: var(--ha-card-background, var(--card-background-color));
  backdrop-filter: blur(var(--ha-card-backdrop-blur, 12px)); }
.head { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; margin-bottom: 10px; }
.head .summary { flex: 1; }
.head h2 { margin: 0; font-size: 1.1em; font-weight: 600; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(330px, 1fr)); gap: 10px; }
.plant { --accent: var(--primary-color); position: relative; display: flex; flex-direction: column; gap: 8px; padding: 12px 12px 10px 16px; border-radius: 16px; overflow: hidden;
  transition: transform .15s ease, box-shadow .15s ease;
  background: color-mix(in srgb, var(--primary-text-color) 5%, transparent);
  border: 1px solid color-mix(in srgb, var(--primary-text-color) 10%, transparent); }
.plant::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 5px; background: var(--accent); }
.plant:hover { transform: translateY(-1px); box-shadow: 0 6px 18px rgba(0,0,0,.18); }
.summary { display: flex; gap: 6px; flex-wrap: wrap; }
.bar { position: relative; height: 8px; border-radius: 6px; background: color-mix(in srgb, var(--primary-text-color) 12%, transparent); }
.bar .fill { position: absolute; left: 0; top: 0; bottom: 0; border-radius: 6px; background: var(--accent); transition: width .4s ease; }
.bar .mark { position: absolute; top: -3px; bottom: -3px; width: 2px; background: var(--primary-text-color); opacity: .75; border-radius: 1px; }
.barlabel { display: flex; justify-content: space-between; font-size: .78em; color: var(--secondary-text-color); margin-top: 2px; }
.top { display: flex; gap: 10px; align-items: center; }
.pic { width: 56px; height: 56px; border-radius: 12px; object-fit: cover; flex: none;
  background: color-mix(in srgb, var(--primary-text-color) 10%, transparent);
  display: flex; align-items: center; justify-content: center; font-size: 28px; }
.title { flex: 1; min-width: 0; }
.name { font-weight: 600; font-size: 1.05em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sub { color: var(--secondary-text-color); font-size: .85em; display: -webkit-box; -webkit-line-clamp: 2;
  -webkit-box-orient: vertical; overflow: hidden; }
.chip { display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; border-radius: 999px;
  font-size: .8em; font-weight: 600; color: #fff; white-space: nowrap; }
.tasks { display: flex; flex-direction: column; gap: 4px; }
.task { display: flex; align-items: center; gap: 8px; font-size: .92em; }
.task .label { flex: 1; min-width: 3.5em; }
.task .when { color: var(--secondary-text-color); font-size: .85em; white-space: nowrap; }
button, select, input, textarea { font: inherit; color: inherit; }
button { cursor: pointer; border: 1px solid color-mix(in srgb, var(--primary-text-color) 20%, transparent);
  background: color-mix(in srgb, var(--primary-color) 14%, transparent); border-radius: 10px;
  padding: 3px 10px; }
button:hover { background: color-mix(in srgb, var(--primary-color) 28%, transparent); }
button.ghost { background: transparent; }
button:disabled { cursor: default; opacity: .7; }
button.busy { animation: pulse 1s ease-in-out infinite; }
button.done { background: #22c55e; color: #fff; border-color: transparent; opacity: 1; }
@keyframes pulse { 50% { opacity: .45; } }
button:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
.warn { display: flex; flex-wrap: wrap; gap: 4px; }
.actions { display: flex; gap: 6px; justify-content: flex-end; }
.muted { color: var(--secondary-text-color); }
svg.chart { width: 100%; height: 130px; display: block; }
.legend { display: flex; gap: 12px; font-size: .8em; color: var(--secondary-text-color); }
.overlay { position: fixed; inset: 0; z-index: 9; background: rgba(0,0,0,.5); display: flex;
  align-items: center; justify-content: center; padding: 12px; }
.dialog { width: min(720px, 100%); max-height: 92vh; overflow: auto; border-radius: 18px; padding: 16px;
  background: var(--ha-card-background, var(--card-background-color)); color: var(--primary-text-color);
  backdrop-filter: blur(16px); display: flex; flex-direction: column; gap: 10px; }
.dialog h3 { margin: 4px 0; }
.kv { display: grid; grid-template-columns: 9em 1fr; gap: 2px 10px; font-size: .92em; }
.kv dt { color: var(--secondary-text-color); } .kv dd { margin: 0; }
form.edit { display: grid; grid-template-columns: 9em 1fr; gap: 6px 10px; align-items: start; }
form.edit input, form.edit textarea, .row input, .row select { width: 100%; box-sizing: border-box; padding: 4px 8px;
  border-radius: 8px; border: 1px solid color-mix(in srgb, var(--primary-text-color) 25%, transparent);
  background: transparent; }
.row { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.row > * { flex: 1; min-width: 7em; } .row > button { flex: none; }
.log { display: flex; flex-direction: column; gap: 2px; font-size: .88em; max-height: 180px; overflow: auto; }
.log div { display: flex; gap: 8px; align-items: center; } .log .u { text-decoration: line-through; opacity: .6; }
.log span.t { flex: 1; }
.tip { position: fixed; pointer-events: none; z-index: 10; padding: 3px 8px; border-radius: 8px; font-size: .8em;
  background: var(--primary-text-color); color: var(--card-background-color); }
`;

class RootineCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._filter = "needs";
    this._dialog = null;
    this._rendered = "";
  }

  setConfig(config) {
    if (!config.entity && config.mode !== "overview") throw new Error("entity or mode: overview");
    this._config = config;
  }

  getCardSize() { return this._config?.mode === "overview" ? 6 : 3; }

  /** Size in sections dashboards. */
  getGridOptions() {
    return this._config?.mode === "overview"
      ? { columns: "full", min_columns: 6 }
      : { columns: 6, min_columns: 4 };
  }

  static getConfigElement() { return document.createElement("rootine-card-editor"); }
  static getStubConfig(hass) {
    const first = Object.keys(hass.states).find((e) => hass.states[e].attributes?.profile && hass.states[e].attributes?.tasks);
    return first ? { entity: first } : { mode: "overview" };
  }

  set hass(hass) {
    this._hass = hass;
    this._t = T[(hass.language || "en").startsWith("de") ? "de" : "en"];
    if (this._dialog) return; // do not re-render while the dialog is open (keeps form input)
    const key = JSON.stringify(this._plants().map((p) => [p.id, p.state, p.attrs.tasks, p.attrs.warnings, p.attrs.location, p.attrs.entity_picture]))
      + this._filter;
    if (key !== this._rendered) { this._rendered = key; this._render(); }
  }

  _plants() {
    const states = this._hass?.states || {};
    const isPlant = (s) => s?.attributes?.profile && s?.attributes?.tasks && s?.attributes?.location;
    const ids = this._config?.mode === "overview"
      ? Object.keys(states).filter((id) => isPlant(states[id]))
      : [this._resolve(this._config?.entity)].filter((id) => isPlant(states[id]));
    return ids.map((id) => ({ id, state: states[id].state, attrs: states[id].attributes, name: states[id].attributes.friendly_name?.replace(/ (Pflegestatus|Care status)$/i, "") || id }))
      .sort((a, b) => RANK.indexOf(a.state) - RANK.indexOf(b.state));
  }

  /** Accept any entity of a plant and find its care status sensor through the device. */
  _resolve(id) {
    const states = this._hass?.states || {};
    if (!id || states[id]?.attributes?.profile) return id;
    return this._siblings(id).find((e) => states[e]?.attributes?.profile && states[e]?.attributes?.tasks) || id;
  }

  /** Entities of the same device (select for location, moisture sensor). */
  _siblings(id) {
    const reg = this._hass.entities || {};
    const device = reg[id]?.device_id;
    return Object.keys(reg).filter((e) => device && reg[e].device_id === device);
  }

  _render() {
    const t = this._t;
    if (!this._config) return;
    // never redraw over an open edit form: it would discard what the user is typing
    if (this._dialog?.edit && this.shadowRoot.querySelector("[data-form]")) {
      this._pendingRender = true;
      return;
    }
    this._pendingRender = false;
    const overview = this._config.mode === "overview";
    let plants = this._plants();
    if (overview && this._filter === "needs") plants = plants.filter((p) => !["ok", "rest", "unknown"].includes(p.state));
    const all = this._plants();
    const body = plants.length
      ? `<div class="grid">${plants.map((p) => this._plantHtml(p)).join("")}</div>`
      : `<div class="muted" style="padding:8px">${all.length ? t.none : t.noEntity}</div>`;
    const counts = RANK.slice(0, 6).map((k) => [k, all.filter((p) => p.state === k).length]).filter(([, n]) => n);
    const summary = overview && counts.length
      ? `<div class="summary">${counts.map(([k, n]) => `<span class="chip" style="background:${COLORS[k]}">${n} · ${esc(t.status[k])}</span>`).join("")}</div>` : "";
    const head = overview
      ? `<div class="head"><h2>${t.overview}</h2>${summary}<div class="actions">
           <button class="${this._filter === "needs" ? "" : "ghost"}" data-filter="needs">${t.needs}</button>
           <button class="${this._filter === "all" ? "" : "ghost"}" data-filter="all">${t.all}</button></div></div>`
      : "";
    this.shadowRoot.innerHTML = `<style>${STYLE}</style><ha-card>${head}${body}</ha-card>${this._dialog ? this._dialogHtml() : ""}`;
    this._bind();
    if (this._dialog) this._afterDialog();
  }

  _chip(status) {
    return `<span class="chip" style="background:${COLORS[status] || COLORS.unknown}">${esc(this._t.status[status] || status)}</span>`;
  }

  _plantHtml(p) {
    const t = this._t, a = p.attrs;
    const pic = a.entity_picture ? `<img class="pic" src="${esc(a.entity_picture)}" alt="">` : `<div class="pic">🌱</div>`;
    const sub = [a.profile.common_name, a.profile.cultivar && `'${a.profile.cultivar}'`].filter(Boolean).join(" ");
    const warns = (a.warnings || []).map((w) =>
      `<span class="chip" style="background:${COLORS[w.key === "sensor_check" ? "check_sensor" : w.key]}" title="${esc(t.reason[w.reason] || "")}">${esc(t.warn[w.key])}${w.reason ? ` · ${esc(t.reason[w.reason] || w.reason)}` : ""}</span>`).join("");
    const tasks = Object.entries(a.tasks).map(([key, task]) => {
      const verb = key === "water" ? t.water : key === "fertilize" ? t.fertilize : t.done;
      const when = task.days === null || task.days === undefined ? "" : t.days(task.days);
      return `<div class="task">${this._chip(task.status)}<span class="label">${esc(task.name)}</span>
        <span class="when">${esc(when)}</span><button data-done="${esc(key)}" data-plant="${esc(p.id)}">${esc(verb)}</button></div>`;
    }).join("");
    const m = a.moisture;
    const bar = m && m.value != null
      ? `<div><div class="bar"><div class="fill" style="width:${Math.max(0, Math.min(100, m.value))}%"></div>${m.threshold != null ? `<div class="mark" style="left:${m.threshold}%" title="${esc(t.threshold)} ${m.threshold} %"></div>` : ""}</div>
         <div class="barlabel"><span>${esc(t.eval)} ${Math.round(m.value)} %</span><span>${m.threshold != null ? `${esc(t.threshold)} ${m.threshold} %` : ""}</span></div></div>` : "";
    return `<div class="plant" style="--accent:${COLORS[p.state] || COLORS.unknown}"><div class="top">${pic}<div class="title"><div class="name">${esc(p.name)}</div>
      <div class="sub">${esc(sub || "")} · ${esc(t[a.location] || a.location)}</div></div>${this._chip(p.state)}</div>
      ${warns ? `<div class="warn">${warns}</div>` : ""}${bar}<div class="tasks">${tasks}</div>
      <div class="actions"><button class="ghost" data-details="${esc(p.id)}">${t.details}</button></div></div>`;
  }

  _bind() {
    const root = this.shadowRoot;
    root.querySelectorAll("[data-filter]").forEach((b) => b.addEventListener("click", () => {
      this._filter = b.dataset.filter; this._rendered = ""; this._render();
    }));
    root.querySelectorAll("[data-done]").forEach((b) => b.addEventListener("click", async () => {
      b.disabled = true;
      b.classList.add("busy");
      const ok = await this._call("rootine", "mark_done", { entity_id: b.dataset.plant, task: b.dataset.done });
      b.classList.remove("busy");
      if (ok) { b.textContent = "✓"; b.classList.add("done"); } else { b.disabled = false; }
    }));
    root.querySelectorAll("[data-details]").forEach((b) => b.addEventListener("click", () => this._open(b.dataset.details)));
  }

  /** Call an action; show HA's toast on failure instead of failing silently. */
  async _call(domain, service, data) {
    try {
      await this._hass.callService(domain, service, data);
      return true;
    } catch (err) {
      this._toast(err?.message || String(err));
      return false;
    }
  }

  _toast(message) {
    this.dispatchEvent(new CustomEvent("hass-notification", { detail: { message }, bubbles: true, composed: true }));
  }

  // ---- detail dialog ----

  async _open(id) {
    this._dialog = { id, edit: false, history: [], chart: null };
    this._onKey = (e) => { if (e.key === "Escape") this._close(); };
    window.addEventListener("keydown", this._onKey);
    this._render();
    await this._loadHistory();
    this._loadChart();
  }

  _close() {
    window.removeEventListener("keydown", this._onKey);
    this._dialog = null; this._rendered = ""; this._render();
  }

  async _loadHistory() {
    try {
      const res = await this._hass.callWS({ type: "call_service", domain: "rootine", service: "get_history",
        service_data: { entity_id: this._dialog.id, limit: 30 }, return_response: true });
      if (this._dialog) { this._dialog.history = res.response.items; this._render(); }
    } catch (e) { /* history is optional */ }
  }

  async _loadChart() {
    const d = this._dialog;
    if (!d) return;
    const evalId = this._siblings(d.id).find((e) => this._hass.states[e]?.attributes?.source_entity);
    if (!evalId) return;
    const attrs = this._hass.states[evalId].attributes;
    const ids = [attrs.source_entity, evalId].filter((e) => this._hass.states[e]);
    const end = new Date(), start = new Date(end - 48 * 3600e3);
    try {
      const res = await this._hass.callWS({ type: "history/history_during_period", start_time: start.toISOString(),
        end_time: end.toISOString(), entity_ids: ids, include_start_time_state: true, significant_changes_only: false,
        minimal_response: true, no_attributes: true });
      d.chart = { start, end, raw: res[attrs.source_entity] || [], eval: res[evalId] || [], threshold: attrs.threshold };
      this._render();
    } catch (e) { /* chart is optional */ }
  }

  _series(points) {
    return (points || []).map((p) => [new Date(p.lu ? p.lu * 1000 : p.last_changed || p.last_updated), parseFloat(p.s ?? p.state)])
      .filter(([, v]) => Number.isFinite(v));
  }

  _chartSvg(chart) {
    const t = this._t, W = 600, H = 120, L = 30, R = 6, TOP = 8, B = 18;
    const raw = this._series(chart.raw), ev = this._series(chart.eval);
    const values = [...raw, ...ev].map(([, v]) => v);
    if (chart.threshold != null) values.push(chart.threshold);
    const lo = Math.max(0, Math.floor((Math.min(...values) - 5) / 10) * 10);
    const hi = Math.min(100, Math.ceil((Math.max(...values) + 5) / 10) * 10);
    const span = Math.max(20, hi - lo);
    const x = (d) => L + ((d - chart.start) / (chart.end - chart.start)) * (W - L - R);
    const y = (v) => TOP + (1 - (v - lo) / span) * (H - TOP - B);
    const line = (pts, color, dash) => {
      if (!pts.length) return "";
      let dpath = `M${x(pts[0][0]).toFixed(1)},${y(pts[0][1]).toFixed(1)}`;
      for (const [dt, v] of pts.slice(1)) dpath += ` H${x(dt).toFixed(1)} V${y(v).toFixed(1)}`;
      dpath += ` H${x(chart.end).toFixed(1)}`;
      return `<path d="${dpath}" fill="none" stroke="${color}" stroke-width="1.8" ${dash ? 'stroke-dasharray="4 3"' : ""}/>`;
    };
    const step = span <= 30 ? 10 : span <= 60 ? 20 : 25;
    const marks = [];
    for (let v = Math.ceil(lo / step) * step; v <= lo + span; v += step) marks.push(v);
    const grid = marks.map((v) => `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="currentColor" opacity=".12"/>
      <text x="${L - 4}" y="${y(v) + 3}" text-anchor="end" font-size="9" fill="currentColor" opacity=".7">${v}</text>`).join("");
    const lang = this._hass.language || undefined;
    const ticks = [0, 12, 24, 36, 48].map((h) => {
      const dt = new Date(chart.start.getTime() + h * 3600e3);
      return `<text x="${x(dt)}" y="${H - 4}" text-anchor="${h === 0 ? "start" : h === 48 ? "end" : "middle"}" font-size="9" fill="currentColor" opacity=".7">${dt.toLocaleTimeString(lang, { hour: "2-digit", minute: "2-digit" })}</text>`;
    }).join("");
    const thr = chart.threshold != null ? `<line x1="${L}" x2="${W - R}" y1="${y(chart.threshold)}" y2="${y(chart.threshold)}" stroke="#ef4444" stroke-dasharray="3 3"/>` : "";
    return `<div class="muted">${t.chart}</div><svg class="chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" data-chart>${grid}${ticks}${thr}
      ${line(raw, "var(--secondary-text-color)", true)}${line(ev, "var(--primary-color)", false)}</svg>
      <div class="legend"><span>┄ ${t.raw}</span><span>━ ${t.eval}</span>${chart.threshold != null ? `<span style="color:#ef4444">┄ ${t.threshold} ${chart.threshold} %</span>` : ""}</div>`;
  }

  _dialogHtml() {
    const d = this._dialog, t = this._t, st = this._hass.states[d.id];
    if (!st) return "";
    const a = st.attributes, p = a.profile;
    const name = a.friendly_name?.replace(/ (Pflegestatus|Care status)$/i, "") || d.id;
    const pic = a.entity_picture ? `<img class="pic" style="width:72px;height:72px" src="${esc(a.entity_picture)}" alt="">` : `<div class="pic" style="width:72px;height:72px">🌱</div>`;
    const taskOptions = Object.entries(a.tasks).map(([k, v]) => `<option value="${esc(k)}">${esc(v.name)}</option>`).join("");
    const kv = (label, value, isMd) => value ? `<dt>${esc(label)}</dt><dd>${isMd ? markdown(value) : esc(value)}</dd>` : "";
    const view = `<dl class="kv">${PROFILE_FIELDS.map((f) => kv(t.fields[f], f.startsWith("care.") ? p[f] : p[f] ?? "", f.startsWith("care.") || f === "notes")).join("")}</dl>`;
    const form = `<form class="edit" data-form>${PROFILE_FIELDS.map((f) => {
      const multi = f.startsWith("care.") || f === "notes";
      return `<label>${esc(t.fields[f])}</label>${multi ? `<textarea name="${f}" rows="3">${esc(p[f] ?? "")}</textarea>` : `<input name="${f}" value="${esc(p[f] ?? "")}">`}`;
    }).join("")}<span></span><div class="actions"><button type="button" class="ghost" data-cancel>${t.cancel}</button><button type="submit">${t.save}</button></div></form>`;
    const log = d.history.map((e) => `<div class="${e.undone ? "u" : ""}"><span class="t">${esc(new Date(e.ts).toLocaleString(this._hass.language))} · ${esc(a.tasks[e.task]?.name || e.task)} · ${esc(t.sources[e.source] || e.source)}${e.note ? ` · ${esc(e.note)}` : ""}</span>${e.undone ? `<span class="muted">${t.undone}</span>` : `<button class="ghost" data-undo="${esc(e.id)}">${t.undo}</button>`}</div>`).join("");
    const locSelect = this._siblings(d.id).find((e) => e.startsWith("select.") && this._hass.states[e]);
    return `<div class="overlay" data-overlay><div class="dialog">
      <div class="top">${pic}<div class="title"><div class="name" style="font-size:1.2em">${esc(name)}</div><div class="sub">${esc([p.common_name, p.species].filter(Boolean).join(" · "))}</div></div>${this._chip(st.state)}
        <button class="ghost" data-close>${t.close}</button></div>
      <div class="row"><button data-photo>${t.photo}</button><input type="file" accept="image/*" data-file hidden>
        ${locSelect ? `<select data-location>${["outdoor", "indoor"].map((o) => `<option value="${o}" ${this._hass.states[locSelect].state === o ? "selected" : ""}>${t[o]}</option>`).join("")}</select>` : ""}
        <button class="ghost" data-edit>${t.edit}</button></div>
      ${d.edit ? form : view}
      ${d.chart ? this._chartSvg(d.chart) : ""}
      <h3>${t.postpone} / ${t.backfill}</h3>
      <div class="row"><select data-task>${taskOptions}</select><input type="date" data-date value="${new Date().toISOString().slice(0, 10)}">
        <button data-backfill>${t.backfill}</button><input type="number" min="1" max="60" value="1" data-days style="max-width:5em"><button data-postpone>${t.postpone}</button></div>
      <h3>${t.history}</h3><div class="log">${log}</div></div></div>`;
  }

  _afterDialog() {
    const root = this.shadowRoot, d = this._dialog, t = this._t;
    const q = (s) => root.querySelector(s);
    q("[data-close]")?.addEventListener("click", () => this._close());
    q("[data-overlay]")?.addEventListener("click", (e) => { if (e.target.dataset.overlay !== undefined) this._close(); });
    q("[data-edit]")?.addEventListener("click", () => { d.edit = !d.edit; this._render(); });
    q("[data-cancel]")?.addEventListener("click", () => { d.edit = false; this._render(); });
    q("[data-edit]")?.setAttribute("aria-pressed", d.edit ? "true" : "false");
    q("[data-form]")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const current = this._hass.states[d.id].attributes.profile;
      const data = { entity_id: d.id };
      for (const f of PROFILE_FIELDS) {
        const v = e.target.elements[f].value.trim();
        if (v !== (current[f] ?? "")) data[f.replace(".", "_")] = v;
      }
      if (Object.keys(data).length > 1) await this._call("rootine", "update_profile", data);
      d.edit = false; this._render();
    });
    q("[data-photo]")?.addEventListener("click", () => q("[data-file]").click());
    q("[data-file]")?.addEventListener("change", async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      const body = new FormData();
      body.append("file", file);
      try {
        const res = await this._hass.fetchWithAuth("/api/image/upload", { method: "POST", body });
        if (!res.ok) throw new Error(String(res.status));
        const json = await res.json();
        await this._call("rootine", "set_photo", { entity_id: d.id,
          photo: { media_content_id: `media-source://image_upload/${json.id}`, media_content_type: file.type || "image/jpeg" } });
      } catch (err) {
        this._toast(t.uploadFailed);
      }
    });
    q("[data-location]")?.addEventListener("change", (e) => {
      const sel = this._siblings(d.id).find((x) => x.startsWith("select."));
      this._call("select", "select_option", { entity_id: sel, option: e.target.value });
    });
    q("[data-backfill]")?.addEventListener("click", async () => {
      const date = q("[data-date]").value;
      await this._call("rootine", "mark_done", { entity_id: d.id, task: q("[data-task]").value,
        when: `${date}T12:00:00`, note: t.backfill });
      await this._loadHistory();
    });
    q("[data-postpone]")?.addEventListener("click", () =>
      this._call("rootine", "postpone", { entity_id: d.id, task: q("[data-task]").value, days: Number(q("[data-days]").value) || 1 }));
    root.querySelectorAll("[data-undo]").forEach((b) => b.addEventListener("click", async () => {
      await this._call("rootine", "undo_event", { entity_id: d.id, event_id: b.dataset.undo });
      await this._loadHistory();
    }));
    const svg = q("[data-chart]");
    if (svg && d.chart) this._tooltip(svg, d.chart);
  }

  _tooltip(svg, chart) {
    const raw = this._series(chart.raw), ev = this._series(chart.eval);
    const at = (pts, time) => { let v = null; for (const [dt, val] of pts) { if (dt <= time) v = val; else break; } return v; };
    let tip;
    svg.addEventListener("mousemove", (e) => {
      const rect = svg.getBoundingClientRect();
      const frac = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
      const time = new Date(chart.start.getTime() + frac * (chart.end - chart.start));
      const r = at(raw, time), v = at(ev, time);
      tip = tip || Object.assign(document.createElement("div"), { className: "tip" });
      tip.textContent = `${time.toLocaleString(this._hass.language, { weekday: "short", hour: "2-digit", minute: "2-digit" })} · ${this._t.raw} ${r ?? "–"} % · ${this._t.eval} ${v == null ? "–" : Math.round(v)} %`;
      tip.style.left = `${e.clientX + 10}px`; tip.style.top = `${e.clientY - 28}px`;
      this.shadowRoot.appendChild(tip);
    });
    svg.addEventListener("mouseleave", () => tip?.remove());
  }
}

class RootineCardEditor extends HTMLElement {
  setConfig(config) { this._config = config; this._draw(); }
  set hass(hass) { this._hass = hass; this._draw(); }
  _draw() {
    if (!this._hass || !this._config) return;
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.computeLabel = (s) => ({ entity: "Pflanze / Plant", mode: "Modus / Mode" }[s.name] || s.name);
      this._form.addEventListener("value-changed", (e) =>
        this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: e.detail.value }, bubbles: true, composed: true })));
      this.appendChild(this._form);
    }
    this._form.hass = this._hass;
    this._form.data = this._config;
    this._form.schema = [
      { name: "entity", selector: { entity: { integration: "rootine", domain: "sensor" } } },
      { name: "mode", selector: { select: { options: [{ value: "overview", label: "Overview" }], mode: "dropdown", custom_value: false } } },
    ];
  }
}

customElements.define("rootine-card", RootineCard);
customElements.define("rootine-card-editor", RootineCardEditor);
window.customCards = window.customCards || [];
window.customCards.push({ type: "rootine-card", name: "Rootine", description: "Plant care overview", preview: false });
console.info(`%c ROOTINE-CARD %c ${VERSION} `, "color:#fff;background:#22c55e", "");
