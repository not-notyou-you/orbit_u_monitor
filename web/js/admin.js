// js/admin.js — Sistem › Manajemen akun dan Sistem › Pengaturan aplikasi (M56). Semua bagian ADMIN.
// Aksi yang memicu unduhan/pipeline (picu ingestion, proses ulang, periksa Live)
// selalu lewat dialog konfirmasi yang menyebut akibatnya.
//
// Susunan: dulu 12 tab rata dalam satu baris; lalu (M53) lima kelompok dengan
// tablist sendiri di dalam halaman ini. Masalahnya, kelompok yang dipilih hanya
// hidup di memori, jadi 13 bagiannya tidak bisa dibagikan, tidak bisa
// di-bookmark, dan hilang tiap refresh.
//
// Sekarang kelompoknya adalah tab router biasa (ROUTES di app.js), dan bagian
// di dalamnya adalah segmen ketiga hash: #pengaturan/jejak/audit. Halaman ini
// tinggal merender baris bagian + panelnya, dan mengikuti `ctx.sub`. Fungsi
// perender tiap bagian tidak berubah; hanya cara masuknya.
'use strict';
Pages['admin'] = (() => {
  const ROLES = [['USER', 'Relawan (USER)'], ['ANALYST', 'Analis (ANALYST)'], ['DATA_ENGINEER', 'Data Engineer'], ['ADMIN', 'Administrator']];
  const SEV = [['INFO', 'Info'], ['WARNING', 'Peringatan'], ['CRITICAL', 'Kritis']];
  const BANDS = ['RAIN_24H', 'RAIN_72H', 'RAIN_7D', 'RAIN_30D', 'NDVI', 'NDWI', 'FLOOD'];
  const OPS = { I: 'INSERT', U: 'UPDATE', D: 'DELETE' };

  // Bagian per kelompok. Kuncinya sekaligus segmen ketiga hash, jadi namanya
  // Indonesia dan sejalan dengan judulnya. Judul & keterangan kelompoknya
  // sendiri ada di ROUTES (app.js) sebagai title + lede.
  // M56: dua kelompok di bawah Sistem. Log (masuk, unduhan, audit) pindah ke
  // Sistem › Log (js/logs.js); kelompok `jejak` tetap ada untuk hash lama.
  const SECTIONS = {
    pengaturan: [{ key: 'ringkasan', title: 'Ringkasan' }, { key: 'pipeline', title: 'Pipeline' },
                 { key: 'scene', title: 'Scene' }, { key: 'live', title: 'Live Area' },
                 { key: 'penyimpanan', title: 'Penyimpanan' }, { key: 'arsip', title: 'Arsip' },
                 { key: 'wilayah', title: 'Wilayah' }, { key: 'aturan', title: 'Aturan & ambang' },
                 { key: 'aplikasi', title: 'Aplikasi' }],
    akses: [{ key: 'pengguna', title: 'Pengguna' }, { key: 'token', title: 'Token API' }],
    jejak: [{ key: 'masuk', title: 'Log Masuk' }, { key: 'unduhan', title: 'Log Unduhan' },
            { key: 'audit', title: 'Audit' }],
  };
  // Kelompok → tab router di bawah #sistem.
  const GROUP_TAB = { pengaturan: 'pengaturan', akses: 'pengguna', jejak: 'log' };
  const TABS = {
    ringkasan: tabSummary, pengguna: tabUsers, scene: tabScenes, live: tabLive, wilayah: tabRegions,
    aturan: tabRules, pipeline: tabPipeline, arsip: tabArchive, penyimpanan: tabStorage,
    aplikasi: tabSettings, token: tabTokens,
    masuk: () => tabLog('login'), unduhan: () => tabLog('download'), audit: tabAudit,
  };
  // Kelompok yang memuat sebuah bagian — dipakai Ringkasan untuk menyusun hash
  // tujuan "Buka →" tanpa perlu tahu susunannya.
  const groupOf = key => Object.keys(SECTIONS).find(g => SECTIONS[g].some(t => t.key === key)) || 'pengaturan';
  const hashOf = key => '#sistem/' + GROUP_TAB[groupOf(key)] + (key === 'ringkasan' ? '' : '/' + key);
  let st = null;

  // Kelompoknya datang dari router (ctx.tab), bagiannya dari segmen ketiga
  // (ctx.sub). Sub yang tidak dikenal — mis. hash lama atau salah tulis —
  // jatuh ke bagian pertama kelompok itu, bukan ke halaman kosong.
  async function init(root, ctx) {
    const group = (ctx.tab && (ctx.tab.group || ctx.tab.key)) || 'pengaturan';
    st = { root, ctx, group: group, tab: sectionKey(group, ctx.sub), users: null, page: {} };
    renderSub();
    await render();
  }
  function destroy() { if (st && st.map) st.map.remove(); st = null; }

  // Dipanggil router saat hanya segmen ketiga yang berubah: panel diganti,
  // fragmen dan baris bagiannya tetap.
  async function onSub(sub) {
    if (!st) return;
    const key = sectionKey(st.group, sub);
    if (key === st.tab) return;
    st.tab = key;
    syncSub();
    await render();
  }

  function sectionKey(group, sub) {
    const list = SECTIONS[group] || SECTIONS.pengaturan;
    return (list.find(t => t.key === sub) || list[0]).key;
  }

  // Baris bagian hanya dirender bila kelompoknya punya lebih dari satu bagian
  // (Ringkasan tidak). Memilih bagian berarti pindah hash, bukan mengubah state
  // internal — dengan begitu tombol Kembali peramban ikut menyusurinya.
  function renderSub() {
    const box = UI.$('#adSub', st.root);
    const list = SECTIONS[st.group] || [];
    box.hidden = list.length < 2;
    if (list.length < 2) { box.innerHTML = ''; return; }
    box.innerHTML = '<div class="sub-row" role="tablist" aria-label="Bagian ' +
      UI.esc((st.ctx.tab && st.ctx.tab.title) || 'Pengaturan') + '">' + list.map(t =>
        '<button type="button" role="tab" data-tab="' + t.key + '" aria-selected="' + (t.key === st.tab) + '"' +
        (t.key === st.tab ? '' : ' tabindex="-1"') + '>' + UI.esc(t.title) + '</button>').join('') + '</div>';
    UI.bindTabs(UI.$('.sub-row', box), key => { if (key !== st.tab) st.ctx.go(hashOf(key)); });
  }

  // Setelah router mengganti bagian, baris tabnya perlu ikut menunjuk ke sana.
  function syncSub() {
    UI.$$('#adSub .sub-row [role=tab]', st.root).forEach(b => {
      const on = b.dataset.tab === st.tab;
      b.setAttribute('aria-selected', String(on)); b.tabIndex = on ? 0 : -1;
    });
  }

  const panel = () => UI.$('#adPanel', st.root);
  const pg = k => st.page[k] || 1;
  async function users() { if (!st.users) st.users = (await API.get('/api/admin/users?limit=500')).items; return st.users; }
  const userOpts = list => '<option value="">Semua pengguna</option>' + list.map(u => '<option value="' + u.user_id + '">' + UI.esc(u.username) + '</option>').join('');

  async function render() {
    if (st.map) { st.map.remove(); st.map = null; }
    panel().innerHTML = UI.screenHTML({ channel: 'SYS', body: UI.loadingHTML() });
    const list = SECTIONS[st.group] || [];
    const groupTitle = (st.ctx.tab && st.ctx.tab.title) || 'Pengaturan';
    const title = (list.find(t => t.key === st.tab) || {}).title || groupTitle;
    const fn = TABS[st.tab];
    try { await fn(); st.ctx.setStatus('Siap · ' + groupTitle + (list.length > 1 ? ' → ' + title : '')); }
    catch (e) { panel().innerHTML = UI.screenHTML({ channel: 'SYS', body: UI.emptyHTML('GAGAL MEMUAT') }); UI.showError('Pengaturan', e); }
  }

  // ---------------------------------------------------------------- pembantu formulir dialog
  function fieldsHTML(fields) {
    return fields.map(f => {
      const id = 'af_' + f.id, req = f.required ? ' required' : '';
      const lbl = '<label for="' + id + '">' + UI.esc(f.label) + (f.required ? ' *' : '') + '</label>';
      let input;
      if (f.type === 'select') input = '<select id="' + id + '"' + req + '>' + f.options.map(([v, l]) => '<option value="' + UI.esc(v) + '"' + (String(f.value) === String(v) ? ' selected' : '') + '>' + UI.esc(l) + '</option>').join('') + '</select>';
      else if (f.type === 'checkbox') return '<label class="check"><input type="checkbox" id="' + id + '"' + (f.value ? ' checked' : '') + '> ' + UI.esc(f.label) + '</label>';
      else if (f.type === 'textarea') input = '<textarea id="' + id + '"' + req + '>' + UI.esc(f.value === undefined || f.value === null ? '' : f.value) + '</textarea>';
      else input = '<input type="' + (f.type || 'text') + '" id="' + id + '"' + req + (f.min !== undefined ? ' min="' + f.min + '"' : '') + (f.max !== undefined ? ' max="' + f.max + '"' : '') +
        (f.step ? ' step="' + f.step + '"' : '') + (f.maxlength ? ' maxlength="' + f.maxlength + '"' : '') + (f.autocomplete ? ' autocomplete="' + f.autocomplete + '"' : '') +
        ' value="' + UI.esc(f.value === undefined || f.value === null ? '' : f.value) + '">';
      return '<div class="field">' + lbl + input + (f.hint ? '<span class="hint">' + UI.esc(f.hint) + '</span>' : '') + '<span class="err" id="' + id + '_e"></span></div>';
    }).join('');
  }
  function collect(win, fields) {
    const out = {};
    fields.forEach(f => {
      const el = UI.$('#af_' + f.id, win);
      if (f.type === 'checkbox') out[f.id] = el.checked;
      else if (f.type === 'number') out[f.id] = el.value === '' ? null : Number(el.value);
      else out[f.id] = el.value === '' ? null : el.value;
    });
    return out;
  }
  function validate(win, fields, extra) {
    let ok = true;
    const v = collect(win, fields);
    fields.forEach(f => {
      if (f.type === 'checkbox') return;
      const x = v[f.id];
      let msg = '';
      if (f.required && (x === null || x === '')) msg = 'Wajib diisi.';
      else if (x !== null && f.type === 'number' && ((f.min !== undefined && x < f.min) || (f.max !== undefined && x > f.max))) msg = 'Rentang ' + f.min + '–' + f.max + '.';
      else if (x !== null && f.pattern && !new RegExp(f.pattern).test(x)) msg = f.patternMsg || 'Format tidak valid.';
      else if (x !== null && f.minlength && String(x).length < f.minlength) msg = 'Minimal ' + f.minlength + ' karakter.';
      if (!msg && extra) msg = extra(f.id, v) || '';
      UI.$('#af_' + f.id + '_e', win).textContent = msg;
      UI.$('#af_' + f.id, win).setAttribute('aria-invalid', msg ? 'true' : 'false');
      if (msg) ok = false;
    });
    const first = win.querySelector('[aria-invalid=true]'); if (first) first.focus();
    return ok;
  }
  // Dialog formulir; bila server menolak, dialog dibuka lagi dengan isian terakhir.
  async function formDialog(title, fields, submit, opts) {
    opts = opts || {};
    for (;;) {
      const v = await UI.dialog({ title, wide: opts.wide, message: opts.message, kind: opts.message ? 'question' : undefined,
        body: fieldsHTML(fields), buttons: [{ label: opts.ok || 'Simpan', value: 'ok', default: true }, { label: 'Batal', value: null, cancel: true }],
        validate: (win, val) => val !== 'ok' || validate(win, fields, opts.extra), collect: win => collect(win, fields) });
      if (!v || v === 'cancel') return null;
      try { return await submit(v); }
      catch (e) {
        await UI.showError(title, e);
        fields.forEach(f => { f.value = v[f.id]; });
      }
    }
  }
  const btn = (attr, label) => '<button type="button" class="small" ' + attr + '>' + UI.esc(label) + '</button>';
  const filterBar = inner => '<form class="ct-filters" novalidate style="display:flex;flex-wrap:wrap;gap:8px;align-items:end;margin-bottom:8px">' + inner + '<button type="submit">Terapkan</button></form>';
  function bindFilter(fn) { const f = UI.$('form.ct-filters', panel()); if (f) f.addEventListener('submit', ev => { ev.preventDefault(); fn(); }); }
  function bindPager(key, fn) { UI.$$('[data-page]', panel()).forEach(b => b.addEventListener('click', () => { st.page[key] = Number(b.dataset.page); fn(); })); }

  // ================================================================ 1. Pengguna
  async function tabUsers() {
    const p = panel();
    if (!UI.$('#auQ', p)) {
      p.innerHTML = filterBar('<div class="field" style="margin:0"><label for="auQ">Cari</label><input type="search" id="auQ" placeholder="nama / pengguna"></div>' +
        '<div class="field" style="margin:0"><label for="auRole">Peran</label><select id="auRole"><option value="">Semua</option>' + ROLES.map(([v, l]) => '<option value="' + v + '">' + l + '</option>').join('') + '</select></div>' +
        '<div class="field" style="margin:0"><label for="auAct">Status</label><select id="auAct"><option value="">Semua</option><option value="true">Aktif</option><option value="false">Nonaktif</option></select></div>') +
        '<div class="btn-row" style="margin-bottom:8px"><button type="button" class="default" id="auNew">Buat akun…</button></div><div id="auList"></div>';
      bindFilter(() => { st.page.users = 1; tabUsers(); });
      UI.$('#auNew', p).addEventListener('click', createUser);
    }
    const r = await API.get('/api/admin/users' + API.qs({ q: UI.$('#auQ', p).value, role_code: UI.$('#auRole', p).value, is_active: UI.$('#auAct', p).value, limit: 50, offset: (pg('users') - 1) * 50 }));
    UI.$('#auList', p).innerHTML = UI.screenHTML({ channel: 'CH-01 · AKUN PENGGUNA', rec: UI.int(r.total) + ' AKUN', recCls: 'off', body: UI.tableHTML([
      { label: 'Pengguna', key: 'username' }, { label: 'Nama', key: 'full_name' }, { label: 'Organisasi', key: 'organization' },
      { label: 'Peran', get: u => (ROLES.find(x => x[0] === u.role_code) || [0, u.role_code])[1] },
      { label: 'Status', html: true, get: u => (u.is_active ? 'AKTIF' : '<span class="v-dim">NONAKTIF</span>') + (u.is_locked ? ' <span class="v-amber">TERKUNCI</span>' : '') },
      { label: 'Masuk terakhir', get: u => u.last_login_at ? UI.dateTime(u.last_login_at) : 'belum pernah' },
      { label: 'Aksi', html: true, get: u => btn('data-edit="' + u.user_id + '"', 'Ubah…') + ' ' + btn('data-pw="' + u.user_id + '"', 'Reset sandi…') + (u.is_locked ? ' ' + btn('data-unlock="' + u.user_id + '"', 'Buka kunci') : '') },
    ], r.items, { empty: 'TIDAK ADA AKUN' }) + UI.pagerHTML(r.total, 50, (pg('users') - 1) * 50) });
    const find = id => r.items.find(u => String(u.user_id) === id);
    UI.$$('[data-edit]', p).forEach(b => b.addEventListener('click', () => editUser(find(b.dataset.edit))));
    UI.$$('[data-pw]', p).forEach(b => b.addEventListener('click', () => resetPw(find(b.dataset.pw))));
    UI.$$('[data-unlock]', p).forEach(b => b.addEventListener('click', () => UI.busy(b, async () => {
      try { await API.post('/api/admin/users/' + b.dataset.unlock + '/unlock'); tabUsers(); } catch (e) { UI.showError('Buka kunci', e); }
    })));
    bindPager('users', tabUsers);
  }
  async function createUser() {
    const r = await formDialog('Buat akun', [
      { id: 'username', label: 'Nama pengguna', required: true, pattern: '^[a-z0-9_.]{3,50}$', patternMsg: '3–50 karakter: huruf kecil, angka, titik, garis bawah.', autocomplete: 'off' },
      { id: 'full_name', label: 'Nama lengkap', required: true, maxlength: 100 }, { id: 'organization', label: 'Organisasi', maxlength: 100, value: 'GMLS' },
      { id: 'role_code', label: 'Peran', type: 'select', options: ROLES, value: 'USER' },
      { id: 'password', label: 'Kata sandi awal', type: 'password', required: true, minlength: 10, hint: 'Minimal 10 karakter. Sampaikan ke pengguna lewat jalur aman.', autocomplete: 'new-password' },
    ], v => API.post('/api/admin/users', v));
    if (r) { st.users = null; UI.info('Buat akun', 'Akun "' + r.username + '" dibuat.'); tabUsers(); }
  }
  async function editUser(u) {
    const r = await formDialog('Ubah akun ' + u.username, [
      { id: 'full_name', label: 'Nama lengkap', required: true, value: u.full_name, maxlength: 100 }, { id: 'organization', label: 'Organisasi', value: u.organization, maxlength: 100 },
      { id: 'role_code', label: 'Peran', type: 'select', options: ROLES, value: u.role_code }, { id: 'is_active', label: 'Akun aktif', type: 'checkbox', value: u.is_active },
    ], v => API.patch('/api/admin/users/' + u.user_id, v));
    if (r) { st.users = null; tabUsers(); }
  }
  async function resetPw(u) {
    const r = await formDialog('Reset kata sandi ' + u.username, [
      { id: 'new_password', label: 'Kata sandi baru', type: 'password', required: true, minlength: 10, autocomplete: 'new-password' },
    ], v => API.post('/api/admin/users/' + u.user_id + '/reset-password', v), { ok: 'Reset' });
    if (r) UI.info('Reset kata sandi', 'Kata sandi "' + u.username + '" diganti.');
  }

  // ================================================================ 2. Scene
  async function tabScenes() {
    const p = panel();
    if (!UI.$('#asSrc', p)) {
      p.innerHTML = '<div class="layout"><div class="control-panel">' +
        '<form id="asF" novalidate><fieldset><legend>Filter scene</legend>' +
        '<div class="field"><label for="asSrc">Sumber</label><select id="asSrc"><option value="S1">Sentinel-1</option><option value="MODIS">MODIS</option><option value="GPM">GPM</option></select></div>' +
        '<div class="field-row"><div class="field"><label for="asFrom">Dari</label><input type="date" id="asFrom"></div><div class="field"><label for="asTo">Sampai</label><input type="date" id="asTo"></div></div>' +
        '<label class="check"><input type="checkbox" id="asInv" checked> Sertakan yang dinonaktifkan</label>' +
        '<div class="btn-row end"><button type="submit">Terapkan</button></div></fieldset></form>' +
        '<form id="aiF" novalidate><fieldset><legend>Picu ingestion</legend>' +
        '<div class="field"><label for="aiJob">Jenis job</label><select id="aiJob"><option value="HYDROMET">Hidromet (GPM + MODIS) rentang tanggal</option><option value="LIVE">Siklus Live sekarang</option></select></div>' +
        '<div class="field-row" id="aiDates"><div class="field"><label for="aiFrom">Dari</label><input type="date" id="aiFrom"></div><div class="field"><label for="aiTo">Sampai</label><input type="date" id="aiTo"></div></div>' +
        '<div class="field hidden" id="aiAreaBox"><label for="aiArea">Live Area</label><select id="aiArea"></select></div>' +
        '<span class="err" id="aiErr"></span><span class="hint">Mengunduh data satelit (Hidromet ≤ 366 hari, berjalan di bawah kunci "hydromet").</span>' +
        '<div class="btn-row end"><button type="submit" id="aiGo">Jalankan…</button></div></fieldset></form>' +
        '</div><div class="deck" id="asList"></div></div>';
      UI.$('#asF', p).addEventListener('submit', ev => { ev.preventDefault(); st.page.scenes = 1; tabScenes(); });
      const job = UI.$('#aiJob', p);
      job.addEventListener('change', () => { UI.$('#aiDates', p).classList.toggle('hidden', job.value !== 'HYDROMET'); UI.$('#aiAreaBox', p).classList.toggle('hidden', job.value !== 'LIVE'); });
      API.get('/api/live/areas').then(a => { UI.$('#aiArea', p).innerHTML = a.map(x => '<option value="' + x.area_id + '">' + UI.esc(x.name) + '</option>').join(''); }).catch(() => {});
      UI.$('#aiF', p).addEventListener('submit', ingest);
    }
    const src = UI.$('#asSrc', p).value;
    const r = await API.get('/api/scenes' + API.qs({ source: src, include_invalid: UI.$('#asInv', p).checked || undefined,
      date_from: UI.$('#asFrom', p).value ? UI.$('#asFrom', p).value + 'T00:00:00Z' : '', date_to: UI.$('#asTo', p).value ? UI.$('#asTo', p).value + 'T23:59:59Z' : '',
      limit: 100, offset: (pg('scenes') - 1) * 100 }));
    const id = s => src === 'S1' ? s.scene_id : s.nasa_scene_id;
    UI.$('#asList', p).innerHTML = UI.screenHTML({ channel: 'CH-01 · SCENE ' + src, rec: UI.int(r.total) + ' BARIS', recCls: 'off', body: UI.tableHTML(
      (src === 'S1' ? [{ label: 'ID', key: 'scene_id' }, { label: 'Produk', get: s => s.product_identifier.slice(0, 40) + '…' }, { label: 'Akuisisi', get: s => UI.dateTime(s.acquisition_datetime) },
        { label: 'Orbit', get: s => (s.orbit_direction === 'ASCENDING' ? 'naik' : s.orbit_direction === 'DESCENDING' ? 'turun' : '—') + ' · rel ' + (s.relative_orbit ?? '—') }]
        : [{ label: 'ID', key: 'nasa_scene_id' }, { label: 'Produk', key: 'product_short_name' }, { label: 'Tile', key: 'tile_id' }, { label: 'Tanggal', get: s => UI.date(s.acquisition_date) }, { label: 'Run', key: 'run_type' }])
      .concat([{ label: 'Valid', html: true, get: s => s.is_valid ? 'YA' : '<span class="v-amber">TIDAK</span>' + (s.invalid_reason ? '<br><span class="v-dim">' + UI.esc(s.invalid_reason) + '</span>' : '') },
        { label: 'Aksi', html: true, get: s => btn('data-val="' + id(s) + '"', s.is_valid ? 'Nonaktifkan…' : 'Pulihkan') + ' ' + btn('data-rep="' + id(s) + '"', 'Proses ulang…') }]),
      r.items, { empty: 'TIDAK ADA SCENE' }) + UI.pagerHTML(r.total, 100, (pg('scenes') - 1) * 100) });
    const find = x => r.items.find(s => String(id(s)) === x);
    UI.$$('[data-val]', p).forEach(b => b.addEventListener('click', () => setValidity(src, find(b.dataset.val), id)));
    UI.$$('[data-rep]', p).forEach(b => b.addEventListener('click', () => reprocess(src, find(b.dataset.rep), id)));
    bindPager('scenes', tabScenes);
  }
  async function setValidity(src, s, id) {
    if (s.is_valid) {
      const r = await formDialog('Nonaktifkan scene #' + id(s), [{ id: 'reason', label: 'Alasan (wajib)', type: 'textarea', required: true, minlength: 3 }],
        v => API.patch('/api/admin/scenes/' + src + '/' + id(s), { is_valid: false, reason: v.reason }),
        { ok: 'Nonaktifkan', message: 'Scene dinonaktifkan (soft delete), tidak dihapus. Data turunannya tidak dipakai lagi sampai dipulihkan.' });
      if (r) tabScenes();
    } else {
      if (!await UI.confirm('Pulihkan scene', 'Pulihkan scene #' + id(s) + ' menjadi valid kembali?', 'Pulihkan')) return;
      try { await API.patch('/api/admin/scenes/' + src + '/' + id(s), { is_valid: true }); tabScenes(); } catch (e) { UI.showError('Pulihkan scene', e); }
    }
  }
  async function reprocess(src, s, id) {
    const what = src === 'S1' ? 'Scene Live tanggal itu dicoba ulang (unduh MODIS/GPM yang gagal).' : 'Job Hidromet tanggal itu diulang: COG yang belum Final dibangun ulang (dapat mengunduh granule NASA).';
    if (!await UI.confirm('Proses ulang', 'Proses ulang ' + src + ' #' + id(s) + '?\n\n' + what, 'Proses ulang')) return;
    try { const r = await API.post('/api/admin/scenes/' + src + '/' + id(s) + '/reprocess'); UI.info('Proses ulang', r.message || 'Diterima; berjalan di latar belakang.'); }
    catch (e) { UI.showError('Proses ulang', e); }
  }
  async function ingest(ev) {
    ev.preventDefault();
    const p = panel(), job = UI.$('#aiJob', p).value, a = UI.$('#aiFrom', p).value, b = UI.$('#aiTo', p).value;
    let msg = '';
    if (job === 'HYDROMET') {
      if (!a || !b) msg = 'Isi kedua tanggal.'; else if (a > b) msg = 'Tanggal akhir sebelum tanggal awal.';
      else if ((UI.parseDate(b) - UI.parseDate(a)) / 864e5 + 1 > 366) msg = 'Maksimal 366 hari.';
    }
    UI.$('#aiErr', p).textContent = msg; if (msg) return;
    const body = job === 'HYDROMET' ? { job, date_from: a, date_to: b } : { job, area_id: Number(UI.$('#aiArea', p).value) };
    if (!await UI.confirm('Picu ingestion', job === 'HYDROMET'
      ? 'Jalankan job Hidromet ' + UI.date(a) + ' – ' + UI.date(b) + '? Sistem akan mengunduh granule GPM dan MODIS (±130 detik per tanggal) dan menulis observasi + alert.'
      : 'Jalankan siklus Live sekarang? Sistem akan mencari dan mengunduh scene Sentinel-1 baru beserta MODIS/GPM.', 'Jalankan')) return;
    await UI.busy(UI.$('#aiGo', p), async () => {
      try { const r = await API.post('/api/admin/ingest', body); UI.info('Picu ingestion', r.message || 'Diterima (202); berjalan di latar belakang. Pantau di tab Pipeline.'); }
      catch (e) { UI.showError('Picu ingestion', e); }
    });
  }

  // ================================================================ 3. Live Area
  async function tabLive() {
    const [areas, maxA] = await Promise.all([API.get('/api/live/areas'), API.get('/api/admin/settings').then(s => (s.items.find(x => x.setting_key === 'live.max_areas') || {}).setting_value).catch(() => 5)]);
    panel().innerHTML = '<div class="btn-row" style="margin-bottom:8px"><button type="button" class="default" id="alNew"' + (areas.length >= (maxA || 5) ? ' disabled' : '') + '>Tambah Live Area…</button>' +
      '<span class="mut">' + UI.int(areas.length) + ' dari maksimal ' + UI.int(maxA || 5) + ' area.</span></div>' +
      UI.screenHTML({ channel: 'CH-01 · LIVE AREA', body: UI.tableHTML([
        { label: 'Nama', key: 'name' }, { label: 'Lokasi', key: 'location_label' }, { label: 'Retensi', cls: 'r', get: a => a.retention + ' scene' },
        { label: 'Scene', cls: 'r', key: 'scene_count' }, { label: 'Terbaru', get: a => UI.date(a.latest_scene_date) },
        { label: 'Status', get: a => (a.enabled ? '' : 'NONAKTIF · ') + a.status + (a.running ? ' (berjalan)' : '') }, { label: 'Ukuran', cls: 'r', get: a => UI.bytes(a.total_size_bytes) },
        { label: 'Aksi', html: true, get: a => btn('data-ed="' + a.area_id + '"', 'Ubah…') + ' ' + btn('data-del="' + a.area_id + '"', 'Hapus…') },
      ], areas, { empty: 'BELUM ADA LIVE AREA' }) });
    const find = id => areas.find(a => String(a.area_id) === id);
    UI.$('#alNew', panel()).addEventListener('click', addArea);
    UI.$$('[data-ed]', panel()).forEach(b => b.addEventListener('click', async () => {
      const a = find(b.dataset.ed);
      const r = await formDialog('Ubah Live Area', [{ id: 'name', label: 'Nama', required: true, value: a.name, maxlength: 200 },
        { id: 'retention', label: 'Retensi scene (1–60)', type: 'number', min: 1, max: 60, required: true, value: a.retention, hint: 'Menurunkan retensi menghapus scene tertua secara permanen.' },
        { id: 'enabled', label: 'Aktif (dipantau penjadwal)', type: 'checkbox', value: a.enabled }],
        v => API.patch('/api/live/areas/' + a.area_id, v));
      if (r) tabLive();
    }));
    UI.$$('[data-del]', panel()).forEach(b => b.addEventListener('click', async () => {
      const a = find(b.dataset.del);
      if (!await UI.confirm('Hapus Live Area', 'Hapus "' + a.name + '"? Semua berkas scene-nya dihapus permanen; log tetap disimpan.', 'Hapus')) return;
      try { await API.del('/api/live/areas/' + a.area_id); tabLive(); } catch (e) { UI.showError('Hapus Live Area', e); }
    }));
  }
  async function addArea() {
    const rois = (await API.get('/api/rois')).items;
    const r = await formDialog('Tambah Live Area', [
      { id: 'region_id', label: 'Lokasi (ROI sistem)', type: 'select', options: rois.map(x => [x.region_id, x.name]), value: rois[0] && rois[0].region_id },
      { id: 'name', label: 'Nama area (opsional)', maxlength: 200 }, { id: 'retention', label: 'Retensi scene (1–60)', type: 'number', min: 1, max: 60, value: 6, required: true }],
      v => API.post('/api/live/areas', { region_id: Number(v.region_id), name: v.name, retention: v.retention }),
      { ok: 'Simpan & mulai', message: 'Sistem akan langsung mengunduh scene Sentinel-1 terbaru beserta MODIS/GPM untuk area ini.' });
    if (r) tabLive();
  }

  // ================================================================ 4. Wilayah
  async function tabRegions() {
    const [r, geo] = await Promise.all([API.get('/api/admin/regions'), API.get('/api/regions?all=true').catch(() => null)]);
    const kec = r.items.filter(x => x.admin_level === 3);
    panel().innerHTML = '<div class="layout wide-left"><div class="control-panel">' +
      '<fieldset><legend>Kecamatan dalam AOI GMLS</legend><div class="listbox" id="arList" style="max-height:340px">' +
      kec.map(x => '<label><input type="checkbox" data-aoi="' + x.region_id + '"' + (x.in_aoi ? ' checked' : '') + '> ' + UI.esc(x.region_name) + '<span class="sub">' + UI.num(x.area_km2, 0) + ' km²</span></label>').join('') +
      '</div><p class="mut" style="margin:4px 0 0;font-size:11px">Mengubah centang langsung membangun ulang ROI AOI dan dataset HYDROMET_AOI. Minimal satu kecamatan.</p></fieldset>' +
      '<form id="arRoi" novalidate><fieldset><legend>ROI gabungan kecamatan</legend><div class="listbox" style="max-height:200px">' +
      kec.map(x => '<label><input type="checkbox" data-roi="' + x.region_id + '"> ' + UI.esc(x.region_name) + '</label>').join('') + '</div>' +
      '<div class="field"><label for="arName">Nama ROI</label><input type="text" id="arName" maxlength="100"></div>' +
      '<div class="field"><label for="arCode">Kode (opsional, A–Z 0–9 _)</label><input type="text" id="arCode" maxlength="20"></div><span class="err" id="arErr"></span>' +
      '<div class="btn-row end"><button type="submit" id="arGo">Buat ROI</button></div></fieldset></form><div id="arExcel"></div></div>' +
      '<div class="deck">' + UI.screenHTML({ channel: 'CH-01 · KECAMATAN KAB. LEBAK (COD-AB)', flush: true, rec: UI.int(kec.filter(x => x.in_aoi).length) + ' DALAM AOI', recCls: 'off', body: '<div class="map tall" id="arMap" role="img" aria-label="Peta kecamatan; AOI ditandai label ★"></div>' }) +
      '<div class="legend" style="color:var(--text)"><span><i style="background:#33ff99"></i>★ DALAM AOI</span><span><i style="background:transparent"></i>DI LUAR AOI</span></div></div></div>';
    Excel.mount(UI.$('#arExcel', panel()), ['kecamatan'], { onImported: tabRegions });
    st.map = Maps.create(UI.$('#arMap', panel()));
    if (st.map && geo) {
      const inAoi = new Set(kec.filter(x => x.in_aoi).map(x => x.region_id));
      const layer = L.geoJSON(geo, { style: f => inAoi.has(f.properties.region_id) ? { color: '#33ff99', weight: 1, fillColor: '#33ff99', fillOpacity: 0.4 } : { color: '#1a9960', weight: 1, fillOpacity: 0 },
        onEachFeature: (f, l) => {
          const on = inAoi.has(f.properties.region_id);
          if (on) l.bindTooltip('★', { permanent: true, direction: 'center', className: 'map-label' });
          l.bindPopup(UI.esc(f.properties.name) + (on ? ' — dalam AOI' : ' — di luar AOI'));
        } }).addTo(st.map);
      setTimeout(() => { if (st && st.map) { st.map.invalidateSize(); st.map.fitBounds(layer.getBounds()); } }, 100);
    }
    UI.$$('[data-aoi]', panel()).forEach(c => c.addEventListener('change', async () => {
      const name = kec.find(x => String(x.region_id) === c.dataset.aoi).region_name;
      if (!await UI.confirm('Ubah AOI', (c.checked ? 'Masukkan ' : 'Keluarkan ') + name + (c.checked ? ' ke' : ' dari') + ' AOI GMLS? ROI AOI dan dataset HYDROMET_AOI dibangun ulang; data kecamatan ini mulai/berhenti dihitung pada job hidromet berikutnya.', 'Ubah')) { c.checked = !c.checked; return; }
      try { await API.patch('/api/admin/regions/' + c.dataset.aoi, { in_aoi: c.checked }); tabRegions(); }
      catch (e) { c.checked = !c.checked; UI.showError('Ubah AOI', e); }
    }));
    UI.$('#arRoi', panel()).addEventListener('submit', async ev => {
      ev.preventDefault();
      const ids = UI.$$('[data-roi]:checked', panel()).map(c => Number(c.dataset.roi)), name = UI.$('#arName', panel()).value.trim(), code = UI.$('#arCode', panel()).value.trim();
      const msg = !ids.length ? 'Pilih minimal satu kecamatan.' : name.length < 2 ? 'Isi nama ROI (minimal 2 karakter).' : code && !/^[A-Z0-9_]{2,20}$/.test(code) ? 'Kode: 2–20 karakter A–Z, 0–9, _.' : '';
      UI.$('#arErr', panel()).textContent = msg; if (msg) return;
      await UI.busy(UI.$('#arGo', panel()), async () => {
        try { const r2 = await API.post('/api/admin/rois', { region_ids: ids, name, region_code: code || null }); UI.info('ROI gabungan', 'ROI "' + (r2.name || name) + '" dibuat dan tersedia di Buat Dataset dan Live Area.'); tabRegions(); }
        catch (e) { UI.showError('ROI gabungan', e); }
      });
    });
  }

  // ================================================================ 5. Aturan & ambang
  async function tabRules() {
    const [rules, th, types] = await Promise.all([API.get('/api/alert-rules'), API.get('/api/admin/quality-thresholds'), API.get('/api/disaster-types?include_inactive=true')]);
    panel().innerHTML =
      '<div class="btn-row" style="margin-bottom:8px"><button type="button" id="rrNew">Tambah aturan alert…</button><button type="button" id="rtNew">Tambah jenis bencana…</button></div>' +
      UI.screenHTML({ channel: 'CH-01 · ATURAN ALERT', body: UI.tableHTML([
        { label: 'Kode', key: 'rule_code' }, { label: 'Bencana', key: 'disaster_type_code' }, { label: 'Band', key: 'band_code' },
        { label: 'Ambang', cls: 'r', get: x => x.comparator + ' ' + (x.threshold_value === null ? UI.NA : UI.num(x.threshold_value, 1)) },
        { label: 'Tingkat', get: x => (SEV.find(s => s[0] === x.severity) || [0, x.severity])[1] }, { label: 'Rujukan', key: 'reference_source' },
        { label: 'Aktif', get: x => x.is_active ? 'YA' : 'TIDAK' }, { label: 'Aksi', html: true, get: x => btn('data-rule="' + x.rule_id + '"', 'Ubah…') },
      ], rules.items) + '<p class="v-dim" style="margin:6px 0 0;font-size:11px">Aturan tidak dihapus; nonaktifkan bila tidak dipakai. Aturan aktif wajib punya ambang.</p>' }) +
      '<div style="height:8px"></div>' + UI.screenHTML({ channel: 'CH-02 · AMBANG KUALITAS DATA (QA)', body: UI.tableHTML([
        { label: 'Band', key: 'band_code' }, { label: 'Metrik', key: 'metric_name' },
        { label: 'Waspada <', cls: 'r', get: x => UI.num(x.warn_below, 3) }, { label: 'Gagal <', cls: 'r', get: x => UI.num(x.fail_below, 3) },
        { label: 'Waspada >', cls: 'r', get: x => UI.num(x.warn_above, 3) }, { label: 'Gagal >', cls: 'r', get: x => UI.num(x.fail_above, 3) },
        { label: 'Rujukan', key: 'reference' }, { label: 'Aktif', get: x => x.is_active ? 'YA' : 'TIDAK' }, { label: 'Aksi', html: true, get: x => btn('data-th="' + x.threshold_id + '"', 'Ubah…') },
      ], th.items) }) +
      '<div style="height:8px"></div>' + UI.screenHTML({ channel: 'CH-03 · JENIS BENCANA', body: UI.tableHTML([
        { label: 'Kode', key: 'type_code' }, { label: 'Nama', key: 'type_name' }, { label: 'Kategori', key: 'category' }, { label: 'Band indikator', key: 'indicator_bands' },
        { label: 'Aktif', get: x => x.is_active ? 'YA' : 'TIDAK' }, { label: 'Aksi', html: true, get: x => btn('data-type="' + x.disaster_type_id + '"', 'Ubah…') },
      ], types.items) }) + '<div id="rrExcel" style="margin-top:8px;max-width:420px"></div>';
    Excel.mount(UI.$('#rrExcel', panel()), ['alert_rules', 'disaster_types'], { onImported: tabRules });
    const typeOpts = types.items.filter(t => t.is_active).map(t => [t.type_code, t.type_name]);
    const ruleFields = x => [
      ...(x ? [] : [{ id: 'rule_code', label: 'Kode aturan', required: true, pattern: '^[A-Z0-9_]{3,40}$', patternMsg: '3–40 karakter A–Z, 0–9, _.' },
        { id: 'disaster_type_code', label: 'Jenis bencana', type: 'select', options: typeOpts }, { id: 'band_code', label: 'Band', type: 'select', options: BANDS.map(b => [b, b]) }]),
      { id: 'comparator', label: 'Pembanding', type: 'select', options: [['>=', '≥'], ['>', '>'], ['<=', '≤'], ['<', '<']], value: x ? x.comparator : '>=' },
      { id: 'threshold_value', label: 'Nilai ambang', type: 'number', step: 'any', value: x ? x.threshold_value : null },
      { id: 'severity', label: 'Tingkat', type: 'select', options: SEV, value: x ? x.severity : 'INFO' },
      { id: 'reference_source', label: 'Rujukan', required: true, value: x ? x.reference_source : '', maxlength: 150 },
      { id: 'is_active', label: 'Aktif', type: 'checkbox', value: x ? x.is_active : true }];
    const ruleExtra = (id, v) => id === 'threshold_value' && v.is_active && v.threshold_value === null ? 'Aturan aktif wajib punya ambang.' : '';
    UI.$('#rrNew', panel()).addEventListener('click', async () => { if (await formDialog('Tambah aturan alert', ruleFields(null), v => API.post('/api/alert-rules', v), { extra: ruleExtra })) tabRules(); });
    UI.$$('[data-rule]', panel()).forEach(b => b.addEventListener('click', async () => {
      const x = rules.items.find(r => String(r.rule_id) === b.dataset.rule);
      if (await formDialog('Ubah aturan ' + x.rule_code, ruleFields(x), v => API.put('/api/alert-rules/' + x.rule_id, v), { extra: ruleExtra,
        message: 'Perubahan ambang berlaku pada pengecekan alert berikutnya dan tercatat di audit.' })) tabRules();
    }));
    UI.$$('[data-th]', panel()).forEach(b => b.addEventListener('click', async () => {
      const x = th.items.find(t => String(t.threshold_id) === b.dataset.th);
      const f = ['warn_below', 'fail_below', 'warn_above', 'fail_above'].map(k => ({ id: k, label: { warn_below: 'Waspada bila di bawah', fail_below: 'Gagal bila di bawah', warn_above: 'Waspada bila di atas', fail_above: 'Gagal bila di atas' }[k], type: 'number', step: 'any', value: x[k] }))
        .concat([{ id: 'reference', label: 'Rujukan', value: x.reference }, { id: 'is_active', label: 'Aktif', type: 'checkbox', value: x.is_active }]);
      if (await formDialog('Ambang QA ' + x.band_code + ' · ' + x.metric_name, f, v => API.put('/api/admin/quality-thresholds', [Object.assign({ threshold_id: x.threshold_id }, v)]))) tabRules();
    }));
    const typeFields = x => [...(x ? [] : [{ id: 'type_code', label: 'Kode', required: true, pattern: '^[A-Z0-9_]{3,30}$', patternMsg: '3–30 karakter A–Z, 0–9, _.' }]),
      { id: 'type_name', label: 'Nama', required: true, minlength: 2, value: x ? x.type_name : '' }, { id: 'category', label: 'Kategori', value: x ? x.category : 'HIDROMETEOROLOGI' },
      { id: 'indicator_bands', label: 'Band indikator', value: x ? x.indicator_bands : '', hint: 'mis. RAIN_24H, VH, FLOOD' }, { id: 'is_active', label: 'Aktif', type: 'checkbox', value: x ? x.is_active : true }];
    UI.$('#rtNew', panel()).addEventListener('click', async () => { if (await formDialog('Tambah jenis bencana', typeFields(null), v => API.post('/api/disaster-types', v))) tabRules(); });
    UI.$$('[data-type]', panel()).forEach(b => b.addEventListener('click', async () => {
      const x = types.items.find(t => String(t.disaster_type_id) === b.dataset.type);
      if (await formDialog('Ubah jenis ' + x.type_code, typeFields(x), v => API.put('/api/disaster-types/' + x.disaster_type_id, v))) tabRules();
    }));
  }

  // ================================================================ 6. Pipeline
  async function tabPipeline() {
    const s = await API.get('/api/admin/pipeline/status');
    const areas = s.live_areas || [];
    const logs = (await Promise.all(areas.map(a => API.get('/api/live/areas/' + a.area_id + '/activity?limit=50').catch(() => []))))
      .flatMap((l, i) => l.map(x => Object.assign({ area: areas[i].name }, x))).sort((a, b) => (a.timestamp < b.timestamp ? 1 : -1)).slice(0, 50);
    const cred = s.credentials || {};
    const warn = Object.entries(cred).filter(([, ok]) => !ok).map(([k]) => k);
    panel().innerHTML = (warn.length ? '<div class="banner raised" role="alert">' + UI.icon('warn32') + '<div class="b-body"><b>Kredensial belum diisi:</b> ' + UI.esc(warn.join(', ')) + '. Job yang membutuhkannya akan gagal.</div></div>' : '') +
      '<div class="readouts" style="margin-bottom:8px">' +
        UI.readoutHTML('HIDROMET TERAKHIR', UI.esc(UI.date(s.hydromet && s.hydromet.last_completed)), 'WAITING ' + UI.int(s.hydromet && s.hydromet.waiting) + ' · GAGAL ' + UI.int(s.hydromet && s.hydromet.failed), s.hydromet && s.hydromet.failed ? 'v-amber' : '') +
        UI.readoutHTML('ANTREAN DATASET', UI.int((s.queue || {}).dataset_jobs_queued), 'JOB MENUNGGU') +
        UI.readoutHTML('DILEWATI (KUNCI) 7 HARI', UI.int((s.skipped_locked_7d || []).length), 'SKIPPED_LOCKED') +
        UI.readoutHTML('KREDENSIAL', warn.length ? 'KURANG' : 'LENGKAP', 'NASA · COPERNICUS', warn.length ? 'v-alert' : '') + '</div>' +
      '<div class="cols-2">' + UI.screenHTML({ channel: 'CH-01 · JOB TERAKHIR PER JENIS', body: UI.tableHTML([
        { label: 'Jenis', key: 'kind' }, { label: 'Job', key: 'job_id' }, { label: 'Status', key: 'status' }, { label: 'Tanggal data', get: j => UI.date(j.date_range_start) },
        { label: 'Mulai', get: j => UI.dateTime(j.started_at) }, { label: 'Selesai', get: j => j.completed_at ? UI.dateTime(j.completed_at) : '' }], s.latest_jobs || []) }) +
      UI.screenHTML({ channel: 'CH-02 · LIVE AREA & LAPORAN', body: UI.tableHTML([{ label: 'Area', key: 'name' }, { label: 'Status', key: 'status' }, { label: 'Diperiksa', get: a => UI.dateTime(a.last_checked_at) }], areas) +
        UI.tableHTML([{ label: 'Laporan', key: 'report_code' }, { label: 'Periode', get: r => UI.date(r.period_start) }, { label: 'Status', key: 'status' }, { label: 'Dibuat', get: r => UI.dateTime(r.generated_at) }], s.reports || [], { empty: 'BELUM ADA LAPORAN' }) }) + '</div>' +
      '<div style="height:8px"></div>' + UI.screenHTML({ channel: 'CH-03 · JADWAL PENJADWAL', body: (s.scheduler || []).length ? UI.tableHTML([{ label: 'Job', get: x => x.id || x.name }, { label: 'Berikutnya', get: x => UI.dateTime(x.next_run_time || x.next) }, { label: 'Jadwal', get: x => x.trigger || '' }], s.scheduler)
        : UI.emptyHTML('PENJADWAL TIDAK AKTIF DI PROSES INI (SCHEDULER_ENABLED=false)') }) +
      '<div style="height:8px"></div>' + UI.screenHTML({ channel: 'CH-04 · LOG 50 TERAKHIR (LIVE + PIPELINE)', body: '<div class="scr-log" style="max-height:320px">' + (logs.length ? logs.map(x =>
        '<div><span class="v-dim">' + UI.esc(UI.dateTime(x.timestamp)) + '</span> [' + UI.esc(x.area) + '] ' + UI.esc(x.stage || x.module || '') + ' <span class="' + (/FAIL|ERROR/.test(x.status) ? 'v-alert' : /RUN|START/.test(x.status) ? 'v-amber' : '') + '">' + UI.esc(x.status || '') + '</span> ' + UI.esc(x.message || '') + '</div>').join('') : UI.emptyHTML()) + '</div>' });
  }

  // ================================================================ 7. Arsip
  async function tabArchive() {
    const s = await API.get('/api/admin/archive/stats');
    panel().innerHTML = '<div class="layout"><div class="control-panel"><form id="avF" novalidate><fieldset><legend>Verifikasi checksum</legend>' +
      '<div class="field"><label for="avN">Ukuran sampel (1–500)</label><input type="number" id="avN" min="1" max="500" value="50"></div>' +
      '<div class="field"><label for="avS">Sumber</label><select id="avS"><option value="">Semua</option><option>SENTINEL1</option><option>MODIS</option><option>GPM</option><option>FUSION</option></select></div>' +
      '<span class="hint">Membaca berkas acak dan membandingkan SHA-256 dengan katalog. Tidak mengubah data.</span>' +
      '<div class="btn-row end"><button type="submit" id="avGo">Verifikasi</button></div></fieldset></form></div><div class="deck">' +
      UI.screenHTML({ channel: 'CH-01 · PRODUK PER SUMBER × TIER', body: UI.tableHTML([{ label: 'Sumber', key: 'source' }, { label: 'Tier', key: 'tier' },
        { label: 'Produk', cls: 'r', get: x => UI.int(x.n) }, { label: 'MB', cls: 'r', get: x => UI.num(x.mb, 1) }, { label: 'Tidak valid', cls: 'r', get: x => UI.int(x.invalid) }], s.products) }) +
      UI.screenHTML({ channel: 'CH-02 · JUMLAH BARIS', body: '<dl class="kv">' + Object.entries(s.rows || {}).map(([k, v]) => '<dt>' + UI.esc(k) + '</dt><dd class="num">' + UI.int(v) + '</dd>').join('') +
        '<dt>rentang hidromet</dt><dd>' + UI.esc(s.hydromet_span && s.hydromet_span.first ? UI.date(s.hydromet_span.first) + ' – ' + UI.date(s.hydromet_span.last) : UI.NA) + '</dd></dl>' }) +
      '<div id="avOut"></div></div></div>';
    UI.$('#avF', panel()).addEventListener('submit', async ev => {
      ev.preventDefault();
      const n = Number(UI.$('#avN', panel()).value);
      if (!(n >= 1 && n <= 500)) { UI.showError('Verifikasi', 'Ukuran sampel 1–500.'); return; }
      await UI.busy(UI.$('#avGo', panel()), async () => {
        try {
          const r = await API.post('/api/admin/archive/verify', { limit: n, source: UI.$('#avS', panel()).value || null });
          UI.$('#avOut', panel()).innerHTML = UI.screenHTML({ channel: 'CH-03 · HASIL VERIFIKASI', rec: (r.missing.length || r.mismatch.length) ? '● MASALAH' : '● OK', recCls: (r.missing.length || r.mismatch.length) ? 'live' : 'off',
            body: '<p class="scr-text" style="margin:0">DIPERIKSA ' + UI.int(r.checked) + ' · COCOK ' + UI.int(r.ok) + ' · <span class="' + (r.missing.length ? 'v-alert' : '') + '">HILANG ' + UI.int(r.missing.length) + '</span> · <span class="' + (r.mismatch.length ? 'v-alert' : '') + '">BEDA ' + UI.int(r.mismatch.length) + '</span></p>' +
              (r.missing.length || r.mismatch.length ? '<div class="scr-log">' + r.missing.map(x => '<div class="v-alert">HILANG ' + UI.esc(JSON.stringify(x)) + '</div>').join('') + r.mismatch.map(x => '<div class="v-alert">BEDA ' + UI.esc(JSON.stringify(x)) + '</div>').join('') + '</div>' : '') });
        } catch (e) { UI.showError('Verifikasi', e); }
      });
    });
  }

  // ================================================================ 7b. Penyimpanan
  // Ringkasan disk SELURUH mesin (semua dataset digabung), berbeda dari tab
  // Struktur di Katalog yang hanya menghitung satu dataset. Hanya baca:
  // berkas dihapus lewat penghapusan dataset dan retensi Live, tidak dari sini.
  async function tabStorage() {
    const s = await API.get('/api/storage/summary');
    const totalMb = ((s.total || {}).size_mb) || 0;
    const tiers = Object.entries(s.tiers || {}).filter(([, t]) => t.file_count > 0);
    const empty = Object.keys(s.tiers || {}).length - tiers.length;
    const part = s.partial_downloads || {};

    panel().innerHTML =
      '<div class="readouts" style="margin-bottom:8px">' +
        UI.readoutHTML('TOTAL DI DISK', UI.esc((s.total || {}).size_human || UI.NA), 'SELURUH DATASET') +
        UI.readoutHTML('TIER TERPAKAI', UI.int(tiers.length), 'KOSONG ' + UI.int(empty)) +
        UI.readoutHTML('UNDUHAN TERPUTUS', UI.int(part.file_count), UI.esc(part.size_human || '0 MB'),
          part.file_count ? 'v-amber' : '') +
      '</div>' +
      UI.screenHTML({ channel: 'CH-01 · PENYIMPANAN PER TIER', rec: UI.esc((s.total || {}).size_human || ''), recCls: 'off',
        body: tiers.length ? tiers.map(([name, t]) =>
          UI.barHTML(name, t.size_mb, totalMb, t.size_human) +
          '<p class="v-dim" style="margin:0 0 4px 116px;font-size:11px">' + UI.int(t.file_count) + ' berkas' +
          (t.description ? ' · ' + UI.esc(t.description) : '') +
          (Object.keys(t.sources || {}).length ? ' · ' + Object.entries(t.sources).map(([k, v]) =>
            UI.esc((UI.SOURCE_LABEL[k] || k) + ' ' + v.size_human)).join(' · ') : '') +
          ' · <a href="#" data-stier="' + UI.esc(name) + '">daftar berkas</a></p>').join('')
          : UI.emptyHTML('BELUM ADA BERKAS DI DISK') }) +
      '<div style="height:8px"></div>' +
      '<div class="cols-2">' +
        UI.screenHTML({ channel: 'CH-02 · PER SATELIT', body: UI.tableHTML([
          { label: 'Sumber', get: x => UI.SOURCE_LABEL[x.src] || x.src },
          { label: 'Berkas', cls: 'r', get: x => UI.int(x.file_count) },
          { label: 'Ukuran', cls: 'r', get: x => x.size_human },
        ], Object.entries(s.by_source || {}).map(([src, v]) => Object.assign({ src: src }, v)),
          { empty: 'BELUM ADA BERKAS PER SATELIT' }) }) +
        UI.screenHTML({ channel: 'CH-03 · UNDUHAN TERPUTUS (.part)', rec: part.file_count ? '● ADA' : '● TIDAK ADA', recCls: part.file_count ? '' : 'off',
          body: '<p class="scr-text" style="margin:0">' + UI.int(part.file_count) + ' BERKAS · ' + UI.esc(part.size_human || '0 MB') + '</p>' +
            '<p class="v-dim" style="margin:4px 0 0;font-size:11px">Berkas .part adalah unduhan yang terhenti; pipeline melanjutkannya sendiri pada siklus berikutnya.' +
            (part.file_count ? ' <a href="#" data-stier="partial">daftar berkas</a>' : '') + '</p>' }) +
      '</div>' +
      '<div id="stFiles"></div>';

    bindStorageFiles();
  }

  // Satu tier bisa tersebar di banyak folder dataset, jadi daftarnya diratakan
  // dulu dan dibatasi 500 baris — sama seperti daftar berkas di Katalog, yang
  // tanpa batas itu pernah membekukan tab.
  function bindStorageFiles() {
    UI.$$('[data-stier]', panel()).forEach(a => a.addEventListener('click', async ev => {
      ev.preventDefault();
      const tier = a.dataset.stier;
      const box = UI.$('#stFiles', panel());
      box.innerHTML = '<div style="height:8px"></div>' + UI.screenHTML({ channel: 'BERKAS ' + tier.toUpperCase(), body: UI.loadingHTML() });
      try {
        const r = await API.get('/api/storage/files/' + encodeURIComponent(tier));
        const rows = (r.directories || []).flatMap(d => (d.files || []).map(f => ({ dir: d.path, name: f.name, size_mb: f.size_mb })));
        box.innerHTML = '<div style="height:8px"></div>' + UI.screenHTML({
          channel: 'BERKAS TIER ' + tier.toUpperCase(), rec: UI.int(rows.length) + ' BERKAS', recCls: 'off',
          body: UI.tableHTML([{ label: 'Nama', key: 'name' }, { label: 'MB', cls: 'r', get: x => UI.num(x.size_mb, 2) },
            { label: 'Folder', key: 'dir' }], rows.slice(0, 500), { empty: 'TIDAK ADA BERKAS' }) +
            (rows.length > 500 ? '<p class="v-dim" style="margin:6px 0 0;font-size:11px">Menampilkan 500 dari ' + UI.int(rows.length) + ' berkas.</p>' : '') });
      } catch (e) { box.innerHTML = ''; UI.showError('Daftar berkas', e); }
    }));
  }

  // ================================================================ 8–9. Log Masuk / Unduhan
  async function tabLog(kind) {
    const p = panel(), key = 'log_' + kind;
    if (!UI.$('#lgUser', p)) {
      const us = await users();
      const actions = kind === 'login' ? [['', 'Semua'], ['LOGIN_SUCCESS', 'Berhasil'], ['LOGIN_FAILED', 'Gagal'], ['LOGOUT', 'Keluar']]
        : [['', 'Semua'], ['DOWNLOAD_PRODUCT', 'Produk'], ['DOWNLOAD_DATASET', 'Dataset ZIP'], ['DOWNLOAD_FUSION', 'Fusion'], ['DOWNLOAD_REPORT', 'Laporan'], ['DOWNLOAD_XLSX', 'Excel'], ['EXPORT_CSV', 'CSV']];
      p.innerHTML = filterBar('<div class="field" style="margin:0"><label for="lgUser">Pengguna</label><select id="lgUser">' + userOpts(us) + '</select></div>' +
        '<div class="field" style="margin:0"><label for="lgAct">Aksi</label><select id="lgAct">' + actions.map(([v, l]) => '<option value="' + v + '">' + l + '</option>').join('') + '</select></div>' +
        '<div class="field" style="margin:0"><label for="lgFrom">Dari</label><input type="date" id="lgFrom"></div><div class="field" style="margin:0"><label for="lgTo">Sampai</label><input type="date" id="lgTo"></div>') + '<div id="lgList"></div>';
      bindFilter(() => { st.page[key] = 1; tabLog(kind); });
    }
    const a = UI.$('#lgFrom', p).value, b = UI.$('#lgTo', p).value;
    if (a && b && a > b) { UI.showError('Filter', { code: 'INVALID_DATE_RANGE' }); return; }
    const r = await API.get('/api/admin/logs/' + kind + API.qs({ user_id: UI.$('#lgUser', p).value, action: UI.$('#lgAct', p).value, date_from: a, date_to: b, page: pg(key), limit: 50 }));
    const cols = kind === 'login'
      ? [{ label: 'Waktu', get: x => UI.dateTime(x.logged_at) }, { label: 'Pengguna', get: x => x.username || (x.username_attempted ? x.username_attempted + ' (percobaan)' : '') },
         { label: 'Hasil', html: true, get: x => x.action === 'LOGIN_FAILED' ? '<span class="v-amber">GAGAL</span>' : x.action === 'LOGOUT' ? 'KELUAR' : 'BERHASIL' },
         { label: 'IP', key: 'ip_address' }, { label: 'Peramban', get: x => (x.user_agent || '').slice(0, 60) }]
      : [{ label: 'Waktu', get: x => UI.dateTime(x.logged_at) }, { label: 'Pengguna', key: 'username' }, { label: 'Jenis', key: 'action' },
         { label: 'Objek', get: x => (x.target_type || '') + (x.target_id ? ' #' + x.target_id : '') + (x.detail && (x.detail.entity || x.detail.filename) ? ' · ' + (x.detail.entity || x.detail.filename) : '') },
         { label: 'Ukuran', cls: 'r', get: x => UI.bytes(x.bytes_sent) }, { label: 'Lewat', get: x => (x.detail && x.detail.auth) === 'token' ? 'token API' : 'sesi web' }];
    UI.$('#lgList', p).innerHTML = UI.screenHTML({ channel: kind === 'login' ? 'CH-01 · LOG MASUK (v_log_login)' : 'CH-01 · LOG UNDUHAN (v_log_unduhan)', rec: UI.int(r.total) + ' BARIS', recCls: 'off',
      body: UI.tableHTML(cols, r.items, { empty: 'TIDAK ADA LOG' }) + UI.pagerHTML(r.total, 50, (pg(key) - 1) * 50) });
    bindPager(key, () => tabLog(kind));
  }

  // ================================================================ 10. Audit
  async function tabAudit() {
    const p = panel();
    if (!UI.$('#adTable', p)) {
      const us = await users();
      p.innerHTML = filterBar('<div class="field" style="margin:0"><label for="adTable">Tabel</label><input type="text" id="adTable" placeholder="mis. alert_rules" maxlength="63"></div>' +
        '<div class="field" style="margin:0"><label for="adOp">Operasi</label><select id="adOp"><option value="">Semua</option><option value="I">INSERT</option><option value="U">UPDATE</option><option value="D">DELETE</option></select></div>' +
        '<div class="field" style="margin:0"><label for="adUser">Pengguna</label><select id="adUser">' + userOpts(us) + '</select></div>' +
        '<div class="field" style="margin:0"><label for="adFrom">Dari</label><input type="date" id="adFrom"></div><div class="field" style="margin:0"><label for="adTo">Sampai</label><input type="date" id="adTo"></div>') + '<div id="adList"></div>';
      bindFilter(() => { st.page.audit = 1; tabAudit(); });
    }
    const names = Object.fromEntries((await users()).map(u => [u.user_id, u.username]));
    const r = await API.get('/api/admin/audit' + API.qs({ table: UI.$('#adTable', p).value.trim(), operation: UI.$('#adOp', p).value, user_id: UI.$('#adUser', p).value,
      date_from: UI.$('#adFrom', p).value, date_to: UI.$('#adTo', p).value, page: pg('audit'), limit: 50 }));
    UI.$('#adList', p).innerHTML = UI.screenHTML({ channel: 'CH-01 · AUDIT_LOG', rec: UI.int(r.total) + ' BARIS', recCls: 'off', body: UI.tableHTML([
      { label: 'Waktu', get: x => UI.dateTime(x.changed_at) }, { label: 'Tabel', key: 'table_name' }, { label: 'Baris', key: 'row_pk' }, { label: 'Operasi', get: x => OPS[x.operation] || x.operation },
      { label: 'Pengguna', get: x => (x.app_user_id ? names[x.app_user_id] || '#' + x.app_user_id : '(langsung DB)') + (x.db_user ? ' · ' + x.db_user : '') },
      { label: 'Kolom berubah', get: x => (x.changed_columns || []).join(', ') }, { label: 'Aksi', html: true, get: x => btn('data-au="' + x.audit_id + '"', 'Rincian…') },
    ], r.items, { empty: 'TIDAK ADA CATATAN AUDIT' }) + UI.pagerHTML(r.total, 50, (pg('audit') - 1) * 50) });
    UI.$$('[data-au]', p).forEach(b => b.addEventListener('click', () => {
      const x = r.items.find(i => String(i.audit_id) === b.dataset.au);
      const keys = Array.from(new Set(Object.keys(x.old_data || {}).concat(Object.keys(x.new_data || {})))).filter(k => k !== 'bbox' && k !== 'geom');
      UI.dialog({ title: 'Audit #' + x.audit_id + ' · ' + x.table_name, wide: 'x', buttons: [{ label: 'Tutup', value: true, default: true, cancel: true }],
        body: UI.screenHTML({ channel: (OPS[x.operation] || x.operation) + ' · BARIS ' + x.row_pk, body: UI.tableHTML([{ label: 'Kolom', get: k => k },
          { label: 'Lama', html: true, get: k => '<span class="v-dim">' + UI.esc(JSON.stringify((x.old_data || {})[k] ?? null)) + '</span>' },
          { label: 'Baru', html: true, get: k => '<span class="' + ((x.changed_columns || []).includes(k) ? 'v-amber' : '') + '">' + UI.esc(JSON.stringify((x.new_data || {})[k] ?? null)) + '</span>' }], keys) +
          '<p class="v-dim" style="margin:6px 0 0;font-size:11px">Kolom rahasia (password_hash, token_hash) disensor; geometri tidak ditampilkan.</p>' }) });
    }));
    bindPager('audit', tabAudit);
  }

  // ================================================================ 11. Pengaturan
  async function tabSettings() {
    const s = await API.get('/api/admin/settings');
    panel().innerHTML = UI.screenHTML({ channel: 'CH-01 · APP_SETTINGS', body: UI.tableHTML([
      { label: 'Kunci', key: 'setting_key' }, { label: 'Nilai', get: x => JSON.stringify(x.setting_value) }, { label: 'Keterangan', key: 'description' },
      { label: 'Diubah', get: x => UI.dateTime(x.updated_at) }, { label: 'Aksi', html: true, get: x => btn('data-set="' + UI.esc(x.setting_key) + '"', 'Ubah…') },
    ], s.items) }) + '<div id="asExcel" style="margin-top:8px;max-width:420px"></div>';
    Excel.mount(UI.$('#asExcel', panel()), ['app_settings'], { onImported: tabSettings });
    UI.$$('[data-set]', panel()).forEach(b => b.addEventListener('click', async () => {
      const x = s.items.find(i => i.setting_key === b.dataset.set);
      const isNum = typeof x.setting_value === 'number', isBool = typeof x.setting_value === 'boolean';
      const f = [isBool ? { id: 'v', label: 'Aktif', type: 'checkbox', value: x.setting_value }
        : { id: 'v', label: 'Nilai' + (isNum ? ' (angka)' : ''), type: isNum ? 'number' : 'text', step: 'any', required: true, value: typeof x.setting_value === 'object' ? JSON.stringify(x.setting_value) : x.setting_value, hint: x.description }];
      if (await formDialog('Ubah ' + x.setting_key, f, v => {
        let val = v.v;
        if (!isNum && !isBool && typeof x.setting_value === 'object') { try { val = JSON.parse(val); } catch (e) { throw { code: 'INVALID_SETTING' }; } }
        return API.put('/api/admin/settings', { settings: { [x.setting_key]: val } });
      })) tabSettings();
    }));
  }

  // ================================================================ 12. Token API
  async function tabTokens() {
    const p = panel();
    if (!UI.$('#atUser', p)) {
      const us = await users();
      p.innerHTML = filterBar('<div class="field" style="margin:0"><label for="atUser">Pemilik</label><select id="atUser">' + userOpts(us) + '</select></div>' +
        '<div class="field" style="margin:0"><label for="atAct">Status</label><select id="atAct"><option value="">Semua</option><option value="true">Aktif</option><option value="false">Dicabut/kedaluwarsa</option></select></div>') + '<div id="atList"></div>';
      bindFilter(() => { st.page.tokens = 1; tabTokens(); });
    }
    const r = await API.get('/api/admin/tokens' + API.qs({ user_id: UI.$('#atUser', p).value, active: UI.$('#atAct', p).value, limit: 50, offset: (pg('tokens') - 1) * 50 }));
    UI.$('#atList', p).innerHTML = UI.screenHTML({ channel: 'CH-01 · SEMUA TOKEN API', rec: UI.int(r.total) + ' TOKEN', recCls: 'off', body: UI.tableHTML([
      { label: 'Pemilik', key: 'username' }, { label: 'Nama', key: 'name' }, { label: 'Prefix', get: t => t.prefix + '…' }, { label: 'Cakupan', key: 'scope' },
      { label: 'Kedaluwarsa', get: t => UI.date(t.expires_at) }, { label: 'Terakhir dipakai', get: t => t.last_used_at ? UI.dateTime(t.last_used_at) : 'belum pernah' },
      { label: 'Status', get: t => t.active ? 'AKTIF' : t.revoked_at ? 'DICABUT' : 'KEDALUWARSA' },
      { label: 'Aksi', html: true, get: t => t.active ? btn('data-rv="' + t.token_id + '"', 'Cabut…') : '' },
    ], r.items, { empty: 'BELUM ADA TOKEN API' }) + UI.pagerHTML(r.total, 50, (pg('tokens') - 1) * 50) });
    UI.$$('[data-rv]', p).forEach(b => b.addEventListener('click', async () => {
      const t = r.items.find(x => String(x.token_id) === b.dataset.rv);
      if (!await UI.confirm('Cabut token', 'Cabut token "' + t.name + '" milik ' + t.username + '? Skrip yang memakainya langsung ditolak.', 'Cabut')) return;
      try { await API.del('/api/auth/tokens/' + t.token_id); tabTokens(); } catch (e) { UI.showError('Cabut token', e); }
    }));
    bindPager('tokens', tabTokens);
  }

  // ================================================================ 0. Ringkasan
  // Pintu masuk Pengaturan (M53): satu layar yang menjawab "apa yang perlu saya
  // kerjakan hari ini". Tidak ada aksi tulis di sini — hanya temuan beserta
  // tautan ke bagian yang menanganinya. Tiap sumber gagal sendiri-sendiri.
  async function tabSummary() {
    const p = panel();
    const [pipe, alerts, userList] = await Promise.all([
      API.get('/api/admin/pipeline/status').catch(() => null),
      API.get('/api/alerts?status=active&limit=200').then(r => r.items || []).catch(() => null),
      users().catch(() => null),
    ]);

    const hy = (pipe && pipe.hydromet) || {};
    const areas = (pipe && pipe.live_areas) || [];
    const cred = (pipe && pipe.credentials) || {};
    const credMissing = Object.keys(cred).filter(k => !cred[k]);
    const areaBad = areas.filter(a => a.status && /FAIL|ERROR|STALE/i.test(a.status));
    const locked = (userList || []).filter(u => u.is_locked);
    const queued = ((pipe && pipe.queue) || {}).dataset_jobs_queued;

    // Temuan: hanya hal yang butuh tindakan, paling mendesak dulu.
    const findings = [];
    if (!pipe) findings.push(['v-alert', 'Status pipeline tidak dapat dibaca.', 'Periksa LINK di taskbar; API atau basis data mungkin tidak terjangkau.', null]);
    if (credMissing.length) findings.push(['v-alert', 'Kredensial belum diisi: ' + credMissing.join(', ') + '.',
      'Job yang membutuhkannya akan gagal. Isi di .env lalu jalankan ulang server.', null]);
    if (hy.failed) findings.push(['v-alert', UI.int(hy.failed) + ' job hidromet berstatus FAILED.',
      'Lihat sebabnya di log pipeline, lalu picu ulang rentang tanggalnya.', 'pipeline']);
    if (areaBad.length) findings.push(['v-amber', UI.int(areaBad.length) + ' Live Area bermasalah: ' + areaBad.map(a => a.name).join(', ') + '.',
      'Coba ulang sumber yang gagal dari Operasi → Live Area.', 'live']);
    if (hy.waiting) findings.push(['v-amber', UI.int(hy.waiting) + ' job menunggu data hulu (WAITING_UPSTREAM).',
      'Normal bila granule penyedia belum terbit; menetap berhari-hari berarti ada masalah.', 'pipeline']);
    if (alerts === null) findings.push(['v-amber', 'Daftar alert tidak dapat dibaca.', 'Coba muat ulang halaman.', null]);
    else if (alerts.length) findings.push(['v-amber', UI.int(alerts.length) + ' alert hujan belum ditandai dibaca.',
      'Penandaan dilakukan di Kondisi → Hujan per kecamatan, oleh Analis atau Administrator.', null]);
    if (locked.length) findings.push(['', UI.int(locked.length) + ' akun terkunci.',
      'Buka kuncinya di Pengguna & akses → Pengguna.', 'pengguna']);
    if (!areas.length) findings.push(['', 'Belum ada Live Area.',
      'Tanpa Live Area, halaman publik dan Kondisi tidak punya scene untuk ditampilkan.', 'live']);

    p.innerHTML =
      '<div class="readouts" style="margin-bottom:8px">' +
        UI.readoutHTML('PERLU PERHATIAN', UI.int(findings.length),
          findings.length ? 'LIHAT DAFTAR DI BAWAH' : 'TIDAK ADA', findings.length ? 'v-amber' : '') +
        UI.readoutHTML('HIDROMET TERAKHIR', UI.esc(hy.last_completed ? UI.date(hy.last_completed) : UI.NA),
          'OBSERVASI ' + UI.esc(hy.last_observation_date ? UI.date(hy.last_observation_date) : UI.NA), 'v-cyan') +
        UI.readoutHTML('ALERT AKTIF', alerts === null ? UI.NA : UI.int(alerts.length),
          alerts === null ? 'TIDAK DAPAT DIBACA' : 'BELUM DITANDAI DIBACA', alerts && alerts.length ? 'v-amber' : '') +
        UI.readoutHTML('ANTREAN DATASET', queued === undefined || queued === null ? UI.NA : UI.int(queued), 'JOB MENUNGGU') +
      '</div>' +
      UI.screenHTML({ channel: 'CH-00 · PERLU PERHATIAN', rec: findings.length ? '● CHECK' : '● NOMINAL', recCls: findings.length ? '' : 'live',
        body: findings.length
          ? '<ul class="findings">' + findings.map(f =>
              '<li><b class="' + f[0] + '">' + UI.esc(f[1]) + '</b><br><span class="v-dim">' + UI.esc(f[2]) + '</span>' +
              (f[3] ? ' <button type="button" class="link-btn" data-goto="' + f[3] + '">Buka →</button>' : '') + '</li>').join('') + '</ul>'
          : UI.emptyHTML('TIDAK ADA TEMUAN. SISTEM BERJALAN NORMAL.') }) +
      '<div style="height:8px"></div>' +
      '<div class="cols-2">' +
        UI.screenHTML({ channel: 'CH-01 · JOB TERAKHIR PER JENIS', body: UI.tableHTML([
          { label: 'Jenis', key: 'kind' },
          { label: 'Status', html: true, get: j => '<span class="' + (/FAIL/i.test(j.status || '') ? 'v-alert' : /QUEUED|RUNNING|WAITING/i.test(j.status || '') ? 'v-amber' : '') + '">' + UI.esc(j.status || UI.NA) + '</span>' },
          { label: 'Tanggal data', get: j => UI.date(j.date_range_start) },
          { label: 'Selesai', get: j => j.completed_at ? UI.dateTime(j.completed_at) : '' },
        ], (pipe && pipe.latest_jobs) || [], { empty: 'BELUM ADA JOB' }) }) +
        UI.screenHTML({ channel: 'CH-02 · LIVE AREA', body: UI.tableHTML([
          { label: 'Area', key: 'name' },
          { label: 'Status', html: true, get: a => '<span class="' + (/FAIL|ERROR/i.test(a.status || '') ? 'v-alert' : '') + '">' + UI.esc(a.status || UI.NA) + '</span>' },
          { label: 'Diperiksa', get: a => UI.dateTime(a.last_checked_at) },
        ], areas, { empty: 'BELUM ADA LIVE AREA' }) }) +
      '</div>';

    // "Buka →" sekarang berpindah lewat hash, jadi bagian yang dituju bisa
    // dibagikan dan tombol Kembali peramban mengembalikan admin ke Ringkasan.
    UI.$$('[data-goto]', p).forEach(b => b.addEventListener('click', () => st.ctx.go(hashOf(b.dataset.goto))));
  }

  return { init, destroy, onSub };
})();
