# etl/report_hydromet.py
"""Laporan Hidromet mingguan/bulanan untuk ANALYST (PIPELINE.md §6.2).

Sembilan bagian; semua angka dibaca dari DB pada periode itu. Bagian tanpa
data menampilkan tabel "—" dan catatan, tidak pernah angka contoh.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import text

from etl import report_generator as rg
from etl.report_periodic import DASH, Doc, is_monthly, num, txt

RAIN_DAY_MM = 0.1      # hari hujan (§6.2 bagian 1)
TITLE = {"HYDROMET_WEEKLY": "Laporan Hidromet Mingguan", "HYDROMET_MONTHLY": "Laporan Hidromet Bulanan"}

LIMITATIONS = [
    "GPM IMERG beresolusi ±0,1° (±11 km): satu kecamatan hanya mencakup 1–6 sel, sehingga hujan lokal "
    "yang sangat terpusat bisa tidak terwakili. Nilai kecamatan adalah rerata berbobot luas irisan sel.",
    "Run IMERG Late/Early belum dikalibrasi penakar hujan; nilai diganti otomatis oleh Final Run ±3,5 bulan "
    "kemudian. Alert yang sudah terpicu tidak diubah (catatan apa yang diketahui saat itu).",
    "MODIS optik terhalang awan; nilai kecamatan dengan piksel valid < 10% ditulis kosong.",
    "Sentinel-1 melintas setiap 6–12 hari, jadi genangan singkat (banjir bandang) bisa tidak terekam; "
    "peta perubahan air memakai ambang tetap VH −20 dB.",
    "Tanggal data hidromet adalah hari UTC (07:00–07:00 WIB).",
]


def _days(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def _rain(sess, start, end):
    """{(region_id, date): {band: value}}, daftar kecamatan AOI."""
    regions = sess.execute(text("""SELECT region_id, pcode, region_name, area_km2 FROM administrative_regions
                                   WHERE in_aoi ORDER BY region_name""")).mappings().all()
    rows = sess.execute(text("""
        SELECT region_id, obs_date, rain_24h_mm, rain_72h_mm, rain_7d_mm, rain_30d_mm, gpm_run
        FROM v_hujan_harian_kecamatan WHERE obs_date BETWEEN :a AND :b"""), {"a": start, "b": end}).mappings().all()
    data = {(r["region_id"], r["obs_date"]): r for r in rows}
    return regions, data


def _aoi_mean(values: list) -> float | None:
    vals = [float(v) for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


def build(sess, code: str, start: date, end: date, workdir: Path, notes: list[str]) -> Doc:
    doc = Doc(TITLE[code], "Gugus Mitigasi Lebak Selatan — AOI GMLS, Kabupaten Lebak", (start, end), workdir=workdir)
    for n in notes:
        doc.note(n)
    days = _days(start, end)
    regions, rain = _rain(sess, start, end)

    aoi24 = {d: _aoi_mean([rain.get((r["region_id"], d), {}).get("rain_24h_mm") for r in regions]) for d in days}
    aoi72 = {d: _aoi_mean([rain.get((r["region_id"], d), {}).get("rain_72h_mm") for r in regions]) for d in days}
    days_with_data = [d for d in days if aoi24[d] is not None]
    totals = {}
    for r in regions:
        vals = [rain.get((r["region_id"], d), {}).get("rain_24h_mm") for d in days]
        vals = [float(v) for v in vals if v is not None]
        totals[r["region_id"]] = sum(vals) if vals else None
    alerts = sess.execute(text("""
        SELECT a.alert_id, a.observation_date, a.region_id, r.region_name, ru.rule_code, a.severity,
               a.observed_value, a.threshold_value, a.triggered_at, a.acknowledged_at
        FROM alert_events a JOIN alert_rules ru USING (rule_id)
        JOIN administrative_regions r ON r.region_id = a.region_id
        WHERE a.observation_date BETWEEN :a AND :b
        ORDER BY a.observation_date, r.region_name, a.threshold_value"""), {"a": start, "b": end}).mappings().all()
    events = sess.execute(text("""SELECT * FROM v_kejadian_dan_hujan WHERE event_date BETWEEN :a AND :b
                                  ORDER BY event_date, region_name"""), {"a": start, "b": end}).mappings().all()

    # 1 -------------------------------------------------------------------------
    doc.h1("1. Ringkasan eksekutif")
    total_aoi = _aoi_mean(list(totals.values()))
    heavy_days = [d for d in days if any(
        (rain.get((r["region_id"], d), {}).get("rain_24h_mm") or 0) >= 50 for r in regions)]
    doc.kv([
        ("Hari dengan data GPM", f"{len(days_with_data)} dari {len(days)} hari"),
        ("Total hujan AOI", num(total_aoi, 1, "mm") if days_with_data else DASH),
        ("Hari hujan (rerata AOI ≥ 0,1 mm)",
         str(sum(1 for d in days_with_data if aoi24[d] >= RAIN_DAY_MM)) if days_with_data else DASH),
        ("Hari lebat (≥ 50 mm di ≥ 1 kecamatan)", str(len(heavy_days)) if days_with_data else DASH),
        ("Jumlah alert", str(len(alerts))),
        ("Jumlah kejadian bencana tercatat", str(len(events))),
    ])
    doc.note("Total hujan AOI = rerata antar kecamatan AOI dari jumlah hujan 24 jam harian selama periode. "
             "Hari lebat memakai ambang BMKG hujan lebat (50 mm/hari).")

    # 2 -------------------------------------------------------------------------
    doc.h1("2. Hujan per kecamatan")
    header = ["Tanggal (UTC)"] + [r["region_name"] for r in regions]
    rows = [[d.isoformat()] + [num(rain.get((r["region_id"], d), {}).get("rain_24h_mm")) for r in regions]
            for d in days if any((r["region_id"], d) in rain for r in regions)]
    if rows:
        rows.append(["Total periode"] + [num(totals[r["region_id"]]) for r in regions])
    doc.table(header, rows, [1.0 * 72] + [(rg._TEXT_W - 72) / max(1, len(regions))] * len(regions))
    if regions and any(v is not None for v in totals.values()):
        _choropleth(doc, sess, totals)
    else:
        doc.note("Peta koroplet tidak dibuat: tidak ada data hujan pada periode ini.")

    # 3 -------------------------------------------------------------------------
    doc.h1("3. Grafik hujan 24 jam dan 72 jam")
    thresholds = sess.execute(text("""
        SELECT b.band_code, ru.threshold_value, ru.severity FROM alert_rules ru JOIN spectral_bands b USING (band_id)
        WHERE ru.is_active AND ru.threshold_value IS NOT NULL AND b.band_code IN ('RAIN_24H', 'RAIN_72H')
        ORDER BY ru.threshold_value""")).all()
    if days_with_data:
        _rain_chart(doc, days, aoi24, aoi72, thresholds)
    else:
        doc.p(DASH)
        doc.note("Grafik tidak dibuat: tidak ada data hujan pada periode ini.")

    # 4 -------------------------------------------------------------------------
    doc.h1("4. Alert")
    def _resp(a):
        if a["acknowledged_at"] is None:
            return DASH
        h = (a["acknowledged_at"] - a["triggered_at"]).total_seconds() / 3600
        return num(h, 1, "jam")
    doc.table(["Tanggal", "Kecamatan", "Aturan", "Severity", "Nilai (mm)", "Ambang", "Status", "Waktu tanggap"],
              [[a["observation_date"].isoformat(), a["region_name"], a["rule_code"], a["severity"],
                num(a["observed_value"]), num(a["threshold_value"], 0),
                "dibaca" if a["acknowledged_at"] else "aktif", _resp(a)] for a in alerts],
              empty="Tidak ada alert pada periode ini.")

    # 5 -------------------------------------------------------------------------
    doc.h1("5. Kejadian bencana dan hujan H-0..H-2")
    doc.table(["Tanggal", "Jenis", "Kecamatan", "Desa", "Terverifikasi", "24h H-0", "24h H-1", "24h H-2", "72h H-0"],
              [[e["event_date"].isoformat(), e["disaster_type_code"], e["region_name"], txt(e["village_name"]),
                "ya" if e["is_verified"] else "tidak", num(e["rain_24h_h0"]), num(e["rain_24h_h1"]),
                num(e["rain_24h_h2"]), num(e["rain_72h_h0"])] for e in events],
              empty="Tidak ada kejadian bencana tercatat pada periode ini.")

    # 6 -------------------------------------------------------------------------
    doc.h1("6. Evaluasi alert")
    if is_monthly(code):
        counts = dict(sess.execute(text("""SELECT outcome, count(*) FROM v_evaluasi_alert
                                           WHERE ref_date <= :b GROUP BY outcome"""), {"b": end}).all())
        hit, miss, fa = (int(counts.get(k, 0)) for k in ("HIT", "MISS", "FALSE_ALARM"))
        doc.kv([("Hit", str(hit)), ("Miss", str(miss)), ("False alarm", str(fa)),
                ("Probability of detection", num(100 * hit / (hit + miss), 1, "%") if hit + miss else DASH),
                ("False alarm ratio", num(100 * fa / (hit + fa), 1, "%") if hit + fa else DASH)])
        doc.note("Kumulatif sejak awal arsip sampai akhir periode: alert WARNING/CRITICAL dibanding kejadian "
                 "terverifikasi sejenis di kecamatan yang sama, alert 0–3 hari sebelum kejadian.")
    else:
        doc.p("Hanya dimuat di laporan bulanan.")

    # 7 -------------------------------------------------------------------------
    doc.h1("7. Vegetasi dan genangan")
    veg = sess.execute(text("""
        SELECT o.region_id, b.band_code, avg(o.value) AS v, count(o.value) AS n
        FROM region_observations o JOIN spectral_bands b USING (band_id)
        WHERE o.obs_date BETWEEN :a AND :b AND b.band_code IN ('NDVI', 'FLOOD')
        GROUP BY o.region_id, b.band_code"""), {"a": start, "b": end}).mappings().all()
    vmap = {(r["region_id"], r["band_code"]): r for r in veg}
    rain30 = {r["region_id"]: rain.get((r["region_id"], end), {}).get("rain_30d_mm") for r in regions}
    vrows = [[r["region_name"], num((vmap.get((r["region_id"], "NDVI")) or {}).get("v"), 2),
              num((vmap.get((r["region_id"], "FLOOD")) or {}).get("v"), 2, "%"),
              str((vmap.get((r["region_id"], "NDVI")) or {}).get("n") or 0),
              num(rain30[r["region_id"]], 1, "mm")] for r in regions]
    doc.table(["Kecamatan", "NDVI rerata", "Genangan MODIS rerata", "Hari NDVI valid", f"Hujan 30 hari s.d. {end}"],
              vrows if any(v[1] != DASH or v[2] != DASH or v[4] != DASH for v in vrows) else [])
    doc.note("Indikator kekeringan: hujan 30 hari (RAIN_30D) yang rendah bersama NDVI yang turun.")

    # 8 -------------------------------------------------------------------------
    doc.h1("8. Ringkasan Live (Sentinel-1)")
    live = sess.execute(text("""
        SELECT a.name AS area_name, s.scene_date, s.status,
               max(m.value) FILTER (WHERE m.metric_name = 'new_km2')      AS new_km2,
               max(m.value) FILTER (WHERE m.metric_name = 'receded_km2')  AS receded_km2,
               max(m.value) FILTER (WHERE m.metric_name = 'same_orbit')   AS same_orbit
        FROM live_scenes s JOIN live_areas a ON a.area_id = s.area_id
        LEFT JOIN live_scene_metrics m ON m.live_scene_id = s.live_scene_id
             AND m.band_id = (SELECT band_id FROM spectral_bands WHERE band_code = 'WATER_CHANGE')
        WHERE s.scene_date BETWEEN :a AND :b AND s.status IN ('READY', 'PARTIAL', 'DELETED')
        GROUP BY a.name, s.scene_date, s.status ORDER BY s.scene_date"""), {"a": start, "b": end}).mappings().all()
    doc.table(["Area", "Tanggal scene", "Status", "Air baru (km²)", "Air surut (km²)", "Orbit sama"],
              [[l["area_name"], l["scene_date"].isoformat(), l["status"], num(l["new_km2"], 2),
                num(l["receded_km2"], 2), DASH if l["same_orbit"] is None else ("ya" if l["same_orbit"] else "tidak")]
               for l in live], empty="Tidak ada scene Sentinel-1 pada periode ini.")

    # 9 -------------------------------------------------------------------------
    doc.h1("9. Catatan keterbatasan")
    doc.bullets(LIMITATIONS)
    return doc


def _rain_chart(doc: Doc, days, aoi24, aoi72, thresholds) -> None:
    fig, ax = rg._fig()
    x = list(days)
    ax.bar(x, [aoi24[d] if aoi24[d] is not None else 0 for d in x], color="#4C72B0", label="24 jam (rerata AOI)")
    ax.plot(x, [aoi72[d] for d in x], color="#DD8452", marker="o", markersize=2.5, label="72 jam (rerata AOI)")
    for band, thr, sev in thresholds:
        ax.axhline(float(thr), linestyle="--", linewidth=0.8, color="#C44E52" if band == "RAIN_24H" else "#8172B3")
        ax.text(x[0], float(thr), f" {band} {sev} {float(thr):g} mm", fontsize=6, va="bottom", color="#555555")
    ax.set_ylabel("mm", fontsize=8)
    ax.legend(fontsize=7, frameon=False)
    fig.autofmt_xdate()
    doc.chart(fig, "Hujan harian rerata kecamatan AOI; garis putus = ambang aturan alert aktif.")


def _choropleth(doc: Doc, sess, totals: dict) -> None:
    import matplotlib.cm as cm
    import matplotlib.colors as mcolors
    from matplotlib import colormaps
    from matplotlib.patches import Polygon as MplPolygon

    geoms = sess.execute(text("""SELECT region_id, region_name,
                                        ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom, 0.001), 5) AS gj
                                 FROM administrative_regions WHERE in_aoi""")).mappings().all()
    vals = [v for v in totals.values() if v is not None]
    norm = mcolors.Normalize(vmin=min(vals), vmax=max(vals) if max(vals) > min(vals) else min(vals) + 1)
    cmap = colormaps["Blues"]
    fig, ax = rg._fig()
    ax.grid(False)
    for g in geoms:
        shape = json.loads(g["gj"])
        polys = shape["coordinates"] if shape["type"] == "MultiPolygon" else [shape["coordinates"]]
        v = totals.get(g["region_id"])
        face = cmap(norm(v)) if v is not None else "#EEEEEE"
        for poly in polys:
            ax.add_patch(MplPolygon(poly[0], closed=True, facecolor=face, edgecolor="#555555", linewidth=0.5))
            cx = sum(p[0] for p in poly[0]) / len(poly[0])
            cy = sum(p[1] for p in poly[0]) / len(poly[0])
        ax.text(cx, cy, g["region_name"], fontsize=5.5, ha="center")
    ax.autoscale_view()
    ax.set_aspect("equal")
    fig.colorbar(cm.ScalarMappable(norm=norm, cmap=cmap), ax=ax, label="mm", shrink=0.8)
    doc.chart(fig, "Total hujan 24 jam selama periode per kecamatan (abu-abu = tanpa data).")
