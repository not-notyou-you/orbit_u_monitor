// js/monitoring.js — Pantauan Live (INTERFACE.md §2.2, §4.3).
// USER: scene ≤ 30 hari + scene terbaru (disaring API); ADMIN: semua + aksi.
'use strict';
Pages['monitoring'] = (() => {
  const AREA_STATUS = { DRAFT: 'Draf', BACKFILLING: 'Mengisi scene awal', ACTIVE: 'Aktif', WAITING: 'Menunggu scene baru',
    ERROR: 'Galat', DELETING: 'Dihapus', DISABLED: 'Nonaktif' };
  const SERIES = [
    ['sentinel1', 'CH-04 · S1 RERATA VH', 'Rerata VH', 'dB'],
    ['modis', 'CH-05 · MODIS LUAS AIR (NDWI > 0)', 'Luas air NDWI', '%'],
    ['gpm', 'CH-06 · GPM HUJAN 72 JAM', 'Hujan 72 jam', 'mm'],
  ];
  const FC_METHOD = { holt: 'Holt teredam', ses: 'pemulusan eksponensial sederhana', persistence: 'nilai terakhir (data belum cukup)' };
  let st = null;

  function init(root, ctx) {
    st = { root, ctx, areas: [], areaId: null, date: null, card: null, timer: null, isAdmin: ctx.me.role_code === 'ADMIN' };
    const $ = s => UI.$(s, root);
    $('#lmAdmin').hidden = !st.isAdmin;
    $('#lmArea').addEventListener('change', e => { st.areaId = Number(e.target.value); st.date = null; loadCard(); });
    $('#lmCheck').addEventListener('click', ev => adminAction(ev.currentTarget, 'check'));
    $('#lmRetry').addEventListener('click', ev => adminAction(ev.currentTarget, 'retry'));
    $('#lmRetentionSave').addEventListener('click', ev => adminAction(ev.currentTarget, 'retention'));
    $('#lmReport').addEventListener('click', ev => UI.busy(ev.currentTarget, async () => {
      const a = area(); if (!a) return;
      try { await API.download('/api/datasets/' + a.dataset_id + '/report', 'laporan_area_' + a.area_id + '.pdf'); }
      catch (e) { UI.showError('Laporan dataset area', e); }
    }));
    $('#lmLogBtn').addEventListener('click', showLog);
    Excel.mount($('#lmExcel'), ['live_scenes']);
    return loadAreas();
  }

  function destroy() { if (st && st.timer) clearInterval(st.timer); st = null; }
  const area = () => st.areas.find(a => a.area_id === st.areaId);

  async function loadAreas() {
    const $ = s => UI.$(s, st.root);
    try { st.areas = await API.get('/api/live/areas'); }
    catch (e) { $('#lmDeck').innerHTML = UI.screenHTML({ channel: 'SYS', body: UI.emptyHTML('GAGAL MEMUAT AREA') }); UI.showError('Pantauan Live', e); return; }
    if (!st.areas.length) {
      $('#lmArea').innerHTML = '<option>—</option>'; $('#lmArea').disabled = true;
      $('#lmDeck').innerHTML = UI.screenHTML({ channel: 'SYS', rec: '● NO DATA', recCls: 'off',
        body: UI.emptyHTML('BELUM ADA LIVE AREA. ADMINISTRATOR DAPAT MENAMBAHKANNYA DI ADMINISTRASI › LIVE AREA.') });
      st.ctx.setStatus('Belum ada Live Area'); return;
    }
    $('#lmArea').innerHTML = st.areas.map(a => '<option value="' + a.area_id + '">' + UI.esc(a.name) + (a.enabled ? '' : ' (nonaktif)') + '</option>').join('');
    st.areaId = st.areaId || st.areas[0].area_id;
    $('#lmArea').value = st.areaId;
    await loadCard();
  }

  async function loadCard() {
    const deck = UI.$('#lmDeck', st.root);
    st.ctx.setStatus('Memuat kartu…');
    try {
      st.card = await API.get('/api/live/areas/' + st.areaId + '/card' + API.qs({ date: st.date }));
    } catch (e) {
      if (e.code === 'SCENE_OUT_OF_RANGE') { st.date = null; UI.showError('Pantauan Live', e); return loadCard(); }
      deck.innerHTML = UI.screenHTML({ channel: 'SYS', body: UI.emptyHTML('GAGAL MEMUAT KARTU') });
      UI.showError('Pantauan Live', e); return;
    }
    // Area hasil kartu lebih baru dari daftar.
    const i = st.areas.findIndex(a => a.area_id === st.areaId);
    if (i >= 0) st.areas[i] = Object.assign({}, st.areas[i], st.card.area);
    renderSide(); renderDeck();
    st.ctx.setStatus('Siap · ' + st.card.area.name + (st.card.scene ? ' · scene ' + UI.date(st.card.scene.date) : ''));
    // Muat ulang otomatis hanya saat siklus berjalan.
    if (st.timer) { clearInterval(st.timer); st.timer = null; }
    if (st.card.area.running) st.timer = setInterval(() => { if (st) loadCard(); }, 20000);
  }

  function renderSide() {
    const $ = s => UI.$(s, st.root);
    const a = st.card.area, dates = st.card.dates || [], sel = st.card.scene && st.card.scene.date;
    $('#lmMeta').innerHTML = [
      ['Status', (AREA_STATUS[a.status] || a.status) + (a.running ? ' (siklus berjalan)' : '')],
      ['Lokasi', a.location_label], ['Retensi', a.retention + ' scene'],
      ['Diperiksa', a.last_checked_at ? UI.dateTime(a.last_checked_at) : UI.NA],
    ].concat(['ADMIN', 'DATA_ENGINEER'].includes(st.ctx.me.role_code) ? [['Ukuran', UI.bytes(a.total_size_bytes)]] : []).map(([k, v]) => '<dt>' + k + '</dt><dd>' + UI.esc(v || UI.NA) + '</dd>').join('');
    $('#lmDates').innerHTML = dates.length ? dates.map(d => {
      const lv = LiveTiles.levelInfo(d.level);
      return '<button type="button" role="option" data-date="' + d.date + '" aria-selected="' + (d.date === sel) + '">' +
        UI.esc(UI.date(d.date)) + '<span class="lvl">' + UI.esc(lv.label) + (d.status === 'PARTIAL' ? ' · sebagian' : '') + '</span></button>';
    }).join('') : '<p class="mut" style="padding:4px">Belum ada scene.</p>';
    UI.$$('#lmDates [data-date]', st.root).forEach(b => b.addEventListener('click', () => { st.date = b.dataset.date; loadCard(); }));
    $('#lmDatesNote').textContent = st.isAdmin ? 'Administrator melihat semua scene tersimpan.' : 'Scene 30 hari terakhir (dan scene terbaru).';
    $('#lmRetention').value = a.retention;
    const sc = st.card.scene;
    const failed = sc && ['modis', 'gpm'].some(s => (sc.source_status[s] || {}).status === 'FAILED');
    $('#lmRetry').disabled = !failed;
  }

  function wcSummary(sc) {
    const wc = sc.water_change;
    if (!wc) return '<p class="scr-text v-dim" style="margin:0">PERUBAHAN AIR: BELUM ADA SCENE PEMBANDING</p>';
    const orbit = wc.same_orbit === 0 ? '<p class="v-amber" style="margin:6px 0 0">⚠ ORBIT BERBEDA — PERUBAHAN BISA KARENA GEOMETRI PENCITRAAN</p>' : '';
    return '<div class="lm-wc"><span class="lbl">DIBANDING ' + UI.esc(UI.date(wc.ref_date).toUpperCase()) + ':</span>' +
      '<span>AIR BARU <b class="v-alert num">' + UI.num(wc.new_km2, 2) + '</b> km²</span>' +
      '<span>SURUT <b class="num">' + UI.num(wc.receded_km2, 2) + '</b> km²</span>' +
      '<span>TETAP <b class="v-cyan num">' + UI.num(wc.persistent_km2, 2) + '</b> km²</span></div>' + orbit;
  }

  function renderDeck() {
    const deck = UI.$('#lmDeck', st.root);
    const { area: a, scene: sc, dates, forecast } = st.card;
    if (!sc) {
      deck.innerHTML = UI.screenHTML({ channel: 'CH-00 · ' + a.name, rec: a.running ? '● REC' : '● NO DATA', recCls: a.running ? '' : 'off',
        body: UI.emptyHTML(a.running ? 'SIKLUS SEDANG MENGUNDUH DAN MEMPROSES SCENE PERTAMA (15–60 MENIT PER SCENE)' : (a.status_message || 'BELUM ADA SCENE YANG SIAP')) });
      return;
    }
    const s = sc.area_status || {};
    const lv = LiveTiles.levelInfo(s.level);
    const latest = dates.length ? dates[0].date : sc.date;
    const wc = sc.water_change || {};
    const srcLamp = k => { const x = (sc.source_status[k] || {}).status; return '<span class="lamp-row"><i class="lamp ' + (x === 'OK' ? 'ok' : x === 'FAILED' ? 'fail' : 'busy') + '"></i>' +
      { sentinel1: 'S1', modis: 'MODIS', gpm: 'GPM' }[k] + ' ' + UI.esc(x === 'OK' ? 'OK' : x === 'FAILED' ? 'GAGAL' : (x || '?')) + '</span>'; };
    let html = '<div class="readouts">' +
      UI.readoutHTML('STATUS AREA', UI.esc((s.label || lv.label).toUpperCase()), UI.esc(a.name), lv.cls) +
      UI.readoutHTML('SCENE', UI.esc(UI.date(sc.date)), sc.date === latest ? 'TERBARU' : 'TERBARU: ' + UI.esc(UI.date(latest)), 'v-cyan') +
      UI.readoutHTML('AIR BARU', UI.num(wc.new_km2, 2), 'km² · Δ VS SCENE T-1', wc.new_km2 > 0 ? 'v-amber' : '') +
      UI.readoutHTML('AIR SURUT', UI.num(wc.receded_km2, 2), 'km²') +
      '</div>';
    html += UI.screenHTML({ channel: 'CH-00 · KONDISI', rec: '● LIVE', recCls: 'live',
      body: '<p class="scr-text" style="margin:0"><b class="' + lv.cls + '">' + UI.esc((s.label || lv.label).toUpperCase()) + '</b> — ' + UI.esc(s.text || '') + '</p>' +
        '<p style="margin:6px 0;display:flex;gap:12px;flex-wrap:wrap">' + ['sentinel1', 'modis', 'gpm'].map(srcLamp).join('') + '</p>' + wcSummary(sc) });
    html += LiveTiles.rowsHTML(sc.previews || {}, sc.interpretations || {}, { sceneDate: sc.date, sourceStatus: sc.source_status });
    const series = (forecast && forecast.series) || {};
    const chartW = Math.max(300, Math.min(900, deck.clientWidth - 40));
    const method = series.sentinel1 && series.sentinel1.forecast ? FC_METHOD[series.sentinel1.forecast.method] || 'pemulusan eksponensial' : '';
    html += '<div class="lm-charts">' + SERIES.map(([k, ch, label, unit]) => {
      const sr = series[k];
      const body = !sr ? UI.emptyHTML('NO DATA') : UI.chartSVG(
        [{ label, points: (sr.actual || []).map(p => ({ x: p.date, y: p.value })) }],
        { unit, bar: sr.chart === 'bar', label: label + ' per scene', selected: sc.date,
          thresholds: sr.thresholds ? Object.fromEntries(Object.entries(sr.thresholds).map(([n, v]) => [n === 'high' ? 'tinggi' : n === 'alert' ? 'waspada' : n, v])) : null,
          forecast: sr.forecast && sr.forecast.points && sr.forecast.points.length ? { points: sr.forecast.points.map(p => ({ x: p.date, mean: p.mean, lo: p.lo, hi: p.hi })) } : null,
          width: chartW, height: 200 });
      return UI.screenHTML({ channel: ch, rec: unit.toUpperCase(), recCls: 'off', body });
    }).join('') + '</div>';
    html += UI.screenHTML({ channel: 'CATATAN PRAKIRAAN', body: '<p class="scr-text v-amber" style="margin:0">GARIS PUTUS-PUTUS DAN PITA = PRAKIRAAN STATISTIK, BUKAN PERINGATAN' +
      (method ? ' (' + UI.esc(method.toUpperCase()) + ', ' + UI.int(forecast.n_scenes) + ' SCENE)' : '') + '. NILAI AKTUAL = GARIS/BATANG HIJAU.</p>' });
    deck.innerHTML = html;
    // "Lihat 3D" di lightbox: pilihan area/tanggal/lapisan dititipkan ke tab
    // Relief 3D lewat sessionStorage, bukan parameter hash -- router
    // menormalkan hash (history.replaceState) sehingga query akan terhapus
    // sebelum halaman tujuan init.
    LiveTiles.bindLightbox(deck, sc.previews || {}, sc.interpretations || {}, sc.date, {
      action: { label: 'Lihat 3D', onPick: item => {
        Terrain3DHandoff.set({ area_id: st.areaId, date: sc.date, key: item.key });
        st.ctx.go('#aoi-3d');
      } },
    });
  }

  async function adminAction(btn, kind) {
    const a = area(); if (!a) return;
    if (kind === 'check' && !await UI.confirm('Periksa sekarang', 'Jalankan siklus Live untuk "' + a.name + '" sekarang? Sistem akan mencari dan mengunduh scene Sentinel-1 baru beserta MODIS/GPM.', 'Jalankan')) return;
    await UI.busy(btn, async () => {
      try {
        if (kind === 'check') {
          const r = await API.post('/api/live/areas/' + a.area_id + '/check');
          UI.info('Periksa sekarang', r.started ? 'Siklus dimulai. Kartu akan diperbarui otomatis.' : 'Siklus untuk area ini sedang berjalan.');
        } else if (kind === 'retry') {
          const d = st.card.scene.date;
          const r = await API.post('/api/live/areas/' + a.area_id + '/scenes/' + d + '/retry');
          UI.info('Coba ulang', r && r.started === false ? (r.message || 'Siklus area ini sedang berjalan.') : 'MODIS/GPM untuk scene ' + UI.date(d) + ' dicoba ulang.');
        } else {
          const n = Number(UI.$('#lmRetention', st.root).value);
          if (!Number.isInteger(n) || n < 1 || n > 60) { UI.showError('Retensi', 'Retensi harus bilangan bulat 1–60.'); return; }
          if (n < a.retention && !await UI.confirm('Ubah retensi', 'Retensi diturunkan dari ' + a.retention + ' ke ' + n + '. Scene tertua di luar batas akan dihapus permanen. Lanjutkan?', 'Simpan')) return;
          await API.patch('/api/live/areas/' + a.area_id, { retention: n });
          UI.info('Ubah retensi', 'Retensi disimpan: ' + n + ' scene.');
        }
        loadCard();
      } catch (e) { UI.showError('Aksi Administrator', e); }
    });
  }

  async function showLog() {
    const a = area(); if (!a) return;
    let ev = [], log = [];
    try { [ev, log] = await Promise.all([API.get('/api/live/areas/' + a.area_id + '/events'), API.get('/api/live/areas/' + a.area_id + '/log')]); }
    catch (e) { UI.showError('Log siklus', e); return; }
    UI.dialog({ title: 'Log siklus — ' + a.name, wide: 'x', buttons: [{ label: 'Tutup', value: true, default: true, cancel: true }],
      body: UI.screenHTML({ channel: 'CH-LOG · LANGKAH SIKLUS', body: '<div class="scr-log">' + (ev.length ? ev.slice(0, 80).map(x =>
          '<div><span class="v-dim">' + UI.esc(UI.dateTime(x.at)) + '</span> ' + UI.esc(x.step) + ' <span class="' + (x.status === 'FAILED' ? 'v-alert' : x.status === 'OK' ? '' : 'v-amber') + '">' + UI.esc(x.status) + '</span> ' + UI.esc(x.message || '') + '</div>').join('') : UI.emptyHTML()) + '</div>' }) +
        '<div style="height:8px"></div>' +
        UI.screenHTML({ channel: 'CH-LOG · SCENE (TERMASUK YANG DIHAPUS)', body: UI.tableHTML([
          { label: 'Tanggal', get: r => UI.date(r.date) }, { label: 'Status', key: 'status' },
          { label: 'Dibuat', get: r => UI.dateTime(r.created_at) },
          { label: 'Dihapus', get: r => r.deleted_at ? UI.dateTime(r.deleted_at) + ' (' + (r.delete_reason || '') + ')' : '' },
          { label: 'Dibebaskan', cls: 'r', get: r => r.freed_bytes ? UI.bytes(r.freed_bytes) : '' },
        ], log) }) });
  }

  return { init, destroy };
})();
