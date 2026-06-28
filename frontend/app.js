"use strict";

// --- tiny helpers ------------------------------------------------------------

const view = document.getElementById("view");
const modalRoot = document.getElementById("modalRoot");
const backBtn = document.getElementById("backBtn");

async function api(path, opts) {
  const res = await fetch("/api" + path, {
    headers: { "content-type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch (e) {}
    throw new Error(msg);
  }
  return res.status === 204 ? null : res.json();
}

const el = (tag, cls, html) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html != null) n.innerHTML = html;
  return n;
};
const esc = (s) =>
  String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const STATUS_LABEL = { ok: "OK", due_soon: "Due soon", overdue: "Overdue", unknown: "No data" };
const CAT_LABEL = {
  inspection: "Inspections", emergency_equipment: "Emergency equipment",
  engine: "Engine", propeller: "Propeller", airframe: "Airframe",
  avionics: "Avionics", registration: "Registration", ad: "Airworthiness Directives",
  other: "Other",
};

function fmtDate(s) {
  if (!s) return "—";
  const d = new Date(s + "T00:00:00");
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}
function daysText(n) {
  if (n == null) return "";
  if (n < 0) return `${-n} day${n === -1 ? "" : "s"} overdue`;
  if (n === 0) return "due today";
  return `in ${n} day${n === 1 ? "" : "s"}`;
}
function statusChip(s) {
  return `<span class="chip ${s}">${STATUS_LABEL[s] || s}</span>`;
}

// --- routing -----------------------------------------------------------------

function go(hash) { location.hash = hash; }
document.getElementById("homeLink").onclick = () => go("#/");
backBtn.onclick = () => go("#/");

window.addEventListener("hashchange", route);
window.addEventListener("load", route);

