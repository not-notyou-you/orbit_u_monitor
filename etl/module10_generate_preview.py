"""Tier PREVIEW: render PNG siap-pandang dari produk satu tanggal akuisisi."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date as date_type, datetime, timezone
from pathlib import Path

import numpy as np
import rasterio
from affine import Affine
from rasterio.enums import Resampling
from rasterio.warp import reproject, transform as warp_transform

from etl import admin_overlay
from etl import folder_manager as fm
from etl import module7_modis_download as m7
from etl import module8_gpm_download as m8

logger = logging.getLogger(__name__)

MODULE = "MODULE10_PREVIEW"

MAX_SIDE = 1024


PCT_LOW = 2.0
PCT_HIGH = 98.0

OVERLAY_OPACITY = 0.55

PNG_COMPRESS_LEVEL = 6


@dataclass(frozen=True)
class PreviewSpec:
    """Satu lapisan yang dirender. `key` sekaligus jadi nama berkas PNG-nya
    (`{key}.png`) di kedua subfolder, supaya grayscale dan colored bisa
    dipasangkan di UI tanpa tabel pemetaan terpisah."""

    key: str
    source: str  # sentinel1 | modis | gpm
    band: str  # band_name seperti di data_products
    label: str
    units: str
    cmap: str
    scale: str
    vmin: float | None = None
    vmax: float | None = None
    transparent_below: float | None = None
    log_db: bool = False
    interpretation: str = ""
    categories: tuple[tuple[int, str, int, str], ...] = ()

    @property
    def categorical(self) -> bool:
        return self.scale == "categorical"


PREVIEW_SPECS: tuple[PreviewSpec, ...] = (
    PreviewSpec(
        key="s1_vv",
        source="sentinel1",
        band="VV",
        label="Sentinel-1 VV",
        units="dB",
        cmap="viridis",
        scale="percentile",
        log_db=True,
        interpretation=(
            "Co-polarised backscatter. Dark = smooth surfaces that reflect "
            "the signal away from the sensor (calm water, asphalt roads, "
            "flooded rice fields); bright = rough surfaces or buildings."
        ),
    ),
    PreviewSpec(
        key="s1_vh",
        source="sentinel1",
        band="VH",
        label="Sentinel-1 VH",
        units="dB",
        cmap="viridis",
        scale="percentile",
        log_db=True,
        interpretation=(
            "Cross-polarised backscatter, dominated by volume scattering. "
            "More sensitive to vegetation and tree stands than VV, and the "
            "water-vs-land contrast is usually sharper."
        ),
    ),
    PreviewSpec(
        key="modis_flood",
        source="modis",
        band="FLOOD",
        label="MODIS Flood 2-day (MCDWD)",
        units="class",
        cmap="categorical",
        scale="categorical",
        vmin=0.0,
        vmax=3.0,
        categories=(
            (0, "#bdbdbd", 110, "No water"),
            (1, "#2171b5", 255, "Permanent water (reference)"),
            (2, "#fd8d3c", 255, "Seasonal flood (recurrent)"),
            (3, "#e31a1c", 255, "Flood (unusual)"),
        ),
        interpretation=(
            "MODIS MCDWD 2-day composite flood map (Terra+Aqua, 250 m). Blue = "
            "permanent water, orange = seasonal flood, red = unusual flood, "
            "grey = observed with no water. Transparent = insufficient data "
            "(usually cloud-covered)."
        ),
    ),
    PreviewSpec(
        key="modis_ndvi",
        source="modis",
        band="NDVI",
        label="MODIS NDVI",
        units="index",
        cmap="RdYlGn",
        scale="fixed",
        vmin=-0.2,
        vmax=0.8,
        interpretation=(
            "Normalized Difference Vegetation Index (8-day MOD09A1 composite, "
            "clouds removed). Red (<0) = water or built-up land; yellow "
            "(~0.3) = sparse vegetation; green (>0.6) = dense canopy. The scale "
            "is fixed at -0.2..0.8 so colours can be compared across dates. "
            "Transparent = cloud."
        ),
    ),
    PreviewSpec(
        key="modis_ndwi",
        source="modis",
        band="NDWI",
        label="MODIS NDWI",
        units="index",
        cmap="BrBG",
        scale="fixed",
        vmin=-0.5,
        vmax=0.5,
        interpretation=(
            "Normalized Difference Water Index (McFeeters formulation: "
            "green/NIR). Brown (<0) = dry land; blue-green (>0) = "
            "open water. The flooding threshold is usually taken around 0. "
            "Transparent = cloud."
        ),
    ),
    PreviewSpec(
        key="gpm_rain_24h",
        source="gpm",
        band="RAIN_24H",
        label="GPM Rainfall 24 h",
        units="mm",
        cmap="YlGnBu",
        scale="zero_based",
        transparent_below=0.1,
        interpretation=(
            "Rainfall over the UTC calendar day of the acquisition date "
            "(daily IMERG, 0.1-degree cells ~11 km). A direct trigger of "
            "flash floods. Pixels <0.1 mm are made transparent so dry areas "
            "are not read as 'very little rain'."
        ),
    ),
    PreviewSpec(
        key="gpm_rain_72h",
        source="gpm",
        band="RAIN_72H",
        label="GPM Rainfall 72 h",
        units="mm",
        cmap="YlGnBu",
        scale="zero_based",
        transparent_below=0.1,
        interpretation=(
            "3-day accumulation. Captures the successive rainfall that "
            "saturates the soil before the peak event."
        ),
    ),
    PreviewSpec(
        key="gpm_rain_7d",
        source="gpm",
        band="RAIN_7D",
        label="GPM Rainfall 7 days",
        units="mm",
        cmap="YlGnBu",
        scale="zero_based",
        transparent_below=0.1,
        interpretation=(
            "1-week accumulation. A proxy for antecedent moisture — the same "
            "rainfall produces far more widespread flooding on saturated soil."
        ),
    ),
)

S1_RGB_KEY = "s1_rgb_composite"
S1_RGB_LABEL = "Sentinel-1 RGB Composite (VV / VH / VV-VH)"
S1_RGB_INTERPRETATION = (
    "False color: R = VV, G = VH, B = VV-VH difference (dB). Open water turns "
    "dark/bluish (both VV and VH low), vegetated land turns "
    "greenish (VH relatively high), built-up areas turn pink to "
    "white (VV very high). Useful for separating flooding from topographic "
    "shadow, which look equally dark in a single-band image."
)


_TIER_BY_LEVEL: dict[str, str] = {"PROCESSED": "cog", "RAW": "aligned"}
_S1_SUFFIX_BY_LEVEL: dict[str, str] = {"PROCESSED": "_lee", "RAW": "_crop"}


def tier_for_level(processing_level: str | None) -> str:
    """Tier on-disk yang dirender untuk level ini: PROCESSED -> gold,
    RAW -> bronze (DOCS/PIPELINE.md, "Preview Stage")."""
    return _TIER_BY_LEVEL[fm.normalize_preview_level(processing_level)]


def _s1_source_path(
    dataset_id: int, dataset_name: str, s1_scene_key: str | None, band: str,
    processing_level: str,
) -> Path | None:
    """Cari raster Sentinel-1 satu band di tier yang sesuai level. Nama
    berkasnya tidak punya fungsi penamaan terpusat seperti MODIS/GPM (module4
    memakai `silver_path.name` apa adanya), jadi band-nya dicocokkan lewat
    sufiks yang ditulis tahap terakhir level itu: `_{BAND}_lee.tif` untuk
    PROCESSED, `_{BAND}_crop.tif` untuk RAW."""
    if not s1_scene_key:
        return None
    level = fm.normalize_preview_level(processing_level)
    scene_dir = fm.get_scene_dir(
        dataset_id, dataset_name, _TIER_BY_LEVEL[level], "sentinel1", s1_scene_key
    )
    if not scene_dir.is_dir():
        return None
    matches = sorted(
        scene_dir.glob(f"*_{band.upper()}{_S1_SUFFIX_BY_LEVEL[level]}.tif")
    )
    if not matches:
        matches = sorted(p for p in scene_dir.glob("*.tif") if f"_{band.upper()}" in p.name)
    return matches[0] if matches else None


def _aux_source_path(
    dataset_id: int, dataset_name: str, source: str, band: str, date_key: str,
    processing_level: str,
) -> Path | None:
    """Cari raster MODIS/GPM satu band untuk satu tanggal di tier level ini."""
    if source == "modis":
        filename = m7.band_filename(band, date_key)
    elif source == "gpm":
        filename = m8.band_filename(band.removeprefix("RAIN_").lower(), date_key)
    else:  # pragma: no cover - dijaga PREVIEW_SPECS
        raise ValueError(f"unknown aux source: {source!r}")
    tier = tier_for_level(processing_level)
    path = fm.get_scene_dir(dataset_id, dataset_name, tier, source, date_key) / filename
    return path if path.exists() else None


def resolve_source_inputs(
    dataset_id: int,
    dataset_name: str,
    date_key: str,
    s1_scene_key: str | None = None,
    s1_files: dict[str, str] | None = None,
    processing_level: str = fm.DEFAULT_PREVIEW_LEVEL,
) -> dict[str, Path]:
    """Petakan `PreviewSpec.key` -> path raster yang ada di disk, di tier yang sesuai `processing_level`."""
    level = fm.normalize_preview_level(processing_level)
    inputs: dict[str, Path] = {}
    for spec in PREVIEW_SPECS:
        if spec.source == "sentinel1":
            path: Path | None = None
            if s1_files and s1_files.get(spec.band):
                candidate = Path(s1_files[spec.band])
                path = candidate if candidate.exists() else None
            if path is None:
                path = _s1_source_path(
                    dataset_id, dataset_name, s1_scene_key, spec.band, level
                )
        else:
            path = _aux_source_path(
                dataset_id, dataset_name, spec.source, spec.band, date_key, level
            )
        if path is not None:
            inputs[spec.key] = path
    return inputs


def resolve_gold_inputs(
    dataset_id: int,
    dataset_name: str,
    date_key: str,
    s1_scene_key: str | None = None,
    s1_gold_files: dict[str, str] | None = None,
) -> dict[str, Path]:
    """Alias lama `resolve_source_inputs` untuk level PROCESSED (tier GOLD)."""
    return resolve_source_inputs(
        dataset_id, dataset_name, date_key,
        s1_scene_key=s1_scene_key, s1_files=s1_gold_files,
        processing_level="PROCESSED",
    )


@dataclass
class _Layer:
    """Satu raster yang sudah dibaca-turun dan dimask."""

    data: np.ndarray  # float32, nilai di piksel mask tidak berarti
    mask: np.ndarray  # True = NoData
    height: int
    width: int
    src_height: int
    src_width: int
    stats: dict = field(default_factory=dict)

    @property
    def valid(self) -> np.ndarray:
        return self.data[~self.mask]


DB_FLOOR = -40.0


def _maybe_to_db(data: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, bool]:
    """Konversi sigma0 linear -> desibel, kalau datanya memang masih linear."""
    valid = data[~mask]
    if valid.size == 0:
        return data, False
    if valid.min() <= 0 or np.percentile(valid, PCT_HIGH) <= 0:
        return data, False  # sudah dB
    with np.errstate(divide="ignore", invalid="ignore"):
        db = 10.0 * np.log10(np.where(mask, 1.0, data))
    return np.maximum(db, DB_FLOOR).astype(np.float32), True


@dataclass(frozen=True)
class _PreviewGrid:
    """Grid PNG bersama (biasanya grid preview Sentinel-1)."""

    transform: Affine
    crs: object
    width: int
    height: int


def _preview_shape(width: int, height: int, max_side: int) -> tuple[int, int]:
    """(out_w, out_h) PNG untuk raster `width` x `height`."""
    longest = max(width, height)
    if longest > max_side:
        scale = max_side / longest
        return max(1, int(round(width * scale))), max(1, int(round(height * scale)))
    factor = max(1, max_side // longest)
    return width * factor, height * factor


def _preview_grid(path: Path, max_side: int = MAX_SIDE) -> _PreviewGrid:
    """Grid PNG untuk raster `path` — dipakai sebagai grid bersama semua
    lapisan satu tanggal kalau `path` adalah Sentinel-1."""
    with rasterio.open(path) as src:
        out_w, out_h = _preview_shape(src.width, src.height, max_side)
        transform = src.transform * Affine.scale(src.width / out_w, src.height / out_h)
        return _PreviewGrid(transform, src.crs, out_w, out_h)


def grid_corners_wgs84(grid: _PreviewGrid) -> list[list[float]]:
    """Empat sudut PNG grid `grid` dalam lon/lat WGS84, urut kiri-atas →
    kanan-atas → kanan-bawah → kiri-bawah.
    """
    t = grid.transform
    cols = (0, grid.width, grid.width, 0)
    rows = (0, 0, grid.height, grid.height)
    xy = [t * (c, r) for c, r in zip(cols, rows)]
    lon, lat = warp_transform(grid.crs, "EPSG:4326",
                              [p[0] for p in xy], [p[1] for p in xy])
    return [[round(x, 7), round(y, 7)] for x, y in zip(lon, lat)]


def _read_downsampled(
    path: Path,
    max_side: int = MAX_SIDE,
    log_db: bool = False,
    grid: _PreviewGrid | None = None,
    categorical: bool = False,
) -> _Layer:
    """Baca band 1 ke ukuran preview."""
    with rasterio.open(path) as src:
        nodata = src.nodata
        src_h, src_w = src.height, src.width
        if grid is not None:
            out_w, out_h = grid.width, grid.height
            coarser = abs(src.transform.a) >= abs(grid.transform.a)
            resampling = (
                Resampling.nearest if categorical or coarser else Resampling.average
            )
            data = np.full((out_h, out_w), np.nan, dtype=np.float32)
            reproject(
                source=rasterio.band(src, 1),
                destination=data,
                src_transform=src.transform,
                src_crs=src.crs,
                src_nodata=nodata,
                dst_transform=grid.transform,
                dst_crs=grid.crs,
                dst_nodata=np.nan,
                resampling=resampling,
            )
        else:
            out_w, out_h = _preview_shape(src.width, src.height, max_side)
            upsample = out_w >= src.width
            resampling = (
                Resampling.nearest if categorical or upsample else Resampling.average
            )
            data = src.read(1, out_shape=(out_h, out_w), resampling=resampling).astype(
                np.float32
            )

    mask = ~np.isfinite(data)
    if nodata is not None and np.isfinite(nodata):
        mask |= np.isclose(data, float(nodata))

    converted = False
    if log_db:
        data, converted = _maybe_to_db(data, mask)

    layer = _Layer(
        data=data, mask=mask, height=out_h, width=out_w,
        src_height=src_h, src_width=src_w,
    )
    valid = layer.valid
    layer.stats = {
        "nodata_percent": round(float(mask.mean()) * 100, 2),
        "min": round(float(valid.min()), 4) if valid.size else None,
        "max": round(float(valid.max()), 4) if valid.size else None,
        "mean": round(float(valid.mean()), 4) if valid.size else None,
        "converted_to_db": converted,
    }
    return layer


def _stretch_range(layer: _Layer, spec: PreviewSpec | None) -> tuple[float, float]:
    """Rentang (lo, hi) yang dipakai memetakan nilai ke 0..1."""
    valid = layer.valid
    if valid.size == 0:
        return 0.0, 1.0

    if spec is not None and spec.scale in ("fixed", "categorical"):
        return float(spec.vmin), float(spec.vmax)

    if spec is not None and spec.scale == "zero_based":
        hi = float(np.percentile(valid, PCT_HIGH))
        if hi <= 0:
            hi = float(valid.max())
        return 0.0, hi if hi > 0 else 1.0

    lo = float(np.percentile(valid, PCT_LOW))
    hi = float(np.percentile(valid, PCT_HIGH))
    if hi <= lo:
        hi = lo + 1.0
    return lo, hi


def _normalize(layer: _Layer, lo: float, hi: float) -> np.ndarray:
    """Nilai -> 0..1, dijepit. Piksel NoData diisi 0 (tidak dipakai: alpha-nya
    nol) supaya tidak ada NaN yang bocor ke colormap."""
    span = hi - lo if hi > lo else 1.0
    norm = (layer.data - lo) / span
    norm = np.clip(norm, 0.0, 1.0)
    return np.where(layer.mask, 0.0, norm)


def _alpha(layer: _Layer, spec: PreviewSpec | None = None) -> np.ndarray:
    """Kanal alpha uint8: 0 di NoData, dan 0 juga di bawah
    `transparent_below` kalau spec memintanya."""
    opaque = ~layer.mask
    if spec is not None and spec.transparent_below is not None:
        opaque &= layer.data >= spec.transparent_below
    return (opaque * 255).astype(np.uint8)


def _save_png(img, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="PNG", optimize=True, compress_level=PNG_COMPRESS_LEVEL)
    return path


def _gray_range(layer: _Layer, spec: PreviewSpec | None) -> tuple[float, float]:
    """Rentang grayscale: persentil per berkas, kecuali data kategorikal —
    persentil kelas diskret (mis. 98% piksel bernilai 1) menjepit kelas
    lain ke putih/hitam, jadi kelas dipetakan ke vmin..vmax tetap."""
    if spec is not None and spec.categorical:
        return _stretch_range(layer, spec)
    return _stretch_range(layer, None)


def _render_grayscale(layer: _Layer, out_path: Path, spec: PreviewSpec | None = None) -> Path:
    """PNG mode LA: satu kanal luminansi (nilai ilmiah) + satu kanal alpha
    (masker NoData). Tetap 'satu kanal data' seperti yang dimaksud tier ini —
    alpha bukan data, dia cuma memisahkan 'gelap' dari 'tidak ada'."""
    from PIL import Image

    lo, hi = _gray_range(layer, spec)
    gray = (_normalize(layer, lo, hi) * 255).astype(np.uint8)
    img = Image.fromarray(np.dstack([gray, _alpha(layer)]), mode="LA")
    return _save_png(img, out_path)


def _colored_rgba(layer: _Layer, spec: PreviewSpec) -> np.ndarray:
    """Array RGBA uint8 untuk render colored."""
    from matplotlib import colormaps
    from matplotlib.colors import to_rgb

    if spec.categorical:
        rgba = np.zeros((layer.height, layer.width, 4), dtype=np.uint8)
        values = np.where(layer.mask, -1, np.rint(layer.data)).astype(np.int32)
        for value, color, alpha, _label in spec.categories:
            hit = values == value
            rgba[hit, :3] = [int(round(c * 255)) for c in to_rgb(color)]
            rgba[hit, 3] = alpha
        return rgba

    lo, hi = _stretch_range(layer, spec)
    rgba = (colormaps[spec.cmap](_normalize(layer, lo, hi)) * 255).astype(np.uint8)
    rgba[..., 3] = _alpha(layer, spec)
    return rgba


def _render_colored(layer: _Layer, spec: PreviewSpec, out_path: Path) -> Path:
    """PNG RGBA hasil colormap matplotlib (atau palet kelas)."""
    from PIL import Image

    img = Image.fromarray(_colored_rgba(layer, spec), mode="RGBA")
    return _save_png(img, out_path)


def _class_percentages(layer: _Layer, spec: PreviewSpec) -> dict[str, float]:
    """Persentase piksel preview per kelas (dari seluruh piksel, termasuk
    NoData) — ringkasan yang lebih berguna daripada min/max/mean kelas."""
    total = layer.data.size or 1
    values = np.where(layer.mask, -1, np.rint(layer.data)).astype(np.int32)
    out = {
        label: round(float((values == value).sum()) / total * 100, 2)
        for value, _color, _alpha, label in spec.categories
    }
    out["No data"] = round(float(layer.mask.sum()) / total * 100, 2)
    return out


def _render_s1_rgb(vv: _Layer, vh: _Layer, out_path: Path) -> Path | None:
    """Komposit false-color VV/VH/(VV-VH)."""
    from PIL import Image

    if vv.data.shape != vh.data.shape:
        logger.warning(
            "[M10] komposit RGB dilewati: dimensi VV %s != VH %s",
            vv.data.shape, vh.data.shape,
        )
        return None

    diff = _Layer(
        data=vv.data - vh.data,
        mask=vv.mask | vh.mask,
        height=vv.height, width=vv.width,
        src_height=vv.src_height, src_width=vv.src_width,
    )

    channels = []
    for lyr in (vv, vh, diff):
        lo, hi = _stretch_range(lyr, None)
        channels.append((_normalize(lyr, lo, hi) * 255).astype(np.uint8))

    alpha = ((~(vv.mask | vh.mask)) * 255).astype(np.uint8)
    img = Image.fromarray(np.dstack(channels + [alpha]), mode="RGBA")
    return _save_png(img, out_path)


def overlay_filename(spec_key: str) -> str:
    return f"{spec_key}_on_s1.png"


def _render_overlay_on_s1(
    base: _Layer, layer: _Layer, spec: PreviewSpec, out_path: Path
) -> Path | None:
    """Lapisan MODIS/GPM (berwarna, transparan di NoData) ditumpuk di atas
    citra Sentinel-1 grayscale sebagai peta dasar. Kedua array sudah berada di
    grid yang sama (lihat "GRID BERSAMA"), jadi tinggal alpha-compositing."""
    from PIL import Image

    if base.data.shape != layer.data.shape:
        logger.warning(
            "[M10] overlay %s dilewati: dimensi dasar %s != lapisan %s",
            spec.key, base.data.shape, layer.data.shape,
        )
        return None

    lo, hi = _stretch_range(base, None)
    gray = (_normalize(base, lo, hi) * 255).astype(np.float32)
    gray = np.where(base.mask, 255.0, gray)

    fg = _colored_rgba(layer, spec).astype(np.float32)
    alpha = fg[..., 3:4] / 255.0
    if not spec.categorical:
        alpha = alpha * OVERLAY_OPACITY
    rgb = fg[..., :3] * alpha + gray[..., None] * (1.0 - alpha)
    img = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), mode="RGB")
    return _save_png(img, out_path)


def _write_json(path: Path, payload: dict) -> Path:
    """Tulis JSON secara atomik (tmp lalu replace), pola yang sama dengan
    `folder_manager.write_dataset_metadata` — sidecar yang setengah tertulis
    saat proses dihentikan akan membuat UI gagal parse."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    tmp.replace(path)
    return path


