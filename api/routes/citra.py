# api/routes/citra.py
"""Halaman Citra Satelit (INTERFACE.md §4.3, M56): ringkasan, satu halaman per
satelit (Sentinel-1, MODIS, GPM), dan laporan PDF gabungan.

Semua role, termasuk pengunjung. Batas waktu per role TIDAK dihitung di
sini: setiap kueri membaca VIEW ``v_citra_scenes``/``v_citra_metrics`` di
bawah role pemanggil (SET LOCAL ROLE), dan VIEW itu yang memotong tanggal —
PUBLIC 30 hari, USER 365 hari, ANALYST/DATA_ENGINEER/ADMIN semua, scene
terbaru tiap area selalu terlihat. Path berkas PNG (folder dataset, yang tidak
boleh dibaca role interaktif) dicari koneksi ``monitor_etl`` SETELAH VIEW
membuktikan scene itu terlihat (pola /public, M51).
"""

from __future__ import annotations

import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.deps import Principal, current_principal, get_etl_db, get_session, mark_download, require_role
from api.errors import ApiError
from etl import band_catalog as bc

router = APIRouter()

WINDOW_DAYS = {"PUBLIC": 30, "USER": 365}
PAGES = ("ringkasan", "s1", "modis", "gpm")


def _window(principal: Principal) -> dict:
    """Keterangan batas untuk UI; penegakannya di VIEW."""
    if principal.has_role("ANALYST") or principal.has_role("DATA_ENGINEER"):
        days = None
    else:
        days = WINDOW_DAYS["USER" if principal.is_authenticated else "PUBLIC"]
    return {"role_code": principal.role_code, "days": days}


def _source(key: str) -> dict:
    src = bc.SOURCES.get(key)
    if src is None:
        raise ApiError(400, "source must be s1, modis or gpm", "INVALID_SOURCE")
    return src


def _keys_for(previews: dict | None, prefix: str) -> list[str]:
    items = (previews or {}).get("items") or {}
    return sorted(k for k in items if k.startswith(prefix))


def _areas(sess: Session) -> list[dict]:
    rows = sess.execute(text("""
        SELECT area_id, area_name, max(scene_date) AS latest_date, count(*) AS n_scenes
        FROM v_citra_scenes GROUP BY area_id, area_name ORDER BY area_name""")).mappings().all()
    return [dict(r) for r in rows]


def _area_or_default(sess: Session, area_id: int | None) -> dict:
    areas = _areas(sess)
    if not areas:
        raise ApiError(404, "No imagery is available yet", "NOT_FOUND")
    if area_id is None:
        return areas[0]
    found = next((a for a in areas if a["area_id"] == area_id), None)
    if found is None:
        raise ApiError(404, f"Area {area_id} has no imagery visible to your role", "NOT_FOUND")
    return found


def _scene(sess: Session, area_id: int, scene_date: date):
    row = sess.execute(text("""SELECT * FROM v_citra_scenes WHERE area_id = :a AND scene_date = :d"""),
                       {"a": area_id, "d": scene_date}).mappings().first()
    if row is None:
        # Scene yang ada tapi di luar batas role tampak sama dengan yang tidak
        # ada untuk VIEW; bedakan supaya UI bisa menjelaskan.
        raise ApiError(404, "Scene not found or outside the time window of your role", "NOT_FOUND")
    return row


def _metrics(sess: Session, live_scene_id: int, source_code: str) -> list[dict]:
    rows = sess.execute(text("""
        SELECT band_code, band_name, unit, metric_name, value, source_date
        FROM v_citra_metrics WHERE live_scene_id = :s AND source_code = :c
        ORDER BY band_code, metric_name"""), {"s": live_scene_id, "c": source_code}).mappings().all()
    return [{**r, "value": None if r["value"] is None else float(r["value"]),
             "metric_label": bc.METRIC_LABELS.get(r["metric_name"], r["metric_name"]),
             "metric_unit": bc.metric_unit(r["metric_name"], r["unit"])} for r in rows]


def _scene_payload(sess: Session, row, key: str) -> dict:
    src = _source(key)
    items = ((row["previews"] or {}).get("items") or {})
    dk = row["scene_date"].isoformat()
    keys = _keys_for(row["previews"], src["prefix"]) if row["files_available"] else []
    base = f"/api/citra/areas/{row['area_id']}/preview/{dk}"
    previews = {}
    for k in keys:
        it = items[k]
        p = {"label": it.get("label"), "legend": it.get("legend"), "url": f"{base}/{k}.png"}
        if it.get("file_adm"):
            p["url_boundaries"] = p["url"] + "?boundaries=1"
        previews[k] = p
    interp = {k: v for k, v in (row["interpretations"] or {}).items() if k.startswith(src["prefix"])}
    status = (row["source_status"] or {}).get({"s1": "sentinel1", "modis": "modis", "gpm": "gpm"}[key])
    return {
        "area_id": row["area_id"], "area_name": row["area_name"], "date": dk, "status": row["status"],
        "files_available": row["files_available"], "area_status": row["area_status"] or None,
        "source_status": status if isinstance(status, dict) else None,
        "previews": previews, "interpretations": interp,
        "metrics": _metrics(sess, row["live_scene_id"], src["source_code"]),
        "preview_grid": (row["previews"] or {}).get("grid"),
    }


