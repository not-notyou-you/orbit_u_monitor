/* Bangun teks Mermaid erDiagram per modul dari SKRIPSI_DATA (skema nyata). */
(function () {
  const MODULES = [
    { id: "akses", name: "Akses, laporan, dan jejak",
      tables: ["roles", "users", "api_tokens", "user_activity_logs", "audit_log", "app_settings", "report_types", "generated_reports"] },
    { id: "pantau", name: "Rujukan dan pemantauan (observasi, peringatan, kejadian, forecast)",
      tables: ["satellite_sources", "spectral_bands", "administrative_regions", "region_observations", "alert_rules", "alert_events",
               "disaster_types", "disaster_events", "band_forecasts", "band_forecast_points", "band_forecast_scores", "quality_thresholds"] },
    { id: "proses", name: "Akuisisi, pemrosesan, lineage, dan mutu",
      tables: ["regions_of_interest", "satellite_scenes", "nasa_scenes", "processing_stages", "processing_jobs", "processing_logs",
               "data_products", "data_lineage", "quality_metrics", "quality_alerts"] },
    { id: "dataset", name: "Dataset, fusion, dan Live",
      tables: ["datasets", "dataset_source_config", "dataset_jobs", "scene_job_state", "cleanup_operations", "fusion_strategies",
               "fusion_products", "live_areas", "live_scenes", "live_scene_metrics", "live_events"] },
  ];

  function shortType(t, physical) {
    let s = t.toLowerCase();
    if (physical) {
      s = s.replace("character varying", "varchar").replace("timestamp with time zone", "timestamptz")
        .replace("timestamp without time zone", "timestamp").replace("double precision", "float8")
        .replace(/geometry\(([a-z]+),\s*4326\)/i, "geometry_$1").replace("user-defined", "enum").replace(/\[\]$/, "_array");
      return s.replace(/[^a-z0-9_]/g, "_").replace(/_+$/, "");
    }
    if (/int|serial/.test(s)) return "integer";
    if (/numeric|double|real/.test(s)) return "decimal";
    if (/varying|char|text/.test(s)) return s.endsWith("[]") ? "list" : "string";
    if (/timestamp/.test(s)) return "datetime";
    if (/^date/.test(s)) return "date";
    if (/bool/.test(s)) return "boolean";
    if (/geometry|geography/.test(s)) return "geometry";
    if (/json/.test(s)) return "document";
    if (/uuid/.test(s)) return "uuid";
    if (/inet/.test(s)) return "address";
    return "enum";
  }

  function keyTag(k) {
    const tags = [];
    if (k.includes("PK")) tags.push("PK");
    if (k.includes("FK")) tags.push("FK");
    if (k.includes("UNIQUE") && !k.includes("PK")) tags.push("UK");
    return tags.join(",");
  }

  function relLine(r, tables) {
    const child = tables[r.child];
    const col = child && child.cols.find((c) => c.n === r.fk);
    const optionalParent = col ? !col.nn : true;
    const left = optionalParent ? "|o" : "||";
    return `    ${r.parent} ${left}--o{ ${r.child} : "${r.fk}"`;
  }

  /* mode: "logical" (kunci + atribut tanpa tipe fisik) atau "physical" (semua kolom + tipe PostgreSQL) */
  function moduleErd(mod, mode) {
    const D = window.SKRIPSI_DATA;
    const inMod = new Set(mod.tables);
    const rels = D.rels.filter((r) => inMod.has(r.child) || inMod.has(r.parent));
    const ext = new Set();
    rels.forEach((r) => { if (!inMod.has(r.parent)) ext.add(r.parent); if (!inMod.has(r.child)) ext.add(r.child); });
    const L = ["erDiagram"];
    const physical = mode === "physical";
    mod.tables.forEach((t) => {
      const T = D.tables[t];
      if (!T) return;
      L.push(`    ${t} {`);
      T.cols.forEach((c) => {
        const tag = keyTag(c.k);
        if (!physical && !tag && mode === "keys") return;
        L.push(`        ${shortType(c.t, physical)} ${c.n}${tag ? " " + tag : ""}`);
      });
      L.push("    }");
    });
    [...ext].forEach((t) => {
      const T = D.tables[t];
      if (!T) return;
      L.push(`    ${t} {`);
      T.cols.filter((c) => c.k.includes("PK")).forEach((c) => L.push(`        ${shortType(c.t, physical)} ${c.n} PK`));
      L.push("    }");
    });
    rels.forEach((r) => L.push(relLine(r, D.tables)));
    return { text: L.join("\n"), ext: [...ext] };
  }

  function multiplicity(r) {
    const D = window.SKRIPSI_DATA;
    const col = D.tables[r.child] && D.tables[r.child].cols.find((c) => c.n === r.fk);
    const child = D.tables[r.child];
    const uniqueFk = col && col.k.includes("UNIQUE") && child.cons.some((k) => k.type === "UNIQUE" && new RegExp(`\\(${r.fk}\\)`).test(k.def));
    return { parent: col && col.nn ? "1" : "0..1", child: uniqueFk ? "0..1" : "0..*", nullable: col ? !col.nn : true };
  }

  function fkAction(r) {
    const D = window.SKRIPSI_DATA;
    const T = D.tables[r.child];
    const k = T && T.cons.find((c) => c.type === "FK" && new RegExp(`^FOREIGN KEY \\(${r.fk}\\)`).test(c.def));
    if (!k) return "";
    const del = (k.def.match(/ON DELETE (CASCADE|SET NULL|RESTRICT|SET DEFAULT)/) || [])[1] || "NO ACTION";
    const upd = (k.def.match(/ON UPDATE (CASCADE|SET NULL|RESTRICT)/) || [])[1];
    return del + (upd ? ` / ON UPDATE ${upd}` : "");
  }

  window.ERD = { MODULES, moduleErd, multiplicity, fkAction, shortType };
})();
