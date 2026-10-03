# etl/geo_utils.py
"""
Utilitas bbox WGS84 (validasi dan konversi). Aturan validasi tinggal di satu
tempat ini supaya UI, API, dan pipeline tidak pernah berbeda pendapat soal
bbox yang sah. Geocoding Nominatim DataLab sudah dihapus (README §5).
"""

from __future__ import annotations

import re

# Batas span AOI. Swath Sentinel-1 IW ~250 km (~2.25 derajat), jadi 10 derajat
# (~1100 km) sudah sangat longgar; di atas itu hampir pasti salah input dan akan
# menarik ratusan scene tanpa disengaja.
MAX_SPAN_DEG = 10.0
# Di bawah ini bbox lebih kecil dari satu piksel GRD (~10 m) dan tidak berguna.
MIN_SPAN_DEG = 0.001


class BBoxError(ValueError):
    """Bbox tidak valid. Pesannya sudah ramah untuk ditampilkan ke pengguna."""


def validate_bbox(
    min_lon: float, min_lat: float, max_lon: float, max_lat: float
) -> tuple[float, float, float, float]:
    """Validasi bbox WGS84 dan kembalikan tuple float yang sudah bersih.

    Raises BBoxError dengan pesan berbahasa Indonesia bila tidak valid.
    """
    try:
        min_lon, min_lat = float(min_lon), float(min_lat)
        max_lon, max_lat = float(max_lon), float(max_lat)
    except (TypeError, ValueError):
        raise BBoxError("Coordinates must be numbers")

    for label, value in (("Longitude", min_lon), ("Longitude", max_lon)):
        if not -180.0 <= value <= 180.0:
            raise BBoxError(f"{label} must be between -180 and 180 (got {value})")
    for label, value in (("Latitude", min_lat), ("Latitude", max_lat)):
        if not -90.0 <= value <= 90.0:
            raise BBoxError(f"{label} must be between -90 and 90 (got {value})")

    if min_lon >= max_lon:
        raise BBoxError("Min longitude must be less than max longitude")
    if min_lat >= max_lat:
        raise BBoxError("Min latitude must be less than max latitude")

    span_lon, span_lat = max_lon - min_lon, max_lat - min_lat
    if span_lon < MIN_SPAN_DEG or span_lat < MIN_SPAN_DEG:
        raise BBoxError(
            f"Area too small, minimum {MIN_SPAN_DEG} degrees (~110 m) per side"
        )
    if span_lon > MAX_SPAN_DEG or span_lat > MAX_SPAN_DEG:
        raise BBoxError(
            f"Area too large, maximum {MAX_SPAN_DEG} degrees (~1100 km) per side"
        )

    return min_lon, min_lat, max_lon, max_lat


def bbox_to_wkt(min_lon: float, min_lat: float, max_lon: float, max_lat: float) -> str:
    """Bbox -> POLYGON WKT, urutan titik searah seperti seed data yang ada."""
    return (
        f"POLYGON(({min_lon} {min_lat}, {max_lon} {min_lat}, "
        f"{max_lon} {max_lat}, {min_lon} {max_lat}, {min_lon} {min_lat}))"
    )


def parse_bbox_string(raw: str) -> tuple[float, float, float, float]:
    """Parse bbox yang di-paste pengguna.

    Menerima 4 angka dipisah koma/spasi/titik-koma dengan urutan
    ``min_lon, min_lat, max_lon, max_lat`` (urutan bbox standar GDAL/GeoJSON).
    """
    numbers = re.findall(r"-?\d+(?:\.\d+)?", raw or "")
    if len(numbers) != 4:
        raise BBoxError(
            "The bbox format must be 4 numbers: min_lon, min_lat, max_lon, max_lat"
        )
    return validate_bbox(*[float(n) for n in numbers])
