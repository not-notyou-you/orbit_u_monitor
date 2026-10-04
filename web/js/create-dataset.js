// js/create-dataset.js — wizard Buat Dataset (INTERFACE.md §2.6) [WARIS DataLab View 1].
// Sumber dan level dipilih per satelit; fusi wajib bila > 1 sumber; rentang ≤ 366 hari;
// "Pakai konfigurasi sebelumnya" per pengguna (/api/datasets/last-config, created_by).
'use strict';
Pages['create-dataset'] = (() => {
  const SOURCES = [
    { key: 'sentinel1', label: 'Sentinel-1 SAR (ESA)', desc: 'radar, menembus awan, ±10 m, kunjungan ulang ±6–12 hari',
      levels: [['RAW', 'kalibrasi + crop (tanpa filter Lee, tanpa QA)'], ['PROCESSED', '+ filter Lee 7×7 + analitik QA + COG']] },
    { key: 'modis', label: 'MODIS optik (NASA)', desc: 'banjir/vegetasi, 250 m, harian',
      levels: [['RAW', 'peta banjir saja (tanpa indeks turunan)'], ['PROCESSED', '+ NDVI + NDWI dari reflektansi']] },
    { key: 'gpm', label: 'GPM IMERG curah hujan (NASA/JAXA)', desc: 'presipitasi, ±10 km, harian',
      levels: [['RAW', 'hujan harian (hari itu saja)'], ['PROCESSED', '+ akumulasi 24 jam / 72 jam / 7 hari']] },
  ];
  const FUSION = [['CO_OCCURRENCE', 'hanya tanggal ketika semua sumber punya data'],
    ['FULL_COVERAGE', 'setiap hari; MODIS/GPM diunduh harian, unduhan jauh lebih besar'],
    ['HYBRID', 'unduh harian, dirakit per tanggal Sentinel-1']];
  const PREVIEW = [['GRAYSCALE', 'peregangan persentil 2–98'], ['COLORED', 'colormap per sumber'], ['COMPOSITE', 'RGB false-color (Sentinel-1 saja)']];
  const SHORT = { sentinel1: 'S1', modis: 'MODIS', gpm: 'GPM' };
  const MAX_DAYS = 366;
  let st = null;

  async function init(root, ctx) {
    st = { root, ctx, rois: [], roiId: null, step: 1, map: null, box: null };
    const $ = s => UI.$(s, root);
    $('#cdSources').innerHTML = SOURCES.map(s => '<fieldset class="cd-src" data-src="' + s.key + '" data-off="true"><legend>' +
      '<label class="check" style="margin:0"><input type="checkbox" data-enable="' + s.key + '"> ' + UI.esc(s.label) + '</label></legend>' +
      '<p class="mut" style="margin:0 0 4px">' + UI.esc(s.desc) + '</p>' +
      s.levels.map(([v, d]) => '<label class="opt"><input type="checkbox" data-level="' + s.key + '" value="' + v + '" disabled><span>' + v + '<small>' + UI.esc(d) + '</small></span></label>').join('') +
      '</fieldset>').join('');
    $('#cdFusionList').innerHTML = FUSION.map(([v, d]) => '<label class="cd-opt"><input type="radio" name="cdFusion" value="' + v + '"><span>' + v.replace('_', ' ') + '<small>' + UI.esc(d) + '</small></span></label>').join('');
    $('#cdPreview').innerHTML = PREVIEW.map(([v, d]) => '<label class="cd-opt"><input type="checkbox" data-preview value="' + v + '"><span>' + v + '<small>' + UI.esc(d) + '</small></span></label>').join('');

    root.addEventListener('change', onChange);
    root.addEventListener('input', () => review());
    $('#cdAll').addEventListener('change', e => { SOURCES.forEach(s => setSource(s.key, e.target.checked, e.target.checked ? ['RAW', 'PROCESSED'] : [])); sync(); });
    $('#cdSearch').addEventListener('input', renderRois);
    const select = UI.bindTabs(root, t => go(Number(t)));
    st.selectTab = n => select(UI.$('[role=tab][data-tab="' + n + '"]', root));
    $('#cdNext').addEventListener('click', () => go(st.step + 1));
    $('#cdBack').addEventListener('click', () => go(st.step - 1));
    $('#cdForm').addEventListener('submit', submit);
    $('#cdCloneBtn').addEventListener('click', ev => UI.busy(ev.currentTarget, applyClone));
    st.map = Maps.create($('#cdMap'));
    try { st.rois = (await API.get('/api/rois')).items; } catch (e) { UI.showError('Lokasi', e); }
    renderRois(); sync(); show(1);
    try { const cfg = await API.get('/api/datasets/last-config', { noRedirect: true }); showClone(cfg); } catch (e) { /* 404 = belum pernah membuat dataset */ }
  }
  function destroy() { if (st && st.map) st.map.remove(); st = null; }

  // ---------------------------------------------------------------- lokasi
  function renderRois() {
    const q = UI.$('#cdSearch', st.root).value.trim().toLowerCase();
    const rows = st.rois.filter(r => !q || r.name.toLowerCase().includes(q) || (r.region_code || '').toLowerCase().includes(q));
    const box = UI.$('#cdRois', st.root);
    box.innerHTML = rows.length ? rows.map(r => '<button type="button" role="option" data-roi="' + r.region_id + '" aria-selected="' + (r.region_id === st.roiId) + '">' +
      UI.esc(r.name) + '<span class="sub">' + (r.area_km2 ? UI.num(r.area_km2, 0) + ' km²' : '') + '</span></button>').join('')
      : '<p class="mut" style="padding:4px">' + (st.rois.length ? 'Tidak ada lokasi yang cocok.' : 'Belum ada ROI sistem.') + '</p>';
    UI.$$('[data-roi]', box).forEach(b => b.addEventListener('click', () => pickRoi(Number(b.dataset.roi))));
  }
  function pickRoi(id) {
    st.roiId = id;
    UI.$$('#cdRois [data-roi]', st.root).forEach(b => b.setAttribute('aria-selected', Number(b.dataset.roi) === id));
    const r = st.rois.find(x => x.region_id === id);
    UI.$('#cdRegion', st.root).innerHTML = r ? '<b>' + UI.esc(r.name) + '</b> — ' + UI.esc(r.description || r.region_code || '') : 'Belum ada lokasi dipilih — pilih dari daftar di kiri.';
    UI.$('#cdAoiRec', st.root).textContent = r ? '● ' + r.name.toUpperCase() : '● BELUM DIPILIH';
    if (st.map && r && r.bbox) {
      if (st.box) st.box.remove();
      const [x0, y0, x1, y1] = r.bbox;
      st.box = L.rectangle([[y0, x0], [y1, x1]], { color: '#4de1ff', weight: 2, fillOpacity: 0.08 }).addTo(st.map);
      st.map.invalidateSize(); st.map.fitBounds(st.box.getBounds(), { padding: [12, 12] });
    }
    review(); err('');
  }

  // ---------------------------------------------------------------- sumber
  const enabled = () => SOURCES.map(s => s.key).filter(k => UI.$('[data-enable="' + k + '"]', st.root).checked);
  const levels = k => UI.$$('[data-level="' + k + '"]:checked', st.root).map(c => c.value);
  function setSource(k, on, lv) {
    UI.$('[data-enable="' + k + '"]', st.root).checked = on;
    UI.$$('[data-level="' + k + '"]', st.root).forEach(c => { c.checked = on && lv.includes(c.value); });
  }
  function onChange(e) {
    const t = e.target;
    if (t.dataset.enable && t.checked && !levels(t.dataset.enable).length) setSource(t.dataset.enable, true, ['PROCESSED']);
    if (t.dataset.level && t.checked) UI.$('[data-enable="' + t.dataset.level + '"]', st.root).checked = true;
    sync(); err('');
  }
  function sync() {
    let all = true;
    SOURCES.forEach(s => {
      const on = UI.$('[data-enable="' + s.key + '"]', st.root).checked;
      const fs = UI.$('.cd-src[data-src="' + s.key + '"]', st.root);
      fs.dataset.off = String(!on);
      UI.$$('[data-level="' + s.key + '"]', fs).forEach(c => { c.disabled = !on; });
      if (!on || levels(s.key).length < s.levels.length) all = false;
    });
    const a = UI.$('#cdAll', st.root); a.checked = all; a.indeterminate = !all && enabled().length > 0;
    const multi = enabled().length > 1;
    UI.$('#cdFusion', st.root).disabled = !multi;
    if (!multi) { UI.$$('[name=cdFusion]', st.root).forEach(r => { r.checked = false; }); UI.$('#cdFusionOnly', st.root).checked = false; }
    UI.$('#cdTolBox', st.root).classList.toggle('hidden', fusion() !== 'FULL_COVERAGE');
    review();
  }
  const fusion = () => { const r = UI.$('[name=cdFusion]:checked', st.root); return r ? r.value : null; };
  const previews = () => UI.$$('[data-preview]:checked', st.root).map(c => c.value);
  const tol = () => { const v = parseInt(UI.$('#cdTol', st.root).value, 10); return Number.isFinite(v) ? Math.min(14, Math.max(0, v)) : 2; };
  const sources = () => Object.fromEntries(enabled().filter(k => levels(k).length).map(k => [k, { processing: levels(k) }]));

  // ---------------------------------------------------------------- langkah
  function validate(step) {
    const $ = s => UI.$(s, st.root);
    if (step === 1) {
      if (!st.roiId) return 'Pilih lokasi dari daftar di kiri terlebih dahulu.';
      const a = $('#cdStart').value, b = $('#cdEnd').value;
      if (!a || !b) return 'Lengkapi tanggal mulai dan tanggal akhir.';
      if (a > b) return 'Tanggal mulai harus sebelum tanggal akhir.';
      if ((UI.parseDate(b) - UI.parseDate(a)) / 864e5 + 1 > MAX_DAYS) return 'Rentang tanggal maksimal ' + MAX_DAYS + ' hari.';
      const c = $('#cdCloud').value; if (c !== '' && (c < 0 || c > 100)) return 'Tutupan awan harus 0–100%.';
      return null;
    }
    if (step === 2) {
      if (!enabled().length) return 'Pilih minimal satu sumber satelit.';
      const empty = enabled().find(k => !levels(k).length);
      if (empty) return 'Pilih minimal satu level pemrosesan untuk ' + SOURCES.find(s => s.key === empty).label + '.';
      return null;
    }
    if (step === 3) return enabled().length > 1 && !fusion() ? 'Pilih strategi fusi (wajib bila lebih dari satu sumber).' : null;
    if (step === 4) return $('#cdName').value.trim() ? null : 'Isi nama dataset.';
    return null;
  }
  function err(msg) {
    const b = UI.$('#cdErr', st.root);
    b.innerHTML = msg ? UI.icon('warn32') + '<div class="b-body">' + UI.esc(msg) + '</div>' : '';
    b.classList.toggle('hidden', !msg);
  }
  function show(n) {
    st.step = n;
    UI.$$('section[data-step]', st.root).forEach(s => { s.hidden = Number(s.dataset.step) !== n; });
    UI.$$('[role=tab][data-tab]', st.root).forEach(t => { const on = Number(t.dataset.tab) === n; t.setAttribute('aria-selected', on); t.tabIndex = on ? 0 : -1; });
    UI.$('#cdBack', st.root).disabled = n === 1;
    UI.$('#cdNext', st.root).classList.toggle('hidden', n === 4);
    UI.$('#cdSubmit', st.root).classList.toggle('hidden', n !== 4);
    err(''); review();
  }
  // Maju hanya melewati langkah yang valid; mundur selalu boleh.
  function go(n) {
    n = Math.min(4, Math.max(1, n));
    for (let s = st.step; s < n; s++) { const m = validate(s); if (m) { show(s); err(m); return; } }
    show(n);
  }

  function review() {
    if (!st) return;
    const $ = s => UI.$(s, st.root);
    const r = st.rois.find(x => x.region_id === st.roiId);
    const multi = enabled().length > 1;
    const src = sources();
    const rows = [['LOKASI', r ? r.name : 'belum dipilih'],
      ['TANGGAL', ($('#cdStart').value ? UI.date($('#cdStart').value) : '—') + ' – ' + ($('#cdEnd').value ? UI.date($('#cdEnd').value) : '—')],
      ['ORBIT S1', { ASCENDING: 'naik', DESCENDING: 'turun' }[$('#cdOrbit').value] || 'naik + turun'],
      ['SUMBER', Object.keys(src).map(k => SHORT[k] + '[' + src[k].processing.map(l => l === 'PROCESSED' ? 'PROC' : l).join('+') + ']').join(' | ') || 'belum dipilih'],
      ['FUSI', fusion() || (multi ? 'belum dipilih' : 'tidak dipakai (1 sumber)')]];
    if (fusion() === 'FULL_COVERAGE') rows.push(['TOLERANSI S1', tol() + ' hari']);
    if (multi && $('#cdFusionOnly').checked) rows.push(['PENYIMPANAN', 'hanya keluaran fusi']);
    rows.push(['PRATINJAU', previews().join(', ') || 'tidak dibuat']);
    if ($('#cdName').value.trim()) rows.push(['NAMA', $('#cdName').value.trim()]);
    $('#cdReview').innerHTML = rows.map(([k, v]) => '<dt>' + k + '</dt><dd>' + UI.esc(v) + '</dd>').join('');
  }

  // ---------------------------------------------------------------- konfigurasi sebelumnya
  function showClone(cfg) {
    st.lastCfg = cfg;
    UI.$('#cdClone', st.root).hidden = false;
    UI.$('#cdCloneInfo', st.root).textContent = (cfg.region_name || 'lokasi tidak diketahui') + '\n' +
      (cfg.date_start ? UI.date(cfg.date_start) + ' – ' + UI.date(cfg.date_end) + '\n' : '') +
      Object.keys(cfg.sources || {}).map(k => (SHORT[k] || k) + '[' + cfg.sources[k].processing.join('+') + ']').join(' | ') +
      '\nFusi: ' + (cfg.fusion_strategy || 'tidak dipakai');
  }
  async function applyClone() {
    let cfg;
    try { cfg = await API.get('/api/datasets/last-config'); } catch (e) { UI.showError('Konfigurasi sebelumnya', e); return; }
    const $ = s => UI.$(s, st.root);
    if (cfg.date_start) $('#cdStart').value = cfg.date_start;
    if (cfg.date_end) $('#cdEnd').value = cfg.date_end;
    SOURCES.forEach(s => setSource(s.key, false, []));
    Object.keys(cfg.sources || {}).forEach(k => setSource(k, true, cfg.sources[k].processing || []));
    sync();
    if (cfg.fusion_strategy) { const r = UI.$('[name=cdFusion][value="' + cfg.fusion_strategy + '"]', st.root); if (r) r.checked = true; }
    $('#cdFusionOnly').checked = !!cfg.fusion_output_only;
    $('#cdTol').value = cfg.s1_match_tolerance_days === undefined ? 2 : cfg.s1_match_tolerance_days;
    UI.$$('[data-preview]', st.root).forEach(c => { c.checked = (cfg.preview_options || []).includes(c.value); });
    sync();
    if (cfg.region_id && st.rois.some(r => r.region_id === cfg.region_id)) pickRoi(cfg.region_id);
    show(1);
    UI.info('Konfigurasi sebelumnya', 'Konfigurasi terakhir diterapkan. Periksa tanggal lalu isi nama dataset baru.' +
      (cfg.region_id && !st.rois.some(r => r.region_id === cfg.region_id) ? '\n\nLokasi "' + (cfg.region_name || cfg.region_id) + '" tidak tersedia lagi — pilih lokasi lain.' : ''));
  }

  // ---------------------------------------------------------------- kirim
  async function submit(ev) {
    ev.preventDefault();
    for (let s = 1; s <= 4; s++) { const m = validate(s); if (m) { show(s); err(m); return; } }
    const $ = s => UI.$(s, st.root);
    const qs = {};
    if ($('#cdCloud').value !== '') qs.min_cloud_cover = Number($('#cdCloud').value);
    if ($('#cdRes').value !== '') qs.resolution_m = Number($('#cdRes').value);
    if ($('#cdOrbit').value) qs.orbit_direction = $('#cdOrbit').value;
    const multi = enabled().length > 1;
    const body = { region_id: st.roiId, date_start: $('#cdStart').value, date_end: $('#cdEnd').value,
      name: $('#cdName').value.trim(), description: $('#cdDesc').value.trim() || null, sources: sources(),
      fusion_strategy: multi ? fusion() : null, fusion_output_only: multi && $('#cdFusionOnly').checked,
      s1_match_tolerance_days: fusion() === 'FULL_COVERAGE' ? tol() : null, preview_options: previews(),
      quality_settings: Object.keys(qs).length ? qs : null, generate_preview: previews().length > 0 };
    if (!await UI.confirm('Buat dataset', 'Buat dataset "' + body.name + '"? Sistem akan langsung mengunduh dan memproses data satelit untuk rentang ini.', 'Buat dataset')) return;
    await UI.busy($('#cdSubmit'), async () => {
      try {
        const r = await API.post('/api/datasets', body);
        await UI.info('Buat dataset', 'Dataset #' + r.dataset_id + ' dibuat (status: ' + r.status + '). Pantau progresnya di Katalog.');
        location.hash = 'katalog';
      } catch (e) { err(UI.errorText(e)); UI.showError('Buat dataset', e); }
    });
  }

  return { init, destroy };
})();
