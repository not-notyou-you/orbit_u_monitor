// web/js/app.js — kerangka "desktop" Orbital 95: router hash, jendela utama, taskbar.
//
// Susunan halaman mengikuti INTERFACE.md §2 (M56, rancangan pemilik proyek):
// Beranda → 3D AOI → Citra Satelit → Forecast → Kejadian → Data → Laporan →
// Sistem, ditambah Masuk (/masuk) dan Registrasi (/daftar) di luar aplikasi.
// Aplikasi terbuka untuk pengunjung: menu disusun dari izin di
// GET /api/auth/session, jadi pengunjung hanya melihat Beranda, Citra
// (30 hari), Kejadian (1 tahun), dan Sistem › Tentang. Hash susunan lama
// (M53) tetap hidup lewat ALIASES.
//
// /app#<tujuan>[/<tab>[/<bagian>]] memuat fragmen pages/<berkas>.html ke panel
// jendela dan skrip js/<berkas>.js (sekali), lalu memanggil
// Pages[<berkas>].init(root, ctx). Satu berkas boleh dipakai beberapa tab
// (mis. citra-sat untuk Sentinel-1/MODIS/GPM); tabnya membawa `source`/`kind`.
'use strict';

window.Pages = window.Pages || {};
const ASSET_V = '6.16';

