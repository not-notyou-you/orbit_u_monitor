// js/logs.js — Sistem › Log (#sistem/log, INTERFACE.md §2 halaman 8.2, M56).
//
// Bagian per peran (pembatasannya di GRANT VIEW, bukan hanya di menu):
//   data      GET /api/logs/data           (logs.data: DATA_ENGINEER, ADMIN)
//   kejadian  GET /api/logs/kejadian       (logs.disasters: ANALYST, ADMIN)
//   masuk     GET /api/admin/logs/login    (ADMIN; termasuk registrasi akun)
//   unduhan   GET /api/admin/logs/download (ADMIN)
//   audit     GET /api/admin/audit         (ADMIN; seluruh audit_log)
'use strict';
Pages['logs'] = (() => {
  const SECTIONS = [
    { key: 'data', title: 'Halaman Data', perm: 'logs.data', url: '/api/logs/data', page: 'offset',
      actions: [['', 'Semua'], ['BACKFILL_START', 'Backfill'], ['SCENE_UPDATE', 'Ubah scene'], ['DOWNLOAD_DATASET', 'Unduh dataset'],
        ['DOWNLOAD_FUSION', 'Unduh fusion'], ['DOWNLOAD_PRODUCT', 'Unduh produk'], ['INSERT', 'Audit: tambah'], ['UPDATE', 'Audit: ubah'], ['DELETE', 'Audit: hapus']] },
    { key: 'kejadian', title: 'Halaman Kejadian', perm: 'logs.disasters', url: '/api/logs/kejadian', page: 'offset',
      actions: [['', 'Semua'], ['INSERT', 'Tambah'], ['UPDATE', 'Ubah / hapus'], ['DOWNLOAD_XLSX', 'Ekspor Excel']] },
    { key: 'masuk', title: 'Masuk & registrasi', perm: 'logs.all', url: '/api/admin/logs/login', page: 'page',
      actions: [['', 'Semua'], ['LOGIN_SUCCESS', 'Masuk berhasil'], ['LOGIN_FAILED', 'Masuk gagal'], ['LOGOUT', 'Keluar'], ['REGISTER', 'Registrasi']] },
    { key: 'unduhan', title: 'Unduhan', perm: 'logs.all', url: '/api/admin/logs/download', page: 'page',
      actions: [['', 'Semua'], ['DOWNLOAD_PRODUCT', 'Produk'], ['DOWNLOAD_DATASET', 'Dataset ZIP'], ['DOWNLOAD_FUSION', 'Fusion'],
        ['DOWNLOAD_REPORT', 'Laporan'], ['DOWNLOAD_XLSX', 'Excel'], ['EXPORT_CSV', 'CSV']] },
    { key: 'audit', title: 'Audit lengkap', perm: 'logs.all', url: '/api/admin/audit', page: 'page', actions: [] },
  ];
  const LIMIT = 50;
  let st = null;

  async function init(root, ctx) {
    const list = SECTIONS.filter(s => Auth.can(s.perm));
    const pick = list.find(s => s.key === ctx.sub) || list[0];
    st = { root, ctx, list, sec: pick, page: 1 };
    renderSub();
    UI.$('#lgFilter', root).addEventListener('submit', ev => { ev.preventDefault(); st.page = 1; UI.busy(UI.$('#lgApply', root), load); });
    syncFilter();
    await load();
  }

  function renderSub() {
    const box = UI.$('#lgSub', st.root);
    box.hidden = st.list.length < 2;
    box.innerHTML = '<div class="sub-row" role="tablist" aria-label="Bagian log">' + st.list.map(s =>
      '<button type="button" role="tab" data-tab="' + s.key + '" aria-selected="' + (s === st.sec) + '"' + (s === st.sec ? '' : ' tabindex="-1"') + '>' +
      UI.esc(s.title) + '</button>').join('') + '</div>';
    UI.bindTabs(UI.$('.sub-row', box), key => {
      st.sec = st.list.find(s => s.key === key); st.page = 1; syncFilter(); load();
    });
  }

  function syncFilter() {
    const $ = s => UI.$(s, st.root);
    const own = st.sec.page === 'offset';
    $('#lgKindBox').hidden = !own;
    $('#lgQBox').hidden = !own;
    $('#lgActBox').hidden = !st.sec.actions.length;
    $('#lgAct').innerHTML = st.sec.actions.map(([v, l]) => '<option value="' + v + '">' + UI.esc(l) + '</option>').join('');
  }

  async function load() {
    const $ = s => UI.$(s, st.root);
    const from = $('#lgFrom').value, to = $('#lgTo').value;
    if (from && to && from > to) { UI.showError('Log', { code: 'INVALID_DATE_RANGE' }); return; }
    const sec = st.sec;
    const q = sec.page === 'offset'
      ? { date_from: from, date_to: to, kind: $('#lgKind').value, action: $('#lgAct').value, q: $('#lgQ').value.trim(), limit: LIMIT, offset: (st.page - 1) * LIMIT }
      : { date_from: from, date_to: to, action: sec.actions.length ? $('#lgAct').value : '', page: st.page, limit: LIMIT };
    st.ctx.setStatus('Memuat…');
    let r;
    try { r = await API.get(sec.url + API.qs(q)); }
    catch (e) { $('#lgList').innerHTML = UI.emptyHTML('GAGAL MEMUAT'); UI.showError('Log', e); return; }
    if (!st) return;
    $('#lgList').innerHTML = UI.screenHTML({ channel: 'CH-01 · LOG ' + sec.title.toUpperCase(), rec: UI.int(r.total) + ' BARIS', recCls: 'off',
      body: UI.tableHTML(columns(sec.key), r.items, { empty: 'TIDAK ADA LOG', caption: 'Log ' + sec.title }) + UI.pagerHTML(r.total, LIMIT, (st.page - 1) * LIMIT) });
    UI.$$('#lgList [data-page]', st.root).forEach(b => b.addEventListener('click', () => { st.page = Number(b.dataset.page); load(); }));
    UI.$$('#lgList [data-detail]', st.root).forEach(b => b.addEventListener('click', () => detail(r.items[Number(b.dataset.detail)])));
    st.ctx.setStatus('Siap · ' + UI.int(r.total) + ' baris');
  }

  function columns(key) {
    const btn = (x, i) => '<button type="button" class="small" data-detail="' + i + '">Rincian…</button>';
    if (key === 'data' || key === 'kejadian') return [
      { label: 'Waktu', get: x => UI.dateTime(x.logged_at) }, { label: 'Jenis', get: x => x.kind === 'AUDIT' ? 'Audit' : 'Aktivitas' },
      { label: 'Aksi', key: 'action' }, { label: 'Objek', get: x => (x.target_type || '') + (x.target_id ? ' #' + x.target_id : '') },
      { label: 'Pengguna', get: x => x.username || '(sistem)' }, { label: '', html: true, get: btn }];
    if (key === 'masuk') return [
      { label: 'Waktu', get: x => UI.dateTime(x.logged_at) },
      { label: 'Pengguna', get: x => x.username || (x.username_attempted ? x.username_attempted + ' (percobaan)' : '') },
      { label: 'Hasil', html: true, get: x => ({ LOGIN_FAILED: '<span class="v-amber">GAGAL</span>', LOGOUT: 'KELUAR', REGISTER: '<span class="v-cyan">REGISTRASI</span>' }[x.action] || 'BERHASIL') },
      { label: 'IP', key: 'ip_address' }, { label: 'Peramban', get: x => (x.user_agent || '').slice(0, 60) }];
    if (key === 'unduhan') return [
      { label: 'Waktu', get: x => UI.dateTime(x.logged_at) }, { label: 'Pengguna', get: x => x.username || 'pengunjung' }, { label: 'Jenis', key: 'action' },
      { label: 'Objek', get: x => (x.target_type || '') + (x.target_id ? ' #' + x.target_id : '') + (x.detail && x.detail.filename ? ' · ' + x.detail.filename : '') },
      { label: 'Ukuran', cls: 'r', get: x => UI.bytes(x.bytes_sent) }];
    return [
      { label: 'Waktu', get: x => UI.dateTime(x.changed_at) }, { label: 'Tabel', key: 'table_name' }, { label: 'Baris', key: 'row_pk' },
      { label: 'Operasi', get: x => ({ I: 'INSERT', U: 'UPDATE', D: 'DELETE' }[x.operation] || x.operation) },
      { label: 'Pengguna', get: x => (x.app_user_id ? '#' + x.app_user_id : '(langsung DB)') + ' · ' + (x.db_user || '') },
      { label: 'Kolom berubah', get: x => (x.changed_columns || []).join(', ') }, { label: '', html: true, get: btn }];
  }

  function detail(x) {
    const d = x.detail || {};
    const old = x.old_data || d.old || {}, neu = x.new_data || d.new || {};
    const changed = x.changed_columns || d.changed_columns || [];
    const keys = Array.from(new Set(Object.keys(old).concat(Object.keys(neu)))).filter(k => k !== 'geom' && k !== 'bbox' && k !== 'location');
    const body = keys.length
      ? UI.tableHTML([{ label: 'Kolom', get: k => k },
          { label: 'Lama', html: true, get: k => '<span class="v-dim">' + UI.esc(JSON.stringify(old[k] ?? null)) + '</span>' },
          { label: 'Baru', html: true, get: k => '<span class="' + (changed.includes(k) ? 'v-amber' : '') + '">' + UI.esc(JSON.stringify(neu[k] ?? null)) + '</span>' }], keys)
      : '<pre class="scr-text" style="white-space:pre-wrap;margin:0">' + UI.esc(JSON.stringify(d, null, 2)) + '</pre>';
    UI.dialog({ title: 'Rincian log', wide: 'x', buttons: [{ label: 'Tutup', value: true, default: true, cancel: true }],
      body: UI.screenHTML({ channel: (x.action || x.operation || '') + ' · ' + (x.target_type || x.table_name || ''), body: body +
        '<p class="v-dim" style="margin:6px 0 0;font-size:11px">Kolom rahasia (password_hash, token_hash) disensor; geometri tidak ditampilkan.</p>' }) });
  }

  return { init };
})();
