# api/routes/diagram.py
"""Halaman Forecast (dulu Diagram; INTERFACE.md §4.3, M56, M61): ANALYST dan ADMIN.

* ``/latest``  — keadaan terbaru: SEMUA band dalam satu grafik, 30 hari
  terakhir, satu warna per band. Band per kecamatan (GPM, MODIS) dirata-rata
  ke seluruh kecamatan AOI; Sentinel-1 (VV, VH) dari metrik scene Live
  (tingkat AOI, karena radar tidak dihitung per kecamatan). ``updated_at``
  dipakai UI untuk memperbarui grafik otomatis saat data baru masuk.
* ``/regions`` — analisa daerah: kecamatan × band × rentang tanggal bebas.
* ``/forecast`` — forecast 15 hari satu band (rerata AOI, satu kecamatan,
  atau rerata beberapa kecamatan) dari seluruh riwayatnya. Dibaca dari
  ``band_forecasts`` bila masih berlaku (``etl.forecast_store``, M62), selain
  itu dihitung di tempat (``etl.band_forecast``).
* ``/report.pdf`` — PDF analisa daerah: daerah & tanggal pilihan pengguna,
  isinya SEMUA band per kecamatan.

Penjelasan, warna, dan garis ambang tiap band dari ``etl.band_catalog``.
"""

from __future__ import annotations

import tempfile
import threading
from collections import OrderedDict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.deps import get_session, mark_download, require_role
from api.errors import ApiError
from etl import band_catalog as bc
from etl import band_forecast as bf
from etl import forecast_store as fs

router = APIRouter()

MAX_REGIONS = 12
MAX_RANGE_DAYS = 3660


def _num(v):
    return None if v is None else float(v)


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _bands(sess: Session, codes: tuple[str, ...] | None = None) -> list[dict]:
    rows = sess.execute(text("""
        SELECT b.band_code, b.band_name, b.unit, s.source_code
        FROM spectral_bands b JOIN satellite_sources s USING (source_id)
        WHERE b.band_code = ANY(:codes) ORDER BY b.band_id"""),
        {"codes": list(dict.fromkeys(codes or (bc.AOI_BANDS + bc.REGION_BANDS)))}).mappings().all()
    return [bc.band_info(r) for r in rows]


def _parse_ids(raw: str, name: str) -> list[int]:
    try:
        ids = [int(x) for x in raw.split(",") if x.strip()]
    except ValueError:
        raise ApiError(400, f"{name} must be a comma-separated list of integers", "BAD_REQUEST")
    if not ids:
        raise ApiError(400, f"{name} must not be empty", "BAD_REQUEST")
    return list(dict.fromkeys(ids))


def _parse_bands(raw: str | None) -> list[str]:
    if not raw:
        return list(bc.REGION_BANDS)
    codes = [c.strip().upper() for c in raw.split(",") if c.strip()]
    bad = [c for c in codes if c not in bc.REGION_BANDS]
    if bad:
        raise ApiError(400, f"Bands not available per kecamatan: {', '.join(bad)}", "INVALID_BAND")
    return list(dict.fromkeys(codes))


def _check_range(date_from: date, date_to: date) -> None:
    if date_from > date_to or (date_to - date_from).days > MAX_RANGE_DAYS:
        raise ApiError(400, f"date_from must be before date_to and the range at most {MAX_RANGE_DAYS} days",
                       "INVALID_DATE_RANGE")


def _aoi_regions(sess: Session, ids: list[int]) -> list[dict]:
    rows = sess.execute(text("""SELECT region_id, pcode, region_name FROM administrative_regions
                                WHERE region_id = ANY(:ids) AND admin_level = 3 ORDER BY region_name"""),
                        {"ids": ids}).mappings().all()
    if len(rows) != len(ids):
        raise ApiError(400, "Every region_id must be a kecamatan", "NOT_KECAMATAN")
    return [dict(r) for r in rows]


def _days(date_from: date, date_to: date) -> list[date]:
    return [date_from + timedelta(days=k) for k in range((date_to - date_from).days + 1)]


