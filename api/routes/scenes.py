# api/routes/scenes.py
"""
GET /api/scenes       — list scenes with filters (?source=S1|MODIS|GPM)
GET /api/scenes/{id}  — scene detail
GET /api/scenes/{id}/status — pipeline status per scene
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select

from api.schemas import (
    NasaSceneListItem,
    PipelineStatusResponse,
    SceneDetail,
    SceneListItem,
    SceneListResponse,
)
from api.deps import Principal, current_principal, get_db
from api.errors import ApiError
from etl.database_client import (
    DataProduct,
    DatabaseClient,
    NasaScene,
    SatelliteScene,
)
from etl.metadata_manager import MetadataManager

from etl import tier_names as tn

router  = APIRouter()
logger  = logging.getLogger(__name__)


@router.get(
    "",
    response_model=SceneListResponse,
    summary="List satellite scenes",
    description=(
        "Retrieve a paginated list of Sentinel-1 scenes with optional filters. "
        "Supports date range, region, orbit direction, and quality score filters."
    ),
)
async def list_scenes(
    db:              DatabaseClient = Depends(get_db),
    principal:       Principal      = Depends(current_principal),
    source:          str            = Query("S1", pattern="^(S1|MODIS|GPM)$",
                                            description="S1 = satellite_scenes; MODIS/GPM = nasa_scenes"),
    include_invalid: bool           = Query(False, description="Include deactivated scenes (ADMIN only)"),
    region_id:       int | None     = Query(None,  description="Filter by region_id"),
    orbit_direction: str | None     = Query(None,  description="ASCENDING or DESCENDING"),
    date_from:       datetime | None = Query(None, description="Acquisition from (UTC ISO)"),
    date_to:         datetime | None = Query(None, description="Acquisition to (UTC ISO)"),
    only_gold:       bool           = Query(False, description="Only scenes with a COG product"),
    limit:           int            = Query(20,    ge=1, le=200, description="Results per page"),
    offset:          int            = Query(0,     ge=0,         description="Pagination offset"),
) -> SceneListResponse:
    """
    List scenes with filter support.

    Query patterns:
    - GET /api/scenes
    - GET /api/scenes?region_id=1&date_from=2024-01-01
    - GET /api/scenes?orbit_direction=ASCENDING&limit=50
    - GET /api/scenes?only_gold=true
    - GET /api/scenes?source=MODIS&date_from=2025-01-01
    - GET /api/scenes?include_invalid=true   (ADMIN)

    Scene yang dinonaktifkan ADMIN (is_valid = false, M23/M24) disembunyikan
    kecuali include_invalid. orbit_direction dan only_gold hanya berlaku
    untuk S1.
    """
    if include_invalid and not principal.has_role("ADMIN"):
        raise ApiError(403, "include_invalid is available to ADMIN only", "ROLE_FORBIDDEN")
    if source != "S1":
        return _list_nasa_scenes(db, source, region_id, date_from, date_to,
                                 include_invalid, limit, offset)

    with db.session() as sess:
        stmt = select(SatelliteScene).where(SatelliteScene.is_available == True)
        if not include_invalid:
            stmt = stmt.where(SatelliteScene.is_valid == True)

        if region_id:
            stmt = stmt.where(SatelliteScene.region_id == region_id)
        if orbit_direction:
            stmt = stmt.where(SatelliteScene.orbit_direction == orbit_direction)
        if date_from:
            stmt = stmt.where(SatelliteScene.acquisition_datetime >= date_from)
        if date_to:
            stmt = stmt.where(SatelliteScene.acquisition_datetime <= date_to)
        if only_gold:
            gold_scene_ids = select(DataProduct.scene_id).where(
                DataProduct.product_tier.in_(tn.tiers_at_rank(3)),
                DataProduct.is_latest    == True,
                DataProduct.is_valid     == True,
            )
            stmt = stmt.where(SatelliteScene.scene_id.in_(gold_scene_ids))

        total = sess.scalar(select(func.count()).select_from(stmt.subquery()))
        scenes = sess.scalars(
            stmt.order_by(SatelliteScene.acquisition_datetime.desc())
                .limit(limit).offset(offset)
        ).all()

        items = [
            SceneListItem(
                scene_id             = s.scene_id,
                scene_uuid           = str(s.scene_uuid),
                product_identifier   = s.product_identifier,
                platform             = s.platform,
                instrument_mode      = s.instrument_mode,
                polarization_vv      = s.polarization_vv,
                polarization_vh      = s.polarization_vh,
                acquisition_datetime = s.acquisition_datetime,
                orbit_direction      = s.orbit_direction,
                orbit_number         = s.orbit_number,
                relative_orbit       = s.relative_orbit,
                cloud_cover_percent  = float(s.cloud_cover_percent) if s.cloud_cover_percent else None,
                resolution_m         = s.resolution_m,
                region_id            = s.region_id,
                is_available         = s.is_available,
                created_at           = s.created_at,
                is_valid             = s.is_valid,
                invalid_reason       = s.invalid_reason,
            )
            for s in scenes
        ]

    return SceneListResponse(total=total or 0, limit=limit, offset=offset, items=items)


def _list_nasa_scenes(db, source, region_id, date_from, date_to, include_invalid,
                      limit, offset) -> SceneListResponse:
    """Granule MODIS/GPM dari nasa_scenes (M30) lewat endpoint yang sama
    (INTERFACE.md §4.7, K12)."""
    with db.session() as sess:
        stmt = select(NasaScene).where(NasaScene.source == source,
                                       NasaScene.is_available == True)
        if not include_invalid:
            stmt = stmt.where(NasaScene.is_valid == True)
        if region_id:
            stmt = stmt.where(NasaScene.region_id == region_id)
        if date_from:
            stmt = stmt.where(NasaScene.acquisition_date >= date_from.date())
        if date_to:
            stmt = stmt.where(NasaScene.acquisition_date <= date_to.date())
        total = sess.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = sess.scalars(
            stmt.order_by(NasaScene.acquisition_date.desc(), NasaScene.nasa_scene_id.desc())
                .limit(limit).offset(offset)
        ).all()
        items = [
            NasaSceneListItem(
                nasa_scene_id=r.nasa_scene_id, source=r.source, tile_id=r.tile_id,
                product_short_name=r.product_short_name, acquisition_date=r.acquisition_date,
                region_id=r.region_id, run_type=r.run_type, is_available=r.is_available,
                is_valid=r.is_valid, invalid_reason=r.invalid_reason, created_at=r.created_at,
            )
            for r in rows
        ]
    return SceneListResponse(total=total or 0, limit=limit, offset=offset, items=items)


@router.get(
    "/{scene_id}",
    response_model=SceneDetail,
    summary="Get scene detail",
    description="Retrieve full metadata for a single Sentinel-1 scene by scene_id.",
)
async def get_scene(
    scene_id: int,
    db: DatabaseClient = Depends(get_db),
) -> SceneDetail:
    meta = MetadataManager(db)
    scene = meta.get_scene_by_id(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail=f"Scene {scene_id} not found")

    with db.session() as sess:
        s = sess.get(SatelliteScene, scene_id)
        return SceneDetail(
            scene_id             = s.scene_id,
            scene_uuid           = str(s.scene_uuid),
            product_identifier   = s.product_identifier,
            platform             = s.platform,
            instrument_mode      = s.instrument_mode,
            polarization_vv      = s.polarization_vv,
            polarization_vh      = s.polarization_vh,
            acquisition_datetime = s.acquisition_datetime,
            orbit_direction      = s.orbit_direction,
            orbit_number         = s.orbit_number,
            relative_orbit       = s.relative_orbit,
            cloud_cover_percent  = float(s.cloud_cover_percent) if s.cloud_cover_percent else None,
            resolution_m         = s.resolution_m,
            region_id            = s.region_id,
            is_available         = s.is_available,
            created_at           = s.created_at,
            updated_at           = s.updated_at,
            raw_file_path        = s.raw_file_path,
            raw_file_size_mb     = float(s.raw_file_size_mb) if s.raw_file_size_mb else None,
            download_url         = s.download_url,
            checksum_md5         = s.checksum_md5,
            incidence_angle_near = float(s.incidence_angle_near) if s.incidence_angle_near else None,
            incidence_angle_far  = float(s.incidence_angle_far) if s.incidence_angle_far else None,
        )


@router.get(
    "/{scene_id}/status",
    response_model=PipelineStatusResponse,
    summary="Pipeline status",
    description="Get per-stage ETL job execution status for a scene.",
)
async def get_pipeline_status(
    scene_id: int,
    db: DatabaseClient = Depends(get_db),
) -> PipelineStatusResponse:
    meta   = MetadataManager(db)
    stages = meta.get_pipeline_status(scene_id)

    if not stages:
        overall = "NOT_STARTED"
    elif all(s["status"] == "SUCCESS" for s in stages):
        overall = "COMPLETE"
    elif any(s["status"] == "FAILED" for s in stages):
        overall = "FAILED"
    else:
        overall = "IN_PROGRESS"

    from api.schemas import JobStatusItem
    return PipelineStatusResponse(
        scene_id = scene_id,
        stages   = [JobStatusItem(**s) for s in stages],
        overall_status = overall,
    )
