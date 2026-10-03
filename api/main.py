# api/main.py
from __future__ import annotations
from dotenv import load_dotenv
load_dotenv()
import logging
import mimetypes
import os
import time

mimetypes.add_type("image/webp", ".webp")
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import Depends, FastAPI, Request, Response
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from etl.database_client import DatabaseClient
from api import errors
from api.activity import ActivityLogMiddleware
# get_db di-re-export supaya `from api.main import get_db` tetap jalan; objeknya
# sama persis dengan api.deps.get_db, jadi dependency_overrides lewat jalur mana
# pun mengenai callable yang sama.
from api.deps import get_db, require_role, set_clients
from api.security import jwt_secret
from api.routes import (
    admin, admin_monitor, alerts, auth, datasets, excel, disasters, health, hydromet, lineage, live, pipeline,
    products, public, quality, regions, report, reports, scenes, storage,
)

logger = logging.getLogger(__name__)
_app_client: DatabaseClient | None = None
_etl_client: DatabaseClient | None = None
_scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global _app_client, _etl_client, _scheduler
    jwt_secret()  # gagal keras di startup bila JWT_SECRET kosong/pendek
    # Request API: monitor_app (NOINHERIT, SET LOCAL ROLE per request).
    # Kerja latar (job dataset, Live, penghapusan): monitor_etl.
    # Tidak ada koneksi superuser dari aplikasi (DATABASE.md §8.1).
    logger.info("[API] startup: initializing DatabaseClients (monitor_app, monitor_etl)")
    _app_client = DatabaseClient.from_env("app")
    _etl_client = DatabaseClient.from_env("etl")
    set_clients(_app_client, _etl_client)
    health_info = _app_client.check_health()
    if not health_info.get("connected"):
        logger.error("[API] DB health check FAILED: %s", health_info)
    else:
        logger.info("[API] DB connected. Pool: %s", health_info)
        if os.getenv("AUTO_RESUME_JOBS", "true").lower() in ("1", "true", "yes"):
            try:
                from etl.dataset_manager import DatasetManager
                resumed = DatasetManager(_etl_client).recover_interrupted_jobs()
                if resumed:
                    logger.warning("[API] %d job terputus dilanjutkan: %s", len(resumed), resumed)
            except Exception:
                logger.exception("[API] gagal memulihkan job yang terputus")

    # Scheduler tunggal (PIPELINE §7): hidromet, Live, laporan, masing-masing
    # di bawah advisory lock PostgreSQL. Bisa dimatikan untuk worker API
    # tambahan (ENABLE_SCHEDULER=false); advisory lock tetap menjaga bila tidak.
    if os.getenv("ENABLE_SCHEDULER", "true").lower() in ("1", "true", "yes"):
        try:
            from etl.scheduler import Scheduler
            _scheduler = Scheduler(_etl_client)
            _scheduler.start()
            logger.info("[API] Scheduler started")
        except Exception:
            logger.exception(
                "[API] Scheduler gagal dimulai (cek instalasi rasterio/apscheduler). "
                "API tetap jalan, tapi job terjadwal tidak akan berjalan."
            )
            _scheduler = None

    yield

    logger.info("[API] shutdown: stopping Scheduler")
    if _scheduler:
        _scheduler.shutdown()

    logger.info("[API] shutdown: disposing DatabaseClients")
    set_clients(None, None)
    for client in (_app_client, _etl_client):
        if client:
            client.dispose()


