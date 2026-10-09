"""M58: Sentinel-1 per kecamatan dan jendela raster dataset utama."""

from datetime import date

import numpy as np
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

from etl import hydromet_aggregate as ha
from etl import raster_retention as rr
from etl import s1_observations as so


def _write(path, arr, x0, y1, res):
    with rasterio.open(path, "w", driver="GTiff", width=arr.shape[1], height=arr.shape[0], count=1,
                       dtype="float32", crs="EPSG:4326", transform=from_origin(x0, y1, res, res),
                       nodata=np.nan) as dst:
        dst.write(arr.astype("float32"), 1)


def test_mosaic_averages_frames_in_linear_and_returns_db(tmp_path):
    # Dua frame bertumpuk penuh: 0.01 dan 0.1 linear -> rata-rata 0.055 -> -12.6 dB.
    a, b = tmp_path / "a.tif", tmp_path / "b.tif"
    _write(a, np.full((20, 20), 0.01), 106.0, -6.0, 0.0005)
    _write(b, np.full((20, 20), 0.1), 106.0, -6.0, 0.0005)
    transform, shape = so._aoi_grid((106.0, -6.009, 106.009, -6.0))
    out = so.mosaic([a, b], transform, shape)
    assert np.allclose(np.nanmean(out), 10 * np.log10(0.055), atol=0.05)


def test_mosaic_accepts_db_input(tmp_path):
    p = tmp_path / "db.tif"
    _write(p, np.full((20, 20), -15.0), 106.0, -6.0, 0.0005)
    transform, shape = so._aoi_grid((106.0, -6.009, 106.009, -6.0))
    assert np.allclose(np.nanmean(so.mosaic([p], transform, shape)), -15.0, atol=0.01)


def test_water_fraction_uses_flood_fraction_rule():
    vh = np.array([[-25.0, -10.0], [-22.0, np.nan]])
    classes = np.where(np.isfinite(vh), np.where(vh < -20, so.WATER_CLASS, 0), so.NODATA_CLASS)
    res = ha.zonal(classes, classes != so.NODATA_CLASS, from_origin(0, 2, 1, 1),
                   box(0, 0, 2, 2), "FRACTION", 0.1)
    assert round(res.value, 1) == 66.7  # 2 dari 3 sel valid di bawah ambang
    assert res.valid_fraction == 0.75


def test_retention_parses_dates_from_names():
    assert rr._file_date("gpm_rain_24h_20240101.tif") == date(2024, 1, 1)
    assert rr._file_date("modis_20240108_flood.tif") == date(2024, 1, 8)
    assert rr._file_date("readme.txt") is None
    assert rr._dir_date("20240110") == date(2024, 1, 10)
    assert rr._dir_date("S1A_IW_GRDH") is None
