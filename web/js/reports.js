// js/reports.js — Laporan (#laporan/kesehatan-data, #laporan/keadaan-aoi; INTERFACE.md §2
// halaman 7, §4.8). Jenis laporan dari tab router (ctx.tab.kind). Daftar
// disaring RLS per audiens; "Buat sendiri" = GET /api/reports/custom.pdf (M56).
'use strict';
Pages['reports'] = (() => {
  const TABS = [
    { key: 'HYDROMET', label: 'Keadaan AOI', perm: 'reports.hydromet' },
    { key: 'DATAHEALTH', label: 'Kesehatan Data', perm: 'reports.datahealth' },
  ];
  const STATUS = { READY: 'SIAP', FAILED: 'GAGAL', GENERATING: 'DIBUAT…', SUPERSEDED: 'DIGANTIKAN', PENDING: 'MENUNGGU' };
  const LIMIT = 50;
  let st = null;

  async function init(root, ctx) {
    const kind = (ctx.tab && ctx.tab.kind) || TABS.find(t => Auth.can(t.perm)).key;
    st = { root, ctx, tab: kind, page: 1, admin: !!ctx.me && ctx.me.role_code === 'ADMIN' };
    const $ = s => UI.$(s, root);
    const today = UI.isoDate(new Date());
    $('#rpTo').value = UI.addDays(today, -1); $('#rpFrom').value = UI.addDays(today, -14);
    $('#rpCustom').addEventListener('submit', ev => { ev.preventDefault(); custom(); });
    const y = new Date().getFullYear();
    $('#rpYear').insertAdjacentHTML('beforeend', Array.from({ length: y - 2022 }, (_, i) => '<option>' + (y - i) + '</option>').join(''));
    $('#rpFilter').addEventListener('submit', ev => { ev.preventDefault(); st.page = 1; UI.busy($('#rpApply'), load); });
    $('#rpAdmin').hidden = !st.admin;
    $('#rpRegen').addEventListener('click', () => regenerate(null));
    await load();
  }

  async function load() {
    const $ = s => UI.$(s, st.root);
    const label = TABS.find(t => t.key === st.tab).label;
    $('#rpCh').textContent = 'LAPORAN ' + label.toUpperCase();
    let r;
    try {
      r = await API.get('/api/reports' + API.qs({ type: st.tab + $('#rpPeriod').value, year: $('#rpYear').value,
        include_superseded: $('#rpOld').checked || undefined, limit: LIMIT, offset: (st.page - 1) * LIMIT }));
    } catch (e) { $('#rpTable').innerHTML = UI.emptyHTML('GAGAL MEMUAT'); UI.showError('Laporan', e); return; }
    $('#rpCount').textContent = UI.int(r.total) + ' LAPORAN';
    $('#rpTable').innerHTML = UI.tableHTML([
      { label: 'Periode', get: x => UI.date(x.period_start) + ' – ' + UI.date(x.period_end) },
      { label: 'Jenis', get: x => x.period === 'WEEKLY' || /WEEKLY/.test(x.report_code) ? 'Mingguan' : 'Bulanan' },
      { label: 'Dibuat', get: x => UI.dateTime(x.generated_at) },
      { label: 'Ukuran', cls: 'r', get: x => x.status === 'FAILED' ? UI.NA : UI.bytes(x.file_size_bytes) },
      { label: 'Status', html: true, get: x => '<span class="' + (x.status === 'FAILED' ? 'v-alert' : x.status === 'SUPERSEDED' ? 'v-dim' : '') + '" title="' + UI.esc(x.error_message || '') + '">' +
          UI.esc(STATUS[x.status] || x.status) + '</span>' + (x.status === 'FAILED' && x.error_message ? '<br><span class="v-dim" style="font-size:11px">' + UI.esc(x.error_message.slice(0, 120)) + '</span>' : '') },
      { label: 'Aksi', html: true, get: x => (x.status === 'READY' || x.status === 'SUPERSEDED' ? '<button type="button" class="small" data-dl="' + x.report_id + '">Unduh PDF</button> ' : '') +
          (st.admin && (x.status === 'READY' || x.status === 'FAILED') ? '<button type="button" class="small" data-regen="' + x.report_id + '">Buat ulang</button>' : '') },
    ], r.items, { empty: 'BELUM ADA LAPORAN. LAPORAN DIBUAT OTOMATIS SETELAH PERIODE BERAKHIR (ARSIP LENGKAP SETELAH BACKFILL).', caption: 'Daftar laporan ' + label })
      + UI.pagerHTML(r.total, LIMIT, (st.page - 1) * LIMIT);
    UI.$$('[data-dl]', st.root).forEach(b => b.addEventListener('click', () => UI.busy(b, async () => {
      const x = r.items.find(i => String(i.report_id) === b.dataset.dl);
      try { await API.download('/api/reports/' + x.report_id + '/download', x.file_name || 'laporan.pdf'); } catch (e) { UI.showError('Unduh laporan', e); }
    })));
    UI.$$('[data-regen]', st.root).forEach(b => b.addEventListener('click', () => regenerate(r.items.find(i => String(i.report_id) === b.dataset.regen))));
    UI.$$('#rpTable [data-page]', st.root).forEach(b => b.addEventListener('click', () => { st.page = Number(b.dataset.page); load(); }));
    st.ctx.setStatus('Siap · ' + UI.int(r.total) + ' laporan');
  }

  async function custom() {
    const $ = s => UI.$(s, st.root);
    const from = $('#rpFrom').value, to = $('#rpTo').value;
    const days = from && to ? Math.round((UI.parseDate(to) - UI.parseDate(from)) / 864e5) + 1 : 0;
    $('#rpCustomErr').textContent = !from || !to || days < 1 ? 'Isi tanggal awal dan akhir (awal ≤ akhir).' : days > 366 ? 'Rentang maksimal 366 hari.' : '';
    if ($('#rpCustomErr').textContent) return;
    await UI.busy($('#rpCustomGo'), async () => {
      st.ctx.setStatus('Membuat PDF…');
      try { await API.download('/api/reports/custom.pdf' + API.qs({ kind: st.tab, date_from: from, date_to: to }), 'laporan.pdf'); st.ctx.setStatus('PDF diunduh'); }
      catch (e) { st.ctx.setStatus('Gagal'); UI.showError('Laporan rentang bebas', e); }
    });
  }

  async function regenerate(item) {
    const codes = ['HYDROMET_WEEKLY', 'HYDROMET_MONTHLY', 'DATAHEALTH_WEEKLY', 'DATAHEALTH_MONTHLY'];
    const names = { HYDROMET_WEEKLY: 'Hidromet mingguan', HYDROMET_MONTHLY: 'Hidromet bulanan', DATAHEALTH_WEEKLY: 'Kesehatan Data mingguan', DATAHEALTH_MONTHLY: 'Kesehatan Data bulanan' };
    const body = await UI.dialog({ title: 'Buat ulang laporan', kind: 'question',
      message: 'Periode mingguan dimulai hari Senin; bulanan tanggal 1. Laporan dibuat di latar belakang.',
      body: '<div class="field"><label for="rgCode">Jenis laporan</label><select id="rgCode">' + codes.map(c => '<option value="' + c + '"' + (item && item.report_code === c ? ' selected' : '') + '>' + names[c] + '</option>').join('') + '</select></div>' +
        '<div class="field"><label for="rgStart">Awal periode</label><input type="date" id="rgStart" value="' + (item ? item.period_start : '') + '"><span class="err" id="rgErr"></span></div>',
      buttons: [{ label: 'Buat ulang', value: 'ok', default: true }, { label: 'Batal', value: null, cancel: true }],
      validate: win => {
        const code = UI.$('#rgCode', win).value, v = UI.$('#rgStart', win).value, d = UI.parseDate(v);
        const msg = !v ? 'Isi awal periode.' : /WEEKLY/.test(code) && d.getDay() !== 1 ? 'Laporan mingguan harus dimulai hari Senin.'
          : /MONTHLY/.test(code) && d.getDate() !== 1 ? 'Laporan bulanan harus dimulai tanggal 1.' : '';
        UI.$('#rgErr', win).textContent = msg; UI.$('#rgStart', win).setAttribute('aria-invalid', msg ? 'true' : 'false');
        return !msg;
      },
      collect: win => ({ report_code: UI.$('#rgCode', win).value, period_start: UI.$('#rgStart', win).value }) });
    if (!body || body === 'cancel') return;
    try {
      const r = await API.post('/api/reports/regenerate', body);
      await UI.info('Buat ulang laporan', 'Diterima: ' + names[r.report_code] + ' ' + UI.date(r.period_start) + ' – ' + UI.date(r.period_end) + '.\nMuat ulang daftar dalam beberapa detik.');
      setTimeout(() => { if (st) load(); }, 4000);
    } catch (e) { UI.showError('Buat ulang laporan', e); }
  }

  return { init };
})();
