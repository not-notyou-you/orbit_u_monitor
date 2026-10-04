// js/home-public.js — Beranda Publik: GET /api/public/live (scene terbaru tiap Live Area aktif).
'use strict';
Pages['home-public'] = {
  async init(root, ctx) {
    UI.$$('[data-icon]', root).forEach(el => { el.innerHTML = UI.icon(el.dataset.icon); });
    if (ctx.me) {
      UI.$('#iconApp', root).hidden = false; UI.$('#iconLogin', root).hidden = true;
      const b = UI.$('#btnLogin', root); b.textContent = 'Buka aplikasi'; b.href = '/app';
    }
    const deck = UI.$('#homeDeck', root);
    const status = t => { UI.$('#homeStatus', root).textContent = 'Status: ' + t; };
    let items = [];
    try {
      items = (await API.get('/api/public/live')).items || [];
    } catch (e) {
      deck.innerHTML = UI.screenHTML({ channel: 'SYS', rec: '● NO SIGNAL', recCls: 'live', body: UI.emptyHTML('DATA TIDAK DAPAT DIMUAT') });
      status('Gagal memuat'); UI.showError('Gagal memuat kondisi terbaru', e); return;
    }
    if (!items.length) {
      deck.innerHTML = UI.screenHTML({ channel: 'CH-00 · STATUS AREA', rec: '● NO DATA', recCls: 'off',
        body: UI.emptyHTML('BELUM ADA SCENE LIVE YANG SIAP. COBA LAGI NANTI.') });
      status('Belum ada data'); return;
    }
    const sel = UI.$('#areaSelect', root);
    if (items.length > 1) {
      UI.$('#areaBox', root).hidden = false;
      sel.innerHTML = items.map(i => '<option value="' + i.area_id + '">' + UI.esc(i.area_name) + '</option>').join('');
      sel.addEventListener('change', () => render(items.find(i => String(i.area_id) === sel.value)));
    }
    render(items[0]);

    function render(it) {
      const st = it.area_status || {};
      const lv = LiveTiles.levelInfo(st.level);
      deck.innerHTML =
        '<div class="readouts">' +
          UI.readoutHTML('STATUS AREA', UI.esc((st.label || lv.label).toUpperCase()), UI.esc(it.area_name), lv.cls) +
          UI.readoutHTML('SCENE TERAKHIR', UI.esc(UI.date(it.scene_date)), 'SENTINEL-1', 'v-cyan') +
        '</div>' +
        UI.screenHTML({ channel: 'CH-00 · KONDISI', rec: '● LIVE', recCls: 'live',
          body: '<p class="scr-text" style="margin:0"><span class="lbl">STATUS:</span> <b class="' + lv.cls + '">' + UI.esc((st.label || lv.label).toUpperCase()) + '</b> — ' +
            UI.esc(st.text || 'Belum ada kalimat kondisi.') + '</p>' +
            '<p class="scr-text v-dim" style="margin:6px 0 0">' + LiveTiles.sentenceHTML((it.interpretations || {}).gpm_rain_72h) + '</p>' +
            '<p class="lbl" style="margin:6px 0 0">DIPERBARUI: SCENE ' + UI.esc(UI.date(it.scene_date)) + ' · KLIK TILE UNTUK LEGENDA DAN PENJELASAN</p>' }) +
        LiveTiles.rowsHTML(it.previews || {}, it.interpretations || {}, { sceneDate: it.scene_date });
      LiveTiles.bindLightbox(deck, it.previews || {}, it.interpretations || {}, it.scene_date);
      status('Siap · ' + it.area_name + ' · scene ' + UI.date(it.scene_date));
    }
  },
};
