# etl/regions.py
"""Wilayah administratif dan ROI turunan (PIPELINE.md §10 langkah 2–4, M8/M27).

Satu tempat untuk tiga aturan yang dipakai bersama oleh
``scripts/load_regions.py`` dan endpoint ADMIN (``/admin/regions``,
``/admin/rois``):

1. Batas COD-AB adm2 + adm3 Kabupaten Lebak -> ``administrative_regions``
   (``ST_Multi(ST_MakeValid(...))``, upsert per ``pcode``).
2. ``in_aoi`` kecamatan -> ROI AOI GMLS (``is_monitor_aoi``) dengan bbox
   ``ST_Envelope(ST_Union(geom))``, ROI per kecamatan AOI, dan bbox dataset
   sistem ``HYDROMET_AOI`` yang mengikutinya.
3. ROI gabungan dari daftar kecamatan (dibuat ADMIN).

Semua fungsi menerima Session pemanggil dan tidak meng-commit sendiri, jadi
skrip (pemilik skema) dan request ADMIN (SET LOCAL ROLE monitor_admin)
memakai jalur yang sama.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

LEBAK_ADM2_PCODE = "ID3602"
SOURCE_DATASET = "COD-AB IDN 2020 (BPS/OCHA)"
AOI_ROI_CODE = "GMLS_AOI"
AOI_ROI_NAME = "AOI GMLS (Lebak Selatan)"
HYDROMET_DATASET_NAME = "HYDROMET_AOI"
HYDROMET_SOURCES = ("GPM", "MODIS")

# Lokasi berkas COD-AB yang dipakai skrip bila --adm2/--adm3 tidak diberikan.
DEFAULT_COD_AB_DIR = Path(__file__).resolve().parent.parent / "data" / "external" / "cod-ab-idn"


@dataclass(frozen=True)
class RegionFeature:
    pcode: str
    name: str
    admin_level: int
    parent_pcode: str | None
    wkb_hex: str


# --- pembacaan shapefile -------------------------------------------------------

def _field(rec: dict, *names: str) -> str | None:
    """Nilai kolom pertama yang ada, tanpa peduli huruf besar/kecil (rilis
    COD-AB memakai ADM3_PCODE, berkas HDX terbaru adm3_pcode)."""
    lower = {k.lower(): v for k, v in rec.items()}
    for n in names:
        v = lower.get(n.lower())
        if v not in (None, ""):
            return str(v).strip()
    return None


def read_cod_ab(path: Path, level: int, adm2_pcode: str = LEBAK_ADM2_PCODE) -> list[RegionFeature]:
    """Fitur level ``level`` (2/3) dari shapefile COD-AB yang berada di
    kabupaten ``adm2_pcode``."""
    import shapefile  # pyshp
    from shapely.geometry import shape as to_geom

    if level not in (2, 3):
        raise ValueError("level must be 2 or 3")
    out: list[RegionFeature] = []
    with shapefile.Reader(str(path)) as r:
        for sr in r.iterShapeRecords():
            rec = sr.record.as_dict()
            if _field(rec, "ADM2_PCODE") != adm2_pcode:
                continue
            geom = to_geom(sr.shape.__geo_interface__)
            if level == 2:
                out.append(RegionFeature(adm2_pcode, _field(rec, "ADM2_EN", "adm2_name") or adm2_pcode,
                                         2, None, geom.wkb_hex))
            else:
                pcode = _field(rec, "ADM3_PCODE")
                if not pcode:
                    continue
                out.append(RegionFeature(pcode, _field(rec, "ADM3_EN", "adm3_name") or pcode,
                                         3, adm2_pcode, geom.wkb_hex))
    if not out:
        raise ValueError(f"no level-{level} feature with ADM2_PCODE={adm2_pcode} in {path}")
    return out


# --- administrative_regions ----------------------------------------------------

_UPSERT_REGION = text("""
    INSERT INTO administrative_regions (parent_region_id, pcode, region_name, admin_level, geom, source_dataset)
    VALUES (
        (SELECT region_id FROM administrative_regions WHERE pcode = :parent),
        :pcode, :name, :level,
        ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_SetSRID(ST_GeomFromWKB(decode(:wkb, 'hex')), 4326)), 3)),
        :src)
    ON CONFLICT (pcode) DO UPDATE SET
        parent_region_id = EXCLUDED.parent_region_id,
        region_name      = EXCLUDED.region_name,
        admin_level      = EXCLUDED.admin_level,
        geom             = EXCLUDED.geom,
        source_dataset   = EXCLUDED.source_dataset
    RETURNING region_id, (xmax = 0) AS inserted
