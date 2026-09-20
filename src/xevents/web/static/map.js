/* Shared, key-free base map: we draw the county polygons we already serve at
   /reference/counties instead of pulling raster tiles from a third party. That keeps the
   demo working offline, behind a firewall and when hosted, with no API key anywhere. */
window.XMap = (() => {
  /* One palette for every map. Smoke used to be a muted brown that read as "no event" at
     low opacity, so it is now a clearly warmer tan, and the opacity floor is high enough
     that any shaded county is obviously shaded. */
  const EVENT_TYPES = [
    { id: "heat", color: "#e4572e", label: "heat" },
    { id: "hurricane_flood", color: "#3d7fdc", label: "hurricane / flood" },
    { id: "wildfire_smoke", color: "#b5894e", label: "wildfire smoke" },
    { id: "air_pollution", color: "#a05cd6", label: "air pollution" },
    { id: "power_outage", color: "#d9a41a", label: "power outage" },
  ];
  const EVENT_COLORS = Object.fromEntries(EVENT_TYPES.map((t) => [t.id, t.color]));
  const SEVERITY_RANK = { Extreme: 4, Severe: 3, Moderate: 2, Minor: 1, Unknown: 0 };
  /* Shading deepens with CAP severity; the floor keeps a minor alert visible. */
  const fillOpacity = (severityRank) => 0.34 + 0.12 * (severityRank || 0);
  const IDLE_COLOR = "#121a23";

  const BASE_STYLE = { weight: 0.35, color: "#243040", fillColor: "#121a23", fillOpacity: 1 };
  let countiesPromise = null;

  function counties() {
    if (!countiesPromise) countiesPromise = fetch("/reference/counties").then((r) => r.json());
    return countiesPromise;
  }

  async function create(elementId, opts = {}) {
    const map = L.map(elementId, {
      zoomControl: true,
      attributionControl: false,
      preferCanvas: true,
      ...opts,
    }).setView(opts.center || [38.5, -96], opts.zoom || 4);
    const geo = await counties();
    const layer = L.geoJSON(geo, { style: () => ({ ...BASE_STYLE }), interactive: false }).addTo(map);
    const byFips = new Map();
    layer.eachLayer((l) => byFips.set(l.feature.id, l));
    L.control.attribution({ prefix: false })
      .addAttribution("County boundaries: US Census Bureau (1:5m)")
      .addTo(map);
    return { map, countyLayer: layer, byFips, baseStyle: BASE_STYLE };
  }

  /* Paint a subset of counties; everything else returns to the base style. */
  function paintCounties(ctx, colorByFips) {
    ctx.byFips.forEach((layer, fips) => {
      const hit = colorByFips.get(fips);
      layer.setStyle(hit ? { ...ctx.baseStyle, fillColor: hit.color, fillOpacity: hit.opacity ?? 0.55, color: hit.color, weight: 0.5 } : ctx.baseStyle);
    });
  }

  /* Shared legend markup so the dashboard and playback explain the map the same way. */
  function legendHtml(countsByType, options = {}) {
    const rows = EVENT_TYPES.filter((t) => !options.onlyActive || (countsByType || {})[t.id])
      .map((t) => {
        const n = (countsByType || {})[t.id];
        return `<div><i style="background:${t.color}"></i><span>${t.label}</span>` +
          `<span class="muted">${n === undefined ? "" : n}</span></div>`;
      })
      .join("");
    return `<div class="hdr">Counties — active event</div>${rows}` +
      `<div><i style="background:${IDLE_COLOR};border-color:#2a3440"></i><span class="muted">no active event</span><span></span></div>` +
      `<div class="note">Shading deepens with severity.</div>`;
  }

  return { create, paintCounties, counties, legendHtml, EVENT_TYPES, EVENT_COLORS, SEVERITY_RANK, fillOpacity, IDLE_COLOR };
})();
