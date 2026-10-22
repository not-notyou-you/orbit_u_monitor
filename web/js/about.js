// js/about.js — Tentang (#tentang, INTERFACE.md §2 halaman 1b, M63).
//
// Isi Beranda sebelum M63 dipindah ke sini: sambutan → penjelasan → kartu
// halaman per peran → peta AOI dengan daftar kecamatan (tema tampilan
// pindah ke Beranda),
// ditambah isi Sistem › Tentang lama (versi API dan status basis data dari
// GET /api/health, sumber data, tabel akses per peran untuk Administrator).
// Alert hujan aktif tidak di sini lagi: Beranda (Pantau Lokasi) menandainya
// per kecamatan.
//
// Hanya membaca. Setiap blok gagal sendiri-sendiri supaya satu endpoint mati
// tidak mengosongkan seluruh halaman.
'use strict';
Pages['about'] = (() => {
  let st = null;

  async function init(root, ctx) {
    st = { root, ctx, map: null, layers: {} };
    UI.$$('[data-icon]', root).forEach(el => { el.innerHTML = UI.icon(el.dataset.icon); });
    // Tabel akses per peran hanya untuk Administrator.
    UI.$('#abRoles', root).hidden = Auth.role() !== 'ADMIN';
    renderHero(root, ctx.me);
    renderNav(root, ctx.me);
    await Promise.all([renderStrip(root), renderMap(root), renderInfo(root)]);
    ctx.setStatus(ctx.me ? 'Siap · masuk sebagai ' + (ctx.me.full_name || ctx.me.username) : 'Siap · pengunjung');
  }

  function destroy() {
    if (st && st.map) st.map.remove();
    st = null;
  }

  // ------------------------------------------------------------- sambutan
  function renderHero(root, me) {
    const box = UI.$('#abHeroBtns', root);
    const btns = ['<a class="btn default" href="#beranda">Pantau lokasi</a>', '<a class="btn" href="#citra">Lihat citra satelit</a>'];
    if (me) {
      UI.$('#abGreeting', root).insertAdjacentHTML('afterbegin',
        '<b>Halo, ' + UI.esc(me.full_name || me.username) + '.</b> ');
    } else {
      btns.push('<a class="btn" href="/masuk?next=' + encodeURIComponent('/app#tentang') + '">Masuk…</a>');
      btns.push('<a class="btn" href="/daftar">Daftar akun</a>');
    }
    box.innerHTML = btns.join('');
  }

  // ------------------------------------------------- navigasi per peran
  // Kartu dirakit dari Shell.ROUTES yang lolos izin peran ini, jadi daftarnya
  // tidak pernah menyimpang dari menu bar dan menu Mulai.
  function renderNav(root, me) {
    const roleLabel = UI.ROLE_LABEL[Auth.role()] || Auth.role();
    UI.$('#abNavLegend', root).textContent = 'Halaman untuk ' + (me ? roleLabel : 'pengunjung');
    UI.$('#abNavIntro', root).textContent = me
      ? 'Peran Anda: ' + roleLabel + '. Halaman yang tidak tampil memang bukan untuk peran ini.'
      : 'Anda belum masuk. Halaman di bawah terbuka untuk umum; masuk atau daftar untuk membuka lebih banyak.';
    const cards = [];
    Shell.ROUTES.filter(r => r.hash !== 'tentang' && Shell.allowed(r)).forEach(r => {
      const tabs = Shell.visibleTabs(r);
      const desc = r.desc + (tabs.length > 1 ? ' (' + tabs.map(t => t.title).join(', ') + ')' : '');
      cards.push(card('#' + r.hash, r.icon, r.title, desc));
    });
    if (!me) {
      cards.push(card('/masuk', 'key', 'Masuk', 'Untuk Relawan, Analis, Data Engineer, dan Administrator.'));
      cards.push(card('/daftar', 'user', 'Daftar akun Relawan',
        'Gratis: Lokasi saya di Beranda, citra satelit setahun ke belakang, 3D AOI, seluruh riwayat kejadian, angka hujan per kecamatan.'));
    }
    cards.push(card('/docs', 'help', 'Dokumentasi API', 'Skema endpoint publik dan ber-token (Swagger).', true));
    UI.$('#abNav', root).innerHTML = cards.join('');
  }

  function card(href, icon, title, desc, ext) {
    return '<a class="navcard" href="' + href + '"' + (ext ? ' target="_blank" rel="noopener"' : '') + '>' +
      UI.icon(icon) + '<span class="nc-body"><span class="nc-title">' + UI.esc(title) + '</span>' +
      '<span class="nc-desc">' + UI.esc(desc) + '</span></span></a>';
  }

  // ---------------------------------------------------------- strip status
  async function renderStrip(root) {
    const strip = UI.$('#abStrip .screen-inner', root);
    const line = html => { strip.innerHTML = '<p class="hs-line">' + html + '</p>'; };
    let items;
    try { items = (await API.get('/api/public/live')).items || []; }
    catch (e) { line('<span class="lbl">STATUS AREA:</span> <span class="v-alert">TIDAK DAPAT DIMUAT</span>'); return; }
    if (!items.length) { line('<span class="lbl">STATUS AREA:</span> <span class="v-dim">BELUM ADA SCENE SIAP</span>'); return; }
    const it = items[0], s = it.area_status || {}, lv = LiveTiles.levelInfo(s.level);
    line('<span class="lbl">STATUS AREA:</span> <b class="' + lv.cls + '">' + UI.esc((s.label || lv.label).toUpperCase()) + '</b> ' +
      '<span class="v-dim">· ' + UI.esc(it.area_name) + (items.length > 1 ? ' +' + (items.length - 1) + ' area lain' : '') +
      ' · SCENE ' + UI.esc(UI.date(it.scene_date)) + '</span>' +
      '<a class="hs-more" href="#beranda">Pantau per kecamatan →</a>');
  }

  // ------------------------------------------------------ peta AOI
  async function renderMap(root) {
    const list = UI.$('#abRegions', root);
    let geo;
    try { geo = await Maps.regions(); }
    catch (e) { list.innerHTML = UI.emptyHTML('DAFTAR KECAMATAN GAGAL DIMUAT'); return; }
    const feats = geo.features.slice().sort((a, b) => a.properties.name.localeCompare(b.properties.name, 'id'));
    const total = feats.reduce((sum, f) => sum + (f.properties.area_km2 || 0), 0);
    UI.$('#abRegionsSum', root).textContent = UI.int(feats.length) + ' kecamatan · ' + UI.num(total, 0) + ' km² (luas dari COD-AB BPS).';
    UI.$('#abMapRec', root).textContent = UI.int(feats.length) + ' KECAMATAN';
    list.innerHTML = feats.map(f => '<button type="button" role="option" data-rid="' + f.properties.region_id + '">' +
      UI.esc(f.properties.name) + ' <span class="sub">' + UI.num(f.properties.area_km2, 0) + ' km²</span></button>').join('') ||
      UI.emptyHTML('AOI BELUM DIATUR');
    if (!st) return;
    st.map = Maps.create(UI.$('#abMap', root));
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

  // ------------------------------------------------------ info aplikasi
  async function renderInfo(root) {
    const box = UI.$('#abInfo', root);
    const rows = [['PERAN ANDA', UI.ROLE_LABEL[Auth.role()] || Auth.role()]];
    try {
      const h = await API.get('/api/health', { noRedirect: true });
      rows.push(['STATUS SERVER', h.db_connected ? 'Terhubung' : 'Basis data tidak terjangkau']);
      if (h.version) rows.push(['VERSI API', h.version]);
    } catch (e) { rows.push(['STATUS SERVER', 'Tidak terjangkau']); }
    rows.push(['DOKUMENTASI API', '/docs']);
    box.innerHTML = rows.map(([k, v]) => '<dt>' + UI.esc(k) + '</dt><dd>' + (v === '/docs'
      ? '<a href="/docs" target="_blank" rel="noopener">/docs (Swagger)</a>' : UI.esc(v)) + '</dd>').join('');
  }

  return { init, destroy };
})();
