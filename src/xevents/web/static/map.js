/* Shared, key-free base map: we draw the county polygons we already serve at
   /reference/counties instead of pulling raster tiles from a third party. That keeps the
   demo working offline, behind a firewall and when hosted, with no API key anywhere. */
window.XMap = (() => {
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

  return { create, paintCounties, counties };
})();
