// web/js/app.js — kerangka "desktop" Orbital 95: router hash, jendela utama, taskbar.
// /app#<halaman> memuat fragmen pages/<berkas>.html ke jendela utama dan
// skrip js/<berkas>.js (sekali), lalu memanggil Pages[<berkas>].init(root, ctx).
// Halaman publik (/ dan /masuk) memakai Shell.mountPublic dengan taskbar yang sama.
'use strict';

window.Pages = window.Pages || {};
const ASSET_V = '4.0';

const ROUTES = [
  { hash: 'pantauan', file: 'monitoring', title: 'Pantauan Live', icon: 'satellite', perm: ['live.recent'], css: true },
  { hash: 'hari-ini', alias: ['statistik'], file: 'statistics', title: 'Statistik Hari Ini', icon: 'drop', perm: ['hydromet.today'] },
  { hash: 'analitik', file: 'analytics', title: 'Analitik', icon: 'chart', perm: ['analytics.view'] },
  { hash: 'kejadian', file: 'disasters', title: 'Kejadian Bencana', icon: 'alarm', perm: ['disasters.manage'] },
  { hash: 'katalog', file: 'catalog', title: 'Katalog Dataset', icon: 'folder', perm: ['datasets.manage'], css: true },
  { hash: 'buat-dataset', file: 'create-dataset', title: 'Buat Dataset', icon: 'disk', perm: ['datasets.manage'], css: true },
  { hash: 'laporan', file: 'reports', title: 'Laporan', icon: 'doc', perm: ['reports.hydromet', 'reports.datahealth'] },
  { hash: 'admin', file: 'admin', title: 'Administrasi', icon: 'gear', perm: ['admin.system'] },
  { hash: 'akun', file: 'account', title: 'Akun Saya', icon: 'user', perm: ['account.manage'] },
];