# --- angka harian GPM/MODIS (Job Hidromet, termasuk backfill) --------------------
#
# Scene Live hanya ada pada tanggal lintasan Sentinel-1 (±6–12 hari sekali) dan
# hanya sebanyak retensi. Angka harian GPM/MODIS per kecamatan diisi Job
# Hidromet dan backfill-nya untuk SETIAP hari, tanpa gambar PNG. Halaman
# GPM/MODIS menampilkan keduanya: tanggal scene (gambar + angka) dan tanggal
# angka harian (angka saja). Agregat AOI lewat v_citra_obs_aoi (batas waktu
# per role); angka per kecamatan hanya untuk USER+ (region_observations).

_OBS_METRICS = (("aoi_mean", "mean_value"), ("aoi_max", "max_value"), ("aoi_min", "min_value"))


def _obs_dates(sess: Session, source_code: str) -> list[date]:
    return list(sess.scalars(text("""SELECT DISTINCT obs_date FROM v_citra_obs_aoi WHERE source_code = :c
                                     ORDER BY obs_date DESC"""), {"c": source_code}).all())


def _obs_metrics(sess: Session, d: date, source_code: str) -> list[dict]:
    rows = sess.execute(text("""SELECT * FROM v_citra_obs_aoi WHERE obs_date = :d AND source_code = :c
                                ORDER BY band_code"""), {"d": d, "c": source_code}).mappings().all()
    out = []
    for r in rows:
        for name, col in _OBS_METRICS:
            out.append({"band_code": r["band_code"], "band_name": r["band_name"], "unit": r["unit"],
                        "metric_name": name, "value": None if r[col] is None else float(r[col]),
                        "source_date": d, "metric_label": bc.METRIC_LABELS.get(name, name),
                        "metric_unit": bc.metric_unit(name, r["unit"])})
        out.append({"band_code": r["band_code"], "band_name": r["band_name"], "unit": r["unit"],
                    "metric_name": "n_regions", "value": float(r["n_regions"]), "source_date": d,
                    "metric_label": bc.METRIC_LABELS["n_regions"], "metric_unit": ""})
    return out


def _per_region(sess: Session, principal: Principal, d: date, source_code: str) -> list[dict] | None:
    """Angka per kecamatan untuk USER+; None untuk pengunjung (fitur akun)."""
    if not principal.is_authenticated:
        return None
    rows = sess.execute(text("""
        SELECT r.region_id, r.region_name, b.band_code, o.value
        FROM region_observations o
        JOIN administrative_regions r ON r.region_id = o.region_id AND r.in_aoi
        JOIN spectral_bands b ON b.band_id = o.band_id
        JOIN satellite_sources s ON s.source_id = b.source_id
        WHERE o.obs_date = :d AND s.source_code = :c ORDER BY r.region_name, b.band_code"""),
        {"d": d, "c": source_code}).all()
    regions: dict[int, dict] = {}
    for rid, name, band, v in rows:
        regions.setdefault(rid, {"region_id": rid, "region_name": name, "values": {}})["values"][band] = (
            None if v is None else float(v))
    return list(regions.values())


def _payload(sess: Session, principal: Principal, area: dict, d: date, key: str) -> dict | None:
    """Isi satu tanggal satu satelit: scene Live (gambar) bila ada, ditambah
    angka harian Hidromet untuk GPM/MODIS. None bila keduanya tidak ada."""
    src = _source(key)
    row = sess.execute(text("SELECT * FROM v_citra_scenes WHERE area_id = :a AND scene_date = :d"),
                       {"a": area["area_id"], "d": d}).mappings().first()
    daily = _obs_metrics(sess, d, src["source_code"]) if key != "s1" else []
    if row is None and not daily:
        return None
    if row is not None:
        out = _scene_payload(sess, row, key)
    else:
        out = {"area_id": area["area_id"], "area_name": area["area_name"], "date": d.isoformat(),
               "status": "HIDROMET", "files_available": False, "area_status": None, "source_status": None,
               "previews": {}, "interpretations": {}, "metrics": [], "preview_grid": None}
    out["has_scene"] = row is not None
    if key != "s1":
        out["daily_metrics"] = daily
        out["per_region"] = _per_region(sess, principal, d, src["source_code"]) if daily else None
        if row is None:
            # Tanpa scene Live: angka harian adalah satu-satunya angka.
            out["metrics"] = daily
    return out


