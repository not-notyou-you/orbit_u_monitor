// js/citra-sat.js — Citra Satelit per satelit (#citra/sentinel-1|modis|gpm,
// INTERFACE.md §2 halaman 3.2–3.4, M56).
//
// Satu skrip untuk tiga tab; satelitnya dari ctx.tab.source (s1|modis|gpm).
// Sumber: /api/citra/sources/{key} (penjelasan + band), /areas/{id}/scenes
// (daftar tanggal dalam batas peran), /areas/{id}/scenes/{tgl} (gambar,
// kalimat, angka). "Bandingkan" memuat tanggal kedua dan menaruh gambarnya
// berdampingan, lalu tabel angka menambah kolom selisih.
//
// M66: kalimat kondisi, penjelasan band, dan "informasi yang bisa diambil"
// digabung menjadi satu layar CH-02 — tiap kalimat tampil di bawah band yang
// dibicarakannya. Pilihan Live Area hanya untuk Administrator. Tanggal dipilih
// dari dropdown (lima baris terlihat, sisanya digulir). Angka per band tidak
// lagi di halaman: modal gambar memuat tabel tanggal × band yang sedang
// dilihat, dan Sebelumnya/Berikutnya menelusuri band lalu tanggal.
//
// M73: di tab GPM, angka per kecamatan menjadi satu bagian "Hujan per
// kecamatan" untuk tanggal yang dipilih — peta koroplet BMKG dan tabel yang
// bisa diurutkan, saling menyorot. Dulu tabel CH-03 + halaman statistics
// (tanggal data terakhir, kartu per kecamatan, daftar alert): dua tanggal dan
// angka yang sama tiga kali. Daftar alert + "tandai dibaca" pindah ke Kejadian;
// di sini tinggal satu baris pemberitahuan dengan tautan ke sana.
'use strict';
Pages['citra-sat'] = (() => {
  // Kunci kalimat kondisi/preview → band yang dibicarakannya.
  const KEY_BAND = {
    s1_vv: 'VV', s1_vh: 'VH', s1_water_change: 'WATER_CHANGE',
    modis_flood: 'FLOOD', modis_ndvi: 'NDVI', modis_ndwi: 'NDWI',
    gpm_rain_24h: 'RAIN_24H', gpm_rain_72h: 'RAIN_72H', gpm_rain_7d: 'RAIN_7D',
  };
  let st = null;

  async function init(root, ctx) {
    const key = (ctx.tab && ctx.tab.source) || 's1';
    st = { root, ctx, key, info: null, area: null, dates: [], date: null, cmp: null, extra: null, cache: {} };
    const $ = s => UI.$(s, root);
    $('#csAreaBox').hidden = Auth.role() !== 'ADMIN';
    $('#csArea').addEventListener('change', e => { CitraState.setArea(Number(e.target.value)); loadDates(); });
    $('#csCmpOn').addEventListener('change', e => {
      $('#csCmpBox').hidden = !e.target.checked;
      st.cmp = e.target.checked ? ($('#csCmp').value || null) : null;
      loadScene();
    });
    $('#csCmp').addEventListener('change', e => { st.cmp = e.target.value || null; loadScene(); });
    bindDropdown();
    try {
      st.info = await API.get('/api/citra/sources/' + key);
      renderInfo();
    } catch (e) { UI.showError('Citra satelit', e); }
    await loadDates();
    if (key === 'gpm') alertStrip();
  }

  function destroy() {
    if (st && st.onDoc) document.removeEventListener('click', st.onDoc);
    if (st && st.rmap) st.rmap.remove();
    st = null;
  }

  // ------------------------------------------------------------- penjelasan
  function renderInfo() {
    const $ = s => UI.$(s, st.root), i = st.info;
    $('#csAboutLegend').textContent = 'Tentang ' + i.label;
    $('#csAbout').textContent = i.about;
    $('#csSpec').innerHTML = '<dt>Lintasan</dt><dd>' + UI.esc(i.revisit) + '</dd><dt>Resolusi</dt><dd>' + UI.esc(i.resolution) + '</dd>' +
      '<dt>Keterbatasan</dt><dd>' + UI.esc(i.limits) + '</dd>';
  }

  // ---------------------------------------------------------- daftar tanggal
  async function loadDates() {
    const $ = s => UI.$(s, st.root);
    let areaId = CitraState.area();
    if (!areaId) {
      try { const s = await API.get('/api/citra/summary'); areaId = s.area && s.area.area_id; fillAreas(s.areas, areaId); }
      catch (e) { UI.showError('Citra satelit', e); return; }
    }
    if (!areaId) { $('#csTiles').innerHTML = UI.screenHTML({ channel: 'CITRA', body: UI.emptyHTML('BELUM ADA SCENE YANG SIAP') }); return; }
    let r;
    try { r = await API.get('/api/citra/areas/' + areaId + '/scenes' + API.qs({ source: st.key })); }
    catch (e) {
      if (e.status === 404) { CitraState.setArea(null); return; }
      UI.showError('Daftar tanggal', e); return;
    }
    CitraState.setArea(r.area.area_id);
    st.area = r.area;
    st.cache = {};
    if (!$('#csArea').options.length) {
      try { fillAreas((await API.get('/api/citra/summary' + API.qs({ area_id: r.area.area_id }))).areas, r.area.area_id); }
      catch (e) { fillAreas([r.area], r.area.area_id); }
    }
    $('#csWindow').textContent = CitraState.windowText(r.window) + (st.key !== 's1'
      ? ' ' + UI.int(r.n_scene_dates) + ' tanggal scene (bergambar) + ' + UI.int(r.n_daily_dates) + ' hari angka harian (Job Hidromet/backfill).' : '');
    st.dates = r.dates;
    const first = r.dates.find(d => d.has_images) || r.dates[0];
    st.date = first ? first.date : null;
    renderDates();
    const cmpOpts = r.dates.map(d => '<option value="' + d.date + '">' + UI.esc(UI.date(d.date)) + (d.has_images ? '' : ' (tanpa gambar)') + '</option>');
    $('#csCmp').innerHTML = cmpOpts.join('');
    const second = r.dates.find(d => d.date !== st.date && d.has_images);
    if (second) $('#csCmp').value = second.date;
    if ($('#csCmpOn').checked) st.cmp = $('#csCmp').value || null;
    await loadScene();
  }

  function fillAreas(areas, selected) {
    UI.$('#csArea', st.root).innerHTML = (areas || []).map(a => '<option value="' + a.area_id + '"' +
      (a.area_id === selected ? ' selected' : '') + '>' + UI.esc(a.area_name) + '</option>').join('');
  }

  const dateNote = d => !d.has_scene ? 'angka harian' : !d.files_available ? 'berkas dihapus retensi'
    : !d.has_images ? 'tanpa gambar' : LiveTiles.levelInfo(d.level).label;

  function renderDates() {
    const box = UI.$('#csDates', st.root), btn = UI.$('#csDateBtn', st.root);
    if (!st.dates.length) {
      btn.textContent = 'Tidak ada tanggal'; btn.disabled = true;
      box.innerHTML = UI.emptyHTML('TIDAK ADA TANGGAL DALAM BATAS PERAN ANDA');
      return;
    }
    btn.disabled = false;
    box.innerHTML = st.dates.map(d => {
      const lv = LiveTiles.levelInfo(d.level);
      return '<button type="button" role="option" data-date="' + d.date + '" aria-selected="' + (d.date === st.date) + '">' +
        UI.esc(UI.date(d.date)) + ' <span class="sub ' + (d.has_images ? lv.cls : 'v-dim') + '">' + UI.esc(dateNote(d)) + '</span></button>';
    }).join('');
    UI.$$('button[data-date]', box).forEach(b => b.addEventListener('click', () => pickDate(b.dataset.date)));
    dateLabel();
  }

  function dateLabel() {
    const d = st.dates.find(x => x.date === st.date);
    UI.$('#csDateBtn', st.root).innerHTML = d ? '<span>' + UI.esc(UI.date(d.date)) + '</span><span class="sub">' + UI.esc(dateNote(d)) + '</span>' : 'Pilih tanggal';
  }

  function pickDate(date) {
    st.date = date;
    UI.$$('#csDates button[data-date]', st.root).forEach(x => x.setAttribute('aria-selected', String(x.dataset.date === date)));
    dateLabel();
    openDates(false, true);
    loadScene();
  }

  // Dropdown tanggal: tertutup sampai tombolnya ditekan; daftarnya lima baris
  // tinggi, sisanya digulir. ↑/↓ berpindah, Esc menutup.
  function openDates(on, focusBtn) {
    const box = UI.$('#csDates', st.root), btn = UI.$('#csDateBtn', st.root);
    box.hidden = !on;
    btn.setAttribute('aria-expanded', String(on));
    if (on) {
      const cur = UI.$('button[aria-selected="true"]', box) || UI.$('button', box);
      if (cur) { cur.scrollIntoView({ block: 'nearest' }); cur.focus(); }
    } else if (focusBtn) btn.focus();
  }

  function bindDropdown() {
    const dd = UI.$('#csDateDd', st.root), box = UI.$('#csDates', st.root), btn = UI.$('#csDateBtn', st.root);
    btn.addEventListener('click', () => openDates(box.hidden));
    st.onDoc = e => { if (st && !box.hidden && !dd.contains(e.target)) openDates(false); };
    document.addEventListener('click', st.onDoc);
    dd.addEventListener('keydown', e => {
      const its = UI.$$('button[data-date]', box), i = its.indexOf(document.activeElement);
      if (e.key === 'Escape' && !box.hidden) { e.preventDefault(); openDates(false, true); }
      else if (e.key === 'ArrowDown' && e.target === btn) { e.preventDefault(); openDates(true); }
      else if (i >= 0 && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
        e.preventDefault(); const n = its[Math.min(its.length - 1, Math.max(0, i + (e.key === 'ArrowDown' ? 1 : -1)))]; if (n) n.focus();
      }
    });
  }

  // ------------------------------------------------------------------ scene
  async function loadScene() {
    if (!st || !st.date || !st.area) return;
    const $ = s => UI.$(s, st.root);
    st.ctx.setStatus('Memuat scene ' + UI.date(st.date) + '…');
    let main, cmp = null;
    try {
      [main, cmp] = await Promise.all([scene(st.date), st.cmp && st.cmp !== st.date ? scene(st.cmp) : null]);
    } catch (e) { UI.showError('Scene', e); return; }
    if (!st) return;
    renderTiles(main, cmp);
    renderKondisi(main, cmp);
    renderPerRegion(main);
    st.ctx.setStatus('Siap · ' + st.info.label + ' · ' + UI.date(main.date) + (cmp ? ' vs ' + UI.date(cmp.date) : ''));
  }

  // Scene per tanggal disimpan sesi halaman ini: modal menelusuri banyak tanggal.
  function scene(date) {
    if (!st.cache[date]) {
      st.cache[date] = API.get('/api/citra/areas/' + st.area.area_id + '/scenes/' + date + API.qs({ source: st.key }))
        .catch(e => { if (st) delete st.cache[date]; throw e; });
    }
    return st.cache[date];
  }

  // Kunci gambar satelit ini (urutan baris LiveTiles: VV, VH, Perubahan air, …).
  const satKeys = () => (LiveTiles.ROWS[['s1', 'modis', 'gpm'].indexOf(st.key)] || { keys: [] }).keys;

  function tile(p, key, date) {
    return '<div class="tile">' +
      '<span class="tl"><span>' + UI.esc(LiveTiles.LABEL[key] || (p && p.label) || key) + '</span><span class="v-dim">' + UI.esc(UI.date(date, 'short')) + '</span></span>' +
      (p ? '<button type="button" class="thumb" data-key="' + key + '" data-date="' + date + '" aria-label="' +
             UI.esc((LiveTiles.LONG[key] || key) + ' ' + UI.date(date)) + ': perbesar dengan angka"><img loading="lazy" ' + UI.imgAttrs(p) + ' alt=""></button>'
         : '<div class="noimg">TIDAK ADA GAMBAR</div>') + '</div>';
  }

  const unitOf = m => m.metric_unit ? ' ' + m.metric_unit : '';

  // Tabel angka satu tanggal. code = band yang dilihat (null = semua band).
  function metricsHTML(s, code) {
    const pick = rows => (rows || []).filter(m => !code || m.band_code === code);
    const rows = pick(s.metrics), daily = s.has_scene ? pick(s.daily_metrics) : [];
    const cols = [];
    if (!code) cols.push({ label: 'Band', get: m => m.band_name });
    cols.push({ label: 'Metrik', get: m => m.metric_label });
    cols.push({ label: 'Nilai', cls: 'r', get: m => UI.num(m.value, 2) + unitOf(m) });
    if (rows.some(m => m.source_date && m.source_date !== s.date)) {
      cols.push({ label: 'Tanggal data', get: m => m.source_date ? UI.date(m.source_date, 'short') : '' });
    }
    return UI.tableHTML(cols, rows, { empty: 'TIDAK ADA ANGKA UNTUK ' + (code ? 'BAND INI' : 'SATELIT INI') + ' PADA TANGGAL TERSEBUT', caption: 'Angka per band' }) +
      (daily.length ? '<p class="lbl" style="margin:8px 0 4px">ANGKA HARIAN JOB HIDROMET (RATA-RATA KECAMATAN AOI)</p>' +
        UI.tableHTML(cols.slice(0, code ? 2 : 3), daily, { caption: 'Angka harian' }) : '');
  }

  function renderTiles(main, cmp) {
    const box = UI.$('#csTiles', st.root);
    const keys = Array.from(new Set(Object.keys(main.previews).concat(cmp ? Object.keys(cmp.previews) : []))).sort();
    const note = main.has_scene === false
      ? '<p class="scr-text v-amber" style="margin:0 0 6px">TIDAK ADA SCENE (LINTASAN SENTINEL-1) PADA TANGGAL INI, JADI TIDAK ADA GAMBAR. ANGKA HARIANNYA DI BAWAH.</p>'
      : !main.files_available ? '<p class="scr-text v-amber" style="margin:0 0 6px">BERKAS GAMBAR SCENE INI SUDAH DIHAPUS RETENSI; ANGKANYA MASIH TERSEDIA DI BAWAH.</p>' : '';
    if (!keys.length) {
      // Tanpa gambar tidak ada modal untuk dibuka, jadi angkanya tampil di sini.
      box.innerHTML = UI.screenHTML({ channel: 'CH-01 · ' + st.info.label.toUpperCase() + ' · ' + UI.date(main.date),
        body: note + UI.emptyHTML('TIDAK ADA GAMBAR UNTUK TANGGAL INI') +
          '<p class="lbl" style="margin:8px 0 4px">ANGKA ' + UI.esc(st.info.label.toUpperCase()) + '</p>' + metricsHTML(main, null) });
      return;
    }
    const body = cmp
      ? '<div class="compare-grid">' + keys.map(k => '<div class="compare-row">' + tile(main.previews[k], k, main.date) + tile(cmp.previews[k], k, cmp.date) + '</div>').join('') + '</div>'
      : '<div class="tiles">' + keys.map(k => tile(main.previews[k], k, main.date)).join('') + '</div>';
    box.innerHTML = UI.screenHTML({ channel: 'CH-01 · ' + st.info.label.toUpperCase() + ' · ' + UI.date(main.date) + (cmp ? ' ⇄ ' + UI.date(cmp.date) : ''),
      rec: cmp ? '● BANDINGKAN' : '', recCls: cmp ? 'live' : '', body: note + body +
        Object.keys(main.previews).map(k => main.previews[k].legend ? '<div class="legend-row"><span class="lbl">' + UI.esc(LiveTiles.LABEL[k] || k) + '</span>' + LiveTiles.legendHTML(main.previews[k].legend) + '</div>' : '').join('') +
        '<p class="mut" style="font-size:11px;margin:6px 0 0">Klik gambar untuk memperbesar dan melihat angkanya; Sebelumnya/Berikutnya menelusuri band lalu tanggal.</p>' });
    UI.$$('button.thumb', box).forEach(b => b.addEventListener('click', () => openModal(b.dataset.date, b.dataset.key)));
  }

  // Modal: tanggal bergambar × band satelit ini, terbaru dulu. Scene tiap
  // tanggal baru dimuat saat dibuka (UI.lightbox opts.resolve).
  function openModal(date, key) {
    const keys = satKeys().length ? satKeys() : [key];
    const dates = st.dates.filter(d => d.has_images).map(d => d.date);
    if (dates.indexOf(date) < 0) dates.unshift(date);
    const items = [];
    dates.forEach(d => keys.forEach(k => items.push({ date: d, key: k,
      title: (LiveTiles.LONG[k] || k) + ' · ' + UI.date(d), channel: (LiveTiles.LONG[k] || k) + ' · ' + UI.date(d) })));
    const start = Math.max(0, items.findIndex(x => x.date === date && x.key === key));
    UI.lightbox(items, start, { resolve: async it => {
      const s = await scene(it.date), p = s.previews[it.key];
      const code = KEY_BAND[it.key];
      const band = (st.info.bands.find(b => b.band_code === code) || {}).band_name || LiveTiles.LABEL[it.key] || it.key;
      return {
        url: p ? p.url : null, url_boundaries: p && p.url_boundaries,
        legend: p ? LiveTiles.legendHTML(p.legend) : '', note: LiveTiles.sentenceHTML((s.interpretations || {})[it.key]),
        side: UI.screenHTML({ channel: 'ANGKA · ' + band.toUpperCase(), rec: UI.date(s.date), body: metricsHTML(s, code) }),
      };
    } });
  }

  // CH-02: tiap band satelit ini dengan penjelasan, ambang, dan kalimat
  // kondisi tanggal terpilih (dan pembanding). Kalimat yang tidak menyebut
  // satu band tertentu tampil paling atas.
  function renderKondisi(main, cmp) {
    const i = st.info, byBand = {}, general = [];
    [main, cmp].filter(Boolean).forEach(s => Object.entries(s.interpretations || {}).forEach(([k, v]) => {
      if (!v || !v.text) return;
      const code = KEY_BAND[k], line = { date: s.date, html: LiveTiles.sentenceHTML(v) };
      if (code && i.bands.some(b => b.band_code === code)) (byBand[code] = byBand[code] || []).push(line);
      else general.push(line);
    }));
    const lines = ls => ls.map(l => '<p class="scr-text cs-cond">' +
      (cmp ? '<span class="lbl">' + UI.esc(UI.date(l.date, 'short')) + '</span> ' : '') + l.html + '</p>').join('');
    const none = !general.length && !Object.keys(byBand).length
      ? '<p class="scr-text v-dim" style="margin:0 0 8px">TIDAK ADA KALIMAT KONDISI UNTUK TANGGAL INI.</p>' : '';
    UI.$('#csInfo', st.root).innerHTML = UI.screenHTML({ channel: 'CH-02 · KONDISI & BAND ' + i.label.toUpperCase(),
      rec: UI.date(main.date) + (cmp ? ' ⇄ ' + UI.date(cmp.date) : ''), body: none + lines(general) +
      '<div class="band-list">' + i.bands.map(b => '<div class="band-item"><span class="swatch" style="background:' + b.color + '"></span>' +
        '<div><b>' + UI.esc(b.band_name) + '</b> <span class="v-dim">(' + UI.esc(b.band_code) + (b.unit ? ', ' + UI.esc(b.unit) : '') + ')</span>' +
        '<p class="scr-text" style="margin:2px 0 0">' + UI.esc(b.about || '') + '</p>' +
        (b.thresholds.length ? '<p class="scr-text v-amber" style="margin:2px 0 0">AMBANG: ' +
          b.thresholds.map(t => UI.esc(t.label) + ' ' + UI.num(t.value, 2)).join(' · ') + '</p>' : '') +
        lines(byBand[b.band_code] || []) +
        '</div></div>').join('') + '</div>' });
  }

  // Tabel per kecamatan lebar (satu kolom per band): selebar jendela, di bawah.
  function renderPerRegion(main) {
    if (st.key === 'gpm') return renderRain(main);
    const box = UI.$('#csPerRegion', st.root);
    if (main.per_region && main.per_region.length) {
      box.innerHTML = UI.screenHTML({ channel: 'CH-03 · ANGKA PER KECAMATAN · ' + UI.date(main.date), body: perRegionHTML(main.per_region) });
    } else {
      box.innerHTML = main.per_region === null && (main.daily_metrics || []).length
        ? '<p class="mut" style="font-size:11px;margin:0">Angka per kecamatan tersedia untuk pengguna yang masuk (akun Relawan gratis).</p>' : '';
    }
  }

  function perRegionHTML(rows) {
    const bands = Array.from(new Set(rows.flatMap(r => Object.keys(r.values)))).sort();
    return UI.tableHTML(
      [{ label: 'Kecamatan', key: 'region_name' }].concat(bands.map(b => ({ label: b, cls: 'r', get: r => UI.num(r.values[b], 2) }))),
      rows, { caption: 'Angka per kecamatan' });
  }

  // ------------------------------------------ hujan per kecamatan (GPM, M73)
  const RAIN_COLS = [['RAIN_24H', '24 jam'], ['RAIN_72H', '72 jam'], ['RAIN_7D', '7 hari'], ['RAIN_30D', '30 hari']];
  const HATCH = { 'hatch-a': 'repeating-linear-gradient(45deg,#ff3b3b 0 4px,#000 4px 7px)', 'hatch-b': 'repeating-linear-gradient(45deg,#ff3b3b 0 2px,#fff 2px 3px)' };
  const catOf = r => UI.bmkgCategory(r.values.RAIN_24H);

  function renderRain(main) {
    const box = UI.$('#csPerRegion', st.root);
    if (st.rmap) { st.rmap.remove(); st.rmap = null; }
    const rows = main.per_region;
    if (!rows || !rows.length) {
      box.innerHTML = rows === null && (main.daily_metrics || []).length
        ? '<p class="mut" style="font-size:11px;margin:0">Hujan per kecamatan tersedia untuk pengguna yang masuk (akun Relawan gratis).</p>' : '';
      return;
    }
    const cols = RAIN_COLS.filter(([b]) => rows.some(r => r.values[b] !== undefined && r.values[b] !== null));
    st.rain = { rows, cols, sort: (st.rain && st.rain.sort) || ['RAIN_24H', -1], layers: {} };
    const legend = '<div class="legend cs-rain-legend">' + Object.values(UI.BMKG).map(c =>
      '<span title="' + UI.esc(c.label + ' · ' + c.range) + '"><i style="background:' + (c.hatch ? HATCH[c.hatch] : c.color) + '"></i>' +
      UI.esc(c.short + ' ' + c.label) + ' <span class="v-dim">' + UI.esc(c.range) + '</span></span>').join('') + '</div>';
    box.innerHTML = UI.screenHTML({ channel: 'CH-03 · HUJAN PER KECAMATAN · ' + UI.date(main.date).toUpperCase(),
      rec: UI.int(rows.length) + ' KECAMATAN', recCls: 'off',
      body: '<div class="cs-rain"><div><div class="map" id="csRainMap" role="img" aria-label="Peta kecamatan berwarna menurut kategori hujan 24 jam BMKG; angka yang sama ada di tabel sebelahnya"></div>' +
        legend + '</div><div id="csRainTable"></div></div>' +
        '<p class="scr-text v-dim" style="margin:6px 0 0;font-size:11px">Hari UTC (07.00–07.00 WIB). Klik judul kolom untuk mengurutkan; arahkan kursor ke baris atau kecamatan di peta untuk menyorot pasangannya.</p>' }) +
      '<details class="ad-fold"><summary>Ekspor / impor Excel</summary><div id="csRainExcel"></div></details>';
    Excel.mount(UI.$('#csRainExcel', st.root), ['hujan_harian', 'observations', 'alerts', 'kecamatan']);
    renderRainTable();
    renderRainMap();
  }

  function renderRainTable() {
    const r = st.rain, [sk, dir] = r.sort;
    const val = x => sk === 'name' ? x.region_name : x.values[sk];
    const rows = r.rows.slice().sort((a, b) => {
      const va = val(a), vb = val(b);
      if (sk === 'name') return dir * va.localeCompare(vb, 'id');
      return va === vb ? 0 : va === null || va === undefined ? 1 : vb === null || vb === undefined ? -1 : dir * (va - vb);
    });
    const keys = ['name'].concat(r.cols.map(c => c[0]), ['RAIN_24H']);
    const box = UI.$('#csRainTable', st.root);
    // Di ponsel tabel jadi kartu (M72) dan judul kolom tak terlihat, jadi
    // urutan dipilih lewat select yang hanya tampil di layar sempit.
    const opts = [['name', 1, 'Nama kecamatan']].concat(r.cols.map(([b, l]) => [b, -1, 'Hujan ' + l + ' (tertinggi dulu)']));
    box.innerHTML = '<div class="field cs-rain-sort"><label for="csRainSort">Urutkan</label><select id="csRainSort">' +
      opts.map(([k, d, l]) => '<option value="' + k + '|' + d + '"' + (k === sk && (k !== 'name' || d === dir) ? ' selected' : '') + '>' + UI.esc(l) + '</option>').join('') +
      '</select></div>' + UI.tableHTML([{ label: 'Kecamatan', key: 'region_name' }].concat(
      r.cols.map(([b, l]) => ({ label: l, cls: 'r', get: x => x.values[b] === null || x.values[b] === undefined ? UI.NA : UI.num(x.values[b], 1) + ' mm' })),
      [{ label: 'Kategori BMKG', html: true, get: x => { const c = catOf(x), m = UI.BMKG[c];
        return m ? '<span class="tag ' + UI.bmkgClass(c) + '">' + UI.esc(m.short + ' · ' + m.label.toUpperCase()) + '</span>' : UI.NA; } }]),
      rows, { caption: 'Hujan per kecamatan, ' + UI.date(st.date),
        rowAttr: x => 'class="cs-rrow" tabindex="0" data-rid="' + x.region_id + '"' });
    UI.$('#csRainSort', box).addEventListener('change', e => { const [k, d] = e.target.value.split('|'); r.sort = [k, Number(d)]; renderRainTable(); });
    UI.$$('thead th', box).forEach((th, i) => {
      const k = keys[i], on = k === sk && (i < keys.length - 1 || sk !== 'RAIN_24H' || i === 1);
      th.classList.add('sortable');
      th.tabIndex = 0;
      th.setAttribute('aria-sort', on ? (dir > 0 ? 'ascending' : 'descending') : 'none');
      if (on) th.insertAdjacentText('beforeend', dir > 0 ? ' ▲' : ' ▼');
      const go = () => { r.sort = [k, k === sk ? -dir : (k === 'name' ? 1 : -1)]; renderRainTable(); };
      th.addEventListener('click', go);
      th.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } });
    });
    UI.$$('.cs-rrow', box).forEach(tr => {
      const id = Number(tr.dataset.rid);
      ['mouseenter', 'focus'].forEach(ev => tr.addEventListener(ev, () => rainSpot(id, true)));
      ['mouseleave', 'blur'].forEach(ev => tr.addEventListener(ev, () => rainSpot(id, false)));
      tr.addEventListener('click', () => { const l = st.rain.layers[id]; if (l) l.openPopup(); });
    });
  }

  // Arsir SL/E: isi path diganti pola setelah digambar (Leaflet tidak punya
  // fill pattern); dipasang ulang tiap kali gaya lapisan berubah.
  function hatch(l) {
    const el = l.getElement && l.getElement();
    const m = el && /bmkg-(hatch-[ab])/.exec(el.getAttribute('class') || '');
    if (m) { el.setAttribute('fill', 'url(#' + m[1] + ')'); el.setAttribute('fill-opacity', '1'); }
  }

  async function renderRainMap() {
    const el = UI.$('#csRainMap', st.root);
    st.rmap = Maps.create(el);
    let geo = null;
    try { geo = await Maps.regions(); } catch (e) { return; }
    if (!st || !st.rmap || !geo || !geo.features) return;
    const map = st.rmap, byId = Object.fromEntries(st.rain.rows.map(x => [x.region_id, x]));
    st.rain.style = f => {
      const x = byId[f.properties.region_id], c = x && UI.BMKG[catOf(x)];
      if (!c) return { color: '#1a9960', weight: 1, dashArray: '4 3', fillOpacity: 0 };
      return { color: '#33ff99', weight: 1, dashArray: null, fillColor: c.color, fillOpacity: c.opacity, className: c.hatch ? 'bmkg-' + c.hatch : '' };
    };
    st.rain.layer = L.geoJSON(geo, {
      style: st.rain.style,
      onEachFeature: (f, layer) => {
        const x = byId[f.properties.region_id], c = x && UI.BMKG[catOf(x)];
        st.rain.layers[f.properties.region_id] = layer;
        layer.bindTooltip(UI.esc(c ? c.short : '—'), { permanent: true, direction: 'center', className: 'map-label' });
        layer.bindPopup(UI.esc(f.properties.name + ': ' + (c ? c.label + ' (' + UI.num(x.values.RAIN_24H, 1) + ' mm/24 jam)' : 'tanpa data')));
        layer.on('mouseover', () => rainSpot(f.properties.region_id, true));
        layer.on('mouseout', () => rainSpot(f.properties.region_id, false));
      },
    }).addTo(map);
    Maps.ensurePatterns(map);
    st.rain.layer.eachLayer(hatch);
    const fit = () => { if (!st || !st.rmap) return; map.invalidateSize(); try { map.fitBounds(st.rain.layer.getBounds(), { padding: [8, 8] }); } catch (e) { /* kosong */ } };
    fit(); setTimeout(fit, 120);
  }

  function rainSpot(id, on) {
    const r = st && st.rain;
    if (!r) return;
    const tr = UI.$('.cs-rrow[data-rid="' + id + '"]', st.root);
    if (tr) tr.classList.toggle('sel', on);
    const l = r.layers[id];
    if (!l) return;
    if (on) { l.setStyle({ weight: 3, color: '#ffffff' }); l.bringToFront(); } else r.layer.resetStyle(l);
    hatch(l);
  }

  // Satu baris pemberitahuan; daftar dan "tandai dibaca" ada di Kejadian.
  async function alertStrip() {
    if (!Auth.can('alerts.view')) return;
    let r;
    try { r = await API.get('/api/alerts' + API.qs({ status: 'active', limit: 500 })); } catch (e) { return; }
    const items = (r && r.items) || [];
    if (!st || !items.length) return;
    const regions = new Set(items.map(a => a.region_id)).size;
    const box = UI.$('#csAlert', st.root);
    box.innerHTML = '<div class="banner raised cs-alert" role="status">' + UI.icon('warn32') + '<div class="b-body"><b>' + UI.int(regions) +
      ' kecamatan dengan alert hujan aktif</b> · ' + UI.int(items.length) + ' alert belum ditandai dibaca. ' +
      '<a href="#kejadian" id="csAlertLink">' + (Auth.can('alerts.acknowledge') ? 'Lihat & tandai dibaca di Kejadian →' : 'Lihat di Kejadian →') + '</a></div></div>';
    UI.$('#csAlertLink', box).addEventListener('click', () => { try { sessionStorage.setItem('orbitu.openAlerts', '1'); } catch (e) { /* abaikan */ } });
  }

  return { init, destroy };
})();
