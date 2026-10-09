# etl/live_preview.py
"""8 preview Live Monitoring per scene (PIPELINE.md §4).

    Baris 1  s1_vv, s1_vh                      grayscale, tanpa overlay
    Baris 2  modis_flood, modis_ndvi, modis_ndwi   warna di atas S1 VH, 40%
    Baris 3  gpm_rain_24h, gpm_rain_72h, gpm_rain_7d

Memakai ulang mesin module10 (grid bersama S1, pembacaan turun, colormap dan
palet kelas PREVIEW_SPECS) supaya arti warna sama persis dengan colored
preview dataset biasa. Yang berbeda hanya komposisinya: dasar SELALU VH
(indikator genangan utama) dan opasitas 40% untuk SEMUA lapisan -- termasuk
peta banjir kategorikal, yang di module10 digambar opak. module10 sendiri
tidak diubah.

Berkas ditulis ke {root dataset}/live/{YYYYMMDD}/{key}.png -- satu folder per
scene, jadi retensi cukup menghapus foldernya (lihat live_monitor._LiveFiles).
Metrik TIDAK dihitung dari PNG ini (live_metrics membaca raster asli).
"""
from __future__ import annotations

import logging
import shutil
from datetime import date
from pathlib import Path

import numpy as np
import rasterio

from etl import admin_overlay
from etl import module10_generate_preview as m10

logger = logging.getLogger(__name__)

OVERLAY_OPACITY = 0.40
# Sisi terpanjang PNG kartu. Kartu menampilkan 3 gambar per baris, jadi 768 px
# sudah tajam di layar retina tanpa membuat halaman berat (~8 PNG per scene).
LIVE_MAX_SIDE = 768
LEGEND_STOPS = 6

_SPECS = {s.key: s for s in m10.PREVIEW_SPECS}
OVERLAY_KEYS = {
    "modis_flood": ("modis", "FLOOD"),
    "modis_ndvi": ("modis", "NDVI"),
    "modis_ndwi": ("modis", "NDWI"),
    "gpm_rain_24h": ("gpm", "24h"),
    "gpm_rain_72h": ("gpm", "72h"),
    "gpm_rain_7d": ("gpm", "7d"),
}

LABELS = {
    "s1_vv": "Sentinel-1 VV",
    "s1_vh": "Sentinel-1 VH",
    "modis_flood": "MODIS Flood Map",
    "modis_ndvi": "MODIS NDVI",
    "modis_ndwi": "MODIS Water Index (NDWI)",
    "gpm_rain_24h": "GPM Rain 24 h",
    "gpm_rain_72h": "GPM Rain 72 h",
    "gpm_rain_7d": "GPM Rain 7 days",
}


def _hex(rgba) -> str:
    r, g, b = (int(round(c * 255)) for c in rgba[:3])
    return f"#{r:02x}{g:02x}{b:02x}"


def _legend_continuous(spec, lo: float, hi: float) -> dict:
    from matplotlib import colormaps
    cmap = colormaps[spec.cmap]
    return {
        "type": "continuous",
        "min": round(float(lo), 3), "max": round(float(hi), 3),
        "units": spec.units,
        "stops": [_hex(cmap(t)) for t in np.linspace(0, 1, LEGEND_STOPS)],
        "opacity": OVERLAY_OPACITY,
    }


def _legend_categorical(spec) -> dict:
    return {
        "type": "categorical",
        "categories": [{"value": v, "color": c, "label": lbl} for v, c, _a, lbl in spec.categories],
        "opacity": OVERLAY_OPACITY,
    }


def _read_s1_db(path: Path, grid):
    """Band S1 di grid preview, dalam dB. sigma0 <= 0 (di luar swath) dijadikan
    NoData DULU: auto-deteksi module10 (_maybe_to_db) menganggap berkas yang
    memuat nol sudah dalam dB dan melewatkan konversinya."""
    layer = m10._read_downsampled(path, grid=grid)
    valid = layer.data[~layer.mask]
    if valid.size and np.median(valid) > 0:
        layer.mask = layer.mask | (layer.data <= 0)
        with np.errstate(divide="ignore", invalid="ignore"):
            db = 10.0 * np.log10(np.where(layer.mask, 1.0, layer.data))
        layer.data = np.maximum(db, m10.DB_FLOOR).astype(np.float32)
    return layer


