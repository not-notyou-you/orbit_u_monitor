// js/citra-report.js — Citra Satelit › Laporan PDF (#citra/laporan, INTERFACE.md §2
// halaman 3.5, M56). GET /api/citra/report.pdf?pages=…&date=…&compare=…
// Halaman yang dicentang (Ringkasan, Sentinel-1, MODIS, GPM) masuk ke SATU
// PDF dengan urutan tetap seperti menu. Tanggal yang ditawarkan hanya yang
// terlihat untuk peran pemanggil, dan API menegakkan batas yang sama.
'use strict';
Pages['citra-report'] = (() => {
  const LABEL = { ringkasan: 'Ringkasan', s1: 'Sentinel-1', modis: 'MODIS', gpm: 'GPM' };
  let st = null;

  async function init(root, ctx) {
    st = { root, ctx, area: null };
    const $ = s => UI.$(s, root);
    const boxes = () => UI.$$('input[name=pages]', root);
    $('#crAll').addEventListener('click', () => { boxes().forEach(b => { b.checked = true; }); preview(); });
    $('#crNone').addEventListener('click', () => { boxes().forEach(b => { b.checked = false; }); preview(); });
    boxes().forEach(b => b.addEventListener('change', preview));
    $('#crArea').addEventListener('change', e => { CitraState.setArea(Number(e.target.value)); loadDates(); });
    $('#crDate').addEventListener('change', preview);
    $('#crCmp').addEventListener('change', preview);
    $('#crCmpOn').addEventListener('change', e => { $('#crCmpBox').hidden = !e.target.checked; preview(); });
    $('#crForm').addEventListener('submit', ev => { ev.preventDefault(); download(); });
    await loadDates();
  }

  async function loadDates() {
    const $ = s => UI.$(s, st.root);
    let summary;
    try { summary = await API.get('/api/citra/summary' + API.qs({ area_id: CitraState.area() || '' })); }
    catch (e) { UI.showError('Laporan citra', e); return; }
    $('#crWindow').textContent = CitraState.windowText(summary.window);
    if (!summary.area) { $('#crPreview').innerHTML = UI.screenHTML({ channel: 'LAPORAN', body: UI.emptyHTML('BELUM ADA SCENE YANG SIAP') }); return; }
    st.area = summary.area;
    CitraState.setArea(summary.area.area_id);
    $('#crArea').innerHTML = summary.areas.map(a => '<option value="' + a.area_id + '"' + (a.area_id === summary.area.area_id ? ' selected' : '') + '>' + UI.esc(a.area_name) + '</option>').join('');
    // Daftar GPM = semua tanggal scene + semua hari angka harian (backfill),
    // jadi tanggal hasil backfill juga bisa dicetak (angka tanpa gambar).
    const r = await API.get('/api/citra/areas/' + summary.area.area_id + '/scenes' + API.qs({ source: 'gpm' }));
    const opt = d => '<option value="' + d.date + '">' + UI.esc(UI.date(d.date)) +
      (d.has_images ? '' : d.has_scene ? ' (tanpa gambar)' : ' (angka harian saja)') + '</option>';
    const opts = r.dates.map(opt).join('');
    $('#crDate').innerHTML = opts || '<option value="">Belum ada data</option>';
    $('#crCmp').innerHTML = opts;
    const withImg = r.dates.filter(d => d.has_images);
    if (withImg[0]) $('#crDate').value = withImg[0].date;
    if (withImg[1]) $('#crCmp').value = withImg[1].date;
    preview();
  }

  function chosen() { return UI.$$('input[name=pages]:checked', st.root).map(b => b.value); }

  function preview() {
    const $ = s => UI.$(s, st.root);
    const pages = chosen();
    $('#crPagesErr').textContent = pages.length ? '' : 'Pilih minimal satu halaman.';
    const cmp = $('#crCmpOn').checked ? $('#crCmp').value : '';
    const date = $('#crDate').value;
    $('#crPreview').innerHTML = UI.screenHTML({ channel: 'ISI PDF', body:
      (pages.length ? '<ol class="scr-text" style="margin:0;padding-left:18px">' + pages.map(p => '<li>' + UI.esc(LABEL[p]) +
        (p === 'ringkasan' ? ' — rekap scene per satelit' : ' — penjelasan, gambar ' + UI.esc(UI.date(date)) +
          (cmp && cmp !== date ? ', perbandingan dengan ' + UI.esc(UI.date(cmp)) : '') + ', kalimat kondisi, tabel angka') + '</li>').join('') +
        '<li>Catatan dan batas waktu peran Anda</li></ol>' : UI.emptyHTML('BELUM ADA HALAMAN YANG DIPILIH')) +
      '<p class="scr-text v-dim" style="margin:8px 0 0">AREA: ' + UI.esc(st.area ? st.area.area_name : UI.NA) + '</p>' });
  }

  async function download() {
    const $ = s => UI.$(s, st.root);
    const pages = chosen();
    if (!pages.length) { $('#crPagesErr').textContent = 'Pilih minimal satu halaman.'; return; }
    if (!st.area || !$('#crDate').value) { UI.showError('Laporan citra', { code: 'NOT_FOUND' }); return; }
    const cmp = $('#crCmpOn').checked && $('#crCmp').value !== $('#crDate').value ? $('#crCmp').value : '';
    await UI.busy($('#crGo'), async () => {
      st.ctx.setStatus('Membuat PDF…');
      try {
        await API.download('/api/citra/report.pdf' + API.qs({ area_id: st.area.area_id, pages: pages.join(','),
          date: $('#crDate').value, compare: cmp }), 'laporan_citra.pdf');
        st.ctx.setStatus('PDF diunduh');
      } catch (e) { st.ctx.setStatus('Gagal'); UI.showError('Laporan citra', e); }
    });
  }

  return { init };
})();
