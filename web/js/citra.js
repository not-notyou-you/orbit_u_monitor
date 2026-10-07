// js/citra.js — Citra Satelit › Ringkasan (#citra/ringkasan, INTERFACE.md §2 halaman 3.1, M56).
// Sumber: GET /api/citra/summary. Batas waktu (pengunjung 30 hari, Relawan
// 1 tahun, peran lain semua) dihitung VIEW v_citra_scenes; di sini hanya
// dijelaskan supaya pengguna tahu kenapa daftar tanggalnya sependek itu.
'use strict';
Pages['citra'] = (() => {
  const TAB = { s1: 'sentinel-1', modis: 'modis', gpm: 'gpm' };
  let st = null;

  async function init(root, ctx) {
    st = { root, ctx };
    UI.$('#ciArea', root).addEventListener('change', e => load(Number(e.target.value)));
    await load(CitraState.area());
  }

  async function load(areaId) {
    const $ = s => UI.$(s, st.root);
    st.ctx.setStatus('Memuat…');
    let r;
    try { r = await API.get('/api/citra/summary' + API.qs({ area_id: areaId || '' })); }
    catch (e) { $('#ciCards').innerHTML = UI.emptyHTML('GAGAL MEMUAT'); UI.showError('Citra satelit', e); return; }
    $('#ciWindow').textContent = CitraState.windowText(r.window);
    if (!r.area) {
      $('#ciArea').innerHTML = '';
      $('#ciCards').innerHTML = UI.screenHTML({ channel: 'CITRA', body: UI.emptyHTML('BELUM ADA SCENE YANG SIAP') });
      st.ctx.setStatus('Belum ada citra');
      return;
    }
    CitraState.setArea(r.area.area_id);
    $('#ciArea').innerHTML = r.areas.map(a => '<option value="' + a.area_id + '"' + (a.area_id === r.area.area_id ? ' selected' : '') + '>' +
      UI.esc(a.area_name) + '</option>').join('');
    const s = r.area_status || {}, lv = LiveTiles.levelInfo(s.level);
    $('#ciStatus').innerHTML = UI.screenHTML({ channel: 'CH-00 · ' + r.area.area_name.toUpperCase(), rec: '● ' + UI.int(r.area.n_scenes) + ' SCENE', recCls: 'live',
      body: '<p class="scr-text" style="margin:0"><span class="lbl">STATUS:</span> <b class="' + lv.cls + '">' +
        UI.esc((s.label || lv.label).toUpperCase()) + '</b> — ' + UI.esc(s.text || 'Belum ada kalimat kondisi.') + '</p>' +
        '<p class="lbl" style="margin:6px 0 0">SCENE TERBARU ' + UI.esc(UI.date(r.area.latest_date)) + '</p>' });
    $('#ciCards').innerHTML = r.sources.map(card).join('');
    UI.applyBoundaries(st.root);
    st.ctx.setStatus('Siap · ' + r.area.area_name);
  }

  function card(src) {
    const lt = src.latest || {};
    const img = lt.preview
      ? '<img ' + UI.imgAttrs(lt.preview) + ' alt="' + UI.esc((lt.preview.label || src.label) + ' ' + UI.date(lt.date)) + '" loading="lazy">'
      : '<div class="noimg">' + UI.esc('TIDAK ADA GAMBAR') + '</div>';
    const sentence = Object.values(lt.interpretations || {}).find(x => x && x.text);
    return '<section class="sat-card raised" aria-label="' + UI.esc(src.label) + '">' +
      '<header><b>' + UI.esc(src.label) + '</b><span class="mut">' + UI.esc(src.resolution + ' · ' + src.revisit) + '</span></header>' +
      '<div class="screen"><div class="screen-inner flush sat-thumb">' + img + '</div></div>' +
      '<dl class="kv"><dt>TANGGAL TERSEDIA</dt><dd>' + UI.int(src.n_dates) + '</dd>' +
      '<dt>BERGAMBAR</dt><dd>' + UI.int(src.n_dates_with_images) + '</dd>' +
      '<dt>GAMBAR TERAKHIR</dt><dd>' + UI.esc(src.latest_date ? UI.date(src.latest_date) : UI.NA) + '</dd>' +
      '<dt>TERLAMA</dt><dd>' + UI.esc(src.oldest_date ? UI.date(src.oldest_date) : UI.NA) + '</dd>' +
      (src.key !== 's1' ? '<dt>HARI ANGKA HARIAN</dt><dd>' + UI.int(src.n_obs_days) + '</dd><dt>ANGKA TERAKHIR</dt><dd>' +
        UI.esc(src.latest_obs_date ? UI.date(src.latest_obs_date) : UI.NA) + '</dd>' : '') + '</dl>' +
      (sentence ? '<p class="sat-sentence">' + LiveTiles.sentenceHTML(sentence) + '</p>' : '') +
      '<p class="mut sat-about">' + UI.esc(src.about) + '</p>' +
      '<div class="btn-row end"><a class="btn default" href="#citra/' + TAB[src.key] + '">Buka ' + UI.esc(src.label) + ' →</a></div>' +
      '</section>';
  }

  return { init };
})();