""")


def upsert_regions(sess: Session, features: list[RegionFeature],
                   source_dataset: str = SOURCE_DATASET) -> dict[str, int]:
    """Upsert per pcode; level 2 lebih dulu supaya FK induk terisi.
    ``in_aoi`` tidak disentuh (milik ADMIN). Mengembalikan jumlah baris
    baru/diperbarui."""
    counts = {"inserted": 0, "updated": 0}
    for f in sorted(features, key=lambda f: f.admin_level):
        row = sess.execute(_UPSERT_REGION, {
            "parent": f.parent_pcode, "pcode": f.pcode, "name": f.name,
            "level": f.admin_level, "wkb": f.wkb_hex, "src": source_dataset,
        }).one()
        counts["inserted" if row.inserted else "updated"] += 1
    return counts


def resolve_kecamatan(sess: Session, names_or_pcodes: list[str]) -> list[int]:
    """region_id kecamatan (level 3) dari nama atau pcode, tanpa peduli huruf
    besar/kecil. Nama yang tidak dikenal -> ValueError (bukan diam-diam
    dilewati: AOI yang kurang satu kecamatan tidak kelihatan salah)."""
    ids, missing = [], []
    for raw in names_or_pcodes:
        key = raw.strip()
        if not key:
            continue
        found = sess.execute(text("""
            SELECT region_id FROM administrative_regions
            WHERE admin_level = 3 AND (upper(pcode) = upper(:k) OR lower(region_name) = lower(:k))
        """), {"k": key}).scalars().all()
        if len(found) != 1:
            missing.append(key if not found else f"{key} (ambiguous)")
        else:
            ids.append(found[0])
    if missing:
        raise ValueError("unknown kecamatan: " + ", ".join(missing))
    return sorted(set(ids))


def set_aoi(sess: Session, region_ids: list[int]) -> None:
    """Tepat kecamatan ``region_ids`` yang in_aoi; sisanya false."""
    sess.execute(text("""
        UPDATE administrative_regions SET in_aoi = (region_id = ANY(:ids))
        WHERE admin_level = 3 AND in_aoi IS DISTINCT FROM (region_id = ANY(:ids))
    """), {"ids": list(region_ids)})


# --- ROI ----------------------------------------------------------------------

def _upsert_roi(sess: Session, code: str, name: str, description: str, geom_sql: str,
                params: dict, *, admin_region_id: int | None = None,
                is_monitor_aoi: bool = False, admin_level: int = 3) -> int:
    """ROI dengan bbox = ST_Envelope(<geom_sql>). Baris lama dengan kode yang
    sama diperbarui (dan dihidupkan lagi bila sempat dihapus)."""
    row = sess.execute(text(f"""
        WITH g AS (SELECT ST_Envelope({geom_sql}) AS bbox)
        INSERT INTO regions_of_interest
            (region_code, name, description, bbox, area_km2, admin_level, source,
             admin_region_id, is_monitor_aoi)
        SELECT :code, :name, :descr, g.bbox, ST_Area(g.bbox::geography) / 1e6, :lvl, 'SYSTEM',
               :arid, :aoi
        FROM g
        ON CONFLICT (region_code) DO UPDATE SET
            name = EXCLUDED.name, description = EXCLUDED.description, bbox = EXCLUDED.bbox,
            area_km2 = EXCLUDED.area_km2, admin_region_id = EXCLUDED.admin_region_id,
            is_monitor_aoi = EXCLUDED.is_monitor_aoi, is_active = true, deleted_at = NULL,
            updated_at = now()
        RETURNING region_id
    """), {**params, "code": code, "name": name, "descr": description, "lvl": admin_level,
           "arid": admin_region_id, "aoi": is_monitor_aoi}).scalar_one()
    return row


def rebuild_monitor_aoi(sess: Session) -> int | None:
    """ROI AOI GMLS + ROI per kecamatan AOI + bbox dataset HYDROMET_AOI dari
    kecamatan in_aoi saat ini. Mengembalikan region_id ROI AOI (None bila
    belum ada kecamatan in_aoi; ROI lama dibiarkan, karena dirujuk FK)."""
    aoi = sess.execute(text("""
        SELECT region_id, pcode, region_name FROM administrative_regions WHERE in_aoi ORDER BY region_name
    """)).all()
    if not aoi:
        logger.warning("[REGIONS] belum ada kecamatan in_aoi; ROI AOI tidak dibangun")
        return None
    names = ", ".join(r.region_name for r in aoi)
    roi_id = _upsert_roi(
        sess, AOI_ROI_CODE, AOI_ROI_NAME, f"Gabungan kecamatan in_aoi: {names}",
        "(SELECT ST_Union(geom) FROM administrative_regions WHERE in_aoi)", {},
        is_monitor_aoi=True, admin_level=2)
    for r in aoi:
        _upsert_roi(sess, r.pcode, r.region_name, f"Kecamatan {r.region_name} (COD-AB {r.pcode})",
                    "(SELECT geom FROM administrative_regions WHERE region_id = :rid)",
                    {"rid": r.region_id}, admin_region_id=r.region_id)
    ensure_hydromet_dataset(sess, roi_id)
    return roi_id


def create_union_roi(sess: Session, region_ids: list[int], name: str, code: str | None = None) -> int:
    """ROI gabungan beberapa kecamatan (POST /admin/rois)."""
    ids = sorted(set(region_ids))
    if not ids:
        raise ValueError("region_ids must not be empty")
    n = sess.scalar(text("SELECT count(*) FROM administrative_regions WHERE admin_level = 3 AND region_id = ANY(:ids)"),
                    {"ids": ids})
    if n != len(ids):
        raise ValueError("every region_id must be an existing kecamatan (admin level 3)")
    code = code or ("U_" + "_".join(str(i) for i in ids))[:20]
    names = sess.scalars(text("SELECT region_name FROM administrative_regions WHERE region_id = ANY(:ids) ORDER BY region_name"),
                         {"ids": ids}).all()
    return _upsert_roi(sess, code, name.strip(), "Gabungan kecamatan: " + ", ".join(names),
                       "(SELECT ST_Union(geom) FROM administrative_regions WHERE region_id = ANY(:ids))",
                       {"ids": ids}, admin_region_id=ids[0] if len(ids) == 1 else None)


# --- dataset sistem HYDROMET_AOI -------------------------------------------------

def ensure_hydromet_dataset(sess: Session, roi_id: int) -> int:
    """Dataset sistem HYDROMET_AOI (PIPELINE §3.1): GPM + MODIS PROCESSED,
    tersembunyi dari Katalog (is_system), bbox = ROI AOI."""
    bbox = sess.execute(text("SELECT ST_AsText(bbox) AS wkt FROM regions_of_interest WHERE region_id = :r"),
                        {"r": roi_id}).scalar_one()
    dataset_id = sess.scalar(text("""
        SELECT dataset_id FROM datasets WHERE is_system AND name = :n AND deleted_at IS NULL
    """), {"n": HYDROMET_DATASET_NAME})
    if dataset_id is None:
        dataset_id = sess.scalar(text("""
            INSERT INTO datasets (name, description, location_label, region_id, bbox, bbox_wkt,
                                  date_start, date_end, required_tiers, fusion_strategy, preview_options,
                                  generate_preview, dataset_kind, is_system, is_deletable, status)
            VALUES (:n, 'Dataset sistem job Hidromet Harian (GPM + MODIS untuk AOI GMLS).',
                    :label, :roi, ST_GeomFromText(:wkt, 4326), :wkt,
                    DATE '2023-01-01', current_date, ARRAY['COG'], NULL, ARRAY[]::text[],
                    false, 'STANDARD', true, false, 'COMPLETED')
            RETURNING dataset_id
        """), {"n": HYDROMET_DATASET_NAME, "label": AOI_ROI_NAME, "roi": roi_id, "wkt": bbox})
        for src in HYDROMET_SOURCES:
            sess.execute(text("""
                INSERT INTO dataset_source_config (dataset_id, source_name, processing_levels)
                VALUES (:d, :s, ARRAY['PROCESSED'])
            """), {"d": dataset_id, "s": src})
        logger.info("[REGIONS] dataset sistem %s dibuat (id=%d)", HYDROMET_DATASET_NAME, dataset_id)
    else:
        sess.execute(text("""
            UPDATE datasets SET region_id = :roi, bbox = ST_GeomFromText(:wkt, 4326), bbox_wkt = :wkt,
                   updated_at = now()
            WHERE dataset_id = :d AND bbox_wkt IS DISTINCT FROM :wkt
        """), {"d": dataset_id, "roi": roi_id, "wkt": bbox})
    return dataset_id


def hydromet_dataset(sess: Session) -> dict | None:
    """{dataset_id, name, region_id, bbox(tuple)} dataset HYDROMET_AOI, atau None."""
    row = sess.execute(text("""
        SELECT dataset_id, name, region_id,
               ST_XMin(bbox) AS x0, ST_YMin(bbox) AS y0, ST_XMax(bbox) AS x1, ST_YMax(bbox) AS y1
        FROM datasets WHERE is_system AND name = :n AND deleted_at IS NULL
    """), {"n": HYDROMET_DATASET_NAME}).mappings().first()
    if row is None:
        return None
    return {"dataset_id": row["dataset_id"], "name": row["name"], "region_id": row["region_id"],
            "bbox": (float(row["x0"]), float(row["y0"]), float(row["x1"]), float(row["y1"]))}


def aoi_regions(sess: Session) -> list[dict]:
    """Kecamatan in_aoi: {region_id, pcode, region_name, wkb(bytes)}."""
    rows = sess.execute(text("""
        SELECT region_id, pcode, region_name, ST_AsBinary(geom) AS wkb
        FROM administrative_regions WHERE in_aoi ORDER BY region_id
    """)).mappings().all()
    return [{**r, "wkb": bytes(r["wkb"])} for r in rows]
