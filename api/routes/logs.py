# api/routes/logs.py
"""Log per halaman (INTERFACE.md §4.8, M56).

* ``/logs/data``     — DATA_ENGINEER: hanya log yang menyangkut halaman Data
  (VIEW ``v_log_data``: unduhan/backfill/ubah scene + audit tabel katalog).
* ``/logs/kejadian`` — ANALYST: hanya log halaman Kejadian
  (VIEW ``v_log_kejadian``: audit kejadian/jenis + ekspor Excel kejadian).

ADMIN membaca keduanya, ditambah log masuk/registrasi, unduhan, dan audit
lengkap di ``/api/admin/logs/*`` dan ``/api/admin/audit``. Pembatasan per
role ada di GRANT VIEW, jadi tes lapis 3 tetap berlaku.
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.deps import get_session, require_role
from api.errors import ApiError

router = APIRouter()


def _page(sess: Session, view: str, date_from: date | None, date_to: date | None, kind: str | None,
          action: str | None, q: str | None, limit: int, offset: int) -> dict:
    if date_from and date_to and date_from > date_to:
        raise ApiError(400, "date_from must not be after date_to", "INVALID_DATE_RANGE")
    where, params = ["true"], {}
    if date_from:
        where.append("logged_at >= :a")
        params["a"] = date_from
    if date_to:
        where.append("logged_at < :b")
        params["b"] = date_to + timedelta(days=1)
    if kind:
        where.append("kind = :k")
        params["k"] = kind
    if action:
        where.append("action = :act")
        params["act"] = action
    if q:
        where.append("(username ILIKE :q OR target_type ILIKE :q OR target_id ILIKE :q OR detail::text ILIKE :q)")
        params["q"] = f"%{q}%"
    cond = " AND ".join(where)
    total = sess.scalar(text(f"SELECT count(*) FROM {view} WHERE {cond}"), params)
    rows = sess.execute(text(f"SELECT * FROM {view} WHERE {cond} ORDER BY logged_at DESC, log_ref DESC "
                             "LIMIT :limit OFFSET :offset"), {**params, "limit": limit, "offset": offset}).mappings().all()
    return {"items": [dict(r) for r in rows], "total": total, "limit": limit, "offset": offset}


_KIND = Query(None, pattern="^(AKTIVITAS|AUDIT)$")


@router.get("/data", summary="Log of the Data page (DATA_ENGINEER)",
            dependencies=[Depends(require_role("DATA_ENGINEER"))])
def data_log(sess: Session = Depends(get_session), date_from: date | None = None, date_to: date | None = None,
             kind: str | None = _KIND, action: str | None = Query(None, max_length=30),
             q: str | None = Query(None, max_length=100),
             limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)) -> dict:
    return _page(sess, "v_log_data", date_from, date_to, kind, action, q, limit, offset)


@router.get("/kejadian", summary="Log of the Disaster events page (ANALYST)",
            dependencies=[Depends(require_role("ANALYST"))])
def kejadian_log(sess: Session = Depends(get_session), date_from: date | None = None, date_to: date | None = None,
                 kind: str | None = _KIND, action: str | None = Query(None, max_length=30),
                 q: str | None = Query(None, max_length=100),
                 limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)) -> dict:
    return _page(sess, "v_log_kejadian", date_from, date_to, kind, action, q, limit, offset)