def _grayscale_info(entries: list[dict]) -> dict:
    return {
        "kind": "grayscale",
        "purpose": "Scientific representation — reading relative values per file.",
        "colormap": "gray (linear, no hue)",
        "image_mode": "LA (luminansi 8-bit + alpha)",
        "stretch": {
            "method": "percentile",
            "percentile_low": PCT_LOW,
            "percentile_high": PCT_HIGH,
            "per_file": True,
            "note": (
                "The range is recomputed from the valid pixels of each file, so "
                "contrast is maximal for that file — but grey levels "
                "are NOT comparable across dates or bands. "
                "For comparison over time use the colored/ folder, whose "
                "scale is fixed."
            ),
        },
        "pre_transform": (
            "Sentinel-1 bands are converted to decibels (10*log10) before "
            "stretching: GOLD stores linear sigma0, whose distribution has an "
            "extreme tail, and a percentile stretch applied directly to it "
            "produces an unreadably dark image. MODIS and GPM are rendered "
            "as-is. Each image's 'transform' field records which ones "
            "were converted."
        ),
        "nodata": "Transparent (alpha=0). Not mapped to black because black is a valid value for low backscatter / water.",
        "interpretation": (
            "Dark = low values within this file's percentile range; bright = "
            "high values. For SAR, dark is usually a smooth surface (water, "
            "asphalt); bright is usually a rough surface or buildings."
        ),
        "images": entries,
    }