// `lede` = keterangan halaman; tidak lagi ditampilkan di jendela (dihapus atas
// permintaan pemilik proyek), disimpan sebagai dokumentasi rute.
const ROUTES = [
  {
    hash: 'beranda', file: 'home', title: 'Beranda', icon: 'globe', perm: ['home.view'],
    lede: 'Sambutan, penjelasan singkat, halaman yang tersedia untuk peran Anda, pilihan tema tampilan, dan peta kecamatan AOI.',
    desc: 'Titik mendarat: apa aplikasi ini, keadaan terakhir, dan pintasan ke halaman Anda.',
  },
  {
    hash: 'aoi-3d', file: 'terrain3d', title: '3D AOI', icon: 'satellite', perm: ['aoi3d.view'], css: true,
    lede: 'Pratinjau scene ditempel di atas model elevasi (DEM) dengan kamera 3D. Reliefnya berasal dari DEM, bukan dari Sentinel-1 — radar GRD tidak mengukur tinggi.',
    desc: 'Citra satelit di atas relief 3D, bisa dimiringkan dan diputar.',
  },
  {
    hash: 'citra', title: 'Citra Satelit', icon: 'dish', perm: ['citra.view'],
    desc: 'Gambar dan angka Sentinel-1, MODIS, dan GPM, perbandingan dua tanggal, dan laporan PDF.',
    tabs: [
      {
        key: 'ringkasan', file: 'citra', title: 'Ringkasan', perm: ['citra.view'],
        lede: 'Rekap scene yang tersedia per satelit untuk area terpilih. Pilih satelit untuk melihat gambar dan angkanya.',
      },
      {
        key: 'sentinel-1', file: 'citra-sat', source: 's1', title: 'Sentinel-1', perm: ['citra.view'],
        lede: 'Radar menembus awan. Pilih tanggal di daftar; centang "Bandingkan" untuk melihat dua tanggal berdampingan.',
      },
      {
        key: 'modis', file: 'citra-sat', source: 'modis', title: 'MODIS', perm: ['citra.view'],
        lede: 'Sensor optik harian; tile kosong biasanya karena awan. Pilih tanggal, lalu bandingkan bila perlu.',
      },
      {
        key: 'gpm', file: 'citra-sat', source: 'gpm', title: 'GPM', perm: ['citra.view'],
        lede: 'Perkiraan hujan satelit (petak ±10 km). Pilih tanggal; angka hujan per kecamatan ada di bawah untuk pengguna yang masuk.',
      },
      {
        key: 'laporan', file: 'citra-report', title: 'Laporan PDF', perm: ['citra.view'],
        lede: 'Centang halaman yang ingin dicetak — satu, beberapa, atau semuanya — lalu unduh sebagai satu PDF.',
      },
    ],
  },
  {
    hash: 'forecast', title: 'Forecast', icon: 'chart', perm: ['diagram.view'],
    desc: 'Grafik semua band 30 hari terakhir dengan forecast 15 hari, dan analisa per kecamatan dengan laporan PDF.',
    tabs: [
      {
        key: 'terbaru', file: 'diagram', mode: 'latest', title: 'Keadaan terbaru', perm: ['diagram.view'],
        lede: 'Semua band dalam satu grafik, 30 hari terakhir plus forecast 15 hari, diperbarui otomatis. Klik nama band untuk menyembunyikan atau membaca penjelasannya.',
      },
      {
        key: 'analisa-daerah', file: 'diagram', mode: 'regions', title: 'Analisa daerah', perm: ['diagram.view'],
        lede: 'Pilih kecamatan (dan warnanya), rentang tanggal, dan band, lalu tekan Tampilkan. Forecast 15 hari dihitung dari data s.d. tanggal akhir. PDF memuat semua band.',
      },
      {
        key: 'evaluasi', file: 'analytics', title: 'Tren & evaluasi alert', perm: ['analytics.view'],
        lede: 'Tren per kecamatan dengan penanda kejadian dan forecast 15 hari (dari data s.d. tanggal akhir), dan evaluasi alert terhadap kejadian terverifikasi.',
      },
    ],
  },
  {
    hash: 'kejadian', title: 'Kejadian', icon: 'alarm', perm: ['disasters.view'],
    desc: 'Kejadian bencana yang benar-benar terjadi di lapangan, di peta dan tabel.',
    tabs: [
      {
        key: 'lihat', file: 'disasters-view', title: 'Lihat kejadian', perm: ['disasters.view'],
        lede: 'Kejadian tercatat di wilayah AOI. Saring menurut tanggal, jenis, atau kecamatan; klik titik di peta untuk detailnya.',
      },
      {
        key: 'kelola', file: 'disasters', title: 'Kelola kejadian', perm: ['disasters.manage'],
        lede: 'Tambah, ubah, atau hapus catatan kejadian. Menghapus hanya menandai; data tidak hilang.',
      },
    ],
  },
  {
    hash: 'data', title: 'Data', icon: 'folder', perm: ['datasets.manage'],
    desc: 'Data per satelit, backfill dengan log, unduhan dengan mode fusion, dan EDA.',
    tabs: [
      {
        key: 'ringkasan', file: 'data-home', title: 'Ringkasan', perm: ['datasets.manage'],
        lede: 'Keadaan data ketiga satelit dan backfill yang sedang berjalan. Pilih satelit untuk mengelola datanya.',
      },
      {
        key: 'sentinel-1', file: 'data-source', source: 's1', title: 'Sentinel-1', perm: ['datasets.manage'],
        lede: 'Scene Sentinel-1 yang tersimpan. Backfill membuat dataset S1 atas AOI; progres dan lognya tampil di bawah.',
      },
      {
        key: 'gpm', file: 'data-source', source: 'gpm', title: 'GPM', perm: ['datasets.manage'],
        lede: 'Granule GPM IMERG. Backfill menjalankan Job Hidromet per tanggal; lognya tampil langsung di bawah.',
      },
      {
        key: 'modis', file: 'data-source', source: 'modis', title: 'MODIS', perm: ['datasets.manage'],
        lede: 'Granule MODIS. Backfill mengisi tanggal yang belum punya angka MODIS; lognya tampil langsung di bawah.',
      },
      {
        key: 'unduh', file: 'create-dataset', title: 'Unduh data', perm: ['datasets.manage'], css: true,
        lede: 'Pilih satelit, tanggal, dan mode: tanpa fusion, atau fusion full coverage / co-occurrence / hybrid. Rentang maksimal 366 hari.',
      },
      {
        key: 'tersimpan', file: 'catalog', title: 'Dataset tersimpan', perm: ['datasets.manage'], css: true,
        lede: 'Dataset yang sudah dibuat. Pilih satu untuk melihat cakupan, produk, asal-usul, dan mengunduh ZIP-nya.',
      },
      {
        key: 'proses', file: 'process', title: 'Proses berjalan', perm: ['datasets.manage'],
        lede: 'Unduhan dan pengolahan yang sedang jalan di seluruh dataset, beserta tahap per scene dan antreannya.',
      },
      {
        key: 'eda', file: 'eda', title: 'EDA', perm: ['eda.view'],
        lede: 'Data understanding: pilih satelit dan rentang tanggal untuk melihat kelengkapan, sebaran, pencilan, dan korelasi.',
      },
    ],
  },
  {
    hash: 'laporan', title: 'Laporan', icon: 'doc', perm: ['reports.hydromet', 'reports.datahealth'],
    desc: 'Laporan PDF otomatis mingguan/bulanan dan laporan rentang tanggal bebas.',
    tabs: [
      {
        key: 'kesehatan-data', file: 'reports', kind: 'DATAHEALTH', title: 'Kesehatan data', perm: ['reports.datahealth'],
        lede: 'Kelengkapan, kualitas, pipeline, dan lineage. Laporan mingguan/bulanan dibuat otomatis; buat sendiri untuk rentang bebas.',
      },
      {
        key: 'keadaan-aoi', file: 'reports', kind: 'HYDROMET', title: 'Keadaan AOI', perm: ['reports.hydromet'],
        lede: 'Hujan, alert, kejadian, dan kondisi permukaan AOI dari satelit. Otomatis mingguan/bulanan, atau buat sendiri untuk rentang bebas.',
      },
    ],
  },
  {
    hash: 'sistem', title: 'Sistem', icon: 'gear', perm: ['about.view'],
    desc: 'Tentang aplikasi, log, akun, dan pengaturan.',
    tabs: [
      {
        key: 'tentang', file: 'about', title: 'Tentang', perm: ['about.view'],
        lede: 'Apa aplikasi ini, sumber datanya, batasannya, dan siapa yang membuatnya.',
      },
      {
        key: 'log', file: 'logs', title: 'Log', perm: ['logs.data', 'logs.disasters', 'logs.all'],
        lede: 'Catatan yang hanya bisa dibaca, sesuai peran: Data Engineer → halaman Data, Analis → halaman Kejadian, Administrator → semuanya.',
      },
      {
        key: 'akun', file: 'account', title: 'Akun saya', perm: ['account.manage'],
        lede: 'Ubah kata sandi dan kelola token API milik Anda sendiri.',
      },
      {
        key: 'pengguna', file: 'admin', group: 'akses', title: 'Manajemen akun', perm: ['admin.accounts'], sub: true,
        lede: 'Akun, peran, dan token API milik seluruh pengguna. Akun Analis, Data Engineer, dan Administrator hanya dibuat di sini.',
      },
      {
        key: 'pengaturan', file: 'admin', group: 'pengaturan', title: 'Pengaturan aplikasi', perm: ['admin.system'], sub: true,
        lede: 'Keadaan sistem, pipeline, scene, Live Area, penyimpanan, wilayah, aturan, dan pengaturan aplikasi.',
      },
    ],
  },
];

