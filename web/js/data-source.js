// js/data-source.js — Data › Satelit (#data/satelit/<sentinel-1|modis|gpm>, INTERFACE.md §2
// halaman 6.2, M56, M67). Satu tab untuk ketiga satelit: pemilih di atas
// mengganti segmen ketiga hash, router memanggil onSub, dan isi dimuat ulang
// tanpa membuang fragmen. Dulu tiga tab terpisah (#data/sentinel-1, …).
//
// * Daftar: GET /api/data/{src}/items (termasuk yang dinonaktifkan).
// * Ubah/hapus: PATCH .../items/{id} {is_valid, reason} (soft delete, alasan
//   wajib, bisa dipulihkan) dan POST .../items/{id}/reprocess. Tidak ada
//   "tambah manual" (M24).
// * Backfill: POST /api/data/{src}/backfill.
//   GPM/MODIS = Job Hidromet, Sentinel-1 = siklus Live dibatasi rentang (M58);
//   keduanya di thread latar, progres + log dibaca dari
//   GET /api/data/backfill/runs/{id}?since=n tiap 2 detik selama berjalan.
//
// M74: backfill satu baris di atas, kotak proses backfill hanya tampil bila
// ada run atau backfill dari proses lain; riwayat dan data tersimpan jadi dua
// tab. Kolom Aksi (dua tombol per baris × 50 baris) diganti klik baris →
// dialog rincian dengan Proses ulang dan Nonaktifkan/Pulihkan.
'use strict';
Pages['data-source'] = (() => {
  const LABEL = { s1: 'Sentinel-1', gpm: 'GPM', modis: 'MODIS' };
  const HELP = {
    s1: 'Mengisi dataset utama dengan setiap lintasan Sentinel-1 yang menutup AOI pada rentang ini (hanya 1 tahun terakhir; lebih lama lewat Katalog Dataset): unduh, olah, gambar, dan angka per kecamatan. Tanggal yang sudah ada dilewati.',
    gpm: 'Menjalankan Job Hidromet (GPM) per tanggal yang belum selesai: unduh granule, hitung hujan per kecamatan, cek alert. Tanggal yang sudah selesai dilewati.',
    modis: 'Mengisi tanggal yang belum punya angka MODIS (genangan, NDVI, NDWI). Job Hidromet ikut memastikan GPM tanggal itu. Tanggal yang sudah lengkap dilewati.',
  };
  const RUN_STATUS = { RUNNING: ['BERJALAN', 'v-cyan'], COMPLETED: ['SELESAI', ''], FAILED: ['GAGAL', 'v-alert'], SKIPPED: ['DILEWATI', 'v-amber'] };
  const LIMIT = 50;
  // Segmen hash → kunci API. Urutan = urutan pemilih.
  const SUB = { 'sentinel-1': 's1', modis: 'modis', gpm: 'gpm' };
  let st = null;

  async function init(root, ctx) {
    st = { root, ctx, src: SUB[ctx.sub] || 's1', page: 1, run: null, lines: [], poll: null };
    const $ = s => UI.$(s, root);
    $('#dsSats').innerHTML = Object.entries(SUB).map(([sub, k]) =>
      '<a href="#data/satelit/' + sub + '" data-src="' + k + '">' + UI.esc(LABEL[k]) + '</a>').join('');
    const today = UI.isoDate(new Date());
    $('#dsBfTo').value = UI.addDays(today, -1); $('#dsBfFrom').value = UI.addDays(today, -7);
    $('#dsBackfill').addEventListener('submit', ev => { ev.preventDefault(); startBackfill(); });
    $('#dsFilter').addEventListener('submit', ev => { ev.preventDefault(); st.page = 1; UI.busy($('#dsApply'), loadItems); });
    UI.bindTabs(root, tab => { $('#dsHistPane').hidden = tab !== 'hist'; $('#dsItemsPane').hidden = tab !== 'items'; });
    await refresh();
  }

  // Satelit lain dipilih: hanya isi yang dimuat ulang.
  async function onSub(sub) {
    if (!st) return;
    const src = SUB[sub] || 's1';
    if (src === st.src) return;
    if (st.poll) { clearTimeout(st.poll); st.poll = null; }
    Object.assign(st, { src, page: 1, run: null, lines: [], hydromet: null, wasRunning: false });
    await refresh();
  }

  async function refresh() {
    const $ = s => UI.$(s, st.root);
    UI.$$('#dsSats a', st.root).forEach(a => a.toggleAttribute('aria-current', a.dataset.src === st.src));
    $('#dsBfHelp').textContent = HELP[st.src];
    $('#dsRun').innerHTML = ''; $('#dsHist').innerHTML = UI.loadingHTML(); $('#dsTable').innerHTML = UI.loadingHTML();
    await Promise.all([loadItems(), loadBackfill()]);
  }

  function destroy() { if (st && st.poll) clearTimeout(st.poll); st = null; }

  // ------------------------------------------------------------------ daftar
  async function loadItems() {
    const $ = s => UI.$(s, st.root);
    const from = $('#dsFrom').value, to = $('#dsTo').value;
    if (from && to && from > to) { UI.showError('Saring daftar', { code: 'INVALID_DATE_RANGE' }); return; }
    const src = st.src;
    let r;
    try {
      r = await API.get('/api/data/' + st.src + '/items' + API.qs({ date_from: from, date_to: to, status: $('#dsStatus').value,
        q: $('#dsQ').value.trim(), limit: LIMIT, offset: (st.page - 1) * LIMIT }));
    } catch (e) { if (st && st.src === src) { $('#dsTable').innerHTML = UI.emptyHTML('GAGAL MEMUAT'); UI.showError('Data ' + LABEL[src], e); } return; }
    if (!st || st.src !== src) return;
    $('#dsCount').textContent = '(' + UI.int(r.total) + ')';
    $('#dsCountRec').textContent = UI.int(r.total) + ' ITEM';
    st.items = r.items;
    const cols = st.src === 's1'
      ? [{ label: 'ID', key: 'id' }, { label: 'Produk', get: x => x.name.length > 42 ? x.name.slice(0, 42) + '…' : x.name },
         { label: 'Akuisisi', get: x => UI.dateTime(x.acquisition_datetime) }, { label: 'Orbit', get: x => (x.orbit_direction || '') + ' ' + (x.relative_orbit || '') },
         { label: 'MB', cls: 'r', get: x => UI.num(x.raw_file_size_mb, 0) }]
      : [{ label: 'ID', key: 'id' }, { label: 'Produk', key: 'name' }, { label: 'Tile', key: 'tile_id' },
         { label: 'Tanggal', get: x => UI.date(x.acquisition_date) }, { label: 'Run', key: 'run_type' }];
    cols.push({ label: 'Produk turunan', cls: 'r', get: x => UI.int(x.n_products) });
    cols.push({ label: 'Status', html: true, get: x => x.is_valid ? 'AKTIF' : '<span class="v-amber" title="' + UI.esc(x.invalid_reason || '') + '">NONAKTIF</span>' });
    $('#dsTable').innerHTML = UI.tableHTML(cols, r.items, { empty: 'BELUM ADA DATA. JALANKAN BACKFILL UNTUK MENGISI.', caption: 'Data ' + LABEL[st.src],
      rowAttr: x => 'class="ds-row" tabindex="0" data-id="' + x.id + '" aria-label="Item #' + x.id + ': buka rincian dan aksi"' }) +
      UI.pagerHTML(r.total, LIMIT, (st.page - 1) * LIMIT);
    UI.$$('#dsTable [data-page]', st.root).forEach(b => b.addEventListener('click', () => { st.page = Number(b.dataset.page); loadItems(); }));
    UI.$$('#dsTable .ds-row', st.root).forEach(tr => {
      const open = () => openItem(Number(tr.dataset.id));
      tr.addEventListener('click', open);
      tr.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } });
    });
    st.ctx.setStatus('Siap · ' + UI.int(r.total) + ' item');
  }

  // Rincian satu item + aksinya (dulu dua tombol di setiap baris tabel).
  async function openItem(id) {
    const x = (st.items || []).find(i => i.id === id);
    if (!x) return;
    const kv = st.src === 's1'
      ? [['PRODUK', x.name], ['AKUISISI', UI.dateTime(x.acquisition_datetime)], ['ORBIT', (x.orbit_direction || '') + ' ' + (x.relative_orbit || '')],
         ['UKURAN', UI.num(x.raw_file_size_mb, 0) + ' MB']]
      : [['PRODUK', x.name], ['TILE', x.tile_id], ['TANGGAL', UI.date(x.acquisition_date)], ['RUN', x.run_type]];
    kv.push(['PRODUK TURUNAN', UI.int(x.n_products)], ['STATUS', x.is_valid ? 'AKTIF' : 'NONAKTIF' + (x.invalid_reason ? ' — ' + x.invalid_reason : '')]);
    const v = await UI.dialog({ title: LABEL[st.src] + ' · item #' + id, wide: true,
      body: '<div class="screen"><div class="screen-inner"><span class="scr-ch">RINCIAN</span><dl class="kv">' +
        kv.map(([k, val]) => '<dt>' + k + '</dt><dd style="overflow-wrap:anywhere">' + UI.esc(val || UI.NA) + '</dd>').join('') + '</dl></div></div>',
      buttons: [{ label: 'Proses ulang…', value: 'reproc' }, x.is_valid ? { label: 'Nonaktifkan…', value: 'off' } : { label: 'Pulihkan', value: 'on' },
        { label: 'Tutup', value: null, default: true, cancel: true }] });
    if (v === 'reproc') reprocess(id);
    else if (v === 'off') deactivate(id);
    else if (v === 'on') setValid(id, true, null);
  }

  async function deactivate(id) {
    const reason = await UI.dialog({ title: 'Nonaktifkan item #' + id, body:
      '<p>Item ini disembunyikan dari pengolahan dan daftar, tetapi barisnya tidak dihapus dan bisa dipulihkan. Alasan wajib diisi.</p>' +
      '<div class="field"><label for="dsReason">Alasan *</label><textarea id="dsReason" maxlength="500"></textarea></div>',
      buttons: [{ label: 'Nonaktifkan', value: 'ok', default: true }, { label: 'Batal', value: null, cancel: true }],
      collect: (win, v) => v === 'ok' ? UI.$('#dsReason', win).value.trim() : null });
    if (reason === null || reason === undefined) return;
    if (!reason) { UI.showError('Nonaktifkan item', { code: 'REASON_REQUIRED' }); return; }
    await setValid(id, false, reason);
  }

  async function setValid(id, valid, reason) {
    try { await API.patch('/api/data/' + st.src + '/items/' + id, { is_valid: valid, reason: reason }); await loadItems(); }
    catch (e) { UI.showError(valid ? 'Pulihkan item' : 'Nonaktifkan item', e); }
  }

  async function reprocess(id) {
    const ok = await UI.confirm('Proses ulang item #' + id,
      st.src === 's1' ? 'Scene Live tanggal ini dicoba ulang (unduh dan olah ulang). Scene milik dataset Katalog diproses ulang dengan menjalankan ulang dataset-nya.'
        : 'Job Hidromet tanggal granule ini dijalankan ulang: angka per kecamatan dan alert dihitung lagi. Bisa memakan beberapa menit.', 'Proses ulang');
    if (!ok) return;
    try { const r = await API.post('/api/data/' + st.src + '/items/' + id + '/reprocess', {}); UI.info('Proses ulang', 'Diterima: ' + (r.job || '') + ' ' + UI.date(r.date) + '. Hasilnya tampil di Riwayat setelah selesai.'); }
    catch (e) { UI.showError('Proses ulang', e); }
  }

  // ---------------------------------------------------------------- backfill
  async function startBackfill() {
    const $ = s => UI.$(s, st.root);
    const from = $('#dsBfFrom').value, to = $('#dsBfTo').value;
    const days = from && to ? Math.round((UI.parseDate(to) - UI.parseDate(from)) / 864e5) + 1 : 0;
    $('#dsBfErr').textContent = !from || !to || days < 1 ? 'Isi tanggal awal dan akhir (awal ≤ akhir).' : days > 366 ? 'Rentang maksimal 366 hari.' : '';
    if ($('#dsBfErr').textContent) return;
    const ok = await UI.confirm('Backfill ' + LABEL[st.src], 'Rentang ' + UI.date(from) + ' – ' + UI.date(to) + ' (' + days + ' hari). ' + HELP[st.src] +
      ' Proses berjalan di latar dan memakai kuota unduhan satelit.', 'Jalankan');
    if (!ok) return;
    await UI.busy($('#dsBfGo'), async () => {
      try {
        const r = await API.post('/api/data/' + st.src + '/backfill', { date_from: from, date_to: to });
        st.run = r.run; st.lines = [];
        await loadBackfill();
      } catch (e) { UI.showError('Backfill ' + LABEL[st.src], e); }
    });
  }

  async function loadBackfill() {
    if (!st) return;
    const src = st.src;
    let r;
    try { r = await API.get('/api/data/' + src + '/backfill'); }
    catch (e) { if (st && st.src === src) UI.$('#dsHist', st.root).innerHTML = UI.emptyHTML('GAGAL MEMUAT'); return; }
    if (!st || st.src !== src) return;
    if (!st.run && r.runs.length) st.run = r.runs[0];
    st.hydromet = r.hydromet || null;
    if (st.src === 's1') {
      // Siklus Live/backfill S1 dari proses lain (skrip, penjadwal): progresnya
      // dibaca dari live_areas lewat /api/data/activity, sama seperti hidromet.
      const a = await API.get('/api/data/activity').catch(() => null);
      if (!st || st.src !== src) return;
      const live = a && (a.live || []).find(l => l.running);
      st.hydromet = live ? { external: true, live } : null;
    }
    renderHydrometHistory(r.days || [], r.stale_dates || []);
    await pollRun();
    // Backfill dari proses lain (skrip, scheduler, worker lain) tidak punya
    // log di sini; perbarui progresnya dari DB tiap 10 detik.
    if (st && st.hydromet && st.hydromet.external && !(st.run && st.run.status === 'RUNNING')) {
      st.poll = setTimeout(() => { loadBackfill(); loadItems(); }, 10000);
    }
  }

  // GPM/MODIS: baris log baru diambil sejak indeks terakhir (since).
  async function pollRun() {
    if (!st) return;
    if (st.poll) { clearTimeout(st.poll); st.poll = null; }
    if (!st.run) { renderRun(null); return; }
    try {
      const id = st.run.run_id;
      const r = await API.get('/api/data/backfill/runs/' + id + API.qs({ since: st.lines.length }));
      if (!st || !st.run || st.run.run_id !== id) return;
      st.lines = st.lines.concat(r.lines || []);
      st.run = r;
      renderRun(r);
      if (r.status === 'RUNNING') st.poll = setTimeout(pollRun, 2000);
      else if (st.wasRunning) { st.wasRunning = false; loadItems(); loadBackfill(); }
      if (r.status === 'RUNNING') st.wasRunning = true;
    } catch (e) {
      if (e.status === 404) { st.run = null; renderRun(null); }
    }
  }

  function renderExternal(h) {
    const $ = s => UI.$(s, st.root);
    if (h.live) {
      const l = h.live, j = l.job, p = l.progress, c = p && p.current;
      $('#dsRunRec').textContent = '● BERJALAN';
      $('#dsRunRec').className = 'scr-rec live';
      $('#dsRun').innerHTML = '<p class="scr-text" style="margin:0">BACKFILL SENTINEL-1 DATASET UTAMA SEDANG BERJALAN ' +
        '(scripts/backfill_s1.py atau penjadwal). Progres dibaca dari basis data; rincian di Data › Ringkasan.</p>' +
        (p && p.dates_total ? UI.progressHTML(p.percent, 'Progres backfill Sentinel-1') : '') +
        '<dl class="kv" style="margin-top:6px"><dt>STATUS</dt><dd>' + UI.esc(l.status_message || UI.NA) + '</dd>' +
        (p && p.dates_total ? '<dt>PROGRES</dt><dd>' + UI.int(p.dates_done) + '/' + UI.int(p.dates_total) + ' tanggal · ' +
          UI.int(p.frames_done) + '/' + UI.int(p.frames_total) + ' frame (' + UI.num(p.percent, 1) + '%)</dd>' +
          '<dt>SEDANG DIKERJAKAN</dt><dd>' + (c ? UI.esc((c.date ? UI.date(c.date) + ' · ' : '') + (c.stage || '') + ' · ' + (c.message || '')) : UI.NA) + '</dd>' +
          '<dt>PERKIRAAN SELESAI</dt><dd>' + UI.esc(p.eta ? UI.dateTime(p.eta) + ' WIB' : 'menghitung…') + '</dd>' : '') +
        '<dt>SCENE TERSIMPAN</dt><dd>' + UI.int(l.n_ready) + '</dd>' +
        (j ? '<dt>JOB #' + j.job_id + '</dt><dd>' + UI.esc(UI.date(j.date_range_start)) + ' – ' + UI.esc(UI.date(j.date_range_end)) + ' · ' +
          UI.int(j.downloaded_count) + ' diunduh, ' + UI.int(j.processed_count) + ' diproses dari ' + UI.int(j.total_scenes) + ' frame</dd>' : '') + '</dl>';
      return;
    }
    $('#dsRunRec').textContent = '● BERJALAN';
    $('#dsRunRec').className = 'scr-rec live';
    $('#dsRun').innerHTML = '<p class="scr-text" style="margin:0">BACKFILL HIDROMET SEDANG BERJALAN DI PROSES LAIN ' +
      '(scripts/backfill_hydromet.py, penjadwal, atau server API lain). Lognya ada di proses itu; progres di bawah dibaca dari basis data.</p>' +
      '<dl class="kv" style="margin-top:6px"><dt>SEDANG DIKERJAKAN</dt><dd>' + UI.esc(h.current_date ? UI.date(h.current_date) : UI.NA) +
      (h.current_started_at ? ' (mulai ' + UI.esc(UI.dateTime(h.current_started_at)) + ')' : '') + '</dd>' +
      '<dt>SELESAI 1 JAM TERAKHIR</dt><dd>' + UI.int(h.done_last_hour) + ' tanggal</dd>' +
      '<dt>TERAKHIR SELESAI</dt><dd>' + UI.esc(h.last_completed_date ? UI.date(h.last_completed_date) : UI.NA) + '</dd></dl>' +
      '<p class="scr-text v-dim" style="margin:6px 0 0">Backfill baru dari halaman ini ditolak sampai proses itu selesai (satu backfill hidromet pada satu waktu).</p>';
  }

  function renderRun(r) {
    const $ = s => UI.$(s, st.root);
    $('#dsRunBox').hidden = !r && !(st.hydromet && st.hydromet.external);
    if (!r && st.hydromet && st.hydromet.external) { renderExternal(st.hydromet); return; }
    if (r && r.status !== 'RUNNING' && st.hydromet && st.hydromet.external) { renderExternal(st.hydromet); return; }
    if (!r) { $('#dsRunRec').textContent = ''; $('#dsRun').innerHTML = ''; return; }
    const s = RUN_STATUS[r.status] || [r.status, ''];
    $('#dsRunRec').textContent = '● ' + s[0];
    $('#dsRunRec').className = 'scr-rec ' + (r.status === 'RUNNING' ? 'live' : 'off');
    const pct = r.total ? r.done / r.total * 100 : (r.status === 'RUNNING' ? 0 : 100);
    $('#dsRun').innerHTML = '<p class="scr-text" style="margin:0 0 4px">#' + r.run_id + ' · ' + UI.esc(UI.date(r.date_from)) + ' – ' + UI.esc(UI.date(r.date_to)) +
      ' · <span class="' + s[1] + '">' + s[0] + '</span>' + (r.total ? ' · hari ' + r.done + ' dari ' + r.total : '') + '</p>' +
      UI.progressHTML(pct, 'Progres backfill') +
      '<div class="scr-log" id="dsLog" style="max-height:260px;margin-top:6px" role="log" aria-live="polite">' +
      st.lines.map(l => '<div class="' + (/FAILED|ERROR|ABORT/.test(l) ? 'v-alert' : /WAITING|SKIP/.test(l) ? 'v-amber' : '') + '">' + UI.esc(l) + '</div>').join('') + '</div>';
    const log = $('#dsLog'); if (log) log.scrollTop = log.scrollHeight;
  }

  const DAY_STATUS = { COMPLETED: ['SELESAI', ''], PROCESSING: ['DIKERJAKAN', 'v-cyan'], FAILED: ['GAGAL', 'v-alert'],
    WAITING_UPSTREAM: ['MENUNGGU NASA', 'v-amber'], READY: ['SELESAI', ''], PARTIAL: ['SEBAGIAN', 'v-amber'],
    INCOMPLETE: ['TIDAK MENUTUP AOI', 'v-dim'], DELETED: ['BERKAS DIHAPUS', 'v-dim'] };

  function renderHydrometHistory(days, stale) {
    UI.$('#dsHistCh', st.root).textContent = st.src === 's1' ? 'RIWAYAT LINTASAN SENTINEL-1 PER TANGGAL' : 'RIWAYAT JOB HIDROMET PER TANGGAL';
    const note = stale.length ? '<p class="scr-text v-amber" style="margin:0 0 6px">' + UI.int(stale.length) +
      ' TANGGAL TERPUTUS (proses berhenti sebelum selesai): ' + UI.esc(stale.slice(0, 5).map(d => UI.date(d)).join(', ')) +
      (stale.length > 5 ? ', …' : '') + '. Tanggal ini dikerjakan ulang otomatis oleh backfill berikutnya yang mencakupnya.</p>' : '';
    UI.$('#dsHist', st.root).innerHTML = note + UI.tableHTML([
      { label: 'Tanggal', get: d => UI.date(d.date) },
      { label: 'Status', html: true, get: d => { const x = d.stale ? ['TERPUTUS', 'v-amber'] : (DAY_STATUS[d.status] || [d.status, '']);
        return '<span class="' + x[1] + '">' + UI.esc(x[0]) + '</span>'; } },
      { label: 'Angka ' + LABEL[st.src], cls: 'r', get: d => UI.int(d.n_observations) },
      { label: 'Gagal', cls: 'r', get: d => UI.int(d.failed_count) },
      { label: 'Selesai', get: d => d.completed_at ? UI.dateTime(d.completed_at) : '' },
    ], days, { empty: st.src === 's1' ? 'BELUM ADA LINTASAN SENTINEL-1' : 'BELUM ADA JOB HIDROMET', caption: 'Riwayat per tanggal' });
  }

  return { init, destroy, onSub };
})();