def _gray_base(vh) -> np.ndarray:
    lo, hi = m10._stretch_range(vh, None)
    gray = (m10._normalize(vh, lo, hi) * 255).astype(np.float32)
    # NoData S1 putih, bukan hitam: hitam adalah nilai sah untuk air tenang.
    return np.where(vh.mask, 255.0, gray)


def _save(arr: np.ndarray, path: Path, mode: str) -> Path:
    from PIL import Image
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(arr, mode=mode).save(path, optimize=False,
                                         compress_level=m10.PNG_COMPRESS_LEVEL)
    return path


def _render_gray(layer, path: Path) -> tuple[Path, dict]:
    lo, hi = m10._stretch_range(layer, None)
    gray = (m10._normalize(layer, lo, hi) * 255).astype(np.uint8)
    alpha = np.where(layer.mask, 0, 255).astype(np.uint8)
    _save(np.dstack([gray, gray, gray, alpha]), path, "RGBA")
    return path, {"type": "grayscale", "min": round(lo, 1), "max": round(hi, 1),
                  "units": "dB", "stops": ["#000000", "#ffffff"]}


def _render_overlay(base_gray: np.ndarray, layer, spec, path: Path) -> tuple[Path, dict]:
    fg = m10._colored_rgba(layer, spec).astype(np.float32)
    alpha = fg[..., 3:4] / 255.0 * OVERLAY_OPACITY
    rgb = fg[..., :3] * alpha + base_gray[..., None] * (1.0 - alpha)
    _save(np.clip(rgb, 0, 255).astype(np.uint8), path, "RGB")
    if spec.categorical:
        return path, _legend_categorical(spec)
    lo, hi = m10._stretch_range(layer, spec)
    return path, _legend_continuous(spec, lo, hi)


def resolve_s1(frames: list[dict], scratch: Path, date_key: str) -> dict:
    """{band: path} Sentinel-1 untuk satu tanggal: frame tunggal apa adanya,
    atau mosaik kalau AOI tertutup beberapa frame hari itu.

    Dipisah supaya perender DAN backfill georeferensi memakai jalan yang sama.
    Kalau keduanya menghitung grid dengan caranya sendiri, suatu saat salah
    satu akan menyimpang dan citra tergeser tanpa ada yang menyadarinya."""
    if len(frames) > 1:
        from etl.s1_mosaic import mosaic_frames
        scratch.mkdir(parents=True, exist_ok=True)
        return mosaic_frames(frames, scratch, date_key=date_key, level="PROCESSED")
    return frames[0]


def grid_dict(grid) -> dict:
    """Georeferensi grid preview sebagai JSON untuk live_scenes.previews.grid.

    Empat sudut, bukan bbox -- lihat module10.grid_corners_wgs84. `width`/
    `height` ikut supaya konsumen bisa MEMERIKSA bahwa grid ini benar milik PNG
    yang ada di disk (dipakai scripts/backfill_preview_grid.py)."""
    return {
        "width": grid.width, "height": grid.height,
        "crs": str(grid.crs),
        "corners_wgs84": m10.grid_corners_wgs84(grid),
    }


