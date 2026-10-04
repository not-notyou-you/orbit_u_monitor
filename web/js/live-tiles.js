// web/js/live-tiles.js — tile preview Live (9 kunci), legenda, dan kalimat kondisi.
// Dipakai Beranda Publik (/api/public/live) dan Pantauan Live (/api/live/areas/{id}/card).
'use strict';

const LiveTiles = (() => {
  // Urutan per INTERFACE §2.1: S1 [VV][VH][Perubahan air] · MODIS [Banjir][NDVI][NDWI] · GPM [24][72][7 hari]
  const ROWS = [
    { src: 'sentinel1', title: 'Sentinel-1 (radar)', ch: 'S1 SAR', keys: ['s1_vv', 's1_vh', 's1_water_change'] },
    { src: 'modis', title: 'MODIS (optik)', ch: 'MODIS', keys: ['modis_flood', 'modis_ndvi', 'modis_ndwi'] },
    { src: 'gpm', title: 'GPM (curah hujan)', ch: 'GPM IMERG', keys: ['gpm_rain_24h', 'gpm_rain_72h', 'gpm_rain_7d'] },
  ];
  const LABEL = {
    s1_vv: 'VV', s1_vh: 'VH', s1_water_change: 'Perubahan air',
    modis_flood: 'Banjir', modis_ndvi: 'NDVI', modis_ndwi: 'NDWI',
    gpm_rain_24h: 'Hujan 24 jam', gpm_rain_72h: 'Hujan 72 jam', gpm_rain_7d: 'Hujan 7 hari',
  };
  const LONG = {
    s1_vv: 'Sentinel-1 VV', s1_vh: 'Sentinel-1 VH', s1_water_change: 'Perubahan air Sentinel-1',
    modis_flood: 'Peta genangan MODIS', modis_ndvi: 'MODIS NDVI', modis_ndwi: 'MODIS NDWI',
    gpm_rain_24h: 'GPM hujan 24 jam', gpm_rain_72h: 'GPM hujan 72 jam', gpm_rain_7d: 'GPM hujan 7 hari',
  };
  // Kategori kalimat (bahasa kode) → label Indonesia + kelas warna. Teks selalu ditulis.
  const CAT = {
    normal: ['NORMAL', ''], alert: ['WASPADA', 'v-amber'], waspada: ['WASPADA', 'v-amber'],
    high: ['TINGGI', 'v-alert'], tinggi: ['TINGGI', 'v-alert'],
    'flood-indicated': ['INDIKASI GENANGAN', 'v-alert'], 'n/a': ['TIDAK TERSEDIA', 'v-dim'], na: ['TIDAK TERSEDIA', 'v-dim'],
  };
  const LEGEND_LABEL = {
    'No water': 'Tanpa air', 'Permanent water (reference)': 'Air permanen (rujukan)',
    'Seasonal flood (recurrent)': 'Genangan musiman (berulang)', 'Flood (unusual)': 'Genangan (tidak biasa)',
  };

  function levelInfo(level) { return UI.LEVEL[level] || { label: 'Tidak tersedia', cls: 'v-dim' }; }

  function sentenceHTML(it) {
    if (!it || !it.text) return '';
    let t = UI.esc(it.text);
    const c = CAT[it.category];
    if (c && it.category) t = t.replace(UI.esc(it.category), '<b class="' + c[1] + '">' + c[0] + '</b>');
    return t;
  }

  function legendHTML(lg) {
    if (!lg) return '';
    let h = '';
    if (lg.type === 'categorical') {
      h = '<div class="legend">' + lg.categories.map(c => {
        const sw = c.color === 'checker' ? 'background:repeating-linear-gradient(45deg,#555 0 3px,#222 3px 6px)'
          : c.color === '#00000000' ? 'background:transparent' : 'background:' + c.color;
        return '<span><i style="' + sw + '"></i>' + UI.esc(LEGEND_LABEL[c.label] || c.label) + '</span>';
      }).join('') + '</div>';
    } else {
      const unit = lg.units && !['index', 'indeks'].includes(lg.units) ? ' ' + lg.units : '';
      h = '<div class="legend"><span class="num">' + UI.num(lg.min, 2) + '</span><span class="ramp" style="background:linear-gradient(90deg,' +
        (lg.stops || []).join(',') + ')"></span><span class="num">' + UI.num(lg.max, 2) + unit + '</span></div>';
    }
    if (lg.warning) h += '<p class="v-amber" style="margin:4px 0 0">⚠ ' + UI.esc(lg.warning.toUpperCase()) + '</p>';
    return h;
  }

  // previews: {key: {url, label, legend, source_date?}}; sourceStatus opsional (kartu Live).
  function rowsHTML(previews, interpretations, opts) {
    opts = opts || {};
    return ROWS.map(row => {
      const failed = opts.sourceStatus && (opts.sourceStatus[row.src] || {}).status === 'FAILED';
      const tiles = row.keys.map(k => {
        const p = previews[k];
        const it = (interpretations || {})[k];
        const cat = it && CAT[it.category];
        const near = p && p.source_date && opts.sceneDate && p.source_date !== opts.sceneDate;
        return '<div class="tile">' +
          '<span class="tl"><span>' + UI.esc(LABEL[k]) + '</span>' + (cat ? '<span class="' + cat[1] + '">' + cat[0] + '</span>' : '') + '</span>' +
          (p ? '<button type="button" class="thumb" data-key="' + k + '" aria-label="' + UI.esc(LONG[k]) + ': buka legenda dan penjelasan">' +
                '<img loading="lazy" src="' + UI.esc(p.url) + '" alt=""></button>'
             : '<div class="noimg">NO DATA</div>') +
          (near ? '<span class="tl v-amber">TERDEKAT ' + UI.esc(UI.date(p.source_date, 'short')) + '</span>' : '') +
          '</div>';
      }).join('');
      return UI.screenHTML({ channel: 'CH-0' + (ROWS.indexOf(row) + 1) + ' · ' + row.ch, rec: failed ? '● GAGAL' : '',
        recCls: failed ? 'live' : '', body: '<div class="tiles">' + tiles + '</div>' +
          (failed && opts.retryButton ? opts.retryButton(row.src) : '') });
    }).join('');
  }

  function bindLightbox(root, previews, interpretations, sceneDate) {
    const keys = ROWS.flatMap(r => r.keys).filter(k => previews[k]);
    const items = keys.map(k => ({
      url: previews[k].url, title: LONG[k], channel: LONG[k] + ' · ' + UI.date(sceneDate),
      legend: legendHTML(previews[k].legend), note: sentenceHTML((interpretations || {})[k]),
    }));
    UI.$$('button.thumb[data-key]', root).forEach(b => b.addEventListener('click', () => UI.lightbox(items, keys.indexOf(b.dataset.key))));
  }

  return { ROWS, LABEL, LONG, CAT, levelInfo, sentenceHTML, legendHTML, rowsHTML, bindLightbox };
})();
window.LiveTiles = LiveTiles;
