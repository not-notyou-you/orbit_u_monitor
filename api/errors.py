# api/errors.py
"""Format error API: {"detail": "...", "code": "..."} (INTERFACE.md §5).

`detail` tetap seperti DataLab (teks Inggris) agar klien lama berfungsi;
`code` adalah kode mesin-baca yang diterjemahkan frontend ke Bahasa
Indonesia. HTTPException biasa dari route warisan mendapat kode bawaan
menurut status.
"""

from __future__ import annotations

import logging

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

DEFAULT_CODES: dict[int, str] = {
    400: "BAD_REQUEST",
    401: "NOT_AUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    422: "VALIDATION_ERROR",
    423: "ACCOUNT_LOCKED",
    429: "RATE_LIMITED",
    500: "INTERNAL_ERROR",
    503: "SERVICE_UNAVAILABLE",
}


class ApiError(HTTPException):
    """HTTPException dengan kode error eksplisit."""

    def __init__(self, status_code: int, detail: str, code: str, headers: dict | None = None) -> None:
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.code = code


def error_body(status_code: int, detail: str, code: str | None = None) -> dict:
    return {"detail": detail, "code": code or DEFAULT_CODES.get(status_code, f"HTTP_{status_code}")}


def error_response(status_code: int, detail: str, code: str | None = None,
                   headers: dict | None = None) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=error_body(status_code, detail, code), headers=headers)


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return error_response(exc.status_code, detail, getattr(exc, "code", None),
                          headers=getattr(exc, "headers", None))


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Ratakan error validasi Pydantic jadi satu kalimat.

    Bentuk bawaan FastAPI (`detail` berisi list of dict) tidak bisa ditampilkan
    langsung di UI; front-end (web/js/ui.js) menerjemahkan `code` ke pesan Indonesia, `detail` sebagai cadangan.
    """
    messages = []
    for err in exc.errors():
        msg = str(err.get("msg", "")).removeprefix("Value error, ").strip()
        loc = [str(p) for p in err.get("loc", []) if p not in ("body", "query", "path")]
        messages.append(f"{'.'.join(loc)}: {msg}" if loc else msg)
    detail = " | ".join(dict.fromkeys(m for m in messages if m)) or "Invalid request"
    return error_response(422, detail, "VALIDATION_ERROR")


def _pgcode(exc: BaseException) -> str | None:
    return getattr(getattr(exc, "orig", None), "pgcode", None)


async def db_exception_handler(request: Request, exc: DBAPIError) -> JSONResponse:
    # 42501 insufficient_privilege: GRANT/RLS menolak kueri yang lolos lapis
    # API (INTERFACE.md §3.2 lapis 3). Ini bukan galat server.
    if _pgcode(exc) == "42501":
        logger.warning("DB permission denied on %s %s: %s", request.method, request.url.path,
                       str(getattr(exc, "orig", exc)).splitlines()[0])
        return error_response(403, "Database permission denied for this role", "DB_PERMISSION_DENIED")
    return await unhandled_exception_handler(request, exc)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Permission error DB yang dibungkus exception lain (mis. manager
    # menangkap lalu melempar ulang) tetap dilaporkan sebagai 403.
    cause = exc
    while cause is not None:
        if isinstance(cause, DBAPIError) and _pgcode(cause) == "42501":
            return await db_exception_handler(request, cause)
        cause = cause.__cause__ or cause.__context__
    logger.error("Unhandled exception on %s: %s", request.url.path, exc, exc_info=True)
    body = error_body(500, "Internal server error", "INTERNAL_ERROR")
    body["path"] = str(request.url.path)
    return JSONResponse(status_code=500, content=body)


def install(app) -> None:
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(DBAPIError, db_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