def region_series(sess: Session, region_ids: list[int], bands: list[str], date_from: date, date_to: date) -> dict:
    """{band_code: {region_id: [{x, y}]}} dari region_observations, SATU titik
    per hari (y = null bila hari itu tidak ada angka) supaya grafik memutus
    garis di hari kosong, bukan menyambungnya seolah ada data."""
    rows = sess.execute(text("""
        SELECT o.region_id, b.band_code, o.obs_date, o.value
        FROM region_observations o JOIN spectral_bands b USING (band_id)
        WHERE o.region_id = ANY(:r) AND b.band_code = ANY(:b) AND o.obs_date BETWEEN :f AND :t"""),
        {"r": region_ids, "b": bands, "f": date_from, "t": date_to}).all()
    got = {(rid, band, d): _num(v) for rid, band, d, v in rows}
    days = _days(date_from, date_to)
    return {b: {r: [{"x": d.isoformat(), "y": got.get((r, b, d))} for d in days] for r in region_ids}
            for b in bands}


def band_ranges(sess: Session, end: date) -> dict[str, tuple[float, float]]:
    """Rentang "biasa" tiap band = persentil 2–98 rerata AOI harian/scene
    dalam 365 hari sampai `end`. Grafik semua band menskalakan tiap garis ke
    rentang ini, bukan ke min–maks jendela 30 hari: dengan min–maks jendela,
    empat titik yang hampir sama pun melompat dari 0 ke 1."""
    start = end - timedelta(days=365)
    rows = sess.execute(text("""
        WITH daily AS (
            SELECT b.band_code, o.obs_date AS d, avg(o.value) AS v
            FROM region_observations o JOIN spectral_bands b USING (band_id)
            JOIN administrative_regions r ON r.region_id = o.region_id AND r.in_aoi
            WHERE o.obs_date BETWEEN :f AND :t GROUP BY 1, 2
            UNION ALL
            SELECT b.band_code, s.scene_date, avg(m.value)
            FROM live_scene_metrics m JOIN live_scenes s USING (live_scene_id)
            JOIN spectral_bands b ON b.band_id = m.band_id
            WHERE m.metric_name = 'mean' AND s.scene_date BETWEEN :f AND :t GROUP BY 1, 2
        )
        SELECT band_code, percentile_cont(0.02) WITHIN GROUP (ORDER BY v),
               percentile_cont(0.98) WITHIN GROUP (ORDER BY v)
        FROM daily WHERE v IS NOT NULL GROUP BY band_code"""), {"f": start, "t": end}).all()
    return {band: (float(lo), float(hi)) for band, lo, hi in rows}


@router.get("/bands", summary="Bands shown in the diagrams: explanation, colour, thresholds")
def bands(sess: Session = Depends(get_session)) -> dict:
    # Tanggal observasi per kecamatan terakhir: UI memakainya sebagai akhir
    # rentang bawaan dan untuk menjelaskan grafik yang kosong.
    last = sess.scalar(text("SELECT max(obs_date) FROM region_observations"))
    return {"items": _bands(sess), "last_obs_date": last}


