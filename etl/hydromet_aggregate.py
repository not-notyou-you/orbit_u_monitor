# etl/hydromet_aggregate.py
"""Zonal statistics COG GPM/MODIS per kecamatan -> ``region_observations`` (PIPELINE.md §3.3).

Raster tidak disimpan di DB, jadi agregasi dikerjakan di Python:

1. Poligon kecamatan ``in_aoi`` dari ``administrative_regions``.
2. Sel raster yang tersentuh poligon: ``geometry_mask(..., all_touched=True)``.
3. Bobot tiap sel = luas irisan ``sel ∩ poligon`` (derajat²) × ``cos(lat)`` pusat
   irisan, yaitu luas permukaan relatif. Untuk GPM 0,1° satu kecamatan hanya
   1–6 sel, sehingga sel tepi yang cuma tersentuh sedikit tidak boleh berbobot
   penuh. Bobot dihitung sekali per (grid, kecamatan) dan di-cache.
4. Nilai:
   ``MEAN``      Σ(w·v) / Σw atas sel valid.
   ``FRACTION``  persen bobot sel valid berkelas air MCDWD (2, 3) terhadap
                 bobot sel valid.
5. ``valid_fraction`` = Σw sel valid / Σw semua sel dalam poligon. Di bawah
   ``app_settings.hydromet.min_valid_fraction`` (0,1) -> ``value = NULL``.
6. Upsert ``ON CONFLICT (region_id, band_id, obs_date)`` hanya bila run baru
   tidak lebih buruk (F > L > E) atau nilai lama NULL, dan nilai NULL tidak
   pernah menimpa nilai yang ada. Inilah yang membuat Final Run menggantikan
   Late Run tanpa logika is_valid (K7/M6).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from sqlalchemy import text

logger = logging.getLogger(__name__)

SOFTWARE_VERSION = "orbit-u-monitor 1.0.0"
ZONAL_METHOD = "area_weighted_overlap"
MIN_VALID_FRACTION = 0.1
FLOOD_WATER_CLASSES = (2, 3)
FLOOD_NODATA = 255

# Urutan kualitas run IMERG. None (MODIS) tidak punya run.
RUN_RANK = {"F": 3, "L": 2, "E": 1}


def worst_run(runs) -> str | None:
    """Run terburuk dari kumpulan run (akumulasi 72h dengan satu hari Late
    adalah produk Late)."""
    runs = [r for r in runs if r in RUN_RANK]
    return min(runs, key=RUN_RANK.__getitem__) if runs else None


@dataclass(frozen=True)
class ZonalResult:
    value: float | None
    valid_fraction: float
    n_cells: int


# --- bobot sel ------------------------------------------------------------------

_WEIGHT_CACHE: dict[tuple, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}


def _grid_key(transform, shape, region_key) -> tuple:
    return (tuple(round(v, 12) for v in tuple(transform)[:6]), tuple(shape), region_key)


def cell_weights(transform, shape: tuple[int, int], geom, region_key=None):
    """(rows, cols, weights) sel yang tersentuh ``geom`` (EPSG:4326).

    ``weights`` = luas irisan sel∩poligon (derajat²) × cos(lat pusat irisan).
    Sel di dalam penuh tidak perlu dipotong; hanya sel tepi yang dihitung
    irisannya (vektorisasi shapely 2).
    """
    import shapely
    from rasterio.features import geometry_mask

    key = _grid_key(transform, shape, region_key) if region_key is not None else None
    if key is not None and key in _WEIGHT_CACHE:
        return _WEIGHT_CACHE[key]

    touched = geometry_mask([geom.__geo_interface__], out_shape=shape, transform=transform,
                            all_touched=True, invert=True)
    rows, cols = np.nonzero(touched)
    if rows.size == 0:
        result = (rows, cols, np.zeros(0))
    else:
        a, b, c, d, e, f = tuple(transform)[:6]
        if b != 0 or d != 0:
            raise ValueError("rotated rasters are not supported")
        x0 = c + cols * a
        x1 = x0 + a
        y0 = f + rows * e
        y1 = y0 + e
        boxes = shapely.box(np.minimum(x0, x1), np.minimum(y0, y1), np.maximum(x0, x1), np.maximum(y0, y1))
        shapely.prepare(geom)
        inside = shapely.contains_properly(geom, boxes)
        area = np.empty(rows.size)
        lat = np.empty(rows.size)
        area[inside] = abs(a * e)
        lat[inside] = (y0[inside] + y1[inside]) / 2.0
        edge = ~inside
        if edge.any():
            inter = shapely.intersection(boxes[edge], geom)
            area[edge] = shapely.area(inter)
            cent = shapely.centroid(inter)
            ys = shapely.get_y(cent)
            lat[edge] = np.where(np.isfinite(ys), ys, (y0[edge] + y1[edge]) / 2.0)
        weights = area * np.cos(np.radians(lat))
        keep = weights > 0
        result = (rows[keep], cols[keep], weights[keep])
    if key is not None:
        _WEIGHT_CACHE[key] = result
    return result


def clear_cache() -> None:
    _WEIGHT_CACHE.clear()


# --- zonal ----------------------------------------------------------------------

def zonal(data: np.ndarray, valid: np.ndarray, transform, geom, aggregation: str,
          min_valid_fraction: float = MIN_VALID_FRACTION, region_key=None) -> ZonalResult:
    """Statistik satu poligon atas satu array (sudah dibaca) dan mask valid-nya."""
    rows, cols, w = cell_weights(transform, data.shape, geom, region_key)
    if w.size == 0 or w.sum() <= 0:
        return ZonalResult(None, 0.0, 0)
    v_ok = valid[rows, cols]
    w_valid = w[v_ok]
    vf = float(w_valid.sum() / w.sum())
    if vf < min_valid_fraction or w_valid.size == 0:
        return ZonalResult(None, round(vf, 4), int(w.size))
    vals = data[rows, cols][v_ok].astype(np.float64)
    if aggregation == "MEAN":
        value = float(np.dot(w_valid, vals) / w_valid.sum())
    elif aggregation == "FRACTION":
        water = np.isin(vals, FLOOD_WATER_CLASSES)
        value = float(w_valid[water].sum() / w_valid.sum() * 100.0)
    else:
        raise ValueError(f"unknown aggregation {aggregation!r}")
    return ZonalResult(value, round(vf, 4), int(w.size))


def read_raster(path: Path, aggregation: str) -> tuple[np.ndarray, np.ndarray, object, dict]:
    """(data, valid, transform, tags) band 1. Raster harus EPSG:4326."""
    with rasterio.open(path) as src:
        if src.crs is not None and src.crs.to_epsg() not in (4326, None):
            raise ValueError(f"{path.name}: expected EPSG:4326, got {src.crs}")
        data = src.read(1)
        nodata = src.nodata
        tags = src.tags()
        transform = src.transform
    valid = np.ones(data.shape, dtype=bool)
    if np.issubdtype(data.dtype, np.floating):
        valid &= np.isfinite(data)
    if nodata is not None and not (isinstance(nodata, float) and math.isnan(nodata)):
        valid &= data != nodata
    if aggregation == "FRACTION":
        valid &= data != FLOOD_NODATA
    return data, valid, transform, tags


def aggregate_raster(path: Path, regions: list[dict], aggregation: str,
                     min_valid_fraction: float = MIN_VALID_FRACTION) -> dict[int, ZonalResult]:
    """{region_id: ZonalResult} untuk satu COG dan daftar kecamatan
    (``etl.regions.aoi_regions``: region_id + wkb)."""
    from shapely import from_wkb

    data, valid, transform, _ = read_raster(path, aggregation)
    out = {}
    for r in regions:
        geom = r.get("geom") or from_wkb(r["wkb"])
        out[r["region_id"]] = zonal(data, valid, transform, geom, aggregation, min_valid_fraction,
                                    region_key=r["region_id"])
    return out


# --- upsert ---------------------------------------------------------------------

_UPSERT = text("""
    INSERT INTO region_observations
        (region_id, band_id, obs_date, value, valid_fraction, source_product_id, run_type, job_id, computed_at)
    VALUES (:region_id, :band_id, :obs_date, :value, :vf, :product_id, :run, :job_id, now())
    ON CONFLICT (region_id, band_id, obs_date) DO UPDATE SET
        value = EXCLUDED.value, valid_fraction = EXCLUDED.valid_fraction,
        source_product_id = EXCLUDED.source_product_id, run_type = EXCLUDED.run_type,
        job_id = EXCLUDED.job_id, computed_at = now()
    WHERE (region_observations.value IS NULL
           OR (EXCLUDED.value IS NOT NULL
               AND COALESCE(CASE EXCLUDED.run_type WHEN 'F' THEN 3 WHEN 'L' THEN 2 WHEN 'E' THEN 1 END, 0)
                   >= COALESCE(CASE region_observations.run_type WHEN 'F' THEN 3 WHEN 'L' THEN 2 WHEN 'E' THEN 1 END, 0)))
    RETURNING obs_id
