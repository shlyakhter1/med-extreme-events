/* Playback: scrub a scenario window; counties and facilities recolor by the events and
   action items active at t. Data: /scenarios, /facilities, /reference/counties (once),
   /events?scenario= and /action-items?scenario= (per scenario, filtered client-side). */
(() => {
  const COLORS = { heat: "#e4572e", hurricane_flood: "#3d7fdc", wildfire_smoke: "#8c6d3f", air_pollution: "#a05cd6", power_outage: "#d9a41a" };
  const SEV = { Extreme: 4, Severe: 3, Moderate: 2, Minor: 1, Unknown: 0 };
  const TYPE_PRIORITY = ["hurricane_flood", "heat", "power_outage", "air_pollution", "wildfire_smoke"];
  const $ = (id) => document.getElementById(id);
  const state = { scenarios: [], facilities: null, counties: null, events: [], items: [], t0: 0, t1: 0, t: 0, timer: null, selected: null, role: "care_team" };

  const map = L.map("map", { zoomControl: true }).setView([38.5, -96], 4);
  L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png", { attribution: "© OpenStreetMap © CARTO", maxZoom: 12 }).addTo(map);
  let countyLayer = null, facilityLayer = null;

  const fmt = (ms) => new Date(ms).toISOString().replace("T", " ").slice(0, 16) + "Z";
  const parse = (s) => Date.parse(s);
  const activeEvents = (t) => state.events.filter((e) => parse(e.onset) <= t && t <= parse(e.expires));
  const activeItems = (t) => state.items.filter((i) => i.status !== "superseded" && parse(i.window_start) <= t && t <= parse(i.window_end));

  async function getJSON(url) { const r = await fetch(url); if (!r.ok) throw new Error(url + " → " + r.status); return r.json(); }

  async function init() {
    $("status").textContent = "loading reference data…";
    const [scenarios, facilities, counties] = await Promise.all([getJSON("/scenarios"), getJSON("/facilities"), getJSON("/reference/counties")]);
    state.scenarios = scenarios; state.facilities = facilities; state.counties = counties;
    countyLayer = L.geoJSON(counties, { style: () => ({ weight: 0.3, color: "#2a3440", fillColor: "#131a22", fillOpacity: 0.6 }), interactive: false }).addTo(map);
    facilityLayer = L.geoJSON(facilities, {
      pointToLayer: (f, ll) => L.circleMarker(ll, { radius: 3, weight: 1, color: "#5b6673", fillColor: "#5b6673", fillOpacity: 0.9 }),
      onEachFeature: (f, layer) => layer.on("click", () => selectFacility(f.properties.id)),
    }).addTo(map);
    const sel = $("scenario");
    for (const s of scenarios) { const o = document.createElement("option"); o.value = s.id; o.textContent = `${s.id} (${s.events} events)`; sel.appendChild(o); }
    sel.addEventListener("change", () => loadScenario(sel.value));
    $("slider").addEventListener("input", (e) => { setT(state.t0 + Number(e.target.value) * 3600e3); });
    $("play").addEventListener("click", togglePlay);
    if (scenarios.length) await loadScenario(scenarios[0].id);
  }

  async function loadScenario(id) {
    stop();
    $("status").textContent = `loading ${id}…`;
    const [ev, it] = await Promise.all([getJSON(`/events?scenario=${id}`), getJSON(`/action-items?scenario=${id}&include_superseded=true`)]);
    state.events = ev.events; state.items = it.items; state.selected = null;
    const s = state.scenarios.find((x) => x.id === id);
    state.t0 = parse(s.window_start); state.t1 = parse(s.window_end);
    // clamp very long tails (e.g. FEMA incident periods) to 10 days past the last alert onset
    const lastOnset = Math.max(...state.events.map((e) => parse(e.onset)));
    state.t1 = Math.min(state.t1, lastOnset + 10 * 86400e3);
    const hours = Math.ceil((state.t1 - state.t0) / 3600e3);
    $("slider").max = hours; $("slider").value = 0; $("tend").textContent = fmt(state.t1);
    const view = { heat_dome_2021: [[45.8, -121.5], 6], ian_2022: [[27.8, -82.0], 6], smoke_nyc_2023: [[40.8, -75.5], 6] }[id];
    if (view) map.setView(view[0], view[1]);
    $("status").textContent = `${state.events.length} events · ${state.items.length} action items (${state.items.filter((i) => i.status === "superseded").length} superseded)`;
    setT(state.t0);
  }

  function setT(t) {
    state.t = Math.max(state.t0, Math.min(state.t1, t));
    $("t").textContent = fmt(state.t);
    $("slider").value = Math.round((state.t - state.t0) / 3600e3);
    render();
  }

  function render() {
    const evs = activeEvents(state.t), items = activeItems(state.t);
    const county = new Map(); // fips → {type, sev}
    for (const e of evs) for (const c of e.geography.county_fips) {
      const cur = county.get(c), sev = SEV[e.severity] || 0;
      if (!cur || sev > cur.sev || (sev === cur.sev && TYPE_PRIORITY.indexOf(e.event_type) < TYPE_PRIORITY.indexOf(cur.type))) county.set(c, { type: e.event_type, sev });
    }
    countyLayer.eachLayer((l) => {
      const hit = county.get(l.feature.id);
      l.setStyle(hit ? { fillColor: COLORS[hit.type], fillOpacity: 0.25 + 0.15 * hit.sev, color: COLORS[hit.type], weight: 0.5 } : { fillColor: "#131a22", fillOpacity: 0.6, color: "#2a3440", weight: 0.3 });
    });
    const byFacility = new Map();
    for (const i of items) { const a = byFacility.get(i.facility_id) || []; a.push(i); byFacility.set(i.facility_id, a); }
    facilityLayer.eachLayer((l) => {
      const its = byFacility.get(l.feature.properties.id);
      if (!its) { l.setStyle({ radius: 3, color: "#5b6673", fillColor: "#5b6673" }); return; }
      const top = its.reduce((b, i) => (i.acuity_rank < b.acuity_rank ? i : b), its[0]);
      const panel = Math.max(...its.map((i) => i.panel || 0));
      l.setStyle({ radius: 5 + Math.min(10, Math.sqrt(panel) / 8), color: "#fff", fillColor: COLORS[top.event_type], fillOpacity: 0.95, weight: 1 });
      l.bringToFront();
    });
    renderSide(evs, items, byFacility);
  }

  function renderSide(evs, items, byFacility) {
    const board = [...byFacility.entries()].map(([fid, its]) => {
      const f = state.facilities.features.find((x) => x.properties.id === fid);
      const top = its.reduce((b, i) => (i.acuity_rank < b.acuity_rank ? i : b), its[0]);
      const panel = Math.max(...its.map((i) => i.panel || 0));
      const sev = Math.max(...its.map((i) => SEV[i.event_severity] || 0));
      return { fid, name: f ? f.properties.name : fid, state: f ? f.properties.state : "", cards: new Set(its.map((i) => i.card_id)).size, top, panel, sev, score: sev * panel };
    }).sort((a, b) => a.top.acuity_rank - b.top.acuity_rank || b.score - a.score);
    const names = {};
    for (const e of evs) names[e.event_name] = (names[e.event_name] || 0) + 1;
    $("summary").innerHTML = `<div><b>${evs.length}</b> active events · <b>${board.length}</b> facilities with action items · <b>${items.length}</b> items</div>
      <div class="muted" style="margin-top:4px">${Object.entries(names).map(([n, c]) => `${n} ×${c}`).join(" · ") || "no active events at this time"}</div>
      <h2>Event board (acuity, then severity × panel)</h2>
      ${board.slice(0, 40).map((b) => `<div class="row" data-fid="${b.fid}"><span><b>${b.name}</b> <span class="muted">${b.state}</span></span><span><span class="tag">${b.top.acuity_class}</span> <span class="tag">${b.cards} card${b.cards > 1 ? "s" : ""}</span> <span class="tag">≈${b.panel.toLocaleString()}</span></span></div>`).join("")}
      ${board.length > 40 ? `<div class="muted">… ${board.length - 40} more</div>` : ""}`;
    $("summary").querySelectorAll(".row").forEach((r) => r.addEventListener("click", () => selectFacility(r.dataset.fid)));
    if (state.selected) renderDetail();
    else $("detail").innerHTML = `<div class="muted" style="margin-top:12px">Click a facility on the map or in the board to see its fired cards, sized panels and the patient-facing text.</div>`;
  }

  async function selectFacility(fid) {
    state.selected = fid;
    await renderDetail();
  }

  async function renderDetail() {
    const fid = state.selected;
    const f = state.facilities.features.find((x) => x.properties.id === fid);
    const items = activeItems(state.t).filter((i) => i.facility_id === fid);
    const at = new Date(state.t).toISOString();
    const scenario = $("scenario").value;
    const full = await getJSON(`/facilities/${fid}/action-items?scenario=${scenario}&at=${encodeURIComponent(at)}`);
    const byCard = new Map();
    for (const i of full.items) { if (i.status === "superseded") continue; const a = byCard.get(i.card_id) || {}; a[i.role] = i; byCard.set(i.card_id, a); }
    const roles = ["care_team", "patient", "caregiver"];
    let html = `<h2>${f ? f.properties.name : fid} <span class="muted">${f ? f.properties.state : ""} · VISN ${f ? f.properties.visn : "?"}</span></h2>
      <div class="role">${roles.map((r) => `<button data-role="${r}" class="${state.role === r ? "on" : ""}">${r.replace("_", " ")}</button>`).join("")}</div>`;
    if (!byCard.size) html += `<div class="muted">No action items active at ${fmt(state.t)}.</div>`;
    for (const [cardId, byRole] of [...byCard.entries()].sort((a, b) => (Object.values(a[1])[0].acuity_rank - Object.values(b[1])[0].acuity_rank))) {
      const any = Object.values(byRole)[0];
      const it = byRole[state.role];
      html += `<div class="card"><h3>${any.card_title}</h3>
        <div class="prov">${any.event_name} · ${any.event_severity} · window ${fmt(Date.parse(any.window_start))} → ${fmt(Date.parse(any.window_end))}</div>
        ${any.panel ? `<div class="prov">Affected panel ≈ <b>${Math.round(any.panel.value).toLocaleString()}</b> <details><summary>how was this computed?</summary><div>${escapeHtml(any.panel.formula)}</div><div>${(any.panel.caveats || []).map(escapeHtml).join("<br>")}</div><div class="muted">Sources: ${(any.panel.sources || []).map(escapeHtml).join("; ")}</div></details></div>` : ""}`;
      if (!it) { html += `<div class="muted">No ${state.role.replace("_", " ")} content for this card.</div></div>`; continue; }
      if (it.message) html += `<p>${escapeHtml(it.message)}</p>`;
      else html += `<ul>${it.actions.map((a) => `<li><span class="tag">${a.phase.replace("_", " ")}</span> ${escapeHtml(a.text)}</li>`).join("")}</ul>`;
      if (it.safety_message) html += `<div class="warn">${escapeHtml(it.safety_message)}</div>`;
      html += `<details><summary>escalation (${it.escalation.length})</summary><ul>${it.escalation.map((e) => `<li>${escapeHtml(e.signs)} → <b>${escapeHtml(e.response || "")}</b>${e.emergency ? " 🚨" : ""}</li>`).join("")}</ul></details>
        <div class="prov">Evidence: ${it.evidence_tier} · <span class="tag">${it.status}</span></div></div>`;
    }
    $("detail").innerHTML = html;
    $("detail").querySelectorAll(".role button").forEach((b) => b.addEventListener("click", () => { state.role = b.dataset.role; renderDetail(); }));
  }

  function escapeHtml(s) { return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }

  function togglePlay() { if (state.timer) stop(); else play(); }
  function play() {
    $("play").textContent = "❚❚ Pause";
    state.timer = setInterval(() => {
      const step = Number($("speed").value) * 3600e3;
      if (state.t + step > state.t1) { stop(); return; }
      setT(state.t + step);
    }, 250);
  }
  function stop() { if (state.timer) clearInterval(state.timer); state.timer = null; $("play").textContent = "▶ Play"; }

  init().catch((e) => { $("status").textContent = String(e); console.error(e); });
})();
