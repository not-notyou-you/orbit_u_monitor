// js/terrain3d.js — Relief 3D: pratinjau Live ditempel (drape) di atas DEM.
//
// APA YANG 3D DI SINI, DAN APA YANG TIDAK
// Sentinel-1 GRD tidak memuat tinggi. GeoTIFF-nya memang array tiga dimensi,
// tapi dimensi ketiganya BAND (VV, VH, turunan), bukan elevasi — semuanya
// nilai hambur-balik di permukaan yang sama. Jadi relief di halaman ini datang
// dari DEM terpisah; citra satelitnya cuma tekstur yang ditempel di atasnya.
// Tinggi yang terlihat adalah topografi tanah, BUKAN hasil ukur radar. Tinggi
// dari Sentinel-1 sendiri butuh InSAR (produk SLC, pasangan orbit,
// interferogram) — jalur pemrosesan terpisah yang tidak ada di pipeline ini.
//
// Georeferensi citra diambil dari scene.preview_grid.corners_wgs84 (empat
// sudut; lihat module10.grid_corners_wgs84). Scene lama yang dirender sebelum
// itu dicatat jatuh kembali ke bbox daerah — citranya tetap tampil, posisinya
// kurang presisi, dan itu dikatakan di layar alih-alih didiamkan.
//
// Leaflet tidak dipakai di halaman ini: ia tidak punya kamera 3D sama sekali.
// MapLibre GL dimuat dari CDN saat halaman ini dibuka saja, bukan di app.html,
// supaya halaman lain tidak menanggung ~800 KB yang tidak mereka pakai.
'use strict';
Pages['terrain3d'] = (() => {
  const MAPLIBRE_VERSION = '4.7.1';
  const MAPLIBRE_JS = 'https://unpkg.com/maplibre-gl@' + MAPLIBRE_VERSION + '/dist/maplibre-gl.js';
  const MAPLIBRE_CSS = 'https://unpkg.com/maplibre-gl@' + MAPLIBRE_VERSION + '/dist/maplibre-gl.css';

  // DEM: AWS Terrain Tiles (data Mapzen/Nextzen, AWS Open Data) — terbuka,
  // tanpa kunci API, encoding "terrarium". Resolusinya ~30 m dan berhenti di
  // zoom 15; zoom lebih dalam memakai ubin 15 yang diregangkan, jadi relief
  // tidak bertambah detail walau citranya iya.
  const DEM_URL = 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png';
  const DEM_MAXZOOM = 15;
  const DEM_ATTR = 'DEM: <a href="https://registry.opendata.aws/terrain-tiles/" target="_blank" rel="noopener">AWS Terrain Tiles</a> (SRTM/NED)';
  const DEM_NOTE = 'AWS Terrain Tiles (terrarium), turunan SRTM — resolusi ~30 m, berhenti di zoom ' + DEM_MAXZOOM +
    '. Tinggi berasal dari DEM ini, bukan dari Sentinel-1.';

  const SRC_IMG = 'citra', SRC_DEM = 'dem', SRC_BASE = 'base';
  const LYR_IMG = 'citra-lyr', LYR_HILL = 'hillshade-lyr', LYR_BASE = 'base-lyr';

  let st = null;

  // ------------------------------------------------------------------ pemuat
  let libPromise = null;
  function loadMapLibre() {
    if (libPromise) return libPromise;
    libPromise = new Promise((resolve, reject) => {
      if (window.maplibregl) return resolve(window.maplibregl);
      const l = document.createElement('link');
      l.rel = 'stylesheet'; l.href = MAPLIBRE_CSS;
      document.head.appendChild(l);
      const s = document.createElement('script');
      s.src = MAPLIBRE_JS;
      s.onload = () => window.maplibregl ? resolve(window.maplibregl) : reject(new Error('MapLibre dimuat tapi tidak terdaftar'));
      s.onerror = () => reject(new Error('Gagal memuat MapLibre GL dari CDN'));
      document.body.appendChild(s);
    }).catch(e => { libPromise = null; throw e; });
    return libPromise;
  }

  // -------------------------------------------------------------- geometri
  // "POLYGON((x y,x y,...))" -> [[lon,lat],...]. Dipakai hanya sebagai jalan
  // mundur, dan jalan mundur yang KASAR: bbox itu milik daerah, sedangkan
  // extent tiap scene berbeda-beda. Scene Sentinel-1 yang cuma satu frame
  // menutupi AOI jauh lebih sempit daripada scene mosaik dua frame, jadi
  // merentangkannya ke bbox daerah bisa menggeser citra puluhan kilometer --
  // bukan sekadar beberapa meter. Karena itu halaman menuliskan bahwa
  // posisinya perkiraan, dan backfill (scripts/backfill_preview_grid.py) ada
  // supaya jalan mundur ini hampir tidak pernah terpakai.
  function wktRing(wkt) {
    const m = /\(\(([^)]*)\)\)/.exec(wkt || '');
    if (!m) return null;
    const pts = m[1].split(',').map(p => p.trim().split(/\s+/).map(Number))
      .filter(p => p.length >= 2 && Number.isFinite(p[0]) && Number.isFinite(p[1]));
    return pts.length >= 4 ? pts : null;
  }

  // Empat sudut penempatan citra, urut kiri-atas -> kanan-atas -> kanan-bawah
  // -> kiri-bawah (urutan `coordinates` image source MapLibre).
  function cornersFor(card) {
    const g = card.scene && card.scene.preview_grid;
    if (g && g.corners_wgs84 && g.corners_wgs84.length === 4) return { corners: g.corners_wgs84, exact: true };
    const ring = wktRing(card.area && card.area.bbox_wkt);
    if (!ring) return null;
    const lons = ring.map(p => p[0]), lats = ring.map(p => p[1]);
    const w = Math.min.apply(null, lons), e = Math.max.apply(null, lons);
    const s = Math.min.apply(null, lats), n = Math.max.apply(null, lats);
    return { corners: [[w, n], [e, n], [e, s], [w, s]], exact: false };
  }

  function bboxOf(corners) {
    const lons = corners.map(p => p[0]), lats = corners.map(p => p[1]);
    return [[Math.min.apply(null, lons), Math.min.apply(null, lats)],
            [Math.max.apply(null, lons), Math.max.apply(null, lats)]];
  }

  // Kunci lapisan yang punya PNG, diurut seperti tile di Kondisi > Citra.
  function layerKeys(previews) {
    return LiveTiles.ROWS.reduce((acc, r) => acc.concat(r.keys.filter(k => previews[k])), []);
  }

  // ------------------------------------------------------------- sumber data
  // Halaman ini melayani DUA jalan masuk dengan satu mesin peta:
  //
  //   live   /app#aoi-3d          — perlu masuk; semua scene tersimpan yang
  //                                 boleh dilihat peran itu (USER 30 hari).
  //   public /relief              — tanpa masuk; HANYA scene terbaru per area,
  //                                 batas yang sama dengan /api/public/live.
  //
  // Keduanya dinormalkan ke bentuk kartu yang sama supaya sisa modul tidak
  // perlu tahu dari mana datanya: {area, dates, scene}. Mode ditentukan oleh
  // body[data-requires-auth] -- penanda yang sudah dipakai app.html vs
  // kondisi.html, bukan tebakan baru.
  const SOURCES = {
    live: {
      async areas() {
        return (await API.get('/api/live/areas')).map(a => ({
          area_id: a.area_id, name: a.name, enabled: a.enabled }));
      },
      async scene(areaId, date) {
        return API.get('/api/live/areas/' + areaId + '/card' + API.qs({ date: date }));
      },
      empty: 'BELUM ADA LIVE AREA. ADMINISTRATOR DAPAT MENAMBAHKANNYA DI PENGATURAN › LIVE AREA.',
      noGeo: 'GEOREFERENSI SCENE TIDAK DIKETAHUI — CITRA TIDAK BISA DITEMPATKAN DI PETA',
    },
    public: {
      // Satu permintaan memuat scene terbaru SEMUA area, jadi hasilnya
      // disimpan dan scene() membacanya dari situ -- berganti area tidak
      // memanggil API lagi.
      async areas() {
        const r = await API.get('/api/public/live');
        this._items = (r && r.items) || [];
        return this._items.map(it => ({ area_id: it.area_id, name: it.area_name, enabled: true }));
      },
      async scene(areaId) {
        const it = (this._items || []).find(x => x.area_id === areaId);
        if (!it) return { area: {}, dates: [], scene: null };
        return {
          area: { name: it.area_name },
          dates: [{ date: it.scene_date, status: it.status }],
          scene: { date: it.scene_date, previews: it.previews || {},
                   interpretations: it.interpretations || {}, preview_grid: it.preview_grid },
        };
      },
      empty: 'BELUM ADA AREA PANTAUAN YANG TERBUKA UNTUK PUBLIK.',
      // Publik hanya melihat scene TERBARU, jadi begitu siklus berikutnya
      // berjalan georeferensinya ada. Itu yang dikatakan, bukan "gagal".
      noGeo: 'SCENE PUBLIK TERBARU BELUM MEMUAT GEOREFERENSI PRATINJAU — RELIEF 3D AKAN TERSEDIA SETELAH SCENE BERIKUTNYA DIRENDER. PRATINJAU 2D-NYA TETAP BISA DILIHAT DI KONDISI TERKINI.',
    },
  };

  // ------------------------------------------------------------------- init
  function init(root, ctx) {
    // Titipan dari tombol "Lihat 3D" di lightbox Pantauan Live, kalau pengguna
    // datang dari sana. Dibaca sekali lalu hangus (lihat Terrain3DHandoff).
    const pick = (window.Terrain3DHandoff && Terrain3DHandoff.take()) || null;
    const pub = document.body.dataset.requiresAuth === 'false';
    st = { root, ctx, pub: pub, src: pub ? SOURCES.public : SOURCES.live,
           areas: [], areaId: null, date: null, card: null, key: null,
           geo: null, map: null, maplibre: null, onAdm: null, ro: null };
    if (pick) {
      st.areaId = pick.area_id || null;
      st.date = pick.date || null;
      st.key = pick.key || null;
    }
    const $ = s => UI.$(s, root);
    $('#t3DemNote').textContent = DEM_NOTE;
    if (pub) {
      // Tidak ada yang bisa dipilih: publik hanya melihat scene terbaru.
      // Pemilihnya disembunyikan, bukan dinonaktifkan -- select berisi satu
      // pilihan yang tidak bisa diubah cuma menimbulkan pertanyaan.
      $('#t3DateField').hidden = true;
      const note = $('#t3ScopeNote');
      note.hidden = false;
      note.textContent = 'Hanya scene terbaru yang terbuka untuk publik. Masuk untuk melihat tanggal lain.';
    }
    $('#t3Area').addEventListener('change', e => { st.areaId = Number(e.target.value); st.date = null; loadCard(); });
    $('#t3Date').addEventListener('change', e => { st.date = e.target.value || null; loadCard(); });
    $('#t3Layer').addEventListener('change', e => { st.key = e.target.value; applyImage(); renderLegend(); });
    $('#t3Opacity').addEventListener('input', e => {
      $('#t3OpacityVal').textContent = e.target.value + '%';
      if (st.map && st.map.getLayer(LYR_IMG)) st.map.setPaintProperty(LYR_IMG, 'raster-opacity', Number(e.target.value) / 100);
    });
    $('#t3Exag').addEventListener('input', e => {
      $('#t3ExagVal').textContent = Number(e.target.value).toFixed(1) + '×';
      applyTerrain();
    });
    $('#t3Pitch').addEventListener('input', e => {
      $('#t3PitchVal').textContent = e.target.value + '°';
      if (st.map) st.map.jumpTo({ pitch: Number(e.target.value) });
    });
    $('#t3Reset').addEventListener('click', fitArea);
    $('#t3North').addEventListener('click', () => { if (st.map) st.map.easeTo({ bearing: 0, duration: 400 }); });
    // Checkbox "Garis wilayah" di taskbar berlaku untuk tekstur ini juga.
    st.onAdm = () => applyImage();
    document.addEventListener('orbit-u:garis-wilayah', st.onAdm);
    return loadAreas();
  }

  function destroy() {
    if (!st) return;
    if (st.onAdm) document.removeEventListener('orbit-u:garis-wilayah', st.onAdm);
    if (st.ro) st.ro.disconnect();
    if (st.map) { try { st.map.remove(); } catch (e) { /* kanvas sudah dilepas */ } }
    st = null;
  }

  function deckMessage(text, cls) {
    UI.$('#t3Deck', st.root).innerHTML = UI.screenHTML({
      channel: 'SYS', rec: cls ? '● TIDAK TERSEDIA' : '', recCls: cls || '', body: UI.emptyHTML(text) });
  }

  async function loadAreas() {
    const $ = s => UI.$(s, st.root);
    try { st.areas = await st.src.areas(); }
    catch (e) { deckMessage('GAGAL MEMUAT AREA'); UI.showError('Relief 3D', e); return; }
    if (!st.areas.length) {
      $('#t3Area').innerHTML = '<option>—</option>'; $('#t3Area').disabled = true;
      deckMessage(st.src.empty, 'off');
      st.ctx.setStatus('Belum ada area'); return;
    }
    $('#t3Area').innerHTML = st.areas.map(a =>
      '<option value="' + a.area_id + '">' + UI.esc(a.name) + (a.enabled ? '' : ' (nonaktif)') + '</option>').join('');
    $('#t3Area').disabled = st.areas.length < 2;
    // Titipan bisa menyebut area yang sudah dihapus; jatuh ke area pertama
    // alih-alih meminta kartu untuk id yang tidak ada lagi.
    if (!st.areas.some(a => a.area_id === st.areaId)) { st.areaId = st.areas[0].area_id; st.date = null; }
    $('#t3Area').value = st.areaId;
    await loadCard();
  }

  async function loadCard() {
    const $ = s => UI.$(s, st.root);
    st.ctx.setStatus('Memuat scene…');
    try {
      st.card = await st.src.scene(st.areaId, st.date);
    } catch (e) {
      if (e.code === 'SCENE_OUT_OF_RANGE') { st.date = null; UI.showError('Relief 3D', e); return loadCard(); }
      deckMessage('GAGAL MEMUAT KARTU'); UI.showError('Relief 3D', e); return;
    }
    const dates = st.card.dates || [], sc = st.card.scene;
    $('#t3Date').innerHTML = dates.length
      ? dates.map(d => '<option value="' + d.date + '">' + UI.esc(UI.date(d.date)) +
          (d.status === 'PARTIAL' ? ' (sebagian)' : '') + '</option>').join('')
      : '<option>—</option>';
    $('#t3Date').disabled = !dates.length;
    if (sc) $('#t3Date').value = sc.date;

    const previews = (sc && sc.previews) || {};
    const keys = layerKeys(previews);
    if (!sc || !keys.length) {
      $('#t3Layer').innerHTML = '<option>—</option>'; $('#t3Layer').disabled = true;
      UI.$('#t3Legend', st.root).innerHTML = '';
      deckMessage(sc ? 'SCENE INI TIDAK PUNYA PRATINJAU YANG BISA DITEMPEL' : 'BELUM ADA SCENE YANG SIAP', 'off');
      st.ctx.setStatus('Tidak ada pratinjau'); return;
    }
    $('#t3Layer').disabled = false;
    $('#t3Layer').innerHTML = keys.map(k =>
      '<option value="' + k + '">' + UI.esc(LiveTiles.LONG[k] || k) + '</option>').join('');
    if (keys.indexOf(st.key) < 0) st.key = keys[0];
    $('#t3Layer').value = st.key;

    const geo = cornersFor(st.card);
    if (!geo) {
      deckMessage(st.src.noGeo, 'off');
      st.ctx.setStatus('Georeferensi tidak ada'); return;
    }
    st.geo = geo;
    try { await ensureMap(); } catch (e) { st.ctx.setStatus('Peta 3D tidak tersedia'); return; }
    if (!st) return;
    applyImage();
    renderLegend();
    fitArea();
    st.ctx.setStatus('Siap · ' + (st.card.area.name || '') + ' · scene ' + UI.date(sc.date) +
      (geo.exact ? '' : ' · posisi perkiraan'));
  }

  // ------------------------------------------------------------------- peta
  async function ensureMap() {
    if (st.map) return;
    const deck = UI.$('#t3Deck', st.root);
    deck.innerHTML = UI.screenHTML({ channel: 'CH-3D · RELIEF', rec: '● MEMUAT', recCls: 'live', flush: true,
      body: '<div class="t3-wrap"><div class="t3-map" id="t3Map"></div>' +
            '<p class="t3-caption" id="t3Caption"></p></div>' });
    let maplibre;
    try { maplibre = await loadMapLibre(); }
    catch (e) {
      deckMessage('MAPLIBRE GL TIDAK DAPAT DIMUAT — PERIKSA KONEKSI INTERNET. HALAMAN INI MEMBUTUHKAN WEBGL DAN AKSES CDN.', 'off');
      throw e;
    }
    if (!st) return;                      // halaman sudah ditinggalkan
    // supported() dihapus di MapLibre v4; hanya diperiksa kalau memang ada.
    if (typeof maplibre.supported === 'function' && !maplibre.supported()) {
      deckMessage('PERAMBAN INI TIDAK MENDUKUNG WEBGL — RELIEF 3D TIDAK BISA DIGAMBAR. PAKAI KONDISI › CITRA UNTUK PRATINJAU 2D.', 'off');
      throw new Error('WebGL tidak didukung');
    }
    st.maplibre = maplibre;
    const sources = {};
    sources[SRC_BASE] = { type: 'raster', tiles: [Maps.TILE_URL], tileSize: 256, maxzoom: 18, attribution: Maps.TILE_ATTR };
    sources[SRC_DEM] = { type: 'raster-dem', tiles: [DEM_URL], tileSize: 256, maxzoom: DEM_MAXZOOM,
                         encoding: 'terrarium', attribution: DEM_ATTR };
    const map = new maplibre.Map({
      container: UI.$('#t3Map', st.root),
      style: {
        version: 8,
        sources: sources,
        layers: [
          { id: LYR_BASE, type: 'raster', source: SRC_BASE },
          // Hillshade di BAWAH citra: saat opasitas citra diturunkan, bentuk
          // lerengnya tetap terbaca walau DEM-nya sendiri tak berwarna.
          { id: LYR_HILL, type: 'hillshade', source: SRC_DEM,
            paint: { 'hillshade-exaggeration': 0.4 } },
        ],
      },
      pitch: Number(UI.$('#t3Pitch', st.root).value),
      bearing: 0,
      maxPitch: 80,
      center: [106.2, -6.75],
      zoom: 9,
      attributionControl: { compact: true },
    });
    map.addControl(new maplibre.NavigationControl({ visualizePitch: true }), 'top-right');
    map.addControl(new maplibre.ScaleControl({ unit: 'metric' }));
    map.on('error', e => console.warn('[Relief 3D]', (e && e.error && e.error.message) || e));
    st.map = map;
    await new Promise(res => map.once('load', res));
    if (!st) { try { map.remove(); } catch (e) { /* diabaikan */ } return; }
    applyTerrain();
    const rec = UI.$('#t3Deck .scr-rec', st.root);
    if (rec) rec.textContent = '● 3D';
    // Panel kiri bisa berubah lebar setelah fragmen dirender.
    if (window.ResizeObserver) {
      st.ro = new ResizeObserver(() => { if (st && st.map) st.map.resize(); });
      st.ro.observe(UI.$('#t3Map', st.root));
    }
  }

  function applyTerrain() {
    if (!st.map) return;
    const ex = Number(UI.$('#t3Exag', st.root).value);
    // 0 = matikan terrain sama sekali, bukan exaggeration 0: dengan terrain
    // aktif MapLibre tetap menyampel DEM tiap frame tanpa ada yang terlihat.
    st.map.setTerrain(ex > 0 ? { source: SRC_DEM, exaggeration: ex } : null);
  }

  // Tekstur = PNG lapisan terpilih, varian bergaris kalau checkbox taskbar aktif.
  function applyImage() {
    if (!st || !st.map || !st.card || !st.card.scene || !st.key || !st.geo) return;
    const p = (st.card.scene.previews || {})[st.key];
    if (!p) return;
    const url = UI.imgSrc(p);
    const coords = st.geo.corners;
    const src = st.map.getSource(SRC_IMG);
    if (src) {
      src.updateImage({ url: url, coordinates: coords });
    } else {
      st.map.addSource(SRC_IMG, { type: 'image', url: url, coordinates: coords });
      st.map.addLayer({ id: LYR_IMG, type: 'raster', source: SRC_IMG,
        paint: { 'raster-opacity': Number(UI.$('#t3Opacity', st.root).value) / 100,
                 // Nearest: satu piksel preview mewakili puluhan meter sensor.
                 // Interpolasi akan mengarang gradien halus yang tidak diukur.
                 'raster-resampling': 'nearest', 'raster-fade-duration': 0 } });
    }
    renderCaption();
  }

  function renderCaption() {
    const cap = UI.$('#t3Caption', st.root);
    if (!cap) return;
    const sc = st.card.scene;
    const bits = [UI.esc(LiveTiles.LONG[st.key] || st.key) + ' · ' + UI.esc(UI.date(sc.date)),
      'relief dari DEM (SRTM), bukan dari radar'];
    if (!st.geo.exact) bits.push('<b class="v-amber">POSISI PERKIRAAN: memakai bbox daerah, bukan extent scene — scene ini dirender sebelum georeferensi preview dicatat</b>');
    cap.innerHTML = bits.join(' · ');
  }

  function renderLegend() {
    const box = UI.$('#t3Legend', st.root);
    if (!box || !st.card.scene) return;
    const p = (st.card.scene.previews || {})[st.key];
    const it = (st.card.scene.interpretations || {})[st.key];
    box.innerHTML = (p ? LiveTiles.legendHTML(p.legend) : '') +
      (it ? '<p class="mut" style="margin:6px 0 0;font-size:11px">' + LiveTiles.sentenceHTML(it) + '</p>' : '');
  }

  function fitArea() {
    if (!st || !st.map || !st.geo) return;
    st.map.fitBounds(bboxOf(st.geo.corners),
      { padding: 24, pitch: Number(UI.$('#t3Pitch', st.root).value), duration: 600 });
  }

  return { init, destroy };
})();
