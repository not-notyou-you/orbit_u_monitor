// js/disasters-view.js — Kejadian › Lihat (#kejadian/lihat, INTERFACE.md §2 halaman 5.1, M56).
// GET /api/disasters (pengunjung: 365 hari lewat v_public_kejadian; peran
// login: semua). Detail: GET /api/disasters/{id}; angka hujan H-0..H-2 hanya
// terisi untuk Analis/Admin (v_kejadian_dan_hujan), selain itu `rain` null.
'use strict';
Pages['disasters-view'] = (() => {
  const SOURCES = { GMLS: 'GMLS', BPBD_LEBAK: 'BPBD Lebak', BNPB_DIBI: 'BNPB (DIBI)', MEDIA: 'Media', LAINNYA: 'Lainnya' };
  const LIMIT = 50;
  let st = null;

  async function init(root, ctx) {
    st = { root, ctx, page: 1, map: null, layer: null, items: [] };
    const $ = s => UI.$(s, root);
    $('#dvManage').hidden = !Auth.can('disasters.manage');
    try {
      const [types, geo] = await Promise.all([API.get('/api/disaster-types'), Maps.regions()]);
      $('#dvType').insertAdjacentHTML('beforeend', types.items.map(t => '<option value="' + UI.esc(t.type_code) + '">' + UI.esc(t.type_name) + '</option>').join(''));
      $('#dvRegion').insertAdjacentHTML('beforeend', geo.features.map(f => f.properties).sort((a, b) => a.name.localeCompare(b.name, 'id'))
        .map(r => '<option value="' + r.region_id + '">' + UI.esc(r.name) + '</option>').join(''));
      st.geo = geo;
    } catch (e) { UI.showError('Kejadian', e); }
    $('#dvFilter').addEventListener('submit', ev => { ev.preventDefault(); st.page = 1; UI.busy($('#dvApply'), load); });
    st.map = Maps.create($('#dvMap'));
    if (st.map && st.geo) {
      const aoi = L.geoJSON(st.geo, { style: { color: '#1a9960', weight: 1, fillOpacity: 0.05 }, interactive: false }).addTo(st.map);
      setTimeout(() => { if (st && st.map) { st.map.invalidateSize(); st.map.fitBounds(aoi.getBounds()); } }, 100);
    }
    await load();
  }

  function destroy() { if (st && st.map) st.map.remove(); st = null; }

  async function load() {
    const $ = s => UI.$(s, st.root);
    const from = $('#dvFrom').value, to = $('#dvTo').value;
    if (from && to && from > to) { UI.showError('Saring kejadian', { code: 'INVALID_DATE_RANGE' }); return; }
    st.ctx.setStatus('Memuat…');
    let r;
    try {
      r = await API.get('/api/disasters' + API.qs({ date_from: from, date_to: to, type_code: $('#dvType').value,
        region_id: $('#dvRegion').value, limit: LIMIT, offset: (st.page - 1) * LIMIT }));
    } catch (e) { $('#dvTable').innerHTML = UI.emptyHTML('GAGAL MEMUAT'); UI.showError('Kejadian', e); return; }
    if (!st) return;
    st.items = r.items;
    const win = $('#dvWindow');
    win.hidden = !r.window_days;
    if (r.window_days) {
      win.innerHTML = UI.icon('info32') + '<div class="b-body">Pengunjung melihat kejadian <b>' + UI.int(r.window_days) +
        ' hari terakhir</b>. <a href="/masuk?next=' + encodeURIComponent('/app#kejadian') + '">Masuk</a> atau ' +
        '<a href="/daftar">daftar akun Relawan</a> untuk seluruh riwayat.</div>';
    }
    $('#dvCount').textContent = UI.int(r.total) + ' KEJADIAN';
    $('#dvTable').innerHTML = UI.tableHTML([
      { label: 'Tanggal', get: e => UI.date(e.event_date) + (e.event_end_date && e.event_end_date !== e.event_date ? ' – ' + UI.date(e.event_end_date) : '') },
      { label: 'Jenis', key: 'disaster_type_name' }, { label: 'Kecamatan', key: 'region_name' }, { label: 'Desa', key: 'village_name' },
      { label: 'Sumber', get: e => SOURCES[e.info_source] || e.info_source },
      { label: 'Verifikasi', html: true, get: e => e.is_verified ? 'TERVERIFIKASI' : '<span class="v-amber">BELUM</span>' },
      { label: 'Detail', html: true, get: e => '<button type="button" class="small" data-open="' + e.event_id + '" aria-label="Detail kejadian ' + e.event_id + '">Lihat…</button>' },
    ], r.items, { empty: 'TIDAK ADA KEJADIAN PADA SARINGAN INI', caption: 'Daftar kejadian bencana' }) +
      UI.pagerHTML(r.total, LIMIT, (st.page - 1) * LIMIT);
    UI.$$('[data-open]', st.root).forEach(b => b.addEventListener('click', () => openDetail(Number(b.dataset.open))));
    UI.$$('#dvTable [data-page]', st.root).forEach(b => b.addEventListener('click', () => { st.page = Number(b.dataset.page); load(); }));
    renderMap();
    st.ctx.setStatus('Siap · ' + UI.int(r.total) + ' kejadian');
  }

  function renderMap() {
    if (!st.map) return;
    if (st.layer) st.layer.remove();
    const pts = st.items.filter(e => e.location);
    UI.$('#dvMapRec', st.root).textContent = UI.int(pts.length) + ' TITIK';
    st.layer = L.layerGroup(pts.map(e => L.circleMarker([e.location.lat, e.location.lon], {
      radius: 6, color: '#000', weight: 1, fillColor: e.is_verified ? '#ffb000' : '#4de1ff', fillOpacity: 0.95,
    }).bindTooltip(UI.esc(e.disaster_type_name + ' · ' + e.region_name + ' · ' + UI.date(e.event_date)))
      .on('click', () => openDetail(e.event_id)))).addTo(st.map);
    if (pts.length) st.map.fitBounds(L.latLngBounds(pts.map(e => [e.location.lat, e.location.lon])).pad(0.3), { maxZoom: 12 });
  }

  async function openDetail(id) {
    let e;
    try { e = await API.get('/api/disasters/' + id); } catch (err) { UI.showError('Detail kejadian', err); return; }
    const kv = [['JENIS', e.disaster_type_name], ['TANGGAL', UI.date(e.event_date) + (e.event_end_date ? ' – ' + UI.date(e.event_end_date) : '')],
      ['KECAMATAN', e.region_name], ['DESA', e.village_name],
      ['TITIK', e.location ? UI.num(e.location.lat, 5) + ', ' + UI.num(e.location.lon, 5) : null],
      ['SUMBER', SOURCES[e.info_source] || e.info_source], ['VERIFIKASI', e.is_verified ? 'Terverifikasi' : 'Belum']];
    const rain = e.rain ? UI.tableHTML([{ label: 'Hari', key: 'day' },
      { label: '24 jam', cls: 'r', get: x => UI.num(x.rain_24h_mm, 1) }, { label: '72 jam', cls: 'r', get: x => UI.num(x.rain_72h_mm, 1) },
      { label: '7 hari', cls: 'r', get: x => UI.num(x.rain_7d_mm, 1) }], e.rain, { caption: 'Hujan sebelum kejadian (mm)' }) : '';
    await UI.dialog({ title: 'Kejadian #' + e.event_id, wide: true,
      body: UI.screenHTML({ channel: 'KEJADIAN #' + e.event_id, body: '<dl class="kv">' + kv.map(([k, x]) => '<dt>' + k + '</dt><dd>' + UI.esc(x || UI.NA) + '</dd>').join('') + '</dl>' +
        '<p class="scr-text" style="margin:8px 0 0"><span class="lbl">DESKRIPSI:</span> ' + UI.esc(e.description) + '</p>' +
        (e.impact_summary ? '<p class="scr-text" style="margin:4px 0 0"><span class="lbl">DAMPAK:</span> ' + UI.esc(e.impact_summary) + '</p>' : '') +
        (rain ? '<p class="lbl" style="margin:8px 0 4px">HUJAN H-0 S.D. H-2 (MM)</p>' + rain : '') }),
      buttons: [{ label: 'Tutup', value: true, default: true, cancel: true }] });
  }

  return { init, destroy };
})();
