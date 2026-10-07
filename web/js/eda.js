// js/eda.js — Data › EDA (#data/eda, INTERFACE.md §2 halaman 6.6, M56).
// GET /api/data/eda?source=…&date_from=…&date_to=… → per variabel: n,
// kekosongan, statistik deskriptif, histogram, pencilan; korelasi Pearson
// berpasangan; kelengkapan per hari. GPM/MODIS: unit analisis kecamatan × hari
// (region_observations). Sentinel-1: scene × band (quality_metrics).
'use strict';
Pages['eda'] = (() => {
  let st = null;

  async function init(root, ctx) {
    st = { root, ctx };
    const $ = s => UI.$(s, root);
    // Akhir rentang bawaan = tanggal terakhir yang punya angka per kecamatan
    // untuk satelit terpilih (Job Hidromet bisa tertinggal dari hari ini).
    const today = UI.isoDate(new Date());
    let last = {};
    try { (await API.get('/api/data/summary')).sources.forEach(s => { last[s.key] = s.key === 's1' ? s.last_date : s.last_obs_date; }); }
    catch (e) { last = {}; }
    const endFor = () => { const l = last[$('#edSource').value]; return l && l < today ? l : UI.addDays(today, -1); };
    const setRange = days => { const end = endFor(); $('#edTo').value = end; $('#edFrom').value = UI.addDays(end, -(days - 1)); };
    setRange(90);
    $('#edSource').addEventListener('change', () => setRange(90));
    UI.$$('[data-range]', root).forEach(b => b.addEventListener('click', () => setRange(Number(b.dataset.range))));
    $('#edForm').addEventListener('submit', ev => { ev.preventDefault(); UI.busy($('#edGo'), run); });
    await run();
  }

  async function run() {
    const $ = s => UI.$(s, st.root);
    const from = $('#edFrom').value, to = $('#edTo').value;
    if (!from || !to || from > to) { UI.showError('EDA', { code: 'INVALID_DATE_RANGE' }); return; }
    st.ctx.setStatus('Menghitung…');
    let r;
    try { r = await API.get('/api/data/eda' + API.qs({ source: $('#edSource').value, date_from: from, date_to: to })); }
    catch (e) { $('#edOut').innerHTML = UI.emptyHTML('GAGAL MEMUAT'); UI.showError('EDA', e); return; }
    if (!st) return;
    $('#edOut').innerHTML = overview(r) + variables(r) + histograms(r) + correlation(r) + completeness(r) + extras(r);
    st.ctx.setStatus('Siap · ' + UI.int(r.n_rows) + ' baris · ' + r.unit_of_analysis);
  }

  function overview(r) {
    const vars = r.variables || [];
    const miss = vars.length ? vars.reduce((s, v) => s + (v.missing_pct || 0), 0) / vars.length : null;
    return '<div class="readouts">' +
      UI.readoutHTML('BARIS', UI.int(r.n_rows), UI.esc(r.unit_of_analysis.toUpperCase())) +
      UI.readoutHTML('VARIABEL', UI.int(vars.length), UI.int(r.n_days) + ' HARI' + (r.n_regions ? ' · ' + UI.int(r.n_regions) + ' KEC.' : '')) +
      UI.readoutHTML('KOSONG RATA-RATA', miss === null ? UI.NA : UI.num(miss, 1) + '%', 'TERHADAP SEL YANG DIHARAPKAN', miss > 30 ? 'v-amber' : '') +
      (r.n_scenes !== undefined ? UI.readoutHTML('SCENE', UI.int(r.n_scenes), UI.int(r.n_invalid) + ' NONAKTIF') : '') + '</div>';
  }

  function variables(r) {
    const n = (v, d) => v === null || v === undefined ? UI.NA : UI.num(v, d === undefined ? 2 : d);
    return UI.screenHTML({ channel: 'CH-01 · STATISTIK DESKRIPTIF', body: UI.tableHTML([
      { label: 'Variabel', html: true, get: v => '<span class="swatch" style="background:' + v.color + '"></span> ' + UI.esc(v.band_code) },
      { label: 'n', cls: 'r', get: v => UI.int(v.n) },
      { label: 'Kosong', cls: 'r', html: true, get: v => '<span class="' + (v.missing_pct > 30 ? 'v-amber' : '') + '">' + n(v.missing_pct, 1) + '%</span>' },
      { label: 'Rerata', cls: 'r', get: v => n(v.mean) }, { label: 'Std', cls: 'r', get: v => n(v.std) },
      { label: 'Min', cls: 'r', get: v => n(v.min) }, { label: 'Q1', cls: 'r', get: v => n(v.q1) }, { label: 'Median', cls: 'r', get: v => n(v.median) },
      { label: 'Q3', cls: 'r', get: v => n(v.q3) }, { label: 'Maks', cls: 'r', get: v => n(v.max) }, { label: 'Skew', cls: 'r', get: v => n(v.skew) },
      { label: 'Pencilan', cls: 'r', html: true, get: v => '<span class="' + (v.outliers ? 'v-amber' : '') + '">' + UI.int(v.outliers) + '</span>' },
    ], r.variables, { empty: 'TIDAK ADA DATA PADA RENTANG INI', caption: 'Statistik deskriptif per variabel' }) });
  }

  function histogram(v) {
    const W = 220, H = 70, bins = v.histogram || [];
    if (!bins.length) return UI.emptyHTML('NO DATA');
    const max = Math.max(...bins.map(b => b.count)) || 1;
    const bw = W / bins.length;
    const bars = bins.map((b, i) => {
      const h = b.count / max * (H - 14);
      return '<rect x="' + (i * bw + 1) + '" y="' + (H - 12 - h) + '" width="' + Math.max(1, bw - 2) + '" height="' + h + '" style="fill:' + v.color + '">' +
        '<title>' + UI.esc(UI.num(b.from, 2) + ' – ' + UI.num(b.to, 2) + ': ' + b.count) + '</title></rect>';
    }).join('');
    return '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Histogram ' + UI.esc(v.band_code) + '">' + bars +
      '<text class="axis" x="0" y="' + (H - 2) + '">' + UI.esc(UI.num(bins[0].from, 1)) + '</text>' +
      '<text class="axis" x="' + W + '" y="' + (H - 2) + '" text-anchor="end">' + UI.esc(UI.num(bins[bins.length - 1].to, 1)) + '</text></svg>';
  }

  function histograms(r) {
    const vars = (r.variables || []).filter(v => v.n);
    if (!vars.length) return '';
    return UI.screenHTML({ channel: 'CH-02 · SEBARAN (HISTOGRAM)', body: '<div class="hist-grid">' + vars.map(v =>
      '<div class="chart hist"><p class="lbl" style="margin:0 0 2px">' + UI.esc(v.band_code) + '</p>' + histogram(v) + '</div>').join('') + '</div>' });
  }

  function correlation(r) {
    const c = r.correlation;
    if (!c || c.variables.length < 2) return '';
    const cell = x => {
      if (x.r === null) return '<td class="na" title="n = ' + x.n + '">' + UI.NA + '</td>';
      const a = Math.min(1, Math.abs(x.r));
      const bg = x.r >= 0 ? 'rgba(51,255,153,' + (a * 0.6) + ')' : 'rgba(255,59,59,' + (a * 0.6) + ')';
      return '<td style="background:' + bg + '" title="n = ' + x.n + '">' + UI.num(x.r, 2) + '</td>';
    };
    return UI.screenHTML({ channel: 'CH-03 · KORELASI PEARSON', body: '<div class="table-wrap"><table class="heat"><thead><tr><th></th>' +
      c.variables.map(v => '<th scope="col">' + UI.esc(v) + '</th>').join('') + '</tr></thead><tbody>' +
      c.matrix.map((row, i) => '<tr><th scope="row">' + UI.esc(c.variables[i]) + '</th>' + row.map(cell).join('') + '</tr>').join('') +
      '</tbody></table></div><p class="scr-text v-dim" style="margin:6px 0 0">Hijau = searah, merah = berlawanan; makin pekat makin kuat. Arahkan kursor untuk jumlah pasangan.</p>' });
  }

  function completeness(r) {
    if (!r.completeness || !r.completeness.length) return '';
    const vars = (r.variables || []).map(v => v.band_code);
    const color = {}; (r.variables || []).forEach(v => { color[v.band_code] = v.color; });
    const series = vars.map(v => ({ label: v, color: color[v], points: r.completeness.map(d => ({ x: d.date, y: d[v] })) }));
    return UI.screenHTML({ channel: 'CH-04 · KELENGKAPAN PER HARI (% KECAMATAN TERISI)', body:
      UI.chartSVG(series, { unit: '%', zero: true, width: 640, height: 170, label: 'Kelengkapan per hari' }) +
      '<div class="band-chips">' + series.map(s => '<span class="chip static"><span class="swatch" style="background:' + s.color + '"></span>' + UI.esc(s.label) + '</span>').join('') + '</div>' });
  }

  function extras(r) {
    const rows = [];
    if (r.valid_fraction) rows.push(['Fraksi piksel valid (rerata)', UI.num(r.valid_fraction.mean, 3) + ' (min ' + UI.num(r.valid_fraction.min, 2) + ')']);
    if (r.run_types && Object.keys(r.run_types).length) rows.push(['Run IMERG', Object.entries(r.run_types).map(([k, n]) => k + ': ' + UI.int(n)).join(' · ')]);
    if (r.orbits && Object.keys(r.orbits).length) rows.push(['Orbit (arah relatif)', Object.entries(r.orbits).map(([k, n]) => k + ': ' + UI.int(n)).join(' · ')]);
    if (r.revisit_gap_days && r.revisit_gap_days.n) rows.push(['Jeda antar akuisisi (hari)', 'median ' + UI.num(r.revisit_gap_days.median, 1) + ', maks ' + UI.num(r.revisit_gap_days.max, 0)]);
    if (r.file_size_mb && r.file_size_mb.n) rows.push(['Ukuran berkas mentah (MB)', 'median ' + UI.num(r.file_size_mb.median, 0) + ', total ' + UI.num(r.file_size_mb.mean * r.file_size_mb.n, 0)]);
    if (!rows.length) return '';
    return UI.screenHTML({ channel: 'CH-05 · METADATA', body: '<dl class="kv">' + rows.map(([k, v]) => '<dt>' + UI.esc(k.toUpperCase()) + '</dt><dd>' + UI.esc(v) + '</dd>').join('') + '</dl>' });
  }

  return { init };
})();
