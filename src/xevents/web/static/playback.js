/* Playback: scrub a scenario's window and watch counties, facilities and action items change.
   Everything for the chosen scenario is loaded once, so scrubbing never waits on the network.

   Two layouts on one clock and one selection state. The layout is derived, never a mode:
   nothing selected → browse (big map + rail); a card or facility selected → focus (a reading
   column for the card, the map demoted to a 190px inset at the top of the rail). The card
   block itself is the server's cards_partial.html, fetched for (facility, card, t) — card
   text never comes from strings in this file. */
(() => {
  const COLORS = XMap.EVENT_COLORS;
  const SEV = XMap.SEVERITY_RANK;
  const TYPE_ORDER = ["hurricane_flood", "heat", "extreme_cold", "power_outage", "air_pollution", "wildfire_smoke"];
  const HOUR = 3600e3;
  const $ = (id) => document.getElementById(id);

  const state = {
    scenarios: [], facilities: null, events: [], items: [], t0: 0, t1: 0, t: 0, peak: null,
    playing: false, timer: null, selectedFacility: null, selectedEvent: null, selectedCard: null,
    role: "care_team", lastCountyPaint: new Map(), lastFacilityPaint: new Map(),
    cards: new Map(), lastBadges: new Map(), feeds: null,
    layout: "browse", browseView: null, focusFitKey: null,
    blockCache: new Map(), blockKey: null, blockSeq: 0, compact: false,
    outreachOnly: false, restoring: false, eventDetail: new Map(),
  };
  // stations (VAMC/HCC) rank before clinics, as on the old dashboard board; the classes come
  // from the profile via the page, never from this file
  const ANCHORS = ((document.body && document.body.dataset && document.body.dataset.anchors) || "").split("|").filter(Boolean);
  const isStation = (fid) => ANCHORS.some((a) => (facilityProps.get(fid)?.classification || "").startsWith(a));
  let ctx = null, facilityLayer = null, facilityById = new Map(), facilityProps = new Map();
  let badgeLayer = null;
  const cardMarkers = new Map();

  const fmt = (ms) => new Date(ms).toISOString().replace("T", " ").slice(0, 16) + "Z";
  const fmtShort = (ms) => new Date(ms).toISOString().slice(5, 16).replace("T", " ");
  const fmtHM = (ms) => new Date(ms).toISOString().slice(11, 16) + "Z";
  const isoAt = (ms) => new Date(ms).toISOString().slice(0, 19) + "Z";
  const parse = (s) => Date.parse(s);
  // times in URLs and forms are UTC; "2021-02-16T15:00" without a zone must not read as local
  const parseUtc = (s) => (s ? Date.parse(/[zZ]|[+-]\d\d:?\d\d$/.test(s) ? s : `${s}Z`) : NaN);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const num = (n) => Math.round(n || 0).toLocaleString("en-US");
  const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
  // one stable colour per card number (index = number - 1): 1 lithium, 2 antipsychotics,
  // 3 delivery, 4 heart failure, 5 insulin, 6 dialysis, 7 cold, 8 smoke.
  // Must match --card-1 … --card-8 in app.css (the server-rendered chips use those).
  const CARD_COLORS = ["#3d7fdc", "#e4572e", "#4a9d5f", "#d9a41a", "#a05cd6", "#e368a8", "#33b5c9", "#8c6d3f"];
  const cardColor = (id) => {
    const card = state.cards.get(id);
    const n = card ? card.number - 1 : [...state.cards.keys()].indexOf(id);
    return CARD_COLORS[Math.max(0, n) % CARD_COLORS.length];
  };
  const cardShort = (id) => {
    const c = state.cards.get(id);
    return c ? `${c.number} · ${c.acuity_class.replace(/_/g, " ")}` : id;
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
  const facilityPlace = (fid, withVisn = true) => {
    const p = facilityProps.get(fid);
    if (!p) return "";
    return [p.city, p.state].filter(Boolean).join(", ") + (withVisn && p.visn ? ` · VISN ${p.visn}` : "");
  };
  const activeEvents = (t) => state.events.filter((e) => e._t0 <= t && t <= e._t1);
  const activeItems = (t) => state.items.filter((i) => i.status !== "superseded" && i._t0 <= t && t <= i._t1);
  const eventByKey = (key) => state.events.find((e) => e.event_key === key);

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
      $("side").innerHTML = `<div class="empty">${msg}</div>`;
      throw new Error(msg);
    }
    $("status").textContent = "loading map and facilities…";
    const [scenarios, facilities, mapCtx, cardDefs] = await Promise.all([
      getJSON("/scenarios"), getJSON("/facilities"), XMap.create("map", { zoomControl: false }), getJSON("/cards"),
    ]);
    state.scenarios = scenarios;
    state.facilities = facilities;
    ctx = mapCtx;
    // hazard pills sit top-left, so the zoom control moves to the right
    L.control.zoom({ position: "topright" }).addTo(ctx.map);
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
    sel.addEventListener("change", async () => { await loadScenario(sel.value); writeUrl(true); });
    $("play").addEventListener("click", togglePlay);
    $("step-back").addEventListener("click", () => { pause(); step(-1); });
    $("step-fwd").addEventListener("click", () => { pause(); step(1); });
    $("expand-map").addEventListener("click", () => clearSelection());
    $("clock").addEventListener("click", editClock);
    $("now-btn").addEventListener("click", () => { pause(); setT(Date.now()); writeUrl(true); });
    $("banner").addEventListener("click", (e) => {
      if (e.target.closest && e.target.closest("#outreach")) {
        state.outreachOnly = !state.outreachOnly;
        invalidatePaint();
        render();
      }
    });
    // An Acknowledge / Mark completed in the card block changes the item on the server; mirror
    // it in the prefetched items so the outreach count and the rail agree without a reload.
    document.body.addEventListener("htmx:afterRequest", (e) => {
      const path = (e.detail && (e.detail.pathInfo?.requestPath || e.detail.requestConfig?.path)) || "";
      const m = /\/dashboard\/action-items\/(.+)\/status\?status=(\w+)/.exec(path);
      if (!m || !e.detail.successful) return;
      const id = decodeURIComponent(m[1]);
      for (const i of state.items) if (i.id === id) i.status = m[2];
      state.blockCache.clear();
      render();
    });
    window.addEventListener("popstate", () => applyUrl(readUrl()));
    window.addEventListener("keydown", (e) => {
      const tag = e.target && e.target.tagName;
      if (tag === "SELECT" || tag === "INPUT" || tag === "TEXTAREA") return;
      if (e.code === "Space" && tag !== "BUTTON" && tag !== "A" && tag !== "SUMMARY") { e.preventDefault(); togglePlay(); }
      if (e.code === "ArrowLeft") { pause(); step(-1); }
      if (e.code === "ArrowRight") { pause(); step(1); }
      if (e.code === "Escape" && closeTop()) e.preventDefault();
    });
    window.addEventListener("resize", () => {
      const compact = isCompact();
      if (compact !== state.compact) drawTimeline(true);
      if (ctx) ctx.map.invalidateSize();
    });
    initTimelineInput();
    // The URL carries the whole view: ?scenario=&at=&card=&facility=&event=
    await applyUrl(readUrl());
    writeUrl(false);
  }

  // ------------------------------------------------------------------ URL state

  function readUrl() {
    try { return new URLSearchParams(window.location.search || ""); } catch { return new URLSearchParams(); }
  }

  /* Restore a view from the URL: scenario first (a load), then time and selection. */
  async function applyUrl(q) {
    state.restoring = true;
    try {
      const want = q.get("scenario") || "live";
      const id = want === "live" || state.scenarios.some((s) => s.id === want) ? want : "live";
      if (id !== $("scenario").value || !state.events.length) {
        $("scenario").value = id;
        await loadScenario(id);
      }
      state.selectedCard = q.get("card") || null;
      state.selectedFacility = q.get("facility") || null;
      state.selectedEvent = state.selectedCard || state.selectedFacility ? null : q.get("event") || null;
      invalidatePaint();
      drawTimeline(true);
      const at = parseUtc(q.get("at"));
      setT(Number.isFinite(at) ? at : state.startAt);
      focusDetail();
    } finally {
      state.restoring = false;
    }
  }

  /* Mirror the view into the URL: replace while scrubbing (throttled), push on a selection or
     scenario change so Back steps out. Live at "now" leaves the time out, so a reload opens
     on the new now rather than an old one. */
  let urlTimer = null;
  function writeUrl(push) {
    if (state.restoring || !window.history || !window.history.replaceState) return;
    const q = new URLSearchParams();
    const id = $("scenario").value;
    q.set("scenario", id);
    const atNow = id === "live" && Math.abs(state.t - Date.now()) < HOUR / 2;
    if (!atNow) q.set("at", new Date(state.t).toISOString().slice(0, 16) + "Z");
    if (state.selectedCard) q.set("card", state.selectedCard);
    if (state.selectedFacility) q.set("facility", state.selectedFacility);
    if (state.selectedEvent) q.set("event", state.selectedEvent);
    const url = `/?${q}`;
    if (urlTimer) { clearTimeout(urlTimer); urlTimer = null; }
    if (push) {
      if (url !== window.location.pathname + window.location.search) window.history.pushState(null, "", url);
    } else {
      urlTimer = setTimeout(() => window.history.replaceState(null, "", url), 250);
    }
  }

  /* Click the clock to type a time (UTC). Enter or leaving the field applies; Esc cancels. */
  function editClock() {
    const btn = $("clock");
    const input = document.createElement("input");
    input.type = "datetime-local";
    input.className = "clock-input";
    input.value = new Date(state.t).toISOString().slice(0, 16);
    input.min = new Date(state.t0).toISOString().slice(0, 16);
    input.max = new Date(state.t1).toISOString().slice(0, 16);
    btn.hidden = true;
    btn.after(input);
    input.focus();
    let done = false;
    const finish = (apply) => {
      if (done) return;
      done = true;
      const t = parseUtc(input.value);
      input.remove();
      btn.hidden = false;
      if (apply && Number.isFinite(t)) { pause(); setT(t); writeUrl(true); }
    };
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); finish(true); }
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); finish(false); btn.focus(); }
    });
    input.addEventListener("blur", () => finish(true));
  }

  async function loadScenario(id) {
    pause();
    $("status").textContent = `loading ${id}…`;
    const live = id === "live";
    const q = live ? "" : `scenario=${encodeURIComponent(id)}&`;
    const [ev, it, feeds] = await Promise.all([
      // compact: map/timeline fields only (a Uri replay drops from ~16 MB to a few); the full
      // event is fetched when one is selected
      getJSON(`/events?${q}compact=1`),
      getJSON(`/action-items?${q}include_superseded=true`),
      live ? getJSON("/feeds").catch(() => null) : Promise.resolve(null),
    ]);
    state.feeds = feeds;
    state.events = ev.events.map((e) => ({ ...e, _t0: parse(e.onset), _t1: parse(e.expires) }));
    state.items = it.items.map((i) => ({ ...i, _t0: parse(i.window_start), _t1: parse(i.window_end) }));
    state.selectedFacility = null;
    state.selectedEvent = null;
    state.selectedCard = null;
    state.blockCache.clear();
    state.blockKey = null;
    state.focusFitKey = null;
    state.browseView = null;
    // Keep lastCountyPaint / lastFacilityPaint: they record what the layers actually show,
    // and render() clears whatever the new view does not repaint. Emptying them here left
    // the previous view's counties and facilities painted in the new one.

    // Focus the timeline on the alert window: a single long-running context event (a FEMA
    // incident period runs for weeks) should not squash the storm into a few pixels.
    const onsets = state.events.map((e) => e._t0);
    const shortEnds = state.events.filter((e) => e._t1 - e._t0 <= 14 * 24 * HOUR).map((e) => e._t1);
    if (live) {
      // Live: the last two weeks, plus whatever forecasts and lead windows reach ahead
      // (capped at a week), so you can scrub back through history and forward into forecasts.
      const now = Date.now();
      const ahead = [...state.events.map((e) => e._t1), ...state.items.map((i) => i._t1)].filter((t) => t > now);
      state.t0 = now - 14 * 24 * HOUR;
      state.t1 = clamp(ahead.length ? Math.max(...ahead) : now, now + HOUR, now + 7 * 24 * HOUR);
    } else if (!onsets.length) {
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
    state.peak = peak ? clamp(typeof peak === "number" ? peak : parse(peak), state.t0, state.t1) : null;
    state.startAt = state.peak ?? state.t0;
    $("now-btn").hidden = !live;
    fitToEvents();
    setT(state.startAt);
  }

  function fitToEvents() {
    ctx.map.invalidateSize({ animate: false });
    const fips = new Set();
    for (const e of state.events) for (const c of e.geography.county_fips) fips.add(c);
    XMap.fitCounties(ctx, fips, 0.1);
  }

  // ------------------------------------------------------------------ transport

  function setT(t) {
    state.t = clamp(t, state.t0, state.t1);
    $("clock").textContent = new Date(state.t).toISOString().replace("T", " ").slice(0, 16);
    const live = $("scenario").value === "live";
    const note = live
      ? (Math.abs(state.t - Date.now()) < HOUR ? "UTC · now" : "UTC")
      : (state.peak !== null && Math.abs(state.t - state.peak) < HOUR / 2 ? "UTC · peak hour" : "UTC");
    $("clock-note").textContent = note;
    render();
    writeUrl(false);
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

  /* One lane per product (AirNow readings grouped per pollutant), a fixed 168px label column
     so the track width is stable across scenarios, and a playhead through every lane. On a
     phone the lanes collapse to one thin row per hazard colour with no labels. */
  const TL = { maxLanes: 9 };
  const isCompact = () => !!(window.matchMedia && window.matchMedia("(max-width: 899px)").matches);

  function lanes() {
    const byName = new Map();
    for (const e of state.events) {
      const key = state.compact ? e.event_type : XMap.eventGroup(e.event_name);  // one AirNow row per pollutant, not per reading
      if (!byName.has(key)) byName.set(key, { name: key, type: e.event_type, events: [], first: e._t0 });
      const lane = byName.get(key);
      lane.events.push(e);
      lane.first = Math.min(lane.first, e._t0);
    }
    const all = [...byName.values()].sort((a, b) =>
      state.compact
        ? TYPE_ORDER.indexOf(a.type) - TYPE_ORDER.indexOf(b.type)
        : a.first - b.first || a.name.localeCompare(b.name)
    );
    if (all.length <= TL.maxLanes) return all;
    const head = all.slice(0, TL.maxLanes - 1);
    const rest = all.slice(TL.maxLanes - 1);
    head.push({
      name: `+${rest.length} more`, type: rest[0].type,
      events: rest.flatMap((l) => l.events), first: rest[0].first, grouped: true,
    });
    return head;
  }

  const pctOf = (t) => ((clamp(t, state.t0, state.t1) - state.t0) / (state.t1 - state.t0 || 1)) * 100;

  function movePlayhead() {
    const el = $("timeline");
    if (!el || !el.querySelector) return false;
    const head = el.querySelector(".tl-playhead");
    if (!head) return false;
    el.style.setProperty("--ph", String(pctOf(state.t) / 100));
    const label = head.querySelector("span");
    if (label) label.textContent = fmtHM(state.t);
    return true;
  }

  function drawTimeline(full = true) {
    const el = $("timeline");
    if (!state.events.length) {
      el.classList.add("empty");
      el.innerHTML = "No events in this window.";
      return;
    }
    if (!full && movePlayhead()) return;
    el.classList.remove("empty");
    state.compact = isCompact();
    const rows = lanes().map((lane) => {
      const color = COLORS[lane.type] || "#5b9dff";
      const bars = lane.events
        .map((e) => {
          const left = pctOf(e._t0);
          const width = Math.max(0.2, pctOf(e._t1) - left);
          const sev = SEV[e.severity] || 0;
          const on = state.selectedEvent === e.event_key ? " on" : "";
          const title = `${e.event_name} · ${e.severity}\n${fmt(e._t0)} → ${fmt(e._t1)}\n${e.geography.county_fips.length} counties`;
          return `<i class="tl-bar${on}" data-key="${esc(e.event_key)}" title="${esc(title)}"` +
            ` style="left:${left.toFixed(3)}%;width:${width.toFixed(3)}%;background:${color};opacity:${(0.5 + 0.125 * sev).toFixed(2)}"></i>`;
        })
        .join("");
      const label = state.compact
        ? (XMap.EVENT_TYPES.find((t) => t.id === lane.type)?.label || lane.name)
        : lane.name;
      return `<div class="tl-lane${lane.grouped ? " more" : ""}"><span class="lab" title="${esc(label)}">${esc(label)}</span>` +
        `<div class="tl-track">${bars}</div></div>`;
    });
    const now = Date.now();
    const nowMark = $("scenario").value === "live" && now >= state.t0 && now <= state.t1
      ? `<div class="tl-now" style="--nw:${(pctOf(now) / 100).toFixed(4)}" title="now"><span>now</span></div>` : "";
    el.innerHTML = rows.join("") + nowMark + `<div class="tl-playhead"><span>${fmtHM(state.t)}</span></div>`;
    movePlayhead();
  }

  function initTimelineInput() {
    const el = $("timeline");
    let dragging = false;
    const seek = (evt) => {
      const track = el.querySelector(".tl-track");
      if (!track) return;
      const rect = track.getBoundingClientRect();
      const frac = clamp((evt.clientX - rect.left) / (rect.width || 1), 0, 1);
      setT(state.t0 + frac * (state.t1 - state.t0));
    };
    el.addEventListener("pointerdown", (evt) => {
      if (!evt.target.closest || !evt.target.closest(".tl-track")) return;
      pause();
      dragging = true;
      const key = evt.target && evt.target.dataset ? evt.target.dataset.key : null;
      if (key) selectEvent(key);
      seek(evt);
    });
    window.addEventListener("pointermove", (evt) => { if (dragging) seek(evt); });
    window.addEventListener("pointerup", () => { dragging = false; });
  }

  // ------------------------------------------------------------------ map + panel

  function render() {
    const evs = activeEvents(state.t);
    const allItems = activeItems(state.t);
    // the outreach chip narrows the rail and the badges to unacknowledged top-acuity items
    const items = state.outreachOnly ? allItems.filter(isOutreach) : allItems;

    const paint = new Map();
    for (const e of evs) {
      for (const c of e.geography.county_fips) {
        const cur = paint.get(c), sev = SEV[e.severity] || 0;
        const better = !cur || sev > cur.sev || (sev === cur.sev && TYPE_ORDER.indexOf(e.event_type) < TYPE_ORDER.indexOf(cur.type));
        if (better) {
          paint.set(c, {
            color: COLORS[e.event_type] || "#5b9dff",
            opacity: XMap.eventOpacity(e, sev),
            sev,
            type: e.event_type,
          });
        }
      }
    }
    if (state.selectedEvent) {
      const sel = eventByKey(state.selectedEvent);
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
    if (ctx.stateLayer) ctx.stateLayer.bringToFront();

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
    const cards = cardsAt(items);
    renderBanner(evs, cards, items, allItems);
    renderHazards(evs);
    applyLayout(items);
    renderSide(evs, items, byFacility, cards);
  }

  /* The layout is a function of the selection. Swapping it is instant (no animated grid
     change — that would reflow Leaflet mid-transition); the map is told its new size and
     fitted to what it should now show. */
  function layoutOf() {
    return state.selectedCard || state.selectedFacility ? "focus" : "browse";
  }

  function applyLayout(items) {
    const want = layoutOf();
    const body = $("pb-body");
    if (want !== state.layout) {
      if (want === "focus" && ctx) state.browseView = { center: ctx.map.getCenter(), zoom: ctx.map.getZoom() };
      state.layout = want;
      body.className = want;
      if (ctx) ctx.map.invalidateSize({ animate: false });
      if (want === "browse") {
        state.focusFitKey = null;
        state.blockKey = null;
        if (ctx && state.browseView) ctx.map.setView(state.browseView.center, state.browseView.zoom, { animate: false });
      }
    }
    if (want === "focus") fitFocus(items);
  }

  /* Scope the inset to the selection's footprint: the counties of the events behind the
     selected card's (or facility's) items. Refit only when the selection changes, so the
     inset does not jump on every tick. */
  function footprint(items) {
    const mine = items.filter(
      (i) => (!state.selectedCard || i.card_id === state.selectedCard) &&
        (!state.selectedFacility || i.facility_id === state.selectedFacility)
    );
    const fips = new Set(), states = new Set();
    for (const key of new Set(mine.map((i) => i.event_key))) {
      const e = eventByKey(key);
      if (!e) continue;
      for (const c of e.geography.county_fips) fips.add(c);
      for (const s of e.geography.states || []) states.add(s);
    }
    return { fips, states, facilities: new Set(mine.map((i) => i.facility_id)) };
  }

  function fitFocus(items) {
    const fp = footprint(items);
    const st = [...fp.states].sort();
    $("inset-label").textContent = fp.fips.size
      ? `${plural(fp.fips.size, "county", "counties")}${st.length ? " · " + (st.length > 4 ? st.slice(0, 4).join(", ") + "…" : st.join(", ")) : ""}`
      : "not firing now";
    const key = `${state.selectedCard || ""}|${state.selectedFacility || ""}`;
    if (key === state.focusFitKey || !ctx) return;
    state.focusFitKey = key;
    ctx.map.invalidateSize({ animate: false });
    if (fp.fips.size) XMap.fitCounties(ctx, fp.fips, 0.05);
    else if (state.selectedFacility && facilityById.get(state.selectedFacility)) {
      ctx.map.setView(facilityById.get(state.selectedFacility).getLatLng(), 7, { animate: false });
    }
  }

  function renderBanner(evs, cards, items, allItems) {
    const live = $("scenario").value === "live";
    const pill = $("mode-pill");
    const facs = new Set(items.map((i) => i.facility_id)).size;
    const counts = outreachChip(allItems) +
      `<span class="hi">${plural(cards.length, "card", "cards")} firing</span> at ${plural(facs, "facility", "facilities")} · ${plural(evs.length, "event", "events")} active`;
    if (!live) {
      const s = state.scenarios.find((x) => x.id === $("scenario").value);
      pill.textContent = "Replay";
      pill.className = "pill";
      $("banner").classList.remove("stale");
      $("banner-text").innerHTML = `<span class="hi">${esc(s ? s.id : "")}</span> · window ${fmt(state.t0).slice(0, 10)} → ${fmt(state.t1).slice(0, 10)} · ${counts}`;
      return;
    }
    // Live: per-feed freshness, and the all-clear caveat — always, stale or not.
    const doc = state.feeds;
    const staleH = doc ? doc.stale_after_hours : 6;
    const runs = (doc && doc.runs) || [];
    let anyStale = !runs.length;
    const feedText = runs.length
      ? runs.map((r) => {
          const age = (Date.now() - parse(r.run_at)) / HOUR;
          const stale = r.status === "ok" && age > staleH;
          if (stale || r.status === "failed") anyStale = true;
          const what = r.status === "ok" ? `<span class="hi">${r.events}</span> events` : r.status === "failed" ? "<b>failed</b>" : "off";
          return `<span title="${esc(r.detail || "")}">${esc(r.provider)}: ${what} (${fmtShort(parse(r.run_at))}Z)${stale ? " <b>(stale)</b>" : ""}</span>`;
        }).join(" · ")
      : "no live events ingested yet";
    pill.textContent = "Live";
    pill.className = anyStale ? "pill stale" : "pill";
    $("banner").classList.toggle("stale", anyStale);
    $("banner-text").innerHTML = `${counts} · ${feedText} · absence of items is not an all-clear when a feed is stale.`;
  }

  /* Outreach queue: care-team items in the top two acuity classes nobody has acknowledged
     yet (the old dashboard's banner). Class names come from the items themselves. */
  function isOutreach(i) {
    return i.acuity_rank <= 1 && i.status === "issued" && i.role === "care_team";
  }

  function outreachChip(allItems) {
    const open = allItems.filter(isOutreach);
    if (!open.length && !state.outreachOnly) return "";
    const classes = [...new Set(open.map((i) => i.acuity_class.replace(/_/g, " ")))].join(" / ");
    const label = state.outreachOnly
      ? `showing outreach only (${open.length}) · show all`
      : `Outreach: ${open.length} unacknowledged high-acuity${classes ? ` (${esc(classes)})` : ""}`;
    return `<button type="button" id="outreach" class="chip warn outreach${state.outreachOnly ? " on" : ""}" title="unacknowledged items in the top two acuity classes — click to ${state.outreachOnly ? "show everything" : "show only these"}">${label}</button> `;
  }

  function renderHazards(evs) {
    const byType = new Map();
    for (const e of evs) {
      const s = byType.get(e.event_type) || new Set();
      for (const c of e.geography.county_fips) s.add(c);
      byType.set(e.event_type, s);
    }
    $("hazards").innerHTML = XMap.EVENT_TYPES.filter((t) => byType.has(t.id))
      .map((t) => `<span><i style="background:${t.color}"></i>${esc(t.label)} <b>${byType.get(t.id).size}</b></span>`)
      .join("");
  }

  function cardsAt(items) {
    const byCard = new Map();
    for (const i of items) {
      const c = byCard.get(i.card_id) || {
        id: i.card_id, title: i.card_title, acuity: i.acuity_rank, acuityClass: i.acuity_class,
        facilities: new Set(), events: new Set(), eventKeys: new Set(), panel: 0, types: new Set(),
      };
      c.facilities.add(i.facility_id);
      c.events.add(i.event_name);
      c.eventKeys.add(i.event_key);
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
      // chips are colour-only on the map, so the tooltip names every card
      const titles = ids.map((id) => `Card ${state.cards.get(id)?.number || ""} · ${state.cards.get(id)?.title || id}`);
      marker.bindTooltip(
        `<b>${esc(facilityProps.get(fid)?.name || fid)}</b><br>${esc(facilityPlace(fid))}<br>${titles.map(esc).join("<br>")}`,
        { direction: "top" }
      );
      marker.on("click", () => selectFacility(fid));
      marker.addTo(badgeLayer);
      cardMarkers.set(fid, marker);
    });
  }

  function renderSide(evs, items, byFacility, cards) {
    renderLegend(cards);
    if (state.layout === "focus") renderCardFocus(evs, items, cards);
    else renderBrowse(evs, items, byFacility, cards);
  }

  // ------------------------------------------------------------------ browse layout

  function renderBrowse(evs, items, byFacility, cards) {
    const board = [...byFacility.entries()].map(([fid, its]) => {
      const top = its.reduce((b, i) => (i.acuity_rank < b.acuity_rank ? i : b), its[0]);
      const panel = Math.max(...its.map((i) => i.panel || 0));
      const sev = Math.max(...its.map((i) => SEV[i.event_severity] || 0));
      const score = Math.max(...its.map((i) => i.rank_score || 0));
      const p = facilityProps.get(fid);
      return { fid, name: p ? p.name : fid, cards: new Set(its.map((i) => i.card_id)).size, top, panel, sev, score, station: isStation(fid) };
    }).sort((a, b) =>
      // acuity class, then severity × rank score (panel, or outage % × emPOWER), stations
      // before clinics, then name — the order the dashboard board used
      a.top.acuity_rank - b.top.acuity_rank || b.sev * b.score - a.sev * a.score ||
      Number(b.station) - Number(a.station) || a.name.localeCompare(b.name));

    const evList = [...evs].sort((a, b) => (SEV[b.severity] || 0) - (SEV[a.severity] || 0) || a.event_name.localeCompare(b.event_name));

    const html = [
      `<div id="detail"></div>`,
      `<div class="side-h sticky"><span class="section-h">Cards firing now</span><span class="n">at ${fmtHM(state.t)}</span></div>`,
      cards.length
        ? `<div class="rank-list">${cards.map((c) => {
            const def = state.cards.get(c.id);
            return `<button type="button" class="rank-row card-row" data-card="${esc(c.id)}" style="--card-color:${cardColor(c.id)}">
              <span class="r1"><i class="swatch" style="background:${cardColor(c.id)}"></i><b>Card ${def ? def.number : ""} · ${esc(c.title)}</b><span class="acu">${esc(c.acuityClass)}</span></span>
              <span class="r2"><span><b>${c.facilities.size}</b> ${c.facilities.size === 1 ? "facility" : "facilities"}</span><span>largest panel <b>${num(c.panel)}</b></span></span>
              <span class="r3">triggered by ${esc(XMap.summarizeNames(c.events))}</span></button>`;
          }).join("")}</div>`
        : `<div class="empty">No cards fire at this time.</div>`,

      `<div class="side-h"><span class="section-h">Facilities by acuity</span><span class="n">${board.length}</span></div>`,
      board.length
        ? `<div class="rank-list">${board.slice(0, 30).map((b) => `<button type="button" class="rank-row" data-fid="${esc(b.fid)}">
            <span class="r1"><span class="name">${esc(b.name)}</span><span class="fig">${num(b.panel)}</span></span>
            <span class="r2"><span>${esc(facilityPlace(b.fid))} · ${plural(b.cards, "card", "cards")}</span><span class="right">${esc(b.top.acuity_class)}</span></span></button>`).join("")}</div>`
        : `<div class="empty">No action items at this time.</div>`,
      board.length > 30 ? `<div class="more">… ${board.length - 30} more</div>` : "",

      `<div class="side-h"><span class="section-h">Events now · ${evList.length}</span></div>`,
      evList.length
        ? `<div class="rank-list">${evList.slice(0, 25).map((e) => {
            const on = state.selectedEvent === e.event_key ? " on" : "";
            return `<button type="button" class="rank-row${on}" data-event="${esc(e.event_key)}">
              <span class="r1" style="flex-wrap:wrap"><span class="name">${esc(e.event_name)}</span>${XMap.temporalityBadge(e.temporality)}<span class="right"><span class="tag sev-${SEV[e.severity] || 0}">${esc(e.severity)}</span></span></span>
              <span class="r2"><span>${esc(placeOf(e))}</span><span class="right num">${plural(e.geography.county_fips.length, "county", "counties")}</span></span></button>`;
          }).join("")}</div>`
        : `<div class="empty">No events active at this time.</div>`,
      evList.length > 25 ? `<div class="more">… ${evList.length - 25} more</div>` : "",
      `<div class="more"><a href="/dashboard/events?${new URLSearchParams({ scenario: $("scenario").value, at: isoAt(state.t), window: "all" })}">all events in this window →</a></div>`,
    ].join("");
    const side = $("side");
    side.innerHTML = html;
    side.querySelectorAll("[data-fid]").forEach((r) => r.addEventListener("click", () => selectFacility(r.dataset.fid)));
    side.querySelectorAll("[data-event]").forEach((r) => r.addEventListener("click", () => selectEvent(r.dataset.event)));
    side.querySelectorAll("[data-card]").forEach((r) => r.addEventListener("click", () => selectCard(r.dataset.card)));
    if (state.selectedEvent) renderEventDetail();
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
      ? `<div class="hdr">Cards firing — click to isolate</div>` +
        cards
          .map((c) => {
            const dim = state.selectedCard && state.selectedCard !== c.id ? "opacity:.45;" : "";
            return `<div data-legend="${esc(c.id)}" style="${dim}" title="${esc(c.title)}"><i class="card-chip" style="background:${cardColor(c.id)}"></i>
              <span>${esc(cardShort(c.id))}</span><span>${c.facilities.size}</span></div>`;
          })
          .join("")
      : `<div class="hdr">Cards firing</div><div class="muted" style="padding:2px 0">none firing now</div>`;
    const facilityKeys =
      `<span class="rule"></span><div class="hdr">Facilities</div>` +
      `<div><i class="dot" style="background:#fff"></i><span>card firing</span><span>size ∝ panel</span></div>` +
      `<div><i class="dot" style="background:var(--idle)"></i><span class="muted">grey dot = facility with no card firing</span></div>`;
    el.innerHTML = cardRows + facilityKeys + `<span class="rule"></span>` + XMap.legendHtml(countyCounts, { onlyActive: true });
    el.querySelectorAll("[data-legend]").forEach((r) =>
      r.addEventListener("click", () => selectCard(r.dataset.legend))
    );
  }

  // ------------------------------------------------------------------ selection chrome

  /* Selections nest: a card can hold a facility drill-down inside it. Every level therefore
     needs a way back to the level above, not only a way out — a breadcrumb, a close button,
     Escape and (in focus) "expand map". */
  function selectionCrumbs() {
    const out = [{ key: "all", label: "Cards firing now" }];
    if (state.selectedCard) out.push({ key: "card", label: `Card ${cardShort(state.selectedCard)}` });
    if (state.selectedEvent) {
      const e = eventByKey(state.selectedEvent);
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
        const label = c.label.length > 48 ? c.label.slice(0, 47) + "…" : c.label;
        return i === crumbs.length - 1
          ? `<span class="crumb on">${esc(label)}</span>`
          : `<a href="#" class="crumb" data-crumb="${c.key}">${esc(label)}</a>`;
      })
      .join('<span class="sep">/</span>');
    return `${trail}<button class="closebtn" data-close="1" title="Close (Esc)" aria-label="Close">×</button>`;
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
    drawTimeline(true);
    render();
    focusDetail();
    writeUrl(true);
  }

  /* Close one level: the facility drill-down first, then the card or event filter. */
  function closeTop() {
    if (state.selectedFacility) state.selectedFacility = null;
    else if (state.selectedEvent) state.selectedEvent = null;
    else if (state.selectedCard) state.selectedCard = null;
    else return false;
    invalidatePaint();
    drawTimeline(true);
    render();
    focusDetail();
    writeUrl(true);
    return true;
  }

  function goToCrumb(key) {
    if (key === "all") return clearSelection();
    state.selectedFacility = null;
    invalidatePaint();
    render();
    focusDetail();
    writeUrl(true);
  }

  /* Called after any selection chrome writes its markup. */
  function wireDetailChrome(el) {
    if (!el || !el.querySelectorAll) return;
    el.querySelectorAll("[data-crumb]").forEach((a) =>
      a.addEventListener("click", (e) => {
        if (e && e.preventDefault) e.preventDefault();
        goToCrumb(a.dataset.crumb);
      })
    );
    el.querySelectorAll("[data-close]").forEach((b) => b.addEventListener("click", () => closeTop()));
  }

  function focusDetail() {
    for (const id of ["side", "reading"]) {
      const el = $(id);
      if (el && typeof el.scrollTop === "number") el.scrollTop = 0;
    }
  }

  // ------------------------------------------------------------------ focus layout

  function renderCardFocus(evs, items, cards) {
    const crumbs = $("crumbs");
    crumbs.innerHTML = detailHeader();
    wireDetailChrome(crumbs);
    if (state.selectedCard) renderCardDetail(items, cards);
    else renderFacilityDetail(items);
  }

  /* Rail for a selected card: where it fires (bar ∝ panel, in the card's colour) and what
     triggered it. The reading column shows the card block for the selected facility, or for
     the facility with the largest panel when none is picked. */
  function renderCardDetail(items, cards) {
    const id = state.selectedCard;
    const color = cardColor(id);
    const mine = items.filter((i) => i.card_id === id);
    const byFac = new Map();
    for (const i of mine) byFac.set(i.facility_id, Math.max(byFac.get(i.facility_id) || 0, i.panel || 0));
    const facs = [...byFac.entries()].map(([fid, panel]) => ({ fid, panel })).sort((a, b) => b.panel - a.panel);
    const maxPanel = facs.length ? Math.max(1, facs[0].panel) : 1;
    const evKeys = [...new Set(mine.map((i) => i.event_key))];
    const trig = evKeys.map(eventByKey).filter(Boolean)
      .sort((a, b) => (Number(b.metrics?.outage_pct) || 0) - (Number(a.metrics?.outage_pct) || 0) || (SEV[b.severity] || 0) - (SEV[a.severity] || 0));

    $("side").innerHTML = [
      `<div class="side-h"><span class="section-h">Firing at</span><span class="n">${plural(facs.length, "facility", "facilities")}</span></div>`,
      facs.length
        ? `<div class="rank-list" style="--card-color:${color}">${facs.slice(0, 40).map((f) => {
            const on = state.selectedFacility === f.fid ? " on" : "";
            return `<button type="button" class="rank-row${on}" data-fid="${esc(f.fid)}">
              <span class="r1"><span class="name">${esc(facilityProps.get(f.fid)?.name || f.fid)}</span><span class="fig">${num(f.panel)}</span></span>
              <span class="bar" style="display:block"><i style="width:${((f.panel / maxPanel) * 100).toFixed(1)}%"></i></span>
              <span class="r2"><span>${esc(facilityPlace(f.fid, false))}</span></span></button>`;
          }).join("")}</div>${facs.length > 40 ? `<div class="more">… ${facs.length - 40} more</div>` : ""}`
        : `<div class="empty">This card is not firing at ${fmt(state.t)}.</div>`,
      `<div class="side-h"><span class="section-h">Triggered by</span><span class="n">${plural(trig.length, "event", "events")}</span></div>`,
      trig.length
        ? `<div class="rank-list">${trig.slice(0, 25).map(triggerRow).join("")}</div>${trig.length > 25 ? `<div class="more">… ${trig.length - 25} more</div>` : ""}`
        : `<div class="empty">No triggering events at this time.</div>`,
    ].join("");
    wireRail();

    const fid = state.selectedFacility && byFac.has(state.selectedFacility) ? state.selectedFacility : facs[0]?.fid;
    const def = state.cards.get(id);
    if (!fid) {
      $("reading").innerHTML = `<div class="loading">${esc(def ? def.title : id)} is not firing at ${fmt(state.t)}. Scrub the timeline, or go back to <a href="#" data-crumb="all">cards firing now</a>.</div>`;
      wireDetailChrome($("reading"));
      state.blockKey = null;
      return;
    }
    const why = state.selectedFacility === fid
      ? ""
      : `Shown for <b style="color:var(--ink)">${esc(facilityProps.get(fid)?.name || fid)}</b> — the largest panel of ${plural(facs.length, "facility", "facilities")} firing this card. Pick another in the rail.`;
    loadCardBlock(fid, id, why);
  }

  function triggerRow(e) {
    const m = e.metrics || {};
    const detail = m.outage_pct !== undefined
      ? `${m.outage_pct}% of customers out${m.poll_streak ? ` · ${plural(Number(m.poll_streak), "poll", "polls")}` : ""}`
      : `${e.severity} · ${plural(e.geography.county_fips.length, "county", "counties")}`;
    return `<button type="button" class="rank-row" data-event="${esc(e.event_key)}" title="${esc(fmt(e._t0))} → ${esc(fmt(e._t1))}">
      <span class="r1"><span class="name">${esc(e.event_name)}</span></span>
      <span class="r2" style="margin-top:5px; gap:7px">${XMap.temporalityBadge(e.temporality)}<span>${esc(detail)}</span></span>
      <span class="r2"><span>${esc(placeOf(e))}</span></span></button>`;
  }

  function wireRail() {
    const side = $("side");
    side.querySelectorAll("[data-fid]").forEach((r) => r.addEventListener("click", () => selectFacility(r.dataset.fid)));
    side.querySelectorAll("[data-event]").forEach((r) => r.addEventListener("click", () => selectEvent(r.dataset.event)));
    side.querySelectorAll("[data-card]").forEach((r) => r.addEventListener("click", () => selectCard(r.dataset.card, true)));
  }

  /* Facility selected without a card: the reading column holds every card firing there. */
  function renderFacilityDetail(items) {
    const fid = state.selectedFacility;
    const mine = items.filter((i) => i.facility_id === fid);
    const cards = cardsAt(mine);
    const evKeys = [...new Set(mine.map((i) => i.event_key))];
    const trig = evKeys.map(eventByKey).filter(Boolean);
    $("side").innerHTML = [
      `<div class="side-h"><span class="section-h">Cards here</span><span class="n">${cards.length}</span></div>`,
      cards.length
        ? `<div class="rank-list">${cards.map((c) => `<button type="button" class="rank-row card-row" data-card="${esc(c.id)}" style="--card-color:${cardColor(c.id)}">
            <span class="r1"><i class="swatch" style="background:${cardColor(c.id)}"></i><b>${esc(c.title)}</b><span class="acu">${esc(c.acuityClass)}</span></span>
            <span class="r2"><span>panel <b>${num(c.panel)}</b></span></span></button>`).join("")}</div>`
        : `<div class="empty">No action items active here at ${fmt(state.t)}.</div>`,
      `<div class="side-h"><span class="section-h">Triggered by</span><span class="n">${plural(trig.length, "event", "events")}</span></div>`,
      trig.length ? `<div class="rank-list">${trig.slice(0, 25).map(triggerRow).join("")}</div>` : `<div class="empty">No triggering events at this time.</div>`,
    ].join("");
    wireRail();
    const p = facilityProps.get(fid) || {};
    const head = `<h1 class="fac-h">${esc(p.name || fid)}</h1><div class="fac-sub">${esc(p.classification || "")} · ${esc(facilityPlace(fid))} · county ${esc(p.county_fips || "?")} · as of ${fmt(state.t)} · <a href="/demo/patient-view?${new URLSearchParams({ facility: fid, scenario: $("scenario").value, at: isoAt(state.t) })}" target="_blank" rel="noopener">patient view ↗</a></div>`;
    if (!mine.length) {
      $("reading").innerHTML = head + `<div class="loading">No cards fire here at ${fmt(state.t)}.</div>`;
      state.blockKey = null;
      return;
    }
    loadCardBlock(fid, null, "", head);
  }

  /* The card block is the server's cards_partial.html for (facility, card, t, audience). The
     key includes the ids of the items active at t, so scrubbing refetches only when the
     underlying items change, and each result is cached. */
  async function loadCardBlock(fid, cardId, why, head = "") {
    const ids = activeItems(state.t)
      .filter((i) => i.facility_id === fid && (!cardId || i.card_id === cardId))
      .map((i) => i.id).sort().join(",");
    const key = `${fid}|${cardId || ""}|${state.role}|${ids}`;
    const prefix = head + (why ? `<p class="cb-prov sans" style="margin:0 0 18px">${why}</p>` : "");
    if (key === state.blockKey) {
      // same block; only the "why" line or header can change
      const pre = $("reading").querySelector("[data-block-prefix]");
      if (pre) pre.innerHTML = prefix;
      return;
    }
    state.blockKey = key;
    const seq = ++state.blockSeq;
    const reading = $("reading");
    const fill = (html) => {
      reading.innerHTML = `<div data-block-prefix>${prefix}</div><div data-block>${html}</div>`;
      if (window.htmx) window.htmx.process(reading);
      reading.querySelectorAll("[data-role]").forEach((a) =>
        a.addEventListener("click", (e) => {
          e.preventDefault();
          state.role = a.dataset.role;
          state.blockKey = null;
          render();
        })
      );
    };
    if (state.blockCache.has(key)) { fill(state.blockCache.get(key)); return; }
    if (!reading.querySelector("[data-block]")) reading.innerHTML = `<div class="loading">Loading card…</div>`;
    const q = new URLSearchParams({ scenario: $("scenario").value, at: isoAt(state.t), role: state.role, embed: "1" });
    if (cardId) q.set("card", cardId);
    try {
      const r = await fetch(`/dashboard/facilities/${encodeURIComponent(fid)}/cards?${q}`);
      if (!r.ok) throw new Error(`card block → ${r.status}`);
      const html = await r.text();
      state.blockCache.set(key, html);
      if (seq === state.blockSeq) fill(html);
    } catch (err) {
      if (seq === state.blockSeq) reading.innerHTML = `<div class="loading">Could not load the card: ${esc(err.message)}</div>`;
      state.blockKey = null;
    }
  }

  /* Event selected (browse): a compact detail above the rail lists; the map highlights it. */
  function renderEventDetail() {
    const e = eventByKey(state.selectedEvent);
    if (!e) return;
    // The list carries compact events; the full one (urgency, notes, outage counts,
    // attribution) comes from /events/detail on first selection and is kept.
    const key = e.event_key;
    if (!state.eventDetail.has(key)) {
      state.eventDetail.set(key, null);
      getJSON(`/events/detail?key=${encodeURIComponent(key)}`)
        .then((doc) => { state.eventDetail.set(key, doc); if (state.selectedEvent === key) renderEventDetail(); })
        .catch(() => state.eventDetail.delete(key));
    }
    const d = state.eventDetail.get(key) || e;
    const mine = state.items.filter((i) => i.event_key === e.event_key);
    const facs = new Set(mine.map((i) => i.facility_id));
    const byCard = new Map();
    for (const i of mine) {
      const c = byCard.get(i.card_id) || { title: i.card_title, facilities: new Set() };
      c.facilities.add(i.facility_id);
      byCard.set(i.card_id, c);
    }
    const cardList = [...byCard.entries()]
      .map(([id, c]) => `<li><span class="swatch" style="background:${cardColor(id)}"></span> <a href="#" data-card="${esc(id)}">${esc(c.title)}</a> — ${plural(c.facilities.size, "facility", "facilities")}</li>`)
      .join("");
    const el = $("detail");
    el.innerHTML = `<nav class="crumbs">${detailHeader()}</nav><div class="detail-card">
      <div class="chips"><span class="tag sev-${SEV[e.severity] || 0}">${esc(e.severity)}</span> ${XMap.temporalityBadge(e.temporality)}</div>
      <h3>${esc(e.event_name)}</h3>
      <div class="cb-prov" style="margin-top:4px">${esc(e.event_key)}</div>
      <div class="prov"><b>Where:</b> ${esc(placeOf(e))}${e.geography.states?.length ? ` (${esc(e.geography.states.join(", "))})` : ""}</div>
      <div class="prov"><b>When:</b> ${fmt(e._t0)} → ${fmt(e._t1)} (${Math.round((e._t1 - e._t0) / 36e5)} h)</div>
      ${d.urgency ? `<div class="prov">Urgency ${esc(d.urgency)} · certainty ${esc(d.certainty)} · source ${esc(d.source)}</div>` : `<div class="prov">source ${esc(e.source)} · loading details…</div>`}
      ${d.geography.note ? `<div class="prov">${esc(d.geography.note)}</div>` : ""}
      ${d.metrics && d.metrics.customers_out !== undefined ? `<div class="prov"><b>Outage:</b> ${Number(d.metrics.customers_out).toLocaleString()} of ${Number(d.metrics.county_customers).toLocaleString()} customers out (${esc(d.metrics.outage_pct)}%)</div>` : ""}
      ${d.attribution ? `<div class="prov">${esc(d.attribution)} ${(d.caveats || []).map(esc).join(" ")}</div>` : ""}
      <div style="margin-top:8px; font-size:12.5px"><b>Cards fired:</b> ${byCard.size ? `${mine.length} action items at ${plural(facs.size, "facility", "facilities")}` : "none — no card trigger matches this event"}</div>
      ${cardList ? `<ul>${cardList}</ul>` : ""}
      <div class="prov" style="margin-top:8px"><a href="/dashboard/events/${encodeURIComponent(e.event_key)}?scenario=${encodeURIComponent($("scenario").value)}">open full event page →</a></div>
    </div>`;
    el.querySelectorAll("[data-card]").forEach((a) => a.addEventListener("click", (ev) => { ev.preventDefault(); selectCard(a.dataset.card); }));
    wireDetailChrome(el);
  }

  // ------------------------------------------------------------------ selection

  function selectCard(id, keepFacility = false) {
    state.selectedCard = state.selectedCard === id && !keepFacility ? null : id;
    state.selectedEvent = null;
    if (!keepFacility) state.selectedFacility = null;
    invalidatePaint();  // force a repaint: colours change with the filter
    drawTimeline(true);
    render();
    focusDetail();
    writeUrl(true);
  }

  function selectEvent(key) {
    state.selectedEvent = state.selectedEvent === key ? null : key;
    state.selectedFacility = null;
    state.selectedCard = null;
    invalidatePaint();
    drawTimeline(true);
    render();
    focusDetail();
    writeUrl(true);
  }

  /* Inside a card, a facility nests under it (breadcrumb gains a level); otherwise it opens
     the facility on its own. */
  function selectFacility(fid) {
    state.selectedFacility = state.selectedFacility === fid ? null : fid;
    state.selectedEvent = null;
    const firesCard = activeItems(state.t).some((i) => i.facility_id === fid && i.card_id === state.selectedCard);
    if (state.selectedCard && state.selectedFacility && !firesCard) state.selectedCard = null;
    invalidatePaint();
    render();
    focusDetail();
    writeUrl(true);
  }

  init().catch((e) => {
    console.error(e);
    $("status").textContent = String(e && e.message ? e.message : e);
    const side = $("side");
    if (side && !side.innerHTML.includes("Could not load")) {
      side.innerHTML = `<div class="empty">Failed to load playback: ${esc(String(e && e.message ? e.message : e))}</div>`;
    }
  });
})();
