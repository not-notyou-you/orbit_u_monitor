# api/routes/excel.py
"""Ekspor/impor Excel generik (Tahap 3; registri di ``etl/excel_io.py``).

    GET  /excel                         daftar jenis data + kemampuan untuk role pemanggil
    GET  /excel/{entity}.xlsx           ekspor (?date_from=&date_to=), dicatat DOWNLOAD_XLSX
    GET  /excel/{entity}/template.xlsx  templat impor (kolom + petunjuk)
    POST /excel/{entity}/import         body = isi berkas .xlsx (?dry_run=true); semua atau tidak sama sekali

Router dijaga ``require_role("USER")``; role per jenis data dicek di sini
(403 ``ENTITY_FORBIDDEN``) dan kueri tetap berjalan di bawah role pemanggil,
jadi GRANT/RLS PostgreSQL menjadi lapis terakhir. Unggahan dikirim sebagai
body mentah (``Content-Type: application/vnd.openxmlformats-officedocument.
spreadsheetml.sheet``), tanpa multipart.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from api.deps import Principal, current_principal, get_session, mark_download, require_role
from api.errors import ApiError, error_body
from etl import excel_io as xio

router = APIRouter()

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def _entity(code: str) -> xio.Entity:
    e = xio.ENTITIES.get(code)
    if e is None:
        raise ApiError(404, f"Unknown data type {code!r}; see GET /api/excel", "NOT_FOUND")
    return e


def _allow(principal: Principal, role: str | None, what: str) -> None:
    if role is None:
        raise ApiError(400, f"{what} is not supported for this data type", "IMPORT_NOT_SUPPORTED")
    if not principal.has_role(role):
        raise ApiError(403, f"{what} of this data type requires role {role}", "ENTITY_FORBIDDEN")


@router.get("", summary="Data types available for Excel export/import")
def list_entities(principal: Principal = Depends(current_principal)) -> dict:
    items = []
    for e in xio.ENTITIES.values():
        if not principal.has_role(e.export_role) and not (e.import_role and principal.has_role(e.import_role)):
            continue
        items.append({
            "code": e.code, "title": e.title, "date_filter": e.date_column is not None,
            "export": principal.has_role(e.export_role), "export_role": e.export_role,
            "import": bool(e.importer and principal.has_role(e.import_role)), "import_role": e.import_role,
            "export_url": f"/api/excel/{e.code}.xlsx",
            "template_url": f"/api/excel/{e.code}/template.xlsx" if e.importer else None,
        })
    return {"items": items, "total": len(items)}


@router.get("/{entity}.xlsx", summary="Export a data type as .xlsx",
            dependencies=[Depends(require_role("USER", download=True))])
def export(entity: str, request: Request, sess: Session = Depends(get_session),
           principal: Principal = Depends(current_principal),
           date_from: date | None = None, date_to: date | None = None) -> Response:
    e = _entity(entity)
    _allow(principal, e.export_role, "Export")
    if date_from and date_to and date_from > date_to:
        raise ApiError(400, "date_from must not be after date_to", "INVALID_DATE_RANGE")
    content, n = xio.export_xlsx(sess, entity, date_from, date_to)
    filename = f"orbit_u_{entity}" + (f"_{date_from or ''}_{date_to or ''}" if e.date_column and (date_from or date_to) else "") + ".xlsx"
    mark_download(request, "DOWNLOAD_XLSX", "excel", None, entity=entity, rows=n, filename=filename,
                  date_from=str(date_from) if date_from else None, date_to=str(date_to) if date_to else None)
    return Response(content, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/{entity}/template.xlsx", summary="Empty import template with column help")
def template(entity: str, principal: Principal = Depends(current_principal)) -> Response:
    e = _entity(entity)
    _allow(principal, e.import_role if e.importer else None, "Import")
    return Response(xio.template_xlsx(entity), media_type=XLSX,
                    headers={"Content-Disposition": f'attachment; filename="template_{entity}.xlsx"'})


@router.post("/{entity}/import", summary="Import an .xlsx file (all rows or nothing)")
async def import_(entity: str, request: Request, sess: Session = Depends(get_session),
                  principal: Principal = Depends(current_principal),
                  dry_run: bool = Query(False, description="Validate only; write nothing")) -> dict:
    e = _entity(entity)
    _allow(principal, e.import_role if e.importer else None, "Import")
    body = await request.body()
    if not body:
        raise ApiError(400, "Send the .xlsx file as the request body", "EMPTY_UPLOAD")
    if len(body) > MAX_UPLOAD_BYTES:
        raise ApiError(413, f"File larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB", "UPLOAD_TOO_LARGE")
    try:
        summary = await run_in_threadpool(xio.import_xlsx, sess, entity, body, principal.user_id, dry_run)
    except ValueError as exc:
        raise ApiError(400, str(exc), "INVALID_IMPORT_FILE")
    if summary["errors"]:
        # Tidak ada yang ditulis (SAVEPOINT dibatalkan); semua error per baris dikembalikan.
        return JSONResponse(status_code=422, content={
            **error_body(422, f"{len(summary['errors'])} row(s) invalid; nothing was imported", "IMPORT_ROWS_INVALID"),
            "errors": summary["errors"], "rows": summary.get("rows")})
    return summary