@router.get("/latest", summary="All bands in one series set, last N days (AOI mean; Sentinel-1 per Live scene)")
def latest(sess: Session = Depends(get_session), days: int = Query(30, ge=7, le=120),
           end: date | None = Query(None, description="Last day of the window; default today (UTC)")) -> dict:
    """Satu titik per hari per band. Sumber per titik:
    * `daily`  — rerata kecamatan AOI dari Job Hidromet (region_observations);
    * `scene`  — rerata AOI metrik scene Live, dipakai untuk band harian hanya
      pada hari yang belum punya angka harian (mis. Job Hidromet/backfill
      tertinggal), dan selalu untuk Sentinel-1 (VV/VH hanya ada per lintasan).
    `range` = rentang biasa 365 hari untuk skala grafik."""
    end = end or _today()
    start = end - timedelta(days=days - 1)
    info = _bands(sess)
    codes = [b["band_code"] for b in info]
    vals: dict[tuple[str, date], tuple[float | None, str]] = {}
    for band, d, v in sess.execute(text("""
        SELECT b.band_code, s.scene_date, avg(m.value)
        FROM live_scene_metrics m
        JOIN live_scenes s ON s.live_scene_id = m.live_scene_id
        JOIN live_areas a ON a.area_id = s.area_id AND a.deleted_at IS NULL
        JOIN spectral_bands b ON b.band_id = m.band_id
        WHERE m.metric_name = 'mean' AND b.band_code = ANY(:codes)
          AND s.scene_date BETWEEN :f AND :t AND s.status IN ('READY', 'PARTIAL', 'DELETED')
        GROUP BY 1, 2"""), {"f": start, "t": end, "codes": codes}).all():
        vals[(band, d)] = (_num(v), "scene")
    for band, d, v in sess.execute(text("""
        SELECT b.band_code, o.obs_date, avg(o.value)
        FROM region_observations o
        JOIN spectral_bands b USING (band_id)
        JOIN administrative_regions r ON r.region_id = o.region_id AND r.in_aoi
        WHERE o.obs_date BETWEEN :f AND :t AND b.band_code = ANY(:codes)
        GROUP BY 1, 2"""), {"f": start, "t": end, "codes": list(bc.REGION_BANDS)}).all():
        vals[(band, d)] = (_num(v), "daily")       # angka harian menang atas scene
    ranges = band_ranges(sess, end)
    last = dict(sess.execute(text("""
        SELECT b.band_code, max(o.obs_date) FROM region_observations o JOIN spectral_bands b USING (band_id)
        GROUP BY 1""")).all())
    days_ = _days(start, end)
    out = []
    for b in info:
        code = b["band_code"]
        pts = []
        for d in days_:
            v, src = vals.get((code, d), (None, None))
            pts.append({"x": d.isoformat(), "y": v, "source": src})
        lo, hi = ranges.get(code, (None, None))
        vs = [p["y"] for p in pts if p["y"] is not None]
        if lo is None and vs:
            lo, hi = min(vs), max(vs)
        out.append({**b, "points": pts, "range": None if lo is None else [lo, hi],
                    "sparse": code in bc.AOI_BANDS, "n_points": len(vs),
                    "n_daily": sum(1 for p in pts if p["source"] == "daily"),
                    "last_daily_date": last.get(code)})
    updated = sess.scalar(text("""SELECT greatest(
        (SELECT max(computed_at) FROM region_observations),
        (SELECT max(updated_at) FROM live_scenes))"""))
    return {"date_from": start, "date_to": end, "updated_at": updated,
            "last_obs_date": sess.scalar(text("SELECT max(obs_date) FROM region_observations")), "bands": out}


# Forecast yang tidak tersimpan (rentang di masa lalu, rerata beberapa
# kecamatan, horizon selain 15) dihitung di tempat dan disimpan di memori
# sampai cap data band berubah.
_FC_CACHE: OrderedDict[tuple, dict] = OrderedDict()
_FC_CACHE_MAX = 256
_FC_LOCK = threading.Lock()


@router.get("/forecast", summary="Forecast of one band (AOI mean, one kecamatan, or the mean of several) from its full history")
def forecast(sess: Session = Depends(get_session),
             band: str = Query(..., description="Band code"),
             region_id: int | None = Query(None, description="Kecamatan; omit for the AOI mean"),
             region_ids: str | None = Query(None, description="Comma-separated kecamatan (max 12): forecast of their daily mean"),
             end: date | None = Query(None, description="Use data up to this day; default today (UTC)"),
             horizon: int = Query(bf.HORIZON, ge=1, le=30)) -> dict:
    """Satu deret per request supaya UI bisa menampilkan progres per deret.

    Jalur cepat (M62): forecast tersimpan di band_forecasts, dihitung saat data
    baru masuk (etl/forecast_store.py). Dipakai bila cap data band sama dengan
    saat dihitung dan `end` tidak memotong data yang dipakainya (end >=
    observasi terakhir). Selain itu dihitung di tempat (etl/band_forecast.py)."""
    code = band.strip().upper()
    ids = _parse_ids(region_ids, "region_ids") if region_ids else [region_id] if region_id is not None else None
    if ids and len(ids) > MAX_REGIONS:
        raise ApiError(400, f"At most {MAX_REGIONS} kecamatan at once", "BAD_REQUEST")
    allowed = bc.REGION_BANDS if ids else bc.AOI_BANDS + bc.REGION_BANDS
    if code not in allowed:
        raise ApiError(400, f"Band not available{' per kecamatan' if ids else ''}: {code}", "INVALID_BAND")
    if ids:
        _aoi_regions(sess, ids)
        ids = sorted(ids)
    end = end or _today()
    single = ids[0] if ids and len(ids) == 1 else None
    stamp = fs.band_stamp(sess, code)
    meta = {"region_id": single, "region_ids": ids, "end": end}

    if horizon == bf.HORIZON and (not ids or single is not None):
        row = fs.latest(sess, code, single)
        if row and row["data_stamp"] == stamp and end >= date.fromisoformat(row["last_obs_date"] or row["end_date"].isoformat()):
            return {**row, **meta}

    key = (code, tuple(ids or ()), end, horizon, stamp)
    with _FC_LOCK:
        hit = _FC_CACHE.get(key)
        if hit is not None:
            _FC_CACHE.move_to_end(key)
            return hit
    pts = fs.aoi_points(sess, code, end) if not ids else fs.region_points(sess, code, ids, end)
    out = {**bf.forecast(pts, code, horizon), **meta, "stored": False}
    with _FC_LOCK:
        _FC_CACHE[key] = out
        while len(_FC_CACHE) > _FC_CACHE_MAX:
            _FC_CACHE.popitem(last=False)
    return out


