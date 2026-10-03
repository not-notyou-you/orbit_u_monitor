# api/routes/regions.py
"""Daftar ROI sistem untuk wizard dataset dan Live Area.

Hanya baca. ROI dibuat oleh sistem/ADMIN dari kecamatan COD-AB (DATABASE.md
§3.6, M27); endpoint tulis dan geocoding milik DataLab sudah dihapus.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from geoalchemy2.shape import to_shape
from sqlalchemy import func, or_, select

from api.schemas import RegionItem, RegionListResponse
from api.deps import get_db
from etl.database_client import DatabaseClient, RegionOfInterest

logger = logging.getLogger(__name__)
router = APIRouter()


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


@router.get("", response_model=RegionListResponse, summary="List locations")
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