// Hash susunan lama → lokasi baru. Tautan dan bookmark lama tetap hidup;
// router menulis ulang alamatnya ke bentuk kanonik tanpa menambah riwayat.
// Dicocokkan dari awalan terpanjang, jadi "pengaturan/operasi/live" ikut
// pindah dengan sisa segmennya.
const ALIASES = {
  // M61: halaman Diagram berganti nama menjadi Forecast
  'diagram': 'forecast',
  // susunan M53
  'kondisi': 'citra',
  'kondisi/citra': 'citra/sentinel-1',
  'kondisi/kecamatan': 'citra/gpm',
  'kondisi/relief': 'aoi-3d',
  'riwayat': 'forecast',
  'riwayat/grafik': 'forecast/evaluasi',
  'riwayat/laporan': 'laporan',
  'data/daftar': 'data/tersimpan',
  'data/buat': 'data/unduh',
  'pengaturan': 'sistem/pengaturan',
  'pengaturan/ringkasan': 'sistem/pengaturan',
  'pengaturan/operasi': 'sistem/pengaturan',
  'pengaturan/konfigurasi': 'sistem/pengaturan',
  'pengaturan/akses': 'sistem/pengguna',
  'pengaturan/jejak': 'sistem/log',
  'akun': 'sistem/akun',
  // susunan sebelum M53
  'pantauan': 'citra/sentinel-1',
  'hari-ini': 'citra/gpm',
  'statistik': 'citra/gpm',
  'analitik': 'forecast/evaluasi',
  'katalog': 'data/tersimpan',
  'buat-dataset': 'data/unduh',
  'admin': 'sistem/pengaturan',
};

