# etl/report_datahealth.py
"""Laporan Kesehatan Data mingguan/bulanan untuk DATA_ENGINEER (PIPELINE.md §6.3).

Delapan bagian; semua angka dari DB (dan checksum berkas untuk sampel
lineage). Bagian tanpa data -> "—". Batas waktu periode untuk kolom
TIMESTAMPTZ dihitung dalam WIB (00:00 Senin s.d. 23:59 Minggu).
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime, time, timedelta
from pathlib import Path

from sqlalchemy import text

from etl.report_periodic import DASH, WIB, Doc, num, pct, txt

TITLE = {"DATAHEALTH_WEEKLY": "Laporan Kesehatan Data Mingguan",
         "DATAHEALTH_MONTHLY": "Laporan Kesehatan Data Bulanan"}
SOURCES = ("SENTINEL1", "MODIS", "GPM")
GAP_DAYS = 10


def _bounds(start: date, end: date) -> tuple[datetime, datetime]:
    return (datetime.combine(start, time(0), tzinfo=WIB),
            datetime.combine(end + timedelta(days=1), time(0), tzinfo=WIB))


def _sha256(path: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def build(sess, code: str, start: date, end: date, workdir: Path, notes: list[str]) -> Doc:
    doc = Doc(TITLE[code], "Orbit-U: The Monitor — kelengkapan, kualitas, pipeline, lineage", (start, end),
              workdir=workdir)
    for n in notes:
        doc.note(n)
    t0, t1 = _bounds(start, end)
    n_days = (end - start).days + 1
    P = {"a": start, "b": end, "t0": t0, "t1": t1}

    present = dict(sess.execute(text("""SELECT source_code, count(DISTINCT data_date) FROM v_kelengkapan_data
                                        WHERE data_date BETWEEN :a AND :b GROUP BY source_code"""), P).all())
    s1_score = sess.scalar(text("SELECT avg(quality_score) FROM quality_metrics WHERE assessed_at >= :t0 AND assessed_at < :t1"), P)
    vf = sess.scalar(text("SELECT avg(valid_fraction) FROM region_observations WHERE obs_date BETWEEN :a AND :b"), P)

    # 1 -------------------------------------------------------------------------
    doc.h1("1. Skor kesehatan")
    completeness = None
    if present:
        completeness = sum(min(1.0, present.get(s, 0) / n_days) for s in ("MODIS", "GPM")) / 2 * 100
    comps = {"Kelengkapan harian MODIS + GPM": completeness,
             "Kualitas radiometrik S1 (rerata quality_score)": None if s1_score is None else float(s1_score),
             "Cakupan spasial (rerata valid_fraction × 100)": None if vf is None else float(vf) * 100}
    avail = [v for v in comps.values() if v is not None]
    doc.kv([(k, num(v, 1, "/ 100")) for k, v in comps.items()]
           + [("Skor kesehatan (rerata komponen yang tersedia)", num(sum(avail) / len(avail), 1, "/ 100") if avail else DASH)])
    doc.note("Adaptasi skor DataLab REPORT §9.1: komponen tanpa data pada periode ini tidak dihitung "
             "(ditulis —), bukan dianggap nol.")

    # 2 -------------------------------------------------------------------------
    doc.h1("2. Kelengkapan per sumber")
    gaps = sess.execute(text("""SELECT source_code, count(*) AS n, max(gap_days) AS longest FROM v_kelengkapan_data
                                WHERE data_date BETWEEN :a AND :b AND is_gap GROUP BY source_code"""), P).mappings().all()
    gmap = {g["source_code"]: g for g in gaps}
    doc.table(["Sumber", "Hari ada data", "Hari tanpa data", f"Gap > {GAP_DAYS} hari", "Gap terpanjang (hari)"],
              [[s, str(present.get(s, 0)), str(n_days - present.get(s, 0)),
                str((gmap.get(s) or {}).get("n") or 0), num((gmap.get(s) or {}).get("longest"), 0)] for s in SOURCES])
    runs = dict(sess.execute(text("""SELECT COALESCE(run_type, '?'), count(*) FROM nasa_scenes
                                     WHERE source = 'GPM' AND acquisition_date BETWEEN :a AND :b
                                     GROUP BY 1"""), P).all())
    doc.h2("Run GPM IMERG")
    doc.table(["Final (F)", "Late (L)", "Early (E)", "Tidak tercatat"],
              [[str(runs.get("F", 0)), str(runs.get("L", 0)), str(runs.get("E", 0)), str(runs.get("?", 0))]]
              if runs else [])

    # 3 -------------------------------------------------------------------------
    doc.h1("3. Kualitas")
    q = sess.execute(text("""SELECT source_code, week_start, n_quality_metrics, avg_quality_score, n_fail, n_warning,
                                    n_quality_alerts, n_observations, avg_valid_fraction
                             FROM v_ringkasan_kualitas WHERE week_start BETWEEN :a - 6 AND :b
                             ORDER BY week_start, source_code"""), P).mappings().all()
    doc.table(["Sumber", "Minggu", "Metrik S1", "Skor rerata", "FAIL", "WARNING", "Quality alert", "Observasi", "valid_fraction"],
              [[r["source_code"], r["week_start"].isoformat(), str(r["n_quality_metrics"]), num(r["avg_quality_score"]),
                str(r["n_fail"]), str(r["n_warning"]), str(r["n_quality_alerts"]), str(r["n_observations"]),
                num(r["avg_valid_fraction"], 3)] for r in q])

    # 4 -------------------------------------------------------------------------
    doc.h1("4. Pipeline")
    jobs = sess.execute(text("""
        SELECT s.stage_name, count(*) AS n,
               count(*) FILTER (WHERE j.status = 'SUCCESS') AS ok,
               count(*) FILTER (WHERE j.status = 'FAILED') AS failed,
               count(*) FILTER (WHERE j.status IN ('WAITING_UPSTREAM', 'SKIPPED_LOCKED')) AS waiting,
               avg(j.duration_seconds) AS dur
        FROM processing_jobs j JOIN processing_stages s USING (stage_id)
        WHERE j.queued_at >= :t0 AND j.queued_at < :t1
        GROUP BY s.stage_name ORDER BY s.stage_name"""), P).mappings().all()
    doc.table(["Tahap", "Job", "Sukses", "Gagal", "Menunggu/dilewati", "Durasi rerata (s)"],
              [[j["stage_name"], str(j["n"]), str(j["ok"]), str(j["failed"]), str(j["waiting"]), num(j["dur"], 1)]
               for j in jobs])
    kinds = sess.execute(text("""
        SELECT CASE WHEN d.is_system THEN 'A (hidromet)' WHEN d.dataset_kind = 'LIVE_AREA' THEN 'B (Live)'
                    ELSE 'C (dataset)' END AS kind, dj.status, count(*) AS n
        FROM dataset_jobs dj JOIN datasets d USING (dataset_id)
        WHERE dj.created_at >= :t0 AND dj.created_at < :t1 OR dj.started_at >= :t0 AND dj.started_at < :t1
        GROUP BY 1, 2 ORDER BY 1, 2"""), P).mappings().all()
    doc.h2("Job per jenis pekerjaan")
    doc.table(["Jenis", "Status", "Jumlah"], [[k["kind"], k["status"], str(k["n"])] for k in kinds])
    errs = sess.execute(text("""
        SELECT COALESCE(error_code, '?') AS code, left(COALESCE(error_message, ''), 120) AS msg, count(*) AS n
        FROM processing_jobs WHERE status = 'FAILED' AND queued_at >= :t0 AND queued_at < :t1
        GROUP BY 1, 2 ORDER BY n DESC LIMIT 5"""), P).mappings().all()
    doc.h2("Error terbanyak")
    doc.table(["Kode", "Pesan", "Jumlah"], [[e["code"], txt(e["msg"]), str(e["n"])] for e in errs],
              empty="Tidak ada job gagal pada periode ini.")

    # 5 -------------------------------------------------------------------------
    doc.h1("5. Lineage")
    tiers = sess.execute(text("""SELECT product_tier::text AS tier, count(*) AS n FROM data_products
                                 WHERE created_at >= :t0 AND created_at < :t1 GROUP BY 1 ORDER BY 1"""), P).mappings().all()
    doc.table(["Tier", "Produk baru"], [[t["tier"], str(t["n"])] for t in tiers])
    sample = sess.execute(text("""SELECT product_id, file_path, data_hash_sha256, band_name, source FROM data_products
                                  WHERE created_at >= :t0 AND created_at < :t1 AND product_tier = 'COG'
                                  ORDER BY random() LIMIT 1"""), P).mappings().first()
    doc.h2("Sampel rantai lineage")
    if sample is None:
        doc.p(DASH)
        doc.note("Tidak ada produk COG baru pada periode ini.")
    else:
        chain, current, seen = [], sample["product_id"], set()
        while current is not None and current not in seen and len(chain) < 10:
            seen.add(current)
            prod = sess.execute(text("""SELECT product_id, product_tier::text AS tier, band_name, file_path,
                                               data_hash_sha256 FROM data_products WHERE product_id = :p"""),
                                {"p": current}).mappings().first()
            if prod is None:
                break
            actual = _sha256(Path(prod["file_path"]))
            status = DASH if actual is None else ("cocok" if actual == prod["data_hash_sha256"] else "TIDAK cocok")
            chain.append([str(prod["product_id"]), prod["tier"], prod["band_name"], Path(prod["file_path"]).name,
                          "berkas tidak ada" if actual is None else status])
            current = sess.scalar(text("""SELECT parent_product_id FROM data_lineage WHERE child_product_id = :c
                                          ORDER BY lineage_id LIMIT 1"""), {"c": current})
        doc.table(["product_id", "Tier", "Band", "Berkas", "Checksum SHA-256"], chain)

    # 6 -------------------------------------------------------------------------
    doc.h1("6. Fusion")
    fus = sess.execute(text("""
        SELECT COALESCE(fusion_strategy, '?') AS strategy, count(*) AS n,
               avg(abs(temporal_offset_modis)) AS off_modis, avg(abs(temporal_offset_gpm)) AS off_gpm,
               count(*) FILTER (WHERE s1_scene_id IS NOT NULL) AS with_s1
        FROM fusion_products WHERE created_at >= :t0 AND created_at < :t1 GROUP BY 1 ORDER BY 1"""), P).mappings().all()
    doc.table(["Strategi", "Stack", "Offset MODIS rerata (hari)", "Offset GPM rerata (hari)", "Cakupan S1"],
              [[f["strategy"], str(f["n"]), num(f["off_modis"], 1), num(f["off_gpm"], 1), pct(f["with_s1"], f["n"])]
               for f in fus], empty="Tidak ada stack fusion dibuat pada periode ini.")

    # 7 -------------------------------------------------------------------------
    doc.h1("7. Penyimpanan")
    store = sess.execute(text("""
        SELECT CASE WHEN d.is_system THEN 'A (hidromet)' WHEN d.dataset_kind = 'LIVE_AREA' THEN 'B (Live)'
                    WHEN d.dataset_id IS NULL THEN '?' ELSE 'C (dataset)' END AS kind,
               p.product_tier::text AS tier, count(*) AS n, sum(p.file_size_mb) AS mb
        FROM data_products p LEFT JOIN datasets d USING (dataset_id)
        WHERE p.is_latest GROUP BY 1, 2 ORDER BY 1, 2""")).mappings().all()
    doc.table(["Jenis pekerjaan", "Tier", "Produk", "Ukuran (MB)"],
              [[s["kind"], s["tier"], str(s["n"]), num(s["mb"], 1)] for s in store])
    freed = sess.execute(text("""SELECT count(*) AS n, COALESCE(sum(freed_bytes), 0) AS b FROM live_scenes
                                 WHERE deleted_at >= :t0 AND deleted_at < :t1"""), P).mappings().one()
    doc.kv([("Scene Live dihapus retensi", str(freed["n"])),
            ("Ruang dibebaskan", num(freed["b"] / 1024 ** 2, 1, "MB") if freed["n"] else DASH)])
    doc.note("Ukuran dari data_products (is_latest) saat laporan dibuat, bukan pemindaian disk.")

    # 8 -------------------------------------------------------------------------
    doc.h1("8. Unduhan")
    dl = sess.execute(text("""SELECT action, role_code, sum(n_downloads) AS n, sum(bytes_sent) AS b
                              FROM v_unduhan_per_role WHERE log_date_wib BETWEEN :a AND :b
                              GROUP BY 1, 2 ORDER BY 1, 2"""), P).mappings().all()
    doc.table(["Jenis", "Role", "Jumlah", "Volume (MB)"],
              [[d["action"], d["role_code"], str(d["n"]), num((d["b"] or 0) / 1024 ** 2, 2)] for d in dl],
              empty="Tidak ada unduhan pada periode ini.")
    doc.note("Tanpa nama pengguna: dikelompokkan per role.")
    return doc
