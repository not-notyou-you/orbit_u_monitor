from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

import logging
import mimetypes
import os
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import Depends, FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from api import errors
from api.activity import ActivityLogMiddleware
from api.compression import GZipTextMiddleware
from api.deps import get_db, require_role, set_clients  # noqa: F401  (get_db di-re-export)
from api.routes import (
    admin, admin_monitor, alerts, auth, citra, data, datasets, diagram, disasters, excel, health, hydromet,
    lineage, live, lokasi, logs, pipeline, products, public, quality, regions, report, reports, scenes, storage,
)
from api.security import jwt_secret
from etl.database_client import DatabaseClient

mimetypes.add_type("image/webp", ".webp")
logger = logging.getLogger(__name__)


def _env_flag(name: str) -> bool:
    return os.getenv(name, "true").lower() in ("1", "true", "yes")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    jwt_secret()
    app_client = DatabaseClient.from_env("app")
    etl_client = DatabaseClient.from_env("etl")
    set_clients(app_client, etl_client)
    health_info = app_client.check_health()
    if not health_info.get("connected"):
        logger.error("[API] DB health check FAILED: %s", health_info)
    elif _env_flag("AUTO_RESUME_JOBS"):
        try:
            from etl.dataset_manager import DatasetManager
            resumed = DatasetManager(etl_client).recover_interrupted_jobs()
            if resumed:
                logger.warning("[API] %d job terputus dilanjutkan: %s", len(resumed), resumed)
        except Exception:
            logger.exception("[API] gagal memulihkan job yang terputus")

    scheduler = None
    if _env_flag("SCHEDULER_ENABLED"):
        try:
            from etl.scheduler import Scheduler
            scheduler = Scheduler(etl_client)
            scheduler.start()
        except Exception:
            logger.exception("[API] Scheduler gagal dimulai; job terjadwal tidak berjalan")
            scheduler = None
    app.state.scheduler = scheduler

    yield

    if scheduler:
        scheduler.shutdown()
    set_clients(None, None)
    app_client.dispose()
    etl_client.dispose()


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
    lifespan=lifespan,
)
app.add_middleware(ActivityLogMiddleware)
app.add_middleware(GZipTextMiddleware)
errors.install(app)


@app.get("/api", include_in_schema=False, dependencies=[Depends(require_role("PUBLIC"))])
async def api_info() -> dict:
    return {"message": app.title, "docs": app.docs_url, "version": app.version}


_ROUTERS = [
    (health.router, "/api", "Health", "PUBLIC"),
    (auth.router, "/api/auth", "Auth", None),
    (public.router, "/api/public", "Public", "PUBLIC"),
    (lokasi.router, "/api/public/lokasi", "Public", "PUBLIC"),
    (citra.router, "/api/citra", "Imagery", "PUBLIC"),
    (diagram.router, "/api/diagram", "Diagram", "ANALYST"),
    (data.router, "/api/data", "Data", "DATA_ENGINEER"),
    (logs.router, "/api/logs", "Logs", "USER"),
    (admin.router, "/api/admin", "Admin", "ADMIN"),
    (scenes.router, "/api/scenes", "Scenes", "DATA_ENGINEER"),
    (products.router, "/api/products", "Products", "DATA_ENGINEER"),
    (quality.router, "/api/quality", "Quality", "DATA_ENGINEER"),
    (lineage.router, "/api/metadata", "Lineage", "DATA_ENGINEER"),
    (storage.router, "/api/storage", "Storage", "ADMIN"),
    (pipeline.router, "/api/pipeline", "Pipeline", "DATA_ENGINEER"),
    (datasets.router, "/api/datasets", "Datasets", "DATA_ENGINEER"),
    (report.router, "/api/datasets", "Report", "DATA_ENGINEER"),
    (live.router, "/api/live", "Live", "USER"),
    (regions.router, "/api/regions", "Regions", "PUBLIC"),
    (regions.rois_router, "/api/rois", "Regions", "USER"),
    (admin_monitor.router, "/api/admin", "Admin", "ADMIN"),
    (hydromet.router, "/api/hydromet", "Hydromet", "USER"),
    (alerts.router, "/api/alerts", "Alerts", "USER"),
    (alerts.rules_router, "/api/alert-rules", "Alerts", "USER"),
    (disasters.router, "/api/disasters", "Disasters", "PUBLIC"),
    (disasters.types_router, "/api/disaster-types", "Disasters", "PUBLIC"),
    (reports.router, "/api/reports", "Reports", "USER"),
    (excel.router, "/api/excel", "Excel", "USER"),
]
for _router, _prefix, _tag, _min_role in _ROUTERS:
    app.include_router(_router, prefix=_prefix, tags=[_tag],
                       dependencies=[Depends(require_role(_min_role))] if _min_role else [])


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
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(title=app.title, version=app.version, description=app.description, routes=app.routes)
    paths = schema.get("paths", {})
    for route in app.routes:
        roles = route_min_roles(route)
        if not roles or not getattr(route, "include_in_schema", False):
            continue
        strongest = max((r for r, _ in roles), key=_ROLE_ORDER.index)
        for method in getattr(route, "methods", ()):
            op = paths.get(route.path_format, {}).get(method.lower())
            if op is not None:
                op["x-min-role"] = strongest
                if any(d for _, d in roles):
                    op["x-download"] = True
    schema.setdefault("components", {}).setdefault("securitySchemes", {}).update({
        "bearerToken": {"type": "http", "scheme": "bearer", "description": "Personal API token trn_... (GET only)"},
        "sessionCookie": {"type": "apiKey", "in": "cookie", "name": "orbit_u_session"},
    })
    schema["security"] = [{"bearerToken": []}, {"sessionCookie": []}]
    from api.openapi_docs import enrich
    enrich(schema)
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi


def _page(path: str, file: str) -> None:
    app.add_api_route(path, lambda: FileResponse(file), include_in_schema=False)


def _redirect(path: str, target: str) -> None:
    app.add_api_route(path, lambda: RedirectResponse(target, status_code=301), include_in_schema=False)


_page("/", "web/app.html")
_page("/app", "web/app.html")
_page("/masuk", "web/masuk.html")
_page("/daftar", "web/daftar.html")
_redirect("/kondisi", "/app#citra")
_redirect("/relief", "/app#aoi-3d")

app.mount("/", StaticFiles(directory="web", html=True), name="web")