const Shell = (() => {
  const loadedScripts = {};
  const loadedCss = {};
  let current = null;       // { route, tab, page }
  const tasks = [];         // tujuan yang pernah dibuka sesi ini (tombol taskbar)
  let healthOk = null;

  function loadScript(file) {
    if (!loadedScripts[file]) {
      loadedScripts[file] = new Promise((resolve, reject) => {
        const s = document.createElement('script');
        s.src = 'js/' + file + '.js?v=' + ASSET_V;
        s.onload = resolve; s.onerror = () => reject(new Error('Gagal memuat skrip ' + file));
        document.body.appendChild(s);
      });
    }
    return loadedScripts[file];
  }
  function loadCss(file) {
    if (loadedCss[file]) return;
    const l = document.createElement('link');
    l.rel = 'stylesheet'; l.href = 'css/' + file + '.css?v=' + ASSET_V;
    document.head.appendChild(l); loadedCss[file] = true;
  }

  // ------------------------------------------------------------ izin & susunan
  const visibleRoutes = () => ROUTES.filter(r => !r.tray && allowed(r));
  function visibleTabs(route) { return (route.tabs || []).filter(t => Auth.canAny(t.perm)); }
  // Tujuan bertab boleh dibuka bila minimal satu tabnya boleh dibuka.
  function allowed(route) {
    return route.tabs ? visibleTabs(route).length > 0 : Auth.canAny(route.perm);
  }

  // ---------------------------------------------------------------- taskbar
  function taskbarHTML(publicMode) {
    return '<nav class="taskbar" aria-label="Taskbar">' +
      '<button type="button" class="start" id="startBtn" aria-haspopup="menu" aria-expanded="false" aria-controls="startMenu">' + UI.icon('satellite') + '<span>Mulai</span></button>' +
      '<label class="tb-check" for="admToggle" title="Tampilkan batas dan nama kecamatan di atas setiap pratinjau citra">' +
        '<input type="checkbox" id="admToggle"><span>Garis wilayah</span></label>' +
      '<div class="task-buttons" id="taskButtons" role="toolbar" aria-label="Halaman yang pernah dibuka"></div>' +
      '<div class="tray" role="status" aria-live="off">' +
        '<span class="lamp-row" id="linkLamp" title="Status tautan server"><i class="lamp" aria-hidden="true"></i><span id="linkText">LINK ?</span></span>' +
        '<span class="tray-extra" id="trayUser">' + (publicMode ? 'Pengunjung' : '') + '</span>' +
        '<time id="utcClock" class="num" title="Waktu UTC"></time>' +
      '</div></nav>' +
      '<div class="start-menu raised hidden" id="startMenu" role="menu" aria-label="Menu Mulai"><div class="side" aria-hidden="true">ORBIT-U 95</div><ul id="startList"></ul></div>';
  }

  function menuItems(me) {
    const items = [];
    // Tujuan bertab dirender bersama tabnya supaya #laporan/keadaan-aoi tercapai
    // dalam satu tindakan. `data-hash` tetap hanya di item tingkat atas: itu
    // yang dipakai untuk menandai halaman aktif dan memeriksa izin per peran.
    ROUTES.filter(r => allowed(r)).forEach(r => {
      items.push({ href: '/app#' + r.hash, label: r.title, icon: r.icon, hash: r.hash });
      const ts = visibleTabs(r);
      if (ts.length > 1) ts.forEach(t => items.push({ href: '/app#' + r.hash + '/' + t.key, label: t.title, icon: r.icon, tabHash: r.hash + '/' + t.key }));
    });
    if (!me) {
      items.push({ sep: true });
      items.push({ href: '/masuk', label: 'Masuk…', icon: 'key' });
      items.push({ href: '/daftar', label: 'Daftar akun…', icon: 'user' });
    }
    items.push({ sep: true });
    items.push({ href: '/docs', label: 'Dokumentasi API', icon: 'help', ext: true });
    if (me) items.push({ action: 'logout', label: 'Keluar', icon: 'door' });
    return items;
  }

  function bindTaskbar(me) {
    const btn = UI.$('#startBtn'), menu = UI.$('#startMenu'), list = UI.$('#startList');
    // Menu Mulai hanya memuat halaman utama; sub-halaman dibuka lewat tab di jendela.
    list.innerHTML = menuItems(me).filter(it => !it.tabHash).map(it => it.sep ? '<li role="separator"><hr></li>' :
      '<li role="none">' + (it.action
        ? '<button type="button" role="menuitem" data-action="' + it.action + '">' + UI.icon(it.icon) + '<span>' + UI.esc(it.label) + '</span></button>'
        : '<a role="menuitem" class="' + (it.tabHash ? 'mi-sub' : 'mi-top') + '" href="' + it.href + '"' + (it.ext ? ' target="_blank" rel="noopener"' : '') +
          (it.hash ? ' data-hash="' + it.hash + '"' : '') + (it.tabHash ? ' data-tab-hash="' + UI.esc(it.tabHash) + '"' : '') + '>' +
          UI.icon(it.icon) + '<span>' + UI.esc(it.label) + '</span></a>') + '</li>').join('');
    const items = () => UI.$$('[role=menuitem]', list);
    const open = on => {
      menu.classList.toggle('hidden', !on); btn.setAttribute('aria-expanded', on);
      if (on) { const cur = items().find(a => a.getAttribute('aria-current')) || items()[0]; if (cur) cur.focus(); }
    };
    btn.addEventListener('click', () => open(menu.classList.contains('hidden')));
    document.addEventListener('click', e => { if (!menu.contains(e.target) && e.target !== btn && !btn.contains(e.target)) open(false); });
    menu.addEventListener('keydown', e => {
      const its = items(), i = its.indexOf(document.activeElement);
      if (e.key === 'ArrowDown') { e.preventDefault(); its[(i + 1) % its.length].focus(); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); its[(i - 1 + its.length) % its.length].focus(); }
      else if (e.key === 'Escape') { e.preventDefault(); open(false); btn.focus(); }
      else if (e.key === 'Tab') open(false);
    });
    list.addEventListener('click', e => {
      const a = e.target.closest('[role=menuitem]'); if (!a) return;
      if (a.dataset.action === 'logout') { open(false); Auth.logout(); return; }
      open(false);
    });
    // Nama pengguna di tray adalah jalan ke "Akun Saya" (tidak lagi menu utama).
    if (me) {
      const label = UI.esc((me.full_name || me.username) + ' · ' + (UI.ROLE_LABEL[me.role_code] || me.role_code));
      const trayEl = UI.$('#trayUser');
      if (Auth.canAny(['account.manage'])) {
        trayEl.innerHTML = '<a href="/app#sistem/akun" title="Akun saya: ubah kata sandi dan token API">' + label + '</a>';
      } else {
        trayEl.textContent = (me.full_name || me.username) + ' · ' + (UI.ROLE_LABEL[me.role_code] || me.role_code);
      }
    } else {
      UI.$('#trayUser').innerHTML = 'Pengunjung · <a href="/masuk">Masuk</a> · <a href="/daftar">Daftar</a>';
    }
    bindBoundaries();
    bindShortcuts();
    tickClock(); setInterval(tickClock, 15000);
    checkHealth(); setInterval(checkHealth, 60000);
  }

  // Alt+1…9 melompat ke tujuan ke-n yang terlihat; Alt+←/→ memutar sub-tab
  // tujuan yang sedang terbuka. Tidak aktif saat fokus ada di kolom isian, dan
  // Alt+Ctrl dilewati karena kombinasi itu adalah AltGr di papan tuts non-US.
  function bindShortcuts() {
    document.addEventListener('keydown', e => {
      if (!e.altKey || e.ctrlKey || e.metaKey) return;
      const el = e.target;
      if (el && /^(INPUT|SELECT|TEXTAREA)$/.test(el.tagName)) return;
      if (/^[1-9]$/.test(e.key)) {
        const r = visibleRoutes()[Number(e.key) - 1]; if (!r) return;
        e.preventDefault();
        // Halaman publik memakai taskbar yang sama tanpa router hash, jadi
        // pintasannya harus memuat /app, bukan hanya mengganti hash.
        location.href = '/app' + canonical(r, visibleTabs(r)[0] || null);
        return;
      }
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
      if (!current || !current.route) return;
      const ts = visibleTabs(current.route);
      const i = ts.indexOf(current.tab);
      if (ts.length < 2 || i < 0) return;
      e.preventDefault();
      location.hash = canonical(current.route, ts[(i + (e.key === 'ArrowRight' ? 1 : ts.length - 1)) % ts.length]);
    });
  }

  // Checkbox "Garis wilayah": satu saklar untuk SEMUA pratinjau citra di
  // aplikasi (tile Live, lightbox, galeri Katalog). Hanya menukar src <img>
  // lewat UI.setBoundaries, jadi halaman yang sedang terbuka tidak dimuat ulang.
  function bindBoundaries() {
    const box = UI.$('#admToggle'); if (!box) return;
    box.checked = UI.boundaries();
    box.addEventListener('change', () => UI.setBoundaries(box.checked));
  }

  function tickClock() {
    const d = new Date();
    UI.$('#utcClock').textContent = String(d.getUTCHours()).padStart(2, '0') + ':' + String(d.getUTCMinutes()).padStart(2, '0') + ' UTC';
  }
  async function checkHealth() {
    let ok = false;
    try { const h = await API.get('/api/health', { noRedirect: true }); ok = !!(h && h.db_connected); } catch (e) { ok = false; }
    healthOk = ok;
    const lamp = UI.$('#linkLamp .lamp');
    lamp.className = 'lamp ' + (ok ? 'ok' : 'fail');
    UI.$('#linkText').textContent = ok ? 'LINK OK' : 'LINK PUTUS';
    UI.$('#linkLamp').title = ok ? 'Server dan basis data terhubung' : 'Server atau basis data tidak terjangkau';
  }

  // "Tujuan › Tab" dipakai di title bar jendela dan di tombol taskbar, supaya
  // keduanya menyebut lokasi yang sama lengkapnya.
  const windowTitle = (route, tab) => route.title + (tab ? ' › ' + tab.title : '');

  function renderTasks() {
    const box = UI.$('#taskButtons'); if (!box) return;
    box.innerHTML = tasks.map(t => {
      const label = windowTitle(t.route, t.tab);
      const on = !!(current && current.route === t.route && current.tab === t.tab);
      return '<button type="button" data-hash="' + UI.esc(canonical(t.route, t.tab).slice(1)) + '"' +
        ' aria-pressed="' + on + '" title="' + UI.esc(label) + '">' +
        UI.icon(t.route.icon) + '<span>' + UI.esc(label) + '</span></button>';
    }).join('');
    UI.$$('button', box).forEach(b => b.addEventListener('click', () => { location.hash = b.dataset.hash; }));
  }

  // ------------------------------------------------------------- menu bar
  // Navigasi yang terlihat tanpa harus membuka tombol Mulai (DESIGN.md §4
  // mengizinkan menu bar di bawah title bar).
  function menubarHTML(route) {
    const rs = visibleRoutes();
    if (rs.length < 2) return '';
    return '<nav class="menubar" aria-label="Menu utama">' + rs.map(r =>
      '<a href="#' + r.hash + '"' + (r === route ? ' aria-current="page"' : '') + '>' + UI.esc(r.title) + '</a>').join('') + '</nav>';
  }

  function subtabsHTML(route, tab) {
    const ts = visibleTabs(route);
    if (ts.length < 2) return '';
    return '<div class="tabs" role="tablist" aria-label="Bagian ' + UI.esc(route.title) + '">' + ts.map(t =>
      '<button type="button" role="tab" data-tab="' + t.key + '" aria-selected="' + (t === tab) + '"' +
      (t === tab ? '' : ' tabindex="-1"') + '>' + UI.esc(t.title) + '</button>').join('') + '</div>';
  }

  const panelHTML = () =>
    '<div id="pageRoot" aria-busy="true">' + UI.screenHTML({ channel: 'SYS', body: UI.loadingHTML() }) + '</div>';

  // ---------------------------------------------------------------- router
  // "#pengaturan/jejak/audit" → { h: 'pengaturan', t: 'jejak', s: 'audit' };
  // hash lama diterjemahkan lewat ALIASES.
  function parseHash() {
    const raw = (location.hash || '').replace(/^#/, '').split('?')[0];
    const parts = raw.split('/');
    let mapped = raw;
    for (let k = parts.length; k > 0; k--) {
      const key = parts.slice(0, k).join('/');
      if (ALIASES[key]) { mapped = [ALIASES[key]].concat(parts.slice(k)).join('/'); break; }
    }
    const out = mapped.split('/');
    return { h: out[0] || '', t: out[1] || '', s: out[2] || '' };
  }
  function findRoute(h) { return ROUTES.find(r => r.hash === h); }
  function defaultRoute() { return visibleRoutes()[0] || ROUTES.find(r => allowed(r)) || ROUTES[0]; }
  // Segmen ketiga hanya ditulis bila segmen tabnya juga tertulis, supaya "sub"
  // tidak pernah bergeser ke posisi tab saat sebagian tab tersembunyi oleh izin.
  function canonical(route, tab, sub) {
    const withTab = !!(tab && visibleTabs(route).length > 1);
    return '#' + route.hash + (withTab ? '/' + tab.key : '') + (withTab && sub ? '/' + sub : '');
  }

  function denied(route) {
    UI.$('#main').innerHTML = UI.windowHTML({
      title: 'Akses ditolak', icon: 'alarm', h: 'h1', cls: 'medium',
      body: '<div class="dialog-msg">' + UI.icon('error32') + '<div class="txt">' + UI.esc(UI.ERROR_TEXT.ROLE_FORBIDDEN) +
        '\nHalaman "' + UI.esc(route.title) + '" tidak tersedia untuk peran ' + UI.esc(UI.ROLE_LABEL[Auth.role()] || Auth.role()) + '.</div></div>' +
        '<div class="btn-row end"><a class="btn default" href="' + canonical(defaultRoute()) + '">OK</a></div>',
      status: '<span>Status: Ditolak (403)</span>',
    });
    renderTasks();
  }

  async function navigate() {
    const parsed = parseHash();
    let route = findRoute(parsed.h);
    if (route && !allowed(route)) {
      // Pengunjung: halaman ini butuh akun, jadi antar ke Masuk dan kembali
      // ke sini sesudahnya. Pengguna yang sudah masuk: perannya kurang.
      if (!Auth.user()) { location.href = Auth.loginUrl('masuk'); return; }
      // Halaman sebelumnya tetap perlu dibereskan (mis. peta Leaflet).
      if (current && current.page && current.page.destroy) { try { current.page.destroy(); } catch (e) { /* abaikan */ } }
      current = null;
      denied(route);
      return;
    }
    if (!route) route = defaultRoute();
    const ts = visibleTabs(route);
    const tab = ts.find(x => x.key === parsed.t) || ts[0] || null;
    const sub = (tab && tab.sub) ? (parsed.s || null) : null;
    const want = canonical(route, tab, sub);
    if ((location.hash || '') !== want) history.replaceState(null, '', want);

    // Pindah bagian di dalam tab yang sama (hanya segmen ketiga yang berubah):
    // halaman menggantinya sendiri lewat onSub, jadi fragmen, peta Leaflet, dan
    // tabel yang sudah dimuat tidak ikut dibuang lalu dimuat ulang.
    if (current && current.route === route && current.tab === tab && current.page && current.page.onSub && UI.$('#pageWindow')) {
      current.sub = sub;
      try { await current.page.onSub(sub); }
      catch (e) { UI.showError('Gagal membuka bagian', e instanceof API.ApiError ? e : String(e.message || e)); }
      return;
    }

    // Pindah tab di dalam tujuan yang sama: cukup ganti panel, jendela tetap.
    const sameRoute = !!(current && current.route === route && UI.$('#pageWindow'));
    if (current && current.page && current.page.destroy) { try { current.page.destroy(); } catch (e) { /* abaikan */ } }
    current = { route: route, tab: tab, sub: sub, page: null };
    document.title = (tab ? tab.title + ' — ' + route.title : route.title) + ' — Orbit-U: The Monitor';

    if (sameRoute) {
      UI.$$('#pageWindow .tabs [role=tab]').forEach(b => {
        const on = b.dataset.tab === (tab && tab.key);
        b.setAttribute('aria-selected', String(on)); b.tabIndex = on ? 0 : -1;
      });
      const ttl = UI.$('#pageWindow .ttl-text h1');
      if (ttl) ttl.textContent = windowTitle(route, tab);
      UI.$('#pageWindow .panel-host').innerHTML = panelHTML();
    } else {
      UI.$('#main').innerHTML = UI.windowHTML({
        title: windowTitle(route, tab), icon: route.icon, h: 'h1', id: 'pageWindow',
        menu: menubarHTML(route),
        body: subtabsHTML(route, tab) +
          '<div class="' + (ts.length > 1 ? 'raised tabpanel ' : '') + 'panel-host"' + (ts.length > 1 ? ' role="tabpanel"' : '') + '>' + panelHTML() + '</div>',
        status: '<span id="pageStatus">Status: Memuat…</span><span class="fit" id="pageRole">' + UI.esc(UI.ROLE_LABEL[Auth.role()] || '') + '</span>',
      });
      if (ts.length > 1) {
        UI.bindTabs(UI.$('#pageWindow .tabs'), key => {
          if (key !== (current.tab && current.tab.key)) location.hash = '#' + route.hash + '/' + key;
        });
      }
    }

    UI.$$('.menubar a').forEach(a => a.toggleAttribute('aria-current', a.getAttribute('href') === '#' + route.hash));
    UI.$$('#startList a[data-hash]').forEach(a => a.toggleAttribute('aria-current', a.dataset.hash === route.hash));
    UI.$$('#startList a[data-tab-hash]').forEach(a => a.toggleAttribute('aria-current', a.dataset.tabHash === route.hash + '/' + (tab ? tab.key : '')));
    // Satu tombol per tujuan+tab: dulu dua tab dari satu tujuan muncul sebagai
    // satu tombol yang selalu tampak "tertekan".
    if (!tasks.some(x => x.route === route && x.tab === tab)) { tasks.push({ route: route, tab: tab }); if (tasks.length > 5) tasks.shift(); }
    renderTasks();

    const file = (tab && tab.file) || route.file;
    const useCss = (tab && tab.css) || route.css;
    if (!file) { setStatus('Tidak tersedia'); return; }
    if (useCss) loadCss(file);
    try {
      const results = await Promise.all([
        fetch('pages/' + file + '.html?v=' + ASSET_V, { cache: 'no-cache' }).then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.text(); }),
        loadScript(file),
      ]);
      if (current.route !== route || current.tab !== tab) return; // pengguna sudah pindah
      const root = UI.$('#pageRoot');
      root.innerHTML = results[0];
      root.removeAttribute('aria-busy');
      const page = window.Pages[file];
      current.page = page;
      const ctx = { me: Auth.user(), route: route, tab: tab, sub: sub, setStatus: setStatus, go: go };
      setStatus('Siap');
      if (page && page.init) await page.init(root, ctx);
    } catch (e) {
      setStatus('Gagal');
      UI.showError('Gagal memuat halaman', e instanceof API.ApiError ? e : String(e.message || e));
    }
  }

  function setStatus(text) { const s = UI.$('#pageStatus'); if (s) s.textContent = 'Status: ' + text; }
  // Dipakai halaman untuk mengantar pengguna ke tujuan/tab lain (mis. tombol
  // "Buat dataset baru" di Katalog) tanpa perlu tahu bentuk hash-nya.
  function go(hash) { location.hash = hash.charAt(0) === '#' ? hash : '#' + hash; }

  // ---------------------------------------------------------------- mount
  async function mountApp() {
    // Aplikasi terbuka untuk pengunjung (M56). requires-auth hanya 'true'
    // untuk pengguna yang sudah masuk, supaya sesi yang kedaluwarsa di tengah
    // jalan mengantar ke /masuk, sedangkan pengunjung tidak pernah dialihkan.
    let me = null;
    try { me = await Auth.load(); } catch (e) { me = null; }
    document.body.dataset.requiresAuth = me ? 'true' : 'false';
    document.body.insertAdjacentHTML('beforeend', taskbarHTML(!me));
    bindTaskbar(me);
    window.addEventListener('hashchange', navigate);
    navigate();
  }

  async function mountPublic(opts) {
    let me = null;
    try { me = await Auth.load(); } catch (e) { me = null; }
    if (opts && opts.redirectIfLoggedIn && me) { location.replace(new URLSearchParams(location.search).get('next') || '/app'); return null; }
    document.body.insertAdjacentHTML('beforeend', taskbarHTML(!me));
    bindTaskbar(me);
    const root = UI.$('#pageRoot');
    const file = opts.file;
    const html = await fetch('pages/' + file + '.html?v=' + ASSET_V, { cache: 'no-cache' }).then(r => r.text());
    root.innerHTML = html;
    await loadScript(file);
    const page = window.Pages[file];
    if (page && page.init) await page.init(root, { me: me, setStatus: setStatus, go: go });
    return me;
  }

  return { mountApp: mountApp, mountPublic: mountPublic, setStatus: setStatus, go: go,
           ROUTES: ROUTES, ALIASES: ALIASES, allowed: allowed, visibleTabs: visibleTabs,
           loadScript: loadScript, loadCss: loadCss, isHealthy: function () { return healthOk; } };
})();
window.Shell = Shell;