def scene_grid(files, scene_date: date, inputs: dict):
    """Grid PNG preview satu scene, dihitung ulang dari raster sumber TANPA
    me-render apa pun. -> (grid, None) atau (None, alasan).

    Untuk mengisi georeferensi scene lama: jauh lebih murah daripada render
    ulang, karena cuma membaca metadata raster. Scene berbingkai banyak tetap
    perlu mosaiknya dibangun lagi -- grid mosaik bukan grid salah satu frame,
    jadi memakai frame pertama akan menghasilkan georeferensi yang salah."""
    frames = [{b: str(p) for b, p in f.items()} for f in inputs.get("s1") or []]
    if not frames:
        return None, "no Sentinel-1 data"
    dk = scene_date.strftime("%Y%m%d")
    # Nama scratch sengaja beda dari milik render_scene_previews: backfill bisa
    # berjalan sementara siklus lain me-render scene yang sama.
    scratch = files.root / "_work" / f"grid_{dk}"
    try:
        s1 = resolve_s1(frames, scratch, dk)
        if "VH" not in s1:
            return None, "VH band is missing"
        return m10._preview_grid(Path(s1["VH"]), LIVE_MAX_SIDE), None
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def render_scene_previews(files, scene_date: date, inputs: dict, regions=None,
                          bbox_wkt: str | None = None) -> dict:
    """Render 8 PNG untuk satu scene. `files` = live_monitor._LiveFiles,
    `inputs` = live_metrics.scene_inputs(). Lapisan yang berkasnya tidak ada
    dilewati (tercatat di "skipped"), bukan menggagalkan scene.

    `bbox_wkt` = AOI daerahnya. Kalau ada, SEMUA PNG dirender di grid tetap
    seluas AOI (etl.aoi_coverage.preview_grid): extent, ukuran, dan keempat
    sudutnya sama persis untuk setiap tanggal, jadi citra antar tanggal bisa
    ditumpuk dan tidak bergeser saat pengguna berpindah tanggal. Tanpa
    `bbox_wkt` grid diturunkan dari footprint S1 seperti dulu -- jalur itu
    masih dipakai pemanggil lama dan oleh scene yang AOI-nya tidak diketahui.

    `regions` = batas kecamatan (etl.admin_overlay.load_regions). Kalau ada,
    setiap PNG ditulis sekali lagi sebagai varian garis wilayah `{key}_adm.png`
    dan namanya dicatat di item sebagai "file_adm" -- itu yang dipakai UI saat
    checkbox "Garis wilayah" aktif."""
    out_dir = files.preview_dir(scene_date)
    out_dir.mkdir(parents=True, exist_ok=True)
    dk = scene_date.strftime("%Y%m%d")
    items: dict[str, dict] = {}
    skipped: dict[str, str] = {}
    # Georeferensi grid bersama. Satu entri per scene, bukan per lapisan:
    # semua PNG scene ini dirender di grid S1 yang sama (lihat "GRID BERSAMA"
    # di module10), jadi keempat sudutnya identik untuk kedelapan berkas.
    # Tetap None kalau S1 tidak ada -- tanpa S1 tidak ada PNG sama sekali.
    grid_info: dict | None = None

    frames = [{b: str(p) for b, p in f.items()} for f in inputs.get("s1") or []]
    if not frames:
        return {"dir": str(out_dir), "items": {}, "skipped": {"s1": "no Sentinel-1 data"}}

    scratch = files.root / "_work" / f"live_{dk}"
    try:
        s1 = resolve_s1(frames, scratch, dk)
        if "VH" not in s1:
            return {"dir": str(out_dir), "items": {}, "skipped": {"s1": "VH band is missing"}}

        if bbox_wkt:
            from etl.aoi_coverage import preview_grid
            with rasterio.open(s1["VH"]) as src:
                scene_crs = src.crs
            grid = preview_grid(bbox_wkt, scene_crs, LIVE_MAX_SIDE)
        else:
            grid = m10._preview_grid(Path(s1["VH"]), LIVE_MAX_SIDE)
        grid_info = grid_dict(grid)
        vh = _read_s1_db(Path(s1["VH"]), grid)
        base = _gray_base(vh)

        for key, band in (("s1_vv", "VV"), ("s1_vh", "VH")):
            if band not in s1:
                skipped[key] = f"{band} band is missing"
                continue
            layer = vh if band == "VH" else _read_s1_db(Path(s1[band]), grid)
            p, legend = _render_gray(layer, out_dir / f"{key}.png")
            items[key] = {"file": p.name, "label": LABELS[key], "legend": legend,
                          "file_adm": admin_overlay.write_variant(p, grid.transform, grid.crs, regions)}

        for key, (source, band) in OVERLAY_KEYS.items():
            found = (inputs.get(source) or {}).get(band)
            if not found:
                skipped[key] = "source file is missing"
                continue
            spec = _SPECS[key]
            try:
                layer = m10._read_downsampled(found[0], grid=grid, categorical=spec.categorical)
                p, legend = _render_overlay(base, layer, spec, out_dir / f"{key}.png")
                items[key] = {"file": p.name, "label": LABELS[key], "legend": legend,
                              "source_date": found[1].isoformat(),
                              "file_adm": admin_overlay.write_variant(p, grid.transform, grid.crs, regions)}
            except Exception as exc:
                logger.exception("[LIVE] preview %s %s gagal", key, scene_date)
                skipped[key] = f"render failed: {exc}"
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    return {"dir": str(out_dir), "items": items, "skipped": skipped,
            "grid": grid_info}
