# api/routes/lokasi.py
"""Pantau Lokasi (INTERFACE.md §4.7, M63): kondisi SATU kecamatan, tanpa login.

Beranda menampilkan, untuk kecamatan yang dipilih (atau tempat perangkat
berada): kalimat kondisi normal/tidak beserta apa yang tidak normal, citra
satelit scene terbaru yang dipotong ke kecamatan itu, angka terbaru, dan tren.

Angka dibaca lewat VIEW ``v_public_lokasi_*`` di bawah role pemanggil, jadi
batas waktu (PUBLIC 30 hari, USER 365 hari) ditegakkan database, sama dengan
halaman Citra. Koneksi ``monitor_etl`` hanya dipakai untuk hal yang tidak
boleh dibaca PUBLIC dan tidak pernah dikirim ke klien: bbox Live Area (untuk
mencari scene yang menutupi kecamatan), path berkas PNG, dan ambang BMKG di
``alert_rules`` (supaya kalimat hujan memakai angka alert yang sama).
Pembacanya ada di etl/lokasi_data.py, dipakai juga peringatan email (M64).

Koordinat perangkat TIDAK pernah dikirim ke endpoint ini: browser sendiri
yang mencocokkan titiknya dengan poligon ``GET /api/regions``.
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.deps import get_etl_db, get_session
from api.errors import ApiError
from etl import band_catalog as bc
from etl import lokasi_data as ld

router = APIRouter()


def _region(sess: Session, region_id: int) -> dict:
    found = ld.regions(sess, [region_id])
    if not found:
        raise ApiError(404, "Kecamatan is not in the monitored area", "NOT_FOUND")
    return found[0]


@router.get("", summary="Monitored kecamatan with a short condition status (public)")
def lokasi_list(sess: Session = Depends(get_session), etl=Depends(get_etl_db)) -> dict:
    ld.sync_thresholds(etl)
    items = []
    for rid, c in ld.conditions(sess).items():
        r = c["region"]
        items.append({
            "region_id": rid, "pcode": r["pcode"], "name": r["name"], "area_km2": r["area_km2"],
            "status": c["status"], "abnormal": len(c["abnormal"]),
            "alert": max((a["severity"] for a in c["alerts"]), key=ld.SEV_RANK.get, default=None),
            "dates": c["dates"],
        })
    return {"items": items, "total": len(items)}


@router.get("/{region_id}", summary="Condition of one kecamatan: sentence, latest numbers, imagery (public)")
def lokasi_detail(region_id: int, sess: Session = Depends(get_session), etl=Depends(get_etl_db)) -> dict:
    region = _region(sess, region_id)
    ld.sync_thresholds(etl)
    latest, prev = ld.obs(sess, region_id).get(region_id, ({}, {}))
    ranges = ld.ranges(sess, region_id).get(region_id, {})
    alerts = ld.alerts(sess, region_id).get(region_id, [])
    res = ld.interpret(latest, prev, ranges, alerts)

    names = dict(sess.execute(text("SELECT band_code, band_name FROM spectral_bands WHERE band_code = ANY(:c)"),
                              {"c": list(ld.TREND_BANDS)}).all())
    units = dict(sess.execute(text("SELECT band_code, unit FROM spectral_bands WHERE band_code = ANY(:c)"),
                              {"c": list(ld.TREND_BANDS)}).all())
    stats = []
    for g, title, bands in ld.GROUPS:
        for b in bands:
            cur, old = latest.get(b) or {}, prev.get(b) or {}
            stats.append({
                "group": g, "group_title": title, "band_code": b, "band_name": names.get(b, b),
                "unit": units.get(b), "color": bc.BANDS.get(b, {}).get("color"), "about": bc.about(b),
                "value": cur.get("value"), "obs_date": cur.get("obs_date"),
                "prev_value": old.get("value"), "prev_date": old.get("obs_date"),
                "range": ranges.get(b), "thresholds": bc.thresholds(b),
            })

    scene = ld.scene(sess, etl, region_id)
    imagery = None
    if scene is not None:
        items = ((scene["previews"] or {}).get("items") or {})
        cropped = ld.has_grid(scene)
        base = f"/api/public/lokasi/{region_id}/preview"
        full = f"/api/public/live/{scene['area_id']}/preview"
        imagery = {
            "area_id": scene["area_id"], "area_name": scene["area_name"], "scene_date": scene["scene_date"],
            # Tanpa grid (scene lama) potongan tidak bisa dibuat: UI memakai tile
            # seluruh area dan mengatakannya.
            "cropped": cropped,
            "interpretations": scene["interpretations"] or {},
            "previews": {k: {"label": v.get("label"), "legend": v.get("legend"),
                             "url": f"{base}/{k}.png" if cropped else f"{full}/{k}.png"}
                         for k, v in items.items()},
        }
    return {"region": region, **res, "stats": stats, "alerts": alerts, "imagery": imagery}


@router.get("/{region_id}/trend", summary="Daily series of one kecamatan for the trend charts (public)")
def lokasi_trend(region_id: int, sess: Session = Depends(get_session),
                 days: int = Query(30, ge=7, le=90)) -> dict:
    _region(sess, region_id)
    end = sess.scalar(text("SELECT max(obs_date) FROM v_public_lokasi_obs WHERE region_id = :r"), {"r": region_id})
    if end is None:
        return {"dates": [], "groups": []}
    start = end - timedelta(days=days - 1)
    rows = sess.execute(text("""
        SELECT band_code, obs_date, value FROM v_public_lokasi_obs
        WHERE region_id = :r AND obs_date BETWEEN :a AND :b AND band_code = ANY(:c)"""),
        {"r": region_id, "a": start, "b": end, "c": list(ld.TREND_BANDS)}).all()
    got = {(b, d): ld.num(v) for b, d, v in rows}
    dates: list[date] = [start + timedelta(days=i) for i in range(days)]
    ranges = ld.ranges(sess, region_id).get(region_id, {})
    units = dict(sess.execute(text("SELECT band_code, unit FROM spectral_bands WHERE band_code = ANY(:c)"),
                              {"c": list(ld.TREND_BANDS)}).all())
    return {
        "dates": dates,
        "groups": [{
            "key": g, "title": title,
            "bands": [{"band_code": b, "unit": units.get(b), "color": bc.BANDS.get(b, {}).get("color"),
                       "range": ranges.get(b), "values": [got.get((b, d)) for d in dates]} for b in bands],
        } for g, title, bands in ld.GROUPS],
    }


@router.get("/{region_id}/preview/{key}.png", summary="Latest-scene preview PNG cropped to one kecamatan (public)")
def lokasi_preview(region_id: int, key: str, sess: Session = Depends(get_session), etl=Depends(get_etl_db)):
    _region(sess, region_id)
    out, why = ld.cropped_preview(sess, etl, region_id, ld.scene(sess, etl, region_id), key)
    if why == "GRID_MISSING":
        raise ApiError(404, "This scene has no georeference; use the full-area preview", "GRID_MISSING")
    if out is None:
        raise ApiError(404, "Preview not found" if why == "NOT_FOUND" else "Kecamatan is outside this scene",
                       "NOT_FOUND")
    return FileResponse(out, media_type="image/png", headers={"Cache-Control": "public, max-age=3600"})
