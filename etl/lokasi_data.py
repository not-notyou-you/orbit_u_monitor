# etl/lokasi_data.py
"""Angka, kalimat kondisi, dan citra SATU kecamatan (M63, M64).

Satu tempat untuk dua pemakai yang harus melihat hal yang sama:
* Beranda / Pantau Lokasi (api/routes/lokasi.py), di bawah role pemanggil;
* peringatan email (etl/notify.py), di bawah ``monitor_etl``.

Angka dibaca lewat VIEW ``v_public_lokasi_*``: batas waktunya per role
pemanggil (``monitor_etl`` = jendela pengunjung, 30 hari + dua observasi
terakhir per band). Kalimat kondisi dari etl/lokasi_interpret.py; ambang hujan
diselaraskan dengan ``alert_rules`` lewat sync_bmkg_thresholds.
"""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import text

# Kelompok grafik tren = baris tile (Sentinel-1, MODIS, GPM).
GROUPS = (
    ("s1", "Sentinel-1 (radar)", ("VV", "VH", "WATER_PCT")),
    ("modis", "MODIS (optik)", ("FLOOD", "NDVI", "NDWI")),
    ("gpm", "GPM (curah hujan)", ("RAIN_24H", "RAIN_72H", "RAIN_7D")),
)
TREND_BANDS = tuple(b for _g, _t, bands in GROUPS for b in bands)
SEV_RANK = {"INFO": 1, "WARNING": 2, "CRITICAL": 3}


def num(v):
    return None if v is None else float(v)


def regions(sess, region_ids=None) -> list[dict]:
    """Kecamatan AOI (semua, atau yang diminta), urut nama."""
    rows = sess.execute(text(
        "SELECT region_id, pcode, region_name AS name, area_km2 FROM administrative_regions "
        "WHERE admin_level = 3 AND in_aoi" + (" AND region_id = ANY(:ids)" if region_ids is not None else "")
        + " ORDER BY region_name"), {"ids": list(region_ids or [])}).mappings().all()
    return [{**r, "area_km2": num(r["area_km2"])} for r in rows]


def obs(sess, region_id: int | None = None) -> dict[int, tuple[dict, dict]]:
    """{region_id: (terbaru, sebelumnya)} per band, masing-masing
    {band_code: {value, obs_date, valid_fraction, run_type}}."""
    rows = sess.execute(text(f"""
        SELECT * FROM (
            SELECT o.*, row_number() OVER (PARTITION BY region_id, band_code ORDER BY obs_date DESC) AS rn
            FROM v_public_lokasi_obs o WHERE o.value IS NOT NULL {"AND o.region_id = :r" if region_id else ""}
        ) q WHERE rn <= 2"""), {"r": region_id}).mappings().all()
    out: dict[int, tuple[dict, dict]] = {}
    for r in rows:
        latest, prev = out.setdefault(r["region_id"], ({}, {}))
        (latest if r["rn"] == 1 else prev)[r["band_code"]] = {
            "value": num(r["value"]), "obs_date": r["obs_date"],
            "valid_fraction": num(r["valid_fraction"]), "run_type": r["run_type"]}
    return out


def ranges(sess, region_id: int | None = None) -> dict[int, dict]:
    rows = sess.execute(text(
        "SELECT * FROM v_public_lokasi_range" + (" WHERE region_id = :r" if region_id else "")),
        {"r": region_id}).mappings().all()
    out: dict[int, dict] = {}
    for r in rows:
        out.setdefault(r["region_id"], {})[r["band_code"]] = {"p02": num(r["p02"]), "p98": num(r["p98"])}
    return out


def alerts(sess, region_id: int | None = None) -> dict[int, list[dict]]:
    rows = sess.execute(text(
        "SELECT * FROM v_public_lokasi_alert" + (" WHERE region_id = :r" if region_id else "")
        + " ORDER BY observation_date DESC"), {"r": region_id}).mappings().all()
    out: dict[int, list[dict]] = {}
    for r in rows:
        out.setdefault(r["region_id"], []).append({
            "observation_date": r["observation_date"], "severity": r["severity"], "band_code": r["band_code"],
            "observed_value": num(r["observed_value"]), "threshold_value": num(r["threshold_value"])})
    return out