function route() {
  const h = location.hash || "#/";
  const m = h.match(/^#\/aircraft\/(\d+)/);
  if (m) { backBtn.classList.remove("hidden"); renderAircraft(+m[1]); }
  else { backBtn.classList.add("hidden"); renderDashboard(); }
}

// --- dashboard ---------------------------------------------------------------

async function renderDashboard() {
  view.innerHTML = '<div class="loading">Loading fleet…</div>';
  let data, fleet;
  try {
    [data, fleet] = await Promise.all([api("/dashboard"), api("/aircraft")]);
  } catch (e) { return showError(e); }

  view.innerHTML = "";
  view.appendChild(el("h1", "page", "Fleet status"));
  view.appendChild(el("p", "sub",
    `${data.fleet_size} aircraft · ${data.totals.ok + data.totals.due_soon + data.totals.overdue} tracked items`));

  const t = data.totals;
  const stats = el("div", "stats");
  stats.appendChild(stat("red", t.overdue, "Overdue"));
  stats.appendChild(stat("amber", t.due_soon, "Due soon"));
  stats.appendChild(stat("green", t.ok, "Current"));
  stats.appendChild(stat("navy", t.airworthiness_overdue, "Airworthiness overdue"));
  view.appendChild(stats);

  const btns = el("div", "btn-row");
  const add = el("button", "btn", "+ Add aircraft");
  add.onclick = addAircraftModal;
  btns.appendChild(add);
  view.appendChild(btns);

  // Aircraft cards
  view.appendChild(el("div", "section-title", "Aircraft"));
  const grid = el("div", "grid");
  fleet.forEach((ac) => grid.appendChild(aircraftCard(ac)));
  if (!fleet.length) grid.appendChild(el("div", "empty", "No aircraft yet. Add one to get started."));
  view.appendChild(grid);

  // Alerts
  view.appendChild(el("div", "section-title", `Attention needed (${data.alerts.length})`));
  if (!data.alerts.length) {
    view.appendChild(el("div", "empty", "Nothing due soon or overdue. 🎉"));
  } else {
    data.alerts.forEach((a) => view.appendChild(alertRow(a)));
  }
}

function stat(cls, n, label) {
  const s = el("div", "stat " + cls);
  s.appendChild(el("div", "n", String(n)));
  s.appendChild(el("div", "l", label));
  return s;
}

function aircraftCard(ac) {
  const c = el("div", "card");
  c.onclick = () => go(`#/aircraft/${ac.id}`);
  const row = el("div", "row");
  const left = el("div");
  left.appendChild(el("div", "tail", esc(ac.tail_number)));
  left.appendChild(el("div", "mm", esc([ac.make, ac.model].filter(Boolean).join(" ")) || "—"));
  row.appendChild(left);
  row.appendChild(el("span", "light " + ac.light));
  c.appendChild(row);

  const meta = el("div", "meta");
  meta.innerHTML =
    `<span><b>${ac.overdue_count}</b> overdue</span>` +
    `<span><b>${ac.due_soon_count}</b> due soon</span>` +
    (ac.home_base ? `<span>${esc(ac.home_base)}</span>` : "");
  c.appendChild(meta);

  if (ac.next_due) {
    c.appendChild(el("div", "next", `Next: ${esc(ac.next_due.name)} — ${fmtDate(ac.next_due.date)}`));
  }
  return c;
}

function alertRow(a) {
  const r = el("div", "alert " + a.status);
  const main = el("div", "a-main");
  const aw = a.is_required_for_airworthiness ? ' <span class="chip aw">AIRWORTHINESS</span>' : "";
  main.appendChild(el("div", "a-name", esc(a.name) + aw));
  main.appendChild(el("div", "a-sub",
    `<span class="a-tail">${esc(a.tail_number)}</span> · ${esc((a.reasons || []).join(" · ") || "")}`));
  r.appendChild(el("span", "light " + (a.status === "overdue" ? "red" : "amber")));
  r.appendChild(main);
  r.appendChild(el("div", "", statusChip(a.status)));
  r.onclick = () => go(`#/aircraft/${a.aircraft_id}`);
  return r;
}

// --- aircraft detail ---------------------------------------------------------

let CURRENT_AIRCRAFT = null;

async function renderAircraft(id) {
  view.innerHTML = '<div class="loading">Loading aircraft…</div>';
  let ac;
  try { ac = await api(`/aircraft/${id}`); } catch (e) { return showError(e); }
  CURRENT_AIRCRAFT = ac;

  view.innerHTML = "";
  view.appendChild(el("h1", "page", esc(ac.tail_number)));
  view.appendChild(el("p", "sub",
    esc([ac.make, ac.model, ac.year].filter(Boolean).join(" ")) +
    (ac.home_base ? ` · ${esc(ac.home_base)}` : "")));

  // Components with update-hours
  view.appendChild(el("div", "section-title", "Components"));
  const strip = el("div", "comp-strip");
  ac.components.forEach((c) => {
    const box = el("div", "comp");
    box.appendChild(el("div", "c-pos", esc(c.position || c.type)));
    box.appendChild(el("div", "c-h", `${c.current_hours.toLocaleString()} h · ${c.current_cycles.toLocaleString()} cyc`));
    const b = el("button", "btn small", "Update hours");
    b.onclick = () => updateHoursModal(c);
    box.appendChild(b);
    strip.appendChild(box);
  });
  view.appendChild(strip);

  // Items grouped by category
  view.appendChild(el("div", "section-title", `Tracked items (${ac.items.length})`));
  const groups = {};
  ac.items.forEach((it) => (groups[it.category] = groups[it.category] || []).push(it));
  const order = Object.keys(CAT_LABEL).filter((k) => groups[k]);
  Object.keys(groups).forEach((k) => { if (!order.includes(k)) order.push(k); });

  order.forEach((cat) => {
    const g = el("div", "cat-group");
    g.appendChild(el("div", "cat-head", CAT_LABEL[cat] || cat));
    groups[cat]
      .sort((a, b) => severity(b.compliance.status) - severity(a.compliance.status))
      .forEach((it) => g.appendChild(itemRow(it)));
    view.appendChild(g);
  });
  if (!ac.items.length) view.appendChild(el("div", "empty", "No tracked items on this aircraft yet."));
}

const severity = (s) => ({ overdue: 3, due_soon: 2, ok: 1, unknown: 0 }[s] || 0);

function intervalText(it) {
  const parts = [];
  if (it.interval_months) parts.push(`${it.interval_months} mo`);
  if (it.interval_hours) parts.push(`${it.interval_hours} h`);
  if (it.interval_cycles) parts.push(`${it.interval_cycles} cyc`);
  if (it.interval_kind === "fixed") return "fixed expiry";
  const join = it.interval_kind === "combo_first" ? " or " :
               it.interval_kind === "combo_last" ? " & " : " / ";
  return parts.join(join) || "—";
}

function itemRow(it) {
  const c = it.compliance;
  const row = el("div", "item");
  row.appendChild(el("span", "light " + lightFor(c.status)));

  const main = el("div", "i-main");
  const aw = it.is_required_for_airworthiness ? ' <span class="chip aw">AIRWORTHINESS</span>' : "";
  const reg = it.reg_reference ? ` <span class="reg">${esc(it.reg_reference)}</span>` : "";
  main.appendChild(el("div", "i-name", `${esc(it.name)}${reg}${aw}`));

  let sub = `Every ${intervalText(it)}`;
  if (it.component_position) sub += ` · ${esc(it.component_position)}`;
  if (c.effective_due_date) sub += ` · due ${fmtDate(c.effective_due_date)} (${daysText(c.remaining_days)})`;
  else sub += " · not yet performed";
  if (c.remaining_hours != null) sub += ` · ${(+c.remaining_hours).toLocaleString()} h left`;
  main.appendChild(el("div", "i-sub", sub));
  row.appendChild(main);

  row.appendChild(el("div", "", statusChip(c.status)));

  const actions = el("div", "i-actions");
  const log = el("button", "btn small primary", "Log");
  log.onclick = () => logCompletionModal(it);
  actions.appendChild(log);
  row.appendChild(actions);
  return row;
}

const lightFor = (s) => (s === "overdue" ? "red" : s === "due_soon" ? "amber" : s === "ok" ? "green" : "grey");

// --- modals ------------------------------------------------------------------

function openModal(title, sub, bodyNode) {
  const overlay = el("div", "overlay");
  const modal = el("div", "modal");
  modal.appendChild(el("h3", null, esc(title)));
  if (sub) modal.appendChild(el("div", "m-sub", esc(sub)));
  modal.appendChild(bodyNode);
  overlay.appendChild(modal);
  overlay.onclick = (e) => { if (e.target === overlay) close(); };
  modalRoot.appendChild(overlay);
  function close() { overlay.remove(); }
  return { close };
}

function field(label, inputHtml) {
  const f = el("div", "field");
  f.appendChild(el("label", null, label));
  f.insertAdjacentHTML("beforeend", inputHtml);
  return f;
}

function todayStr() { return new Date().toISOString().slice(0, 10); }

function logCompletionModal(it) {
  const comp = (CURRENT_AIRCRAFT.components || []).find((c) => c.id === it.component_id);
  const body = el("div");
  const form = el("form");
  form.appendChild(field("Date performed", `<input name="performed_date" type="date" value="${todayStr()}" required>`));
  if (it.component_id) {
    const h = comp ? comp.current_hours : "";
    form.appendChild(field(`Hours at completion${comp ? " (" + comp.position + ")" : ""}`,
      `<input name="performed_at_hours" type="number" step="0.1" value="${h}">`));
  }
  form.appendChild(field("Performed by", `<input name="performed_by" placeholder="Name / shop">`));
  form.appendChild(field("Sign-off (A&P/IA + cert #)", `<input name="signed_off_by" placeholder="e.g. IA 1234567">`));
  form.insertAdjacentHTML("beforeend",
    `<div class="two">` +
    `<div class="field"><label>Vendor</label><input name="vendor"></div>` +
    `<div class="field"><label>Cost ($)</label><input name="cost" type="number" step="0.01"></div></div>`);
  form.appendChild(field("Notes", `<textarea name="notes" rows="2"></textarea>`));

  const actions = el("div", "actions");
  const cancel = el("button", "btn", "Cancel"); cancel.type = "button";
  const save = el("button", "btn primary", "Log completion"); save.type = "submit";
  actions.appendChild(cancel); actions.appendChild(save);
  form.appendChild(actions);
  body.appendChild(form);

  const m = openModal(`Log: ${it.name}`, "Advances the next due date.", body);
  cancel.onclick = m.close;
  form.onsubmit = async (e) => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(form).entries());
    const payload = {
      performed_date: fd.performed_date,
      performed_at_hours: fd.performed_at_hours ? +fd.performed_at_hours : null,
      performed_by: fd.performed_by || null,
      signed_off_by: fd.signed_off_by || null,
      vendor: fd.vendor || null,
      cost: fd.cost ? +fd.cost : null,
      notes: fd.notes || null,
    };
    save.disabled = true;
    try {
      await api(`/items/${it.id}/events`, { method: "POST", body: JSON.stringify(payload) });
      m.close();
      renderAircraft(CURRENT_AIRCRAFT.id);
    } catch (err) { alert("Error: " + err.message); save.disabled = false; }
  };
}