# --- endpoint ---------------------------------------------------------------------

@router.get("/summary", summary="Imagery overview per satellite for one area (role time window applied)")
def summary(sess: Session = Depends(get_session), principal: Principal = Depends(current_principal),
            area_id: int | None = Query(None, description="Default: the first area with imagery")) -> dict:
    areas = _areas(sess)
    window = _window(principal)
    if not areas:
        return {"window": window, "areas": [], "area": None, "sources": []}
    area = _area_or_default(sess, area_id)
    rows = sess.execute(text("""SELECT scene_date, files_available, previews FROM v_citra_scenes
                                WHERE area_id = :a ORDER BY scene_date DESC"""),
                        {"a": area["area_id"]}).mappings().all()
    latest = sess.execute(text("""SELECT * FROM v_citra_scenes WHERE area_id = :a AND files_available
                                  ORDER BY scene_date DESC LIMIT 1"""), {"a": area["area_id"]}).mappings().first()
    sources = []
    for key, src in bc.SOURCES.items():
        with_png = [r for r in rows if r["files_available"] and _keys_for(r["previews"], src["prefix"])]
        obs = _obs_dates(sess, src["source_code"]) if key != "s1" else []
        all_dates = sorted({r["scene_date"] for r in rows} | set(obs), reverse=True)
        item = {"key": key, "label": src["label"], "about": src["about"], "revisit": src["revisit"],
                "resolution": src["resolution"], "n_dates": len(all_dates), "n_dates_with_images": len(with_png),
                "n_obs_days": len(obs), "latest_obs_date": obs[0] if obs else None,
                "latest_date": with_png[0]["scene_date"] if with_png else None,
                "oldest_date": all_dates[-1] if all_dates else None, "latest": None}
        if latest is not None:
            p = _scene_payload(sess, latest, key)
            item["latest"] = {"date": p["date"], "interpretations": p["interpretations"],
                              "preview": next(iter(p["previews"].values()), None)}
        sources.append(item)
    return {"window": window, "areas": areas, "area": area,
            "area_status": (latest["area_status"] if latest is not None else None) or None,
            "sources": sources}


@router.get("/sources/{key}", summary="What a satellite measures and which bands it provides")
def source_info(key: str, sess: Session = Depends(get_session)) -> dict:
    src = _source(key)
    rows = sess.execute(text("""
        SELECT b.band_code, b.band_name, b.unit, s.source_code
        FROM spectral_bands b JOIN satellite_sources s USING (source_id)
        WHERE s.source_code = :c ORDER BY b.band_id"""), {"c": src["source_code"]}).mappings().all()
    return {"key": key, **{k: v for k, v in src.items() if k != "prefix"},
            "bands": [bc.band_info(r) for r in rows]}


@router.get("/areas/{area_id}/scenes", summary="Scene dates of one satellite within your role's time window")
def scene_dates(area_id: int, source: str = Query(..., pattern="^(s1|modis|gpm)$"),
                sess: Session = Depends(get_session), principal: Principal = Depends(current_principal)) -> dict:
    src = _source(source)
    area = _area_or_default(sess, area_id)
    rows = sess.execute(text("""SELECT scene_date, status, files_available, previews, area_status
                                FROM v_citra_scenes WHERE area_id = :a ORDER BY scene_date DESC"""),
                        {"a": area_id}).mappings().all()
    obs = set(_obs_dates(sess, src["source_code"])) if source != "s1" else set()
    by_date = {r["scene_date"]: {"date": r["scene_date"].isoformat(), "status": r["status"],
                                 "files_available": r["files_available"], "has_scene": True,
                                 "has_images": bool(r["files_available"] and _keys_for(r["previews"], src["prefix"])),
                                 "has_daily": r["scene_date"] in obs,
                                 "level": (r["area_status"] or {}).get("level")} for r in rows}
    for d in obs - set(by_date):
        by_date[d] = {"date": d.isoformat(), "status": "HIDROMET", "files_available": False, "has_scene": False,
                      "has_images": False, "has_daily": True, "level": None}
    dates = [by_date[d] for d in sorted(by_date, reverse=True)]
    return {"area": area, "source": source, "window": _window(principal), "dates": dates,
            "n_scene_dates": len(rows), "n_daily_dates": len(obs)}


