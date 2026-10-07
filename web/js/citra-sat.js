// js/citra-sat.js — Citra Satelit per satelit (#citra/sentinel-1|modis|gpm,
// INTERFACE.md §2 halaman 3.2–3.4, M56).
//
// Satu skrip untuk tiga tab; satelitnya dari ctx.tab.source (s1|modis|gpm).
// Sumber: /api/citra/sources/{key} (penjelasan + band), /areas/{id}/scenes
// (daftar tanggal dalam batas peran), /areas/{id}/scenes/{tgl} (gambar,
// kalimat, angka). "Bandingkan" memuat tanggal kedua dan menaruh gambarnya
// berdampingan, lalu tabel angka menambah kolom selisih.
//
// Tab GPM untuk pengguna yang masuk juga memuat "Hujan per kecamatan"
// (halaman statistics yang sudah ada, dengan acknowledge alert untuk Analis):
// angka GPM per kecamatan adalah bagian dari data GPM, bukan halaman terpisah.
'use strict';
Pages['citra-sat'] = (() => {
  let st = null;

  async function init(root, ctx) {
    const key = (ctx.tab && ctx.tab.source) || 's1';
    st = { root, ctx, key, info: null, area: null, dates: [], date: null, cmp: null, extra: null };
    const $ = s => UI.$(s, root);
    $('#csArea').addEventListener('change', e => { CitraState.setArea(Number(e.target.value)); loadDates(); });
    $('#csCmpOn').addEventListener('change', e => {
      $('#csCmpBox').hidden = !e.target.checked;
      st.cmp = e.target.checked ? ($('#csCmp').value || null) : null;
      loadScene();
    });
    $('#csCmp').addEventListener('change', e => { st.cmp = e.target.value || null; loadScene(); });
    try {
      st.info = await API.get('/api/citra/sources/' + key);
      renderInfo();
    } catch (e) { UI.showError('Citra satelit', e); }
    await loadDates();
    if (key === 'gpm' && Auth.can('hydromet.today')) mountRainPerKecamatan();
  }

  function destroy() {
    if (st && st.extra && window.Pages.statistics && Pages.statistics.destroy) {
      try { Pages.statistics.destroy(); } catch (e) { /* abaikan */ }
    }
    st = null;
  }

  // ------------------------------------------------------------- penjelasan
  function renderInfo() {
    const $ = s => UI.$(s, st.root), i = st.info;
    $('#csAboutLegend').textContent = 'Tentang ' + i.label;
    $('#csAbout').textContent = i.about;
    $('#csSpec').innerHTML = '<dt>Lintasan</dt><dd>' + UI.esc(i.revisit) + '</dd><dt>Resolusi</dt><dd>' + UI.esc(i.resolution) + '</dd>';
    $('#csExtract').innerHTML = i.extractable.map(x => '<li>' + UI.esc(x) + '</li>').join('');
    $('#csLimits').textContent = i.limits;
    $('#csBands').innerHTML = UI.screenHTML({ channel: 'BAND ' + i.label.toUpperCase(), body:
      '<div class="band-list">' + i.bands.map(b => '<div class="band-item"><span class="swatch" style="background:' + b.color + '"></span>' +
        '<div><b>' + UI.esc(b.band_name) + '</b> <span class="v-dim">(' + UI.esc(b.band_code) + (b.unit ? ', ' + UI.esc(b.unit) : '') + ')</span>' +
        '<p class="scr-text" style="margin:2px 0 0">' + UI.esc(b.about || '') + '</p>' +
        (b.thresholds.length ? '<p class="scr-text v-amber" style="margin:2px 0 0">AMBANG: ' +
          b.thresholds.map(t => UI.esc(t.label) + ' ' + UI.num(t.value, 2)).join(' · ') + '</p>' : '') +
        '</div></div>').join('') + '</div>' });
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

  function renderDates() {
    const box = UI.$('#csDates', st.root);
    if (!st.dates.length) { box.innerHTML = UI.emptyHTML('TIDAK ADA TANGGAL DALAM BATAS PERAN ANDA'); return; }
    box.innerHTML = st.dates.map(d => {
      const lv = LiveTiles.levelInfo(d.level);
      const note = !d.has_scene ? 'angka harian' : !d.files_available ? 'berkas dihapus retensi' : !d.has_images ? 'tanpa gambar' : lv.label;
      return '<button type="button" role="option" data-date="' + d.date + '" aria-selected="' + (d.date === st.date) + '">' +
        UI.esc(UI.date(d.date)) + ' <span class="sub ' + (d.has_images ? lv.cls : 'v-dim') + '">' + UI.esc(note) + '</span></button>';
    }).join('');
    UI.$$('button[data-date]', box).forEach(b => b.addEventListener('click', () => {
      st.date = b.dataset.date;
      UI.$$('button[data-date]', box).forEach(x => x.setAttribute('aria-selected', String(x === b)));
      loadScene();
    }));
  }

  // ------------------------------------------------------------------ scene
  async function loadScene() {
    if (!st || !st.date || !st.area) return;
    const $ = s => UI.$(s, st.root);
    st.ctx.setStatus('Memuat scene ' + UI.date(st.date) + '…');
    const url = d => '/api/citra/areas/' + st.area.area_id + '/scenes/' + d + API.qs({ source: st.key });
    let main, cmp = null;
    try {
      [main, cmp] = await Promise.all([API.get(url(st.date)), st.cmp && st.cmp !== st.date ? API.get(url(st.cmp)) : null]);
    } catch (e) { UI.showError('Scene', e); return; }
    if (!st) return;
    renderTiles(main, cmp);
    renderSentences(main, cmp);
    renderMetrics(main, cmp);
    st.ctx.setStatus('Siap · ' + st.info.label + ' · ' + UI.date(main.date) + (cmp ? ' vs ' + UI.date(cmp.date) : ''));
  }

  function tile(p, key, date) {
    return '<div class="tile">' +
      '<span class="tl"><span>' + UI.esc(LiveTiles.LABEL[key] || (p && p.label) || key) + '</span><span class="v-dim">' + UI.esc(UI.date(date, 'short')) + '</span></span>' +
      (p ? '<button type="button" class="thumb" data-key="' + key + '" data-date="' + date + '" aria-label="' +
             UI.esc((LiveTiles.LONG[key] || key) + ' ' + UI.date(date)) + ': perbesar"><img loading="lazy" ' + UI.imgAttrs(p) + ' alt=""></button>'
         : '<div class="noimg">TIDAK ADA GAMBAR</div>') + '</div>';
  }

  function renderTiles(main, cmp) {
    const box = UI.$('#csTiles', st.root);
    const keys = Array.from(new Set(Object.keys(main.previews).concat(cmp ? Object.keys(cmp.previews) : []))).sort();
    const note = main.has_scene === false
      ? '<p class="scr-text v-amber" style="margin:0 0 6px">TIDAK ADA SCENE (LINTASAN SENTINEL-1) PADA TANGGAL INI, JADI TIDAK ADA GAMBAR. ANGKA HARIAN DARI JOB HIDROMET ADA DI BAWAH.</p>'
      : !main.files_available ? '<p class="scr-text v-amber" style="margin:0 0 6px">BERKAS GAMBAR SCENE INI SUDAH DIHAPUS RETENSI; ANGKANYA MASIH TERSEDIA DI BAWAH.</p>' : '';
    if (!keys.length) {
      box.innerHTML = UI.screenHTML({ channel: st.info.label.toUpperCase() + ' · ' + UI.date(main.date), body: note + UI.emptyHTML('TIDAK ADA GAMBAR UNTUK TANGGAL INI') });
      return;
    }
    const body = cmp
      ? '<div class="compare-grid">' + keys.map(k => '<div class="compare-row">' + tile(main.previews[k], k, main.date) + tile(cmp.previews[k], k, cmp.date) + '</div>').join('') + '</div>'
      : '<div class="tiles">' + keys.map(k => tile(main.previews[k], k, main.date)).join('') + '</div>';
    box.innerHTML = UI.screenHTML({ channel: 'CH-01 · ' + st.info.label.toUpperCase() + ' · ' + UI.date(main.date) + (cmp ? ' ⇄ ' + UI.date(cmp.date) : ''),
      rec: cmp ? '● BANDINGKAN' : '', recCls: cmp ? 'live' : '', body: note + body +
        Object.keys(main.previews).map(k => main.previews[k].legend ? '<div class="legend-row"><span class="lbl">' + UI.esc(LiveTiles.LABEL[k] || k) + '</span>' + LiveTiles.legendHTML(main.previews[k].legend) + '</div>' : '').join('') });
    const items = [];
    [main, cmp].filter(Boolean).forEach(s => keys.forEach(k => { const p = s.previews[k]; if (p) items.push({
      key: k, date: s.date, url: p.url, url_boundaries: p.url_boundaries, title: (LiveTiles.LONG[k] || k) + ' · ' + UI.date(s.date),
      channel: (LiveTiles.LONG[k] || k) + ' · ' + UI.date(s.date), legend: LiveTiles.legendHTML(p.legend),
      note: LiveTiles.sentenceHTML((s.interpretations || {})[k]) }); }));
    UI.$$('button.thumb', box).forEach(b => b.addEventListener('click', () => {
      UI.lightbox(items, Math.max(0, items.findIndex(x => x.key === b.dataset.key && x.date === b.dataset.date)));
    }));
  }

  function renderSentences(main, cmp) {
    const line = (s) => {
      const rows = Object.entries(s.interpretations || {}).filter(([, v]) => v && v.text);
      return rows.length ? rows.map(([, v]) => '<p class="scr-text" style="margin:0 0 4px">' + LiveTiles.sentenceHTML(v) + '</p>').join('')
        : '<p class="scr-text v-dim" style="margin:0">TIDAK ADA KALIMAT KONDISI.</p>';
    };
    UI.$('#csSentences', st.root).innerHTML = UI.screenHTML({ channel: 'CH-02 · KONDISI', body:
      '<p class="lbl" style="margin:0 0 4px">' + UI.esc(UI.date(main.date)) + '</p>' + line(main) +
      (cmp ? '<p class="lbl" style="margin:8px 0 4px">' + UI.esc(UI.date(cmp.date)) + '</p>' + line(cmp) : '') });
  }

  function renderMetrics(main, cmp) {
    const by = {};
    (cmp ? cmp.metrics : []).forEach(m => { by[m.band_code + '|' + m.metric_name] = m; });
    const unit = m => m.metric_unit ? ' ' + m.metric_unit : '';
    const cols = [
      { label: 'Band', get: m => m.band_name },
      { label: 'Metrik', get: m => m.metric_label },
      { label: UI.date(main.date, 'short'), cls: 'r', get: m => UI.num(m.value, 2) + unit(m) },
    ];
    if (cmp) {
      cols.push({ label: UI.date(cmp.date, 'short'), cls: 'r', get: m => { const o = by[m.band_code + '|' + m.metric_name]; return o ? UI.num(o.value, 2) + unit(o) : UI.NA; } });
      cols.push({ label: 'Selisih', cls: 'r', html: true, get: m => {
        const o = by[m.band_code + '|' + m.metric_name];
        if (!o || o.value === null || m.value === null) return UI.NA;
        const d = m.value - o.value;
        return '<span class="' + (Math.abs(d) < 1e-9 ? 'v-dim' : 'v-cyan') + '">' + (d > 0 ? '+' : '') + UI.esc(UI.num(d, 2)) + '</span>';
      } });
    }
    cols.push({ label: 'Tanggal data', get: m => m.source_date ? UI.date(m.source_date, 'short') : '' });
    // Hari dengan scene: angka scene di atas, angka harian Hidromet di bawahnya.
    const daily = main.has_scene && (main.daily_metrics || []).length
      ? '<p class="lbl" style="margin:8px 0 4px">ANGKA HARIAN JOB HIDROMET (RATA-RATA KECAMATAN AOI)</p>' +
        UI.tableHTML(cols.slice(0, 3), main.daily_metrics, { caption: 'Angka harian' }) : '';
    const per = main.per_region && main.per_region.length ? perRegionHTML(main.per_region)
      : (main.per_region === null && (main.daily_metrics || []).length
        ? '<p class="scr-text v-dim" style="margin:8px 0 0">ANGKA PER KECAMATAN TERSEDIA UNTUK PENGGUNA YANG MASUK (AKUN RELAWAN GRATIS).</p>' : '');
    UI.$('#csMetrics', st.root).innerHTML = UI.screenHTML({ channel: 'CH-03 · ANGKA ' + st.info.label.toUpperCase(),
      body: UI.tableHTML(cols, main.metrics, { empty: 'TIDAK ADA ANGKA UNTUK SATELIT INI PADA TANGGAL TERSEBUT', caption: 'Angka per band' }) + daily + per });
  }

  function perRegionHTML(rows) {
    const bands = Array.from(new Set(rows.flatMap(r => Object.keys(r.values)))).sort();
    return '<p class="lbl" style="margin:8px 0 4px">PER KECAMATAN</p>' + UI.tableHTML(
      [{ label: 'Kecamatan', key: 'region_name' }].concat(bands.map(b => ({ label: b, cls: 'r', get: r => UI.num(r.values[b], 2) }))),
      rows, { caption: 'Angka per kecamatan' });
  }

  // ------------------------------------------- hujan per kecamatan (GPM, USER+)
  async function mountRainPerKecamatan() {
    const box = UI.$('#csExtra', st.root);
    box.innerHTML = '<fieldset><legend>Hujan per kecamatan — tanggal data terakhir</legend><div id="csRain">' + UI.loadingHTML() + '</div></fieldset>';
    try {
      const [html] = await Promise.all([
        fetch('pages/statistics.html', { cache: 'no-cache' }).then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.text(); }),
        Shell.loadScript('statistics'),
      ]);
      if (!st) return;
      const host = UI.$('#csRain', st.root);
      host.innerHTML = html;
      st.extra = true;
      await Pages.statistics.init(host, Object.assign({}, st.ctx, { setStatus: () => {} }));
    } catch (e) {
      const host = st && UI.$('#csRain', st.root);
      if (host) host.innerHTML = UI.emptyHTML('ANGKA PER KECAMATAN GAGAL DIMUAT');
    }
  }

  return { init, destroy };
})();
