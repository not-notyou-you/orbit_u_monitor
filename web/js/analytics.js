// js/analytics.js — Analitik (INTERFACE.md §2.4). Data: /hydromet/observations (dipaginasi),
// /disasters, /alerts/evaluation, /alerts, /alert-rules.
'use strict';
Pages['analytics'] = (() => {
  const UNIT = { RAIN_24H: 'mm', RAIN_72H: 'mm', RAIN_7D: 'mm', RAIN_30D: 'mm', NDVI: '', NDWI: '', FLOOD: '%' };
  const MAX_DAYS = 1100; // ±3 tahun arsip backfill
  let st = null;

  async function init(root, ctx) {
    st = { root, ctx, regions: [], alertPage: 1 };
    const $ = s => UI.$(s, root);
    Excel.mount($('#anExcel'), ['hujan_harian', 'observations', 'disaster_rain', 'alert_evaluation', 'alerts']);
    try {
      const [geo, latest] = await Promise.all([Maps.regions(), API.get('/api/hydromet/trend?band=RAIN_24H&days=1')]);
      st.regions = geo.features.map(f => f.properties).sort((a, b) => a.name.localeCompare(b.name, 'id'));
      const end = (latest.dates && latest.dates[0]) || UI.isoDate(new Date());
      $('#anTo').value = end; $('#anFrom').value = UI.addDays(end, -29);
    } catch (e) { UI.showError('Analitik', e); }
    $('#anRegions').innerHTML = st.regions.length ? st.regions.map(r =>
      '<label><input type="checkbox" value="' + r.region_id + '" checked> ' + UI.esc(r.name) + '</label>').join('') : '<p class="mut">Belum ada kecamatan AOI.</p>';
    $('#anAll').addEventListener('click', () => UI.$$('#anRegions input', root).forEach(i => { i.checked = true; }));
    $('#anNone').addEventListener('click', () => UI.$$('#anRegions input', root).forEach(i => { i.checked = false; }));
    $('#anForm').addEventListener('submit', ev => { ev.preventDefault(); UI.busy($('#anApply'), apply); });
    $('#anCsv').addEventListener('click', ev => UI.busy(ev.currentTarget, exportCsv));
    await apply();
  }

  function filters() {
    const $ = s => UI.$(s, st.root);
    const f = { from: $('#anFrom').value, to: $('#anTo').value, band: $('#anBand').value,
      ids: UI.$$('#anRegions input:checked', st.root).map(i => Number(i.value)) };
    let err = '';
    if (!f.from || !f.to) err = 'Isi kedua tanggal.';
    else if (f.from > f.to) err = 'Tanggal akhir sebelum tanggal awal.';
    else if ((UI.parseDate(f.to) - UI.parseDate(f.from)) / 864e5 > MAX_DAYS) err = 'Rentang maksimal ' + MAX_DAYS + ' hari.';
    else if (!f.ids.length) err = 'Pilih minimal satu kecamatan.';
    $('#anDateErr').textContent = err;
    [$('#anFrom'), $('#anTo')].forEach(i => i.setAttribute('aria-invalid', err && !err.startsWith('Pilih') ? 'true' : 'false'));
    return err ? null : f;
  }

  async function fetchAll(band, from, to) {
    const out = [];
    for (let offset = 0; ; offset += 5000) {
      const r = await API.get('/api/hydromet/observations' + API.qs({ band, date_from: from, date_to: to, limit: 5000, offset }));
      out.push(...r.items);
      if (out.length >= r.total || !r.items.length) break;
    }
    return out;
  }

  async function apply() {
    const f = filters(); if (!f) return;
    st.f = f; st.alertPage = 1;
    st.ctx.setStatus('Memuat…');
    const $ = s => UI.$(s, st.root);
    ['#anTrend', '#anHeat', '#anCorr', '#anEval', '#anAlerts'].forEach(s => { $(s).innerHTML = UI.loadingHTML(); });
    try {
      const [obs, rain24, rain72, events, ev, rules] = await Promise.all([
        fetchAll(f.band, f.from, f.to),
        f.band === 'RAIN_24H' ? null : fetchAll('RAIN_24H', f.from, f.to),
        fetchAll('RAIN_72H', f.from, f.to),
        API.get('/api/disasters' + API.qs({ date_from: f.from, date_to: f.to, limit: 1000 })),
        API.get('/api/alerts/evaluation' + API.qs({ date_from: f.from, date_to: f.to })),
        API.get('/api/alert-rules'),
      ]);
      const sel = new Set(f.ids);
      const pick = rows => rows.filter(r => sel.has(r.region_id));
      st.obs = pick(obs); st.r24 = pick(rain24 || obs); st.r72 = pick(rain72);
      st.events = (events.items || []).filter(e => sel.has(e.region_id));
      st.rules = (rules.items || []).filter(r => r.is_active && r.threshold_value !== null);
      renderReadouts(ev); renderTrend(); renderHeat(); renderCorr(); renderEval(ev);
      await loadAlerts();
      st.ctx.setStatus('Siap · ' + UI.date(f.from) + ' – ' + UI.date(f.to));
    } catch (e) {
      ['#anTrend', '#anHeat', '#anCorr', '#anEval', '#anAlerts'].forEach(s => { $(s).innerHTML = UI.emptyHTML('GAGAL MEMUAT'); });
      st.ctx.setStatus('Gagal'); UI.showError('Analitik', e);
    }
  }

  function renderReadouts(ev) {
    const vals = st.obs.map(o => o.value).filter(v => v !== null);
    const unit = UNIT[st.f.band];
    UI.$('#anReadouts', st.root).innerHTML =
      UI.readoutHTML('OBSERVASI', UI.int(st.obs.length), UI.esc(st.f.band)) +
      UI.readoutHTML('MAKSIMUM', vals.length ? UI.num(Math.max(...vals), 1) : UI.NA, UI.esc(unit || 'INDEKS')) +
      UI.readoutHTML('KEJADIAN', UI.int(st.events.length), 'DALAM RENTANG', st.events.length ? 'v-amber' : '') +
      UI.readoutHTML('POD / FAR', (ev.pod === null ? UI.NA : UI.num(ev.pod, 2)) + ' / ' + (ev.far === null ? UI.NA : UI.num(ev.far, 2)), 'EVALUASI ALERT');
  }

  function groupBy(rows, key) { const m = {}; rows.forEach(r => { (m[r[key]] = m[r[key]] || []).push(r); }); return m; }

  function thresholdsFor(band) {
    const t = {};
    st.rules.filter(r => r.band_code === band).sort((a, b) => a.threshold_value - b.threshold_value)
      .forEach(r => { t[UI.SEVERITY[r.severity] ? UI.SEVERITY[r.severity].label : r.severity] = r.threshold_value; });
    return t;
  }

  function renderTrend() {
    const box = UI.$('#anTrend', st.root);
    UI.$('#anTrendRec', st.root).textContent = st.f.band;
    if (!st.obs.length) { box.innerHTML = UI.emptyHTML('BELUM ADA OBSERVASI UNTUK FILTER INI — ARSIP TERISI SETELAH BACKFILL'); return; }
    const by = groupBy(st.obs, 'region_name');
    const w = Math.max(280, Math.min(560, (box.clientWidth || 600) / (box.clientWidth > 700 ? 2 : 1) - 16));
    // Ambang jauh di atas data membuat garis data tampak datar: tampilkan yang ≤ 1,5× maks.
    const vmax = Math.max(...st.obs.map(o => o.value).filter(v => v !== null));
    const all = thresholdsFor(st.f.band);
    const thr = Object.fromEntries(Object.entries(all).filter(([, v]) => v <= vmax * 1.5));
    const hidden = Object.entries(all).filter(([, v]) => v > vmax * 1.5);
    // Small multiples: satu grafik satu warna per kecamatan (≤ 3 warna sinyal per screen).
    box.innerHTML = '<div class="cols-2">' + Object.keys(by).sort((a, b) => a.localeCompare(b, 'id')).map(name => {
      const pts = by[name].sort((a, b) => a.obs_date < b.obs_date ? -1 : 1).map(o => ({ x: o.obs_date, y: o.value }));
      return '<div><p class="lbl" style="margin:0 0 2px">' + UI.esc(name.toUpperCase()) + '</p>' +
        UI.chartSVG([{ label: name, points: pts }], { unit: UNIT[st.f.band], thresholds: thr, width: w, height: 150, zero: st.f.band.startsWith('RAIN'), label: 'Tren ' + st.f.band + ' ' + name }) + '</div>';
    }).join('') + '</div>' + (hidden.length ? '<p class="v-dim" style="margin:6px 0 0;font-size:11px">AMBANG DI ATAS SKALA (TIDAK DIGAMBAR): ' +
      hidden.map(([n, v]) => UI.esc(n.toUpperCase()) + ' ' + UI.num(v, 0)).join(' · ') + '</p>' : '');
  }

  function renderHeat() {
    const box = UI.$('#anHeat', st.root);
    if (!st.r24.length) { box.innerHTML = UI.emptyHTML('BELUM ADA DATA HUJAN 24 JAM'); return; }
    const byDate = groupBy(st.r24, 'obs_date');
    const mean = {};
    Object.entries(byDate).forEach(([d, rows]) => {
      const v = rows.map(r => r.value).filter(x => x !== null);
      mean[d] = v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
    });
    const months = [];
    for (let d = UI.parseDate(st.f.from); d <= UI.parseDate(st.f.to); d = new Date(d.getFullYear(), d.getMonth() + 1, 1)) {
      const key = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0');
      if (!months.includes(key)) months.push(key);
    }
    const cell = (iso) => {
      const v = mean[iso];
      if (v === undefined || v === null) return '<td class="na" title="' + UI.esc(UI.date(iso)) + ': tanpa data"></td>';
      const cat = UI.bmkgCategory(v);
      const bg = v >= 100 ? 'var(--alert)' : v >= 50 ? 'var(--amber)' : 'rgba(51,255,153,' + Math.min(0.9, 0.1 + v / 50 * 0.8).toFixed(2) + ')';
      const mark = v >= 100 ? '▲▲' : v >= 50 ? '▲' : '';
      return '<td style="background:' + bg + ';color:#000;text-shadow:none" title="' + UI.esc(UI.date(iso) + ': ' + UI.num(v, 1) + ' mm (' + UI.BMKG[cat].label + ')') + '">' + mark + '</td>';
    };
    box.innerHTML = '<table class="heat" aria-label="Heatmap hujan harian: baris bulan, kolom tanggal 1–31"><thead><tr><th></th>' +
      Array.from({ length: 31 }, (_, i) => '<th scope="col">' + (i + 1) + '</th>').join('') + '</tr></thead><tbody>' +
      months.map(m => {
        const [y, mo] = m.split('-').map(Number);
        const days = new Date(y, mo, 0).getDate();
        return '<tr><th scope="row">' + UI.esc(new Date(y, mo - 1, 1).toLocaleDateString('id-ID', { month: 'short', year: 'numeric' })) + '</th>' +
          Array.from({ length: 31 }, (_, i) => {
            if (i >= days) return '<td style="border:0"></td>';
            const iso = m + '-' + String(i + 1).padStart(2, '0');
            return iso < st.f.from || iso > st.f.to ? '<td style="border:0"></td>' : cell(iso);
          }).join('') + '</tr>';
      }).join('') + '</tbody></table>' +
      '<div class="legend"><span><i style="background:rgba(51,255,153,.2)"></i>RENDAH</span><span><i style="background:rgba(51,255,153,.8)"></i>~ 50 MM</span>' +
      '<span><i style="background:var(--amber)"></i>▲ ≥ 50 MM (LEBAT)</span><span><i style="background:var(--alert)"></i>▲▲ ≥ 100 MM</span><span><i></i>TANPA DATA</span></div>';
  }

  function meanSeries(rows) {
    const by = groupBy(rows, 'obs_date');
    return Object.keys(by).sort().map(d => {
      const v = by[d].map(r => r.value).filter(x => x !== null);
      return { x: d, y: v.length ? v.reduce((a, b) => a + b, 0) / v.length : null };
    });
  }

  function renderCorr() {
    const box = UI.$('#anCorr', st.root);
    if (!st.r24.length) { box.innerHTML = UI.emptyHTML('BELUM ADA DATA HUJAN'); return; }
    const w = Math.max(300, Math.min(900, (box.clientWidth || 600) - 16));
    const markers = st.events.map((e, i) => ({ x: e.event_date, label: String(i + 1),
      tip: (i + 1) + '. ' + e.disaster_type_name + ' — ' + e.region_name + ' (' + UI.date(e.event_date) + ')' }));
    box.innerHTML = UI.chartSVG([
      { label: 'Hujan 24 jam (rerata)', points: meanSeries(st.r24) },
      { label: 'Hujan 72 jam (rerata)', cls: 's2', points: meanSeries(st.r72) },
    ], { unit: 'mm', width: w, height: 200, zero: true, markers, label: 'Hujan rerata dan kejadian',
      thresholds: Object.fromEntries(Object.entries(thresholdsFor('RAIN_24H')).filter(([, v]) => v <= 1.5 * Math.max(1, ...st.r72.concat(st.r24).map(o => o.value || 0)))) }) +
      '<div class="legend"><span><i style="background:var(--phos)"></i>HUJAN 24 JAM</span><span><i style="background:var(--cyan)"></i>HUJAN 72 JAM</span>' +
      '<span><i style="background:var(--amber)"></i>KEJADIAN (NOMOR)</span></div>' +
      (st.events.length ? UI.tableHTML([
        { label: '#', get: (e, i) => i + 1 }, { label: 'Tanggal', get: e => UI.date(e.event_date) },
        { label: 'Jenis', key: 'disaster_type_name' }, { label: 'Kecamatan', key: 'region_name' },
        { label: 'Hujan 24j H-0', cls: 'r', get: e => rainOn(st.r24, e, 0) },
        { label: 'H-1', cls: 'r', get: e => rainOn(st.r24, e, -1) }, { label: 'H-2', cls: 'r', get: e => rainOn(st.r24, e, -2) },
        { label: '72j H-0', cls: 'r', get: e => rainOn(st.r72, e, 0) },
        { label: 'Verifikasi', get: e => e.is_verified ? 'TERVERIFIKASI' : 'BELUM' },
      ], st.events, { caption: 'Kejadian dan hujan H-0..H-2' }) : UI.emptyHTML('BELUM ADA KEJADIAN BENCANA TERCATAT DALAM RENTANG INI'));
  }
  function rainOn(rows, e, off) {
    const d = UI.addDays(e.event_date, off);
    const r = rows.find(x => x.region_id === e.region_id && x.obs_date === d);
    return r && r.value !== null ? UI.num(r.value, 1) : UI.NA;
  }

  function renderEval(ev) {
    UI.$('#anEval', st.root).innerHTML =
      '<p class="scr-text" style="margin:0 0 6px">HIT <b>' + UI.int(ev.hit) + '</b> · MISS <b class="v-amber">' + UI.int(ev.miss) + '</b> · FALSE ALARM <b class="v-amber">' + UI.int(ev.false_alarm) + '</b>' +
      ' · POD <b>' + (ev.pod === null ? UI.NA : UI.num(ev.pod, 2)) + '</b> · FAR <b>' + (ev.far === null ? UI.NA : UI.num(ev.far, 2)) + '</b></p>' +
      UI.tableHTML([
        { label: 'Aturan', get: r => r.rule_code || '(kejadian tanpa alert)' },
        { label: 'Hit', cls: 'r', get: r => UI.int(r.hit) }, { label: 'Miss', cls: 'r', get: r => UI.int(r.miss) },
        { label: 'False alarm', cls: 'r', get: r => UI.int(r.false_alarm) },
      ], ev.by_rule || [], { empty: 'BELUM DAPAT DIEVALUASI — BUTUH ALERT WARNING+ DAN KEJADIAN TERVERIFIKASI', caption: 'Evaluasi per aturan' }) +
      '<p class="v-dim" style="margin:6px 0 0;font-size:11px">POD = hit/(hit+miss); FAR = false alarm/(hit+false alarm). "—" bila penyebut nol. ' + UI.esc(ev.definition || '') + '</p>';
  }

  async function loadAlerts() {
    const box = UI.$('#anAlerts', st.root), limit = 50;
    const r = await API.get('/api/alerts' + API.qs({ date_from: st.f.from, date_to: st.f.to, limit, offset: (st.alertPage - 1) * limit }));
    const sel = new Set(st.f.ids);
    UI.$('#anAlertRec', st.root).textContent = UI.int(r.total) + ' ALERT';
    const hours = a => a.acknowledged_at ? (new Date(a.acknowledged_at) - new Date(a.triggered_at)) / 36e5 : null;
    box.innerHTML = UI.tableHTML([
      { label: 'Tanggal', get: a => UI.date(a.observation_date) }, { label: 'Kecamatan', key: 'region_name' },
      { label: 'Tingkat', html: true, get: a => '<span class="' + UI.SEVERITY[a.severity].cls + '">' + UI.esc(UI.SEVERITY[a.severity].label.toUpperCase()) + '</span>' },
      { label: 'Nilai', cls: 'r', get: a => UI.num(a.observed_value, 1) + ' ≥ ' + UI.num(a.threshold_value, 0) },
      { label: 'Aturan', key: 'rule_code' },
      { label: 'Status', get: a => a.acknowledged_at ? 'DIBACA · ' + (a.acknowledged_by_username || '') : 'AKTIF' },
      { label: 'Waktu tanggap', cls: 'r', get: a => hours(a) === null ? UI.NA : UI.num(hours(a), 1) + ' jam' },
      { label: 'Catatan', get: a => a.ack_note || '' },
    ], r.items.filter(a => sel.has(a.region_id)), { empty: 'TIDAK ADA ALERT DALAM RENTANG INI', caption: 'Riwayat alert' }) + UI.pagerHTML(r.total, limit, (st.alertPage - 1) * limit);
    UI.$$('[data-page]', box).forEach(b => b.addEventListener('click', () => { st.alertPage = Number(b.dataset.page); loadAlerts().catch(e => UI.showError('Riwayat alert', e)); }));
  }

  async function exportCsv() {
    const f = filters(); if (!f) return;
    const q = { band: f.band, date_from: f.from, date_to: f.to };
    if (f.ids.length === 1) q.region_id = f.ids[0];
    try { await API.download('/api/hydromet/observations.csv' + API.qs(q), 'observasi_' + f.band + '.csv'); }
    catch (e) { UI.showError('Ekspor CSV', e); }
  }

  return { init };
})();