_OPTION_TO_KIND: dict[str, str] = {
    "GRAYSCALE": "grayscale",
    "COLORED": "colored",
    "COMPOSITE": "composite",
}


def _normalize_options(options) -> set[str]:
    """Ubah datasets.preview_options jadi himpunan nama folder render."""
    if options is None:
        return set(_OPTION_TO_KIND.values())
    out: set[str] = set()
    for raw in options:
        kind = _OPTION_TO_KIND.get(str(raw).strip().upper())
        if kind is None:
            logger.warning("[M10] opsi preview tidak dikenal diabaikan: %r", raw)
            continue
        out.add(kind)
    return out


def _composite_info(entries: list[dict]) -> dict:
    """Sidecar composite/. Skemanya sengaja beda dari colored_info: komposit
    tidak punya colormap maupun rentang nilai tunggal — yang perlu dijelaskan
    adalah pemetaan kanal ke besaran."""
    return {
        "kind": "composite",
        "count": len(entries),
        "description": (
            "False-color RGB composite of several bands at once. Colour here "
            "expresses the relationship between bands, not the value of a "
            "single quantity, so no colorbar can be attached to it. The "
            "*_on_s1.png files are an exception: coloured MODIS/GPM layers "
            "(see 'legend'/colored/) are stacked over the grayscale "
            "Sentinel-1 image as a base map."
        ),
        "not_for": "Quantitative analysis — use gold/*.tif or fusion/*.h5.",
        "images": entries,
    }


