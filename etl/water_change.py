# etl/water_change.py
"""Peta perubahan air Sentinel-1 antar scene Live (PIPELINE.md §4.1, M19).

1. VH (dB) scene sekarang dan scene pembanding dibaca pada grid scene
   sekarang, diturunkan ke sisi terpanjang 2048 px dengan rata-rata di ruang
   LINEAR (rata-rata dB bukan rata-rata daya).
2. Air = ``VH < app_settings.water.vh_threshold_db`` (default −20 dB).
3. Kelas per piksel yang valid di kedua tanggal:

       PERSISTENT  air -> air      biru   #2F6FDE
       NEW         darat -> air    merah  #E04545
       RECEDED     air -> darat    hijau  #2FA36B
       LAND        darat -> darat  transparan (latar VH abu)
       NODATA      NoData salah satu tanggal -> pola kotak-kotak

4. Orbit relatif berbeda -> label "orbit berbeda — perubahan bisa karena
   geometri pencitraan" di PNG dan ``same_orbit = 0``.
5. Luas = jumlah piksel × luas piksel geodesik (km²).

Keterbatasan (ditulis di skripsi): ambang tetap (bukan Otsu), permukaan
halus bisa terbaca air, vegetasi tergenang bisa terbaca darat.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject

from etl.atomic_write import atomic_path

logger = logging.getLogger(__name__)

PREVIEW_KEY = "s1_water_change"
DEFAULT_THRESHOLD_DB = -20.0
MAX_SIDE = 2048
PNG_MAX_SIDE = 768
EARTH_RADIUS_KM = 6371.0088

NODATA, LAND, PERSISTENT, NEW, RECEDED = 0, 1, 2, 3, 4
COLORS = {PERSISTENT: "#2F6FDE", NEW: "#E04545", RECEDED: "#2FA36B"}
LABELS = {PERSISTENT: "Air tetap", NEW: "Air baru", RECEDED: "Air surut", LAND: "Darat tetap",
          NODATA: "Tidak ada data"}
ORBIT_WARNING = "orbit berbeda — perubahan bisa karena geometri pencitraan"

# Orbit relatif Sentinel-1 dari orbit absolut (ESA: siklus 175 orbit).
# S1C/S1D belum punya offset yang terverifikasi -> None (tidak dibandingkan).
_ORBIT_OFFSET = {"S1A": 73, "S1B": 27}
_PRODUCT_RE = re.compile(r"^(S1[A-D])_\w+?_\d{8}T\d{6}_\d{8}T\d{6}_(\d{6})_")


def relative_orbit(product_id: str | None) -> int | None:
    """Orbit relatif dari nama produk S1 (…_{orbit absolut 6 digit}_…)."""
    if not product_id:
        return None
    m = _PRODUCT_RE.match(Path(product_id).name)
    if not m or m.group(1) not in _ORBIT_OFFSET:
        return None
    return (int(m.group(2)) - _ORBIT_OFFSET[m.group(1)]) % 175 + 1


def same_orbit(cur_products, prev_products) -> bool | None:
    """True/False bila orbit relatif kedua scene diketahui; None bila tidak."""
    a = {o for p in cur_products or [] if (o := relative_orbit(p)) is not None}
    b = {o for p in prev_products or [] if (o := relative_orbit(p)) is not None}
    if not a or not b:
        return None
    return bool(a & b)


@dataclass
class WaterChange:
    classes: np.ndarray          # uint8 kelas di atas
    vh_db: np.ndarray            # VH sekarang (dB, NaN = NoData), untuk latar PNG
    transform: object
    crs: object
    metrics: dict = field(default_factory=dict)


# --- pembacaan -------------------------------------------------------------------

def _target_shape(width: int, height: int, max_side: int) -> tuple[int, int]:
    if max(width, height) <= max_side:
        return height, width
    s = max_side / max(width, height)
    return max(1, round(height * s)), max(1, round(width * s))


def _to_linear(arr: np.ndarray) -> tuple[np.ndarray, bool]:
    """(linear, was_db). COG Live menyimpan sigma0 linear (0 = di luar
    swath); instalasi lama bisa menyimpan dB (median negatif)."""
    valid = arr[np.isfinite(arr)]
    if valid.size and np.median(valid) < 0:
        return np.where(np.isfinite(arr), 10.0 ** (arr / 10.0), np.nan), True
    return np.where(np.isfinite(arr) & (arr > 0), arr, np.nan), False


def _read_linear(path: Path) -> tuple[np.ndarray, object, object]:
    with rasterio.open(path) as src:
        arr = src.read(1, masked=True).astype("float64").filled(np.nan)
        lin, _ = _to_linear(arr)
        return lin, src.transform, src.crs


def read_vh_pair(cur_path: Path, prev_path: Path, max_side: int = MAX_SIDE):
    """(cur_lin, prev_lin, transform, crs) di grid turunan scene sekarang."""
    cur, cur_tf, crs = _read_linear(cur_path)
    h, w = _target_shape(cur.shape[1], cur.shape[0], max_side)
    dst_tf = cur_tf * cur_tf.scale(cur.shape[1] / w, cur.shape[0] / h)
    out = []
    for arr, tf, src_crs in ((cur, cur_tf, crs), _read_linear(prev_path)):
        dst = np.full((h, w), np.nan, dtype="float64")
        reproject(arr, dst, src_transform=tf, src_crs=src_crs, dst_transform=dst_tf, dst_crs=crs,
                  src_nodata=np.nan, dst_nodata=np.nan, resampling=Resampling.average)
        out.append(dst)
    return out[0], out[1], dst_tf, crs


def to_db(lin: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(np.isfinite(lin) & (lin > 0), 10.0 * np.log10(lin), np.nan)


# --- klasifikasi & luas -------------------------------------------------------------

def classify(cur_db: np.ndarray, prev_db: np.ndarray, threshold_db: float = DEFAULT_THRESHOLD_DB) -> np.ndarray:
    valid = np.isfinite(cur_db) & np.isfinite(prev_db)
    cur_w = cur_db < threshold_db
    prev_w = prev_db < threshold_db
    out = np.full(cur_db.shape, NODATA, dtype="uint8")
    out[valid & ~prev_w & ~cur_w] = LAND
    out[valid & prev_w & cur_w] = PERSISTENT
    out[valid & ~prev_w & cur_w] = NEW
    out[valid & prev_w & ~cur_w] = RECEDED
    return out


def pixel_area_km2(transform, crs, shape: tuple[int, int]) -> np.ndarray:
    """Luas tiap piksel (km²), shape (rows, 1) untuk broadcast. Grid
    geografis: luas pita lintang pada bola (R² Δλ |sin φ1 − sin φ2|)."""
    rows = shape[0]
    a, e, f = transform.a, transform.e, transform.f
    if crs is not None and crs.is_geographic:
        top = f + np.arange(rows) * e
        bottom = top + e
        dlon = math.radians(abs(a))
        area = EARTH_RADIUS_KM ** 2 * dlon * np.abs(np.sin(np.radians(top)) - np.sin(np.radians(bottom)))
        return area[:, None]
    return np.full((rows, 1), abs(a * e) / 1e6)


def summarize(classes: np.ndarray, areas: np.ndarray) -> dict:
    full = np.broadcast_to(areas, classes.shape)
    def km2(cls):
        return round(float(full[classes == cls].sum()), 4)
    valid = classes != NODATA
    return {"new_km2": km2(NEW), "receded_km2": km2(RECEDED), "persistent_km2": km2(PERSISTENT),
            "valid_km2": round(float(full[valid].sum()), 4),
            "valid_fraction": round(float(valid.mean()) if classes.size else 0.0, 4)}


def compute(cur_vh: Path, prev_vh: Path, threshold_db: float = DEFAULT_THRESHOLD_DB,
            max_side: int = MAX_SIDE) -> WaterChange:
    cur_lin, prev_lin, tf, crs = read_vh_pair(cur_vh, prev_vh, max_side)
    cur_db, prev_db = to_db(cur_lin), to_db(prev_lin)
    classes = classify(cur_db, prev_db, threshold_db)
    metrics = summarize(classes, pixel_area_km2(tf, crs, classes.shape))
    metrics["threshold_db"] = threshold_db
    return WaterChange(classes, cur_db, tf, crs, metrics)


# --- PNG --------------------------------------------------------------------------

def _hex_rgb(h: str) -> tuple[int, int, int]:
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


def render_png(wc: WaterChange, path: Path, *, orbit_differs: bool = False, max_side: int = PNG_MAX_SIDE) -> dict:
    """PNG RGB: latar VH abu, kelas berwarna, NoData kotak-kotak, label orbit."""
    from PIL import Image, ImageDraw

    classes, db = wc.classes, wc.vh_db
    # Diskalakan (nearest) ke sisi terpanjang max_side, naik maupun turun,
    # supaya tile seragam dan label orbit selalu terbaca.
    s = max_side / max(classes.shape)
    h, w = max(1, round(classes.shape[0] * s)), max(1, round(classes.shape[1] * s))
    if (h, w) != classes.shape:
        ri = (np.arange(h) * classes.shape[0] / h).astype(int)
        ci = (np.arange(w) * classes.shape[1] / w).astype(int)
        classes, db = classes[np.ix_(ri, ci)], db[np.ix_(ri, ci)]
    finite = db[np.isfinite(db)]
    lo, hi = (np.percentile(finite, (2, 98)) if finite.size else (-25.0, 0.0))
    gray = np.clip((np.nan_to_num(db, nan=lo) - lo) / max(hi - lo, 1e-6), 0, 1) * 200 + 30
    rgb = np.repeat(gray[..., None], 3, axis=2)
    yy, xx = np.indices(classes.shape)
    checker = np.where(((yy // 8) + (xx // 8)) % 2 == 0, 205.0, 245.0)
    nod = classes == NODATA
    rgb[nod] = checker[nod][:, None]
    for cls, color in COLORS.items():
        rgb[classes == cls] = _hex_rgb(color)
    img = Image.fromarray(rgb.astype("uint8"), mode="RGB")
    if orbit_differs:
        draw = ImageDraw.Draw(img)
        text = ORBIT_WARNING
        box = draw.textbbox((0, 0), text)
        draw.rectangle((4, 4, box[2] + 12, box[3] + 12), fill=(255, 255, 255))
        draw.text((8, 8), text, fill=(180, 40, 40))
    with atomic_path(path) as tmp:
        img.save(tmp, format="PNG")
    return {
        "type": "categorical",
        "categories": [{"value": c, "color": COLORS.get(c, "#00000000" if c == LAND else "checker"),
                        "label": LABELS[c]} for c in (PERSISTENT, NEW, RECEDED, LAND, NODATA)],
        "opacity": 1.0,
        "warning": ORBIT_WARNING if orbit_differs else None,
    }


# --- metrik ke live_scene_metrics ----------------------------------------------------

# valid_km2 (luas teramati di kedua tanggal) tambahan atas §4.1: penyebut
# persen perubahan bersih untuk kategori kalimat.
METRIC_NAMES = ("new_km2", "receded_km2", "persistent_km2", "valid_km2", "same_orbit")


def save_metrics(sess, live_scene_id: int, ref_live_scene_id: int, metrics: dict,
                 same: bool | None, source_date=None) -> None:
    """Ganti baris band WATER_CHANGE satu scene (§4.1 langkah 5)."""
    from sqlalchemy import text

    band_id = sess.scalar(text("SELECT band_id FROM spectral_bands WHERE band_code = 'WATER_CHANGE'"))
    sess.execute(text("DELETE FROM live_scene_metrics WHERE live_scene_id = :s AND band_id = :b"),
                 {"s": live_scene_id, "b": band_id})
    values = {k: metrics.get(k) for k in METRIC_NAMES[:4]}
    if same is not None:
        values["same_orbit"] = 1 if same else 0
    for name, value in values.items():
        sess.execute(text("""
            INSERT INTO live_scene_metrics (live_scene_id, band_id, metric_name, value, source_date, ref_live_scene_id)
            VALUES (:s, :b, :m, :v, :d, :ref)"""),
            {"s": live_scene_id, "b": band_id, "m": name, "v": value, "d": source_date, "ref": ref_live_scene_id})


def load_metrics(sess, live_scene_ids) -> dict[int, dict]:
    """{live_scene_id: {new_km2, receded_km2, persistent_km2, same_orbit, ref_live_scene_id, ref_date}}."""
    from sqlalchemy import text

    ids = list(live_scene_ids)
    if not ids:
        return {}
    rows = sess.execute(text("""
        SELECT m.live_scene_id, m.metric_name, m.value, m.ref_live_scene_id, r.scene_date AS ref_date
        FROM live_scene_metrics m
        JOIN spectral_bands b ON b.band_id = m.band_id AND b.band_code = 'WATER_CHANGE'
        LEFT JOIN live_scenes r ON r.live_scene_id = m.ref_live_scene_id
        WHERE m.live_scene_id = ANY(:ids)"""), {"ids": ids}).all()
    out: dict[int, dict] = {}
    for sid, name, value, ref, ref_date in rows:
        d = out.setdefault(sid, {"ref_live_scene_id": ref, "ref_date": ref_date})
        d[name] = None if value is None else float(value)
    return out


def sentence(wc: dict | None) -> dict:
    """Kalimat Bahasa Indonesia untuk tile perubahan air (format live_interpret)."""
    from etl.live_interpret import NA, THRESHOLDS, _delta_category, _sentence, fmt

    what = "perubahan air radar (VH)"
    if not wc:
        return _sentence(what, NA, "belum ada scene pembanding")
    new, rec = wc.get("new_km2") or 0.0, wc.get("receded_km2") or 0.0
    ref = wc.get("ref_date")
    because = (f"air baru {fmt(new, 2)} km² dan air surut {fmt(rec, 2)} km² dibanding scene "
               f"{ref.isoformat() if hasattr(ref, 'isoformat') else ref}")
    if wc.get("same_orbit") == 0:
        because += f" ({ORBIT_WARNING})"
    # Kategori dari pertambahan bersih air sebagai poin persen area teramati,
    # dengan ambang yang sama dengan kalimat VH (s1_vh_*_delta_pct).
    valid = wc.get("valid_km2") or 0.0
    net_pct = (new - rec) / valid * 100 if valid > 0 else None
    cat = _delta_category(net_pct, THRESHOLDS["s1_vh_warn_delta_pct"], THRESHOLDS["s1_vh_flood_delta_pct"])
    return _sentence(what, cat, because)
