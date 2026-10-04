// js/statistics.js — Statistik Hari Ini (INTERFACE.md §2.3, §4.4–4.5).
'use strict';
Pages['statistics'] = (() => {
  const SEV_RANK = { CRITICAL: 3, WARNING: 2, INFO: 1 };
  const RUN = { F: ['Final', ''], L: ['Late · sementara', 'v-amber'], E: ['Early · sementara', 'v-amber'] };
  let st = null;

  async function init(root, ctx) {
    st = { root, ctx, map: null, layer: null, today: null, alerts: [] };
    const $ = s => UI.$(s, root);
    $('#stLegend').innerHTML = '<table class="scr-table"><tbody>' + Object.entries(UI.BMKG).map(([k, c]) =>
      '<tr><td><i style="display:inline-block;width:14px;height:14px;vertical-align:-3px;border:1px solid #33ff99;background:' +
        (c.hatch ? (c.hatch === 'hatch-a' ? 'repeating-linear-gradient(45deg,#ff3b3b 0 4px,#000 4px 7px)' : 'repeating-linear-gradient(45deg,#ff3b3b 0 2px,#fff 2px 3px)') : c.color) +
        ';opacity:' + (c.hatch ? 1 : c.opacity + .3) + '"></i></td><td class="' + UI.bmkgClass(k) + '">' + c.short + ' · ' + UI.esc(c.label.toUpperCase()) + '</td><td class="r num">' + UI.esc(c.range) + '</td></tr>').join('') +
      '<tr><td><i style="display:inline-block;width:14px;height:14px;vertical-align:-3px;border:1px dashed #1a9960"></i></td><td class="v-dim">TANPA DATA</td><td></td></tr></tbody></table>';
    $('#stSort').addEventListener('change', renderCards);
    $('#stReload').addEventListener('click', ev => UI.busy(ev.currentTarget, load));
    Excel.mount($('#stExcel'), ['hujan_harian', 'observations', 'alerts', 'kecamatan']);
    st.map = Maps.create($('#stMap'));
    await load();
  }

  function destroy() { if (st && st.map) st.map.remove(); st = null; }

  async function load() {
    const $ = s => UI.$(s, st.root);
    st.ctx.setStatus('Memuat…');
    let geo = null;
    try {
      const [today, alerts, g] = await Promise.all([
        API.get('/api/hydromet/today'),
        API.get('/api/alerts?status=active&limit=500'),
        Maps.regions().catch(() => null),
      ]);
      st.today = today; st.alerts = alerts.items || []; geo = g;
    } catch (e) {
      $('#stCards').innerHTML = UI.emptyHTML('GAGAL MEMUAT DATA'); st.ctx.setStatus('Gagal'); UI.showError('Statistik Hari Ini', e); return;
    }
    const t = st.today, regs = t.regions || [];
    if (t.obs_date) {
      const [a, b] = (t.window_wib || '').split('/');
      $('#stDate').innerHTML = 'Data hujan untuk <b>' + UI.esc(UI.date(t.obs_date, 'long')) + '</b><br>(' +
        (a ? UI.esc(a.slice(11, 16).replace(':', '.')) + '–' + UI.esc((b || '').slice(11, 16).replace(':', '.')) + ' WIB, hari UTC' : '07.00–07.00 WIB') + ')';
    } else {
      $('#stDate').textContent = 'Belum ada data hidromet. Data akan muncul setelah job hidromet harian / backfill selesai.';
    }
    const withRain = regs.filter(r => r.rain_24h_mm !== null && r.rain_24h_mm !== undefined);
    const top = withRain.slice().sort((x, y) => y.rain_24h_mm - x.rain_24h_mm)[0];
    $('#stReadouts').innerHTML =
      UI.readoutHTML('TANGGAL DATA', UI.esc(t.obs_date ? UI.date(t.obs_date) : UI.NA), 'HARI UTC', 'v-cyan') +
      UI.readoutHTML('HUJAN 24 JAM TERTINGGI', top ? UI.num(top.rain_24h_mm, 1) : UI.NA, top ? 'mm · ' + UI.esc(top.name.toUpperCase()) : 'mm',
        top ? UI.bmkgClass(top.bmkg_category || UI.bmkgCategory(top.rain_24h_mm)) : '') +
      UI.readoutHTML('ALERT AKTIF', UI.int(st.alerts.length), st.alerts.length ? 'BELUM DITANDAI DIBACA' : 'TIDAK ADA', st.alerts.length ? 'v-amber' : '') +
      UI.readoutHTML('KECAMATAN AOI', UI.int(regs.length), 'BERDATA ' + UI.int(withRain.length));
    renderAlerts(); renderMap(geo); renderCards();
    st.ctx.setStatus(regs.length ? 'Siap · ' + UI.date(t.obs_date) : 'Belum ada data');
  }

  // ---- spanduk alert: severity tertinggi per kecamatan (v_alert_aktif)
  function renderAlerts() {
    const box = UI.$('#stAlerts', st.root);
    if (!st.alerts.length) { box.innerHTML = ''; return; }
    const byRegion = {};
    st.alerts.forEach(a => { (byRegion[a.region_id] = byRegion[a.region_id] || []).push(a); });
    const groups = Object.values(byRegion).map(list => list.sort((x, y) => SEV_RANK[y.severity] - SEV_RANK[x.severity] || (y.observation_date > x.observation_date ? 1 : -1)))
      .sort((x, y) => SEV_RANK[y[0].severity] - SEV_RANK[x[0].severity]);
    const worst = groups[0][0].severity;
    const canAck = Auth.can('alerts.acknowledge');
    box.innerHTML = '<div class="banner raised" role="alert">' + UI.icon(worst === 'INFO' ? 'info32' : worst === 'CRITICAL' ? 'error32' : 'warn32') +
      '<div class="b-body"><b>' + UI.int(groups.length) + ' kecamatan dengan alert aktif</b> (tertinggi: ' + UI.esc(UI.SEVERITY[worst].label) + ')' +
      '<div class="screen" style="margin-top:6px"><div class="screen-inner"><span class="scr-ch">ALERT AKTIF</span>' +
      UI.tableHTML([
        { label: 'Kecamatan', get: g => g[0].region_name },
        { label: 'Tingkat', html: true, get: g => '<span class="' + UI.SEVERITY[g[0].severity].cls + '">' + UI.esc(UI.SEVERITY[g[0].severity].label.toUpperCase()) + '</span>' },
        { label: 'Tanggal', get: g => UI.date(g[0].observation_date) },
        { label: 'Nilai', cls: 'r', get: g => UI.num(g[0].observed_value, 1) + ' mm ≥ ' + UI.num(g[0].threshold_value, 0) },
        { label: 'Aturan', get: g => g[0].rule_code + (g.length > 1 ? ' (+' + (g.length - 1) + ')' : '') },
      ], groups, { caption: 'Alert aktif per kecamatan' }) + '</div></div>' +
      (canAck ? '<div class="btn-row" style="margin-top:6px">' + groups.map(g =>
        '<button type="button" class="small" data-ack="' + g[0].region_id + '">Tandai sudah dibaca: ' + UI.esc(g[0].region_name) + '</button>').join('') + '</div>'
        : '<p class="mut" style="margin:6px 0 0">Penandaan "sudah dibaca" dilakukan Analis atau Administrator.</p>') +
      '</div></div>';
    UI.$$('[data-ack]', box).forEach(b => b.addEventListener('click', () => acknowledge(b, byRegion[b.dataset.ack])));
  }

  async function acknowledge(btn, list) {
    const name = list[0].region_name;
    const note = await UI.dialog({ title: 'Tandai sudah dibaca', kind: 'question',
      message: list.length + ' alert aktif untuk ' + name + ' akan ditandai sudah dibaca atas nama Anda.',
      body: '<div class="field"><label for="ackNote">Catatan (opsional, maks. 500 karakter)</label><textarea id="ackNote" maxlength="500"></textarea></div>',
      buttons: [{ label: 'Tandai', value: 'ok', default: true }, { label: 'Batal', value: null, cancel: true }],
      collect: win => UI.$('#ackNote', win).value });
    if (note === null || note === 'cancel') return;
    await UI.busy(btn, async () => {
      let done = 0;
      for (const a of list) {
        try { await API.post('/api/alerts/' + a.alert_id + '/acknowledge', { note: note || null }); done++; }
        catch (e) {
          if (e.code === 'ALERT_ALREADY_ACKED') { done++; continue; }
          await UI.showError('Tandai sudah dibaca', e); break;
        }
      }
      if (done) UI.info('Tandai sudah dibaca', done + ' alert untuk ' + name + ' ditandai sudah dibaca.');
      load();
    });
  }

  function catOf(r) { return r.bmkg_category || UI.bmkgCategory(r.rain_24h_mm); }

  function renderMap(geo) {
    const map = st.map;
    UI.$('#stMapRec', st.root).textContent = st.today.obs_date ? '● ' + UI.date(st.today.obs_date, 'short').toUpperCase() : '● NO DATA';
    if (!map) return;
    if (st.layer) { st.layer.remove(); st.layer = null; }
    if (!geo || !geo.features || !geo.features.length) return;
    const byId = Object.fromEntries((st.today.regions || []).map(r => [r.region_id, r]));
    st.layer = L.geoJSON(geo, {
      style: f => {
        const r = byId[f.properties.region_id];
        const c = r && UI.BMKG[catOf(r)];
        if (!c) return { color: '#1a9960', weight: 1, dashArray: '4 3', fillOpacity: 0 };
        return { color: '#33ff99', weight: 1, fillColor: c.color, fillOpacity: c.opacity, className: c.hatch ? 'bmkg-' + c.hatch : '' };
      },
      onEachFeature: (f, layer) => {
        const r = byId[f.properties.region_id];
        const c = r && UI.BMKG[catOf(r)];
        const txt = f.properties.name + ': ' + (c ? c.label + ' (' + UI.num(r.rain_24h_mm, 1) + ' mm)' : 'tanpa data');
        // Label permanen ringkas (singkatan kategori, lihat legenda) agar tidak bertumpuk;
        // nama kecamatan + kategori lengkap di tooltip dan kartu.
        layer.bindTooltip(UI.esc(c ? c.short : '—'), { permanent: true, direction: 'center', className: 'map-label' });
        layer.bindPopup(UI.esc(txt));
        layer.on('add', () => { const el = layer.getElement && layer.getElement(); if (el) el.setAttribute('aria-label', txt); });
      },
    }).addTo(map);
    Maps.ensurePatterns(map);
    // Arsir: ganti isi path setelah dirender (Leaflet tidak mendukung fill pattern langsung).
    st.layer.eachLayer(l => {
      const el = l.getElement && l.getElement();
      const m = el && /bmkg-(hatch-[ab])/.exec(el.getAttribute('class') || '');
      if (m) { el.setAttribute('fill', 'url(#' + m[1] + ')'); el.setAttribute('fill-opacity', '1'); }
    });
    const fit = () => { map.invalidateSize(); try { map.fitBounds(st.layer.getBounds(), { padding: [8, 8] }); } catch (e) { /* kosong */ } };
    fit(); setTimeout(fit, 120);
  }

  function renderCards() {
    const box = UI.$('#stCards', st.root);
    const regs = ((st.today && st.today.regions) || []).slice();
    UI.$('#stCount', st.root).textContent = UI.int(regs.length) + ' KECAMATAN';
    if (!regs.length) { box.innerHTML = UI.emptyHTML('BELUM ADA DATA HIDROMET — MENUNGGU JOB HARIAN / BACKFILL'); return; }
    const sort = UI.$('#stSort', st.root).value;
    regs.sort(sort === 'name' ? (a, b) => a.name.localeCompare(b.name, 'id') : (a, b) => (b.rain_24h_mm ?? -1) - (a.rain_24h_mm ?? -1));
    box.innerHTML = '<div class="kcards">' + regs.map(r => {
      const code = catOf(r), c = UI.BMKG[code];
      const run = RUN[r.gpm_run];
      const al = r.active_alert;
      return '<article class="kcard" aria-label="' + UI.esc(r.name) + '">' +
        '<header><b>' + UI.esc(r.name.toUpperCase()) + '</b><span class="tag ' + UI.bmkgClass(code) + '">' + (c ? c.short + ' · ' + UI.esc(c.label.toUpperCase()) : 'TANPA DATA') + '</span></header>' +
        '<dl class="kv">' +
          '<dt>HUJAN 24 JAM</dt><dd class="num ' + UI.bmkgClass(code) + '">' + UI.num(r.rain_24h_mm, 1) + ' mm</dd>' +
          '<dt>72 JAM</dt><dd class="num">' + UI.num(r.rain_72h_mm, 1) + ' mm</dd>' +
          '<dt>7 HARI</dt><dd class="num">' + UI.num(r.rain_7d_mm, 1) + ' mm</dd>' +
          '<dt>30 HARI</dt><dd class="num">' + UI.num(r.rain_30d_mm, 1) + ' mm</dd>' +
          '<dt>NDVI</dt><dd class="num">' + UI.num(r.ndvi, 2) + '</dd>' +
          '<dt>BANJIR MODIS</dt><dd class="num">' + UI.pct(r.modis_flood_pct, 2) + (r.modis_date && r.modis_date !== st.today.obs_date ? ' <span class="v-dim">(' + UI.esc(UI.date(r.modis_date, 'short')) + ')</span>' : '') + '</dd>' +
          '<dt>RUN GPM</dt><dd class="' + (run ? run[1] : '') + '">' + UI.esc(run ? run[0].toUpperCase() : (r.gpm_run || UI.NA)) + '</dd>' +
        '</dl>' +
        (al ? '<p class="' + UI.SEVERITY[al.severity].cls + '" style="margin:6px 0 0">▲ ALERT ' + UI.esc(UI.SEVERITY[al.severity].label.toUpperCase()) + ' · ' + UI.esc(al.rule_code) + '</p>' : '') +
        '</article>';
    }).join('') + '</div>';
  }

  return { init, destroy };
})();