def _colored_info(entries: list[dict]) -> dict:
    return {
        "kind": "colored",
        "purpose": "Publication and presentation — colours that can be read across dates.",
        "image_mode": "RGBA (8-bit per kanal)",
        "colormap_strategy": {
            "sentinel1": (
                "viridis, perceptually uniform sequential. Backscatter is an "
                "ordered quantity, so a diverging colormap would invent a "
                "midpoint with no physical meaning. Plus one false-color "
                "RGB composite (VV/VH/VV-VH)."
            ),
            "modis": (
                "FLOOD: class palette (grey = no water, blue = permanent "
                "water, orange = seasonal flood, red = unusual flood, "
                "transparent = insufficient data); see each entry's 'legend'. "
                "NDVI RdYlGn is fixed at -0.2..0.8 (red = water/built-up land, "
                "green = vegetation); NDWI BrBG is fixed at -0.5..0.5 with zero "
                "in the middle (brown = dry, blue-green = water). Clouds are transparent."
            ),
            "gpm": (
                "YlGnBu sequential starting at zero, with the upper bound at the "
                "98th percentile per file. Zero is a true zero (not the data "
                "minimum), and pixels below 0.1 mm are made transparent so dry "
                "areas are not read as light rain."
            ),
        },
        "nodata": "Transparent (alpha=0), same as grayscale/.",
        "grid": (
            "When Sentinel-1 is present, MODIS/GPM are reprojected onto the S1 "
            "preview grid (nearest-neighbour; see 'aligned_to') so all PNGs "
            "of one date have the same size and can be stacked. MODIS 250/500 m "
            "pixels and GPM 0.1-degree cells appear as blocks."
        ),
        "ideal_use_cases": [
            "Figures for reports, posters, and presentations",
            "Comparing conditions across dates (fixed scale for MODIS)",
            "Quick overlays on a base map — the transparent background fits right in",
        ],
        "caveat": (
            "Colours are quantised to 8-bit and part of the range is "
            "clipped. For quantitative analysis use the COG in gold/ or the "
            "HDF5 in fusion/, not this PNG."
        ),
        "images": entries,
    }


