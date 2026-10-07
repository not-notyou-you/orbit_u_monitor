# api/routes/disasters.py
"""Kejadian bencana dan master jenis (INTERFACE.md §4.6).

Baca ``/disasters`` terbuka untuk semua (M56): pengunjung membaca VIEW
``v_public_kejadian`` (365 hari terakhir, tanpa kolom internal), role login
membaca ``disaster_events`` tanpa batas waktu. Tulis ANALYST (GRANT analyst
SIU, tanpa D -> hapus = soft delete ``deleted_at``). ``/disaster-types``: GET
PUBLIC, tulis ADMIN. Validasi bersama dengan ``scripts/import_disasters.py``
ada di ``etl.disasters``.
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

router = APIRouter()        # /api/disasters (baca PUBLIC, tulis ANALYST)
types_router = APIRouter()  # /api/disaster-types (baca PUBLIC, tulis ADMIN)

ADMIN = [Depends(require_role("ADMIN"))]
ANALYST = [Depends(require_role("ANALYST"))]
PUBLIC_WINDOW_DAYS = 365

# Kolom VIEW publik = EVENT_SELECT tanpa source_reference/recorded_by/verified_by.
_PUBLIC_SELECT = """
    SELECT e.event_id, e.disaster_type_code, e.disaster_type_name, e.region_id, e.pcode, e.region_name,
           e.village_name, e.lat, e.lon, e.event_date, e.event_end_date, e.description, e.impact_summary,
           e.info_source, e.is_verified
    FROM v_public_kejadian e
"""


def _get(sess: Session, event_id: int) -> dict:
    row = dz.get_event(sess, event_id)
    if row is None:
        raise ApiError(404, f"Disaster event {event_id} not found", "NOT_FOUND")
    return row


def _value_error(exc: ValueError) -> ApiError:
    return ApiError(400, str(exc), "INVALID_DISASTER")


@router.get("", summary="List disaster events (visitors: last 365 days)")
def list_disasters(sess: Session = Depends(get_session),
                   principal: Principal = Depends(current_principal),
                   date_from: date | None = None, date_to: date | None = None,
                   type_code: str | None = None, region_id: int | None = None,
                   is_verified: bool | None = None,
                   limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)) -> dict:
    public = not principal.is_authenticated
    type_col = "e.disaster_type_code" if public else "dt.type_code"
    where, params = ([] if public else ["e.deleted_at IS NULL"]) or ["true"], {}
    if date_from:
        where.append("e.event_date >= :a")
        params["a"] = date_from
    if date_to:
        where.append("e.event_date <= :b")
        params["b"] = date_to
    if type_code:
        where.append(f"{type_col} = :t")
        params["t"] = type_code
    if region_id is not None:
        where.append("e.region_id = :r")
        params["r"] = region_id
    if is_verified is not None:
        where.append("e.is_verified = :v")
        params["v"] = is_verified
    cond = " AND ".join(where)
    if public:
        count_sql, select_sql = "SELECT count(*) FROM v_public_kejadian e", _PUBLIC_SELECT
    else:
        count_sql = "SELECT count(*) FROM disaster_events e JOIN disaster_types dt USING (disaster_type_id)"
        select_sql = dz.EVENT_SELECT
    total = sess.scalar(text(f"{count_sql} WHERE {cond}"), params)
    rows = sess.execute(text(f"{select_sql} WHERE {cond} ORDER BY e.event_date DESC, e.event_id DESC "
                             "LIMIT :limit OFFSET :offset"), {**params, "limit": limit, "offset": offset}).mappings().all()
    return {"items": [dz.event_dict(r) for r in rows], "total": total, "limit": limit, "offset": offset,
            # Batas yang berlaku untuk pemanggil, supaya UI bisa mengatakannya.
            "window_days": PUBLIC_WINDOW_DAYS if public else None}


@router.get("/{event_id}", summary="Disaster event detail; rainfall H-0..H-2 for ANALYST")
def get_disaster(event_id: int, sess: Session = Depends(get_session),
                 principal: Principal = Depends(current_principal)) -> dict:
    if not principal.is_authenticated:
        row = sess.execute(text(_PUBLIC_SELECT + " WHERE e.event_id = :e"), {"e": event_id}).mappings().first()
        if row is None:
            raise ApiError(404, f"Disaster event {event_id} not found", "NOT_FOUND")
        return {**dz.event_dict(row), "rain": None}
    event = _get(sess, event_id)
    if not principal.has_role("ANALYST"):
        # v_kejadian_dan_hujan milik ANALYST (evaluasi alert, M16).
        return {**event, "rain": None}
    rain = sess.execute(text("SELECT * FROM v_kejadian_dan_hujan WHERE event_id = :e"), {"e": event_id}).mappings().first()
    event["rain"] = [{
        "day": f"H-{k}",
        "rain_24h_mm": None if rain is None or rain[f"rain_24h_h{k}"] is None else float(rain[f"rain_24h_h{k}"]),
        "rain_72h_mm": None if rain is None or rain[f"rain_72h_h{k}"] is None else float(rain[f"rain_72h_h{k}"]),
        "rain_7d_mm": None if rain is None or rain[f"rain_7d_h{k}"] is None else float(rain[f"rain_7d_h{k}"]),
    } for k in range(3)]
    return event


@router.post("", status_code=201, summary="Record a disaster event", dependencies=ANALYST)
def create_disaster(req: DisasterCreate, sess: Session = Depends(get_session),
                    principal: Principal = Depends(current_principal)) -> dict:
    try:
        event_id = dz.insert_event(sess, req.model_dump(), recorded_by=principal.user_id)
    except ValueError as exc:
        raise _value_error(exc)
    return _get(sess, event_id)


@router.put("/{event_id}", summary="Change a disaster event", dependencies=ANALYST)
def update_disaster(event_id: int, req: DisasterUpdate, sess: Session = Depends(get_session),
                    principal: Principal = Depends(current_principal)) -> dict:
    _get(sess, event_id)
    try:
        dz.update_event(sess, event_id, req.model_dump(exclude_unset=True), user_id=principal.user_id)
    except ValueError as exc:
        raise _value_error(exc)
    return _get(sess, event_id)


@router.delete("/{event_id}", summary="Soft-delete a disaster event", dependencies=ANALYST)
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
