# api/routes/disasters.py
"""Kejadian bencana dan master jenis (INTERFACE.md §4.6).

``/disasters`` ANALYST (RLS/GRANT: analyst SIU, tanpa D -> hapus = soft
delete ``deleted_at``). ``/disaster-types``: GET USER, tulis ADMIN.
Validasi bersama dengan ``scripts/import_disasters.py`` ada di
``etl.disasters``.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.deps import Principal, current_principal, get_session, require_role
from api.errors import ApiError
from api.schemas_monitor import DisasterCreate, DisasterTypeCreate, DisasterTypeUpdate, DisasterUpdate
from etl import disasters as dz

router = APIRouter()        # /api/disasters (ANALYST, dijaga di api/main.py)
types_router = APIRouter()  # /api/disaster-types (USER)

ADMIN = [Depends(require_role("ADMIN"))]


def _get(sess: Session, event_id: int) -> dict:
    row = dz.get_event(sess, event_id)
    if row is None:
        raise ApiError(404, f"Disaster event {event_id} not found", "NOT_FOUND")
    return row


def _value_error(exc: ValueError) -> ApiError:
    return ApiError(400, str(exc), "INVALID_DISASTER")


@router.get("", summary="List disaster events")
def list_disasters(sess: Session = Depends(get_session),
                   date_from: date | None = None, date_to: date | None = None,
                   type_code: str | None = None, region_id: int | None = None,
                   is_verified: bool | None = None,
                   limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)) -> dict:
    where, params = ["e.deleted_at IS NULL"], {}
    if date_from:
        where.append("e.event_date >= :a")
        params["a"] = date_from
    if date_to:
        where.append("e.event_date <= :b")
        params["b"] = date_to
    if type_code:
        where.append("dt.type_code = :t")
        params["t"] = type_code
    if region_id is not None:
        where.append("e.region_id = :r")
        params["r"] = region_id
    if is_verified is not None:
        where.append("e.is_verified = :v")
        params["v"] = is_verified
    cond = " AND ".join(where)
    total = sess.scalar(text(f"SELECT count(*) FROM disaster_events e JOIN disaster_types dt USING (disaster_type_id) "
                             f"WHERE {cond}"), params)
    rows = sess.execute(text(f"{dz.EVENT_SELECT} WHERE {cond} ORDER BY e.event_date DESC, e.event_id DESC "
                             "LIMIT :limit OFFSET :offset"), {**params, "limit": limit, "offset": offset}).mappings().all()
    return {"items": [dz.event_dict(r) for r in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/{event_id}", summary="Disaster event detail with rainfall H-0..H-2")
def get_disaster(event_id: int, sess: Session = Depends(get_session)) -> dict:
    event = _get(sess, event_id)
    rain = sess.execute(text("SELECT * FROM v_kejadian_dan_hujan WHERE event_id = :e"), {"e": event_id}).mappings().first()
    event["rain"] = [{
        "day": f"H-{k}",
        "rain_24h_mm": None if rain is None or rain[f"rain_24h_h{k}"] is None else float(rain[f"rain_24h_h{k}"]),
        "rain_72h_mm": None if rain is None or rain[f"rain_72h_h{k}"] is None else float(rain[f"rain_72h_h{k}"]),
        "rain_7d_mm": None if rain is None or rain[f"rain_7d_h{k}"] is None else float(rain[f"rain_7d_h{k}"]),
    } for k in range(3)]
    return event


@router.post("", status_code=201, summary="Record a disaster event")
def create_disaster(req: DisasterCreate, sess: Session = Depends(get_session),
                    principal: Principal = Depends(current_principal)) -> dict:
    try:
        event_id = dz.insert_event(sess, req.model_dump(), recorded_by=principal.user_id)
    except ValueError as exc:
        raise _value_error(exc)
    return _get(sess, event_id)


@router.put("/{event_id}", summary="Change a disaster event")
def update_disaster(event_id: int, req: DisasterUpdate, sess: Session = Depends(get_session),
                    principal: Principal = Depends(current_principal)) -> dict:
    _get(sess, event_id)
    try:
        dz.update_event(sess, event_id, req.model_dump(exclude_unset=True), user_id=principal.user_id)
    except ValueError as exc:
        raise _value_error(exc)
    return _get(sess, event_id)


@router.delete("/{event_id}", summary="Soft-delete a disaster event")
def delete_disaster(event_id: int, sess: Session = Depends(get_session)) -> dict:
    _get(sess, event_id)
    sess.execute(text("UPDATE disaster_events SET deleted_at = now(), updated_at = now() WHERE event_id = :e"),
                 {"e": event_id})
    return {"ok": True, "message": f"Disaster event {event_id} deleted"}


# --- jenis bencana ------------------------------------------------------------

_TYPE_SELECT = "SELECT disaster_type_id, type_code, type_name, category, indicator_bands, is_active FROM disaster_types"


@types_router.get("", summary="List disaster types")
def list_types(sess: Session = Depends(get_session), include_inactive: bool = False) -> dict:
    rows = sess.execute(text(_TYPE_SELECT + ("" if include_inactive else " WHERE is_active")
                             + " ORDER BY type_name")).mappings().all()
    return {"items": [dict(r) for r in rows], "total": len(rows)}


@types_router.post("", status_code=201, summary="Add a disaster type", dependencies=ADMIN)
def create_type(req: DisasterTypeCreate, sess: Session = Depends(get_session)) -> dict:
    try:
        with sess.begin_nested():
            type_id = sess.scalar(text("""
                INSERT INTO disaster_types (type_code, type_name, category, indicator_bands, is_active)
                VALUES (:type_code, :type_name, :category, :indicator_bands, :is_active)
                RETURNING disaster_type_id"""), req.model_dump())
    except IntegrityError:
        raise ApiError(409, f"Type code {req.type_code} already exists", "TYPE_CODE_TAKEN")
    return dict(sess.execute(text(_TYPE_SELECT + " WHERE disaster_type_id = :i"), {"i": type_id}).mappings().one())


@types_router.put("/{type_id}", summary="Change a disaster type", dependencies=ADMIN)
def update_type(type_id: int, req: DisasterTypeUpdate, sess: Session = Depends(get_session)) -> dict:
    fields = req.model_dump(exclude_unset=True)
    if fields:
        sets = ", ".join(f"{k} = :{k}" for k in fields)
        sess.execute(text(f"UPDATE disaster_types SET {sets} WHERE disaster_type_id = :i"), {**fields, "i": type_id})
    row = sess.execute(text(_TYPE_SELECT + " WHERE disaster_type_id = :i"), {"i": type_id}).mappings().first()
    if row is None:
        raise ApiError(404, f"Disaster type {type_id} not found", "NOT_FOUND")
    return dict(row)
