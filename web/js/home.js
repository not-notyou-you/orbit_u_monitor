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
// Panel pantau satu kecamatan: kalimat kondisi (normal/tidak + apa yang tidak
// normal) → citra scene terbaru dipotong ke kecamatan → angka terbaru + tren
// 30 hari terhadap rentang biasa. Sumber: GET /api/public/lokasi[/{id}[/trend]].
'use strict';
Pages['home'] = (() => {
  const PICK_KEY = 'orbit-u.lokasi';
  const LEVEL_COLOR = { '-1': '#808080', 0: '#33ff99', 1: '#ffb000', 2: '#ff3b3b' };
  // Indeks 3 desimal: dengan 2 desimal nilai yang sedikit di luar rentang
  // biasa tampak sama dengan batasnya ("-0,59 · biasa s.d. -0,59").
  const DIGITS = { VV: 1, VH: 1, WATER_PCT: 1, FLOOD: 1, NDVI: 3, NDWI: 3, RAIN_24H: 1, RAIN_72H: 1, RAIN_7D: 1 };
  // Band per lintasan (Sentinel-1): titiknya jarang, garisnya disambung.
  const SPARSE = new Set(['VV', 'VH', 'WATER_PCT']);
  let st = null;

  async function init(root, ctx) {
    st = { root, ctx, map: null, layers: {}, me: null, token: 0, items: [], geo: null, current: null, stopWatch: null };
    UI.$$('[data-icon]', root).forEach(el => { el.innerHTML = UI.icon(el.dataset.icon); });
    renderHero(root, ctx.me);

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
      placePanel('after');
      const last = remembered();
      if (last) show(last, 'pick', false);
    }
    ctx.setStatus(ctx.me ? 'Siap · masuk sebagai ' + (ctx.me.full_name || ctx.me.username) : 'Siap · pengunjung');
  }

  function destroy() {
    if (st && st.map) st.map.remove();
    if (st && st.stopWatch) st.stopWatch();
    st = null;
  }

  // ---------------------------------------------------------------- landing
  function renderHero(root, me) {
    const btns = ['<button type="button" class="default" id="hoGo">Pantau lokasi ↓</button>',
      '<a class="btn" href="#tentang">Tentang aplikasi</a>'];
    if (me) {
      UI.$('#hoGreeting', root).insertAdjacentHTML('afterbegin', '<b>Halo, ' + UI.esc(me.full_name || me.username) + '.</b> ');
    } else {
      btns.push('<a class="btn" href="/masuk?next=' + encodeURIComponent('/app#beranda') + '">Masuk…</a>');
      btns.push('<a class="btn" href="/daftar">Daftar akun</a>');
    }
    UI.$('#hoHeroBtns', root).innerHTML = btns.join('');
    UI.$('#hoGo', root).addEventListener('click', () => {
      const first = UI.$$('.pl-sec', root).find(el => !el.hidden);
      if (first) scrollTo(first);
    });
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
      placePanel('after');
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
      placePanel('after');
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
    placePanel('mine');
    show(p.region_id, 'mine', false);
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
    if (st.current && st.current.source === 'mine') { placePanel('after'); st.current.source = 'pick'; }
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
    UI.$$('button[data-rid]', box).forEach(b => b.addEventListener('click', () => show(+b.dataset.rid, 'pick', true)));
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
        l.on('click', () => show(f.properties.region_id, 'pick', true));
      },
    }).addTo(st.map);
    st.aoiBounds = layer.getBounds();
    setTimeout(() => { if (st && st.map) { st.map.invalidateSize(); st.map.fitBounds(st.aoiBounds); } }, 100);
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

  // 'mine' = panel di dalam Lokasi saya (sebelum Informasi lokasi);
  // 'after' = panel sesudah Informasi lokasi.
  function placePanel(where) {
    const panel = UI.$('#hoPantau', st.root);
    if (where === 'mine') UI.$('#hoMine', st.root).insertAdjacentElement('afterend', panel);
    else UI.$('#hoInfo', st.root).insertAdjacentElement('afterend', panel);
  }

  function remembered() {
    let v = null;
    try { v = +localStorage.getItem(PICK_KEY); } catch (e) { /* mode privat */ }
    return v && st.items.some(it => it.region_id === v) ? v : null;
  }

  function scrollTo(el) {
    const reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    el.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
  }

  // ------------------------------------------------------------ panel pantau
  async function show(rid, source, scroll) {
    if (!st) return;
    const token = ++st.token;
    st.current = { rid, source };
    if (source === 'pick') { try { localStorage.setItem(PICK_KEY, String(rid)); } catch (e) { /* mode privat */ } }
    highlight(rid);
    const it = st.items.find(x => x.region_id === rid);
    const panel = UI.$('#hoPantau', st.root);
    panel.hidden = false;
    UI.$('#hoPantauTitle', st.root).textContent = (source === 'mine' ? 'Lokasi saya · ' : 'Pantau lokasi · ') +
      'Kecamatan ' + (it ? it.name : '');
    UI.$('#hoNarasi', st.root).innerHTML = UI.screenHTML({ channel: 'CH-01 · KONDISI', body: UI.loadingHTML() });
    UI.$('#hoCitra', st.root).innerHTML = '';
    UI.$('#hoStats', st.root).innerHTML = '';
    UI.$('#hoTrend', st.root).innerHTML = '';
    UI.$('#hoCitraNote', st.root).textContent = '';
    if (scroll) scrollTo(panel);

    let d;
    try { d = await API.get('/api/public/lokasi/' + rid); }
    catch (e) {
      if (!st || token !== st.token) return;
      UI.$('#hoNarasi', st.root).innerHTML = UI.screenHTML({ channel: 'CH-01 · KONDISI', rec: '● NO SIGNAL', recCls: 'live',
        body: UI.emptyHTML('KONDISI KECAMATAN TIDAK DAPAT DIMUAT') });
      st.ctx.setStatus('Gagal memuat kondisi');
      return;
    }
    if (!st || token !== st.token) return;
    renderNarasi(d);
    renderSubscribe(d.region);
    renderCitra(d);
    renderStats(d);
    st.ctx.setStatus('Siap · Kecamatan ' + d.region.name);
    try {
      const tr = await API.get('/api/public/lokasi/' + rid + '/trend');
      if (st && token === st.token) renderTrend(tr, d);
    } catch (e) {
      if (st && token === st.token) UI.$('#hoTrend', st.root).innerHTML = UI.screenHTML({ channel: 'TREN 30 HARI', body: UI.emptyHTML('TREN TIDAK DAPAT DIMUAT') });
    }
  }

  function daysAgo(iso) {
    const d = UI.parseDate(iso);
    if (!d) return null;
    return Math.round((Date.now() - d.getTime()) / 864e5);
  }

  function dateLine(dates) {
    const part = (label, iso) => {
      if (!iso) return label + ' <span class="v-dim">belum ada</span>';
      const n = daysAgo(iso);
      return label + ' ' + UI.esc(UI.date(iso)) + (n !== null && n > 1 ? ' <span class="' + (n > 14 ? 'v-amber' : 'v-dim') + '">(' + n + ' hari lalu)</span>' : '');
    };
    return part('SENTINEL-1', dates.s1) + ' · ' + part('MODIS', dates.modis) + ' · ' + part('GPM', dates.gpm);
  }

  function renderNarasi(d) {
    const s = d.status || {};
    const lv = LiveTiles.levelInfo(s.level);
    const reason = (s.text || '').split(' — ').slice(1).join(' — ');
    let body = '<p class="pl-status"><span class="lbl">STATUS:</span> <b class="' + lv.cls + '">' +
      UI.esc((s.label || lv.label).toUpperCase()) + '</b>' + (reason ? ' — ' + UI.esc(reason) : '') + '</p>';
    if ((d.abnormal || []).length) {
      body += '<p class="lbl" style="margin:8px 0 2px">YANG TIDAK NORMAL:</p><ul class="pl-abn">' + d.abnormal.map(a =>
        '<li><b class="' + (a.level >= 2 ? 'v-alert' : 'v-amber') + '">' + UI.esc(a.what.charAt(0).toUpperCase() + a.what.slice(1)) +
        '</b> — ' + UI.esc(a.because) + '.</li>').join('') + '</ul>';
    } else if (s.level === 0) {
      body += '<p class="scr-text v-dim" style="margin:6px 0 0">Semua indikator yang tersedia berada di bawah ambang waspada. ' +
        'Tidak adanya tanda bukan jaminan aman: satelit bisa melewatkan kejadian singkat.</p>';
    }
    const all = Object.values(d.items || {});
    if (all.length) {
      body += '<details class="pl-all"><summary class="lbl">SEMUA KALIMAT KONDISI (' + all.length + ')</summary><ul class="pl-abn">' +
        all.map(it => '<li>' + LiveTiles.sentenceHTML(it) + '</li>').join('') + '</ul></details>';
    }
    body += '<p class="lbl" style="margin:8px 0 0">DATA: ' + dateLine(d.dates || {}) + '</p>';
    UI.$('#hoNarasi', st.root).innerHTML =
      '<div class="readouts">' +
        UI.readoutHTML('STATUS', UI.esc((s.label || lv.label).toUpperCase()), 'Kecamatan ' + UI.esc(d.region.name), lv.cls) +
        UI.readoutHTML('TIDAK NORMAL', UI.int((d.abnormal || []).length), (d.abnormal || []).length ? 'indikator di atas ambang' : 'semua dalam batas',
          (d.abnormal || []).length ? 'v-amber' : '') +
        UI.readoutHTML('LUAS', UI.num(d.region.area_km2, 0) + ' km²', 'COD-AB BPS', 'v-cyan') +
      '</div>' +
      UI.screenHTML({ channel: 'CH-01 · KONDISI KEC. ' + d.region.name.toUpperCase(), rec: '● LIVE', recCls: 'live', body });
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

  function renderCitra(d) {
    const box = UI.$('#hoCitra', st.root);
    const im = d.imagery;
    if (!im || !Object.keys(im.previews || {}).length) {
      UI.$('#hoCitraNote', st.root).textContent = '';
      box.innerHTML = UI.screenHTML({ channel: 'CITRA', rec: '● NO DATA', recCls: 'off', body: UI.emptyHTML('BELUM ADA SCENE YANG MENUTUPI KECAMATAN INI') });
      return;
    }
    UI.$('#hoCitraNote', st.root).innerHTML = 'Scene terbaru ' + UI.esc(UI.date(im.scene_date)) + ' (Live Area ' + UI.esc(im.area_name) + '). ' +
      (im.cropped ? 'Gambar dipotong ke batas Kecamatan ' + UI.esc(d.region.name) + '; di luar batas transparan.'
        : '<span class="v-amber">Scene ini belum punya georeferensi, jadi yang tampil citra seluruh area.</span>') +
      ' MODIS/GPM memakai data terdekat dengan tanggal scene. Klik gambar untuk legenda dan penjelasan.';
    // Kalimat per tile = kalimat KECAMATAN ini (kuncinya sama dengan tile);
    // tile tanpa padanan per kecamatan (perubahan air) memakai kalimat area.
    const interp = Object.assign({}, im.interpretations || {}, d.items || {});
    box.innerHTML = LiveTiles.rowsHTML(im.previews, interp, { sceneDate: im.scene_date });
    const opts = Auth.can('aoi3d.view') ? { action: { label: 'Lihat 3D', onPick: item => {
      Terrain3DHandoff.set({ area_id: im.area_id, date: im.scene_date, key: item.key });
      location.hash = '#aoi-3d';
    } } } : {};
    LiveTiles.bindLightbox(box, im.previews, interp, im.scene_date, opts);
  }

  function fmtVal(s, v) {
    if (v === null || v === undefined) return '—';
    const unit = s.unit && !['index', 'indeks'].includes(s.unit) ? ' ' + s.unit : '';
    return UI.num(v, DIGITS[s.band_code] === undefined ? 1 : DIGITS[s.band_code]) + unit;
  }

  function renderStats(d) {
    const box = UI.$('#hoStats', st.root);
    box.innerHTML = (d.stats || []).map(s => {
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

  function renderTrend(tr, d) {
    const box = UI.$('#hoTrend', st.root);
    if (!tr.dates || !tr.dates.length) { box.innerHTML = UI.screenHTML({ channel: 'TREN 30 HARI', body: UI.emptyHTML('BELUM ADA DERET WAKTU') }); return; }
    const statOf = code => (d.stats || []).find(s => s.band_code === code) || {};
    box.innerHTML = tr.groups.map((g, gi) => UI.screenHTML({
      channel: 'CH-0' + (gi + 2) + ' · TREN ' + tr.dates.length + ' HARI · ' + g.title.toUpperCase(),
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
    })).join('');
  }

  return { init, destroy };
})();