@router.get("/regions", summary="Per-kecamatan series for chosen regions, bands and dates")
def regions(sess: Session = Depends(get_session),
            region_ids: str = Query(..., description="Comma-separated kecamatan region_id (max 12)"),
            bands: str | None = Query(None, description="Comma-separated band codes; default all per-kecamatan bands"),
            date_from: date = Query(...), date_to: date = Query(...)) -> dict:
    ids = _parse_ids(region_ids, "region_ids")
    if len(ids) > MAX_REGIONS:
        raise ApiError(400, f"At most {MAX_REGIONS} kecamatan at once", "BAD_REQUEST")
    codes = _parse_bands(bands)
    _check_range(date_from, date_to)
    regs = _aoi_regions(sess, ids)
    data = region_series(sess, ids, codes, date_from, date_to)
    return {"date_from": date_from, "date_to": date_to, "regions": regs,
            "bands": [{**b, "series": [{"region_id": r["region_id"], "points": data[b["band_code"]][r["region_id"]]}
                                       for r in regs]} for b in _bands(sess, tuple(codes))]}


@router.get("/report.pdf", summary="PDF of the region analysis: chosen kecamatan and dates, all bands")
def report_pdf(request: Request, sess: Session = Depends(get_session),
               region_ids: str = Query(...), date_from: date = Query(...), date_to: date = Query(...),
               colors: str | None = Query(None, description="Comma-separated #rrggbb per region, same order"),
               _p=Depends(require_role("ANALYST", download=True))) -> Response:
    ids = _parse_ids(region_ids, "region_ids")
    if len(ids) > MAX_REGIONS:
        raise ApiError(400, f"At most {MAX_REGIONS} kecamatan at once", "BAD_REQUEST")
    _check_range(date_from, date_to)
    regs = _aoi_regions(sess, ids)
    palette = [c.strip() for c in (colors or "").split(",")]
    colour = {rid: (palette[i] if i < len(palette) and len(palette[i]) == 7 and palette[i].startswith("#") else None)
              for i, rid in enumerate(ids)}
    codes = list(bc.REGION_BANDS)
    data = region_series(sess, ids, codes, date_from, date_to)

    from etl.report_diagram import build
    with tempfile.TemporaryDirectory(prefix="orbit_u_diagram_") as wd:
        out = Path(wd) / "diagram.pdf"
        build(out, regions=regs, colours=colour, bands=_bands(sess, tuple(codes)), data=data,
              date_from=date_from, date_to=date_to, generated_at=datetime.now(timezone.utc), workdir=Path(wd))
        body = out.read_bytes()
    filename = f"analisa_daerah_{date_from.isoformat()}_{date_to.isoformat()}.pdf"
    mark_download(request, "DOWNLOAD_REPORT", "region_observations", None, format="pdf", filename=filename,
                  region_ids=ids)
    return Response(body, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