def _previous_s1_scene_key(metadata_path: Path, date_key: str) -> str | None:
    """s1_scene_key dari sidecar render sebelumnya, HANYA kalau sidecar itu
    menggambarkan tanggal yang sama.
    """
    try:
        with open(metadata_path, encoding="utf-8") as f:
            payload = json.load(f)
        if payload.get("acquisition_date") != date_key:
            return None
        value = payload.get("s1_scene_key")
    except (OSError, ValueError, AttributeError):
        return None
    return value if isinstance(value, str) and value else None


def generate_previews(
    dataset_id: int,
    dataset_name: str,
    acquisition_date: date_type | datetime | str,
    s1_scene_key: str | None = None,
    s1_gold_files: dict[str, str] | None = None,
    max_side: int = MAX_SIDE,
    overwrite: bool = True,
    processing_level: str = fm.DEFAULT_PREVIEW_LEVEL,
    s1_files: dict[str, str] | None = None,
    options: tuple[str, ...] | list[str] | None = None,
    max_width: int | None = None,
) -> dict:
    """Render seluruh preview untuk satu tanggal akuisisi pada SATU level pemrosesan."""
    if max_width is not None:
        max_side = max_width
    level = fm.normalize_preview_level(processing_level)
    tier = tier_for_level(level)
    wanted = _normalize_options(options)
    date_key = fm.date_key(acquisition_date)
    preview_dir = fm.ensure_preview_dir(dataset_id, dataset_name, date_key)
    level_dir = fm.get_preview_level_dir(dataset_id, dataset_name, date_key, level)

    replaced_scene_key = _previous_s1_scene_key(
        level_dir / fm.dated_filename(date_key, "preview_metadata.json"), date_key
    )
    if replaced_scene_key == s1_scene_key or not s1_scene_key:
        replaced_scene_key = None
    if replaced_scene_key:
        logger.warning(
            "[M10] PREVIEW %s level=%s: scene %s menimpa preview scene %s "
            "(nama berkas PNG hanya berprefiks tanggal, bukan scene)",
            date_key, level, s1_scene_key, replaced_scene_key,
        )

    def _kind_dir(kind: str) -> Path | None:
        if kind not in wanted:
            return None
        return fm.ensure_preview_kind_dir(
            dataset_id, dataset_name, date_key, kind, level
        )

    gray_dir = _kind_dir("grayscale")
    color_dir = _kind_dir("colored")
    composite_dir = _kind_dir("composite")

    inputs = resolve_source_inputs(
        dataset_id, dataset_name, date_key,
        s1_scene_key=s1_scene_key,
        s1_files=s1_files or s1_gold_files,
        processing_level=level,
    )

    regions = admin_overlay.load_regions()

    def _adm_variant(path: Path, entry: dict) -> None:
        """Tulis {stem}_adm.png dan catat namanya di `entry["file_adm"]`."""
        if not regions or grid is None:
            return
        if (entry.get("width"), entry.get("height")) != (grid.width, grid.height):
            return   # PNG di grid lain: batas wilayah akan meleset dari piksel
        name = admin_overlay.write_variant(path, grid.transform, grid.crs, regions)
        if name:
            entry["file_adm"] = name

    gray_entries: list[dict] = []
    color_entries: list[dict] = []
    written: list[Path] = []
    skipped: list[dict] = []
    layers: dict[str, _Layer] = {}

    grid: _PreviewGrid | None = None
    grid_source: str | None = None
    for s1_key in ("s1_vv", "s1_vh"):
        if s1_key in inputs:
            try:
                grid = _preview_grid(inputs[s1_key], max_side=max_side)
                grid_source = s1_key
            except Exception:
                logger.exception("[M10] gagal baca grid %s, lapisan aux tanpa grid bersama", s1_key)
            break

    for spec in PREVIEW_SPECS:
        src_path = inputs.get(spec.key)
        if src_path is None:
            skipped.append({
                "key": spec.key,
                "source": spec.source,
                "band": spec.band,
                "reason": "GOLD file is not on disk",
            })
            continue

        png_name = fm.dated_filename(date_key, f"{spec.key}.png")
        gray_path = gray_dir / png_name if gray_dir else None
        color_path = color_dir / png_name if color_dir else None
        wanted_paths = [p for p in (gray_path, color_path) if p is not None]
        if not overwrite and wanted_paths and all(p.exists() for p in wanted_paths):
            skipped.append({
                "key": spec.key, "source": spec.source, "band": spec.band,
                "reason": "already exists (overwrite=False)",
            })
            continue

        try:
            layer = _read_downsampled(
                src_path, max_side=max_side, log_db=spec.log_db,
                grid=grid if spec.source != "sentinel1" else None,
                categorical=spec.categorical,
            )
        except Exception as exc:
            logger.exception("[M10] gagal baca %s untuk %s", src_path, spec.key)
            skipped.append({
                "key": spec.key, "source": spec.source, "band": spec.band,
                "reason": f"failed to read: {exc}",
            })
            continue

        if layer.valid.size == 0:
            skipped.append({
                "key": spec.key, "source": spec.source, "band": spec.band,
                "reason": "all pixels are NoData",
            })
            continue

        layers[spec.key] = layer

        common = {
            "key": spec.key,
            "source": spec.source,
            "band": spec.band,
            "label": spec.label,
            "units": spec.units,
            "source_file": str(src_path),
            "width": layer.width,
            "height": layer.height,
            "source_width": layer.src_width,
            "source_height": layer.src_height,
            "statistics": layer.stats,
            "transform": "10*log10(sigma0)" if layer.stats.get("converted_to_db") else "none",
            "aligned_to": grid_source if spec.source != "sentinel1" and grid is not None else None,
        }
        if spec.categorical:
            common["statistics"] = {**layer.stats, "class_percent": _class_percentages(layer, spec)}

        try:
            if gray_path is not None:
                _render_grayscale(layer, gray_path, spec)
                g_lo, g_hi = _gray_range(layer, spec)
                gray_entry = {
                    **common,
                    "file": gray_path.name,
                    "colormap": "gray",
                    "value_range": [round(g_lo, 4), round(g_hi, 4)],
                    "range_method": (
                        "fixed classes" if spec.categorical
                        else f"percentile {PCT_LOW}-{PCT_HIGH}"
                    ),
                    "size_bytes": gray_path.stat().st_size,
                }
                _adm_variant(gray_path, gray_entry)
                gray_entries.append(gray_entry)
                written.append(gray_path)

            if color_path is not None:
                _render_colored(layer, spec, color_path)
                c_lo, c_hi = _stretch_range(layer, spec)
                entry = {
                    **common,
                    "file": color_path.name,
                    "colormap": spec.cmap,
                    "value_range": [round(c_lo, 4), round(c_hi, 4)],
                    "range_method": spec.scale,
                    "transparent_below": spec.transparent_below,
                    "interpretation": spec.interpretation,
                    "size_bytes": color_path.stat().st_size,
                }
                if spec.categorical:
                    entry["legend"] = [
                        {"value": v, "color": c, "alpha": a, "label": lbl}
                        for v, c, a, lbl in spec.categories
                    ]
                if not _colored_rgba(layer, spec)[..., 3].any():
                    entry["all_transparent"] = True
                    entry["note"] = (
                        f"All pixels are below {spec.transparent_below} {spec.units} "
                        "(no rain)" if spec.transparent_below is not None
                        else "No class can be displayed"
                    )
                _adm_variant(color_path, entry)
                color_entries.append(entry)
                written.append(color_path)
        except Exception as exc:
            logger.exception("[M10] gagal render %s", spec.key)
            skipped.append({
                "key": spec.key, "source": spec.source, "band": spec.band,
                "reason": f"render failed: {exc}",
            })

    composite_entries: list[dict] = []
    if composite_dir is not None and "s1_vv" in layers and "s1_vh" in layers:
        rgb_path = composite_dir / fm.dated_filename(date_key, f"{S1_RGB_KEY}.png")
        try:
            if _render_s1_rgb(layers["s1_vv"], layers["s1_vh"], rgb_path) is not None:
                rgb_entry = {
                    "key": S1_RGB_KEY,
                    "source": "sentinel1",
                    "band": "VV+VH",
                    "label": S1_RGB_LABEL,
                    "units": "dB (per kanal)",
                    "file": rgb_path.name,
                    "colormap": "false-color RGB",
                    "range_method": f"persentil {PCT_LOW}-{PCT_HIGH} per kanal",
                    "channels": {"R": "VV", "G": "VH", "B": "VV - VH"},
                    "width": layers["s1_vv"].width,
                    "height": layers["s1_vv"].height,
                    "interpretation": S1_RGB_INTERPRETATION,
                    "size_bytes": rgb_path.stat().st_size,
                }
                _adm_variant(rgb_path, rgb_entry)
                composite_entries.append(rgb_entry)
                written.append(rgb_path)
        except Exception as exc:
            logger.exception("[M10] gagal render komposit RGB")
            skipped.append({
                "key": S1_RGB_KEY, "source": "sentinel1", "band": "VV+VH",
                "reason": f"render failed: {exc}",
            })

    if composite_dir is not None and grid is not None and grid_source in layers:
        base_layer = layers[grid_source]
        for spec in PREVIEW_SPECS:
            layer = layers.get(spec.key)
            if spec.source == "sentinel1" or layer is None:
                continue
            out_path = composite_dir / fm.dated_filename(date_key, overlay_filename(spec.key))
            try:
                if _render_overlay_on_s1(base_layer, layer, spec, out_path) is None:
                    continue
                entry = {
                    "key": f"{spec.key}_on_s1",
                    "source": spec.source,
                    "band": spec.band,
                    "label": f"{spec.label} over Sentinel-1",
                    "units": spec.units,
                    "file": out_path.name,
                    "colormap": f"{spec.cmap} over grayscale {grid_source}",
                    "range_method": spec.scale,
                    "basemap": grid_source,
                    "width": layer.width,
                    "height": layer.height,
                    "interpretation": (
                        f"{spec.interpretation} The grey background is the "
                        f"{grid_source} image (coastline, land, sea) so that "
                        "pixel positions can be read geographically."
                    ),
                    "size_bytes": out_path.stat().st_size,
                }
                if spec.categorical:
                    entry["legend"] = [
                        {"value": v, "color": c, "alpha": a, "label": lbl}
                        for v, c, a, lbl in spec.categories
                    ]
                _adm_variant(out_path, entry)
                composite_entries.append(entry)
                written.append(out_path)
            except Exception as exc:
                logger.exception("[M10] gagal render overlay %s", spec.key)
                skipped.append({
                    "key": f"{spec.key}_on_s1", "source": spec.source,
                    "band": spec.band, "reason": f"render failed: {exc}",
                })

    if overwrite:
        known = {
            fm.dated_filename(date_key, f"{spec.key}.png") for spec in PREVIEW_SPECS
        } | {fm.dated_filename(date_key, f"{S1_RGB_KEY}.png")} | {
            fm.dated_filename(date_key, overlay_filename(spec.key))
            for spec in PREVIEW_SPECS if spec.source != "sentinel1"
        }
        known |= {admin_overlay.adm_name(n) for n in known}
        for kind_dir, entries in (
            (gray_dir, gray_entries), (color_dir, color_entries),
            (composite_dir, composite_entries),
        ):
            if kind_dir is None:
                continue
            current = {e["file"] for e in entries} | {e["file_adm"] for e in entries if e.get("file_adm")}
            for stale in kind_dir.glob("*.png"):
                if stale.name in known and stale.name not in current:
                    stale.unlink()
                    logger.info("[M10] hapus preview basi %s", stale)

    kinds: dict[str, dict] = {}
    for kind, kind_dir, entries, info_fn in (
        ("grayscale", gray_dir, gray_entries, _grayscale_info),
        ("colored", color_dir, color_entries, _colored_info),
        ("composite", composite_dir, composite_entries, _composite_info),
    ):
        if kind_dir is None:
            continue
        info_name = fm.dated_filename(date_key, f"{kind}_info.json")
        written.append(_write_json(kind_dir / info_name, info_fn(entries)))
        kinds[kind] = {
            "dir": kind,
            "info": info_name,
            "files": [e["file"] for e in entries],
        }

    sources_present = sorted({e["source"] for e in gray_entries + color_entries})
    metadata = {
        "dataset_id": dataset_id,
        "dataset_name": dataset_name,
        "acquisition_date": date_key,
        "s1_scene_key": s1_scene_key,
        "replaced_s1_scene_key": replaced_scene_key,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generator": MODULE,
        "tier": "PREVIEW",
        "processing_level": level,
        "derived_from": tier.upper(),
        "options": sorted(wanted),
        "max_side_px": max_side,
        "grid": (
            {"aligned_to": grid_source, "width": grid.width, "height": grid.height}
            if grid is not None else None
        ),
        "png_compress_level": PNG_COMPRESS_LEVEL,
        "sources_present": sources_present,
        "counts": {
            "grayscale": len(gray_entries),
            "colored": len(color_entries),
            "composite": len(composite_entries),
            "total_png": len(gray_entries) + len(color_entries) + len(composite_entries),
            "skipped": len(skipped),
        },
        "kinds": kinds,
        "skipped": skipped,
        "usage": {
            "grayscale": "Scientific reading of a single file; contrast is optimised per file.",
            "colored": "Publication and cross-date comparison; fixed scale.",
            "not_for": "Quantitative analysis — use gold/*.tif or fusion/*.h5.",
        },
    }
    metadata_name = fm.dated_filename(date_key, "preview_metadata.json")
    level_dir.mkdir(parents=True, exist_ok=True)
    written.append(_write_json(level_dir / metadata_name, metadata))
    written.append(_write_json(preview_dir / metadata_name, metadata))

    total_mb = sum(p.stat().st_size for p in written if p.exists()) / (1024 ** 2)
    logger.info(
        "[M10] PREVIEW %s level=%s dari %s: %d grayscale + %d colored + %d komposit "
        "PNG (%d dilewati, %.2f MB)",
        date_key, level, tier, len(gray_entries), len(color_entries),
        len(composite_entries), len(skipped), total_mb,
    )

    return {**metadata, "files": [str(p) for p in written], "total_size_mb": round(total_mb, 3)}


def run(
    dataset_id: int,
    dataset_name: str,
    acquisition_date: date_type | datetime | str,
    **kwargs,
) -> dict:
    """Alias konsisten dengan module2/module3/module4 yang juga mengekspos `run`."""
    return generate_previews(dataset_id, dataset_name, acquisition_date, **kwargs)


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if len(sys.argv) < 4:
        print(
            "Usage: python -m etl.module10_generate_preview "
            "<dataset_id> <dataset_name> <YYYYMMDD> [s1_scene_key]"
        )
        raise SystemExit(1)

    result = generate_previews(
        int(sys.argv[1]),
        sys.argv[2],
        sys.argv[3],
        s1_scene_key=sys.argv[4] if len(sys.argv) > 4 else None,
    )
    print(json.dumps(result["counts"], indent=2))
    for item in result["skipped"]:
        print(f"  dilewati {item['key']}: {item['reason']}")
