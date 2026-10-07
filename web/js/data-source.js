// js/data-source.js — Data › Sentinel-1 | GPM | MODIS (#data/<satelit>, INTERFACE.md §2
// halaman 6.2–6.4, M56). Satelitnya dari ctx.tab.source.
//
// * Daftar: GET /api/data/{src}/items (termasuk yang dinonaktifkan).
// * Ubah/hapus: PATCH .../items/{id} {is_valid, reason} (soft delete, alasan
//   wajib, bisa dipulihkan) dan POST .../items/{id}/reprocess. Tidak ada
//   "tambah manual" (M24).
// * Backfill: POST /api/data/{src}/backfill.
//   - GPM/MODIS: Job Hidromet di thread latar; progres + log dibaca dari
//     GET /api/data/backfill/runs/{id}?since=n tiap 2 detik selama berjalan.
//   - Sentinel-1: membuat dataset S1 atas AOI; progres dari
//     GET /api/datasets/{id}/status, log dari GET /api/datasets/{id}/logs.
'use strict';
Pages['data-source'] = (() => {
  const LABEL = { s1: 'Sentinel-1', gpm: 'GPM', modis: 'MODIS' };
  const HELP = {
    s1: 'Membuat dataset Sentinel-1 atas AOI untuk rentang ini (maks. 366 hari). Scene yang sudah ada dipakai ulang; progres dan log dataset tampil di sebelah.',
    gpm: 'Menjalankan Job Hidromet (GPM) per tanggal yang belum selesai: unduh granule, hitung hujan per kecamatan, cek alert. Tanggal yang sudah selesai dilewati.',
    modis: 'Mengisi tanggal yang belum punya angka MODIS (genangan, NDVI, NDWI). Job Hidromet ikut memastikan GPM tanggal itu. Tanggal yang sudah lengkap dilewati.',
  };
  const RUN_STATUS = { RUNNING: ['BERJALAN', 'v-cyan'], COMPLETED: ['SELESAI', ''], FAILED: ['GAGAL', 'v-alert'], SKIPPED: ['DILEWATI', 'v-amber'] };
  const LIMIT = 50;
  let st = null;

  async function init(root, ctx) {
    const src = (ctx.tab && ctx.tab.source) || 'gpm';
    st = { root, ctx, src, page: 1, run: null, lines: [], poll: null, dataset: null };
    const $ = s => UI.$(s, root);
    $('#dsBfHelp').textContent = HELP[src];
    const today = UI.isoDate(new Date());
    $('#dsBfTo').value = UI.addDays(today, -1); $('#dsBfFrom').value = UI.addDays(today, -7);
    $('#dsBackfill').addEventListener('submit', ev => { ev.preventDefault(); startBackfill(); });
    $('#dsFilter').addEventListener('submit', ev => { ev.preventDefault(); st.page = 1; UI.busy($('#dsApply'), loadItems); });
    await Promise.all([loadItems(), loadBackfill()]);
  }

  function destroy() { if (st && st.poll) clearTimeout(st.poll); st = null; }

  // ------------------------------------------------------------------ daftar
  async function loadItems() {
    const $ = s => UI.$(s, st.root);
    const from = $('#dsFrom').value, to = $('#dsTo').value;
    if (from && to && from > to) { UI.showError('Saring daftar', { code: 'INVALID_DATE_RANGE' }); return; }
    let r;
    try {
      r = await API.get('/api/data/' + st.src + '/items' + API.qs({ date_from: from, date_to: to, status: $('#dsStatus').value,
        q: $('#dsQ').value.trim(), limit: LIMIT, offset: (st.page - 1) * LIMIT }));
    } catch (e) { $('#dsTable').innerHTML = UI.emptyHTML('GAGAL MEMUAT'); UI.showError('Data ' + LABEL[st.src], e); return; }
    if (!st) return;
    $('#dsCount').textContent = UI.int(r.total) + ' ITEM';
    const cols = st.src === 's1'
      ? [{ label: 'ID', key: 'id' }, { label: 'Produk', get: x => x.name.length > 42 ? x.name.slice(0, 42) + '…' : x.name },
         { label: 'Akuisisi', get: x => UI.dateTime(x.acquisition_datetime) }, { label: 'Orbit', get: x => (x.orbit_direction || '') + ' ' + (x.relative_orbit || '') },
         { label: 'MB', cls: 'r', get: x => UI.num(x.raw_file_size_mb, 0) }]
      : [{ label: 'ID', key: 'id' }, { label: 'Produk', key: 'name' }, { label: 'Tile', key: 'tile_id' },
         { label: 'Tanggal', get: x => UI.date(x.acquisition_date) }, { label: 'Run', key: 'run_type' }];
    cols.push({ label: 'Produk turunan', cls: 'r', get: x => UI.int(x.n_products) });
    cols.push({ label: 'Status', html: true, get: x => x.is_valid ? 'AKTIF' : '<span class="v-amber" title="' + UI.esc(x.invalid_reason || '') + '">NONAKTIF</span>' });
    cols.push({ label: 'Aksi', html: true, get: x =>
      '<button type="button" class="small" data-reproc="' + x.id + '">Proses ulang…</button> ' +
      (x.is_valid ? '<button type="button" class="small" data-off="' + x.id + '">Nonaktifkan…</button>'
                  : '<button type="button" class="small" data-on="' + x.id + '">Pulihkan</button>') });
    $('#dsTable').innerHTML = UI.tableHTML(cols, r.items, { empty: 'BELUM ADA DATA. JALANKAN BACKFILL UNTUK MENGISI.', caption: 'Data ' + LABEL[st.src] }) +
      UI.pagerHTML(r.total, LIMIT, (st.page - 1) * LIMIT);
    UI.$$('#dsTable [data-page]', st.root).forEach(b => b.addEventListener('click', () => { st.page = Number(b.dataset.page); loadItems(); }));
    UI.$$('[data-off]', st.root).forEach(b => b.addEventListener('click', () => deactivate(Number(b.dataset.off))));
    UI.$$('[data-on]', st.root).forEach(b => b.addEventListener('click', () => setValid(Number(b.dataset.on), true, null)));
    UI.$$('[data-reproc]', st.root).forEach(b => b.addEventListener('click', () => reprocess(Number(b.dataset.reproc))));
    st.ctx.setStatus('Siap · ' + UI.int(r.total) + ' item');
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
        if (r.kind === 'DATASET') { st.dataset = r.dataset_id; st.run = null; }
        else { st.run = r.run; st.lines = []; st.dataset = null; }
        await loadBackfill();
      } catch (e) { UI.showError('Backfill ' + LABEL[st.src], e); }
    });
  }

  async function loadBackfill() {
    if (!st) return;
    let r;
    try { r = await API.get('/api/data/' + st.src + '/backfill'); }
    catch (e) { UI.$('#dsHist', st.root).innerHTML = UI.emptyHTML('GAGAL MEMUAT'); return; }
    if (!st) return;
    if (st.src === 's1') {
      if (!st.dataset && r.datasets.length) st.dataset = r.datasets[0].dataset_id;
      renderS1History(r.datasets);
      await renderS1Run();
    } else {
      if (!st.run && r.runs.length) st.run = r.runs[0];
      st.hydromet = r.hydromet || null;
      renderHydrometHistory(r.days, r.stale_dates || []);
      await pollRun();
      // Backfill dari proses lain (skrip, scheduler, worker lain) tidak punya
      // log di sini; perbarui progresnya dari DB tiap 10 detik.
      if (st && st.hydromet && st.hydromet.external && !(st.run && st.run.status === 'RUNNING')) {
        st.poll = setTimeout(() => { loadBackfill(); loadItems(); }, 10000);
      }
    }
  }

  // GPM/MODIS: baris log baru diambil sejak indeks terakhir (since).
  async function pollRun() {
    if (!st) return;
    if (st.poll) { clearTimeout(st.poll); st.poll = null; }
    if (!st.run) { renderRun(null); return; }
    try {
      const r = await API.get('/api/data/backfill/runs/' + st.run.run_id + API.qs({ since: st.lines.length }));
      if (!st) return;
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
    if (!r && st.hydromet && st.hydromet.external) { renderExternal(st.hydromet); return; }
    if (r && r.status !== 'RUNNING' && st.hydromet && st.hydromet.external) { renderExternal(st.hydromet); return; }
    if (!r) {
      $('#dsRunRec').textContent = '';
      $('#dsRun').innerHTML = UI.emptyHTML('BELUM ADA BACKFILL SEJAK SERVER DIMULAI. RIWAYAT PER TANGGAL ADA DI BAWAH.');
      return;
    }
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
    WAITING_UPSTREAM: ['MENUNGGU NASA', 'v-amber'] };

  function renderHydrometHistory(days, stale) {
    UI.$('#dsHistCh', st.root).textContent = 'CH-02 · RIWAYAT JOB HIDROMET PER TANGGAL';
    const note = stale.length ? '<p class="scr-text v-amber" style="margin:0 0 6px">' + UI.int(stale.length) +
      ' TANGGAL TERPUTUS (proses berhenti sebelum selesai): ' + UI.esc(stale.slice(0, 5).map(d => UI.date(d)).join(', ')) +
      (stale.length > 5 ? ', …' : '') + '. Tanggal ini dikerjakan ulang otomatis oleh backfill berikutnya yang mencakupnya.</p>' : '';
    UI.$('#dsHist', st.root).innerHTML = note + '<div class="scroll-box">' + UI.tableHTML([
      { label: 'Tanggal', get: d => UI.date(d.date) },
      { label: 'Status', html: true, get: d => { const x = d.stale ? ['TERPUTUS', 'v-amber'] : (DAY_STATUS[d.status] || [d.status, '']);
        return '<span class="' + x[1] + '">' + UI.esc(x[0]) + '</span>'; } },
      { label: 'Angka ' + LABEL[st.src], cls: 'r', get: d => UI.int(d.n_observations) },
      { label: 'Gagal', cls: 'r', get: d => UI.int(d.failed_count) },
      { label: 'Selesai', get: d => d.completed_at ? UI.dateTime(d.completed_at) : '' },
    ], days, { empty: 'BELUM ADA JOB HIDROMET', caption: 'Riwayat job per tanggal' }) + '</div>';
  }

  function renderS1History(datasets) {
    UI.$('#dsHistCh', st.root).textContent = 'CH-02 · DATASET BACKFILL SENTINEL-1';
    UI.$('#dsHist', st.root).innerHTML = UI.tableHTML([
      { label: '#', key: 'dataset_id' }, { label: 'Rentang', get: d => UI.date(d.date_start, 'short') + ' – ' + UI.date(d.date_end, 'short') },
      { label: 'Status', get: d => UI.datasetStatus(d.status) },
      { label: 'Scene', cls: 'r', get: d => UI.int(d.completed_scenes) + '/' + UI.int(d.total_scenes) + (d.failed_scenes ? ' (' + d.failed_scenes + ' gagal)' : '') },
      { label: 'Log', html: true, get: d => '<button type="button" class="small" data-ds="' + d.dataset_id + '">Lihat log</button>' },
    ], datasets, { empty: 'BELUM ADA BACKFILL SENTINEL-1', caption: 'Dataset backfill Sentinel-1' }) +
      '<p class="scr-text v-dim" style="margin:6px 0 0">Unduhan dan tahap per scene juga terlihat di <a href="#data/proses">Data › Proses berjalan</a>.</p>';
    UI.$$('[data-ds]', st.root).forEach(b => b.addEventListener('click', () => { st.dataset = Number(b.dataset.ds); renderS1Run(); }));
  }

  async function renderS1Run() {
    if (!st) return;
    if (st.poll) { clearTimeout(st.poll); st.poll = null; }
    const $ = s => UI.$(s, st.root);
    $('#dsRunCh').textContent = 'CH-01 · PROSES BACKFILL (DATASET)';
    if (!st.dataset) { $('#dsRunRec').textContent = ''; $('#dsRun').innerHTML = UI.emptyHTML('BELUM ADA BACKFILL SENTINEL-1'); return; }
    let s, l;
    try {
      [s, l] = await Promise.all([API.get('/api/datasets/' + st.dataset + '/status'), API.get('/api/datasets/' + st.dataset + '/logs?limit=200&order=asc')]);
    } catch (e) { $('#dsRun').innerHTML = UI.emptyHTML('LOG DATASET TIDAK DAPAT DIMUAT'); return; }
    if (!st) return;
    const active = UI.DATASET_ACTIVE.has(s.status);
    $('#dsRunRec').textContent = '● ' + UI.datasetStatus(s.status).toUpperCase();
    $('#dsRunRec').className = 'scr-rec ' + (active ? 'live' : 'off');
    $('#dsRun').innerHTML = '<p class="scr-text" style="margin:0 0 4px">DATASET #' + st.dataset + ' · ' + UI.esc(UI.datasetStatus(s.status)) +
      (s.progress_percent !== undefined ? ' · ' + UI.num(s.progress_percent, 0) + '%' : '') + '</p>' +
      UI.progressHTML(s.progress_percent || 0, 'Progres dataset') +
      '<div class="scr-log" id="dsLog" style="max-height:260px;margin-top:6px" role="log">' + ((l.logs || []).length ? l.logs.map(x =>
        '<div><span class="v-dim">' + UI.esc(UI.dateTime(x.timestamp)) + '</span> ' + UI.esc(x.stage || x.module || '') + ' <span class="' +
        (/FAIL|ERROR/.test(x.status) ? 'v-alert' : /RUN|START|WAIT/.test(x.status) ? 'v-amber' : '') + '">' + UI.esc(x.status || '') + '</span> ' +
        UI.esc(x.message || '') + '</div>').join('') : UI.emptyHTML('BELUM ADA BARIS LOG')) + '</div>';
    const log = $('#dsLog'); if (log) log.scrollTop = log.scrollHeight;
    if (active) st.poll = setTimeout(renderS1Run, 4000);
  }

  return { init, destroy };
})();