function updateHoursModal(comp) {
  const body = el("div");
  const form = el("form");
  form.appendChild(field("Current hours", `<input name="hours" type="number" step="0.1" value="${comp.current_hours}" required>`));
  form.appendChild(field("Current cycles", `<input name="cycles" type="number" value="${comp.current_cycles}">`));
  form.appendChild(field("Reading date", `<input name="reading_date" type="date" value="${todayStr()}">`));
  const actions = el("div", "actions");
  const cancel = el("button", "btn", "Cancel"); cancel.type = "button";
  const save = el("button", "btn primary", "Save"); save.type = "submit";
  actions.appendChild(cancel); actions.appendChild(save);
  form.appendChild(actions);
  body.appendChild(form);

  const m = openModal(`Update hours: ${comp.position || comp.type}`,
    "Updates projections for this component's hours-based items.", body);
  cancel.onclick = m.close;
  form.onsubmit = async (e) => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(form).entries());
    save.disabled = true;
    try {
      await api(`/components/${comp.id}/hours`, {
        method: "POST",
        body: JSON.stringify({
          hours: +fd.hours,
          cycles: fd.cycles ? +fd.cycles : null,
          reading_date: fd.reading_date || null,
        }),
      });
      m.close();
      renderAircraft(CURRENT_AIRCRAFT.id);
    } catch (err) { alert("Error: " + err.message); save.disabled = false; }
  };
}

