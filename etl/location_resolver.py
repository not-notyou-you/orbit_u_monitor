# etl/location_resolver.py
from __future__ import annotations
import logging
from geoalchemy2.shape import to_shape
from sqlalchemy import select
from etl.database_client import DatabaseClient, RegionOfInterest

logger = logging.getLogger(__name__)


def resolve_region_id(db: DatabaseClient, region_id: int) -> tuple[str, int, str]:
    """Ambil bbox/label dari lokasi yang dipilih pengguna di UI.

    Jalur utama sejak lokasi dikelola di tabel: UI mengirim region_id, jadi tidak
    ada lagi pencocokan nama yang ambigu kalau ada dua lokasi bernama mirip.
    """
    with db.session() as sess:
        region = sess.get(RegionOfInterest, region_id)
        if region is None or not region.is_active or region.deleted_at is not None:
            raise ValueError(f"Location with id {region_id} was not found or has been deleted")
        return to_shape(region.bbox).wkt, region.region_id, region.name


def _match_known_region(db: DatabaseClient, location: str) -> tuple[str, int, str] | None:
    normalized = location.strip().lower()
    with db.session() as sess:
        rows = sess.scalars(
            select(RegionOfInterest).where(
                RegionOfInterest.is_active == True,
                RegionOfInterest.deleted_at.is_(None),
            )
        ).all()
        for r in rows:
            if r.name.strip().lower() == normalized or r.region_code.strip().lower() == normalized:
                bbox_wkt = to_shape(r.bbox).wkt
                return bbox_wkt, r.region_id, r.name
    return None


def resolve_location(db: DatabaseClient, location: str) -> tuple[str, int, str]:
    """Cocokkan nama/kode lokasi ke ROI sistem yang sudah ada.

    Tidak ada lagi fallback geocoding: ROI hanya lahir dari kecamatan COD-AB
    (DATABASE.md §3.6), jadi nama yang tidak dikenal adalah kesalahan input.
    """
    known = _match_known_region(db, location)
    if not known:
        raise ValueError(f"Location not found: {location}")
    bbox_wkt, region_id, label = known
    logger.info("[LOCATION] '%s' matched known region_id=%d", location, region_id)
    return bbox_wkt, region_id, label
