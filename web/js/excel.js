// web/js/excel.js — kotak "Excel" (INTERFACE.md §4.10) untuk halaman yang relevan.
// Excel.mount(el, ['disasters', 'disaster_types']) menampilkan hanya jenis data yang
// diizinkan role (GET /api/excel). Impor: uji dulu (?dry_run=true) → ringkasan →
// konfirmasi → impor sungguhan. Semua baris atau tidak sama sekali (422 + error per baris).
'use strict';

const Excel = (() => {
  let catalog = null;
  async function list() {
    if (!catalog) catalog = API.get('/api/excel').then(r => r.items).catch(e => { catalog = null; throw e; });
    return catalog;
  }

  function summaryText(s) {
    return 'Baris dibaca: ' + UI.int(s.rows) + '\nBaru: ' + UI.int(s.inserted) + '\nDiperbarui: ' + UI.int(s.updated) +
      '\nDuplikat (dilewati): ' + UI.int(s.duplicates);
  }

  async function doImport(entity, title, onDone) {
    const input = document.createElement('input');
    input.type = 'file'; input.accept = '.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
    input.addEventListener('change', async () => {
      const f = input.files[0]; if (!f) return;
      if (f.size > 10 * 1024 * 1024) { UI.showError('Impor ' + title, { code: 'UPLOAD_TOO_LARGE' }); return; }
      const buf = await f.arrayBuffer();
      const hdr = { 'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' };
      try {
        const dry = await API.post('/api/excel/' + entity + '/import?dry_run=true', buf, { headers: hdr });
        const ok = await UI.dialog({ title: 'Impor ' + title + ' — hasil pemeriksaan', kind: 'question',
          message: 'Berkas "' + f.name + '" lolos pemeriksaan. Belum ada data yang disimpan.\n\n' + summaryText(dry) + '\n\nSimpan sekarang?',
          buttons: [{ label: 'Simpan', value: true, default: true }, { label: 'Batal', value: false, cancel: true }] });
        if (!ok) return;
        const res = await API.post('/api/excel/' + entity + '/import', buf, { headers: hdr });
        await UI.info('Impor ' + title, 'Impor selesai.\n\n' + summaryText(res));
        if (onDone) onDone(res);
      } catch (e) {
        UI.showError('Impor ' + title, e);
      }
    });
    input.click();
  }

  // opts: { title, onImported }
  async function mount(el, codes, opts) {
    opts = opts || {};
    let items;
    try { items = (await list()).filter(i => codes.includes(i.code)).sort((a, b) => codes.indexOf(a.code) - codes.indexOf(b.code)); }
    catch (e) { el.innerHTML = ''; return; }
    if (!items.length) { el.innerHTML = ''; return; }
    const anyDate = items.some(i => i.date_filter);
    const uid = 'xl' + Math.random().toString(36).slice(2, 7);
    el.innerHTML = '<fieldset><legend>' + UI.esc(opts.title || 'Ekspor / impor Excel') + '</legend>' +
      (items.length > 1 ? '<div class="field"><label for="' + uid + 'e">Jenis data</label><select id="' + uid + 'e">' +
        items.map(i => '<option value="' + i.code + '">' + UI.esc(i.title) + '</option>').join('') + '</select></div>'
        : '<p class="mut">' + UI.esc(items[0].title) + '</p>') +
      (anyDate ? '<div class="field-row" data-dates><div class="field"><label for="' + uid + 'f">Dari tanggal</label><input type="date" id="' + uid + 'f"></div>' +
        '<div class="field"><label for="' + uid + 't">Sampai</label><input type="date" id="' + uid + 't"></div></div>' : '') +
      '<div class="btn-row"><button type="button" data-x="export">' + UI.icon('disk') + 'Ekspor .xlsx</button>' +
      '<button type="button" data-x="template">Templat</button><button type="button" data-x="import">Impor…</button></div>' +
      '<p class="mut" style="margin:4px 0 0;font-size:11px">Impor diperiksa dulu; tidak ada yang disimpan sebelum Anda menyetujui.</p></fieldset>';
    const sel = el.querySelector('#' + uid + 'e');
    const cur = () => items.find(i => i.code === (sel ? sel.value : items[0].code));
    const sync = () => {
      const c = cur();
      const dates = el.querySelector('[data-dates]');
      if (dates) dates.classList.toggle('hidden', !c.date_filter);
      el.querySelector('[data-x=template]').classList.toggle('hidden', !c.import);
      el.querySelector('[data-x=import]').classList.toggle('hidden', !c.import);
    };
    if (sel) sel.addEventListener('change', sync);
    sync();
    el.querySelector('[data-x=export]').addEventListener('click', ev => UI.busy(ev.currentTarget, async () => {
      const c = cur();
      const df = el.querySelector('#' + uid + 'f'), dt = el.querySelector('#' + uid + 't');
      const q = c.date_filter ? API.qs({ date_from: df && df.value, date_to: dt && dt.value }) : '';
      try { await API.download(c.export_url + q, 'orbit_u_' + c.code + '.xlsx'); }
      catch (e) { UI.showError('Ekspor ' + c.title, e); }
    }));
    el.querySelector('[data-x=template]').addEventListener('click', ev => UI.busy(ev.currentTarget, async () => {
      const c = cur();
      try { await API.download(c.template_url, 'template_' + c.code + '.xlsx'); }
      catch (e) { UI.showError('Templat ' + c.title, e); }
    }));
    el.querySelector('[data-x=import]').addEventListener('click', () => { const c = cur(); doImport(c.code, c.title, opts.onImported); });
  }

  return { mount, list };
})();
window.Excel = Excel;
