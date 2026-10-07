// js/landing.js — Beranda publik (`/`), INTERFACE.md §2.1.
//
// Halaman sambutan, bukan monitor. Urutannya sambutan → penjelasan → navigasi
// halaman: pengunjung baru perlu tahu dulu ini apa dan apa batasannya sebelum
// melihat angka. Tile satelit ada di halaman tersendiri `/kondisi` (§2.2); di
// sini hanya strip satu baris status area sebagai pengantar ke sana.
//
// Sumber strip: GET /api/public/live (area pertama). Kartu menu dirakit dari
// Shell.ROUTES yang lolos izin Auth, jadi daftarnya tidak pernah menyimpang
// dari menu bar dan menu Mulai di dalam aplikasi; izin tetap dari
// GET /api/auth/me, dan API/DB tetap menegakkan akses.
'use strict';
Pages['landing'] = {
  async init(root, ctx) {
    UI.$$('[data-icon]', root).forEach(el => { el.innerHTML = UI.icon(el.dataset.icon); });
    const status = t => { UI.$('#landingStatus', root).textContent = 'Status: ' + t; };
    const me = ctx.me;

    if (me) {
      UI.$('#iconApp', root).hidden = false;
      UI.$('#iconLogin', root).hidden = true;
      const b = UI.$('#btnPrimary', root);
      b.textContent = 'Buka aplikasi'; b.href = '/app';
    }

    renderMenu(root, me);
    status(me ? 'Siap · masuk sebagai ' + (me.full_name || me.username) : 'Siap · pengunjung');
    await renderStrip(root, status);
  },
};

// ------------------------------------------------------------------ menu peran
function card(href, icon, title, desc, ext) {
  return '<a class="navcard" href="' + href + '"' + (ext ? ' target="_blank" rel="noopener"' : '') + '>' +
    UI.icon(icon) + '<span class="nc-body"><span class="nc-title">' + UI.esc(title) + '</span>' +
    '<span class="nc-desc">' + UI.esc(desc) + '</span></span></a>';
}

function renderMenu(root, me) {
  const legend = UI.$('#menuLegend', root);
  const intro = UI.$('#menuIntro', root);
  const box = UI.$('#navCards', root);
  const cards = [];

  if (!me) {
    legend.textContent = 'Menu';
    intro.textContent = 'Anda belum masuk. Bagian di bawah terbuka untuk umum; halaman lain terbuka setelah masuk.';
    // Pengguna yang sudah masuk tidak diberi kartu ini: mereka punya kartu
    // "Kondisi" milik aplikasi, yang isinya lebih lengkap (30 hari + prakiraan).
    cards.push(card('/kondisi', 'monitor', 'Kondisi terkini',
      'Status area dan tile satelit terbaru. Tanpa login.'));
    cards.push(card('/relief', 'satellite', 'Relief 3D',
      'Citra terbaru ditempel di atas model elevasi, bisa dimiringkan dan diputar. Relief dari DEM, bukan dari radar.'));
    cards.push(card('/masuk', 'key', 'Masuk', 'Gunakan akun yang diberikan Admin GMLS.'));
    cards.push(card('/docs', 'help', 'Dokumentasi API', 'Skema endpoint publik dan ber-token (Swagger).', true));
    UI.$('#rolesBox', root).hidden = false;
  } else {
    const roleLabel = UI.ROLE_LABEL[me.role_code] || me.role_code;
    legend.textContent = 'Menu untuk ' + roleLabel;
    intro.textContent = 'Halaman yang tersedia untuk peran ' + roleLabel + '. Menu yang sama ada di dalam aplikasi, di menu bar dan tombol Mulai.';
    Shell.ROUTES.filter(r => Auth.canAny(r.perm)).forEach(r => {
      cards.push(card('/app#' + r.hash, r.icon, r.title, r.desc || ''));
    });
    cards.push(card('/docs', 'help', 'Dokumentasi API', 'Skema endpoint dan token API Anda (Swagger).', true));
  }
  box.innerHTML = cards.join('');
}

// ------------------------------------------------------------- strip status
// Strip satu baris di bawah hero: status area terbaru + tanggal scene, dengan
// tautan ke `/kondisi`. Beranda sengaja tidak memuat tile — itu pekerjaan
// halaman Kondisi Terkini (§2.2).
async function renderStrip(root, status) {
  const strip = UI.$('#heroStrip .screen-inner', root);
  const line = html => { strip.innerHTML = '<p class="hs-line">' + html + '</p>'; };

  let items = [];
  try {
    items = (await API.get('/api/public/live')).items || [];
  } catch (e) {
    // Beranda tetap berguna tanpa data: sambutan, penjelasan, dan menu utuh.
    line('<span class="lbl">STATUS AREA:</span> <span class="v-alert">TIDAK DAPAT DIMUAT</span>' +
      '<a class="hs-more" href="/kondisi">Coba halaman Kondisi →</a>');
    status('Kondisi terkini gagal dimuat');
    return;
  }
  if (!items.length) {
    line('<span class="lbl">STATUS AREA:</span> <span class="v-dim">BELUM ADA SCENE SIAP</span>' +
      '<a class="hs-more" href="/kondisi">Kondisi terkini →</a>');
    return;
  }

  const it = items[0];
  const st = it.area_status || {};
  const lv = LiveTiles.levelInfo(st.level);
  const extra = items.length > 1 ? ' +' + (items.length - 1) + ' area lain' : '';
  line('<span class="lbl">STATUS AREA:</span> ' +
    '<b class="' + lv.cls + '">' + UI.esc((st.label || lv.label).toUpperCase()) + '</b> ' +
    '<span class="v-dim">· ' + UI.esc(it.area_name) + UI.esc(extra) +
    ' · SCENE ' + UI.esc(UI.date(it.scene_date)) + '</span>' +
    '<a class="hs-more" href="/kondisi">Kondisi terkini →</a>');
}
