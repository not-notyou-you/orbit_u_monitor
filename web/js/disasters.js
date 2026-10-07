// js/disasters.js — Kejadian Bencana (INTERFACE.md §2.5, §4.6). CRUD tercatat di audit_log (trigger DB).
'use strict';
Pages['disasters'] = (() => {
  const SOURCES = { GMLS: 'GMLS', BPBD_LEBAK: 'BPBD Lebak', BNPB_DIBI: 'BNPB (DIBI)', MEDIA: 'Media', LAINNYA: 'Lainnya' };
  const LIMIT = 50;
  let st = null;
  // API mengembalikan `location: {lat, lon}` (etl.disasters.event_dict);
  // perender di bawah membaca e.lat/e.lon. Dulu tidak pernah diterjemahkan,
  // sehingga titik peta dan prefill formulir selalu kosong.
  const flat = e => Object.assign(e, { lat: e.location ? e.location.lat : null, lon: e.location ? e.location.lon : null });

  async function init(root, ctx) {
    st = { root, ctx, types: [], regions: [], page: 1, map: null, layer: null, items: [] };
    const $ = s => UI.$(s, root);
    try {
      const [types, geo] = await Promise.all([API.get('/api/disaster-types'), Maps.regions()]);
      st.types = types.items; st.regions = geo.features.map(f => f.properties).sort((a, b) => a.name.localeCompare(b.name, 'id'));
      st.geo = geo;
    } catch (e) { UI.showError('Kejadian Bencana', e); }
    $('#dzType').insertAdjacentHTML('beforeend', st.types.map(t => '<option value="' + UI.esc(t.type_code) + '">' + UI.esc(t.type_name) + '</option>').join(''));
    $('#dzRegion').insertAdjacentHTML('beforeend', st.regions.map(r => '<option value="' + r.region_id + '">' + UI.esc(r.name) + '</option>').join(''));
    $('#dzFilter').addEventListener('submit', ev => { ev.preventDefault(); st.page = 1; UI.busy($('#dzApply'), load); });
    $('#dzNew').addEventListener('click', () => openForm(null));
    Excel.mount($('#dzExcel'), ['disasters', 'disaster_rain', 'disaster_types'], { onImported: load });
    st.map = Maps.create($('#dzMap'));
    if (st.map && st.geo) {
      st.aoi = L.geoJSON(st.geo, { style: { color: '#1a9960', weight: 1, fillOpacity: 0.05 }, interactive: false }).addTo(st.map);
      setTimeout(() => { if (st && st.map) { st.map.invalidateSize(); st.map.fitBounds(st.aoi.getBounds()); } }, 100);
    }
    await load();
  }

  function destroy() { if (st && st.map) st.map.remove(); st = null; }

  async function load() {
    const $ = s => UI.$(s, st.root);
    const from = $('#dzFrom').value, to = $('#dzTo').value;
    if (from && to && from > to) { UI.showError('Saring daftar kejadian', { code: 'INVALID_DATE_RANGE' }); return; }
    st.ctx.setStatus('Memuat…');
    let r;
    try {
      r = await API.get('/api/disasters' + API.qs({ date_from: from, date_to: to, type_code: $('#dzType').value,
        region_id: $('#dzRegion').value, is_verified: $('#dzVer').value, limit: LIMIT, offset: (st.page - 1) * LIMIT }));
    } catch (e) { $('#dzTable').innerHTML = UI.emptyHTML('GAGAL MEMUAT'); UI.showError('Kejadian Bencana', e); return; }
    st.items = r.items.map(flat);
    $('#dzCount').textContent = UI.int(r.total) + ' KEJADIAN';
    $('#dzTable').innerHTML = UI.tableHTML([
      { label: 'Tanggal', get: e => UI.date(e.event_date) + (e.event_end_date && e.event_end_date !== e.event_date ? ' – ' + UI.date(e.event_end_date) : '') },
      { label: 'Jenis', key: 'disaster_type_name' }, { label: 'Kecamatan', key: 'region_name' }, { label: 'Desa', key: 'village_name' },
      { label: 'Sumber', get: e => SOURCES[e.info_source] || e.info_source },
      { label: 'Verifikasi', html: true, get: e => e.is_verified ? 'TERVERIFIKASI' : '<span class="v-amber">BELUM</span>' },
      { label: 'Titik', get: e => e.lat !== null && e.lat !== undefined ? 'ADA' : '' },
      { label: 'Aksi', html: true, get: e => '<button type="button" class="small" data-open="' + e.event_id + '" aria-label="Detail kejadian ' + e.event_id + '">Properti…</button>' },
    ], st.items, { empty: 'BELUM ADA KEJADIAN TERCATAT. GUNAKAN "CATAT KEJADIAN BARU" ATAU IMPOR EXCEL.', caption: 'Daftar kejadian bencana' }) +
      UI.pagerHTML(r.total, LIMIT, (st.page - 1) * LIMIT);
    UI.$$('[data-open]', st.root).forEach(b => b.addEventListener('click', () => openDetail(Number(b.dataset.open))));
    UI.$$('#dzTable [data-page]', st.root).forEach(b => b.addEventListener('click', () => { st.page = Number(b.dataset.page); load(); }));
    renderMap();
    st.ctx.setStatus('Siap · ' + UI.int(r.total) + ' kejadian');
  }

  function renderMap() {
    if (!st.map) return;
    if (st.layer) st.layer.remove();
    const pts = st.items.filter(e => e.lat !== null && e.lat !== undefined);
    UI.$('#dzMapRec', st.root).textContent = UI.int(pts.length) + ' TITIK';
    st.layer = L.layerGroup(pts.map(e => L.circleMarker([e.lat, e.lon], {
      radius: 6, color: '#000', weight: 1, fillColor: e.is_verified ? '#ffb000' : '#4de1ff', fillOpacity: 0.95,
    }).bindTooltip(UI.esc(e.disaster_type_name + ' · ' + e.region_name + ' · ' + UI.date(e.event_date) + (e.is_verified ? '' : ' (belum diverifikasi)')))
      .on('click', () => openDetail(e.event_id)))).addTo(st.map);
    if (pts.length) st.map.fitBounds(L.latLngBounds(pts.map(e => [e.lat, e.lon])).pad(0.3), { maxZoom: 12 });
  }

  async function openDetail(id) {
    let e;
    try { e = flat(await API.get('/api/disasters/' + id)); } catch (err) { UI.showError('Detail kejadian', err); return; }
    const kv = [['JENIS', e.disaster_type_name], ['TANGGAL', UI.date(e.event_date) + (e.event_end_date ? ' – ' + UI.date(e.event_end_date) : '')],
      ['KECAMATAN', e.region_name], ['DESA', e.village_name], ['TITIK', e.lat !== null && e.lat !== undefined ? UI.num(e.lat, 5) + ', ' + UI.num(e.lon, 5) : null],
      ['SUMBER', (SOURCES[e.info_source] || e.info_source) + (e.source_reference ? ' · ' + e.source_reference : '')],
      ['VERIFIKASI', e.is_verified ? 'Terverifikasi' : 'Belum'], ['DICATAT', UI.dateTime(e.recorded_at)]];
    const v = await UI.dialog({ title: 'Properti kejadian #' + e.event_id, wide: true,
      body: UI.screenHTML({ channel: 'KEJADIAN #' + e.event_id, body: '<dl class="kv">' + kv.map(([k, x]) => '<dt>' + k + '</dt><dd>' + UI.esc(x || UI.NA) + '</dd>').join('') + '</dl>' +
          '<p class="scr-text" style="margin:8px 0 0"><span class="lbl">DESKRIPSI:</span> ' + UI.esc(e.description) + '</p>' +
          (e.impact_summary ? '<p class="scr-text" style="margin:4px 0 0"><span class="lbl">DAMPAK:</span> ' + UI.esc(e.impact_summary) + '</p>' : '') }) +
        '<div style="height:8px"></div>' +
        UI.screenHTML({ channel: 'HUJAN KECAMATAN H-0..H-2', body: UI.tableHTML([
          { label: 'Hari', key: 'day' }, { label: 'Hujan 24 jam', cls: 'r', get: r => UI.num(r.rain_24h_mm, 1) + ' mm' },
          { label: '72 jam', cls: 'r', get: r => UI.num(r.rain_72h_mm, 1) + ' mm' }, { label: '7 hari', cls: 'r', get: r => UI.num(r.rain_7d_mm, 1) + ' mm' },
        ], e.rain || []) + '<p class="v-dim" style="margin:4px 0 0;font-size:11px">"—" = belum ada data hidromet untuk tanggal itu (menunggu backfill).</p>' }),
      buttons: [{ label: 'Ubah…', value: 'edit', default: true }, { label: 'Hapus…', value: 'del' }, { label: 'Tutup', value: null, cancel: true }] });
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
      await UI.info('Kejadian Bencana', (e ? 'Perubahan kejadian #' : 'Kejadian #') + r.event_id + ' tersimpan.');
      load();
    } catch (err) { await UI.showError('Simpan kejadian', err); openForm(e, Object.assign({}, body, { lat: body.location ? body.location.lat : null, lon: body.location ? body.location.lon : null })); }
  }

  return { init, destroy };
})();
