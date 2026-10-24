// js/home.js — Beranda: Pantau Lokasi (#beranda, INTERFACE.md §2 halaman 1, M63).
//
// Landing singkat lalu Pantau lokasi, dengan dua keadaan:
// * Lokasi saya: pengguna yang SUDAH MASUK, izin lokasi diberikan, dan
//   perangkat berada di kecamatan AOI ("wilayah terdaftar"). Panel pantau
//   kecamatan itu tampil lebih dulu, Informasi lokasi di bawahnya.
// * Selain itu (pengunjung, di luar wilayah, izin ditolak, peramban tanpa
//   lokasi, koneksi tidak aman): Informasi lokasi lebih dulu, lalu panel
//   pantau kecamatan yang dipilih (atau pilihan terakhir di peramban ini).
//
// Izin lokasi tidak pernah diminta saat halaman dibuka: hanya dibaca
// otomatis bila sudah 'granted', selain itu lewat tombol (js/geo.js).
// Koordinat hanya dipakai di browser untuk mencari kecamatannya.
//
// Satu kecamatan tampil dalam dua bagian (M66):
// * Pantau lokasi: tiga KPI — status, update terakhir (waktu angka kecamatan
//   terakhir dihitung), dan luas daerah — di dalam Informasi lokasi, di bawah
//   pilihan kecamatan dan di atas peta.
// * Detail lokasi: SATU satelit sekaligus. Kiri pilihan satelit dan channel,
//   kanan citra scene terbaru dipotong ke kecamatan dengan panah ‹ › untuk
//   berganti channel (menyeberang ke satelit lain di ujungnya); angka terbaru + tren 30 hari di bawahnya hanya untuk
//   satelit itu. Sumber: GET /api/public/lokasi[/{id}[/trend]].
//
// Tema tampilan (js/theme.js; M65) berada di antara Informasi lokasi dan
// Detail lokasi.
'use strict';
Pages['home'] = (() => {
  const PICK_KEY = 'orbit-u.lokasi';
  const LEVEL_COLOR = { '-1': '#808080', 0: '#33ff99', 1: '#ffb000', 2: '#ff3b3b' };
  // Indeks 3 desimal: dengan 2 desimal nilai yang sedikit di luar rentang
  // biasa tampak sama dengan batasnya ("-0,59 · biasa s.d. -0,59").
  const DIGITS = { VV: 1, VH: 1, WATER_PCT: 1, FLOOD: 1, NDVI: 3, NDWI: 3, RAIN_24H: 1, RAIN_72H: 1, RAIN_7D: 1 };
  // Band per lintasan (Sentinel-1): titiknya jarang, garisnya disambung.
  const SPARSE = new Set(['VV', 'VH', 'WATER_PCT']);
  // Urutan = LiveTiles.ROWS dan kelompok stats/tren API (etl/lokasi_data.GROUPS).
  const SATS = ['s1', 'modis', 'gpm'];
  const SAT_NAME = { s1: 'Sentinel-1', modis: 'MODIS', gpm: 'GPM' };
  let st = null;

  async function init(root, ctx) {
    st = { root, ctx, map: null, layers: {}, me: null, token: 0, items: [], geo: null, current: null, stopWatch: null,
           sat: 's1', ch: null, d: null, tr: null };
    UI.$$('[data-icon]', root).forEach(el => { el.innerHTML = UI.icon(el.dataset.icon); });
    renderHero(root, ctx.me);
    renderThemes(root);

    const [list, geo] = await Promise.all([
      API.get('/api/public/lokasi').catch(e => { UI.showError('Daftar lokasi gagal dimuat', e); return { items: [] }; }),
      Maps.regions().catch(() => null),
    ]);
    if (!st) return;
    st.items = list.items || [];
    st.geo = geo;
    renderList();
    renderMap();

    let detected = false;
    if (ctx.me) {
      const s = await Geo.state();
      if (!st) return;
      if (s === 'granted') detected = await detect();
      else geoBar(s);
      st.stopWatch = Geo.watchPermission(onPermission);
    } else {
      visitorBar();
    }
    if (!detected) {
      const last = remembered();
      if (last) show(last, 'pick');
    }
    ctx.setStatus(ctx.me ? 'Siap · masuk sebagai ' + (ctx.me.full_name || ctx.me.username) : 'Siap · pengunjung');
  }

  function destroy() {
    // stop(): animasi peta yang masih berjalan saat halaman ditutup melempar galat Leaflet (_leaflet_pos).
    if (st && st.map) { st.map.stop(); st.map.remove(); }
    if (st && st.stopWatch) st.stopWatch();
    if (st && st.onTheme) document.removeEventListener('orbit-u:tema', st.onTheme);
    st = null;
  }

  // ---------------------------------------------------------------- landing
  // Tanpa tombol navigasi (M66): Informasi lokasi langsung di bawahnya, dan
  // Masuk/Daftar untuk pengunjung ada di bar lokasi serta taskbar.
  function renderHero(root, me) {
    if (me) UI.$('#hoGreeting', root).insertAdjacentHTML('afterbegin', '<b>Halo, ' + UI.esc(me.full_name || me.username) + '.</b> ');
  }

  // ---------------------------------------------------------- tema tampilan
  // Satu kartu radio per tema di js/theme.js. Memilih langsung menerapkan
  // tema ke seluruh aplikasi (atribut data-theme di <html>), tanpa memuat ulang.
  function renderThemes(root) {
    const box = UI.$('#hoThemes', root);
    if (!box || !window.Theme) { const fs = UI.$('#hoTheme', root); if (fs) fs.hidden = true; return; }
    const cur = Theme.get();
    box.innerHTML = Theme.LIST.map(t =>
      '<label class="tp-opt' + (t.key === cur ? ' on' : '') + '">' +
        '<input type="radio" name="hoTema" value="' + t.key + '"' + (t.key === cur ? ' checked' : '') + '>' +
        '<span class="tp-prev tp-' + t.key + '" aria-hidden="true"><span class="tp-win">' +
          '<span class="tp-bar"><i></i><i></i><i></i></span>' +
          '<span class="tp-body"><span class="tp-ln"></span><span class="tp-ln s"></span><span class="tp-btn"></span></span>' +
        '</span></span>' +
        '<span class="tp-text"><span class="tp-name">' + UI.esc(t.name) +
          (t.note ? ' <small>(' + UI.esc(t.note) + ')</small>' : '') +
          '<span class="tp-check" aria-hidden="true">dipakai</span></span>' +
        '<span class="tp-desc">' + UI.esc(t.desc) + '</span></span>' +
      '</label>').join('');
    const mark = k => UI.$$('.tp-opt', box).forEach(l => {
      const inp = UI.$('input', l), on = inp.value === k;
      l.classList.toggle('on', on); inp.checked = on;
    });
    box.addEventListener('change', e => {
      if (e.target.name !== 'hoTema') return;
      mark(Theme.set(e.target.value));
      const t = Theme.LIST.find(x => x.key === e.target.value);
      st && st.ctx.setStatus('Tema: ' + (t ? t.name : e.target.value));
    });
    // Tema diganti dari tab lain → kartu yang terpilih ikut.
    st.onTheme = e => mark(e.detail);
    document.addEventListener('orbit-u:tema', st.onTheme);
  }

  // ------------------------------------------------------------- geolokasi
  // Satu pembacaan sekaligus: menekan "Gunakan lokasi saya" juga memicu event
  // izin 'granted' (onPermission), yang tanpa ini membaca lokasi dua kali.
  function detect() {
    if (!st.detecting) st.detecting = readLocation().finally(() => { if (st) st.detecting = null; });
    return st.detecting;
  }

  async function readLocation() {
    const bar = UI.$('#hoGeo', st.root);
    bar.innerHTML = '<p class="pl-geo-line">Membaca lokasi perangkat…</p>';
    let pos;
    try { pos = await Geo.locate(); }
    catch (e) {
      if (!st) return false;
      geoBar(e.code === 1 ? 'denied' : 'error', e.code);
      return false;
    }
    if (!st) return false;
    if (!st.geo || !(st.geo.features || []).length) {
      // Tanpa poligon kecamatan, "di luar wilayah" bisa saja keliru.
      bar.innerHTML = '<p class="pl-geo-line">Batas kecamatan gagal dimuat, jadi lokasi Anda belum bisa dicocokkan. ' +
        'Pilih kecamatan dari daftar. <button type="button" class="small" id="hoRetry">Coba lagi</button></p>';
      bindRetry();
      return false;
    }
    const feat = Geo.regionAt(pos.lon, pos.lat, st.geo);
    markDevice(pos);
    const acc = pos.accuracy ? ' · akurasi ±' + (pos.accuracy >= 1000 ? UI.num(pos.accuracy / 1000, 1) + ' km' : UI.int(pos.accuracy) + ' m') : '';
    const rough = pos.accuracy > Geo.ROUGH_M;
    if (!feat) {
      UI.$('#hoMine', st.root).hidden = true;
      bar.innerHTML = '<p class="pl-geo-line"><b>Lokasi Anda di luar wilayah terpantau</b>' + UI.esc(acc) +
        '. Orbit-U memantau ' + UI.int(st.items.length) + ' kecamatan Lebak Selatan; pilih salah satu di bawah.' +
        (rough ? ' Lokasinya perkiraan kasar — bila Anda sebenarnya di Lebak Selatan, pilih kecamatan secara manual.' : '') +
        ' <button type="button" class="small" id="hoRetry">Coba lagi</button></p>';
      bindRetry();
      return false;
    }
    const p = feat.properties;
    UI.$('#hoMine', st.root).hidden = false;
    UI.$('#hoMineWhere', st.root).innerHTML = 'Anda berada di <b>Kecamatan ' + UI.esc(p.name) + '</b>' + UI.esc(acc) + '.' +
      (rough ? ' <span class="v-amber">Lokasi perkiraan (akurasi rendah, mis. dari Wi-Fi); bila keliru, pilih kecamatan di Informasi lokasi.</span>' : '') +
      ' <button type="button" class="small" id="hoRetry">Perbarui</button>' +
      '<span class="pl-priv">Koordinat hanya dipakai di peramban ini untuk mencari kecamatan; tidak dikirim ke server.</span>';
    bindRetry();
    bar.innerHTML = '<p class="pl-geo-line">Ingin melihat kecamatan lain? Pilih dari daftar atau peta.</p>';
    show(p.region_id, 'mine');
    return true;
  }

  function bindRetry() {
    const b = UI.$('#hoRetry', st.root);
    if (b) b.addEventListener('click', () => UI.busy(b, async () => {
      if (!st.geo) st.geo = await Maps.regions().catch(() => null);
      return detect();
    }));
  }

  // Bar status lokasi untuk pengguna yang sudah masuk tetapi belum/tidak bisa dideteksi.
  function geoBar(state, code) {
    const bar = UI.$('#hoGeo', st.root);
    UI.$('#hoMine', st.root).hidden = true;
    if (state === 'prompt') {
      bar.innerHTML = '<p class="pl-geo-line">Izinkan lokasi untuk langsung melihat kecamatan tempat Anda berada. ' +
        '<button type="button" class="default" id="hoUseLoc">Gunakan lokasi saya</button></p>' +
        '<p class="pl-priv">Peramban akan meminta izin. Koordinat hanya dipakai di peramban ini untuk mencari kecamatan; tidak dikirim ke server.</p>';
      const b = UI.$('#hoUseLoc', bar);
      b.addEventListener('click', () => UI.busy(b, () => detect()));
      return;
    }
    const reason = Geo.REASON[state === 'error' ? (code || 0) : state] || Geo.REASON[0];
    const help = (state === 'denied' || code === 1 || code === 2)
      ? '<details class="pl-help"><summary>Cara mengaktifkan izin lokasi</summary><p>' + UI.esc(Geo.HELP[Geo.platform()]) + '</p></details>' : '';
    const retry = (state === 'error') ? ' <button type="button" class="small" id="hoRetry">Coba lagi</button>' : '';
    bar.innerHTML = '<p class="pl-geo-line">' + UI.esc(reason) + retry + '</p>' + help;
    if (retry) bindRetry();
  }

  function visitorBar() {
    UI.$('#hoGeo', st.root).innerHTML = '<p class="pl-geo-line"><b>Lokasi saya</b> tersedia setelah masuk: kecamatan tempat Anda berada ' +
      'dideteksi otomatis bila Anda mengizinkan lokasi. <a href="/masuk?next=' + encodeURIComponent('/app#beranda') + '">Masuk</a> · ' +
      '<a href="/daftar">Daftar akun Relawan (gratis)</a></p>';
  }

  // Izin dicabut/diberikan dari pengaturan situs selagi halaman terbuka.
  function onPermission(state) {
    if (!st) return;
    if (state === 'granted') { detect(); return; }
    geoBar(state);
    if (st.current && st.current.source === 'mine') st.current.source = 'pick';
  }

  // ------------------------------------------------------- daftar + peta
  function badge(it) {
    const lv = LiveTiles.levelInfo(it.status && it.status.level);
    return '<span class="pl-badge ' + lv.cls + '">' + UI.esc(((it.status && it.status.label) || lv.label).toUpperCase()) + '</span>' +
      (it.alert ? '<span class="pl-badge v-alert">ALERT</span>' : '');
  }

  function renderList() {
    const box = UI.$('#hoList', st.root);
    if (!st.items.length) { box.innerHTML = UI.emptyHTML('BELUM ADA KECAMATAN TERPANTAU'); return; }
    box.innerHTML = st.items.map(it => '<button type="button" role="option" aria-selected="false" data-rid="' + it.region_id + '">' +
      '<span class="pl-name">' + UI.esc(it.name) + '</span>' + badge(it) + '</button>').join('');
    UI.$$('button[data-rid]', box).forEach(b => b.addEventListener('click', () => show(+b.dataset.rid, 'pick')));
    const counts = [0, 0, 0];
    st.items.forEach(it => { const l = it.status && it.status.level; if (l >= 0) counts[l]++; });
    UI.$('#hoListSum', st.root).textContent = UI.int(st.items.length) + ' kecamatan · ' + UI.int(counts[0]) + ' normal, ' +
      UI.int(counts[1]) + ' waspada, ' + UI.int(counts[2]) + ' tinggi.';
    UI.$('#hoMapRec', st.root).textContent = UI.int(st.items.length) + ' KECAMATAN';
  }

  function styleFor(rid) {
    const it = st.items.find(x => x.region_id === rid);
    const lvl = it && it.status ? it.status.level : -1;
    const sel = st.current && st.current.rid === rid;
    const c = LEVEL_COLOR[lvl] || LEVEL_COLOR[-1];
    return { color: sel ? '#ffffff' : c, fillColor: c, weight: sel ? 3 : 1, fillOpacity: sel ? 0.4 : 0.22 };
  }

  function renderMap() {
    st.map = Maps.create(UI.$('#hoMap', st.root));
    if (!st.map || !st.geo || !st.geo.features.length) return;
    const layer = L.geoJSON(st.geo, {
      style: f => styleFor(f.properties.region_id),
      onEachFeature: (f, l) => {
        st.layers[f.properties.region_id] = l;
        const it = st.items.find(x => x.region_id === f.properties.region_id);
        l.bindTooltip(UI.esc(f.properties.name) + (it && it.status ? ' · ' + UI.esc(it.status.label) : ''), { sticky: true });
        l.on('click', () => show(f.properties.region_id, 'pick'));
      },
    }).addTo(st.map);
    st.aoiBounds = layer.getBounds();
    setTimeout(() => { if (st && st.map) { st.map.invalidateSize(); st.map.fitBounds(st.aoiBounds, { animate: false }); } }, 100);
  }

  // Titik perangkat + lingkaran akurasi, hanya di peta lokal ini.
  function markDevice(pos) {
    if (!st.map) return;
    if (st.device) st.device.forEach(l => l.remove());
    st.device = [
      L.circle([pos.lat, pos.lon], { radius: pos.accuracy || 0, color: '#4de1ff', weight: 1, fillOpacity: 0.08 }),
      L.circleMarker([pos.lat, pos.lon], { radius: 5, color: '#000', weight: 1, fillColor: '#4de1ff', fillOpacity: 1 })
        .bindTooltip('Lokasi perangkat Anda'),
    ];
    st.device.forEach(l => l.addTo(st.map));
  }

  function highlight(rid) {
    Object.entries(st.layers).forEach(([id, l]) => l.setStyle(styleFor(+id)));
    UI.$$('#hoList button[data-rid]', st.root).forEach(b => b.setAttribute('aria-selected', String(+b.dataset.rid === rid)));
    const l = st.layers[rid];
    if (l && st.map) { l.bringToFront(); st.map.fitBounds(l.getBounds(), { maxZoom: 11, padding: [20, 20] }); }
  }

  function remembered() {
    let v = null;
    try { v = +localStorage.getItem(PICK_KEY); } catch (e) { /* mode privat */ }
    return v && st.items.some(it => it.region_id === v) ? v : null;
  }

  // ------------------------------------------------------------ panel pantau
  async function show(rid, source) {
    if (!st) return;
    const token = ++st.token;
    st.current = { rid, source };
    if (source === 'pick') { try { localStorage.setItem(PICK_KEY, String(rid)); } catch (e) { /* mode privat */ } }
    highlight(rid);
    const it = st.items.find(x => x.region_id === rid);
    const panel = UI.$('#hoPantau', st.root), detail = UI.$('#hoDetail', st.root);
    const name = 'Kecamatan ' + (it ? it.name : '');
    panel.hidden = false;
    detail.hidden = true;
    UI.$('#hoPantauTitle', st.root).textContent = (source === 'mine' ? 'Lokasi saya · ' : 'Pantau lokasi · ') + name;
    UI.$('#hoDetailTitle', st.root).textContent = 'Detail lokasi · ' + name;
    UI.$('#hoKpi', st.root).innerHTML = UI.loadingHTML();
    st.d = null; st.tr = null;

    let d;
    try { d = await API.get('/api/public/lokasi/' + rid); }
    catch (e) {
      if (!st || token !== st.token) return;
      UI.$('#hoKpi', st.root).innerHTML = UI.screenHTML({ channel: 'KONDISI', rec: '● NO SIGNAL', recCls: 'live',
        body: UI.emptyHTML('KONDISI KECAMATAN TIDAK DAPAT DIMUAT') });
      st.ctx.setStatus('Gagal memuat kondisi');
      return;
    }
    if (!st || token !== st.token) return;
    st.d = d;
    renderKpi(d);
    renderSubscribe(d.region);
    detail.hidden = false;
    renderDetail();
    st.ctx.setStatus('Siap · Kecamatan ' + d.region.name);
    try {
      const tr = await API.get('/api/public/lokasi/' + rid + '/trend');
      if (st && token === st.token) { st.tr = tr; renderTrend(); }
    } catch (e) {
      if (st && token === st.token) UI.$('#hoTrend', st.root).innerHTML = UI.screenHTML({ channel: 'TREN 30 HARI', body: UI.emptyHTML('TREN TIDAK DAPAT DIMUAT') });
    }
  }

  // Waktu WIB apa pun zona waktu perangkatnya: semua kecamatan ada di Lebak Selatan.
  function wib(iso) {
    const d = UI.parseDate(iso);
    if (!d) return '—';
    return d.toLocaleString('id-ID', { timeZone: 'Asia/Jakarta', day: 'numeric', month: 'short', year: 'numeric',
      hour: '2-digit', minute: '2-digit' }) + ' WIB';
  }

  function renderKpi(d) {
    const s = d.status || {};
    const lv = LiveTiles.levelInfo(s.level);
    const reason = (s.text || '').split(' — ').slice(1).join(' — ');
    UI.$('#hoKpi', st.root).innerHTML =
      UI.readoutHTML('STATUS', UI.esc((s.label || lv.label).toUpperCase()), reason ? UI.esc(reason) : '', lv.cls) +
      UI.readoutHTML('UPDATE TERAKHIR', UI.esc(wib(d.updated_at)), 'angka satelit terakhir dihitung') +
      UI.readoutHTML('LUAS DAERAH', UI.num(d.region.area_km2, 0) + ' km²', 'Sumber data: BPS (COD-AB)', 'v-cyan');
  }

  // Peringatan email untuk kecamatan ini (M64). Hanya pengguna yang masuk;
  // email dan pilihan kecamatan tetap diatur lengkap di Akun saya.
  async function renderSubscribe(region) {
    const box = UI.$('#hoSub', st.root);
    if (!st.ctx.me) { box.hidden = true; return; }
    let p;
    try { p = await API.get('/api/auth/notify'); } catch (e) { box.hidden = true; return; }
    if (!st || !st.current || st.current.rid !== region.region_id) return;
    const on = p.all_regions || p.region_ids.includes(region.region_id);
    const mailOk = p.email && p.email_verified_at;
    box.hidden = false;
    if (on && mailOk) {
      box.innerHTML = 'Peringatan email untuk Kecamatan ' + UI.esc(region.name) + ' aktif (dikirim ke ' + UI.esc(p.email) + '). ' +
        '<a href="#sistem/akun">Atur di Akun saya</a>';
      return;
    }
    box.innerHTML = (on ? 'Kecamatan ini sudah Anda pilih, tetapi email belum diisi. '
      : '<button type="button" class="small" id="hoSubBtn">Terima peringatan email untuk kecamatan ini</button> ') +
      (mailOk ? '' : '<a href="#sistem/akun">Isi email di Akun saya</a> agar peringatan terkirim.');
    const b = UI.$('#hoSubBtn', box);
    if (b) b.addEventListener('click', () => UI.busy(b, async () => {
      try {
        await API.put('/api/auth/notify', { all_regions: false, region_ids: p.region_ids.concat([region.region_id]) });
        renderSubscribe(region);
      } catch (e) { UI.showError('Peringatan email', e); }
    }));
  }

  // ---------------------------------------------------------- detail lokasi
  // Tingkat terburuk tiap satelit dari daftar "tidak normal" API (kunci
  // kalimat berawalan s1_/modis_/gpm_), untuk lencana di pilihan satelit.
  function satLevel(sat) {
    return ((st.d && st.d.abnormal) || []).filter(a => (a.key || '').indexOf(sat + '_') === 0)
      .reduce((m, a) => Math.max(m, a.level || 0), 0);
  }

  const interpOf = d => Object.assign({}, (d.imagery && d.imagery.interpretations) || {}, d.items || {});

  function renderDetail() {
    const d = st.d, im = d.imagery || {}, previews = im.previews || {};
    const row = LiveTiles.ROWS[SATS.indexOf(st.sat)];
    if (row.keys.indexOf(st.ch) < 0) st.ch = row.keys.find(k => previews[k]) || row.keys[0];
    const interp = interpOf(d);

    UI.$('#hoSats', st.root).innerHTML = SATS.map((k, i) => {
      const lvl = satLevel(k), lv = LiveTiles.levelInfo(lvl);
      return '<label class="check"><input type="radio" name="hoSat" value="' + k + '"' + (k === st.sat ? ' checked' : '') + '>' +
        '<span class="pl-name">' + UI.esc(LiveTiles.ROWS[i].title) + '</span>' +
        (lvl > 0 ? '<span class="pl-badge ' + lv.cls + '">' + UI.esc(lv.label.toUpperCase()) + '</span>' : '') + '</label>';
    }).join('');
    UI.$('#hoChs', st.root).innerHTML = row.keys.map(k => {
      const cat = interp[k] && LiveTiles.CAT[interp[k].category];
      return '<label class="check"><input type="radio" name="hoCh" value="' + k + '"' + (k === st.ch ? ' checked' : '') +
        (previews[k] ? '' : ' disabled') + '>' +
        '<span class="pl-name">' + UI.esc(LiveTiles.LABEL[k]) + '</span>' +
        (cat && cat[1] ? '<span class="pl-badge ' + cat[1] + '">' + UI.esc(cat[0]) + '</span>' : '') +
        (previews[k] ? '' : '<span class="v-dim">tidak ada</span>') + '</label>';
    }).join('');
    UI.$$('input[name=hoSat]', st.root).forEach(r => r.addEventListener('change', () => pickSat(r.value)));
    UI.$$('input[name=hoCh]', st.root).forEach(r => r.addEventListener('change', () => { st.ch = r.value; renderView(); }));

    const date = d.dates && d.dates[st.sat];
    UI.$('#hoCitraNote', st.root).innerHTML = !im.scene_date ? '' :
      'Scene terbaru ' + UI.esc(UI.date(im.scene_date)) +
      (st.sat !== 's1' ? ' (' + UI.esc(SAT_NAME[st.sat]) + ' memakai data terdekat dengan tanggal itu)' : '') + '. ' +
      (im.cropped ? 'Gambar dipotong ke batas kecamatan.'
        : '<span class="v-amber">Scene ini belum punya georeferensi, jadi yang tampil citra seluruh area.</span>') +
      (date ? ' Angka ' + UI.esc(SAT_NAME[st.sat]) + ' terakhir: ' + UI.esc(UI.date(date)) + '.' : '');
    UI.$('#hoStatsTitle', st.root).textContent = 'Statistik ' + SAT_NAME[st.sat];
    renderView();
    renderStats();
    renderTrend();
  }

  // Pilihan satelit di kiri dan panah di citra memakai jalan yang sama; ch =
  // null berarti channel pertama yang bergambar. Fokus kembali ke panah yang
  // ditekan, karena isi layar digambar ulang.
  function pickSat(sat, step, ch) {
    st.sat = sat;
    st.ch = ch || null;
    renderDetail();
    if (step) { const b = UI.$('#hoView .pl-nav[data-step="' + step + '"]', st.root); if (b) b.focus(); }
  }

  function renderView() {
    const d = st.d, im = d.imagery || {}, previews = im.previews || {};
    const box = UI.$('#hoView', st.root);
    const i = SATS.indexOf(st.sat), row = LiveTiles.ROWS[i];
    // Panah menelusuri semua channel bergambar berurutan, menyeberang ke
    // satelit berikutnya/sebelumnya di ujung channel satelit ini.
    let seq = [];
    LiveTiles.ROWS.forEach((r, ri) => r.keys.forEach(k => { if (previews[k]) seq.push({ sat: SATS[ri], ch: k }); }));
    if (!seq.some(x => x.ch === st.ch)) seq = seq.concat([{ sat: st.sat, ch: st.ch }]);
    const pos = seq.findIndex(x => x.ch === st.ch);
    const prev = seq[(pos + seq.length - 1) % seq.length], next = seq[(pos + 1) % seq.length];
    const interp = interpOf(d);
    const p = previews[st.ch];
    const img = p
      ? '<button type="button" class="thumb" data-key="' + st.ch + '" aria-label="' + UI.esc(LiveTiles.LONG[st.ch]) +
          ': perbesar, legenda, dan penjelasan"><img ' + UI.imgAttrs(p) + ' alt=""></button>'
      : '<div class="noimg">' + (Object.keys(previews).length ? 'NO DATA' : 'BELUM ADA SCENE YANG MENUTUPI KECAMATAN INI') + '</div>';
    const sentence = LiveTiles.sentenceHTML(interp[st.ch]);
    const nav = (step, to) => {
      const name = SAT_NAME[to.sat] + ' ' + LiveTiles.LABEL[to.ch];
      return '<button type="button" class="pl-nav" data-step="' + step + '" title="' + UI.esc(name) + '"' +
        ' aria-label="Channel ' + (step > 0 ? 'berikutnya' : 'sebelumnya') + ': ' + UI.esc(name) + '">' +
        '<svg viewBox="0 0 24 48" aria-hidden="true"><path d="' + (step > 0 ? 'M6 6 L18 24 L6 42' : 'M18 6 L6 24 L18 42') + '"/></svg></button>';
    };
    box.innerHTML = UI.screenHTML({
      channel: 'CH-01 · ' + row.ch + ' · ' + LiveTiles.LABEL[st.ch].toUpperCase(),
      rec: im.scene_date ? UI.date(im.scene_date) : '● NO DATA', recCls: im.scene_date ? '' : 'off',
      body: '<div class="pl-viewer">' + nav(-1, prev) + '<div class="pl-img">' + img + '</div>' + nav(1, next) + '</div>' +
        (p && p.legend ? LiveTiles.legendHTML(p.legend) : '') +
        (sentence ? '<p class="scr-text" style="margin:6px 0 0">' + sentence + '</p>' : ''),
    });
    UI.$$('.pl-nav', box).forEach(b => b.addEventListener('click', () => {
      const to = b.dataset.step === '1' ? next : prev;
      pickSat(to.sat, b.dataset.step, to.ch);
    }));
    if (!p) return;
    // Lightbox hanya berisi channel satelit ini, sama dengan yang tampil.
    const own = {};
    row.keys.forEach(k => { if (previews[k]) own[k] = previews[k]; });
    const opts = Auth.can('aoi3d.view') ? { action: { label: 'Lihat 3D', onPick: item => {
      Terrain3DHandoff.set({ area_id: im.area_id, date: im.scene_date, key: item.key });
      location.hash = '#aoi-3d';
    } } } : {};
    LiveTiles.bindLightbox(box, own, interp, im.scene_date, opts);
  }

  function fmtVal(s, v) {
    if (v === null || v === undefined) return '—';
    const unit = s.unit && !['index', 'indeks'].includes(s.unit) ? ' ' + s.unit : '';
    return UI.num(v, DIGITS[s.band_code] === undefined ? 1 : DIGITS[s.band_code]) + unit;
  }

  function renderStats() {
    const box = UI.$('#hoStats', st.root);
    box.innerHTML = (st.d.stats || []).filter(s => s.group === st.sat).map(s => {
      const r = s.range || {};
      const out = s.value !== null && s.value !== undefined && r.p98 !== null && r.p98 !== undefined &&
        (s.value > r.p98 || s.value < r.p02);
      const sub = [];
      if (s.obs_date) sub.push(UI.esc(UI.date(s.obs_date, 'short')));
      if (s.prev_value !== null && s.prev_value !== undefined) sub.push('sebelumnya ' + UI.esc(fmtVal(s, s.prev_value)));
      if (r.p02 !== null && r.p02 !== undefined) sub.push('biasa ' + UI.esc(UI.num(r.p02, DIGITS[s.band_code] || 1)) + ' s.d. ' + UI.esc(fmtVal(s, r.p98)));
      return '<div title="' + UI.esc(s.about || '') + '">' +
        UI.readoutHTML(s.band_name || s.band_code, UI.esc(fmtVal(s, s.value)), sub.join(' · ') +
          (out ? '<br><span class="v-amber">DI LUAR RENTANG BIASA</span>' : ''), out ? 'v-amber' : '') + '</div>';
    }).join('') || UI.emptyHTML('BELUM ADA ANGKA');
  }

  function renderTrend() {
    const box = UI.$('#hoTrend', st.root), tr = st.tr, d = st.d;
    if (!tr) { box.innerHTML = UI.screenHTML({ channel: 'TREN 30 HARI', body: UI.loadingHTML() }); return; }
    const g = (tr.groups || []).find(x => x.key === st.sat);
    if (!tr.dates || !tr.dates.length || !g) { box.innerHTML = UI.screenHTML({ channel: 'TREN 30 HARI', body: UI.emptyHTML('BELUM ADA DERET WAKTU') }); return; }
    const statOf = code => (d.stats || []).find(s => s.band_code === code) || {};
    box.innerHTML = UI.screenHTML({
      channel: 'CH-02 · TREN ' + tr.dates.length + ' HARI · ' + g.title.toUpperCase(),
      body: '<div class="pl-charts">' + g.bands.map(b => {
        const s = statOf(b.band_code);
        let pts = tr.dates.map((x, i) => ({ x, y: b.values[i] }));
        if (SPARSE.has(b.band_code)) pts = pts.filter(p => p.y !== null && p.y !== undefined);
        const ys = pts.map(p => p.y).filter(v => v !== null && v !== undefined);
        // Garis ambang hanya bila dekat dengan data; ambang yang jauh (mis.
        // hujan 100 mm saat hari-hari 3 mm) menggencet garisnya jadi datar.
        const thr = {};
        if (ys.length) {
          const lo = Math.min(...ys), hi = Math.max(...ys), span = Math.max(hi - lo, Math.abs(hi) * 0.2, 1);
          (s.thresholds || []).forEach(t => { if (t.value >= lo - span && t.value <= hi + span) thr[t.label] = t.value; });
        }
        const unit = b.unit && !['index', 'indeks'].includes(b.unit) ? b.unit : '';
        return '<div class="pl-chart"><p class="lbl"><i class="swatch" style="background:' + UI.esc(b.color || '#33ff99') + '"></i> ' +
          UI.esc(s.band_name || b.band_code) + (unit ? ' (' + UI.esc(unit) + ')' : '') + '</p>' +
          UI.chartSVG([{ label: s.band_name || b.band_code, color: b.color, points: pts }],
            { width: 360, height: 150, unit, thresholds: thr, label: 'Tren ' + (s.band_name || b.band_code),
              zero: /^RAIN|FLOOD|WATER_PCT/.test(b.band_code), range: b.range ? { lo: b.range.p02, hi: b.range.p98 } : null }) +
          '</div>';
      }).join('') + '</div>',
    });
  }

  return { init, destroy };
})();