""")


def band_ids(sess) -> dict[str, tuple[int, str]]:
    """{band_code: (band_id, aggregation)}."""
    return {r.band_code: (r.band_id, r.aggregation)
            for r in sess.execute(text("SELECT band_code, band_id, aggregation FROM spectral_bands"))}


def upsert_observations(sess, band_code: str, obs_date, results: dict[int, ZonalResult], *,
                        run_type: str | None = None, product_id: int | None = None,
                        job_id: int | None = None) -> int:
    """Tulis hasil satu band × tanggal. Mengembalikan jumlah baris yang
    benar-benar ditulis (baris yang ditolak aturan F>L>E tidak dihitung)."""
    band_id = band_ids(sess)[band_code][0]
    written = 0
    for region_id, res in results.items():
        value = None if res.value is None else round(res.value, 4)
        row = sess.execute(_UPSERT, {
            "region_id": region_id, "band_id": band_id, "obs_date": obs_date, "value": value,
            "vf": res.valid_fraction, "product_id": product_id, "run": run_type, "job_id": job_id,
        }).first()
        written += row is not None
    return written


def job_parameters(gpm_run: str | None, n_regions: int, min_valid_fraction: float) -> dict:
    """``processing_jobs.parameters_json`` tahap HYDROMET_AGGREGATE (PIPELINE §3.7)."""
    return {
        "software_version": SOFTWARE_VERSION,
        "stage": "HYDROMET_AGGREGATE",
        "zonal_method": ZONAL_METHOD,
        "all_touched": True,
        "min_valid_fraction": min_valid_fraction,
        "gpm_run": gpm_run,
        "regions": n_regions,
    }
