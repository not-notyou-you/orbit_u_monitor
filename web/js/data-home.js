// js/data-home.js — Data › Ringkasan (#data/ringkasan, INTERFACE.md §2 halaman 6.1, M56, M67, M74).
// Baris status dan bagian "sedang berjalan" diisi js/process.js (dimuat di
// sini dengan fragmen yang sama). Halaman ini sendiri mengisi tabel dataset
// utama per satelit dari GET /api/data/summary + /api/data/activity.
//
// M74: tiga kartu satelit, dua kotak dataset utama, dan tabel "backfill
// terakhir" diganti satu tabel tiga baris. Rincian per tanggal dan per item
// tetap di Data › Satelit (tombol Kelola →).
'use strict';
Pages['data-home'] = (() => {
  const TAB = { s1: 'sentinel-1', modis: 'modis', gpm: 'gpm' };
  const LIVE = { BACKFILLING: 'MENGISI RIWAYAT', RUNNING: 'MEMERIKSA SCENE BARU', WAITING: 'MENUNGGU GILIRAN', ACTIVE: 'SIAGA', ERROR: 'GALAT' };
  let st = null;

  async function init(root, ctx) {
    st = { root, ctx, timer: null, proc: false };
    await Promise.all([load(), mountProcess()]);
    st.timer = setInterval(load, 15000);
  }
  function destroy() {
    if (st && st.timer) clearInterval(st.timer);
    if (st && st.proc && Pages.process && Pages.process.destroy) { try { Pages.process.destroy(); } catch (e) { /* abaikan */ } }
    st = null;
  }

  async function mountProcess() {
    try { await Shell.loadScript('process'); } catch (e) { UI.$('#pcStatus', st.root).textContent = 'Status proses gagal dimuat.'; return; }
    if (!st) return;
    st.proc = true;
    await Pages.process.init(st.root, st.ctx);
  }

  // Status proses tiap satelit: Sentinel-1 dari siklus Live, MODIS/GPM dari Job Hidromet.
  function procOf(s, a) {
    if (s.backfill_running) return ['BACKFILL BERJALAN', 'v-cyan'];
    if (!a) return [UI.NA, ''];
    if (s.key === 's1') {
      const l = (a.live || [])[0];
      if (!l) return ['BELUM ADA LIVE AREA', 'v-amber'];
      return [(LIVE[l.status] || l.status) + (l.running ? '' : ' · 01, 07, 13, 19 WIB'), l.status === 'ERROR' ? 'v-alert' : l.running ? 'v-cyan' : ''];
    }
    const h = a.hydromet || {};
    return h.locked ? ['JOB HIDROMET BERJALAN', 'v-cyan'] : ['SIAGA · HARIAN 02.00 WIB', ''];
  }

  async function load() {
    if (!st) return;
    const $ = s => UI.$(s, st.root);
    let r, a;
    try { [r, a] = await Promise.all([API.get('/api/data/summary'), API.get('/api/data/activity').catch(() => null)]); }
    catch (e) { if (st && !st.loaded) { $('#dhTable').innerHTML = UI.emptyHTML('GAGAL MEMUAT'); UI.showError('Data', e); } return; }
    if (!st) return;
    st.loaded = true;
    $('#dhRec').textContent = UI.int(r.sources.length) + ' SATELIT';
    $('#dhTable').innerHTML = UI.tableHTML([
      { label: 'Satelit', html: true, get: s => '<b>' + UI.esc(s.label) + '</b>' },
      { label: 'Rentang data', get: s => s.first_date ? UI.date(s.first_date, 'short') + ' – ' + UI.date(s.last_date, 'short') : UI.NA },
      { label: 'Hari data', cls: 'r', get: s => UI.int(s.n_days) + (s.key !== 's1' ? ' (' + UI.int(s.obs_days) + ' berangka kec.)' : '') },
      { label: 'Item aktif', cls: 'r', html: true, get: s => UI.int(s.n_valid) + ' / ' + UI.int(s.n_total) +
        (s.n_invalid ? ' <span class="v-amber">(' + UI.int(s.n_invalid) + ' nonaktif)</span>' : '') },
      { label: 'Masuk terakhir', get: s => s.last_ingested_at ? UI.dateTime(s.last_ingested_at) : UI.NA },
      { label: 'Proses', html: true, get: s => { const p = procOf(s, a); return '<span class="' + p[1] + '">' + UI.esc(p[0]) + '</span>'; } },
      { label: '', cls: 'r', html: true, get: s => '<a class="btn small" href="#data/satelit/' + TAB[s.key] + '">Kelola →</a>' },
    ], r.sources, { caption: 'Dataset utama per satelit', empty: 'BELUM ADA DATA SATELIT' });
  }

  return { init, destroy };
})();