function addAircraftModal() {
  const body = el("div");
  const form = el("form");
  form.appendChild(field("Tail number", `<input name="tail_number" placeholder="N123AB" required>`));
  form.insertAdjacentHTML("beforeend",
    `<div class="two">` +
    `<div class="field"><label>Make</label><input name="make"></div>` +
    `<div class="field"><label>Model</label><input name="model"></div></div>` +
    `<div class="two">` +
    `<div class="field"><label>Year</label><input name="year" type="number"></div>` +
    `<div class="field"><label>Home base</label><input name="home_base"></div></div>`);
  const actions = el("div", "actions");
  const cancel = el("button", "btn", "Cancel"); cancel.type = "button";
  const save = el("button", "btn primary", "Add"); save.type = "submit";
  actions.appendChild(cancel); actions.appendChild(save);
  form.appendChild(actions);
  body.appendChild(form);

  const m = openModal("Add aircraft", "You can seed standard items from the catalog after.", body);
  cancel.onclick = m.close;
  form.onsubmit = async (e) => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(form).entries());
    save.disabled = true;
    try {
      const ac = await api("/aircraft", {
        method: "POST",
        body: JSON.stringify({
          tail_number: fd.tail_number,
          make: fd.make || null, model: fd.model || null,
          year: fd.year ? +fd.year : null, home_base: fd.home_base || null,
        }),
      });
      m.close();
      go(`#/aircraft/${ac.id}`);
    } catch (err) { alert("Error: " + err.message); save.disabled = false; }
  };
}

function showError(e) {
  view.innerHTML = `<div class="empty">Couldn't load data.<br><small>${esc(e.message)}</small></div>`;
}

// PWA service worker (best-effort; ignored if unsupported)
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
