// js/diagram.js — Forecast (dulu Diagram; #forecast/terbaru, #forecast/analisa-daerah;
// INTERFACE.md §2 halaman 4, M56, M61). ANALYST & ADMIN.
//
// 4.1 Keadaan terbaru (ctx.tab.mode = 'latest'): GET /api/diagram/latest.
//     Semua band dalam SATU grafik, satu warna per band, 30 hari terakhir.
//     Satuan band berbeda, jadi tiap garis diskalakan ke rentangnya sendiri
//     (0–1) — yang dibandingkan adalah arah dan waktu naik-turunnya, bukan
//     besarnya. Nilai asli ada di tooltip dan tabel. Diperbarui otomatis:
//     halaman memeriksa `updated_at` tiap 5 menit dan menggambar ulang bila
//     ada data baru.
// 4.2 Analisa daerah (mode = 'regions'): kecamatan (+ warna) × tanggal ×
//     band → satu grafik per band (GET /api/diagram/regions). PDF memuat
//     SEMUA band untuk kecamatan & tanggal yang sama (GET /report.pdf).
//
// Forecast 15 hari (M61): grafik data tampil lebih dulu; forecast menyusul
// lewat GET /api/diagram/forecast, satu request per deret (band × AOI atau
// band × kecamatan) supaya palang progres jujur. Setiap grafik punya
// sakelar forecast di bawahnya, menyala bawaannya.
//
// Penjelasan dan ambang tiap band dari GET /api/diagram/bands (sumbernya
// etl/band_catalog.py — ambang yang sama dengan kalimat kondisi dan alert).
'use strict';
Pages['diagram'] = (() => {
  const POLL_MS = 5 * 60 * 1000;
  // Warna awal kecamatan; pengguna bisa menggantinya.
  const REGION_COLORS = ['#ffb000', '#4de1ff', '#33ff99', '#ff6b6b', '#c08cff', '#ff8a00', '#00d1b2', '#ff5fa2',
                         '#8f9bff', '#d9d9d9', '#f4f442', '#7bd389'];
  let st = null;

  async function init(root, ctx) {
    const mode = (ctx.tab && ctx.tab.mode) || 'latest';
    st = { root, ctx, mode, bands: [], hidden: new Set(), timer: null, updatedAt: null, latest: null,
           fcOn: true, fcOff: new Set() };
    const progSel = mode === 'latest' ? '#dgFcProg' : '#dgRegFcProg';
    st.q = UI.forecastQueue(() => st && UI.$(progSel, root));
    UI.$('#dgLatest', root).hidden = mode !== 'latest';
    UI.$('#dgRegions', root).hidden = mode !== 'regions';
    try { const b = await API.get('/api/diagram/bands'); st.bands = b.items; st.lastObs = b.last_obs_date; }
    catch (e) { UI.showError('Forecast', e); return; }
    if (mode === 'latest') {
      await loadLatest();
      st.timer = setInterval(poll, POLL_MS);
    } else {
      await initRegions();
    }
  }

  function destroy() { if (st) { if (st.timer) clearInterval(st.timer); st.q.stop(); } st = null; }

  // ===================================================== 4.1 keadaan terbaru
  const latestKey = code => 'aoi|' + code + '|' + st.latest.date_to;

  function latestForecasts() {
    if (!st.fcOn || !st.latest) return;
    st.q.run(st.latest.bands.map(b => ({ key: latestKey(b.band_code), q: { band: b.band_code, end: st.latest.date_to } })),
      () => { if (st) drawLatest(); });
  }

  async function loadLatest() {
    st.ctx.setStatus('Memuat…');
    let r;
    try { r = await API.get('/api/diagram/latest' + API.qs({ end: st.end || '' })); }
    catch (e) { UI.$('#dgChart', st.root).innerHTML = UI.emptyHTML('GAGAL MEMUAT'); UI.showError('Forecast', e); return; }
    if (!st) return;
    // 30 hari terakhir tanpa satu pun angka harian (backfill/Job Hidromet
    // tertinggal): tampilkan 30 hari s.d. angka harian terakhir, yang punya
    // titik setiap hari untuk 7 band, sekali saja saat halaman dibuka.
    if (!st.end && !st.autoChecked && r.last_obs_date && r.last_obs_date < r.date_from &&
        !r.bands.some(b => b.n_daily)) {
      st.autoChecked = true; st.auto = true; st.end = r.last_obs_date;
      return loadLatest();
    }
    st.autoChecked = true;
    st.latest = r;
    st.updatedAt = r.updated_at;
    if (!st.fcBound) {
      st.fcBound = true;
      UI.$('#dgFcOn', st.root).addEventListener('change', ev => {
        st.fcOn = ev.target.checked;
        if (st.fcOn) latestForecasts(); else st.q.stop();
        drawLatest();
      });
    }
    drawLatest();
    st.ctx.setStatus('Siap · ' + UI.date(r.date_from) + ' – ' + UI.date(r.date_to) + ' · diperiksa ' + clock());
    latestForecasts();
  }

  async function poll() {
    if (!st) return;
    try {
      if (st.end) return;   // jendela tetap di masa lalu: tidak ada yang perlu diperbarui
      const r = await API.get('/api/diagram/latest');
      if (!st) return;
      if (r.updated_at !== st.updatedAt || r.date_to !== st.latest.date_to) {
        st.latest = r; st.updatedAt = r.updated_at; st.q.reset(); drawLatest();
        st.ctx.setStatus('Data baru masuk · diperbarui ' + clock());
        latestForecasts();
      } else {
        st.ctx.setStatus('Siap · tidak ada data baru · diperiksa ' + clock());
      }
    } catch (e) { st.ctx.setStatus('Pemeriksaan otomatis gagal · ' + clock()); }
  }

  const clock = () => { const d = new Date(); return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0'); };

  function drawLatest() {
    const r = st.latest;
    const visible = r.bands.filter(b => !st.hidden.has(b.band_code));
    // Penjelasan cakupan: angka harian per kecamatan bisa tertinggal dari
    // hari ini (Job Hidromet/backfill); titik di rentang itu lalu berasal
    // dari scene Live (±6–12 hari sekali), bukan setiap hari.
    const stale = UI.$('#dgStale', st.root);
    const dailyBands = r.bands.filter(b => b.per_region);
    const nDaily = dailyBands.reduce((s, b) => s + b.n_daily, 0);
    const lastObs = r.last_obs_date || st.lastObs;
    const behind = lastObs && lastObs < r.date_to;
    let note = '';
    if (st.end) {
      const s1 = r.bands.filter(b => b.sparse && !b.n_points).map(b => b.band_name);
      note = (st.auto ? 'ANGKA HARIAN PER KECAMATAN BARU SAMPAI ' + UI.esc(UI.date(st.end).toUpperCase()) +
        ' (BACKFILL/JOB HIDROMET BELUM MENCAPAI HARI INI), JADI GRAFIK MENAMPILKAN 30 HARI S.D. TANGGAL ITU. '
        : 'MENAMPILKAN 30 HARI S.D. ' + UI.esc(UI.date(st.end).toUpperCase()) + '. ') +
        (s1.length ? UI.esc(s1.join(', ').toUpperCase()) + ' TIDAK PUNYA SCENE DI RENTANG INI. ' : '') +
        '<button type="button" class="small" id="dgNow">Tampilkan 30 hari terakhir (scene Live)</button>';
    } else if (behind) {
      note = 'ANGKA HARIAN PER KECAMATAN BARU SAMPAI ' + UI.esc(UI.date(lastObs).toUpperCase()) +
        (nDaily ? '' : ' (DI LUAR RENTANG INI)') + ' — BACKFILL/JOB HIDROMET BELUM MENCAPAI HARI INI. ' +
        'TITIK BERBINGKAI PUTIH BERASAL DARI SCENE LIVE (±6–12 HARI SEKALI). ' +
        '<button type="button" class="small" id="dgLast">Tampilkan 30 hari s.d. ' + UI.esc(UI.date(lastObs)) + '</button>';
    }
    stale.hidden = !note;
    stale.innerHTML = note;
    const now = UI.$('#dgNow', st.root);
    if (now) now.addEventListener('click', () => { st.end = null; st.auto = false; loadLatest(); });
    const lb = UI.$('#dgLast', st.root);
    if (lb) lb.addEventListener('click', () => { st.end = lastObs; st.auto = false; loadLatest(); });

    const fcOf = b => st.fcOn ? st.q.cache[latestKey(b.band_code)] : null;
    const fcMap = {};
    visible.forEach(b => { const f = fcOf(b); if (f && f.points && f.points.length) fcMap[b.band_code] = f; });
    UI.$('#dgChart', st.root).innerHTML = normalizedChart(visible, r.date_from, r.date_to, fcMap);
    bindTips(UI.$('#dgChart .dg-chart', st.root));
    UI.$('#dgChips', st.root).innerHTML = r.bands.map(b => {
      const n = b.n_points;
      return '<button type="button" class="chip" data-band="' + b.band_code + '" aria-pressed="' + !st.hidden.has(b.band_code) + '"' +
        ' title="' + UI.esc(n ? n + ' titik dalam rentang ini' : 'Tidak ada data dalam rentang ini') + '"><span class="swatch" style="background:' + b.color + '"></span>' +
        UI.esc(b.band_name) + ' <span class="v-dim">(' + (n ? UI.int(n) : 'kosong') + ')</span></button>';
    }).join('');
    UI.$$('#dgChips [data-band]', st.root).forEach(btn => btn.addEventListener('click', () => {
      const c = btn.dataset.band;
      if (st.hidden.has(c)) st.hidden.delete(c); else st.hidden.add(c);
      drawLatest();
    }));
    UI.$('#dgExplain', st.root).innerHTML = UI.tableHTML([
      { label: 'Band', html: true, get: b => '<span class="swatch" style="background:' + b.color + '"></span> ' + UI.esc(b.band_name) },
      { label: 'Terakhir', cls: 'r', get: b => { const p = lastPoint(b); return p ? UI.num(p.y, 2) + (b.unit ? ' ' + b.unit : '') : UI.NA; } },
      { label: 'Tanggal', get: b => { const p = lastPoint(b); return p ? UI.date(p.x, 'short') + (p.source === 'scene' ? ' (scene)' : '') : ''; } },
      { label: 'Titik', cls: 'r', get: b => UI.int(b.n_points) + (b.per_region ? ' (' + UI.int(b.n_daily) + ' harian)' : '') },
      { label: 'Rentang biasa (365 hr)', get: b => b.range ? UI.num(b.range[0], 2) + ' – ' + UI.num(b.range[1], 2) + (b.unit ? ' ' + b.unit : '') : UI.NA },
      { label: 'Ambang', get: b => b.thresholds.length ? b.thresholds.map(t => t.label + ' ' + UI.num(t.value, 2)).join(' · ')
        : (b.band_code === 'VV' || b.band_code === 'NDVI') ? 'perubahan antar scene' : UI.NA },
      { label: 'Forecast H+15', get: b => { const f = fcOf(b), p = f && f.points && f.points[f.points.length - 1];
        return !st.fcOn ? 'mati' : !p ? (f ? UI.NA : '…') : UI.num(p.mean, 2) + (b.unit ? ' ' + b.unit : '') + ' (' + UI.num(p.lo, 2) + ' – ' + UI.num(p.hi, 2) + ') · ' + UI.date(p.x, 'short'); } },
      { label: 'Model forecast', get: b => st.fcOn ? UI.forecastDesc(fcOf(b)) : 'mati' },
      { label: 'Penjelasan', get: b => b.about },
    ], visible, { empty: 'SEMUA BAND DISEMBUNYIKAN', caption: 'Nilai terakhir, forecast, dan penjelasan band' });
  }

  // Tooltip titik: tampil saat kursor di atas titik, saat titik difokus
  // (keyboard), atau saat diklik/disentuh. Latarnya warna band; warna teksnya
  // hitam atau putih, mana yang lebih kontras dengan warna itu.
  function inkFor(hex) {
    const m = /^#?([0-9a-f]{6})$/i.exec(hex || ''); if (!m) return '#fff';
    const lin = c => { c /= 255; return c <= .03928 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4; };
    const n = parseInt(m[1], 16);
    const L = .2126 * lin(n >> 16 & 255) + .7152 * lin(n >> 8 & 255) + .0722 * lin(n & 255);
    return (L + .05) / .05 >= 1.05 / (L + .05) ? '#000' : '#fff';
  }
  function bindTips(box) {
    if (!box) return;
    const tip = document.createElement('div');
    tip.className = 'chart-tip dg-tip'; tip.hidden = true; tip.setAttribute('role', 'status');
    box.appendChild(tip);
    let pinned = null;
    const show = el => {
      const parts = el.dataset.tip.split(' · ');
      tip.innerHTML = '<b>' + UI.esc(parts.shift()) + '</b><br>' + UI.esc(parts.join(' · '));
      tip.style.background = el.dataset.color; tip.style.color = inkFor(el.dataset.color);
      tip.hidden = false;
      const bb = box.getBoundingClientRect(), r = el.getBoundingClientRect();
      let left = r.left - bb.left + r.width / 2 - tip.offsetWidth / 2;
      left = Math.max(0, Math.min(left, bb.width - tip.offsetWidth));
      let top = r.top - bb.top - tip.offsetHeight - 6;
      if (top < 0) top = r.bottom - bb.top + 6;
      tip.style.left = left + 'px'; tip.style.top = top + 'px';
    };
    const hide = () => { if (!pinned) tip.hidden = true; };
    UI.$$('.hit', box).forEach(el => {
      el.addEventListener('mouseenter', () => show(el));
      el.addEventListener('mouseleave', () => { if (pinned) show(pinned); else hide(); });
      el.addEventListener('focus', () => show(el));
      el.addEventListener('blur', hide);
      el.addEventListener('click', e => { e.stopPropagation(); pinned = pinned === el ? null : el; if (pinned) show(el); else hide(); });
    });
    box.addEventListener('click', () => { pinned = null; tip.hidden = true; });
  }

  function lastPoint(b) { const pts = b.points.filter(p => p.y !== null); return pts[pts.length - 1] || null; }

  // Grafik SVG semua band. Satuan berbeda, jadi tiap garis diskalakan ke
  // "rentang biasa" band itu (persentil 2–98 dalam 365 hari, dari API):
  // 0 = rendah biasa, 1 = tinggi biasa; nilai di luar rentang dijepit ke tepi.
  // Skala tetap ini membuat garis yang datar tetap tampak datar.
  // Satu titik per tanggal yang berdata. Band harian diputus di hari kosong;
  // Sentinel-1 (`sparse`) memang hanya ada per lintasan sehingga disambung.
  // `fcMap` {band_code: forecast}: sumbu waktu diperpanjang sampai hari
  // forecast terakhir; forecast = garis putus + pita 80% berwarna band,
  // dijepit ke 0–1 supaya pita lebar tidak memipihkan garis data.
  function normalizedChart(bands, from, to, fcMap) {
    const W = 760, H = 280, L = 34, R = 12, T = 14, B = 26;
    const t = d => (UI.parseDate(d) || new Date()).getTime();
    const fcEnd = Math.max(0, ...Object.values(fcMap).map(f => t(f.points[f.points.length - 1].x)));
    const x0 = t(from), x1 = Math.max(t(to), x0 + 864e5, fcEnd);
    const X = v => L + (v - x0) / (x1 - x0) * (W - L - R);
    const Y = v => T + (1 - v) * (H - T - B);
    let g = '';
    if (fcEnd > t(to)) {
      g += '<rect class="fc-zone" x="' + X(t(to)) + '" y="' + T + '" width="' + (W - R - X(t(to))) + '" height="' + (H - T - B) + '"/>' +
        '<text class="fc-lbl" x="' + (X(t(to)) + 4) + '" y="' + (T + 10) + '">FORECAST 15 HARI →</text>';
    }
    [[0, 'rendah'], [0.5, ''], [1, 'tinggi']].forEach(([v, lbl]) => {
      g += '<line class="grid" x1="' + L + '" x2="' + (W - R) + '" y1="' + Y(v) + '" y2="' + Y(v) + '"/>' +
        '<text class="axis" x="' + (L - 4) + '" y="' + (Y(v) + 3) + '" text-anchor="end">' + UI.num(v, 1) + '</text>' +
        (lbl ? '<text class="axis" style="opacity:.6" x="' + (W - R) + '" y="' + (Y(v) - 3) + '" text-anchor="end">' + lbl + ' biasa</text>' : '');
    });
    const days = Math.round((x1 - x0) / 864e5);
    for (let k = 0; k <= days; k++) {
      const d = UI.addDays(from, k), x = X(t(d));
      g += '<line class="grid" x1="' + x + '" x2="' + x + '" y1="' + (H - B) + '" y2="' + (H - B + 3) + '"/>';
      if (k % Math.max(1, Math.ceil(days / 7)) === 0 || k === days)
        g += '<text class="axis" x="' + x + '" y="' + (H - 6) + '" text-anchor="middle">' + UI.date(d, 'short') + '</text>';
    }
    const hits = [];
    let any = false;
    bands.forEach(b => {
      const have = b.points.filter(p => p.y !== null);
      if (!have.length || !b.range) return;
      any = true;
      // Rentang biasa diperluas bila data yang tampil keluar darinya, supaya
      // titik tidak dijepit ke tepi grafik.
      const vs = have.map(p => p.y).concat(fcMap[b.band_code] ? fcMap[b.band_code].points.map(p => p.mean) : []);
      const lo = Math.min(b.range[0], ...vs), hi = Math.max(b.range[1], ...vs), span = hi - lo;
      const n = v => span > 0 ? (v - lo) / span : 0.5;
      b.thresholds.forEach(th => {
        const y = n(th.value);
        if (y < 0 || y > 1) return;
        g += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + Y(y) + '" y2="' + Y(y) + '" style="stroke:' + b.color +
          ';stroke-dasharray:4 3;stroke-width:1;opacity:.7"/>';
        hits.push({ x: W - R - 30, y: Y(y), color: b.color, tip: b.band_name + ' · ambang ' + th.label + ' ' + UI.num(th.value, 2) + (b.unit ? ' ' + b.unit : '') });
      });
      // Garis: angka harian bersebelahan disambung (diputus di hari kosong);
      // titik scene Live (±6–12 hari sekali) disambung antar scene. Band
      // Sentinel-1 (VV, VH, …) hanya ada per lintasan, jadi semua titiknya
      // disambung apa pun sumbernya (scene Live atau angka per kecamatan).
      let prev = null;
      have.forEach(p => {
        if (prev && (b.sparse || p.source === 'scene' && prev.source === 'scene' ||
                     (t(p.x) - t(prev.x)) <= 864e5 * 1.5)) {
          g += '<line class="line" style="stroke:' + b.color + (p.source === 'scene' && !b.sparse ? ';stroke-dasharray:3 2' : '') +
            '" x1="' + X(t(prev.x)) + '" y1="' + Y(n(prev.y)) + '" x2="' + X(t(p.x)) + '" y2="' + Y(n(p.y)) + '"/>';
        }
        prev = p;
      });
      have.forEach(p => {
        const x = X(t(p.x)), y = Y(n(p.y));
        // Titik dari scene Live diberi bingkai putih supaya beda dari angka harian.
        g += '<rect class="dot" style="fill:' + b.color + (p.source === 'scene' && !b.sparse ? ';stroke:#fff;stroke-width:1' : '') +
          '" x="' + (x - 2.5) + '" y="' + (y - 2.5) + '" width="5" height="5"/>';
        hits.push({ x, y, color: b.color, tip: b.band_name + ' · ' + UI.date(p.x) + ': ' + UI.num(p.y, 2) + (b.unit ? ' ' + b.unit : '') +
          (p.source === 'scene' ? ' (scene Live)' : p.source === 'daily' ? ' (harian)' : '') });
      });
      const f = fcMap[b.band_code];
      if (f) {
        const c = v => Math.max(0, Math.min(1, n(v)));
        const last = have[have.length - 1];
        const start = [[X(t(last.x)), Y(n(last.y))]];
        const up = f.points.map(p => [X(t(p.x)), Y(c(p.hi))]), down = f.points.slice().reverse().map(p => [X(t(p.x)), Y(c(p.lo))]);
        g += '<polygon style="fill:' + b.color + ';fill-opacity:.12;stroke:none" points="' + start.concat(up, down).map(q => q.join(',')).join(' ') + '"/>';
        g += '<polyline style="fill:none;stroke:' + b.color + ';stroke-width:2;stroke-dasharray:5 4" points="' +
          start.concat(f.points.map(p => [X(t(p.x)), Y(c(p.mean))])).map(q => q.join(',')).join(' ') + '"/>';
        const u = b.unit ? ' ' + b.unit : '';
        f.points.forEach(p => hits.push({ x: X(t(p.x)), y: Y(c(p.mean)), color: b.color,
          tip: b.band_name + ' · forecast ' + UI.date(p.x) + ': ' + UI.num(p.mean, 2) + u + ' · 80%: ' + UI.num(p.lo, 2) + ' – ' + UI.num(p.hi, 2) + u }));
      }
    });
    if (!any) return UI.emptyHTML('BELUM ADA DATA PADA RENTANG INI');
    hits.forEach(h => { g += '<rect class="hit" tabindex="0" x="' + (h.x - 6) + '" y="' + (h.y - 6) + '" width="12" height="12" data-tip="' +
      UI.esc(h.tip) + '" data-color="' + UI.esc(h.color) + '" aria-label="' + UI.esc(h.tip) + '"></rect>'; });
    return '<div class="chart dg-chart"><svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Semua band, diskalakan ke rentang biasa tiap band' +
      (Object.keys(fcMap).length ? ', dengan forecast 15 hari' : '') + '">' + g + '</svg></div>';
  }

  // ======================================================= 4.2 analisa daerah
  async function initRegions() {
    const $ = s => UI.$(s, st.root);
    let geo;
    try { geo = await Maps.regions(); } catch (e) { UI.showError('Forecast', e); return; }
    const regions = geo.features.map(f => f.properties).sort((a, b) => a.name.localeCompare(b.name, 'id'));
    $('#dgRegionList').innerHTML = regions.map((r, i) =>
      '<div class="region-row"><label class="check"><input type="checkbox" name="rg" value="' + r.region_id + '"' + (i < 2 ? ' checked' : '') + '> ' +
      UI.esc(r.name) + '</label><input type="color" aria-label="Warna ' + UI.esc(r.name) + '" data-color="' + r.region_id + '" value="' +
      REGION_COLORS[i % REGION_COLORS.length] + '"></div>').join('') || UI.emptyHTML('AOI BELUM DIATUR');
    const regionBands = st.bands.filter(b => b.per_region);
    $('#dgBandList').innerHTML = regionBands.map(b => '<label class="check"><input type="checkbox" name="bd" value="' + b.band_code + '"' +
      (b.band_code === 'RAIN_24H' || b.band_code === 'NDVI' ? ' checked' : '') + '> <span class="swatch" style="background:' + b.color + '"></span> ' +
      UI.esc(b.band_name) + '</label>').join('') +
      '<p class="mut" style="font-size:11px;margin:4px 0 0">Sentinel-1 (VV/VH) tidak dihitung per kecamatan; lihat Keadaan terbaru atau Citra › Sentinel-1.</p>';
    // Akhir rentang bawaan = observasi terakhir (bisa lebih tua dari hari ini
    // bila Job Hidromet tertinggal), supaya grafik pertama tidak kosong.
    const today = UI.isoDate(new Date());
    const end = st.lastObs && st.lastObs < today ? st.lastObs : today;
    $('#dgTo').value = end; $('#dgFrom').value = UI.addDays(end, -29);
    UI.$$('[data-range]', st.root).forEach(b => b.addEventListener('click', () => {
      $('#dgTo').value = end; $('#dgFrom').value = UI.addDays(end, -(Number(b.dataset.range) - 1));
    }));
    $('#dgForm').addEventListener('submit', ev => { ev.preventDefault(); UI.busy($('#dgGo'), showRegions); });
    $('#dgPdf').addEventListener('click', () => UI.busy($('#dgPdf'), pdf));
    UI.$$('[data-color]', st.root).forEach(inp => inp.addEventListener('change', () => { if (st.last) drawRegions(st.last); }));
    await showRegions();
  }

  function selection() {
    const $ = s => UI.$(s, st.root);
    const ids = UI.$$('input[name=rg]:checked', st.root).map(x => Number(x.value));
    const bands = UI.$$('input[name=bd]:checked', st.root).map(x => x.value);
    const from = $('#dgFrom').value, to = $('#dgTo').value;
    $('#dgRegionErr').textContent = !ids.length ? 'Pilih minimal satu kecamatan.' : ids.length > 12 ? 'Maksimal 12 kecamatan.' : '';
    if (!ids.length || ids.length > 12) return null;
    if (!from || !to || from > to) { UI.showError('Analisa daerah', { code: 'INVALID_DATE_RANGE' }); return null; }
    return { ids, bands, from, to };
  }
  const colorOf = id => { const el = UI.$('[data-color="' + id + '"]', st.root); return el ? el.value : '#cccccc'; };

  async function showRegions() {
    const sel = selection();
    if (!sel) return;
    if (!sel.bands.length) { UI.$('#dgRegionCharts', st.root).innerHTML = UI.screenHTML({ channel: 'ANALISA', body: UI.emptyHTML('PILIH MINIMAL SATU BAND') }); return; }
    st.ctx.setStatus('Memuat…');
    try {
      st.last = await API.get('/api/diagram/regions' + API.qs({ region_ids: sel.ids.join(','), bands: sel.bands.join(','), date_from: sel.from, date_to: sel.to }));
    } catch (e) { UI.showError('Analisa daerah', e); st.ctx.setStatus('Gagal'); return; }
    drawRegions(st.last);
    st.ctx.setStatus('Siap · ' + st.last.regions.length + ' kecamatan · ' + UI.date(sel.from) + ' – ' + UI.date(sel.to));
    regionForecasts();
  }

  // Forecast dihitung dari data s.d. tanggal akhir rentang terpilih, jadi
  // rentang di masa lalu menampilkan apa yang akan diramalkan saat itu.
  const regionKey = (code, rid) => 'r|' + code + '|' + rid + '|' + st.last.date_to;

  function regionForecasts() {
    const r = st.last;
    if (!r) return;
    const jobs = [];
    r.bands.filter(b => !st.fcOff.has(b.band_code)).forEach(b => r.regions.forEach(g => jobs.push({
      key: regionKey(b.band_code, g.region_id), q: { band: b.band_code, region_id: g.region_id, end: r.date_to } })));
    if (jobs.length) st.q.run(jobs, () => { if (st) drawRegions(st.last); }); else st.q.stop();
  }

  function drawRegions(r) {
    const name = {}; r.regions.forEach(x => { name[x.region_id] = x.region_name; });
    UI.$('#dgRegionCharts', st.root).innerHTML = r.bands.map((b, i) => {
      const on = !st.fcOff.has(b.band_code);
      const fcs = b.series.map(s => on ? st.q.cache[regionKey(b.band_code, s.region_id)] : null);
      const series = b.series.map((s, k) => ({ label: name[s.region_id], color: colorOf(s.region_id), points: s.points,
        forecast: fcs[k] && fcs[k].points && fcs[k].points.length ? fcs[k].points : null }));
      const thr = {}; b.thresholds.forEach(t => { thr[t.label] = t.value; });
      const legend = '<div class="band-chips">' + series.map(s => '<span class="chip static"><span class="swatch" style="background:' + s.color + '"></span>' + UI.esc(s.label) + '</span>').join('') + '</div>';
      const models = on ? '<p class="scr-text v-dim fc-models">' + series.map((s, k) =>
        '<span><span class="swatch" style="background:' + s.color + '"></span> ' + UI.esc(s.label) + ': ' + UI.esc(UI.forecastDesc(fcs[k])) + '</span>').join('') + '</p>' : '';
      return UI.screenHTML({ channel: 'CH-0' + (i + 1) + ' · ' + b.band_name.toUpperCase(), rec: b.unit ? b.unit.toUpperCase() : '', body:
        UI.chartSVG(series, { unit: b.unit, thresholds: thr, zero: b.band_code.startsWith('RAIN'), width: 640, height: 200,
          label: b.band_name + ' per kecamatan' + (on ? ', dengan forecast 15 hari' : '') }) +
        legend + UI.forecastToggleHTML('data-fc-band="' + UI.esc(b.band_code) + '"', on) + models +
        '<p class="scr-text v-dim" style="margin:6px 0 0">' + UI.esc(b.about) +
        (b.thresholds.length ? ' Ambang: ' + b.thresholds.map(t => t.label + ' ' + UI.num(t.value, 2)).join(' · ') + '.' : '') + '</p>' });
    }).join('');
    UI.$$('[data-fc-band]', st.root).forEach(inp => inp.addEventListener('change', () => {
      if (inp.checked) st.fcOff.delete(inp.dataset.fcBand); else st.fcOff.add(inp.dataset.fcBand);
      drawRegions(st.last);
      regionForecasts();
    }));
  }

  async function pdf() {
    const sel = selection();
    if (!sel) return;
    st.ctx.setStatus('Membuat PDF…');
    try {
      await API.download('/api/diagram/report.pdf' + API.qs({ region_ids: sel.ids.join(','), date_from: sel.from, date_to: sel.to,
        colors: sel.ids.map(colorOf).join(',') }), 'analisa_daerah.pdf');
      st.ctx.setStatus('PDF diunduh');
    } catch (e) { st.ctx.setStatus('Gagal'); UI.showError('PDF analisa daerah', e); }
  }

  return { init, destroy };
})();
