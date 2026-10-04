// js/catalog.js — Katalog Dataset (INTERFACE.md §2.6, §4.7) [WARIS DataLab View 2].
// Daftar + aksi di Control Panel; rincian dataset terpilih di tab property sheet (screen).
'use strict';
Pages['catalog'] = (() => {
  const STATUS = { QUEUED: 'Antre', PREPARING: 'Menyiapkan', DOWNLOADING: 'Mengunduh', PROCESSING: 'Memproses', PAUSED: 'Dijeda',
    CLEANUP: 'Membersihkan', COMPLETED: 'Selesai', PARTIAL: 'Sebagian', FAILED: 'Gagal', CANCELLED: 'Dibatalkan', DELETING: 'Menghapus', DRAFT: 'Draf' };
  const ACTIVE = new Set(['QUEUED', 'PREPARING', 'DOWNLOADING', 'PROCESSING', 'PAUSED', 'CLEANUP', 'DELETING']);
  const SRC = { sentinel1: 'Sentinel-1', modis: 'MODIS', gpm: 'GPM', fusion: 'Fusion', SENTINEL1: 'Sentinel-1', MODIS: 'MODIS', GPM: 'GPM', FUSION: 'Fusion' };
  const PHASE = { download: 'Diunduh', processing: 'Diproses', fusion: 'Difusikan' };
  const KIND = { grayscale: 'Grayscale', colored: 'Berwarna', composite: 'Komposit & overlay' };
  let st = null;

  async function init(root, ctx) {
    st = { root, ctx, items: [], sel: null, tab: 'ringkasan', prog: {}, timer: null, pv: {} };
    const $ = s => UI.$(s, root);
    $('#ctSearch').addEventListener('input', renderList);
    $('#ctList').addEventListener('keydown', listKeys);
    $('#ctRefresh').addEventListener('click', ev => UI.busy(ev.currentTarget, load));
    UI.$$('#ctActions [data-act]', root).forEach(b => b.addEventListener('click', () => action(b, b.dataset.act)));
    UI.bindTabs(root, tab => { st.tab = tab; renderTab(); });
    Excel.mount($('#ctExcel'), ['datasets', 'products', 's1_scenes', 'nasa_scenes', 'quality_summary', 'completeness']);
    await load();
    st.timer = setInterval(() => { if (st && st.items.some(d => ACTIVE.has(d.status))) load(true); }, 10000);
  }
  function destroy() { if (st && st.timer) clearInterval(st.timer); st = null; }

  const ds = () => st.items.find(d => d.dataset_id === st.sel);
  const mine = d => d.created_by === st.ctx.me.user_id || st.ctx.me.role_code === 'ADMIN';

  async function load(quiet) {
    try { st.items = (await API.get('/api/datasets?limit=200')).items; }
    catch (e) { if (!quiet) UI.showError('Katalog Dataset', e); return; }
    if (!st.items.some(d => d.dataset_id === st.sel)) st.sel = st.items.length ? st.items[0].dataset_id : null;
    renderList();
    await select(st.sel, quiet);
  }

  function renderList() {
    const q = UI.$('#ctSearch', st.root).value.trim().toLowerCase();
    const rows = st.items.filter(d => !q || d.name.toLowerCase().includes(q));
    UI.$('#ctList', st.root).innerHTML = rows.length ? rows.map(d =>
      '<button type="button" role="option" data-id="' + d.dataset_id + '" aria-selected="' + (d.dataset_id === st.sel) + '">' +
        '<span class="nm">' + UI.esc(d.name) + '</span><span class="st">' + UI.esc(STATUS[d.status] || d.status) + '</span></button>').join('')
      : '<p class="mut" style="padding:4px">' + (st.items.length ? 'Tidak ada yang cocok.' : 'Belum ada dataset. Buat lewat "Buat dataset baru".') + '</p>';
    UI.$$('#ctList [data-id]', st.root).forEach(b => b.addEventListener('click', () => select(Number(b.dataset.id))));
  }
  function listKeys(e) {
    const opts = UI.$$('#ctList [data-id]', st.root), i = opts.indexOf(document.activeElement);
    if (e.key === 'ArrowDown' && i < opts.length - 1) { e.preventDefault(); opts[i + 1].focus(); }
    if (e.key === 'ArrowUp' && i > 0) { e.preventDefault(); opts[i - 1].focus(); }
  }

  async function select(id, quiet) {
    st.sel = id;
    UI.$$('#ctList [data-id]', st.root).forEach(b => b.setAttribute('aria-selected', Number(b.dataset.id) === id));
    const d = ds();
    syncActions();
    if (!d) {
      UI.$('#ctReadouts', st.root).innerHTML = '';
      UI.$('#ctProgress', st.root).innerHTML = '';
      UI.$('#ctPanel', st.root).innerHTML = UI.screenHTML({ channel: 'KATALOG', body: UI.emptyHTML('BELUM ADA DATASET') });
      st.ctx.setStatus('Belum ada dataset'); return;
    }
    try { st.prog[id] = await API.get('/api/datasets/' + id + '/status'); } catch (e) { st.prog[id] = null; }
    const p = st.prog[id];
    UI.$('#ctReadouts', st.root).innerHTML =
      UI.readoutHTML('STATUS', UI.esc((STATUS[d.status] || d.status).toUpperCase()), UI.esc(d.status), d.status === 'FAILED' ? 'v-alert' : ACTIVE.has(d.status) ? 'v-amber' : '') +
      UI.readoutHTML('SCENE SELESAI', UI.int(d.completed_scenes) + '/' + UI.int(d.total_scenes), 'GAGAL ' + UI.int(d.failed_scenes), d.failed_scenes ? 'v-amber' : '') +
      UI.readoutHTML('UKURAN', UI.esc(UI.bytes(d.total_size_bytes)), 'DI DISK') +
      UI.readoutHTML('PROGRES', p ? UI.int(p.progress_percent) + '%' : UI.NA, p && p.paused ? 'DIJEDA' + (p.pause_reason ? ': ' + UI.esc(p.pause_reason) : '') : 'PIPELINE');
    UI.$('#ctProgress', st.root).innerHTML = p && ACTIVE.has(d.status)
      ? '<div class="progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="' + p.progress_percent + '" aria-label="Progres dataset"><i style="width:' + Math.max(1, p.progress_percent) + '%"></i></div>' : '';
    st.ctx.setStatus((quiet ? 'Diperbarui · ' : 'Siap · ') + d.name);
    renderTab();
  }

  function syncActions() {
    const d = ds();
    const on = (act, ok) => { const b = UI.$('#ctActions [data-act="' + act + '"]', st.root); b.disabled = !ok; };
    on('download', d && d.total_size_bytes > 0); on('report', d && d.total_size_bytes > 0);
    on('pause', d && ['QUEUED', 'PREPARING', 'DOWNLOADING', 'PROCESSING'].includes(d.status));
    on('resume', d && d.status === 'PAUSED'); on('retry', d && d.status === 'FAILED');
    on('cancel', d && ['DOWNLOADING', 'PROCESSING'].includes(d.status));
    on('delete', d && mine(d) && d.status !== 'DELETING');
    UI.$('#ctActNote', st.root).textContent = d && !mine(d) ? 'Hapus hanya untuk pembuat (' + (d.created_by_name || '—') + ') atau Administrator.' : '';
  }

  async function action(btn, act) {
    const d = ds(); if (!d) return;
    const base = '/api/datasets/' + d.dataset_id;
    await UI.busy(btn, async () => {
      try {
        if (act === 'download') return await API.download(base + '/download', d.name + '.zip');
        if (act === 'report') return await API.download(base + '/report', 'laporan_' + d.dataset_id + '.pdf');
        if (act === 'pause') await API.post(base + '/pause', {});
        if (act === 'resume') await API.post(base + '/resume');
        if (act === 'retry') await API.post('/api/pipeline/trigger?dataset_id=' + d.dataset_id);
        if (act === 'cancel') {
          if (!await UI.confirm('Batalkan proses', 'Hentikan pemrosesan "' + d.name + '"? Data antara (RAW, ALIGNED, DESPECKLED/INDICES/ACCUMULATED) dihapus; COG dan FUSED yang sudah selesai disimpan.', 'Batalkan proses')) return;
          const r = await API.post(base + '/cancel', { cascade_delete: true });
          UI.info('Batalkan proses', 'Dibatalkan: ' + UI.int(r.deleted_files) + ' berkas dihapus, tier ' + r.retained_tier + ' disimpan.');
        }
        if (act === 'delete') {
          const force = await UI.dialog({ title: 'Hapus dataset', kind: 'warn',
            message: 'Semua berkas dataset "' + d.name + '" akan dihapus permanen. Tindakan ini tidak dapat dibatalkan.',
            body: '<label class="check"><input type="checkbox" id="delForce"> Paksa hentikan proses yang sedang berjalan</label>',
            buttons: [{ label: 'Hapus', value: 'ok' }, { label: 'Batal', value: null, cancel: true, default: true }],
            collect: win => UI.$('#delForce', win).checked });
          if (force === null || force === 'cancel') return;
          await API.del(base + '?force=' + !!force);
          UI.info('Hapus dataset', 'Penghapusan dimulai. Berkas dihapus oleh pipeline di latar belakang.');
        }
        await load(true);
      } catch (e) { UI.showError('Aksi dataset', e); }
    });
  }

  // ---------------------------------------------------------------- tab
  async function renderTab() {
    const panel = UI.$('#ctPanel', st.root), d = ds();
    if (!d) return;
    const tab = st.tab;
    const put = html => { if (st && st.tab === tab && ds() === d) panel.innerHTML = html; };
    if (tab !== 'ringkasan' && !panel.innerHTML.includes('data-keep')) put(UI.screenHTML({ channel: 'SYS', body: UI.loadingHTML() }));
    try {
      if (tab === 'ringkasan') put(summaryHTML(d));
      else if (tab === 'sumber') put(sourcesHTML(await API.get('/api/datasets/' + d.dataset_id + '/storage/by-source')));
      else if (tab === 'struktur') {
        const [s, q] = await Promise.all([API.get('/api/datasets/' + d.dataset_id + '/storage/summary'),
          API.get('/api/quality/dataset/' + d.dataset_id + '/by-source').catch(() => ({ sources: [] }))]);
        put(structureHTML(s, q)); bindTierFiles(d);
      } else if (tab === 'pratinjau') { st.pvData = await API.get('/api/datasets/' + d.dataset_id + '/preview'); drawPreview(d); }
      else if (tab === 'produk') await drawProducts(d, 1);
      else if (tab === 'log') {
        const l = await API.get('/api/datasets/' + d.dataset_id + '/logs?limit=100');
        const prog = st.prog[d.dataset_id];
        put(UI.screenHTML({ channel: 'CH-LOG · PIPELINE', body: '<div class="scr-log" style="max-height:420px">' + ((l.logs || []).length ? l.logs.map(x =>
          '<div><span class="v-dim">' + UI.esc(UI.dateTime(x.timestamp)) + '</span> ' + UI.esc(x.stage || x.module || '') + ' <span class="' +
          (/FAIL|ERROR/.test(x.status) ? 'v-alert' : /RUN|START|WAIT/.test(x.status) ? 'v-amber' : '') + '">' + UI.esc(x.status || '') + '</span> ' + UI.esc(x.message || '') + '</div>').join('') : UI.emptyHTML()) + '</div>' }) +
          (prog && prog.scenes && prog.scenes.length ? '<div style="height:8px"></div>' + UI.screenHTML({ channel: 'STATUS PIPELINE SENTINEL-1 PER SCENE', body: UI.tableHTML([
            { label: 'Scene', key: 'product_identifier' }, { label: 'Tahap', key: 'current_stage' }, { label: 'Status', key: 'stage_status' },
            { label: 'Percobaan', cls: 'r', get: s => s.attempt_number + '/' + s.max_retries }, { label: 'Catatan', key: 'last_error' },
          ], prog.scenes) }) : ''));
      }
    } catch (e) { put(UI.screenHTML({ channel: 'SYS', body: UI.emptyHTML('GAGAL MEMUAT') })); UI.showError('Katalog Dataset', e); }
  }

  function summaryHTML(d) {
    const cfg = (d.source_configs || []).map(c => (SRC[c.source] || c.source) + ' [' + (c.processing || []).join(' + ') + ']' +
      (c.source === 'sentinel1' ? ' · orbit ' + ({ ASCENDING: 'naik', DESCENDING: 'turun' }[d.s1_orbit_direction] || 'naik + turun') : '')).join('\n');
    const kv = [['NAMA', d.name], ['DESKRIPSI', d.description], ['LOKASI', d.location_label], ['TANGGAL', UI.date(d.date_start) + ' – ' + UI.date(d.date_end)],
      ['SUMBER & LEVEL', cfg], ['STRATEGI FUSI', d.fusion_strategy ? d.fusion_strategy + (d.fusion_output_only ? ' (hanya keluaran fusi)' : '') +
        (d.fusion_strategy === 'FULL_COVERAGE' ? ' · toleransi S1 ' + d.s1_match_tolerance_days + ' hari' : '') : 'tidak dipakai (1 sumber)'],
      ['PRATINJAU', (d.preview_options || []).join(', ') || 'tidak dibuat'], ['TIER', (d.required_tiers || []).join(', ')],
      ['PEMBUAT', d.created_by_name], ['DIBUAT', UI.dateTime(d.created_at)], ['DIPERBARUI', UI.dateTime(d.updated_at)],
      ['DISALIN DARI', d.last_config_source ? 'dataset #' + d.last_config_source : null]];
    const per = Object.keys(d.scenes_by_source || {}).map(k => (SRC[k] || k) + ': ' + UI.int(d.scenes_by_source[k]) + ' scene · ' + UI.bytes((d.bytes_by_source || {})[k])).join('\n');
    return UI.screenHTML({ channel: 'CH-01 · KONFIGURASI DATASET #' + d.dataset_id, rec: UI.esc((STATUS[d.status] || d.status).toUpperCase()),
      recCls: d.status === 'COMPLETED' ? 'off' : '', body: '<dl class="kv">' + kv.map(([k, v]) => '<dt>' + k + '</dt><dd class="scr-text">' + UI.esc(v || UI.NA) + '</dd>').join('') + '</dl>' +
        (per ? '<p class="scr-text" style="margin:8px 0 0"><span class="lbl">PER SATELIT:</span>\n' + UI.esc(per) + '</p>' : '') });
  }

  function barRow(label, size, total, right) {
    const pct = total > 0 ? size / total * 100 : 0;
    return '<div class="ct-bar"><span>' + UI.esc(label) + '</span><span class="trk" role="img" aria-label="' + UI.esc(label + ' ' + UI.num(pct, 0) + '%') + '"><i style="width:' + Math.max(pct, size ? 1 : 0).toFixed(1) + '%"></i></span><span class="num" style="text-align:right">' + UI.esc(right) + '</span></div>';
  }

  function sourcesHTML(data) {
    const keys = ['sentinel1', 'modis', 'gpm'].filter(k => (data.sources || {})[k]);
    if (!keys.length && !data.fusion) return UI.screenHTML({ channel: 'DETAIL SUMBER', body: UI.emptyHTML('BELUM ADA DATA YANG DIUNDUH') });
    return keys.map((k, i) => {
      const s = data.sources[k];
      return UI.screenHTML({ channel: 'CH-0' + (i + 1) + ' · ' + SRC[k], rec: UI.bytes(s.size_bytes), recCls: 'off', body: s.stages.map(stg =>
        barRow((PHASE[stg.phase] || stg.phase) + ' · ' + stg.tier, stg.size_bytes, s.size_bytes, UI.bytes(stg.size_bytes)) +
        '<details><summary class="v-dim" style="cursor:pointer">' + UI.int(stg.scenes.length) + ' item · ' + UI.int(stg.file_count) + ' berkas</summary>' +
        UI.tableHTML([{ label: 'Item', key: 'scene' }, { label: 'Berkas', cls: 'r', key: 'file_count' }, { label: 'Ukuran', cls: 'r', get: x => UI.bytes(x.size_bytes) }], stg.scenes) + '</details>').join('') });
    }).join('<div style="height:8px"></div>') +
      (data.fusion ? '<div style="height:8px"></div>' + UI.screenHTML({ channel: 'FUSION (HDF5)', rec: UI.bytes(data.fusion.size_bytes), recCls: 'off',
        body: UI.tableHTML([{ label: 'Tanggal', key: 'scene' }, { label: 'Berkas', cls: 'r', key: 'file_count' }, { label: 'Ukuran', cls: 'r', get: x => UI.bytes(x.size_bytes) }], data.fusion.scenes) }) : '');
  }

  function structureHTML(s, q) {
    if (s.legacy_layout) return UI.screenHTML({ channel: 'STRUKTUR', body: UI.emptyHTML('DATASET MEMAKAI FORMAT FOLDER LAMA — BERKAS TETAP DAPAT DIUNDUH (ZIP)') });
    const tiers = Object.entries(s.tiers || {});
    return '<div data-keep>' + UI.screenHTML({ channel: 'CH-01 · PENYIMPANAN PER TIER', rec: UI.bytes(s.total_size_bytes), recCls: 'off',
      body: tiers.length ? tiers.map(([t, x]) => barRow(t, x.size_bytes, s.total_size_bytes, UI.bytes(x.size_bytes)) +
        '<p class="v-dim" style="margin:0 0 4px 116px;font-size:11px">' + UI.int(x.file_count) + ' berkas · ' + UI.int(x.scene_count) + ' item' +
        (Object.keys(x.sources || {}).length ? ' · ' + Object.entries(x.sources).map(([k, v]) => (SRC[k] || k) + ' ' + UI.bytes(v.size_bytes)).join(' · ') : '') +
        ' · <a href="#" data-tier="' + UI.esc(t) + '">daftar berkas</a></p>').join('') : UI.emptyHTML('BELUM ADA BERKAS') }) +
      '<div style="height:8px"></div>' +
      UI.screenHTML({ channel: 'CH-02 · KUALITAS PER SUMBER', body: UI.tableHTML([
        { label: 'Sumber', get: x => SRC[x.source] || x.source },
        { label: 'Jenis', get: x => x.kind === 'RADIOMETRIC' ? 'Radiometrik' : 'Cakupan' },
        { label: 'Produk', cls: 'r', key: 'product_count' }, { label: 'Item', cls: 'r', key: 'scene_count' },
        { label: 'Skor', cls: 'r', get: x => UI.num(x.quality_score, 2) }, { label: 'Status', key: 'quality_flag' },
        { label: 'Per band', get: x => Object.entries(x.bands || {}).map(([b, v]) => b + ' ' + UI.num(v, 2)).join(' · ') },
      ], q.sources || [], { empty: 'BELUM ADA METRIK KUALITAS' }) +
        '<p class="v-dim" style="margin:6px 0 0;font-size:11px">Ambang QA diatur Administrator (quality_thresholds), bukan per dataset.</p>' }) +
      '<div id="ctFiles"></div></div>';
  }

  function bindTierFiles(d) {
    UI.$$('[data-tier]', st.root).forEach(a => a.addEventListener('click', async ev => {
      ev.preventDefault();
      const box = UI.$('#ctFiles', st.root);
      box.innerHTML = '<div style="height:8px"></div>' + UI.screenHTML({ channel: 'BERKAS ' + a.dataset.tier, body: UI.loadingHTML() });
      try {
        const r = await API.get('/api/datasets/' + d.dataset_id + '/storage/files/' + encodeURIComponent(a.dataset.tier));
        const rows = r.scenes.flatMap(sc => sc.files.map(f => ({ scene: sc.scene, source: sc.source, ...f })));
        box.innerHTML = '<div style="height:8px"></div>' + UI.screenHTML({ channel: 'BERKAS TIER ' + a.dataset.tier, rec: UI.int(rows.length) + ' BERKAS', recCls: 'off',
          body: UI.tableHTML([{ label: 'Item', key: 'scene' }, { label: 'Sumber', get: x => SRC[x.source] || x.source }, { label: 'Nama', key: 'name' },
            { label: 'MB', cls: 'r', get: x => UI.num(x.size_mb, 2) }], rows.slice(0, 500), { empty: 'TIDAK ADA BERKAS' }) });
      } catch (e) { box.innerHTML = ''; UI.showError('Daftar berkas', e); }
    }));
  }

  // ---------------------------------------------------------------- pratinjau
  function drawPreview(d) {
    const panel = UI.$('#ctPanel', st.root), data = st.pvData;
    if (!data || !data.scenes || !data.scenes.length) {
      const msg = d.generate_preview === false ? 'PRATINJAU TIDAK DIAKTIFKAN UNTUK DATASET INI (PILIH OPSI PRATINJAU SAAT MEMBUAT DATASET)'
        : !(d.required_tiers || []).some(t => ['COG', 'FUSED'].includes(t)) ? 'PRATINJAU DIBUAT DARI TIER COG; DATASET INI BERHENTI SEBELUM COG'
        : 'BELUM ADA PRATINJAU — DIBUAT OTOMATIS SETELAH TAHAP COG SELESAI';
      panel.innerHTML = UI.screenHTML({ channel: 'PRATINJAU', body: UI.emptyHTML(msg) }); return;
    }
    const pv = st.pv[d.dataset_id] = st.pv[d.dataset_id] || {};
    const scene = data.scenes.find(s => s.scene === pv.scene) || data.scenes[0];
    pv.scene = scene.scene;
    const levels = scene.processing_levels || [];
    pv.level = levels.includes(pv.level) ? pv.level : levels[0] || null;
    const kinds = ((scene.by_level && pv.level && scene.by_level[pv.level]) || scene).kinds || {};
    pv.kind = data.kinds.includes(pv.kind) ? pv.kind : (data.kinds.includes('colored') ? 'colored' : data.kinds[0]);
    const block = kinds[pv.kind] || { images: [], info: {} };
    const fmtKey = k => /^\d{8}$/.test(k) ? UI.date(k.slice(0, 4) + '-' + k.slice(4, 6) + '-' + k.slice(6)) : k;
    panel.innerHTML = '<div class="ct-filters">' +
      '<div class="field"><label for="pvScene">Tanggal</label><select id="pvScene">' + data.scenes.map(s => '<option value="' + UI.esc(s.scene) + '"' + (s.scene === scene.scene ? ' selected' : '') + '>' +
        UI.esc(fmtKey(s.scene)) + (s.coverage_quality === 'partial' ? ' (cakupan sebagian)' : '') + '</option>').join('') + '</select></div>' +
      (levels.length > 1 ? '<div class="field"><label for="pvLevel">Level</label><select id="pvLevel">' + levels.map(l => '<option' + (l === pv.level ? ' selected' : '') + '>' + UI.esc(l) + '</option>').join('') + '</select></div>' : '') +
      '<div class="field"><label for="pvKind">Jenis</label><select id="pvKind">' + data.kinds.map(k => '<option value="' + k + '"' + (k === pv.kind ? ' selected' : '') + '>' +
        UI.esc(KIND[k] || k) + ' (' + ((kinds[k] || {}).count || 0) + ')</option>').join('') + '</select></div>' +
      '<span class="mut">Total pratinjau: ' + UI.esc(UI.bytes(data.total_size_bytes)) + '</span></div>' +
      UI.screenHTML({ channel: 'PRATINJAU · ' + fmtKey(scene.scene) + (pv.level ? ' · ' + pv.level : ''), rec: scene.coverage_quality === 'partial' ? '● CAKUPAN SEBAGIAN' : '',
        body: (block.info && block.info.purpose ? '<p class="scr-text v-dim" style="margin:0 0 6px">' + UI.esc(block.info.purpose) + '</p>' : '') +
          (block.images.length ? '<div class="tiles">' + block.images.map((img, i) => '<div class="tile"><span class="tl"><span>' + UI.esc(img.label || img.key) + '</span><span>' + UI.esc(SRC[img.source] || '') + '</span></span>' +
            '<button type="button" class="thumb" data-pv="' + i + '" aria-label="' + UI.esc((img.label || img.key) + ': buka legenda') + '"><img loading="lazy" src="' + UI.esc(img.url) + '" alt=""></button></div>').join('') + '</div>'
            : UI.emptyHTML('TIDAK ADA GAMBAR JENIS INI UNTUK TANGGAL INI')) +
          ((scene.skipped || []).length ? '<p class="v-amber" style="margin:6px 0 0">' + UI.int(scene.skipped.length) + ' LAPISAN TIDAK DIRENDER: ' + UI.esc(scene.skipped.map(s => s.key).join(', ')) + '</p>' : '') });
    const re = () => drawPreview(d);
    UI.$('#pvScene', panel).addEventListener('change', e => { pv.scene = e.target.value; re(); });
    if (UI.$('#pvLevel', panel)) UI.$('#pvLevel', panel).addEventListener('change', e => { pv.level = e.target.value; re(); });
    UI.$('#pvKind', panel).addEventListener('change', e => { pv.kind = e.target.value; re(); });
    const items = block.images.map(img => ({ url: img.url, title: img.label || img.key, legend: legendOf(img), note: UI.esc(img.interpretation || img.note || '') }));
    UI.$$('[data-pv]', panel).forEach(b => b.addEventListener('click', () => UI.lightbox(items, Number(b.dataset.pv))));
  }
  function legendOf(img) {
    if (Array.isArray(img.legend) && img.legend.length) return LiveTiles.legendHTML({ type: 'categorical', categories: img.legend });
    if (img.channels) return '<div class="legend">' + Object.entries(img.channels).map(([c, b]) => '<span>' + UI.esc(c + ' = ' + b) + '</span>').join('') + '</div>';
    if (img.colormap || img.cmap) return '<p class="v-dim" style="margin:4px 0 0">COLORMAP ' + UI.esc(img.colormap || img.cmap) + (img.vmin !== undefined ? ' · ' + UI.num(img.vmin, 2) + ' – ' + UI.num(img.vmax, 2) : '') + '</p>';
    return '';
  }

  // ---------------------------------------------------------------- produk & lineage
  async function drawProducts(d, page) {
    const panel = UI.$('#ctPanel', st.root), limit = 50;
    const f = st.prodFilter = st.prodFilter || { source: '', tier: '' };
    const r = await API.get('/api/products' + API.qs({ dataset_id: d.dataset_id, source: f.source, tier: f.tier, limit, offset: (page - 1) * limit }));
    panel.innerHTML = '<div class="ct-filters">' +
      '<div class="field"><label for="prSrc">Sumber</label><select id="prSrc"><option value="">Semua</option>' + ['SENTINEL1', 'MODIS', 'GPM', 'FUSION'].map(s => '<option value="' + s + '"' + (f.source === s ? ' selected' : '') + '>' + SRC[s] + '</option>').join('') + '</select></div>' +
      '<div class="field"><label for="prTier">Tier</label><select id="prTier"><option value="">Semua</option>' + ['RAW', 'ALIGNED', 'DESPECKLED', 'INDICES', 'ACCUMULATED', 'COG', 'FUSED'].map(t => '<option' + (f.tier === t ? ' selected' : '') + '>' + t + '</option>').join('') + '</select></div></div>' +
      UI.screenHTML({ channel: 'PRODUK DATASET #' + d.dataset_id, rec: UI.int(r.total) + ' PRODUK', recCls: 'off', body: UI.tableHTML([
        { label: 'ID', key: 'product_id' }, { label: 'Sumber', get: p => SRC[p.source] || p.source }, { label: 'Tier', key: 'product_tier' }, { label: 'Band', key: 'band_name' },
        { label: 'Asal', get: p => p.scene_id ? 'scene S1 #' + p.scene_id : p.nasa_scene_id ? 'granule NASA #' + p.nasa_scene_id : 'fusi (tanpa scene)' },
        { label: 'Berkas', key: 'file_name' }, { label: 'MB', cls: 'r', get: p => UI.num(p.file_size_mb, 2) },
        { label: 'Aksi', html: true, get: p => '<button type="button" class="small" data-dl="' + p.product_id + '">Unduh</button> <button type="button" class="small" data-lin="' + p.product_id + '">Asal-usul…</button>' },
      ], r.items, { empty: 'BELUM ADA PRODUK' }) + UI.pagerHTML(r.total, limit, (page - 1) * limit) });
    UI.$('#prSrc', panel).addEventListener('change', e => { f.source = e.target.value; drawProducts(d, 1).catch(err => UI.showError('Produk', err)); });
    UI.$('#prTier', panel).addEventListener('change', e => { f.tier = e.target.value; drawProducts(d, 1).catch(err => UI.showError('Produk', err)); });
    UI.$$('[data-page]', panel).forEach(b => b.addEventListener('click', () => drawProducts(d, Number(b.dataset.page)).catch(err => UI.showError('Produk', err))));
    UI.$$('[data-dl]', panel).forEach(b => b.addEventListener('click', () => UI.busy(b, async () => {
      const p = r.items.find(x => String(x.product_id) === b.dataset.dl);
      try { await API.download('/api/products/' + p.product_id + '/download', p.file_name); } catch (e) { UI.showError('Unduh produk', e); }
    })));
    UI.$$('[data-lin]', panel).forEach(b => b.addEventListener('click', () => lineage(r.items.find(x => String(x.product_id) === b.dataset.lin))));
  }

  async function lineage(p) {
    let up, down;
    try { [up, down] = await Promise.all([API.get('/api/metadata/lineage/' + p.product_id), API.get('/api/metadata/lineage/' + p.product_id + '?direction=descendants')]); }
    catch (e) { UI.showError('Asal-usul produk', e); return; }
    const cols = [{ label: 'Langkah', get: (s, i) => i + 1 }, { label: 'Transformasi', key: 'transformation_type' }, { label: 'Sumber', get: s => SRC[s.source] || s.source },
      { label: 'Tier', get: s => (s.parent_tier || '?') + ' → ' + (s.child_tier || '?') }, { label: 'Induk → anak', get: s => '#' + s.parent_product_id + ' → #' + s.child_product_id },
      { label: 'Job', key: 'job_id' }, { label: 'Waktu', get: s => UI.dateTime(s.created_at) }];
    UI.dialog({ title: 'Asal-usul produk #' + p.product_id, wide: 'x', buttons: [{ label: 'Tutup', value: true, default: true, cancel: true }],
      body: UI.screenHTML({ channel: 'PRODUK #' + p.product_id + ' · ' + p.file_name, body: '<dl class="kv"><dt>SHA-256</dt><dd class="scr-text" style="overflow-wrap:anywhere">' + UI.esc(p.data_hash_sha256) + '</dd>' +
          '<dt>CRS</dt><dd>' + UI.esc(p.crs) + '</dd><dt>UKURAN PIKSEL</dt><dd>' + UI.num(p.pixel_size_m, 1) + ' m</dd><dt>DIMENSI</dt><dd>' + UI.int(p.rows) + ' × ' + UI.int(p.cols) + ' × ' + UI.int(p.band_count) + '</dd></dl>' }) +
        '<div style="height:8px"></div>' + UI.screenHTML({ channel: 'LELUHUR (SAMPAI SUMBER RAW)', rec: UI.int(up.total_steps) + ' LANGKAH', recCls: 'off', body: UI.tableHTML(cols, up.chain, { empty: 'TIDAK ADA LELUHUR (PRODUK SUMBER)' }) }) +
        '<div style="height:8px"></div>' + UI.screenHTML({ channel: 'TURUNAN', rec: UI.int(down.total_steps) + ' LANGKAH', recCls: 'off', body: UI.tableHTML(cols, down.chain, { empty: 'TIDAK ADA TURUNAN' }) }) });
  }

  return { init, destroy };
})();
