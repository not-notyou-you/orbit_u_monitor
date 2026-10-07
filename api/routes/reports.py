# api/routes/reports.py
"""Laporan periodik (INTERFACE.md §4.8).

Daftar dan unduhan disaring RLS ``generated_reports`` per audiens: ANALYST
melihat Hidromet, DATA_ENGINEER Kesehatan Data, ADMIN keduanya. Laporan di
luar audiens -> 404 (tidak membocorkan keberadaannya). Regenerasi ADMIN
berjalan di latar dengan koneksi monitor_etl.
"""

from __future__ import annotations

import logging
import threading
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.deps import Principal, current_principal, get_etl_db, get_session, mark_download, require_role
from api.errors import ApiError
from api.schemas_monitor import ReportRegenerateRequest

logger = logging.getLogger(__name__)
router = APIRouter()


def _audience_only(principal: Principal = Depends(current_principal)) -> Principal:
    if not (principal.has_role("ANALYST") or principal.has_role("DATA_ENGINEER")):
        # ANALYST dan DATA_ENGINEER tidak bertingkat, jadi bukan require_role.
        raise ApiError(403, "Reports are for ANALYST (Hydromet) or DATA_ENGINEER (Data Health)", "REPORT_AUDIENCE")
    return principal


_SELECT = """
    SELECT g.report_id, t.report_code, t.report_name, t.period, g.period_start, g.period_end, g.status,
           g.file_size_bytes, g.checksum_sha256, g.error_message, g.generated_by, g.generated_at, g.file_path
    FROM generated_reports g JOIN report_types t USING (report_type_id)
"""


def _item(r) -> dict:
    d = dict(r)
    d["file_name"] = Path(d.pop("file_path")).name if d["status"] != "FAILED" else None
    return d


@router.get("", summary="List periodic reports for your audience", dependencies=[Depends(_audience_only)])
def list_reports(sess: Session = Depends(get_session),
                 type: str | None = Query(None, pattern="^(HYDROMET|DATAHEALTH)(_WEEKLY|_MONTHLY)?$"),
                 year: int | None = Query(None, ge=2000, le=2100),
                 include_superseded: bool = False,
                 limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)) -> dict:
    where, params = ["true"], {}
    if not include_superseded:
        where.append("g.status <> 'SUPERSEDED'")
    if type:
        where.append("t.report_code LIKE :t")
        params["t"] = type + "%"
    if year:
        where.append("extract(year FROM g.period_start) = :y")
        params["y"] = year
    cond = " AND ".join(where)
    total = sess.scalar(text(f"SELECT count(*) FROM generated_reports g JOIN report_types t USING (report_type_id) "
                             f"WHERE {cond}"), params)
    rows = sess.execute(text(f"{_SELECT} WHERE {cond} ORDER BY g.period_start DESC, t.report_code, g.report_id DESC "
                             "LIMIT :limit OFFSET :offset"), {**params, "limit": limit, "offset": offset}).mappings().all()
    return {"items": [_item(r) for r in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/{report_id}/download", summary="Download a report PDF",
            dependencies=[Depends(_audience_only), Depends(require_role("USER", download=True))])
def download_report(report_id: int, request: Request, sess: Session = Depends(get_session)):
    row = sess.execute(text(_SELECT + " WHERE g.report_id = :r"), {"r": report_id}).mappings().first()
    # RLS menyembunyikan laporan audiens lain -> sama dengan tidak ada.
    if row is None or row["status"] == "FAILED":
        raise ApiError(404, f"Report {report_id} not found", "NOT_FOUND")
    path = Path(row["file_path"])
    if not path.is_file():
        raise ApiError(404, "Report file is missing on disk", "FILE_MISSING")
    mark_download(request, "DOWNLOAD_REPORT", "generated_reports", report_id, format="pdf",
                  report_code=row["report_code"], period_start=str(row["period_start"]))
    return FileResponse(path, media_type="application/pdf", filename=path.name)


def _regenerate(etl, code: str, period_start, user_id: int | None) -> None:
    from etl.report_periodic import generate_report
    try:
        generate_report(etl, code, period_start, generated_by=user_id)
    except Exception:
        logger.exception("[REPORT] regenerasi %s %s gagal", code, period_start)


@router.post("/regenerate", status_code=202, summary="Regenerate a report (old one becomes SUPERSEDED)",
             dependencies=[Depends(require_role("ADMIN"))])
def regenerate(req: ReportRegenerateRequest, principal: Principal = Depends(current_principal),
               etl=Depends(get_etl_db)) -> dict:
    from etl.report_periodic import period_for
    try:
        start, end = period_for(req.report_code, req.period_start)
    except ValueError as exc:
        raise ApiError(400, str(exc), "INVALID_PERIOD")
    threading.Thread(target=_regenerate, args=(etl, req.report_code, start, principal.user_id),
                     name=f"report-{req.report_code}-{start}", daemon=True).start()
    return {"accepted": True, "report_code": req.report_code, "period_start": start, "period_end": end}


MAX_CUSTOM_DAYS = 366
_KIND_ROLE = {"HYDROMET": "ANALYST", "DATAHEALTH": "DATA_ENGINEER"}


@router.get("/custom.pdf", summary="Report for a free date range (generated now, not stored)",
            dependencies=[Depends(require_role("USER", download=True))])
def custom_report(request: Request, kind: str = Query(..., pattern="^(HYDROMET|DATAHEALTH)$"),
                  date_from: date = Query(...), date_to: date = Query(...),
                  principal: Principal = Depends(current_principal), etl=Depends(get_etl_db)) -> Response:
    """Same templates as the weekly/monthly reports, for any range up to 366
    days (M56). Audience as for stored reports: HYDROMET for ANALYST,
    DATAHEALTH for DATA_ENGINEER, ADMIN both. The PDF is built with the
    pipeline connection (like the scheduler) after the audience check, and
    is returned directly instead of being registered in generated_reports,
    whose periods are fixed weeks and months."""
    if not principal.has_role(_KIND_ROLE[kind]):
        raise ApiError(403, f"{kind} reports are for {_KIND_ROLE[kind]}", "REPORT_AUDIENCE")
    if date_from > date_to or (date_to - date_from).days + 1 > MAX_CUSTOM_DAYS:
        raise ApiError(400, f"date_from must be before date_to and the range at most {MAX_CUSTOM_DAYS} days",
                       "INVALID_DATE_RANGE")
    import tempfile
    from datetime import datetime, timezone

    from etl.report_periodic import build_pdf, builder_for

    code = f"{kind}_{'MONTHLY' if (date_to - date_from).days >= 7 else 'WEEKLY'}"
    label = {"HYDROMET": "Laporan Hidrometeorologi", "DATAHEALTH": "Laporan Kesehatan Data"}[kind]
    with tempfile.TemporaryDirectory(prefix="orbit_u_custom_") as wd:
        with etl.session() as sess:
            doc = builder_for(code)(sess, code, date_from, date_to, Path(wd),
                                    [f"Rentang dipilih sendiri: {date_from:%d-%m-%Y} s.d. {date_to:%d-%m-%Y}."])
        doc.title = f"{label} (rentang bebas)"
        out = Path(wd) / "custom.pdf"
        build_pdf(doc, out, datetime.now(timezone.utc))
        body = out.read_bytes()
    filename = f"{kind}_{date_from.isoformat()}_{date_to.isoformat()}.pdf"
    mark_download(request, "DOWNLOAD_REPORT", "report_custom", None, format="pdf", kind=kind,
                  date_from=str(date_from), date_to=str(date_to), filename=filename)
    return Response(body, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