app = FastAPI(
    title="Orbit-U: The Monitor API",
    description=(
        "REST API for hydrometeorological monitoring of South Lebak: Live "
        "monitoring, dataset catalog, scenes, products, quality metrics, "
        "lineage, and administration. Authenticate with the `orbit_u_session` "
        "cookie (web) or `Authorization: Bearer trn_...` (personal API token, "
        "read-only). Every operation lists its minimum role in `x-min-role`. "
        'Errors use `{"detail": "...", "code": "..."}`.'
    ),
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Tanpa CORS: frontend disajikan dari origin yang sama (INTERFACE.md §1),
# cookie SameSite=Strict.
app.add_middleware(ActivityLogMiddleware)


@app.middleware("http")
async def log_requests(request: Request, call_next) -> Response:
    start = time.perf_counter()
    response: Response = await call_next(request)
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    logger.info("%s %s -> %d (%dms)", request.method, request.url.path, response.status_code, elapsed_ms)
    return response


errors.install(app)


# Info API. Dulu ada di "/", lalu tergeser waktu web UI di-mount di "/" (commit
# 76bdcc3). Sekarang tinggal di "/api" bersama route lainnya, sedangkan "/"
# memang milik UI.
@app.get("/api", include_in_schema=False, dependencies=[Depends(require_role("PUBLIC"))])
async def api_info() -> dict:
    return {"message": app.title, "docs": app.docs_url, "version": app.version}


def _role(min_role: str) -> list:
    return [Depends(require_role(min_role))]


# Role minimum per kelompok (INTERFACE.md §4). Route yang butuh role lebih
# tinggi, atau unduhan, menambah require_role(...) sendiri.
app.include_router(health.router, prefix="/api", tags=["Health"], dependencies=_role("PUBLIC"))
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(public.router, prefix="/api/public", tags=["Public"], dependencies=_role("PUBLIC"))
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"], dependencies=_role("ADMIN"))
app.include_router(scenes.router, prefix="/api/scenes", tags=["Scenes"], dependencies=_role("DATA_ENGINEER"))
app.include_router(products.router, prefix="/api/products", tags=["Products"], dependencies=_role("DATA_ENGINEER"))
app.include_router(quality.router, prefix="/api/quality", tags=["Quality"], dependencies=_role("DATA_ENGINEER"))
app.include_router(lineage.router, prefix="/api/metadata", tags=["Lineage"], dependencies=_role("DATA_ENGINEER"))
# /api/preview/* (thumbnail on-the-fly dari COG) sudah dipensiunkan: galeri
# membaca PNG tier PREVIEW lewat /api/datasets/{id}/preview, dan dua jalur
# render dengan stretch/NoData berbeda berarti dua definisi "preview".
# /api/storage/* membaca disk seluruh mesin -> ADMIN (Tahap 2, S5).
app.include_router(storage.router, prefix="/api/storage", tags=["Storage"], dependencies=_role("ADMIN"))
app.include_router(pipeline.router, prefix="/api/pipeline", tags=["Pipeline"], dependencies=_role("DATA_ENGINEER"))
app.include_router(datasets.router, prefix="/api/datasets", tags=["Datasets"], dependencies=_role("DATA_ENGINEER"))
app.include_router(report.router, prefix="/api/datasets", tags=["Report"], dependencies=_role("DATA_ENGINEER"))
app.include_router(live.router, prefix="/api/live", tags=["Live"], dependencies=_role("USER"))
app.include_router(regions.router, prefix="/api/regions", tags=["Regions"], dependencies=_role("USER"))
app.include_router(regions.rois_router, prefix="/api/rois", tags=["Regions"], dependencies=_role("USER"))
# Tahap 3: monitoring (INTERFACE.md §4.4–4.6, §4.9).
app.include_router(admin_monitor.router, prefix="/api/admin", tags=["Admin"], dependencies=_role("ADMIN"))
app.include_router(hydromet.router, prefix="/api/hydromet", tags=["Hydromet"], dependencies=_role("USER"))
app.include_router(alerts.router, prefix="/api/alerts", tags=["Alerts"], dependencies=_role("USER"))
app.include_router(alerts.rules_router, prefix="/api/alert-rules", tags=["Alerts"], dependencies=_role("USER"))
app.include_router(disasters.router, prefix="/api/disasters", tags=["Disasters"], dependencies=_role("ANALYST"))
app.include_router(disasters.types_router, prefix="/api/disaster-types", tags=["Disasters"],
                   dependencies=_role("USER"))
app.include_router(reports.router, prefix="/api/reports", tags=["Reports"], dependencies=_role("USER"))
app.include_router(excel.router, prefix="/api/excel", tags=["Excel"], dependencies=_role("USER"))


def route_min_roles(route) -> list[tuple[str, bool]]:
    """(min_role, download) setiap require_role yang menjaga route."""
    found = []
    stack = [getattr(route, "dependant", None)]
    while stack:
        dep = stack.pop()
        if dep is None:
            continue
        call = getattr(dep, "call", None)
        if call is not None and hasattr(call, "min_role"):
            found.append((call.min_role, call.download))
        stack.extend(dep.dependencies)
    return found


_ROLE_ORDER = ("PUBLIC", "USER", "ANALYST", "DATA_ENGINEER", "ADMIN")


def custom_openapi() -> dict:
    """OpenAPI dengan `x-min-role` per operasi (INTERFACE.md §6.1)."""
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(title=app.title, version=app.version, description=app.description,
                         routes=app.routes)
    for route in app.routes:
        roles = route_min_roles(route)
        if not roles or not getattr(route, "include_in_schema", False):
            continue
        strongest = max((r for r, _ in roles), key=_ROLE_ORDER.index)
        for method in getattr(route, "methods", ()):
            op = schema.get("paths", {}).get(route.path_format, {}).get(method.lower())
            if op is not None:
                op["x-min-role"] = strongest
                if any(d for _, d in roles):
                    op["x-download"] = True
    schema.setdefault("components", {}).setdefault("securitySchemes", {}).update({
        "bearerToken": {"type": "http", "scheme": "bearer",
                        "description": "Personal API token trn_... (GET only)"},
        "sessionCookie": {"type": "apiKey", "in": "cookie", "name": "orbit_u_session"},
    })
    schema["security"] = [{"bearerToken": []}, {"sessionCookie": []}]
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi


# "/" milik landing page (web/index.html); aplikasi kerjanya ada di "/app".
# Halaman HTML tidak membawa data; pemeriksaan login /app dilakukan app.js
# lewat /api/auth/me (data tetap dijaga API).
@app.get("/app", include_in_schema=False)
async def web_app() -> FileResponse:
    return FileResponse("web/app.html")


@app.get("/masuk", include_in_schema=False)
async def web_login() -> FileResponse:
    return FileResponse("web/masuk.html")


app.mount("/", StaticFiles(directory="web", html=True), name="web")