const Shell = (() => {
  const loadedScripts = {};
  const loadedCss = {};
  let current = null;       // { route, page }
  const tasks = [];         // halaman yang pernah dibuka sesi ini (tombol taskbar)
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

  // ---------------------------------------------------------------- taskbar
  function taskbarHTML(publicMode) {
    return '<nav class="taskbar" aria-label="Taskbar">' +
      '<button type="button" class="start" id="startBtn" aria-haspopup="menu" aria-expanded="false" aria-controls="startMenu">' + UI.icon('satellite') + '<span>Mulai</span></button>' +
      '<div class="task-buttons" id="taskButtons" role="toolbar" aria-label="Jendela terbuka"></div>' +
      '<div class="tray" role="status" aria-live="off">' +
        '<span class="lamp-row" id="linkLamp" title="Status tautan server"><i class="lamp" aria-hidden="true"></i><span id="linkText">LINK ?</span></span>' +
        '<span class="tray-extra" id="trayUser">' + (publicMode ? 'Pengunjung' : '') + '</span>' +
        '<time id="utcClock" class="num" title="Waktu UTC"></time>' +
      '</div></nav>' +
      '<div class="start-menu raised hidden" id="startMenu" role="menu" aria-label="Menu Mulai"><div class="side" aria-hidden="true">ORBIT-U 95</div><ul id="startList"></ul></div>';
  }

  function menuItems(me) {
    const items = [{ href: '/', label: 'Beranda Publik', icon: 'globe' }];
    if (!me) {
      items.push({ href: '/masuk', label: 'Masuk…', icon: 'key' });
    } else {
      ROUTES.filter(r => Auth.canAny(r.perm)).forEach(r => items.push({ href: '/app#' + r.hash, label: r.title, icon: r.icon, hash: r.hash }));
    }
    items.push({ sep: true });
    items.push({ href: '/docs', label: 'Dokumentasi API', icon: 'help', ext: true });
    if (me) items.push({ action: 'logout', label: 'Keluar', icon: 'door' });
    return items;
  }

  function bindTaskbar(me) {
    const btn = UI.$('#startBtn'), menu = UI.$('#startMenu'), list = UI.$('#startList');
    list.innerHTML = menuItems(me).map(it => it.sep ? '<li role="separator"><hr></li>' :
      '<li role="none">' + (it.action
        ? '<button type="button" role="menuitem" data-action="' + it.action + '">' + UI.icon(it.icon) + '<span>' + UI.esc(it.label) + '</span></button>'
        : '<a role="menuitem" href="' + it.href + '"' + (it.ext ? ' target="_blank" rel="noopener"' : '') + (it.hash ? ' data-hash="' + it.hash + '"' : '') + '>' + UI.icon(it.icon) + '<span>' + UI.esc(it.label) + '</span></a>') + '</li>').join('');
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
    if (me) UI.$('#trayUser').textContent = (me.full_name || me.username) + ' · ' + (UI.ROLE_LABEL[me.role_code] || me.role_code);
    tickClock(); setInterval(tickClock, 15000);
    checkHealth(); setInterval(checkHealth, 60000);
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

  function renderTasks() {
    const box = UI.$('#taskButtons'); if (!box) return;
    box.innerHTML = tasks.map(r => '<button type="button" data-hash="' + r.hash + '" aria-pressed="' + (current && current.route === r) + '" title="' + UI.esc(r.title) + '">' +
      UI.icon(r.icon) + '<span>' + UI.esc(r.title) + '</span></button>').join('');
    UI.$$('button', box).forEach(b => b.addEventListener('click', () => { location.hash = b.dataset.hash; }));
  }

  // ---------------------------------------------------------------- router
  function findRoute(hash) {
    const h = (hash || '').replace(/^#/, '').split('?')[0];
    return ROUTES.find(r => r.hash === h || (r.alias || []).includes(h));
  }
  function defaultRoute() { return ROUTES.find(r => Auth.canAny(r.perm)) || ROUTES[ROUTES.length - 1]; }

  async function navigate() {
    const main = UI.$('#main');
    let route = findRoute(location.hash);
    if (!route) { route = defaultRoute(); history.replaceState(null, '', '#' + route.hash); }
    if (current && current.page && current.page.destroy) { try { current.page.destroy(); } catch (e) { /* abaikan */ } }
    current = { route, page: null };
    document.title = route.title + ' — Orbit-U: The Monitor';
    UI.$$('#startList a[data-hash]').forEach(a => a.toggleAttribute('aria-current', a.dataset.hash === route.hash));

    if (!Auth.canAny(route.perm)) {
      main.innerHTML = UI.windowHTML({ title: 'Akses ditolak', icon: 'alarm', h: 'h1', cls: 'medium',
        body: '<div class="dialog-msg">' + UI.icon('error32') + '<div class="txt">' + UI.esc(UI.ERROR_TEXT.ROLE_FORBIDDEN) +
          '\nHalaman "' + UI.esc(route.title) + '" tidak tersedia untuk peran ' + UI.esc(UI.ROLE_LABEL[Auth.role()] || Auth.role()) + '.</div></div>' +
          '<div class="btn-row end"><a class="btn default" href="#' + defaultRoute().hash + '">OK</a></div>',
        status: '<span>Status: Ditolak (403)</span>' });
      renderTasks();
      return;
    }
    if (!tasks.includes(route)) { tasks.push(route); if (tasks.length > 5) tasks.shift(); }
    renderTasks();
    main.innerHTML = UI.windowHTML({ title: route.title, icon: route.icon, h: 'h1', id: 'pageWindow',
      body: '<div id="pageRoot" aria-busy="true">' + UI.screenHTML({ channel: 'SYS', body: UI.loadingHTML() }) + '</div>',
      status: '<span id="pageStatus">Status: Memuat…</span><span class="fit" id="pageRole">' + UI.esc(UI.ROLE_LABEL[Auth.role()] || '') + '</span>' });
    if (route.css) loadCss(route.file);
    try {
      const [html] = await Promise.all([
        fetch('pages/' + route.file + '.html?v=' + ASSET_V, { cache: 'no-cache' }).then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.text(); }),
        loadScript(route.file),
      ]);
      if (current.route !== route) return; // pengguna sudah pindah halaman
      const root = UI.$('#pageRoot');
      root.innerHTML = html;
      root.removeAttribute('aria-busy');
      const page = window.Pages[route.file];
      current.page = page;
      const ctx = { me: Auth.user(), route, setStatus };
      setStatus('Siap');
      if (page && page.init) await page.init(root, ctx);
    } catch (e) {
      setStatus('Gagal');
      UI.showError('Gagal memuat halaman', e instanceof API.ApiError ? e : String(e.message || e));
    }
  }

  function setStatus(text) { const s = UI.$('#pageStatus'); if (s) s.textContent = 'Status: ' + text; }

  // ---------------------------------------------------------------- mount
  async function mountApp() {
    document.body.dataset.requiresAuth = 'true';
    const me = await Auth.require();
    document.body.insertAdjacentHTML('beforeend', taskbarHTML(false));
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
    if (page && page.init) await page.init(root, { me, setStatus });
    return me;
  }

  return { mountApp, mountPublic, setStatus, ROUTES, isHealthy: () => healthOk };
})();
window.Shell = Shell;
