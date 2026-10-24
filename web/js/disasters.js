// js/disasters.js — Kejadian (#kejadian, INTERFACE.md §2 halaman 5, §4.6, M68).
//
// Satu halaman untuk semua peran (dulu tab Lihat kejadian = disasters-view.js
// dan Kelola kejadian). GET /api/disasters: pengunjung 365 hari lewat
// v_public_kejadian, peran yang masuk seluruh riwayat. Dengan izin
// disasters.manage (Analis, Admin) halaman yang sama menampilkan tombol
// "Catat kejadian baru", Ubah/Hapus di detail, dan Excel. CRUD tercatat di
// audit_log (trigger DB); hapus = soft delete.
//
// Daftar diambil sekali per saringan (maks. 1000, batas API) lalu dipaginasi
// di browser, supaya lencana ringkasan (jumlah, terverifikasi, per jenis)
// menghitung seluruh hasil saringan, bukan satu halaman. Peta dan daftar
// berdampingan dan saling menyorot.
//
// M73: alert hujan aktif (dulu di Citra › GPM) tampil sebagai satu lencana di
// baris ringkasan; klik membuka daftar per kecamatan dengan "Tandai dibaca"
// per baris (izin alerts.acknowledge). Tautan dari GPM membuka daftar ini
// langsung (sessionStorage 'orbitu.openAlerts').
'use strict';
Pages['disasters'] = (() => {
  const SOURCES = { GMLS: 'GMLS', BPBD_LEBAK: 'BPBD Lebak', BNPB_DIBI: 'BNPB (DIBI)', MEDIA: 'Media', LAINNYA: 'Lainnya' };
  const LIMIT = 50, FETCH = 1000;
  const DOT = { on: '#ffb000', off: '#4de1ff' };
  const SEV_RANK = { CRITICAL: 3, WARNING: 2, INFO: 1 };
  const OPEN_ALERTS = 'orbitu.openAlerts';
  let st = null;
  // API mengembalikan `location: {lat, lon}` (etl.disasters.event_dict);
  // perender di bawah membaca e.lat/e.lon.
  const flat = e => Object.assign(e, { lat: e.location ? e.location.lat : null, lon: e.location ? e.location.lon : null });
  const hasPt = e => e.lat !== null && e.lat !== undefined;

  async function init(root, ctx) {
    st = { root, ctx, types: [], regions: [], page: 1, map: null, layer: null, items: [], markers: {}, alerts: [],
           manage: Auth.can('disasters.manage') };
    const $ = s => UI.$(s, root);
    try {
      const [types, geo] = await Promise.all([API.get('/api/disaster-types'), Maps.regions()]);
      st.types = types.items; st.regions = geo.features.map(f => f.properties).sort((a, b) => a.name.localeCompare(b.name, 'id'));
      st.geo = geo;
    } catch (e) { UI.showError('Kejadian', e); }
    $('#dzType').insertAdjacentHTML('beforeend', st.types.map(t => '<option value="' + UI.esc(t.type_code) + '">' + UI.esc(t.type_name) + '</option>').join(''));
    $('#dzRegion').insertAdjacentHTML('beforeend', st.regions.map(r => '<option value="' + r.region_id + '">' + UI.esc(r.name) + '</option>').join(''));
    $('#dzFilter').addEventListener('submit', ev => { ev.preventDefault(); UI.busy($('#dzApply'), load); });
    $('#dzReset').addEventListener('click', () => { $('#dzFilter').reset(); load(); });
    $('#dzNew').hidden = !st.manage;
    $('#dzExcelBox').hidden = !st.manage;
    if (st.manage) {
      $('#dzNew').addEventListener('click', () => openForm(null));
      Excel.mount($('#dzExcel'), ['disasters', 'disaster_rain', 'disaster_types'], { onImported: load });
    }
    st.map = Maps.create($('#dzMap'));
    if (st.map && st.geo) {
      st.aoi = L.geoJSON(st.geo, { style: { color: '#1a9960', weight: 1, fillOpacity: 0.05 }, interactive: false }).addTo(st.map);
      setTimeout(() => { if (st && st.map) { st.map.invalidateSize(); st.map.fitBounds(st.aoi.getBounds()); } }, 100);
    }
    await load();
    await loadAlerts();
  }

  function destroy() { if (st && st.map) st.map.remove(); st = null; }

  async function load() {
    const $ = s => UI.$(s, st.root);
    const from = $('#dzFrom').value, to = $('#dzTo').value;
    if (from && to && from > to) { UI.showError('Saring kejadian', { code: 'INVALID_DATE_RANGE' }); return; }
    st.ctx.setStatus('Memuat…');
    let r;
    try {
      r = await API.get('/api/disasters' + API.qs({ date_from: from, date_to: to, type_code: $('#dzType').value,
        region_id: $('#dzRegion').value, is_verified: $('#dzVer').value, limit: FETCH, offset: 0 }));
    } catch (e) { $('#dzTable').innerHTML = UI.emptyHTML('GAGAL MEMUAT'); UI.showError('Kejadian', e); return; }
    if (!st) return;
    st.items = r.items.map(flat);
    st.total = r.total;
    st.page = 1;
    const win = $('#dzWindow');
    win.hidden = !r.window_days;
    if (r.window_days) {
      win.innerHTML = 'Pengunjung melihat kejadian <b>' + UI.int(r.window_days) + ' hari terakhir</b>. ' +
        '<a href="/masuk?next=' + encodeURIComponent('/app#kejadian') + '">Masuk</a> atau <a href="/daftar">daftar akun Relawan</a> untuk seluruh riwayat.';
    }
    renderChips();
    renderTable();
    renderMap();
    st.ctx.setStatus('Siap · ' + UI.int(r.total) + ' kejadian');
  }

  // Lencana: jumlah, status verifikasi, dan jenis — masing-masing tombol yang
  // mengisi saringan yang sama di atas (klik lagi untuk melepas).
  function renderChips() {
    const $ = s => UI.$(s, st.root);
    const ver = st.items.filter(e => e.is_verified).length;
    const byType = {};
    st.items.forEach(e => { const k = e.disaster_type_code; byType[k] = byType[k] || { name: e.disaster_type_name, n: 0 }; byType[k].n++; });
    const curT = $('#dzType').value, curV = $('#dzVer').value;
    const chip = (attr, label, on) => '<button type="button" class="chip dz-chip" ' + attr + ' aria-pressed="' + on + '">' + label + '</button>';
    $('#dzChips').innerHTML = '<span class="dz-total"><b>' + UI.int(st.total) + '</b> kejadian' +
        (st.total > st.items.length ? ' <span class="v-dim">(ringkasan dari ' + UI.int(st.items.length) + ' terbaru)</span>' : '') + '</span>' +
      chip('data-ver="true"', '<span class="dz-dot" style="background:' + DOT.on + '"></span>' + UI.int(ver) + ' terverifikasi', curV === 'true') +
      chip('data-ver="false"', '<span class="dz-dot" style="background:' + DOT.off + '"></span>' + UI.int(st.items.length - ver) + ' belum', curV === 'false') +
      Object.entries(byType).sort((a, b) => b[1].n - a[1].n).map(([k, t]) =>
        chip('data-type="' + UI.esc(k) + '"', UI.esc(t.name) + ' ' + UI.int(t.n), curT === k)).join('') +
      (st.alerts.length ? '<button type="button" class="chip dz-chip dz-alert" data-alerts aria-haspopup="dialog">▲ Alert hujan aktif · ' +
        UI.int(alertGroups().length) + ' kecamatan</button>' : '');
    const ab = UI.$('[data-alerts]', $('#dzChips'));
    if (ab) ab.addEventListener('click', openAlerts);
    UI.$$('[data-ver]', $('#dzChips')).forEach(b => b.addEventListener('click', () => {
      $('#dzVer').value = curV === b.dataset.ver ? '' : b.dataset.ver; load();
    }));
    UI.$$('[data-type]', $('#dzChips')).forEach(b => b.addEventListener('click', () => {
      $('#dzType').value = curT === b.dataset.type ? '' : b.dataset.type; load();
    }));
  }

  // ---------------------------------------------------- alert hujan aktif
  async function loadAlerts() {
    if (!Auth.can('alerts.view')) return;
    try {
      const r = await API.get('/api/alerts' + API.qs({ status: 'active', limit: 500 }));
      if (!st) return;
      st.alerts = r.items || [];
    } catch (e) { return; }
    renderChips();
    let want = false;
    try { want = sessionStorage.getItem(OPEN_ALERTS) === '1'; sessionStorage.removeItem(OPEN_ALERTS); } catch (e) { /* abaikan */ }
    if (want && st.alerts.length) openAlerts();
  }

  // Satu baris per kecamatan: alert dengan tingkat tertinggi (lalu terbaru) di depan.
  function alertGroups() {
    const by = {};
    st.alerts.forEach(a => { (by[a.region_id] = by[a.region_id] || []).push(a); });
    return Object.values(by).map(l => l.sort((x, y) => SEV_RANK[y.severity] - SEV_RANK[x.severity] || (y.observation_date > x.observation_date ? 1 : -1)))
      .sort((x, y) => SEV_RANK[y[0].severity] - SEV_RANK[x[0].severity] || x[0].region_name.localeCompare(y[0].region_name, 'id'));
  }

  function openAlerts() {
    return UI.dialog({ title: 'Alert hujan aktif', wide: 'x', body: '<div id="dzAlertBody"></div>',
      buttons: [{ label: 'Tutup', value: null, default: true }], onOpen: win => fillAlerts(win) });
  }

  function fillAlerts(win) {
    const box = UI.$('#dzAlertBody', win);
    if (!box || !st) return;
    const groups = alertGroups(), canAck = Auth.can('alerts.acknowledge');
    if (!groups.length) { box.innerHTML = UI.emptyHTML('SEMUA ALERT SUDAH DITANDAI DIBACA'); return; }
    box.innerHTML = '<p class="mut" style="margin:0 0 6px;font-size:11px">Satu baris per kecamatan (tingkat tertinggi). ' +
      (canAck ? 'Menandai dibaca berarti alert sudah ditinjau; alert tidak dihapus.' : 'Penandaan "sudah dibaca" dilakukan Analis atau Administrator.') + '</p>' +
      '<div class="screen"><div class="screen-inner"><span class="scr-ch">ALERT AKTIF</span><span class="scr-rec off">' + UI.int(st.alerts.length) + ' ALERT</span>' +
      UI.tableHTML([
        { label: 'Kecamatan', get: g => g[0].region_name },
        { label: 'Tingkat', html: true, get: g => '<span class="' + UI.SEVERITY[g[0].severity].cls + '">' + UI.esc(UI.SEVERITY[g[0].severity].label.toUpperCase()) + '</span>' },
        { label: 'Tanggal', get: g => UI.date(g[0].observation_date) },
        { label: 'Nilai', cls: 'r', get: g => UI.num(g[0].observed_value, 1) + ' mm ≥ ' + UI.num(g[0].threshold_value, 0) },
        { label: 'Aturan', get: g => g[0].rule_code + (g.length > 1 ? ' (+' + (g.length - 1) + ')' : '') },
      ].concat(canAck ? [{ label: 'Aksi', cls: 'r', html: true, get: g =>
        '<button type="button" class="small" data-ack="' + g[0].region_id + '" aria-label="Tandai sudah dibaca: ' + UI.esc(g[0].region_name) + '">Tandai dibaca…</button>' }] : []),
      groups, { caption: 'Alert aktif per kecamatan' }) + '</div></div>' +
      (canAck && groups.length > 1 ? '<div class="btn-row end" style="margin-top:6px"><button type="button" class="small" data-ack-all>Tandai semua dibaca (' +
        UI.int(groups.length) + ' kecamatan)…</button></div>' : '');
    UI.$$('[data-ack]', box).forEach(b => b.addEventListener('click', () =>
      acknowledge(b, groups.find(g => String(g[0].region_id) === b.dataset.ack), null, win)));
    const all = UI.$('[data-ack-all]', box);
    if (all) all.addEventListener('click', () => acknowledge(all, st.alerts.slice(), 'semua ' + groups.length + ' kecamatan', win));
  }

  async function acknowledge(btn, list, label, win) {
    const name = label || list[0].region_name;
    const note = await UI.dialog({ title: 'Tandai sudah dibaca', kind: 'question',
      message: list.length + ' alert aktif untuk ' + name + ' akan ditandai sudah dibaca atas nama Anda.',
      body: '<div class="field"><label for="ackNote">Catatan (opsional, maks. 500 karakter)</label><textarea id="ackNote" maxlength="500"></textarea></div>',
      buttons: [{ label: 'Tandai', value: 'ok', default: true }, { label: 'Batal', value: null, cancel: true }],
      collect: w => UI.$('#ackNote', w).value });
    if (note === null || note === 'cancel' || !st) return;
    await UI.busy(btn, async () => {
      let done = 0;
      for (const a of list) {
        try { await API.post('/api/alerts/' + a.alert_id + '/acknowledge', { note: note || null }); done++; }
        catch (e) {
          if (e.code === 'ALERT_ALREADY_ACKED') { done++; continue; }
          await UI.showError('Tandai sudah dibaca', e); break;
        }
      }
      if (done) st.ctx.setStatus(done + ' alert untuk ' + name + ' ditandai sudah dibaca');
      const ids = new Set(list.map(a => a.alert_id));
      try { const r = await API.get('/api/alerts' + API.qs({ status: 'active', limit: 500 })); if (st) st.alerts = r.items || []; }
      catch (e) { if (st) st.alerts = st.alerts.filter(a => !ids.has(a.alert_id)); }
    });
    if (!st) return;
    renderChips();
    fillAlerts(win);
  }

  function renderTable() {
    const $ = s => UI.$(s, st.root);
    const rows = st.items.slice((st.page - 1) * LIMIT, st.page * LIMIT);
    $('#dzCount').textContent = UI.int(st.total) + ' KEJADIAN';
    $('#dzTable').innerHTML = UI.tableHTML([
      { label: 'Tanggal', get: e => UI.date(e.event_date) + (e.event_end_date && e.event_end_date !== e.event_date ? ' – ' + UI.date(e.event_end_date) : '') },
      { label: 'Jenis', key: 'disaster_type_name' },
      { label: 'Kecamatan', html: true, get: e => UI.esc(e.region_name) + (hasPt(e) ? '' : ' <span class="v-dim" style="font-size:11px">· tanpa titik</span>') },
      { label: 'Status', html: true, get: e => e.is_verified ? 'TERVERIFIKASI' : '<span class="v-amber">BELUM</span>' },
    ], rows, { empty: st.manage ? 'BELUM ADA KEJADIAN PADA SARINGAN INI. GUNAKAN "CATAT KEJADIAN BARU" ATAU IMPOR EXCEL.' : 'TIDAK ADA KEJADIAN PADA SARINGAN INI',
      caption: 'Daftar kejadian bencana',
      rowAttr: e => 'class="dz-row" tabindex="0" data-id="' + e.event_id + '" aria-label="Kejadian ' + UI.esc(e.disaster_type_name + ', ' + e.region_name + ', ' + UI.date(e.event_date)) + ': buka detail"' }) +
      UI.pagerHTML(st.items.length, LIMIT, (st.page - 1) * LIMIT);
    UI.$$('#dzTable .dz-row', st.root).forEach(tr => {
      const id = Number(tr.dataset.id);
      tr.addEventListener('click', () => openDetail(id));
      tr.addEventListener('keydown', ev => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); openDetail(id); } });
      tr.addEventListener('mouseenter', () => spot(id, true));
      tr.addEventListener('mouseleave', () => spot(id, false));
      tr.addEventListener('focus', () => spot(id, true));
      tr.addEventListener('blur', () => spot(id, false));
    });
    UI.$$('#dzTable [data-page]', st.root).forEach(b => b.addEventListener('click', () => { st.page = Number(b.dataset.page); renderTable(); }));
  }

  // Sorot satu kejadian di peta dan di daftar sekaligus.
  function spot(id, on) {
    const m = st.markers[id];
    if (m) { m.setStyle({ radius: on ? 10 : 6, weight: on ? 3 : 1, color: on ? '#fff' : '#000' }); if (on) { m.bringToFront(); m.openTooltip(); } else m.closeTooltip(); }
    const tr = UI.$('#dzTable .dz-row[data-id="' + id + '"]', st.root);
    if (tr) tr.classList.toggle('dz-on', on);
  }

  function renderMap() {
    if (!st.map) return;
    if (st.layer) st.layer.remove();
    st.markers = {};
    const pts = st.items.filter(hasPt);
    UI.$('#dzMapRec', st.root).textContent = UI.int(pts.length) + ' TITIK';
    st.layer = L.layerGroup(pts.map(e => {
      const m = L.circleMarker([e.lat, e.lon], { radius: 6, color: '#000', weight: 1, fillColor: e.is_verified ? DOT.on : DOT.off, fillOpacity: 0.95 })
        .bindTooltip(UI.esc(e.disaster_type_name + ' · ' + e.region_name + ' · ' + UI.date(e.event_date) + (e.is_verified ? '' : ' (belum diverifikasi)')))
        .on('click', () => openDetail(e.event_id))
        .on('mouseover', () => { const tr = UI.$('#dzTable .dz-row[data-id="' + e.event_id + '"]', st.root); if (tr) tr.classList.add('dz-on'); })
        .on('mouseout', () => { const tr = UI.$('#dzTable .dz-row[data-id="' + e.event_id + '"]', st.root); if (tr) tr.classList.remove('dz-on'); });
      st.markers[e.event_id] = m;
      return m;
    })).addTo(st.map);
    if (pts.length) st.map.fitBounds(L.latLngBounds(pts.map(e => [e.lat, e.lon])).pad(0.3), { maxZoom: 12 });
  }

  async function openDetail(id) {
    let e;
    try { e = flat(await API.get('/api/disasters/' + id)); } catch (err) { UI.showError('Detail kejadian', err); return; }
    const kv = [['JENIS', e.disaster_type_name], ['TANGGAL', UI.date(e.event_date) + (e.event_end_date ? ' – ' + UI.date(e.event_end_date) : '')],
      ['KECAMATAN', e.region_name], ['DESA', e.village_name], ['TITIK', hasPt(e) ? UI.num(e.lat, 5) + ', ' + UI.num(e.lon, 5) : null],
      ['SUMBER', (SOURCES[e.info_source] || e.info_source) + (e.source_reference ? ' · ' + e.source_reference : '')],
      ['VERIFIKASI', e.is_verified ? 'Terverifikasi' : 'Belum']].concat(e.recorded_at ? [['DICATAT', UI.dateTime(e.recorded_at)]] : []);
    // Angka hujan H-0..H-2 hanya terisi untuk Analis/Admin (v_kejadian_dan_hujan); selain itu `rain` null.
    const rain = e.rain ? UI.screenHTML({ channel: 'HUJAN KECAMATAN H-0..H-2', body: UI.tableHTML([
      { label: 'Hari', key: 'day' }, { label: 'Hujan 24 jam', cls: 'r', get: r => UI.num(r.rain_24h_mm, 1) + ' mm' },
      { label: '72 jam', cls: 'r', get: r => UI.num(r.rain_72h_mm, 1) + ' mm' }, { label: '7 hari', cls: 'r', get: r => UI.num(r.rain_7d_mm, 1) + ' mm' },
    ], e.rain) + '<p class="v-dim" style="margin:4px 0 0;font-size:11px">"—" = belum ada data hidromet untuk tanggal itu (menunggu backfill).</p>' }) : '';
    const v = await UI.dialog({ title: 'Kejadian #' + e.event_id, wide: true,
      body: UI.screenHTML({ channel: 'KEJADIAN #' + e.event_id, body: '<dl class="kv">' + kv.map(([k, x]) => '<dt>' + k + '</dt><dd>' + UI.esc(x || UI.NA) + '</dd>').join('') + '</dl>' +
          '<p class="scr-text" style="margin:8px 0 0"><span class="lbl">DESKRIPSI:</span> ' + UI.esc(e.description) + '</p>' +
          (e.impact_summary ? '<p class="scr-text" style="margin:4px 0 0"><span class="lbl">DAMPAK:</span> ' + UI.esc(e.impact_summary) + '</p>' : '') }) +
        (rain ? '<div style="height:8px"></div>' + rain : ''),
      buttons: (st.manage ? [{ label: 'Ubah…', value: 'edit' }, { label: 'Hapus…', value: 'del' }] : [])
        .concat([{ label: 'Tutup', value: null, default: true, cancel: true }]) });
    if (v === 'edit') openForm(e);
    if (v === 'del') remove(e);
  }

  async function remove(e) {
    if (!await UI.confirm('Hapus kejadian', 'Hapus kejadian #' + e.event_id + ' (' + e.disaster_type_name + ', ' + e.region_name + ', ' + UI.date(e.event_date) + ')?\n\n' +
      'Data tidak dihapus permanen (soft delete) dan perubahan tercatat di log audit.', 'Hapus')) return;
    try { await API.del('/api/disasters/' + e.event_id); UI.info('Hapus kejadian', 'Kejadian #' + e.event_id + ' dihapus.'); load(); }
    catch (err) { UI.showError('Hapus kejadian', err); }
  }

  function formHTML(e) {
    const v = (k, d) => UI.esc(e && e[k] !== null && e[k] !== undefined ? e[k] : (d || ''));
    const types = st.types.filter(t => t.is_active || (e && t.type_code === e.disaster_type_code));
    return '<form id="dzForm" novalidate>' +
      '<div class="cols-2">' +
      '<fieldset><legend>Kejadian</legend>' +
        '<div class="field"><label for="fType">Jenis bencana *</label><select id="fType" required>' + '<option value="">— pilih —</option>' +
          types.map(t => '<option value="' + UI.esc(t.type_code) + '"' + (e && e.disaster_type_code === t.type_code ? ' selected' : '') + '>' + UI.esc(t.type_name) + '</option>').join('') + '</select><span class="err" id="fTypeErr"></span></div>' +
        '<div class="field-row"><div class="field"><label for="fDate">Tanggal mulai *</label><input type="date" id="fDate" required value="' + v('event_date') + '" max="' + UI.isoDate(new Date()) + '"><span class="err" id="fDateErr"></span></div>' +
        '<div class="field"><label for="fEnd">Tanggal selesai</label><input type="date" id="fEnd" value="' + v('event_end_date') + '"><span class="err" id="fEndErr"></span></div></div>' +
        '<div class="field"><label for="fDesc">Deskripsi * (10–4000 karakter)</label><textarea id="fDesc" required minlength="10" maxlength="4000" aria-describedby="fDescCnt fDescErr">' + v('description') + '</textarea>' +
          '<span class="hint" id="fDescCnt"></span><span class="err" id="fDescErr"></span></div>' +
        '<div class="field"><label for="fImpact">Ringkasan dampak (tanpa data pribadi, maks. 500)</label><textarea id="fImpact" maxlength="500" style="min-height:40px">' + v('impact_summary') + '</textarea></div>' +
      '</fieldset>' +
      '<fieldset><legend>Lokasi &amp; sumber</legend>' +
        '<div class="field"><label for="fRegion">Kecamatan *</label><select id="fRegion" required><option value="">— pilih —</option>' +
          st.regions.map(r => '<option value="' + r.region_id + '"' + (e && e.region_id === r.region_id ? ' selected' : '') + '>' + UI.esc(r.name) + '</option>').join('') + '</select><span class="err" id="fRegionErr"></span></div>' +
        '<div class="field"><label for="fVillage">Desa</label><input type="text" id="fVillage" maxlength="100" value="' + v('village_name') + '"></div>' +
        '<div class="field-row"><div class="field"><label for="fLat">Lintang (opsional)</label><input type="number" step="0.00001" id="fLat" value="' + v('lat') + '"></div>' +
        '<div class="field"><label for="fLon">Bujur</label><input type="number" step="0.00001" id="fLon" value="' + v('lon') + '"></div></div>' +
        '<span class="err" id="fLatErr"></span>' +
        '<div class="screen" style="margin-bottom:8px"><div class="screen-inner flush"><span class="scr-ch">KLIK PETA UNTUK TITIK</span><div class="map" id="fMap" style="height:180px"></div></div></div>' +
        '<div class="field"><label for="fSource">Sumber informasi *</label><select id="fSource">' +
          Object.entries(SOURCES).map(([k, l]) => '<option value="' + k + '"' + ((e ? e.info_source : 'GMLS') === k ? ' selected' : '') + '>' + l + '</option>').join('') + '</select></div>' +
        '<div class="field"><label for="fRef">Rujukan (tautan/nomor laporan)</label><input type="text" id="fRef" value="' + v('source_reference') + '"></div>' +
        '<label class="check"><input type="checkbox" id="fVer"' + (e && e.is_verified ? ' checked' : '') + '> Sudah diverifikasi</label>' +
      '</fieldset></div></form>';
  }

  function validate(win) {
    const $ = s => UI.$(s, win);
    const set = (id, msg) => { $('#' + id).setAttribute('aria-invalid', msg ? 'true' : 'false'); $('#' + id + 'Err').textContent = msg || ''; return !msg; };
    const d = $('#fDate').value, end = $('#fEnd').value, desc = $('#fDesc').value.trim();
    const lat = $('#fLat').value, lon = $('#fLon').value;
    let ok = set('fType', $('#fType').value ? '' : 'Pilih jenis bencana.');
    ok = set('fDate', d ? '' : 'Wajib diisi.') && ok;
    ok = set('fEnd', end && d && end < d ? 'Tidak boleh sebelum tanggal mulai.' : '') && ok;
    ok = set('fDesc', desc.length < 10 ? 'Minimal 10 karakter.' : desc.length > 4000 ? 'Maksimal 4000 karakter.' : '') && ok;
    ok = set('fRegion', $('#fRegion').value ? '' : 'Pilih kecamatan.') && ok;
    const latOk = (!lat && !lon) || (lat && lon && Math.abs(lat) <= 90 && Math.abs(lon) <= 180);
    $('#fLatErr').textContent = latOk ? '' : 'Isi lintang dan bujur sekaligus (atau kosongkan keduanya).';
    ok = latOk && ok;
    const first = win.querySelector('[aria-invalid=true]'); if (first) first.focus();
    return ok;
  }

  async function openForm(e, draft) {
    let map = null, marker = null;
    const body = await UI.dialog({ title: e ? 'Ubah kejadian #' + e.event_id : 'Catat kejadian baru', wide: 'x', body: formHTML(draft || e),
      buttons: [{ label: 'Simpan', value: 'save', default: true }, { label: 'Batal', value: null, cancel: true }],
      validate: (win, val) => val !== 'save' || validate(win),
      collect: win => {
        const $ = s => UI.$(s, win);
        const lat = $('#fLat').value, lon = $('#fLon').value;
        return { disaster_type_code: $('#fType').value, region_id: Number($('#fRegion').value), village_name: $('#fVillage').value.trim() || null,
          location: lat && lon ? { lat: Number(lat), lon: Number(lon) } : null, event_date: $('#fDate').value, event_end_date: $('#fEnd').value || null,
          description: $('#fDesc').value.trim(), impact_summary: $('#fImpact').value.trim() || null, info_source: $('#fSource').value,
          source_reference: $('#fRef').value.trim() || null, is_verified: $('#fVer').checked };
      },
      onOpen: win => {
        const $ = s => UI.$(s, win);
        const cnt = () => { $('#fDescCnt').textContent = $('#fDesc').value.trim().length + ' / 4000 karakter'; };
        $('#fDesc').addEventListener('input', cnt); cnt();
        map = Maps.create($('#fMap'), { attributionControl: false });
        if (!map) return;
        if (st.geo) L.geoJSON(st.geo, { style: { color: '#1a9960', weight: 1, fillOpacity: 0.05 }, interactive: false }).addTo(map);
        const put = (lat, lon) => { if (marker) marker.remove(); marker = L.circleMarker([lat, lon], { radius: 6, color: '#000', fillColor: '#ffb000', fillOpacity: 1 }).addTo(map); };
        const pre = draft || e;
        if (pre && pre.lat !== null && pre.lat !== undefined) put(pre.lat, pre.lon);
        map.on('click', ev => { $('#fLat').value = ev.latlng.lat.toFixed(5); $('#fLon').value = ev.latlng.lng.toFixed(5); put(ev.latlng.lat, ev.latlng.lng); });
      } });
    if (map) map.remove();
    if (!body || body === 'cancel') return;
    try {
      const r = e ? await API.put('/api/disasters/' + e.event_id, body) : await API.post('/api/disasters', body);
      await UI.info('Kejadian', (e ? 'Perubahan kejadian #' : 'Kejadian #') + r.event_id + ' tersimpan.');
      load();
    } catch (err) { await UI.showError('Simpan kejadian', err); openForm(e, Object.assign({}, body, { lat: body.location ? body.location.lat : null, lon: body.location ? body.location.lon : null })); }
  }

  return { init, destroy };
})();
