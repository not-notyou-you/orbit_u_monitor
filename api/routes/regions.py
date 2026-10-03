# api/routes/regions.py
"""Wilayah (INTERFACE.md §4.4).

``GET /regions``  kecamatan AOI GMLS + GeoJSON (``ST_SimplifyPreserveTopology``).
``GET /rois``     daftar ROI sistem untuk wizard dataset dan Live Area (dulu
                  ``GET /regions``; dipindah Tahap 3, IMPLEMENTATION_NOTES T3-5).

Hanya baca. ROI dibuat oleh sistem/ADMIN dari kecamatan COD-AB (DATABASE.md
§3.6, M27); endpoint tulis dan geocoding milik DataLab sudah dihapus.
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Query
from geoalchemy2.shape import to_shape
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from api.schemas import RegionItem, RegionListResponse
from api.deps import get_db, get_session
from etl.database_client import DatabaseClient, RegionOfInterest

logger = logging.getLogger(__name__)
router = APIRouter()        # /api/regions
rois_router = APIRouter()   # /api/rois


def _to_item(r: RegionOfInterest) -> RegionItem:
    bounds = to_shape(r.bbox).bounds
    source = r.source or "SEEDER"
    return RegionItem(
        region_id=r.region_id,
        region_code=r.region_code,
        name=r.name,
        description=r.description,
        bbox=list(bounds),
        area_km2=float(r.area_km2) if r.area_km2 is not None else None,
        source=source,
        created_at=r.created_at,
    )


@rois_router.get("", response_model=RegionListResponse, summary="List system ROIs (dataset wizard, Live Area)")
async def list_regions(
    db: DatabaseClient = Depends(get_db),
    q: str | None = Query(None, description="Filter by location name/code (case-insensitive)"),
    include_deleted: bool = Query(False, description="Also include locations that have been deleted"),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> RegionListResponse:
    stmt = select(RegionOfInterest)
    if not include_deleted:
        stmt = stmt.where(
            RegionOfInterest.is_active == True,
            RegionOfInterest.deleted_at.is_(None),
        )
    if q and q.strip():
        pattern = f"%{q.strip().lower()}%"
        stmt = stmt.where(or_(
            func.lower(RegionOfInterest.name).like(pattern),
            func.lower(RegionOfInterest.region_code).like(pattern),
        ))
    with db.session() as sess:
        total = sess.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = sess.scalars(
            stmt.order_by(RegionOfInterest.name).limit(limit).offset(offset)
        ).all()
        items = [_to_item(r) for r in rows]
    return RegionListResponse(items=items, total=total)


@router.get("", summary="Kecamatan of the GMLS AOI as simplified GeoJSON")
def kecamatan_geojson(
    sess: Session = Depends(get_session),
    all_lebak: bool = Query(False, alias="all", description="All kecamatan of Kabupaten Lebak, not only the AOI"),
    tolerance: float = Query(0.0005, ge=0, le=0.01, description="ST_SimplifyPreserveTopology tolerance (degrees)"),
) -> dict:
    """Poligon kecamatan disederhanakan ST_SimplifyPreserveTopology;
    ``?all=true`` = semua kecamatan Kabupaten Lebak."""
    rows = sess.execute(text(f"""
        SELECT region_id, pcode, region_name, in_aoi, area_km2,
               ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom, :tol), 6) AS gj
        FROM administrative_regions
        WHERE admin_level = 3 {'' if all_lebak else 'AND in_aoi'}
        ORDER BY region_name"""), {"tol": tolerance}).mappings().all()
    return {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "id": r["region_id"],
            "geometry": json.loads(r["gj"]),
            "properties": {"region_id": r["region_id"], "pcode": r["pcode"], "name": r["region_name"],
                           "in_aoi": r["in_aoi"], "area_km2": float(r["area_km2"]) if r["area_km2"] is not None else None},
        } for r in rows],
    }