def sync_thresholds(etl) -> None:
    """Ambang hujan kalimat = aturan alert BMKG aktif (alert_rules, hanya ETL)."""
    from etl.live_interpret import sync_bmkg_thresholds
    try:
        with etl.session() as s:
            sync_bmkg_thresholds(s)
    except Exception:   # ambang default THRESHOLDS tetap berlaku
        pass


def interpret(latest, prev, rng, al) -> dict:
    from etl.lokasi_interpret import interpret_region
    return interpret_region(latest, prev, rng, al)


def conditions(sess, region_ids=None) -> dict[int, dict]:
    """{region_id: {region, latest, prev, ranges, alerts, **interpret_region}}."""
    o, rg, al = obs(sess), ranges(sess), alerts(sess)
    out = {}
    for r in regions(sess, region_ids):
        latest, prev = o.get(r["region_id"], ({}, {}))
        res = interpret(latest, prev, rg.get(r["region_id"], {}), al.get(r["region_id"], []))
        out[r["region_id"]] = {"region": r, "latest": latest, "prev": prev,
                               "ranges": rg.get(r["region_id"], {}), "alerts": al.get(r["region_id"], []), **res}
    return out


# ------------------------------------------------------------------------- citra

def area_for(etl, region_id: int) -> int | None:
    """Live Area aktif yang bbox-nya paling banyak menutupi kecamatan."""
    with etl.session() as s:
        return s.scalar(text("""
            SELECT a.area_id FROM live_areas a
            JOIN administrative_regions r ON r.region_id = :r
            WHERE a.deleted_at IS NULL AND a.enabled
              AND ST_Intersects(ST_GeomFromText(a.bbox_wkt, 4326), r.geom)
            ORDER BY ST_Area(ST_Intersection(ST_GeomFromText(a.bbox_wkt, 4326), r.geom)) DESC, a.area_id
            LIMIT 1"""), {"r": region_id})


# Isi v_public_live_latest. monitor_etl membaca tabelnya langsung dengan
# syarat yang sama (VIEW itu hanya diberikan ke role pengunjung).
_LATEST_BASE = """
    SELECT s.area_id, a.name AS area_name, s.live_scene_id, s.scene_date, s.status, s.area_status,
           s.interpretations, s.previews, s.source_status
    FROM live_scenes s JOIN live_areas a ON a.area_id = s.area_id
    WHERE s.area_id = :a AND a.deleted_at IS NULL AND a.enabled AND s.deleted_at IS NULL
      AND s.status IN ('READY', 'PARTIAL')
    ORDER BY s.scene_date DESC LIMIT 1"""


def scene(sess, etl, region_id: int, *, base_tables: bool = False):
    """Scene Live terbaru yang menutupi kecamatan, atau None."""
    area_id = area_for(etl, region_id)
    if area_id is None:
        return None
    sql = _LATEST_BASE if base_tables else "SELECT * FROM v_public_live_latest WHERE area_id = :a"
    return sess.execute(text(sql), {"a": area_id}).mappings().first()


def has_grid(scene_row) -> bool:
    return bool(((scene_row["previews"] or {}).get("grid") or {}).get("corners_wgs84"))


def cropped_preview(sess, etl, region_id: int, scene_row, key: str) -> tuple[Path | None, str]:
    """(PNG dipotong ke kecamatan, '') atau (None, alasan: NOT_FOUND | GRID_MISSING | OUTSIDE)."""
    if scene_row is None or key not in (((scene_row["previews"] or {}).get("items")) or {}):
        return None, "NOT_FOUND"
    if not has_grid(scene_row):
        return None, "GRID_MISSING"
    from etl.live_monitor import LiveMonitor
    from etl.region_crop import cached_crop
    src = LiveMonitor(etl).preview_path(scene_row["area_id"], scene_row["scene_date"], key)
    if src is None:
        return None, "NOT_FOUND"
    gj = sess.scalar(text("SELECT ST_AsGeoJSON(geom) FROM administrative_regions WHERE region_id = :r"),
                     {"r": region_id})
    out = cached_crop(src, scene_row["previews"]["grid"], json.loads(gj), scene_row["area_id"],
                      scene_row["scene_date"], key, region_id)
    return (out, "") if out is not None else (None, "OUTSIDE")
