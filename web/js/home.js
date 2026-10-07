// js/home.js — Beranda (#beranda, INTERFACE.md §2 halaman 1, M56).
//
// Satu halaman untuk semua peran, termasuk pengunjung. Urutannya mengikuti
// rancangan: sambutan → penjelasan → navigasi halaman per peran → peta AOI
// dengan daftar kecamatan. Pengguna yang sudah masuk juga melihat alert hujan
// aktif (dulu di Beranda aplikasi lama), karena itu informasi terpenting.
//
// Hanya membaca. Setiap blok gagal sendiri-sendiri supaya satu endpoint mati
// tidak mengosongkan seluruh beranda.
'use strict';
Pages['home'] = (() => {
  const SEV_RANK = { CRITICAL: 3, WARNING: 2, INFO: 1 };
  let st = null;

  async function init(root, ctx) {
    st = { root, ctx, map: null, layers: {} };
    UI.$$('[data-icon]', root).forEach(el => { el.innerHTML = UI.icon(el.dataset.icon); });
    renderHero(root, ctx.me);
    renderNav(root, ctx.me);
    renderThemes(root);
    const tasks = [renderStrip(root), renderMap(root)];
    if (Auth.can('alerts.view')) tasks.push(renderAlerts(root));
    await Promise.all(tasks);
    ctx.setStatus(ctx.me ? 'Siap · masuk sebagai ' + (ctx.me.full_name || ctx.me.username) : 'Siap · pengunjung');
  }

  function destroy() {
    if (st && st.map) st.map.remove();
    if (st && st.onTheme) document.removeEventListener('orbit-u:tema', st.onTheme);
    st = null;
  }

  // ---------------------------------------------------------------- 1.1
  function renderHero(root, me) {
    const box = UI.$('#hoHeroBtns', root);
    const btns = ['<a class="btn default" href="#citra">Lihat citra satelit</a>'];
    if (me) {
      UI.$('#hoGreeting', root).insertAdjacentHTML('afterbegin',
        '<b>Halo, ' + UI.esc(me.full_name || me.username) + '.</b> ');
    } else {
      btns.push('<a class="btn" href="/masuk?next=' + encodeURIComponent('/app#beranda') + '">Masuk…</a>');
      btns.push('<a class="btn" href="/daftar">Daftar akun</a>');
    }
    box.innerHTML = btns.join('');
  }

  // ---------------------------------------------------------------- 1.3
  // Kartu dirakit dari Shell.ROUTES yang lolos izin peran ini, jadi daftarnya
  // tidak pernah menyimpang dari menu bar dan menu Mulai.
  function renderNav(root, me) {
    const roleLabel = UI.ROLE_LABEL[Auth.role()] || Auth.role();
    UI.$('#hoNavLegend', root).textContent = 'Halaman untuk ' + (me ? roleLabel : 'pengunjung');
    UI.$('#hoNavIntro', root).textContent = me
      ? 'Peran Anda: ' + roleLabel + '. Halaman yang tidak tampil memang bukan untuk peran ini.'
      : 'Anda belum masuk. Halaman di bawah terbuka untuk umum; masuk atau daftar untuk membuka lebih banyak.';
    const cards = [];
    Shell.ROUTES.filter(r => r.hash !== 'beranda' && Shell.allowed(r)).forEach(r => {
      const tabs = Shell.visibleTabs(r);
      const desc = r.desc + (tabs.length > 1 ? ' (' + tabs.map(t => t.title).join(', ') + ')' : '');
      cards.push(card('#' + r.hash, r.icon, r.title, desc));
    });
    if (!me) {
      cards.push(card('/masuk', 'key', 'Masuk', 'Untuk Relawan, Analis, Data Engineer, dan Administrator.'));
      cards.push(card('/daftar', 'user', 'Daftar akun Relawan',
        'Gratis: citra satelit setahun ke belakang, 3D AOI, seluruh riwayat kejadian, angka hujan per kecamatan.'));
    }
    cards.push(card('/docs', 'help', 'Dokumentasi API', 'Skema endpoint publik dan ber-token (Swagger).', true));
    UI.$('#hoNav', root).innerHTML = cards.join('');
  }

  function card(href, icon, title, desc, ext) {
    return '<a class="navcard" href="' + href + '"' + (ext ? ' target="_blank" rel="noopener"' : '') + '>' +
      UI.icon(icon) + '<span class="nc-body"><span class="nc-title">' + UI.esc(title) + '</span>' +
      '<span class="nc-desc">' + UI.esc(desc) + '</span></span></a>';
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

  // ---------------------------------------------------------- strip status
  async function renderStrip(root) {
    const strip = UI.$('#hoStrip .screen-inner', root);
    const line = html => { strip.innerHTML = '<p class="hs-line">' + html + '</p>'; };
    let items;
    try { items = (await API.get('/api/public/live')).items || []; }
    catch (e) { line('<span class="lbl">STATUS AREA:</span> <span class="v-alert">TIDAK DAPAT DIMUAT</span>'); return; }
    if (!items.length) { line('<span class="lbl">STATUS AREA:</span> <span class="v-dim">BELUM ADA SCENE SIAP</span>'); return; }
    const it = items[0], s = it.area_status || {}, lv = LiveTiles.levelInfo(s.level);
    line('<span class="lbl">STATUS AREA:</span> <b class="' + lv.cls + '">' + UI.esc((s.label || lv.label).toUpperCase()) + '</b> ' +
      '<span class="v-dim">· ' + UI.esc(it.area_name) + (items.length > 1 ? ' +' + (items.length - 1) + ' area lain' : '') +
      ' · SCENE ' + UI.esc(UI.date(it.scene_date)) + '</span>' +
      '<a class="hs-more" href="#citra">Citra satelit →</a>');
  }

  // ------------------------------------------------------------ alert aktif
  async function renderAlerts(root) {
    const box = UI.$('#hoAlerts', root);
    // "Aktif" di Beranda = belum ditandai dibaca DAN dari 7 hari terakhir.
    // Backfill hidromet menghasilkan ratusan alert historis yang belum dibaca;
    // itu bukan keadaan sekarang, jadi hanya disebut jumlahnya.
    let alerts, older = 0;
    const since = UI.addDays(UI.isoDate(new Date()), -7);
    try {
      const [recent, all] = await Promise.all([API.get('/api/alerts' + API.qs({ status: 'active', date_from: since, limit: 200 })),
        API.get('/api/alerts?status=active&limit=1')]);
      alerts = recent.items || [];
      older = Math.max(0, (all.total || 0) - (recent.total || 0));
    }
    catch (e) {
      box.innerHTML = '<div class="banner raised" role="note">' + UI.icon('warn32') +
        '<div class="b-body"><b>Daftar alert tidak dapat dimuat.</b> Periksa status LINK di taskbar.</div></div>';
      return;
    }
    const olderNote = older ? '<p class="scr-text v-dim" style="margin:6px 0 0">' + UI.int(older) +
      ' alert lebih lama dari 7 hari (mis. hasil backfill) belum ditandai dibaca — lihat Citra › GPM.</p>' : '';
    if (!alerts.length) {
      box.innerHTML = UI.screenHTML({ channel: 'CH-02 · ALERT 7 HARI TERAKHIR', rec: '● NOMINAL', recCls: 'live',
        body: '<p class="scr-text" style="margin:0">TIDAK ADA ALERT HUJAN DALAM 7 HARI TERAKHIR.</p>' +
          '<p class="scr-text v-dim" style="margin:6px 0 0">Tidak adanya alert bukan jaminan kondisi aman. Alert hanya dihitung untuk tanggal yang sudah diolah Job Hidromet.</p>' + olderNote });
      return;
    }
    const byRegion = {};
    alerts.forEach(a => { (byRegion[a.region_id] = byRegion[a.region_id] || []).push(a); });
    const groups = Object.values(byRegion)
      .map(list => list.slice().sort((x, y) => SEV_RANK[y.severity] - SEV_RANK[x.severity]))
      .sort((x, y) => SEV_RANK[y[0].severity] - SEV_RANK[x[0].severity]);
    const worst = groups[0][0].severity;
    box.innerHTML = '<div class="banner raised" role="alert">' +
      UI.icon(worst === 'INFO' ? 'info32' : worst === 'CRITICAL' ? 'error32' : 'warn32') +
      '<div class="b-body"><b>' + UI.int(groups.length) + ' kecamatan dengan alert hujan 7 hari terakhir</b> — tertinggi: ' +
      UI.esc(UI.SEVERITY[worst].label) + '.' +
      '<div class="screen" style="margin-top:6px"><div class="screen-inner"><span class="scr-ch">ALERT AKTIF</span>' +
      UI.tableHTML([
        { label: 'Kecamatan', get: g => g[0].region_name },
        { label: 'Tingkat', html: true, get: g => '<span class="' + UI.SEVERITY[g[0].severity].cls + '">' + UI.esc(UI.SEVERITY[g[0].severity].label.toUpperCase()) + '</span>' },
        { label: 'Tanggal', get: g => UI.date(g[0].observation_date) },
        { label: 'Nilai', cls: 'r', get: g => UI.num(g[0].observed_value, 1) + ' mm ≥ ' + UI.num(g[0].threshold_value, 0) },
      ], groups.slice(0, 5), { caption: 'Alert hujan aktif per kecamatan' }) + '</div></div>' +
      olderNote + '<p style="margin:6px 0 0"><a href="#citra/gpm">Buka Citra › GPM</a>' +
      (Auth.can('alerts.acknowledge') ? ' untuk menandai sudah dibaca.' : ' untuk seluruh daftar per kecamatan.') +
      '</p></div></div>';
  }

  // ------------------------------------------------------------------ 1.4
  async function renderMap(root) {
    const list = UI.$('#hoRegions', root);
    let geo;
    try { geo = await Maps.regions(); }
    catch (e) { list.innerHTML = UI.emptyHTML('DAFTAR KECAMATAN GAGAL DIMUAT'); return; }
    const feats = geo.features.slice().sort((a, b) => a.properties.name.localeCompare(b.properties.name, 'id'));
    const total = feats.reduce((sum, f) => sum + (f.properties.area_km2 || 0), 0);
    UI.$('#hoRegionsSum', root).textContent = UI.int(feats.length) + ' kecamatan · ' + UI.num(total, 0) + ' km² (luas dari COD-AB BPS).';
    UI.$('#hoMapRec', root).textContent = UI.int(feats.length) + ' KECAMATAN';
    list.innerHTML = feats.map(f => '<button type="button" role="option" data-rid="' + f.properties.region_id + '">' +
      UI.esc(f.properties.name) + ' <span class="sub">' + UI.num(f.properties.area_km2, 0) + ' km²</span></button>').join('') ||
      UI.emptyHTML('AOI BELUM DIATUR');
    st.map = Maps.create(UI.$('#hoMap', root));
    if (!st.map || !feats.length) return;
    const base = { color: '#33ff99', weight: 1, fillOpacity: 0.12 };
    const layer = L.geoJSON(geo, {
      style: () => base,
      onEachFeature: (f, l) => {
        st.layers[f.properties.region_id] = l;
        l.bindTooltip(UI.esc(f.properties.name), { sticky: true });
      },
    }).addTo(st.map);
    setTimeout(() => { if (st && st.map) { st.map.invalidateSize(); st.map.fitBounds(layer.getBounds()); } }, 100);
    UI.$$('button[data-rid]', list).forEach(b => b.addEventListener('click', () => {
      Object.values(st.layers).forEach(l => l.setStyle(base));
      UI.$$('button[data-rid]', list).forEach(x => x.setAttribute('aria-selected', String(x === b)));
      const l = st.layers[b.dataset.rid];
      if (l) { l.setStyle({ color: '#ffb000', weight: 3, fillOpacity: 0.3 }); st.map.fitBounds(l.getBounds(), { maxZoom: 12 }); l.openTooltip(); }
    }));
  }

  return { init, destroy };
})();
