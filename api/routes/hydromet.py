# api/routes/hydromet.py
"""Hidromet (INTERFACE.md §4.4): statistik hari ini, observasi, tren, ekspor CSV.

Tanggal = hari UTC (``region_observations.obs_date``). USER hanya melihat 30
hari terakhir; ANALYST (dan ADMIN) bebas. Router dijaga
``require_role("USER")`` di api/main.py.
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.deps import Principal, current_principal, get_session, mark_download, require_role
from api.errors import ApiError

router = APIRouter()

# Batas USER sama dengan halaman Citra (M56): 365 hari. ANALYST dan
# DATA_ENGINEER melihat seluruh arsip. Rentang bawaan tanpa date_from: 30 hari.
USER_MAX_DAYS = 365
DEFAULT_DAYS = 30
WIB = ZoneInfo("Asia/Jakarta")
BANDS = ("RAIN_24H", "RAIN_72H", "RAIN_7D", "RAIN_30D", "FLOOD", "NDVI", "NDWI")
_SEVERITY_ORDER = {"INFO": 1, "WARNING": 2, "CRITICAL": 3}


def _num(v):
    return None if v is None else float(v)


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


def _full_archive(principal: Principal) -> bool:
    return principal.has_role("ANALYST") or principal.has_role("DATA_ENGINEER")


def _check_range(principal: Principal, date_from: date | None, date_to: date | None) -> tuple[date, date]:
    today = _utc_today()
    date_to = date_to or today
    if date_from is None:
        date_from = date_to - timedelta(days=DEFAULT_DAYS - 1)
    if date_from > date_to:
        raise ApiError(400, "date_from must not be after date_to", "INVALID_DATE_RANGE")
    if not _full_archive(principal) and date_from < today - timedelta(days=USER_MAX_DAYS):
        raise ApiError(403, f"USER can only view the last {USER_MAX_DAYS} days; ANALYST and DATA_ENGINEER see the full archive",
                       "DATE_OUT_OF_RANGE")
    return date_from, date_to


@router.get("/today", summary="Today's rainfall statistics per kecamatan (v_statistik_hari_ini)")
def today(sess: Session = Depends(get_session)) -> dict:
    rows = sess.execute(text("SELECT * FROM v_statistik_hari_ini ORDER BY region_name")).mappings().all()
    if not rows:
        return {"obs_date": None, "window_wib": None, "regions": []}
    obs_date = rows[0]["obs_date"]
    alerts = sess.execute(text("""
        SELECT DISTINCT ON (region_id) region_id, alert_id, severity, rule_code
        FROM v_alert_aktif WHERE observation_date = :d
        ORDER BY region_id, CASE severity WHEN 'CRITICAL' THEN 3 WHEN 'WARNING' THEN 2 ELSE 1 END DESC, alert_id
    """), {"d": obs_date}).mappings().all()
    by_region = {a["region_id"]: {"alert_id": a["alert_id"], "severity": a["severity"], "rule_code": a["rule_code"]}
                 for a in alerts}
    start = datetime.combine(obs_date, time(0), tzinfo=timezone.utc).astimezone(WIB)
    end = start + timedelta(days=1)
    return {
        "obs_date": obs_date,
        # Hari UTC = 07:00 WIB s.d. 07:00 WIB hari berikutnya.
        "window_wib": f"{start.isoformat(timespec='minutes')}/{end.isoformat(timespec='minutes')}",
        "regions": [{
            "region_id": r["region_id"], "pcode": r["pcode"], "name": r["region_name"],
            "rain_24h_mm": _num(r["rain_24h_mm"]), "rain_72h_mm": _num(r["rain_72h_mm"]),
            "rain_7d_mm": _num(r["rain_7d_mm"]), "rain_30d_mm": _num(r["rain_30d_mm"]),
            "bmkg_category": r["bmkg_category"], "gpm_run": r["gpm_run"],
            "ndvi": _num(r["ndvi"]), "ndwi": _num(r["ndwi"]), "modis_flood_pct": _num(r["modis_flood_pct"]),
            "modis_date": r["modis_date"], "active_alert": by_region.get(r["region_id"]),
        } for r in rows],
    }


def _observations_sql(where: list[str]) -> str:
    return f"""
        SELECT o.obs_date, o.region_id, r.pcode, r.region_name, b.band_code, b.unit,
               o.value, o.valid_fraction, o.run_type, o.source_product_id, o.computed_at
        FROM region_observations o
        JOIN spectral_bands b ON b.band_id = o.band_id
        JOIN administrative_regions r ON r.region_id = o.region_id
        WHERE {' AND '.join(where)}
    """


def _observation_filters(region_id, band, date_from, date_to) -> tuple[list[str], dict]:
    where = ["o.obs_date BETWEEN :a AND :b"]
    params: dict = {"a": date_from, "b": date_to}
    if region_id is not None:
        where.append("o.region_id = :rid")
        params["rid"] = region_id
    if band:
        where.append("b.band_code = :band")
        params["band"] = band
    return where, params


@router.get("/observations", summary="Daily observations per kecamatan and band")
def observations(sess: Session = Depends(get_session), principal: Principal = Depends(current_principal),
                 region_id: int | None = None,
                 band: str | None = Query(None, pattern="^(" + "|".join(BANDS) + ")$"),
                 date_from: date | None = None, date_to: date | None = None,
                 limit: int = Query(500, ge=1, le=5000), offset: int = Query(0, ge=0)) -> dict:
    date_from, date_to = _check_range(principal, date_from, date_to)
    where, params = _observation_filters(region_id, band, date_from, date_to)
    total = sess.scalar(text(f"SELECT count(*) FROM ({_observations_sql(where)}) q"), params)
    rows = sess.execute(text(_observations_sql(where) + " ORDER BY o.obs_date, r.region_name, b.band_code "
                             "LIMIT :limit OFFSET :offset"), {**params, "limit": limit, "offset": offset}).mappings().all()
    items = [{**r, "value": _num(r["value"]), "valid_fraction": _num(r["valid_fraction"])} for r in rows]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/trend", summary="Last-N-days series per kecamatan for charts")
def trend(sess: Session = Depends(get_session), principal: Principal = Depends(current_principal),
          band: str = Query("RAIN_24H", pattern="^(" + "|".join(BANDS) + ")$"),
          days: int = Query(30, ge=1, le=366)) -> dict:
    if days > USER_MAX_DAYS and not _full_archive(principal):
        raise ApiError(403, f"USER can only view the last {USER_MAX_DAYS} days", "DATE_OUT_OF_RANGE")
    end = sess.scalar(text("""
        SELECT max(o.obs_date) FROM region_observations o JOIN spectral_bands b USING (band_id)
        WHERE b.band_code = :band"""), {"band": band})
    if end is None:
        return {"band": band, "dates": [], "series": []}
    start = end - timedelta(days=days - 1)
    rows = sess.execute(text("""
        SELECT r.region_id, r.pcode, r.region_name, o.obs_date, o.value
        FROM administrative_regions r
        LEFT JOIN region_observations o ON o.region_id = r.region_id
             AND o.band_id = (SELECT band_id FROM spectral_bands WHERE band_code = :band)
             AND o.obs_date BETWEEN :a AND :b
        WHERE r.in_aoi ORDER BY r.region_name, o.obs_date"""), {"band": band, "a": start, "b": end}).mappings().all()
    dates = [start + timedelta(days=i) for i in range(days)]
    series: dict[int, dict] = {}
    for r in rows:
        s = series.setdefault(r["region_id"], {"region_id": r["region_id"], "pcode": r["pcode"],
                                               "name": r["region_name"], "values": {}})
        if r["obs_date"] is not None:
            s["values"][r["obs_date"]] = _num(r["value"])
    return {"band": band, "dates": dates,
            "series": [{**s, "values": [s["values"].get(d) for d in dates]} for s in series.values()]}


@router.get("/observations.csv", summary="Export observations as CSV (logged)",
            dependencies=[Depends(require_role("ANALYST", download=True))])
def observations_csv(request: Request, sess: Session = Depends(get_session),
                     principal: Principal = Depends(current_principal),
                     region_id: int | None = None,
                     band: str | None = Query(None, pattern="^(" + "|".join(BANDS) + ")$"),
                     date_from: date | None = None, date_to: date | None = None) -> Response:
    date_from, date_to = _check_range(principal, date_from, date_to)
    where, params = _observation_filters(region_id, band, date_from, date_to)
    rows = sess.execute(text(_observations_sql(where) + " ORDER BY o.obs_date, r.region_name, b.band_code"),
                        params).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["obs_date_utc", "region_id", "pcode", "kecamatan", "band", "unit", "value",
                "valid_fraction", "gpm_run", "source_product_id", "computed_at"])
    for r in rows:
        w.writerow(["" if v is None else v for v in r])
    filename = f"hydromet_{date_from}_{date_to}.csv"
    mark_download(request, "EXPORT_CSV", "region_observations", None, format="csv", filename=filename,
                  rows=len(rows), date_from=str(date_from), date_to=str(date_to), band=band, region_id=region_id)
    return Response(buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
