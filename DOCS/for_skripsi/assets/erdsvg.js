/* ERD Crow's Foot berwarna per modul, digambar sebagai SVG dari SKRIPSI_DATA (skema nyata).
   Tabel dan modul bisa digeser dengan mouse; posisi disimpan di localStorage per diagram. */
(function () {
  const NS = "http://www.w3.org/2000/svg";
  const FONT = "Arial, Helvetica, sans-serif";

  /* Pembagian modul yang disarankan. Urutan = nomor modul. */
  const MODULES = [
    { id: "M1", name: "Pengguna, Laporan & Audit", color: "#2563a8", tint: "#e8f0fa",
      tables: ["roles", "users", "api_tokens", "app_settings", "report_types", "generated_reports", "user_activity_logs", "audit_log"],
      desc: "Siapa yang boleh masuk dan dengan peran apa, token API, pengaturan, laporan PDF periodik, log aktivitas, dan jejak perubahan data (RM4)." },
    { id: "M2", name: "Rujukan Wilayah & Sensor", color: "#0f8a7e", tint: "#e3f4f2",
      tables: ["satellite_sources", "spectral_bands", "administrative_regions", "regions_of_interest"],
      desc: "Master yang dirujuk hampir semua modul: sumber satelit, variabel (band), kecamatan COD-AB, dan AOI." },
    { id: "M3", name: "Akuisisi, Pemrosesan & Mutu", color: "#b5582a", tint: "#fbece4",
      tables: ["satellite_scenes", "nasa_scenes", "processing_stages", "processing_jobs", "processing_logs", "data_products", "data_lineage",
               "quality_thresholds", "quality_metrics", "quality_alerts"],
      desc: "Scene/granule dari penyedia, job per tahap, berkas keluaran, graf lineage SHA-256, dan kontrol mutu (RM2)." },
    { id: "M4", name: "Dataset & Fusion", color: "#8a6d0b", tint: "#f8f1da",
      tables: ["datasets", "dataset_source_config", "dataset_jobs", "scene_job_state", "cleanup_operations", "fusion_strategies", "fusion_products"],
      desc: "Dataset historis buatan Data Engineer, eksekusi job, resume per scene, dan stack HDF5 multi-sensor." },
    { id: "M5", name: "Live Monitoring", color: "#c03a6b", tint: "#fae6ee",
      tables: ["live_areas", "live_scenes", "live_scene_metrics", "live_events"],
      desc: "Area pantauan Sentinel-1 per lintasan, scene, metrik numerik, dan log siklus." },
    { id: "M6", name: "Observasi, Peringatan & Kejadian", color: "#1f7a35", tint: "#e4f3e8",
      tables: ["region_observations", "alert_rules", "alert_events", "band_forecasts", "band_forecast_points", "band_forecast_scores",
               "disaster_types", "disaster_events"],
      desc: "Inti sistem: nilai harian per kecamatan, aturan dan peringatan hujan, forecast 15 hari, dan arsip kejadian bencana sebagai pembanding (RM1, RM3)." },
  ];
  const MOD_OF = {};
  MODULES.forEach((m) => m.tables.forEach((t) => (MOD_OF[t] = m)));

  /* Kolom FK "pencatat" yang membuat garis ke users menumpuk; bisa disembunyikan. */
  const BOOKKEEPING = new Set(["created_by", "updated_by", "invalidated_by", "generated_by", "verified_by"]);

  /* Posisi modul di grid keseluruhan: Rujukan di tengah karena paling banyak dirujuk. */
  const GRID = [["M3", "M2", "M6"], ["M4", "M1", "M5"]];

  const HEAD = 24, ROW = 17, W = 210, PAD = 18, GAP = 26, TITLE = 28;

  function el(tag, a, p) { const e = document.createElementNS(NS, tag); for (const k in a) if (a[k] !== undefined) e.setAttribute(k, a[k]); if (p) p.append(e); return e; }
  function text(p, x, y, s, o = {}) {
    const t = el("text", { x, y, "font-family": o.mono ? "Consolas, 'Courier New', monospace" : FONT, "font-size": o.size || 11, fill: o.fill || "#1d1f22",
      "font-weight": o.bold ? "bold" : "normal", "font-style": o.italic ? "italic" : "normal", "text-anchor": o.anchor || "start", "text-decoration": o.underline ? "underline" : "none" }, p);
    t.textContent = s; return t;
  }

  function shortType(t) {
    return t.toLowerCase().replace("character varying", "varchar").replace("timestamp with time zone", "timestamptz")
      .replace("double precision", "float8").replace(/geometry\((\w+),\s*4326\)/, "geom($1)").replace("user-defined", "enum").replace("smallint", "int2")
      .replace("integer", "int4").replace("bigint", "int8");
  }

  function tableCols(t, mode, keep) {
    const T = window.SKRIPSI_DATA.tables[t];
    if (!T) return [];
    return T.cols.filter((c) => mode === "all" || c.k || (keep && keep.has(c.n)));
  }

  function tag(c) {
    const k = c.k || "";
    const out = [];
    if (k.includes("PK")) out.push("PK");
    if (k.includes("FK")) out.push("FK");
    if (k.includes("UNIQUE") && !k.includes("PK")) out.push("UK");
    return out.join(",");
  }

  /* opts: {tables:[...], ext:{name:[cols]}, mode, hideBook, key, layout(boxes) } */
  function render(host, opts) {
    const D = window.SKRIPSI_DATA;
    host.innerHTML = "";
    const inSet = new Set(opts.tables);
    const ext = opts.ext || {};
    const all = [...opts.tables, ...Object.keys(ext)];
    const rels = D.rels.filter((r) => all.includes(r.parent) && all.includes(r.child) && (inSet.has(r.parent) || inSet.has(r.child))
      && !(opts.hideBook && BOOKKEEPING.has(r.fk)));

    const boxes = {};
    all.forEach((t) => {
      const isExt = !inSet.has(t);
      const cols = isExt ? D.tables[t].cols.filter((c) => (ext[t] || []).includes(c.n)) : tableCols(t, opts.mode);
      boxes[t] = { t, cols, ext: isExt, w: W, h: HEAD + Math.max(1, cols.length) * ROW + 6, x: 0, y: 0 };
    });
    opts.layout(boxes);

    const saved = load(opts.key);
    if (saved) Object.entries(saved).forEach(([t, p]) => { if (boxes[t]) { boxes[t].x = p[0]; boxes[t].y = p[1]; } });

    const svg = el("svg", { "font-family": FONT });
    const gMods = el("g", {}, svg), gEdges = el("g", {}, svg), gTables = el("g", {}, svg), gLegend = el("g", {}, svg);

    function modBoxes() {
      const out = [];
      MODULES.forEach((m) => {
        const bs = m.tables.filter((t) => boxes[t] && !boxes[t].ext).map((t) => boxes[t]);
        if (!bs.length || opts.noModuleFrame) return;
        const x0 = Math.min(...bs.map((b) => b.x)) - PAD, y0 = Math.min(...bs.map((b) => b.y)) - PAD - TITLE;
        const x1 = Math.max(...bs.map((b) => b.x + b.w)) + PAD, y1 = Math.max(...bs.map((b) => b.y + b.h)) + PAD;
        out.push({ m, x0, y0, x1, y1 });
      });
      return out;
    }

    function drawMods() {
      gMods.innerHTML = "";
      modBoxes().forEach(({ m, x0, y0, x1, y1 }) => {
        const g = el("g", { "data-mod": m.id, style: "cursor:move" }, gMods);
        el("rect", { x: x0, y: y0, width: x1 - x0, height: y1 - y0, rx: 10, fill: m.tint, stroke: m.color, "stroke-width": 2 }, g);
        el("rect", { x: x0, y: y0, width: x1 - x0, height: TITLE, rx: 10, fill: m.color }, g);
        el("rect", { x: x0, y: y0 + TITLE - 10, width: x1 - x0, height: 10, fill: m.color }, g);
        text(g, x0 + 12, y0 + 19, `${m.id} · ${m.name}`, { fill: "#fff", bold: true, size: 13 });
      });
    }

    function rowY(b, col) {
      const i = b.cols.findIndex((c) => c.n === col);
      return b.y + HEAD + (i < 0 ? 0 : i) * ROW + ROW / 2 + 2;
    }

    function endMarks(g, x, y, s, kind) {
      // s = +1 garis keluar ke kanan dari titik (x,y), -1 ke kiri
      const st = { stroke: "#1d1f22", "stroke-width": 1.3, fill: "none" };
      if (kind === "many") {
        el("path", { d: `M${x + s * 13},${y} L${x},${y - 6} M${x + s * 13},${y} L${x},${y} M${x + s * 13},${y} L${x},${y + 6}`, ...st }, g);
        el("circle", { cx: x + s * 19, cy: y, r: 3.6, fill: "#fff", stroke: "#1d1f22", "stroke-width": 1.3 }, g);
      } else {
        el("line", { x1: x + s * 7, y1: y - 6, x2: x + s * 7, y2: y + 6, ...st }, g);
        if (kind === "one") el("line", { x1: x + s * 12, y1: y - 6, x2: x + s * 12, y2: y + 6, ...st }, g);
        else el("circle", { cx: x + s * 15, cy: y, r: 3.6, fill: "#fff", stroke: "#1d1f22", "stroke-width": 1.3 }, g);
      }
    }

    function drawEdges() {
      gEdges.innerHTML = "";
      rels.forEach((r) => {
        const c = boxes[r.child], p = boxes[r.parent];
        const col = D.tables[r.child].cols.find((x) => x.n === r.fk);
        const pk = (p.cols.find((x) => (x.k || "").includes("PK")) || p.cols[0] || { n: "" }).n;
        const cy = rowY(c, r.fk), py = rowY(p, pk);
        let cx, px, cs, ps;
        if (r.parent === r.child) {
          cx = c.x + c.w; px = p.x + p.w; cs = 1; ps = 1;
        } else if (c.x + c.w + 30 < p.x) { cx = c.x + c.w; cs = 1; px = p.x; ps = -1; }
        else if (p.x + p.w + 30 < c.x) { cx = c.x; cs = -1; px = p.x + p.w; ps = 1; }
        else { cx = c.x + c.w; px = p.x + p.w; cs = 1; ps = 1; }
        const d = Math.max(50, Math.abs(px - cx) / 2);
        const g = el("g", {}, gEdges);
        const color = MOD_OF[r.child] && !c.ext ? MOD_OF[r.child].color : "#555";
        el("path", { d: `M${cx},${cy} C${cx + cs * d},${cy} ${px + ps * d},${py} ${px},${py}`, fill: "none", stroke: color, "stroke-width": 1.4, opacity: 0.85,
          "stroke-dasharray": col && !col.nn ? "5 3" : undefined }, g);
        endMarks(g, cx, cy, cs, "many");
        endMarks(g, px, py, ps, col && col.nn ? "one" : "zeroOne");
      });
    }

    function drawTables() {
      gTables.innerHTML = "";
      Object.values(boxes).forEach((b) => {
        const m = MOD_OF[b.t] || { color: "#777" };
        const g = el("g", { "data-t": b.t, transform: `translate(${b.x},${b.y})`, style: "cursor:move" }, gTables);
        el("rect", { width: b.w, height: b.h, fill: "#fff", stroke: m.color, "stroke-width": b.ext ? 1.2 : 1.6, "stroke-dasharray": b.ext ? "5 3" : undefined }, g);
        el("rect", { width: b.w, height: HEAD, fill: b.ext ? "#fff" : m.color, stroke: m.color, "stroke-width": b.ext ? 1.2 : 1.6, "stroke-dasharray": b.ext ? "5 3" : undefined }, g);
        text(g, 8, 16, b.t, { fill: b.ext ? m.color : "#fff", bold: true, size: 12 });
        if (b.ext) text(g, b.w - 6, 16, MOD_OF[b.t] ? MOD_OF[b.t].id : "", { fill: m.color, size: 10, anchor: "end", bold: true });
        b.cols.forEach((c, i) => {
          const y = HEAD + i * ROW + 13;
          const tg = tag(c);
          if (i % 2) el("rect", { x: 1, y: HEAD + i * ROW + 1, width: b.w - 2, height: ROW, fill: "#f6f7f8" }, g);
          text(g, 6, y, tg, { size: 9.5, bold: true, fill: tg.includes("PK") ? "#a15c00" : "#555" });
          text(g, 38, y, c.n, { size: 11, bold: tg.includes("PK"), underline: tg.includes("PK"), italic: tg.includes("FK") && !tg.includes("PK") });
          text(g, b.w - 6, y, (opts.typeFn || shortType)(c.t).slice(0, 16), { size: 9.5, fill: "#666", anchor: "end", mono: true });
        });
      });
    }

    function drawLegend(x, y) {
      gLegend.innerHTML = "";
      if (opts.noLegend) return;
      const items = opts.legendModules || MODULES;
      text(gLegend, x, y, "Keterangan", { bold: true, size: 12 });
      items.forEach((m, i) => {
        const cx = x + (i % 3) * 270, cy = y + 14 + Math.floor(i / 3) * 20;
        el("rect", { x: cx, y: cy, width: 14, height: 14, fill: m.color }, gLegend);
        text(gLegend, cx + 20, cy + 11, `${m.id} ${m.name}`, { size: 11 });
      });
      const ly = y + 14 + Math.ceil(items.length / 3) * 20 + 12;
      const g = el("g", {}, gLegend);
      el("path", { d: `M${x},${ly} L${x + 60},${ly}`, stroke: "#1d1f22", "stroke-width": 1.4 }, g); endMarks(g, x, ly, 1, "many"); endMarks(g, x + 60, ly, -1, "one");
      text(gLegend, x + 70, ly + 4, "FK wajib: induk tepat satu (||), anak nol atau banyak (o<)", { size: 11 });
      el("path", { d: `M${x + 420},${ly} L${x + 480},${ly}`, stroke: "#1d1f22", "stroke-width": 1.4, "stroke-dasharray": "5 3" }, g); endMarks(g, x + 420, ly, 1, "many"); endMarks(g, x + 480, ly, -1, "zeroOne");
      text(gLegend, x + 490, ly + 4, "FK boleh kosong: induk nol atau satu (o|)", { size: 11 });
      text(gLegend, x, ly + 24, "PK = primary key (garis bawah) · FK = foreign key (miring) · UK = unique/alternate key · kotak putus-putus = tabel dari modul lain", { size: 11, fill: "#444" });
    }

    function fit() {
      const bs = Object.values(boxes);
      const mods = modBoxes();
      const minX = Math.min(...bs.map((b) => b.x), ...mods.map((m) => m.x0)) - 20;
      const minY = Math.min(...bs.map((b) => b.y), ...mods.map((m) => m.y0)) - 20;
      const maxX = Math.max(...bs.map((b) => b.x + b.w), ...mods.map((m) => m.x1)) + 60;
      const maxY = Math.max(...bs.map((b) => b.y + b.h), ...mods.map((m) => m.y1)) + 20;
      const legendH = opts.noLegend ? 0 : 50 + Math.ceil((opts.legendModules || MODULES).length / 3) * 20 + 40;
      drawLegend(minX + 20, maxY + 20);
      const w = Math.max(maxX - minX, 860), h = maxY - minY + legendH;
      svg.setAttribute("viewBox", `${minX} ${minY} ${w} ${h}`);
      svg.setAttribute("width", w); svg.setAttribute("height", h);
      let bg = svg.querySelector("rect.bg");
      if (!bg) { bg = el("rect", { class: "bg", fill: "#fff" }); svg.insertBefore(bg, svg.firstChild); }
      bg.setAttribute("x", minX); bg.setAttribute("y", minY); bg.setAttribute("width", w); bg.setAttribute("height", h);
    }

    function redraw() { drawMods(); drawEdges(); drawTables(); fit(); }
    redraw();
    host.append(svg);

    // geser tabel atau seluruh modul
    let drag = null;
    const pt = (e) => { const p = svg.createSVGPoint(); p.x = e.clientX; p.y = e.clientY; return p.matrixTransform(svg.getScreenCTM().inverse()); };
    svg.addEventListener("pointerdown", (e) => {
      const tg = e.target.closest("[data-t]"), mg = e.target.closest("[data-mod]");
      if (!tg && !mg) return;
      const p = pt(e);
      const names = tg ? [tg.dataset.t] : MODULES.find((m) => m.id === mg.dataset.mod).tables.filter((t) => boxes[t]);
      drag = { p, names, start: names.map((t) => [boxes[t].x, boxes[t].y]) };
      svg.setPointerCapture(e.pointerId);
      e.preventDefault();
    });
    svg.addEventListener("pointermove", (e) => {
      if (!drag) return;
      const p = pt(e), dx = p.x - drag.p.x, dy = p.y - drag.p.y;
      drag.names.forEach((t, i) => { boxes[t].x = Math.round((drag.start[i][0] + dx) / 2) * 2; boxes[t].y = Math.round((drag.start[i][1] + dy) / 2) * 2; });
      drawMods(); drawEdges(); drawTables();
    });
    svg.addEventListener("pointerup", () => {
      if (!drag) return;
      drag = null; fit();
      save(opts.key, Object.fromEntries(Object.values(boxes).map((b) => [b.t, [b.x, b.y]])));
    });
    return { svg, rels };
  }

  function load(key) { try { return JSON.parse(localStorage.getItem("erd." + key) || "null"); } catch (e) { return null; } }
  function save(key, v) { try { localStorage.setItem("erd." + key, JSON.stringify(v)); } catch (e) {} }
  function reset(key) { try { localStorage.removeItem("erd." + key); } catch (e) {} }

  /* Urutkan tabel modul menurut kedalaman ketergantungan (induk di kiri). */
  function depthOrder(tables) {
    const rels = window.SKRIPSI_DATA.rels.filter((r) => tables.includes(r.parent) && tables.includes(r.child) && r.parent !== r.child);
    const depth = {};
    const get = (t, seen = new Set()) => {
      if (depth[t] !== undefined) return depth[t];
      if (seen.has(t)) return 0;
      seen.add(t);
      const ps = rels.filter((r) => r.child === t).map((r) => r.parent);
      return (depth[t] = ps.length ? 1 + Math.max(...ps.map((p) => get(p, seen))) : 0);
    };
    tables.forEach((t) => get(t));
    return depth;
  }

  /* Tata letak satu modul mulai (x0, y0): kolom per kedalaman. Mengembalikan lebar & tinggi. */
  function layoutModule(boxes, m, x0, y0) {
    const ts = m.tables.filter((t) => boxes[t]);
    const depth = depthOrder(ts);
    const maxD = Math.max(0, ...Object.values(depth));
    let w = 0, h = 0;
    for (let d = 0; d <= maxD; d++) {
      let y = y0;
      ts.filter((t) => depth[t] === d).forEach((t) => { boxes[t].x = x0 + d * (W + 60); boxes[t].y = y; y += boxes[t].h + GAP; });
      w = Math.max(w, d * (W + 60) + W); h = Math.max(h, y - y0 - GAP);
    }
    return { w, h };
  }

  function layoutWhole(boxes) {
    const sizes = {};
    MODULES.forEach((m) => (sizes[m.id] = layoutModule(boxes, m, 0, 0)));
    const colW = [0, 1, 2].map((c) => Math.max(...GRID.map((row) => sizes[row[c]].w)));
    const rowH = GRID.map((row) => Math.max(...row.map((id) => sizes[id].h)));
    const MG = 90;
    GRID.forEach((row, r) => row.forEach((id, c) => {
      const x0 = colW.slice(0, c).reduce((a, b) => a + b + 2 * PAD + MG, 0) + PAD;
      const y0 = rowH.slice(0, r).reduce((a, b) => a + b + 2 * PAD + TITLE + MG, 0) + PAD + TITLE;
      layoutModule(boxes, MODULES.find((m) => m.id === id), x0, y0);
    }));
  }

  function layoutOne(m) {
    return (boxes) => {
      const { w, h } = layoutModule(boxes, m, 0, 0);
      const exts = Object.values(boxes).filter((b) => b.ext);
      const D = window.SKRIPSI_DATA;
      const parents = exts.filter((b) => D.rels.some((r) => r.parent === b.t && m.tables.includes(r.child)));
      const children = exts.filter((b) => !parents.includes(b));
      let y = 0;
      parents.forEach((b) => { b.x = -W - 150; b.y = y; y += b.h + GAP; });
      y = 0;
      children.forEach((b) => { b.x = w + 150; b.y = y; y += b.h + GAP; });
      void h;
    };
  }

  /* Tabel luar yang terhubung ke modul m, beserta kolom yang perlu ditampilkan. */
  function externals(m, hideBook) {
    const D = window.SKRIPSI_DATA;
    const ext = {};
    D.rels.forEach((r) => {
      if (hideBook && BOOKKEEPING.has(r.fk)) return;
      const pIn = m.tables.includes(r.parent), cIn = m.tables.includes(r.child);
      if (pIn === cIn) return;
      if (!pIn) { const pk = D.tables[r.parent].cols.find((c) => (c.k || "").includes("PK")); (ext[r.parent] = ext[r.parent] || new Set()).add(pk.n); }
      else { const T = D.tables[r.child]; (ext[r.child] = ext[r.child] || new Set()).add(T.cols.find((c) => (c.k || "").includes("PK")).n); ext[r.child].add(r.fk); }
    });
    return Object.fromEntries(Object.entries(ext).map(([k, v]) => [k, [...v]]));
  }

  window.ERDSVG = { MODULES, MOD_OF, BOOKKEEPING, GRID, render, reset, layoutWhole, layoutOne, externals };
})();
