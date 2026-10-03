# etl/live_metrics.py
"""Metrik ringkas satu scene Daerah Live, dihitung dari COG PROCESSED.

Satu fungsi publik, scene_inputs() + compute_metrics(). Hasilnya angka-angka
kecil (rata-rata, persen) yang dipakai untuk kalimat kondisi
(etl/live_interpret.py), grafik, dan forecast. Karena itu harus tetap ada
walau berkasnya sudah dihapus retensi -- yang disimpan adalah angkanya, bukan
pointer ke raster.

Penyimpanan (M31): angka ditulis sebagai baris live_scene_metrics (satu baris
per band x metrik, save_scene_metrics); deskriptor teks (run IMERG, periode
komposit, tanggal observasi) ikut di live_scenes.source_status[sumber].meta.
load_scene_metrics menyusun ulang dict yang sama persis bentuknya dengan
compute_metrics(), sehingga live_interpret, live_forecast, dan kartu Live
tidak perlu tahu tabelnya.

Nilai dihitung dari raster ASLI (bukan dari PNG preview). Satu pengecualian:
raster Sentinel-1 dibaca turun ke sisi terpanjang S1_METRIC_MAX_SIDE (rata-rata
di ranah linear) supaya AOI besar tidak memuat ratusan juta piksel ke memori.
Raster yang sudah difilter Lee tidak berubah berarti oleh agregasi ini.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling

from etl import folder_manager as fm
from etl import module7_modis_download as m7
from etl import module8_gpm_download as m8
from etl.live_interpret import THRESHOLDS
from etl.module9_fusion import AUX_DAY_OFFSETS

logger = logging.getLogger(__name__)

S1_METRIC_MAX_SIDE = 2048
MODIS_BANDS = ("FLOOD", "NDVI", "NDWI")
GPM_WINDOWS = ("24h", "72h", "7d")


# ---------------------------------------------------------------------------
# Pencarian berkas
# ---------------------------------------------------------------------------

def s1_frames(root: Path, scene_date: date) -> list[dict[str, Path]]:
    """[{VV: path, VH: path}] per frame S1 tanggal itu (COG _lee)."""
    dk = scene_date.strftime("%Y%m%d")
    base = root / fm.SOURCE_DIR_NAMES["sentinel1"] / "PROCESSED"
    frames: dict[str, dict[str, Path]] = {}
    if base.is_dir():
        for p in sorted(base.glob(f"*_{dk}T*_lee.tif")):
            for band in ("VV", "VH"):
                tag = f"_{band}_lee.tif"
                if p.name.endswith(tag):
                    frames.setdefault(p.name[: -len(tag)], {})[band] = p
    return [f for f in frames.values() if f]


def aux_file(root: Path, source: str, band: str, scene_date: date) -> tuple[Path, date] | None:
    """Berkas MODIS/GPM untuk tanggal scene, memakai urutan pencocokan yang
    sama dengan fusion (AUX_DAY_OFFSETS: hari itu, lalu D-1)."""
    sub = fm.SOURCE_DIR_NAMES[source]
    for off in AUX_DAY_OFFSETS:
        d = scene_date + timedelta(days=off)
        dk = d.strftime("%Y%m%d")
        name = m7.band_filename(band, dk) if source == "modis" else m8.band_filename(band, dk)
        p = root / sub / "PROCESSED" / name
        if p.exists():
            return p, d
    return None


def scene_inputs(root: Path, scene_date: date) -> dict:
    """Semua input satu scene: {'s1': [frames], 'modis': {band: (path, d)},
    'gpm': {window: (path, d)}} -- yang tidak ada tidak muncul."""
    return {
        "s1": s1_frames(root, scene_date),
        "modis": {b: f for b in MODIS_BANDS if (f := aux_file(root, "modis", b, scene_date))},
        "gpm": {w: f for w in GPM_WINDOWS if (f := aux_file(root, "gpm", w, scene_date))},
    }


# ---------------------------------------------------------------------------
# Pembacaan
# ---------------------------------------------------------------------------

def _read(path: Path, band: int = 1, max_side: int | None = None) -> tuple[np.ndarray, dict]:
    """Band sebagai float64 dengan NaN di NoData, plus tag berkasnya."""
    with rasterio.open(path) as src:
        shape = None
        if max_side and max(src.width, src.height) > max_side:
            s = max_side / max(src.width, src.height)
            shape = (max(1, int(src.height * s)), max(1, int(src.width * s)))
        data = src.read(band, out_shape=shape, masked=True,
                        resampling=Resampling.average if shape else Resampling.nearest)
        tags = src.tags()
    arr = np.asarray(data.astype(np.float64).filled(np.nan), dtype=np.float64)
    arr[~np.isfinite(arr)] = np.nan
    return arr, tags


def _r(v, nd=2):
    return None if v is None or not np.isfinite(v) else round(float(v), nd)


def _to_db(lin: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        out = 10.0 * np.log10(np.where(lin > 0, lin, np.nan))
    return out


# ---------------------------------------------------------------------------
# Metrik per sumber
# ---------------------------------------------------------------------------

def s1_metrics(frames: list[dict[str, Path]]) -> dict | None:
    """Rata-rata VV/VH (dB) dan % piksel VH di bawah ambang air, dikumpulkan
    dari semua frame hari itu."""
    vv_all, vh_all = [], []
    for f in frames:
        for band, bucket in (("VV", vv_all), ("VH", vh_all)):
            if band in f:
                arr, _ = _read(f[band], max_side=S1_METRIC_MAX_SIDE)
                # GOLD menyimpan sigma0 linear (0 = di luar swath). Data yang
                # sudah dB (instalasi dengan cog_convert_db) punya median
                # negatif; linear tidak pernah.
                valid = arr[np.isfinite(arr)]
                if valid.size and np.median(valid) > 0:
                    arr = _to_db(arr)
                bucket.append(arr[np.isfinite(arr)].ravel())
    if not vv_all and not vh_all:
        return None
    vv = np.concatenate(vv_all) if vv_all else np.array([])
    vh = np.concatenate(vh_all) if vh_all else np.array([])
    thr = THRESHOLDS["s1_vh_water_db"]
    return {
        "vv_mean_db": _r(vv.mean()) if vv.size else None,
        "vh_mean_db": _r(vh.mean()) if vh.size else None,
        "vh_water_pct": _r((vh < thr).mean() * 100) if vh.size else None,
        "vh_water_threshold_db": thr,
        "frames": len(frames),
        "valid_pixels": int(vh.size),
    }


def modis_metrics(files: dict[str, tuple[Path, date]]) -> dict:
    out: dict = {}
    if "FLOOD" in files:
        path, d = files["FLOOD"]
        arr, tags = _read(path)
        total = arr.size
        valid = np.isfinite(arr) & (arr != 255)
        n = int(valid.sum())
        v = arr[valid]
        out["flood"] = {
            "matched_date": d.isoformat(),
            "observation_date": tags.get("OBSERVATION_DATE"),
            "valid_pct": _r(n / total * 100 if total else 0),
            "cloud_pct": _r(100 - n / total * 100 if total else 100),
            # Persen dari piksel yang TERAMATI, bukan dari seluruh AOI.
            "flood_pct": _r((v == 3).mean() * 100) if n else None,
            "recurring_pct": _r((v == 2).mean() * 100) if n else None,
            "water_pct": _r(np.isin(v, (1, 2, 3)).mean() * 100) if n else None,
        }
    for band in ("NDVI", "NDWI"):
        if band not in files:
            continue
        path, d = files[band]
        arr, tags = _read(path)
        age, _ = _read(path, band=2)
        valid = np.isfinite(arr)
        n = int(valid.sum())
        v = arr[valid]
        periods = [p for p in (tags.get("PERIODS_USED") or "").split(",") if p]
        entry = {
            "matched_date": d.isoformat(),
            "valid_pct": _r(n / arr.size * 100 if arr.size else 0),
            "cloud_pct": _r(100 - n / arr.size * 100 if arr.size else 100),
            "mean": _r(v.mean(), 3) if n else None,
            "age_days_median": _r(np.nanmedian(age[valid]), 1) if n else None,
            # MOD09A1 = komposit 8 hari; tanggal awal periode terbaru dipakai.
            "composite_period": periods[0] if periods else None,
            "lookback_days": int(tags["LOOKBACK_DAYS"]) if tags.get("LOOKBACK_DAYS") else None,
        }
        if band == "NDWI":
            entry["water_pct"] = _r((v > THRESHOLDS["ndwi_water"]).mean() * 100) if n else None
        out[band.lower()] = entry
    return out


def gpm_metrics(files: dict[str, tuple[Path, date]]) -> dict:
    out: dict = {}
    for window, (path, d) in files.items():
        arr, tags = _read(path)
        v = arr[np.isfinite(arr)]
        v = v[v >= 0]
        out[f"rain_{window}"] = {
            "matched_date": d.isoformat(),
            "mean_mm": _r(v.mean(), 1) if v.size else None,
            "max_mm": _r(v.max(), 1) if v.size else None,
            "imerg_runs": tags.get("IMERG_RUNS"),
            "window_start": tags.get("WINDOW_START_UTC"),
            "window_end": tags.get("WINDOW_END_UTC"),
        }
    return out


def compute_metrics(inputs: dict, scene_date: date | None = None) -> dict:
    """{'sentinel1': {...}|None, 'modis': {...}, 'gpm': {...}}. Satu sumber
    yang gagal dibaca tidak menggugurkan yang lain.

    Entri MODIS/GPM yang berkasnya diambil dari tanggal lain (D-1) diberi
    `nearest: True` supaya UI dan kalimat kondisi menyebutnya "terdekat"."""
    result: dict = {}
    for key, fn, arg in (
        ("sentinel1", s1_metrics, inputs.get("s1") or []),
        ("modis", modis_metrics, inputs.get("modis") or {}),
        ("gpm", gpm_metrics, inputs.get("gpm") or {}),
    ):
        try:
            result[key] = fn(arg) if arg else ({} if key != "sentinel1" else None)
        except Exception:
            logger.exception("[LIVE] metrik %s gagal", key)
            result[key] = {} if key != "sentinel1" else None
    if scene_date is not None:
        iso = scene_date.isoformat()
        for key in ("modis", "gpm"):
            for entry in (result.get(key) or {}).values():
                entry["nearest"] = entry.get("matched_date") != iso
    return result


def source_status(inputs: dict, metrics: dict) -> dict:
    """Status tiap sumber: OK | UNAVAILABLE (berkas ada, tapi tidak ada piksel
    valid -- awan) | FAILED (berkas tidak ada: unduh/proses gagal, bisa dicoba
    ulang)."""
    st: dict = {}
    s1 = metrics.get("sentinel1")
    st["sentinel1"] = {"status": "OK" if s1 and s1.get("valid_pixels") else "FAILED",
                       "frames": len(inputs.get("s1") or [])}

    mod = metrics.get("modis") or {}
    missing = [b for b in MODIS_BANDS if b not in (inputs.get("modis") or {})]
    if missing:
        m_status = "FAILED"
    elif all((mod.get(k) or {}).get("valid_pct") in (0, None) for k in ("flood", "ndvi", "ndwi")):
        m_status = "UNAVAILABLE"
    else:
        m_status = "OK"
    st["modis"] = {"status": m_status, "missing": missing}

    g_missing = [w for w in GPM_WINDOWS if w not in (inputs.get("gpm") or {})]
    st["gpm"] = {"status": "FAILED" if g_missing else "OK", "missing": g_missing}
    return st


# ---------------------------------------------------------------------------
# Penyimpanan 1NF (M31): dict compute_metrics() <-> baris live_scene_metrics
# ---------------------------------------------------------------------------

# (sumber, entri, field dict) -> (band_code, metric_name). entri None = dict
# sumbernya langsung (Sentinel-1 tidak bersarang per band).
METRIC_ROWS: tuple[tuple[str, str | None, str, str, str], ...] = (
    ("sentinel1", None, "vv_mean_db", "VV", "mean"),
    ("sentinel1", None, "vh_mean_db", "VH", "mean"),
    ("sentinel1", None, "vh_water_pct", "VH", "pct_below_threshold"),
    ("sentinel1", None, "vh_water_threshold_db", "VH", "threshold_db"),
    ("sentinel1", None, "frames", "VH", "frames"),
    ("sentinel1", None, "valid_pixels", "VH", "valid_pixels"),
    *(("modis", "flood", f, "FLOOD", f)
      for f in ("valid_pct", "cloud_pct", "flood_pct", "recurring_pct", "water_pct")),
    *(("modis", "ndvi", f, "NDVI", f)
      for f in ("valid_pct", "cloud_pct", "mean", "age_days_median", "lookback_days")),
    *(("modis", "ndwi", f, "NDWI", f)
      for f in ("valid_pct", "cloud_pct", "mean", "age_days_median", "lookback_days", "water_pct")),
    *(("gpm", f"rain_{w}", f, f"RAIN_{w.upper()}", metric)
      for w in GPM_WINDOWS for f, metric in (("mean_mm", "mean"), ("max_mm", "max"))),
)
_ROW_BY_KEY = {(band, metric): (src, entry, field) for src, entry, field, band, metric in METRIC_ROWS}
_INT_FIELDS = frozenset({"frames", "valid_pixels", "lookback_days"})
# Deskriptor teks: tidak dikueri, jadi ikut source_status[sumber].meta (K6).
META_FIELDS: dict[str, tuple[str, ...]] = {
    "modis": ("observation_date", "composite_period"),
    "gpm": ("imerg_runs", "window_start", "window_end"),
}


def metric_rows(metrics: dict, scene_date: date) -> tuple[list[tuple], dict]:
    """Pecah dict compute_metrics() menjadi ([(band_code, metric_name, value,
    source_date)], meta). Field yang ada tapi bernilai None tetap jadi baris
    (value NULL) supaya entri sumbernya tersusun ulang apa adanya."""
    rows: list[tuple] = []
    for src, entry_key, field, band, metric in METRIC_ROWS:
        container = metrics.get(src)
        entry = container if entry_key is None else (container or {}).get(entry_key)
        if not entry or field not in entry:
            continue
        matched = entry.get("matched_date") if entry_key is not None else None
        source_date = date.fromisoformat(matched) if matched else (
            scene_date if entry_key is None else None)
        rows.append((band, metric, entry[field], source_date))
    meta: dict = {}
    for src, fields in META_FIELDS.items():
        for entry_key, entry in (metrics.get(src) or {}).items():
            kept = {f: entry[f] for f in fields if f in entry}
            if kept:
                meta.setdefault(src, {})[entry_key] = kept
    return rows, meta


def metrics_from_rows(rows, meta: dict | None, scene_date: date | None) -> dict:
    """Kebalikan metric_rows(): susun ulang dict berbentuk compute_metrics()
    dari baris (band_code, metric_name, value, source_date) + meta. Baris yang
    tidak dikenal peta ini (mis. WATER_CHANGE) dilewati."""
    out: dict = {"sentinel1": None, "modis": {}, "gpm": {}}
    for band, metric, value, source_date in rows:
        key = _ROW_BY_KEY.get((band, metric))
        if key is None:
            continue
        src, entry_key, field = key
        if value is not None:
            value = int(value) if field in _INT_FIELDS else float(value)
        if entry_key is None:
            out[src] = out[src] or {}
            out[src][field] = value
            continue
        entry = out[src].setdefault(entry_key, {})
        entry[field] = value
        if source_date is not None:
            entry["matched_date"] = source_date.isoformat()
    for src, entries in (meta or {}).items():
        target = out.get(src)
        for entry_key, fields in (entries or {}).items():
            if isinstance(target, dict) and isinstance(target.get(entry_key), dict):
                target[entry_key].update(fields)
    if scene_date is not None:
        iso = scene_date.isoformat()
        for src in ("modis", "gpm"):
            for entry in out[src].values():
                entry["nearest"] = entry.get("matched_date") != iso
    return out


def save_scene_metrics(sess, live_scene_id: int, scene_date: date, metrics: dict) -> dict:
    """Ganti seluruh baris live_scene_metrics satu scene dengan isi `metrics`
    (dalam session pemanggil). Mengembalikan meta deskriptor untuk ditaruh
    di source_status[sumber].meta."""
    from sqlalchemy import delete, select

    from etl.database_client import LiveSceneMetric, SpectralBand

    rows, meta = metric_rows(metrics, scene_date)
    band_ids = dict(sess.execute(select(SpectralBand.band_code, SpectralBand.band_id)).all())
    sess.execute(delete(LiveSceneMetric).where(
        LiveSceneMetric.live_scene_id == live_scene_id,
        LiveSceneMetric.metric_name.in_({metric for *_, metric in METRIC_ROWS}),
        LiveSceneMetric.band_id.in_([band_ids[b] for b in {r[3] for r in METRIC_ROWS}]),
    ))
    sess.add_all(
        LiveSceneMetric(live_scene_id=live_scene_id, band_id=band_ids[band],
                        metric_name=metric, value=value, source_date=source_date)
        for band, metric, value, source_date in rows
    )
    sess.flush()
    return meta


def load_scene_metrics(sess, scenes) -> dict[int, dict]:
    """{live_scene_id: dict berbentuk compute_metrics()} untuk baris
    LiveScene yang diberikan (dalam session pemanggil)."""
    from sqlalchemy import select

    from etl.database_client import LiveSceneMetric, SpectralBand

    scenes = list(scenes)
    by_id: dict[int, list] = {s.live_scene_id: [] for s in scenes}
    if by_id:
        for sid, band, metric, value, source_date in sess.execute(
            select(LiveSceneMetric.live_scene_id, SpectralBand.band_code,
                   LiveSceneMetric.metric_name, LiveSceneMetric.value,
                   LiveSceneMetric.source_date)
            .join(SpectralBand, SpectralBand.band_id == LiveSceneMetric.band_id)
            .where(LiveSceneMetric.live_scene_id.in_(list(by_id)))
        ):
            by_id[sid].append((band, metric, value, source_date))
    return {
        s.live_scene_id: metrics_from_rows(
            by_id[s.live_scene_id],
            {src: (v or {}).get("meta") or {} for src, v in (s.source_status or {}).items()
             if isinstance(v, dict)},
            s.scene_date,
        )
        for s in scenes
    }
