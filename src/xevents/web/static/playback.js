/* Playback: scrub a scenario's window and watch counties, facilities and action items change.
   Everything for the chosen scenario is loaded once, so scrubbing never waits on the network;
   only the per-facility card text is fetched on demand (and cached). */
(() => {
  const COLORS = XMap.EVENT_COLORS;
  const SEV = XMap.SEVERITY_RANK;
  const TYPE_ORDER = ["hurricane_flood", "heat", "extreme_cold", "power_outage", "air_pollution", "wildfire_smoke"];
  const HOUR = 3600e3;
  const $ = (id) => document.getElementById(id);

  const state = {
    scenarios: [], facilities: null, events: [], items: [], t0: 0, t1: 0, t: 0,
    playing: false, timer: null, selectedFacility: null, selectedEvent: null, selectedCard: null,
    role: "care_team", detailCache: new Map(), lastCountyPaint: new Map(), lastFacilityPaint: new Map(),
    cards: new Map(), cardSample: new Map(), lastBadges: new Map(), carbon: null,
  };
  let ctx = null, facilityLayer = null, facilityById = new Map(), facilityProps = new Map();
  let badgeLayer = null;
  const cardMarkers = new Map();

  const fmt = (ms) => new Date(ms).toISOString().replace("T", " ").slice(0, 16) + "Z";
  const fmtShort = (ms) => new Date(ms).toISOString().slice(5, 16).replace("T", " ");
  const parse = (s) => Date.parse(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  // one stable colour per card number (index = number - 1): 1 lithium, 2 antipsychotics,
  // 3 delivery, 4 heart failure, 5 insulin, 6 dialysis, 7 cold, 8 smoke
  const CARD_COLORS = ["#4c8dff", "#e4572e", "#2fb37a", "#d9a41a", "#a05cd6", "#e06c9f", "#5fc9e8", "#8c6d3f"];
  const cardColor = (id) => {
    const card = state.cards.get(id);
    const n = card ? card.number - 1 : [...state.cards.keys()].indexOf(id);
    return CARD_COLORS[Math.max(0, n) % CARD_COLORS.length];
  };
  const placeOf = (e) => {
    if (e.geography.area_desc) {
      const d = e.geography.area_desc;
      return d.length > 68 ? d.slice(0, 67) + "…" : d;
    }
    const st = (e.geography.states || []).join(", ");
    const n = e.geography.county_fips.length;
    return st ? `${st} · ${n} count${n === 1 ? "y" : "ies"}` : `${n} counties`;
  };
  const facilityPlace = (fid) => {
    const p = facilityProps.get(fid);
    if (!p) return "";
    return [p.city, p.state].filter(Boolean).join(", ") + (p.visn ? ` · VISN ${p.visn}` : "");
  };
  const activeEvents = (t) => state.events.filter((e) => e._t0 <= t && t <= e._t1);
  const activeItems = (t) => state.items.filter((i) => i.status !== "superseded" && i._t0 <= t && t <= i._t1);

  const getJSON = async (url) => {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`${url} → ${r.status}`);
    return r.json();
  };

  // ------------------------------------------------------------------ boot

  function missingDependency() {
    if (typeof L === "undefined") return "Leaflet (/static/vendor/leaflet.js)";
    if (typeof XMap === "undefined") return "the map helper (/static/map.js)";
    return null;
  }

  async function init() {
    // Fail loudly: a script that 404s (or a stale cached 404) used to leave a blank page.
    const missing = missingDependency();
    if (missing) {
      const msg = `Could not load ${missing}. Reload the page; if it persists, do a hard reload.`;
      $("status").textContent = msg;
      $("side").innerHTML = `<div class="muted">${msg}</div>`;
      throw new Error(msg);
    }
    $("status").textContent = "loading map and facilities…";
    const [scenarios, facilities, mapCtx, cardDefs, carbon] = await Promise.all([
      getJSON("/scenarios"), getJSON("/facilities"), XMap.create("map"), getJSON("/cards"),
      getJSON("/carbon").catch(() => null),
    ]);
    state.carbon = carbon;
    state.scenarios = scenarios;
    state.facilities = facilities;
    ctx = mapCtx;
    for (const c of cardDefs) state.cards.set(c.id, c);
    facilityLayer = L.geoJSON(facilities, {
      pointToLayer: (f, ll) => L.circleMarker(ll, { radius: 2.5, weight: 1, color: "#5b6673", fillColor: "#5b6673", fillOpacity: 0.85 }),
      onEachFeature: (f, layer) => {
        facilityById.set(f.properties.id, layer);
        facilityProps.set(f.properties.id, f.properties);
        layer.on("click", () => selectFacility(f.properties.id));
      },
    }).addTo(ctx.map);
    badgeLayer = L.layerGroup().addTo(ctx.map);

    const sel = $("scenario");
    sel.innerHTML =
      `<option value="live">live (now) — last 2 weeks</option>` +
      scenarios.map((s) => `<option value="${s.id}">${s.id} — replay, ${s.events} events</option>`).join("");
    sel.addEventListener("change", () => loadScenario(sel.value));
    $("play").addEventListener("click", togglePlay);
    $("step-back").addEventListener("click", () => { pause(); step(-1); });
    $("step-fwd").addEventListener("click", () => { pause(); step(1); });
    window.addEventListener("keydown", (e) => {
      if (e.target.tagName === "SELECT" || e.target.tagName === "INPUT") return;
      if (e.code === "Space") { e.preventDefault(); togglePlay(); }
      if (e.code === "ArrowLeft") { pause(); step(-1); }
      if (e.code === "ArrowRight") { pause(); step(1); }
      if (e.code === "Escape" && closeTop()) e.preventDefault();
    });
    window.addEventListener("resize", () => drawTimeline(true));
    initTimelineInput();
    // Honour ?scenario= so the dashboard can hand off to the same view.
    let initial = "live";
    try {
      const want = new URLSearchParams(window.location.search || "").get("scenario");
      if (want && (want === "live" || scenarios.some((s) => s.id === want))) initial = want;
    } catch { /* no URL available (tests) */ }
    sel.value = initial;
    await loadScenario(initial);
  }

  async function loadScenario(id) {
    pause();
    $("status").textContent = `loading ${id}…`;
    const live = id === "live";
    const q = live ? "" : `scenario=${encodeURIComponent(id)}&`;
    const [ev, it] = await Promise.all([
      getJSON(`/events?${q}`.replace(/[?&]$/, "")),
      getJSON(`/action-items?${q}include_superseded=true`),
    ]);
    syncNav(id);
    state.events = ev.events.map((e) => ({ ...e, _t0: parse(e.onset), _t1: parse(e.expires) }));
    state.items = it.items.map((i) => ({ ...i, _t0: parse(i.window_start), _t1: parse(i.window_end) }));
    state.selectedFacility = null;
    state.selectedEvent = null;
    state.selectedCard = null;
    state.detailCache.clear();
    // Keep lastCountyPaint / lastFacilityPaint: they record what the layers actually show,
    // and render() clears whatever the new view does not repaint. Emptying them here left
    // the previous view's counties and facilities painted in the new one.

    // Focus the timeline on the alert window: a single long-running context event (a FEMA
    // incident period runs for weeks) should not squash the storm into a few pixels.
    const onsets = state.events.map((e) => e._t0);
    const shortEnds = state.events.filter((e) => e._t1 - e._t0 <= 14 * 24 * HOUR).map((e) => e._t1);
    if (!onsets.length) {
      // No events (live mode before any ingest): Math.min() of nothing is Infinity and
      // formatting it throws, so anchor the window on the last 24 h and say why it is empty.
      state.t1 = Date.now();
      state.t0 = state.t1 - 24 * HOUR;
    } else {
      state.t0 = Math.min(...onsets);
      state.t1 = Math.max(shortEnds.length ? Math.max(...shortEnds) : 0, Math.max(...onsets) + 24 * HOUR);
    }
    $("t-start").textContent = fmt(state.t0);
    $("t-end").textContent = fmt(state.t1);

    const superseded = state.items.filter((i) => i.status === "superseded").length;
    $("status").textContent = state.events.length
      ? `${state.events.length} events · ${state.items.length} items (${superseded} superseded)`
      : (live ? "no live events ingested yet — run EVENT_MODE=live make ingest match, or pick a replay scenario" : `no events in ${id}`);
    drawTimeline();
    // Start where there is something to see: now for live, the busiest hour for a replay.
    const peak = live ? Date.now() : state.scenarios.find((s) => s.id === id)?.peak_at;
    setT(peak ? clamp(typeof peak === "number" ? peak : parse(peak), state.t0, state.t1) : state.t0);
    fitToEvents();
  }

  function syncNav(id) {
    const qs = `?scenario=${encodeURIComponent(id)}`;
    $("nav-dashboard").href = `/${qs}`;
    $("nav-events").href = `/dashboard/events${qs}`;
  }

  function fitToEvents() {
    const fips = new Set();
    for (const e of state.events) for (const c of e.geography.county_fips) fips.add(c);
    XMap.fitCounties(ctx, fips, 0.1);
  }

  // ------------------------------------------------------------------ transport

  function setT(t) {
    state.t = clamp(t, state.t0, state.t1);
    $("clock").textContent = fmt(state.t);
    render();
  }
  const stepMs = () => Number($("speed").value) * HOUR;
  function step(dir) { setT(state.t + dir * stepMs()); }

  function syncPlayButton() { $("play").textContent = state.playing ? "❚❚ Pause" : "▶ Play"; }
  function play() {
    if (state.playing) return;
    if (state.t >= state.t1) setT(state.t0);
    state.playing = true;
    syncPlayButton();
    state.timer = setInterval(() => {
      if (!state.playing) return;
      if (state.t + stepMs() >= state.t1) { setT(state.t1); pause(); return; }
      step(1);
    }, 300);
  }
  function pause() {
    state.playing = false;
    if (state.timer) { clearInterval(state.timer); state.timer = null; }
    syncPlayButton();
  }
  function togglePlay() { state.playing ? pause() : play(); }

  // ------------------------------------------------------------------ timeline

  const TL = { margin: 8, labelW: 132, laneH: 13, axisH: 18, maxLanes: 9 };

  function lanes() {
    const byName = new Map();
    for (const e of state.events) {
      const key = XMap.eventGroup(e.event_name);  // one AirNow row per pollutant, not per reading
      if (!byName.has(key)) byName.set(key, { name: key, type: e.event_type, events: [], first: e._t0 });
      const lane = byName.get(key);
      lane.events.push(e);
      lane.first = Math.min(lane.first, e._t0);
    }
    const all = [...byName.values()].sort((a, b) => a.first - b.first || a.name.localeCompare(b.name));
    if (all.length <= TL.maxLanes) return all;
    const head = all.slice(0, TL.maxLanes - 1);
    const rest = all.slice(TL.maxLanes - 1);
    head.push({
      name: `+${rest.length} more event types`, type: rest[0].type,
      events: rest.flatMap((l) => l.events), first: rest[0].first, grouped: true,
    });
    return head;
  }

  const xOf = (t, w) => TL.labelW + ((clamp(t, state.t0, state.t1) - state.t0) / (state.t1 - state.t0 || 1)) * (w - TL.labelW - TL.margin);
  const tOf = (x, w) => state.t0 + ((x - TL.labelW) / (w - TL.labelW - TL.margin)) * (state.t1 - state.t0);

  function movePlayhead() {
    const svg = $("timeline");
    if (!svg || !svg.querySelector) return;
    const w = svg.clientWidth || (svg.parentElement && svg.parentElement.clientWidth) || 1200;
    const px = xOf(state.t, w);
    const line = svg.querySelector("#playhead-line");
    const head = svg.querySelector("#playhead-head");
    if (!line || !head) return false;
    line.setAttribute("x1", px);
    line.setAttribute("x2", px);
    head.setAttribute("points", `${px - 5},${TL.axisH - 10} ${px + 5},${TL.axisH - 10} ${px},${TL.axisH - 3}`);
    return true;
  }

  function drawTimeline(full = true) {
    const svg = $("timeline");
    if (!state.events.length) { svg.innerHTML = ""; return; }
    if (!full && movePlayhead()) return;
    const w = svg.clientWidth || svg.parentElement.clientWidth;
    const ls = lanes();
    const h = TL.axisH + ls.length * TL.laneH + 10;
    svg.setAttribute("height", h);
    svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
    const parts = [];

    // day gridlines + labels
    const days = Math.max(1, Math.round((state.t1 - state.t0) / (24 * HOUR)));
    const stepDays = days > 20 ? Math.ceil(days / 10) : 1;
    for (let d = new Date(state.t0); d <= state.t1; d = new Date(d.getTime() + stepDays * 24 * HOUR)) {
      const day = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate());
      if (day < state.t0) continue;
      const x = xOf(day, w);
      parts.push(`<line x1="${x}" y1="${TL.axisH - 4}" x2="${x}" y2="${h - 6}" stroke="#222c38" stroke-width="1"/>`);
      parts.push(`<text x="${x + 3}" y="12">${new Date(day).toISOString().slice(5, 10)}</text>`);
    }

    ls.forEach((lane, i) => {
      const y = TL.axisH + i * TL.laneH;
      const color = COLORS[lane.type] || "#4c8dff";
      parts.push(`<text class="lane-label" x="0" y="${y + 9}">${esc(lane.name.length > 24 ? lane.name.slice(0, 23) + "…" : lane.name)}</text>`);
      for (const e of lane.events) {
        const x1 = xOf(e._t0, w), x2 = xOf(e._t1, w);
        const sev = SEV[e.severity] || 0;
        const on = state.selectedEvent === e.event_key;
        parts.push(
          `<rect class="bar" data-key="${esc(e.event_key)}" x="${x1}" y="${y + 1.5}" width="${Math.max(2, x2 - x1)}" height="${TL.laneH - 4}" rx="2"` +
          ` fill="${color}" fill-opacity="${0.35 + 0.15 * sev}" stroke="${on ? "#fff" : "none"}" stroke-width="${on ? 1.2 : 0}">` +
          `<title>${esc(e.event_name)} · ${esc(e.severity)}\n${fmt(e._t0)} → ${fmt(e._t1)}\n${e.geography.county_fips.length} counties</title></rect>`
        );
      }
    });

    const px = xOf(state.t, w);
    parts.push(`<line id="playhead-line" x1="${px}" y1="${TL.axisH - 6}" x2="${px}" y2="${h - 4}" stroke="#fff" stroke-width="1.5"/>`);
    parts.push(`<polygon id="playhead-head" points="${px - 5},${TL.axisH - 10} ${px + 5},${TL.axisH - 10} ${px},${TL.axisH - 3}" fill="#fff"/>`);
    svg.innerHTML = parts.join("");
  }

  function initTimelineInput() {
    const svg = $("timeline");
    let dragging = false;
    const seek = (evt) => {
      const rect = svg.getBoundingClientRect();
      setT(tOf(evt.clientX - rect.left, rect.width));
    };
    svg.addEventListener("mousedown", (evt) => {
      pause();
      dragging = true;
      const key = evt.target && evt.target.dataset ? evt.target.dataset.key : null;
      if (key) selectEvent(key);
      seek(evt);
    });
    window.addEventListener("mousemove", (evt) => { if (dragging) seek(evt); });
    window.addEventListener("mouseup", () => { dragging = false; });
  }

  // ------------------------------------------------------------------ map + panel

  function render() {
    const evs = activeEvents(state.t);
    const items = activeItems(state.t);

    const paint = new Map();
    for (const e of evs) {
      for (const c of e.geography.county_fips) {
        const cur = paint.get(c), sev = SEV[e.severity] || 0;
        const better = !cur || sev > cur.sev || (sev === cur.sev && TYPE_ORDER.indexOf(e.event_type) < TYPE_ORDER.indexOf(cur.type));
        if (better) {
          paint.set(c, {
            color: COLORS[e.event_type] || "#4c8dff",
            opacity: XMap.eventOpacity(e, sev),
            sev,
            type: e.event_type,
          });
        }
      }
    }
    if (state.selectedEvent) {
      const sel = state.events.find((e) => e.event_key === state.selectedEvent);
      if (sel) for (const c of sel.geography.county_fips) paint.set(c, { color: "#ffffff", opacity: 0.45, sev: 9, type: sel.event_type });
    }
    // repaint only what changed
    const seen = new Set();
    paint.forEach((v, fips) => {
      seen.add(fips);
      const prev = state.lastCountyPaint.get(fips);
      if (!prev || prev.color !== v.color || prev.opacity !== v.opacity) {
        const layer = ctx.byFips.get(fips);
        if (layer) layer.setStyle({ ...ctx.baseStyle, fillColor: v.color, fillOpacity: v.opacity, color: v.color, weight: 0.5 });
      }
    });
    state.lastCountyPaint.forEach((_, fips) => {
      if (!seen.has(fips)) { const layer = ctx.byFips.get(fips); if (layer) layer.setStyle(ctx.baseStyle); }
    });
    state.lastCountyPaint = paint;

    const byFacility = new Map();
    for (const i of items) {
      if (state.selectedCard && i.card_id !== state.selectedCard) continue;
      const a = byFacility.get(i.facility_id) || [];
      a.push(i);
      byFacility.set(i.facility_id, a);
    }
    const fseen = new Set();
    byFacility.forEach((its, fid) => {
      fseen.add(fid);
      const top = its.reduce((b, i) => (i.acuity_rank < b.acuity_rank ? i : b), its[0]);
      const panel = Math.max(...its.map((i) => i.panel || 0));
      // When a card is selected the map answers "where is this card firing?", so colour by
      // card; otherwise colour by the event driving the highest-acuity item.
      const fill = state.selectedCard ? cardColor(state.selectedCard) : COLORS[top.event_type] || "#fff";
      const key = `${fill}|${Math.round(panel)}|${state.selectedFacility === fid}`;
      if (state.lastFacilityPaint.get(fid) !== key) {
        const layer = facilityById.get(fid);
        if (layer) {
          layer.setStyle({
            radius: 5 + Math.min(10, Math.sqrt(panel) / 8),
            color: state.selectedFacility === fid ? "#ffe680" : "#fff",
            weight: state.selectedFacility === fid ? 2.5 : 1,
            fillColor: fill,
            fillOpacity: 0.95,
          });
          layer.bringToFront();
        }
      }
      state.lastFacilityPaint.set(fid, key);
      const l = facilityById.get(fid);
      if (l) {
        const cards = [...new Set(its.map((i) => i.card_title))];
        l.bindTooltip(
          `<b>${esc(facilityProps.get(fid)?.name || fid)}</b><br>${esc(facilityPlace(fid))}` +
          `<br>${cards.length} card${cards.length > 1 ? "s" : ""}: ${esc(cards.join(" · "))}` +
          `<br>panel ≈ ${panel.toLocaleString()}`
        );
      }
    });
    state.lastFacilityPaint.forEach((_, fid) => {
      if (!fseen.has(fid)) {
        const layer = facilityById.get(fid);
        if (layer) {
          layer.setStyle({ radius: 2.5, color: "#5b6673", fillColor: "#5b6673", fillOpacity: 0.85, weight: 1 });
          layer.unbindTooltip();
        }
        state.lastFacilityPaint.delete(fid);
      }
    });

    drawBadges(byFacility);
    drawTimeline(false);
    renderSide(evs, items, byFacility);
  }

  /* Two audiences, not three. Caregiver wording is the same guidance addressed to whoever
     is helping, so it belongs beside the patient text rather than behind a third tab. */
  const ROLES = [
    { id: "care_team", label: "care team" },
    { id: "patient", label: "patient & caregiver" },
  ];
  const roleOf = () => (state.role === "care_team" ? "care_team" : "patient");

  function roleToggle() {
    return `<div class="roles">${ROLES.map(
      (r) => `<button data-role="${r.id}" class="${roleOf() === r.id ? "on" : ""}">${r.label}</button>`
    ).join("")}</div>`;
  }

  function roleContent(def) {
    if (roleOf() === "care_team") {
      const acts = def.actions.care_team || [];
      if (!acts.length) return `<div class="muted">No care-team content on this card.</div>`;
      let out = "";
      for (const phase of ["pre_event", "during_event", "any"]) {
        const list = acts.filter((a) => a.phase === phase);
        if (!list.length) continue;
        const label = { pre_event: "Pre-event (3–7 days out)", during_event: "During event", any: "Actions" }[phase];
        out += `<div class="prov" style="margin-top:6px">${label}</div><ul>${list.map((a) => `<li>${esc(a.text)}</li>`).join("")}</ul>`;
      }
      return out;
    }
    const patient = def.actions.patient || [];
    const caregiver = def.actions.caregiver || [];
    let out = patient.length
      ? `<p>${esc(patient.map((a) => a.text).join(" "))}</p>`
      : `<div class="muted">No patient wording on this card yet.</div>`;
    out += caregiver.length
      ? `<div class="prov" style="margin-top:6px">For a caregiver</div><p>${esc(caregiver.map((a) => a.text).join(" "))}</p>`
      : `<div class="prov" style="margin-top:6px">Caregiver wording is not yet written for this card; the patient guidance above is what a caregiver would be given.</div>`;
    return out;
  }

  /* Carbon is display-only context: order-of-magnitude estimates from published LCAs.
     Drugs within a card are alternatives a patient takes one of, so they are shown as
     separate scenarios and never summed. */
  function carbonBlock(def, panelValue) {
    const table = state.carbon;
    if (!table) return "";
    const entries = (table.by_card || {})[String(def.number)] || [];
    if (!entries.length) return "";
    const patients = Math.round(panelValue || 0);
    const rows = entries
      .map((e) => {
        const [lo, hi] = e.kg_co2e_per_patient_year;
        const tLo = (patients * lo) / 1000;
        const tHi = (patients * hi) / 1000;
        const perDose = e.g_co2e_per_daily_dose
          ? `${e.g_co2e_per_daily_dose[0]}–${e.g_co2e_per_daily_dose[1]} g/dose`
          : e.kg_co2e_per_session
            ? `${e.kg_co2e_per_session[0]}–${e.kg_co2e_per_session[1]} kg/session`
            : "—";
        const fmtT = (v) => (v >= 100 ? Math.round(v).toLocaleString() : v.toFixed(v < 10 ? 1 : 0));
        return `<tr><td>${esc(e.drug)}<div class="prov">${esc(e.assumed_dose)} · ${esc(e.basis.replace("_", " "))} · confidence ${esc(e.confidence.replace("_", "–"))}</div>${
          e.note ? `<div class="prov">${esc(e.note)}</div>` : ""
        }</td><td>${perDose}</td><td>${lo}–${hi} kg</td><td>${e.km_driven_equivalent_per_year[0].toLocaleString()}–${e.km_driven_equivalent_per_year[1].toLocaleString()} km</td><td><b>${fmtT(tLo)}–${fmtT(tHi)} t</b></td></tr>`;
      })
      .join("");
    return `<details style="margin-top:8px"><summary>carbon footprint of this card's therapies (${entries.length})</summary>
      <div class="prov" style="margin:4px 0">Scaled to this facility's estimated panel of <b>${patients.toLocaleString()}</b> patients.
        Drugs on a card are alternatives, so rows are separate scenarios and must not be added together.</div>
      <table class="carbon"><thead><tr><th>Therapy</th><th>Per dose</th><th>Per patient-year</th><th>≈ car km/yr</th><th>Panel t CO2e/yr</th></tr></thead>
      <tbody>${rows}</tbody></table>
      <div class="warn" style="margin-top:6px">${esc(table.ui_disclaimer)}</div>
      <div class="prov">Scope: ${esc(table.assumptions.scope)}. Car equivalent at ${table.assumptions.car_kg_co2e_per_km} kg CO2e/km.</div>
      </details>`;
  }

  /* Selections nest: a card filter can hold a facility drill-down inside it. The detail
     panel therefore needs a way back to the level above, not only a way out — so it carries
     a breadcrumb, a close button and an Escape binding rather than relying on the reader
     discovering that clicking the same row again toggles it off. */
  function selectionCrumbs() {
    const out = [{ key: "all", label: "All cards" }];
    if (state.selectedCard) {
      const def = state.cards.get(state.selectedCard);
      out.push({ key: "card", label: def ? def.title : state.selectedCard });
    }
    if (state.selectedEvent) {
      const e = state.events.find((x) => x.event_key === state.selectedEvent);
      out.push({ key: "event", label: e ? e.event_name : state.selectedEvent });
    }
    if (state.selectedFacility) {
      const fp = facilityProps.get(state.selectedFacility);
      out.push({ key: "facility", label: fp ? fp.name : state.selectedFacility });
    }
    return out;
  }

  function detailHeader() {
    const crumbs = selectionCrumbs();
    const trail = crumbs
      .map((c, i) => {
        const label = c.label.length > 34 ? c.label.slice(0, 33) + "…" : c.label;
        return i === crumbs.length - 1
          ? `<span class="crumb on">${esc(label)}</span>`
          : `<a href="#" class="crumb" data-crumb="${c.key}">${esc(label)}</a>`;
      })
      .join('<span class="sep">\u203a</span>');
    return `<div class="crumbs">${trail}` +
      `<button class="closebtn" data-close="1" title="Close (Esc)" aria-label="Close">\u00d7</button></div>`;
  }

  function invalidatePaint() {
    state.lastFacilityPaint = new Map();
    state.lastBadges = new Map();
  }

  function clearSelection() {
    state.selectedCard = null;
    state.selectedEvent = null;
    state.selectedFacility = null;
    invalidatePaint();
    render();
    focusDetail();
  }

  /* Close one level: the facility drill-down first, then the card or event filter. */
  function closeTop() {
    if (state.selectedFacility) state.selectedFacility = null;
    else if (state.selectedEvent) state.selectedEvent = null;
    else if (state.selectedCard) state.selectedCard = null;
    else return false;
    invalidatePaint();
    render();
    focusDetail();
    return true;
  }

  function goToCrumb(key) {
    if (key === "all") return clearSelection();
    state.selectedFacility = null;
    invalidatePaint();
    render();
    focusDetail();
  }

  /* Called after any detail panel writes its markup. */
  function wireDetailChrome() {
    const el = $("detail");
    if (!el || !el.querySelectorAll) return;
    el.querySelectorAll("[data-crumb]").forEach((a) =>
      a.addEventListener("click", (e) => {
        if (e && e.preventDefault) e.preventDefault();
        goToCrumb(a.dataset.crumb);
      })
    );
    el.querySelectorAll("[data-close]").forEach((b) => b.addEventListener("click", () => closeTop()));
  }

  function cardsAt(items) {
    const byCard = new Map();
    for (const i of items) {
      const c = byCard.get(i.card_id) || {
        id: i.card_id, title: i.card_title, acuity: i.acuity_rank, acuityClass: i.acuity_class,
        facilities: new Set(), events: new Set(), panel: 0, types: new Set(),
      };
      c.facilities.add(i.facility_id);
      c.events.add(i.event_name);
      c.types.add(i.event_type);
      c.panel = Math.max(c.panel, i.panel || 0);
      c.acuity = Math.min(c.acuity, i.acuity_rank);
      byCard.set(i.card_id, c);
    }
    return [...byCard.values()].sort((a, b) => a.acuity - b.acuity);
  }

  /* Facilities are circles (a place). Cards are a small fanned stack of coloured chips
     above the circle (a playbook card), so "where is this card firing" is readable at a
     glance and never confused with the weather shading underneath. */
  function badgeHtml(cardIds, selected) {
    const shown = selected ? cardIds.filter((c) => c === selected) : cardIds.slice(0, 4);
    const extra = !selected && cardIds.length > 4 ? cardIds.length - 4 : 0;
    const chips = shown
      .map((id, n) => {
        const tilt = shown.length === 1 ? 0 : -10 + (20 / Math.max(1, shown.length - 1)) * n;
        return `<i style="background:${cardColor(id)};transform:rotate(${tilt}deg)"></i>`;
      })
      .join("");
    return `<span class="cards${selected ? " one" : ""}">${chips}${extra ? `<b>+${extra}</b>` : ""}</span>`;
  }

  function drawBadges(byFacility) {
    const want = new Map();
    byFacility.forEach((its, fid) => {
      const ids = [...new Set(its.map((i) => i.card_id))].sort(
        (a, b) => (state.cards.get(a)?.number || 0) - (state.cards.get(b)?.number || 0)
      );
      want.set(fid, ids);
    });
    // remove badges that are no longer wanted
    cardMarkers.forEach((marker, fid) => {
      if (!want.has(fid)) { badgeLayer.removeLayer(marker); cardMarkers.delete(fid); state.lastBadges.delete(fid); }
    });
    want.forEach((ids, fid) => {
      const sig = `${ids.join(",")}|${state.selectedCard || ""}`;
      if (state.lastBadges.get(fid) === sig) return;
      state.lastBadges.set(fid, sig);
      const old = cardMarkers.get(fid);
      if (old) badgeLayer.removeLayer(old);
      const f = state.facilities.features.find((x) => x.properties.id === fid);
      if (!f) return;
      const [lon, lat] = f.geometry.coordinates;
      const width = 9 + Math.max(0, (state.selectedCard ? 1 : Math.min(4, ids.length)) - 1) * 7;
      const marker = L.marker([lat, lon], {
        icon: L.divIcon({
          className: "card-badge",
          html: badgeHtml(ids, state.selectedCard),
          iconSize: [width, 14],
          iconAnchor: [width / 2, 20],
        }),
        interactive: true,
        keyboard: false,
      });
      const titles = ids.map((id) => state.cards.get(id)?.title || id);
      marker.bindTooltip(
        `<b>${esc(facilityProps.get(fid)?.name || fid)}</b><br>${esc(facilityPlace(fid))}<br>${titles.map(esc).join("<br>")}`,
        { direction: "top" }
      );
      marker.on("click", () => selectFacility(fid));
      marker.addTo(badgeLayer);
      cardMarkers.set(fid, marker);
    });
  }

  function renderSide(evs, items, byFacility) {
    const board = [...byFacility.entries()].map(([fid, its]) => {
      const top = its.reduce((b, i) => (i.acuity_rank < b.acuity_rank ? i : b), its[0]);
      const panel = Math.max(...its.map((i) => i.panel || 0));
      const sev = Math.max(...its.map((i) => SEV[i.event_severity] || 0));
      const p = facilityProps.get(fid);
      return { fid, name: p ? p.name : fid, cards: new Set(its.map((i) => i.card_id)).size, top, panel, sev };
    }).sort((a, b) => a.top.acuity_rank - b.top.acuity_rank || b.sev * b.panel - a.sev * a.panel);

    const cards = cardsAt(items);
    const evList = [...evs].sort((a, b) => (SEV[b.severity] || 0) - (SEV[a.severity] || 0) || a.event_name.localeCompare(b.event_name));
    const filterNote = state.selectedCard
      ? `<span class="clear">filtered to this card · <a href="#" id="clear-card">show all</a></span>` : "";

    const html = [
      `<h2>At ${fmt(state.t)}</h2>`,
      `<div><b>${evs.length}</b> active events · <b>${cards.length}</b> cards firing · <b>${board.length}</b> facilities · <b>${items.length}</b> action items</div>`,

      `<div id="detail"></div>`,
      `<h2>Cards firing now (${cards.length}) ${filterNote}</h2>`,
      cards.map((c) => {
        const on = state.selectedCard === c.id ? " on" : "";
        return `<div class="row${on}" data-card="${esc(c.id)}">
          <span><span class="swatch" style="background:${cardColor(c.id)}"></span><b>${esc(c.title)}</b>
            <span class="loc">${c.facilities.size} facilit${c.facilities.size === 1 ? "y" : "ies"} · triggered by ${esc(XMap.summarizeNames(c.events))}</span></span>
          <span><span class="tag">${esc(c.acuityClass)}</span> <span class="tag">≈${Math.round(c.panel).toLocaleString()}</span></span></div>`;
      }).join("") || `<div class="muted">No cards fire at this time.</div>`,

      `<h2>Events now (${evList.length})</h2>`,
      evList.slice(0, 25).map((e) => {
        const on = state.selectedEvent === e.event_key ? " on" : "";
        return `<div class="row${on}" data-event="${esc(e.event_key)}">
          <span><b>${esc(e.event_name)}</b>
            <span class="loc">${esc(placeOf(e))}</span>
            <span class="loc">${fmtShort(e._t0)} → ${fmtShort(e._t1)} UTC</span></span>
          <span><span class="tag sev-${SEV[e.severity] || 0}">${esc(e.severity)}</span></span></div>`;
      }).join("") || `<div class="muted">No events active at this time.</div>`,
      evList.length > 25 ? `<div class="muted">… ${evList.length - 25} more</div>` : "",

      `<h2>Facilities by acuity (${board.length})</h2>`,
      board.slice(0, 30).map((b) => {
        const on = state.selectedFacility === b.fid ? " on" : "";
        return `<div class="row${on}" data-fid="${esc(b.fid)}">
          <span><b>${esc(b.name)}</b>
            <span class="loc">${esc(facilityPlace(b.fid))}</span>
            <span class="loc">until ${fmtShort(b.top._t1)} UTC</span></span>
          <span><span class="tag">${esc(b.top.acuity_class)}</span> <span class="tag">${b.cards} card${b.cards > 1 ? "s" : ""}</span> <span class="tag">≈${b.panel.toLocaleString()}</span></span></div>`;
      }).join("") || `<div class="muted">No action items at this time.</div>`,
      board.length > 30 ? `<div class="muted">… ${board.length - 30} more</div>` : "",
    ].join("");
    $("side").innerHTML = html;
    $("side").querySelectorAll("[data-fid]").forEach((r) => r.addEventListener("click", () => selectFacility(r.dataset.fid)));
    $("side").querySelectorAll("[data-event]").forEach((r) => r.addEventListener("click", () => selectEvent(r.dataset.event)));
    $("side").querySelectorAll("[data-card]").forEach((r) => r.addEventListener("click", () => selectCard(r.dataset.card)));
    const clear = document.getElementById("clear-card");
    if (clear) {
      clear.addEventListener("click", (e) => {
        if (e && e.preventDefault) { e.preventDefault(); e.stopPropagation(); }
        clearSelection();
      });
    }
    renderLegend(cards);
    if (state.selectedFacility) renderFacilityDetail();
    else if (state.selectedEvent) renderEventDetail();
    else if (state.selectedCard) renderCardDetail(cards);
    else $("detail").innerHTML = "";
  }

  function renderLegend(cards) {
    const el = document.getElementById("map-legend");
    if (!el) return;
    el.hidden = false;
    const counts = {};
    for (const e of activeEvents(state.t)) {
      for (const c of e.geography.county_fips) {
        (counts[e.event_type] ||= new Set()).add(c);
      }
    }
    const countyCounts = Object.fromEntries(Object.entries(counts).map(([k, v]) => [k, v.size]));
    const cardRows = cards.length
      ? `<div class="hdr">Cards — click to isolate</div>` +
        cards
          .map((c) => {
            const dim = state.selectedCard && state.selectedCard !== c.id ? "opacity:.45;" : "";
            const title = c.title.length > 30 ? c.title.slice(0, 29) + "…" : c.title;
            return `<div data-legend="${esc(c.id)}" style="${dim}cursor:pointer"><i class="card-chip" style="background:${cardColor(c.id)}"></i>
              <span>${esc(title)}</span><span class="muted">${c.facilities.size}</span></div>`;
          })
          .join("")
      : `<div class="hdr">Cards</div><div class="muted" style="padding:2px 0">none firing now</div>`;
    el.innerHTML = XMap.legendHtml(countyCounts) + cardRows;
    el.querySelectorAll("[data-legend]").forEach((r) =>
      r.addEventListener("click", () => selectCard(r.dataset.legend))
    );
  }

  // ------------------------------------------------------------------ selection

  function focusDetail() {
    const side = $("side");
    if (side && typeof side.scrollTop === "number") side.scrollTop = 0;
  }

  async function selectCard(id) {
    state.selectedCard = state.selectedCard === id ? null : id;
    state.selectedEvent = null;
    state.selectedFacility = null;
    state.lastFacilityPaint = new Map();  // force a repaint: colours change with the filter
    state.lastBadges = new Map();
    if (state.selectedCard) {
      const firing = state.items.find(
        (i) => i.card_id === state.selectedCard && i.status !== "superseded" && i._t0 <= state.t && state.t <= i._t1
      );
      if (firing) await loadCardSample(state.selectedCard, firing.facility_id);
    }
    render();
    focusDetail();
  }

  function selectEvent(key) {
    state.selectedEvent = state.selectedEvent === key ? null : key;
    drawTimeline(true);
    state.selectedFacility = null;
    state.selectedCard = null;
    state.lastBadges = new Map();
    state.lastFacilityPaint = new Map();
    render();
  }

  async function selectFacility(fid) {
    state.selectedFacility = state.selectedFacility === fid ? null : fid;
    state.selectedEvent = null;
    state.lastFacilityPaint = new Map();
    state.lastBadges = new Map();
    if (state.selectedFacility && !state.detailCache.has(fid)) {
      const scenario = $("scenario").value;
      const doc = await getJSON(`/facilities/${encodeURIComponent(fid)}/action-items?scenario=${encodeURIComponent(scenario)}`);
      state.detailCache.set(fid, doc.items.map((i) => ({ ...i, _t0: parse(i.window_start), _t1: parse(i.window_end) })));
    }
    render();
    focusDetail();
  }

  async function loadCardSample(cardId, facilityId) {
    /* The card definition holds the reviewed text; the action item holds the profile's
       templated escalation and safety line. Pull one item so we never invent either. */
    if (state.cardSample.has(cardId)) return state.cardSample.get(cardId);
    try {
      const view = $("scenario").value;
      const q = view === "live" ? "" : `scenario=${encodeURIComponent(view)}&`;
      const doc = await getJSON(`/facilities/${encodeURIComponent(facilityId)}/action-items?${q}`.replace(/[?&]$/, ""));
      const items = doc.items.filter((i) => i.card_id === cardId);
      const byRole = {};
      for (const i of items) byRole[i.role] = i;
      state.cardSample.set(cardId, byRole);
      return byRole;
    } catch {
      state.cardSample.set(cardId, {});
      return {};
    }
  }

  function renderCardDetail(cards) {
    const summary = cards.find((c) => c.id === state.selectedCard);
    const def = state.cards.get(state.selectedCard);
    if (!summary || !def) {
      $("detail").innerHTML =
        detailHeader() +
        `<h2>Selected card</h2><div class="muted">This card is not firing at ${fmt(state.t)}.</div>`;
      wireDetailChrome();
      return;
    }
    const sample = state.cardSample.get(state.selectedCard) || {};
    const it = sample[state.role];
    const facs = [...summary.facilities]
      .map((fid) => ({ fid, p: facilityProps.get(fid), panel: Math.max(...state.items.filter((i) => i.facility_id === fid && i.card_id === def.id).map((i) => i.panel || 0)) }))
      .sort((a, b) => b.panel - a.panel);
    const totalPanel = facs.reduce((sum, f) => sum + (f.panel || 0), 0);

    let html = detailHeader() + `<h2>Selected card</h2><div class="card">
      <h3><span class="swatch" style="background:${cardColor(def.id)}"></span>${esc(def.title)}</h3>
      <div class="prov">${esc(def.id)} v${esc(def.version)} · acuity ${esc(def.acuity_class)} · evidence ${esc(def.evidence_tier)}</div>
      <div class="prov"><b>When:</b> fires ${def.window_days.min}–${def.window_days.max} days ahead · active at ${fmt(state.t)} UTC</div>
      <div class="prov"><b>Where now:</b> ${facs.length} facilit${facs.length === 1 ? "y" : "ies"} · triggered by ${esc(XMap.summarizeNames(summary.events, 6))}</div>
      <div class="prov"><b>Estimated panel across those facilities:</b> ≈ ${Math.round(totalPanel).toLocaleString()} veterans</div>
      <p>${esc(def.summary)}</p>
      ${roleToggle()}`;
    html += roleContent(def);
    if (it && it.safety_message) html += `<div class="warn">${esc(it.safety_message)}</div>`;
    html += carbonBlock(def, facs.length ? Math.max(...facs.map((f) => f.panel || 0)) : 0);
    const esc_list = (it ? it.escalation : def.escalation) || [];
    html += `<details><summary>escalation triggers (${esc_list.length})</summary><ul>${esc_list
      .map((e) => `<li>${esc(e.signs)}${e.response ? ` → <b>${esc(e.response)}</b>` : ""}${e.emergency ? " 🚨" : ""}</li>`)
      .join("")}</ul></details>`;
    html += `<details><summary>sources (${def.sources.length})</summary><ul>${def.sources.map((x) => `<li>${esc(x.citation)}</li>`).join("")}</ul></details>`;
    html += `<details open><summary>facilities firing this card (${facs.length})</summary><ul>${facs
      .slice(0, 25)
      .map((f) => `<li><a href="#" data-goto="${esc(f.fid)}">${esc(f.p ? f.p.name : f.fid)}</a> <span class="muted">${esc(f.p ? [f.p.city, f.p.state].filter(Boolean).join(", ") : "")} · ≈${Math.round(f.panel).toLocaleString()}</span></li>`)
      .join("")}</ul>${facs.length > 25 ? `<div class="muted">… ${facs.length - 25} more</div>` : ""}</details>`;
    html += `<div class="prov" style="margin-top:6px">Patient-facing wording is reviewed clinical content, shown verbatim from the card library.</div></div>`;
    $("detail").innerHTML = html;
    $("detail").querySelectorAll(".roles button").forEach((b) =>
      b.addEventListener("click", () => { state.role = b.dataset.role; renderCardDetail(cards); })
    );
    $("detail").querySelectorAll("[data-goto]").forEach((a) =>
      a.addEventListener("click", (e) => { e.preventDefault(); selectFacility(a.dataset.goto); })
    );
    wireDetailChrome();
  }

  function renderEventDetail() {
    const e = state.events.find((x) => x.event_key === state.selectedEvent);
    if (!e) return;
    const mine = state.items.filter((i) => i.event_key === e.event_key);
    const facs = new Set(mine.map((i) => i.facility_id));
    const byCard = new Map();
    for (const i of mine) {
      const c = byCard.get(i.card_id) || { title: i.card_title, facilities: new Set() };
      c.facilities.add(i.facility_id);
      byCard.set(i.card_id, c);
    }
    const cardList = [...byCard.entries()]
      .map(([id, c]) => `<li><span class="swatch" style="background:${cardColor(id)}"></span>${esc(c.title)} — ${c.facilities.size} facilities</li>`)
      .join("");
    $("detail").innerHTML = detailHeader() + `<h2>Selected event</h2><div class="card">
      <h3>${esc(e.event_name)} <span class="tag sev-${SEV[e.severity] || 0}">${esc(e.severity)}</span> ${XMap.temporalityBadge(e.temporality)}</h3>
      <div class="prov">${esc(e.event_key)}</div>
      <div class="prov"><b>Where:</b> ${esc(placeOf(e))}${e.geography.states?.length ? ` (${esc(e.geography.states.join(", "))})` : ""}</div>
      <div class="prov"><b>When:</b> ${fmt(e._t0)} → ${fmt(e._t1)} UTC (${Math.round((e._t1 - e._t0) / 36e5)} h)</div>
      <div class="prov">Urgency ${esc(e.urgency)} · certainty ${esc(e.certainty)} · source ${esc(e.source)}</div>
      ${e.geography.note ? `<div class="prov">${esc(e.geography.note)}</div>` : ""}
      ${e.metrics && e.metrics.outage_pct !== undefined ? `<div class="prov"><b>Outage:</b> ${Number(e.metrics.customers_out).toLocaleString()} of ${Number(e.metrics.county_customers).toLocaleString()} customers out (${esc(e.metrics.outage_pct)}%)</div>` : ""}
      ${e.attribution ? `<div class="prov">${esc(e.attribution)} ${(e.caveats || []).map(esc).join(" ")}</div>` : ""}
      <div style="margin-top:6px"><b>Cards fired:</b> ${byCard.size ? `${mine.length} action items at ${facs.size} facilities` : "none — no card trigger matches this event"}</div>
      ${cardList ? `<ul>${cardList}</ul>` : ""}
      <div class="prov" style="margin-top:6px"><a href="/dashboard/events/${encodeURIComponent(e.event_key)}?scenario=${encodeURIComponent($("scenario").value)}">open full event page →</a></div>
    </div>`;
    wireDetailChrome();
  }

  function renderFacilityDetail() {
    const fid = state.selectedFacility;
    const f = state.facilities.features.find((x) => x.properties.id === fid);
    const all = state.detailCache.get(fid) || [];
    const live = all.filter((i) => i.status !== "superseded" && i._t0 <= state.t && state.t <= i._t1);
    const byCard = new Map();
    for (const i of live) {
      const entry = byCard.get(i.card_id) || { title: i.card_title, acuity: i.acuity_rank, roles: {} };
      const cur = entry.roles[i.role];
      if (!cur || (SEV[i.event_severity] || 0) > (SEV[cur.event_severity] || 0)) entry.roles[i.role] = i;
      byCard.set(i.card_id, entry);
    }
    const p = f ? f.properties : {};
    let html = detailHeader() + `<h2>${esc(p.name || fid)}</h2>
      <div class="prov"><b>Where:</b> ${esc(p.city || "")}, ${esc(p.state || "")} · VISN ${esc(p.visn || "?")} · county ${esc(p.county_fips || "?")}</div>
      <div class="prov">${esc(p.classification || "")} · as of ${fmt(state.t)} UTC</div>
      ${roleToggle()}`;
    if (!byCard.size) html += `<div class="muted">No action items active at ${fmt(state.t)}.</div>`;
    for (const [cardId, entry] of [...byCard.entries()].sort((a, b) => a[1].acuity - b[1].acuity)) {
      const any = Object.values(entry.roles)[0];
      const it = entry.roles[state.role];
      html += `<div class="card"><h3>${esc(entry.title)}</h3>
        <div class="prov">${esc(any.event_name)} · ${esc(any.event_severity)} ${XMap.temporalityBadge(any.event_temporality)}${any.compounding_events && any.compounding_events.length ? ` <span class="tag compounding">compounding${any.event_type !== "power_outage" ? " · acuity +1" : ""}</span> ${any.compounding_events.map(esc).join(" ")}` : ""}</div>
        <div class="prov"><b>Window:</b> ${fmtShort(parse(any.window_start))} → ${fmtShort(parse(any.window_end))} UTC</div>`;
      if (any.panel) {
        html += `<div class="prov">Affected panel ≈ <b style="color:var(--ink)">${Math.round(any.panel.value).toLocaleString()}</b>
          <details><summary>how was this computed?</summary><div>${esc(any.panel.formula)}</div>
          <div>${(any.panel.caveats || []).map(esc).join("<br>")}</div>
          <div class="muted">Sources: ${(any.panel.sources || []).map(esc).join("; ")}</div></details></div>`;
      }
      const def = state.cards.get(cardId);
      if (def) html += roleContent(def);
      if (it && it.safety_message) html += `<div class="warn">${esc(it.safety_message)}</div>`;
      if (def) html += carbonBlock(def, any.panel ? any.panel.value : 0);
      if (!it) { html += `</div>`; continue; }
      html += `<details><summary>escalation (${it.escalation.length})</summary><ul>${it.escalation.map((x) => `<li>${esc(x.signs)} → <b>${esc(x.response || "")}</b>${x.emergency ? " 🚨" : ""}</li>`).join("")}</ul></details>
        <div class="prov">Evidence: ${esc(it.evidence_tier)} · <span class="tag">${esc(it.status)}</span> · <a href="/dashboard/facilities/${encodeURIComponent(fid)}?scenario=${encodeURIComponent($("scenario").value)}">full page →</a></div></div>`;
    }
    $("detail").innerHTML = html;
    $("detail").querySelectorAll(".roles button").forEach((b) => b.addEventListener("click", () => { state.role = b.dataset.role; renderFacilityDetail(); }));
    wireDetailChrome();
  }

  init().catch((e) => {
    console.error(e);
    $("status").textContent = String(e && e.message ? e.message : e);
    const side = $("side");
    if (side && !side.innerHTML.includes("Could not load")) {
      side.innerHTML = `<div class="muted">Failed to load playback: ${String(e && e.message ? e.message : e)}</div>`;
    }
  });
})();
