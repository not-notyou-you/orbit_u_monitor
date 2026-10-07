# api/routes/public.py
"""Halaman publik (INTERFACE.md §4.2): scene Live terbaru per area aktif, tanpa login.

Hanya scene TERBARU yang publik: tanpa prakiraan, tanpa riwayat tanggal.
Data dibaca lewat ``v_public_live_latest`` di bawah role ``monitor_public``;
path berkas PNG (folder dataset, yang tidak boleh dibaca PUBLIC) dicari
dengan koneksi ``monitor_etl`` SETELAH VIEW memastikan tanggalnya terbaru.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.deps import get_etl_db, get_session
from api.errors import ApiError

router = APIRouter()


def _preview(item: dict, url: str) -> dict:
    """Satu tile publik. "url_boundaries" hanya disertakan kalau varian garis
    wilayah ada di disk (lihat etl/admin_overlay.py)."""
    out = {"label": item.get("label"), "legend": item.get("legend"), "url": url}
    if item.get("file_adm"):
        out["url_boundaries"] = url + "?boundaries=1"
    return out


def _public_item(r) -> dict:
    items = ((r["previews"] or {}).get("items") or {})
    return {
        "area_id": r["area_id"],
        "area_name": r["area_name"],
        "scene_date": r["scene_date"],
        "status": r["status"],
        "area_status": r["area_status"] or None,
        "interpretations": r["interpretations"] or {},
        "previews": {key: _preview(v, f"/api/public/live/{r['area_id']}/preview/{key}.png")
                     for key, v in items.items()},
        # Georeferensi grid PNG (empat sudut lon/lat) -- dipakai halaman Relief
        # 3D publik untuk menempatkan citra di atas DEM. Ikut dari manifest
        # `previews` yang sudah ada di VIEW, jadi tidak ada kolom baru yang
        # perlu dibuka ke role monitor_public. None untuk scene yang dirender
        # sebelum ini dicatat; halaman tujuan mengatakannya, bukan menebak.
        "preview_grid": (r["previews"] or {}).get("grid"),
    }


@router.get("/live", summary="Latest Live scene per active area (public)")
def public_live(sess: Session = Depends(get_session)) -> dict:
    rows = sess.execute(text("SELECT * FROM v_public_live_latest ORDER BY area_name")).mappings().all()
    return {"items": [_public_item(r) for r in rows], "total": len(rows)}


@router.get("/live/{area_id}/preview/{key}.png", summary="Preview PNG of the latest scene (public)")
def public_preview(area_id: int, key: str, sess: Session = Depends(get_session), etl=Depends(get_etl_db),
                   scene_date: date | None = Query(None, alias="date",
                                                   description="Only the latest scene date is accepted"),
                   boundaries: bool = Query(False, description="Variant with kecamatan borders and names")):
    row = sess.execute(text("SELECT scene_date, previews FROM v_public_live_latest WHERE area_id = :a"),
                       {"a": area_id}).mappings().first()
    if row is None:
        raise ApiError(404, "No public scene for this area", "NOT_FOUND")
    if scene_date is not None and scene_date != row["scene_date"]:
        raise ApiError(403, "Only the latest scene is public; sign in to see older scenes", "SCENE_NOT_PUBLIC")
    if key not in ((row["previews"] or {}).get("items") or {}):
        raise ApiError(404, "Preview not found", "NOT_FOUND")
    from etl.live_monitor import LiveMonitor
    path = LiveMonitor(etl).preview_path(area_id, row["scene_date"], key, boundaries=boundaries)
    if path is None:
        raise ApiError(404, "Preview not found", "NOT_FOUND")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "public, max-age=3600"})
