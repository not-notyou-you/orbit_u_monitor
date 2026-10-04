// web/js/maps.js — peta Leaflet di dalam screen (INTERFACE §1: Esri World Street Map
// + poligon kecamatan AOI). Tile diberi filter fosfor lewat CSS (main.css), data tidak.
'use strict';

const Maps = (() => {
  const TILE_URL = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}';
  const TILE_ATTR = 'Tiles &copy; Esri &mdash; Esri, HERE, Garmin, USGS, Intermap, NRCan, METI, OSM';
  let regionsCache = null;

  function available() { return typeof window.L !== 'undefined'; }

  function create(el, opts) {
    if (!available()) {
      el.innerHTML = UI.emptyHTML('PETA TIDAK TERSEDIA (LEAFLET TIDAK DAPAT DIMUAT — PERIKSA KONEKSI INTERNET)');
      return null;
    }
    const map = L.map(el, Object.assign({ zoomControl: true, attributionControl: true, scrollWheelZoom: false, preferCanvas: false }, opts || {}));
    L.tileLayer(TILE_URL, { maxZoom: 18, attribution: TILE_ATTR }).addTo(map);
    map.setView([-6.75, 106.2], 10);
    // Ukuran kontainer bisa berubah setelah fragmen dirender.
    setTimeout(() => map.invalidateSize(), 50);
    return map;
  }

  // Pola arsir SVG untuk kategori BMKG tertinggi (warna bukan satu-satunya pembawa makna).
  function ensurePatterns(map) {
    const svg = map.getPanes().overlayPane.querySelector('svg');
    if (!svg || svg.querySelector('#hatch-a')) return;
    const ns = 'http://www.w3.org/2000/svg';
    const defs = document.createElementNS(ns, 'defs');
    defs.innerHTML =
      '<pattern id="hatch-a" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">' +
        '<rect width="8" height="8" fill="#ff3b3b" fill-opacity=".45"/><line x1="0" y1="0" x2="0" y2="8" stroke="#000" stroke-width="3"/></pattern>' +
      '<pattern id="hatch-b" width="6" height="6" patternUnits="userSpaceOnUse">' +
        '<rect width="6" height="6" fill="#ff3b3b" fill-opacity=".85"/><path d="M0 0L6 6M6 0L0 6" stroke="#fff" stroke-width="1.2"/></pattern>';
    svg.insertBefore(defs, svg.firstChild);
  }

  async function regions(all) {
    if (all) return API.get('/api/regions?all=true');
    if (!regionsCache) regionsCache = API.get('/api/regions').catch(e => { regionsCache = null; throw e; });
    return regionsCache;
  }

  return { create, ensurePatterns, regions, available };
})();
window.Maps = Maps;