@router.get("/areas/{area_id}/scenes/{scene_date}", summary="One scene of one satellite: images, sentences, numbers")
def scene_detail(area_id: int, scene_date: date, source: str = Query(..., pattern="^(s1|modis|gpm)$"),
                 sess: Session = Depends(get_session), principal: Principal = Depends(current_principal)) -> dict:
    out = _payload(sess, principal, _area_or_default(sess, area_id), scene_date, source)
    if out is None:
        raise ApiError(404, "No scene or daily data on this date, or outside the time window of your role",
                       "NOT_FOUND")
    return out


@router.get("/areas/{area_id}/preview/{scene_date}/{key}.png", summary="Preview PNG of a visible scene")
def preview(area_id: int, scene_date: date, key: str, sess: Session = Depends(get_session),
            etl=Depends(get_etl_db), principal: Principal = Depends(current_principal),
            boundaries: bool = Query(False, description="Variant with kecamatan borders and names")):
    row = _scene(sess, area_id, scene_date)
    if not row["files_available"] or key not in ((row["previews"] or {}).get("items") or {}):
        raise ApiError(404, "Preview not found", "NOT_FOUND")
    from etl.live_monitor import LiveMonitor
    path = LiveMonitor(etl).preview_path(area_id, scene_date, key, boundaries=boundaries)
    if path is None:
        raise ApiError(404, "Preview not found", "NOT_FOUND")
    cache = "public, max-age=3600" if not principal.is_authenticated else "private, max-age=86400"
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": cache})


@router.get("/report.pdf", summary="PDF of selected imagery pages (overview, Sentinel-1, MODIS, GPM)")
def report_pdf(request: Request,
               area_id: int | None = None,
               pages: str = Query("ringkasan,s1,modis,gpm",
                                  description="Comma-separated subset of: ringkasan, s1, modis, gpm"),
               scene_date: date | None = Query(None, alias="date", description="Scene date; default latest"),
               compare: date | None = Query(None, description="Second scene date for the comparison section"),
               sess: Session = Depends(get_session), etl=Depends(get_etl_db),
               principal: Principal = Depends(require_role("PUBLIC", download=True))) -> Response:
    chosen = [p.strip() for p in pages.split(",") if p.strip()]
    if not chosen or any(p not in PAGES for p in chosen):
        raise ApiError(400, "pages must be a comma-separated subset of ringkasan, s1, modis, gpm", "INVALID_PAGES")
    chosen = [p for p in PAGES if p in chosen]          # urutan tetap seperti menu
    area = _area_or_default(sess, area_id)
    if scene_date is None:
        scene_date = sess.scalar(text("""SELECT max(scene_date) FROM v_citra_scenes
                                         WHERE area_id = :a AND files_available"""), {"a": area["area_id"]})
        if scene_date is None:
            raise ApiError(404, "No scene with images is available", "NOT_FOUND")
    keys = [k for k in chosen if k != "ringkasan"]
    mains = {k: _payload(sess, principal, area, scene_date, k) for k in keys}
    cmps = {k: _payload(sess, principal, area, compare, k) for k in keys} if compare else {}
    if keys and all(v is None for v in mains.values()):
        raise ApiError(404, "No scene or daily data on this date, or outside the time window of your role",
                       "NOT_FOUND")
    summ = summary(sess, principal, area["area_id"]) if "ringkasan" in chosen else None

    from etl.live_monitor import LiveMonitor
    from etl.report_citra import build

    monitor = LiveMonitor(etl)

    def png(payload, key):
        if not payload.get("has_scene"):
            return None
        p = monitor.preview_path(area["area_id"], date.fromisoformat(payload["date"]), key)
        return Path(p) if p else None

    def empty(d):
        return {"date": d.isoformat(), "files_available": False, "has_scene": False, "previews": {},
                "interpretations": {}, "metrics": []}

    sections = [{"key": k, "source": bc.SOURCES[k], "main": mains[k] or empty(scene_date),
                 "compare": (cmps.get(k) or empty(compare)) if compare else None} for k in keys]
    generated_at = datetime.now(timezone.utc)
    with tempfile.TemporaryDirectory(prefix="orbit_u_citra_") as wd:
        out = Path(wd) / "citra.pdf"
        build(out, area=area, window=_window(principal), summary=summ, sections=sections, png=png,
              generated_at=generated_at, workdir=Path(wd))
        data = out.read_bytes()
    filename = f"citra_{area['area_id']}_{scene_date.isoformat()}_{'-'.join(chosen)}.pdf"
    mark_download(request, "DOWNLOAD_REPORT", "live_scenes", None, format="pdf", date=str(scene_date),
                  filename=filename, pages=chosen)
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
