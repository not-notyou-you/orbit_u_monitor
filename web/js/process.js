// js/process.js — Proses berjalan (#data/proses).
//
// Katalog menjawab "apa isi dataset ini"; halaman ini menjawab "apa yang
// sedang jalan sekarang" tanpa harus memilih dataset satu per satu. Sumber
// datanya sama (/api/datasets + /api/datasets/{id}/status), hanya dibaca
// lintas dataset dan hanya untuk status yang masih bergerak.
//
// Label status dan nama satelit diambil dari UI (UI.datasetStatus,
// UI.DATASET_ACTIVE, UI.SOURCE_LABEL) supaya tidak jadi salinan kedua dari
// daftar yang sama di catalog.js.
'use strict';
Pages['process'] = (() => {
  const ACTIVE = UI.DATASET_ACTIVE;
  const PHASE = { download: 'Diunduh', processing: 'Diproses', fusion: 'Difusikan' };
  // Status tahap pipeline: hanya tiga warna sinyal, sesuai aturan tampilan.
  const stageCls = v => /FAIL|ERROR/i.test(v || '') ? 'v-alert' : /RUN|START|WAIT|PENDING/i.test(v || '') ? 'v-amber' : '';
  let st = null;

  async function init(root, ctx) {
    st = { root, ctx, items: [], prog: {}, rail: null, all: false, timer: null };
    UI.$('#pcRefresh', root).addEventListener('click', ev => UI.busy(ev.currentTarget, () => load()));
    UI.$('#pcAll', root).addEventListener('change', ev => { st.all = ev.target.checked; load(); });
    await load();
    // Timer dipasang sekali dan memeriksa sendiri apakah masih ada yang
    // bergerak, jadi halaman yang menganggur tidak menembaki API.
    st.timer = setInterval(() => { if (st && st.items.some(d => ACTIVE.has(d.status))) load(true); }, 10000);
  }
  function destroy() { if (st && st.timer) clearInterval(st.timer); st = null; }

  async function load(quiet) {
    let list;
    try { list = (await API.get('/api/datasets?limit=200')).items || []; }
    catch (e) { if (!quiet) UI.showError('Proses berjalan', e); return; }
    if (!st) return;
    st.items = list;

    const shown = list.filter(d => st.all || ACTIVE.has(d.status));
    // Progres per dataset diminta hanya untuk yang ditampilkan, dan
    // kegagalan satu dataset tidak boleh mengosongkan seluruh halaman.
    const progs = await Promise.all(shown.map(d =>
      API.get('/api/datasets/' + d.dataset_id + '/status').catch(() => null)));
    if (!st) return;
    shown.forEach((d, i) => { st.prog[d.dataset_id] = progs[i]; });
    st.rail = await API.get('/api/pipeline/status/current').catch(() => null);
    if (!st) return;

    renderReadouts(list);
    renderList(shown);
    renderRail();
    const moving = list.filter(d => ACTIVE.has(d.status)).length;
    st.ctx.setStatus((quiet ? 'Diperbarui · ' : 'Siap · ') +
      (moving ? moving + ' proses berjalan' : 'tidak ada proses berjalan'));
  }

  function renderReadouts(list) {
    const moving = list.filter(d => ACTIVE.has(d.status));
    const queued = list.filter(d => d.status === 'QUEUED').length;
    const paused = list.filter(d => d.status === 'PAUSED').length;
    const failed = list.filter(d => d.status === 'FAILED').length;
    UI.$('#pcReadouts', st.root).innerHTML =
      UI.readoutHTML('SEDANG BERJALAN', UI.int(moving.length), 'DARI ' + UI.int(list.length) + ' DATASET', moving.length ? 'v-amber' : '') +
      UI.readoutHTML('ANTRE', UI.int(queued), 'MENUNGGU GILIRAN') +
      UI.readoutHTML('DIJEDA', UI.int(paused), 'PERLU DILANJUTKAN', paused ? 'v-amber' : '') +
      UI.readoutHTML('GAGAL', UI.int(failed), 'PERLU DICOBA ULANG', failed ? 'v-alert' : '');
  }

  function renderList(shown) {
    const box = UI.$('#pcList', st.root);
    if (!shown.length) {
      box.innerHTML = UI.screenHTML({ channel: 'PROSES BERJALAN', body: UI.emptyHTML(
        st.items.length
          ? 'TIDAK ADA PROSES YANG BERJALAN. SIKLUS LIVE JALAN 01, 07, 13, DAN 19 WIB; HIDROMET HARIAN 02 WIB.'
          : 'BELUM ADA DATASET. BUAT LEWAT "BUAT DATASET BARU".') });
      return;
    }
    box.innerHTML = shown.map(cardHTML).join('<div style="height:8px"></div>');
    bindActions();
  }

  function cardHTML(d) {
    const p = st.prog[d.dataset_id];
    const act = ACTIVE.has(d.status);
    // Lapisan progres (ProgressLayer) memecah satu angka persen menjadi per
    // satelit per fase, jadi "40%" bisa dibaca sebagai bagian mana yang jalan.
    const layers = (p && p.layers) || [];
    const waiting = p && p.waiting;
    return UI.screenHTML({
      channel: 'DATASET #' + d.dataset_id + ' · ' + (d.name || '').toUpperCase(),
      rec: UI.esc(UI.datasetStatus(d.status).toUpperCase()),
      recCls: act ? '' : 'off',
      body:
        (act ? UI.progressHTML(p ? p.progress_percent : 0, 'Progres ' + (d.name || 'dataset')) : '') +
        '<p class="scr-text" style="margin:6px 0 0">' +
          '<span class="lbl">SCENE:</span> ' + UI.int(p ? p.downloaded_count : 0) + ' diunduh · ' +
          UI.int(p ? p.processed_count : 0) + ' diproses · ' +
          '<span class="' + ((p && p.failed_count) ? 'v-alert' : '') + '">' + UI.int(p ? p.failed_count : 0) + ' gagal</span>' +
          ' dari ' + UI.int(p ? p.total_scenes : d.total_scenes) + '\n' +
          '<span class="lbl">RENTANG:</span> ' + UI.esc(UI.date(d.date_start)) + ' – ' + UI.esc(UI.date(d.date_end)) +
          ' · <span class="lbl">UKURAN:</span> ' + UI.esc(UI.bytes(d.total_size_bytes)) +
          ' · <span class="lbl">PEMBUAT:</span> ' + UI.esc(d.created_by_name || UI.NA) + '</p>' +
        (p && p.paused ? '<p class="v-amber" style="margin:6px 0 0">DIJEDA' + (p.pause_reason ? ': ' + UI.esc(p.pause_reason) : '') + '</p>' : '') +
        (p && p.queue_position ? '<p class="v-dim" style="margin:6px 0 0">Antrean nomor ' + UI.int(p.queue_position) + '.</p>' : '') +
        (waiting && waiting.reason ? '<p class="v-amber" style="margin:6px 0 0">MENUNGGU DATA HULU: ' + UI.esc(waiting.reason) + '</p>' : '') +
        (layers.length ? '<div style="margin-top:8px">' + layers.map(l => UI.barHTML(
          (UI.SOURCE_LABEL[l.source] || l.source) + ' · ' + (PHASE[l.phase] || l.phase),
          l.ratio, 1, UI.num(l.ratio * 100, 0) + '%')).join('') + '</div>' : '') +
        scenesHTML(p) +
        actionsHTML(d),
    });
  }

  // Tabel per-scene bisa panjang untuk beberapa dataset sekaligus, jadi
  // tertutup secara bawaan: yang dicari pertama biasanya "berapa persen",
  // bukan "scene mana".
  function scenesHTML(p) {
    const rows = (p && p.scenes) || [];
    if (!rows.length) return '';
    const bad = rows.filter(r => /FAIL|ERROR/i.test(r.stage_status || '')).length;
    return '<details style="margin-top:8px"><summary class="v-dim" style="cursor:pointer">' +
      UI.int(rows.length) + ' scene · tahap per scene' + (bad ? ' · ' + UI.int(bad) + ' gagal' : '') + '</summary>' +
      UI.tableHTML([
        { label: 'Scene', key: 'product_identifier' },
        { label: 'Tahap', get: r => r.current_stage || UI.NA },
        { label: 'Status', html: true, get: r => '<span class="' + stageCls(r.stage_status) + '">' + UI.esc(r.stage_status || UI.NA) + '</span>' },
        { label: 'Percobaan', cls: 'r', get: r => UI.int(r.attempt_number) + '/' + UI.int(r.max_retries) },
        { label: 'Mulai', get: r => r.started_at ? UI.dateTime(r.started_at) : '' },
        { label: 'Catatan', key: 'last_error' },
      ], rows) + '</details>';
  }

  // Tombol yang tidak berlaku untuk status sekarang dihilangkan, bukan
  // ditampilkan mati: di daftar beberapa dataset, baris tombol mati lebih
  // membingungkan daripada baris yang pendek.
  function actionsHTML(d) {
    const btn = [];
    if (['QUEUED', 'PREPARING', 'DOWNLOADING', 'PROCESSING'].includes(d.status)) btn.push(['pause', 'Jeda']);
    if (d.status === 'PAUSED') btn.push(['resume', 'Lanjutkan']);
    if (d.status === 'FAILED') btn.push(['retry', 'Coba ulang']);
    if (['DOWNLOADING', 'PROCESSING'].includes(d.status)) btn.push(['cancel', 'Batalkan…']);
    return '<div class="btn-row end" style="margin-top:8px">' +
      '<button type="button" class="small" data-open="' + d.dataset_id + '">Buka di Katalog</button>' +
      btn.map(([a, label]) => '<button type="button" class="small" data-act="' + a + '" data-id="' + d.dataset_id + '">' + label + '</button>').join('') +
      '</div>';
  }

  function renderRail() {
    const r = st.rail;
    const box = UI.$('#pcRail', st.root);
    if (!r || !r.scene_id) { box.innerHTML = ''; return; }
    box.innerHTML = '<div style="height:8px"></div>' + UI.screenHTML({
      channel: 'TAHAP SCENE SENTINEL-1 TERAKHIR' + (r.product_identifier ? ' · ' + UI.esc(r.product_identifier) : ''),
      rec: UI.esc(r.overall_status || ''), recCls: r.active ? '' : 'off',
      body: UI.tableHTML([
        { label: 'Tahap', key: 'stage' },
        { label: 'Status', html: true, get: x => '<span class="' + stageCls(x.status) + '">' + UI.esc(x.status || UI.NA) + '</span>' },
        { label: 'Selesai', get: x => x.completed_at ? UI.dateTime(x.completed_at) : '' },
      ], r.stages || [], { empty: 'BELUM ADA TAHAP TERCATAT' }) +
        '<p class="v-dim" style="margin:6px 0 0;font-size:11px">Ini scene Sentinel-1 terakhir yang diproses pipeline, bukan ringkasan seluruh dataset.</p>',
    });
  }

  function bindActions() {
    const root = st.root;
    UI.$$('#pcList [data-open]', root).forEach(b => b.addEventListener('click', () => st.ctx.go('#data/tersimpan')));
    UI.$$('#pcList [data-act]', root).forEach(b => b.addEventListener('click', () => run(b, b.dataset.act, Number(b.dataset.id))));
  }

  // Aksi yang menghentikan pemrosesan selalu lewat konfirmasi yang menyebut
  // akibatnya; jeda dan lanjut bisa dibatalkan sendiri, jadi langsung jalan.
  async function run(btn, act, id) {
    const d = st.items.find(x => x.dataset_id === id);
    if (!d) return;
    const base = '/api/datasets/' + id;
    await UI.busy(btn, async () => {
      try {
        if (act === 'pause') await API.post(base + '/pause', {});
        else if (act === 'resume') await API.post(base + '/resume');
        else if (act === 'retry') await API.post('/api/pipeline/trigger?dataset_id=' + id);
        else if (act === 'cancel') {
          if (!await UI.confirm('Batalkan proses',
            'Hentikan pemrosesan "' + d.name + '"? Data antara (RAW, ALIGNED, DESPECKLED/INDICES/ACCUMULATED) dihapus; COG dan FUSED yang sudah selesai disimpan.',
            'Batalkan proses')) return;
          const r = await API.post(base + '/cancel', { cascade_delete: true });
          UI.info('Batalkan proses', 'Dibatalkan: ' + UI.int(r.deleted_files) + ' berkas dihapus, tier ' + r.retained_tier + ' disimpan.');
        }
        await load(true);
      } catch (e) { UI.showError('Aksi dataset', e); }
    });
  }

  return { init, destroy };
})();
