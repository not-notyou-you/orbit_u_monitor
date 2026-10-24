// js/reports.js — Laporan (#laporan/kesehatan-data, #laporan/keadaan-aoi; INTERFACE.md §2
// halaman 7, §4.8). Jenis laporan dari tab router (ctx.tab.kind). Daftar
// disaring RLS per audiens; "Buat sendiri" = GET /api/reports/custom.pdf (M56).
//
// M68: dua kartu laporan terbaru (mingguan, bulanan) di atas; saringan satu
// baris yang langsung berlaku saat diubah; rentang bebas dan "buat ulang
// periode" (Administrator) lewat dialog, bukan kotak tetap di panel kiri.
//
// M75: setiap permintaan memeriksa bahwa halaman yang memulainya masih yang
// tampil (st yang sama) sebelum menulis ke layar. Dulu berpindah tab
// Laporan saat daftar masih dimuat membuat permintaan lama menulis ke tab
// baru, atau melempar galat karena st sudah dikosongkan.
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
    const y = new Date().getFullYear();
    $('#rpYear').insertAdjacentHTML('beforeend', Array.from({ length: y - 2022 }, (_, i) => '<option>' + (y - i) + '</option>').join(''));
    $('#rpFilter').addEventListener('change', () => { st.page = 1; load(); });
    $('#rpFilter').addEventListener('submit', ev => ev.preventDefault());
    $('#rpCustomBtn').addEventListener('click', custom);
    $('#rpRegen').hidden = !st.admin;
    $('#rpRegen').addEventListener('click', () => regenerate(null));
    await Promise.all([loadLatest(), load()]);
  }

  const download = x => API.download('/api/reports/' + x.report_id + '/download', x.file_name || 'laporan.pdf');

  // Kartu laporan terbaru per periode: yang paling sering dicari.
  async function loadLatest() {
    const my = st;
    const box = UI.$('#rpLatest', my.root);
    const pick = async period => {
      const r = await API.get('/api/reports' + API.qs({ type: my.tab + period, limit: 5, offset: 0 })).catch(() => null);
      return r ? (r.items || []).find(x => x.status === 'READY') || null : null;
    };
    const [w, m] = await Promise.all([pick('_WEEKLY'), pick('_MONTHLY')]);
    if (st !== my) return;
    const card = (title, x) => '<div class="rp-card raised"><div class="rp-card-text"><span class="lbl">' + UI.esc(title) + '</span>' +
      (x ? '<b>' + UI.esc(UI.date(x.period_start) + ' – ' + UI.date(x.period_end)) + '</b><span class="mut">Dibuat ' + UI.esc(UI.dateTime(x.generated_at)) +
        ' · ' + UI.esc(UI.bytes(x.file_size_bytes)) + '</span>' : '<span class="mut">Belum ada laporan.</span>') + '</div>' +
      (x ? '<button type="button" class="default" data-latest="' + x.report_id + '">Unduh PDF</button>' : '') + '</div>';
    box.innerHTML = card('Mingguan terakhir', w) + card('Bulanan terakhir', m);
    const items = [w, m].filter(Boolean);
    UI.$$('[data-latest]', box).forEach(b => b.addEventListener('click', () => UI.busy(b, async () => {
      try { await download(items.find(x => String(x.report_id) === b.dataset.latest)); } catch (e) { UI.showError('Unduh laporan', e); }
    })));
  }

  async function load() {
    const my = st;
    if (!my) return;
    const $ = s => UI.$(s, my.root);
    const label = TABS.find(t => t.key === my.tab).label;
    $('#rpCh').textContent = 'LAPORAN ' + label.toUpperCase();
    let r;
    try {
      r = await API.get('/api/reports' + API.qs({ type: st.tab + $('#rpPeriod').value, year: $('#rpYear').value,
        include_superseded: $('#rpOld').checked || undefined, limit: LIMIT, offset: (st.page - 1) * LIMIT }));
    } catch (e) {
      if (st !== my) return;
      $('#rpTable').innerHTML = UI.emptyHTML('GAGAL MEMUAT') + '<div class="btn-row" style="justify-content:center"><button type="button" class="small" id="rpRetry">Coba lagi</button></div>';
      $('#rpRetry').addEventListener('click', load);
      UI.showError('Laporan', e); return;
    }
    if (st !== my) return;
    $('#rpCount').textContent = UI.int(r.total) + ' LAPORAN';
    $('#rpTable').innerHTML = UI.tableHTML([
      { label: 'Periode', get: x => UI.date(x.period_start) + ' – ' + UI.date(x.period_end) },
      { label: 'Jenis', get: x => x.period === 'WEEKLY' || /WEEKLY/.test(x.report_code) ? 'Mingguan' : 'Bulanan' },
      { label: 'Dibuat', get: x => UI.dateTime(x.generated_at) },
      { label: 'Ukuran', cls: 'r', get: x => x.status === 'FAILED' ? UI.NA : UI.bytes(x.file_size_bytes) },
      { label: 'Status', html: true, get: x => '<span class="' + (x.status === 'FAILED' ? 'v-alert' : x.status === 'SUPERSEDED' ? 'v-dim' : '') + '" title="' + UI.esc(x.error_message || '') + '">' +
          UI.esc(STATUS[x.status] || x.status) + '</span>' + (x.status === 'FAILED' && x.error_message ? '<br><span class="v-dim" style="font-size:11px">' + UI.esc(x.error_message.slice(0, 120)) + '</span>' : '') },
      { label: 'Aksi', html: true, get: x => (x.status === 'READY' || x.status === 'SUPERSEDED' ? '<button type="button" class="small" data-dl="' + x.report_id + '">Unduh PDF</button> ' : '') +
          (st.admin && (x.status === 'READY' || x.status === 'FAILED') ? '<button type="button" class="small" data-regen="' + x.report_id + '">Buat ulang…</button>' : '') },
    ], r.items, { empty: 'BELUM ADA LAPORAN. LAPORAN DIBUAT OTOMATIS SETELAH PERIODE BERAKHIR (ARSIP LENGKAP SETELAH BACKFILL).', caption: 'Daftar laporan ' + label })
      + UI.pagerHTML(r.total, LIMIT, (st.page - 1) * LIMIT);
    UI.$$('[data-dl]', st.root).forEach(b => b.addEventListener('click', () => UI.busy(b, async () => {
      const x = r.items.find(i => String(i.report_id) === b.dataset.dl);
      try { await download(x); } catch (e) { UI.showError('Unduh laporan', e); }
    })));
    UI.$$('[data-regen]', st.root).forEach(b => b.addEventListener('click', () => regenerate(r.items.find(i => String(i.report_id) === b.dataset.regen))));
    UI.$$('#rpTable [data-page]', st.root).forEach(b => b.addEventListener('click', () => { st.page = Number(b.dataset.page); load(); }));
    st.ctx.setStatus('Siap · ' + UI.int(r.total) + ' laporan');
  }

  // Rentang bebas: PDF dibuat saat itu juga dan langsung diunduh; tidak disimpan di daftar.
  async function custom() {
    const today = UI.isoDate(new Date());
    const v = await UI.dialog({ title: 'Buat laporan rentang bebas', kind: 'question',
      message: 'PDF ' + TABS.find(t => t.key === st.tab).label + ' dibuat saat itu juga dan langsung diunduh; tidak disimpan di daftar. Maksimal 366 hari.',
      body: '<div class="field-row"><div class="field"><label for="rpFrom">Dari</label><input type="date" id="rpFrom" value="' + UI.addDays(today, -14) + '"></div>' +
        '<div class="field"><label for="rpTo">Sampai</label><input type="date" id="rpTo" value="' + UI.addDays(today, -1) + '"></div></div><span class="err" id="rpCustomErr"></span>',
      buttons: [{ label: 'Buat & unduh PDF', value: 'ok', default: true }, { label: 'Batal', value: null, cancel: true }],
      validate: (win, val) => {
        if (val !== 'ok') return true;
        const from = UI.$('#rpFrom', win).value, to = UI.$('#rpTo', win).value;
        const days = from && to ? Math.round((UI.parseDate(to) - UI.parseDate(from)) / 864e5) + 1 : 0;
        const msg = !from || !to || days < 1 ? 'Isi tanggal awal dan akhir (awal ≤ akhir).' : days > 366 ? 'Rentang maksimal 366 hari.' : '';
        UI.$('#rpCustomErr', win).textContent = msg;
        return !msg;
      },
      collect: win => ({ from: UI.$('#rpFrom', win).value, to: UI.$('#rpTo', win).value }) });
    if (!v || v === 'cancel') return;
    await UI.busy(UI.$('#rpCustomBtn', st.root), async () => {
      st.ctx.setStatus('Membuat PDF…');
      try { await API.download('/api/reports/custom.pdf' + API.qs({ kind: st.tab, date_from: v.from, date_to: v.to }), 'laporan.pdf'); st.ctx.setStatus('PDF diunduh'); }
      catch (e) { st.ctx.setStatus('Gagal'); UI.showError('Laporan rentang bebas', e); }
    });
  }

  async function regenerate(item) {
    const codes = [st.tab + '_WEEKLY', st.tab + '_MONTHLY'];
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
      setTimeout(() => { if (st) { load(); loadLatest(); } }, 4000);
    } catch (e) { UI.showError('Buat ulang laporan', e); }
  }

  function destroy() { st = null; }

  return { init, destroy };
})();
