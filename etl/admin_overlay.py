# etl/admin_overlay.py
"""Varian "garis wilayah" dari setiap PNG preview (INTERFACE: checkbox taskbar).

Setiap preview map disimpan DUA kali:

    {key}.png       citra apa adanya (yang tampil secara default)
    {key}_adm.png   citra yang sama + batas kecamatan dan nama wilayahnya

Dua berkas, bukan satu berkas plus overlay di browser: batas wilayah harus
sejajar piksel dengan rasternya, dan satu-satunya tempat yang tahu transform
affine + CRS raster itu adalah perender PNG di sini. Menggambarnya di CSS/SVG
berarti menebak georeferensi di sisi klien.

Geometrinya dari ``administrative_regions`` (COD-AB adm3, EPSG:4326), dibaca
SEKALI per proses lalu dipakai ulang semua scene (batas administratif tidak
berubah di tengah siklus). Garis digambar putih dengan casing hitam, nama
wilayah putih dengan stroke hitam -- satu-satunya pasangan yang tetap terbaca
di atas citra gelap (air), terang (NoData putih), maupun colormap hujan.

Modul ini TIDAK PERNAH melempar ke pemanggil: varian garis wilayah adalah
tambahan, jadi kegagalannya (DB mati, batas belum dimuat) hanya berarti
preview biasa saja yang ada dan UI diam-diam memakai itu.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

SUFFIX = "_adm"
# Toleransi penyederhanaan batas, derajat (~33 m di ekuator). Garis preview
# tebalnya 2-3 px pada 768-1024 px untuk AOI seukuran kabupaten, jadi simpul
# yang lebih rapat dari ini tidak pernah terlihat -- hanya memperlambat.
SIMPLIFY_DEG = 0.0003
LINE_RGB = (255, 255, 255)
CASING_RGB = (0, 0, 0)
LABEL_RGB = (255, 255, 255)


def adm_name(filename: str | Path) -> str:
    """s1_vh.png -> s1_vh_adm.png."""
    p = Path(filename)
    return p.with_name(p.stem + SUFFIX + p.suffix).name


def is_adm_file(filename: str) -> bool:
    return Path(filename).stem.endswith(SUFFIX)


@dataclass(frozen=True)
class Region:
    name: str
    rings: tuple[tuple[tuple[float, float], ...], ...]   # lon/lat
    label: tuple[float, float]                           # lon/lat


_cache: list[Region] | None = None
_own_db = None


def _rings(geojson: dict):
    """Cincin luar+dalam dari Polygon/MultiPolygon GeoJSON."""
    t, coords = geojson.get("type"), geojson.get("coordinates") or []
    polys = coords if t == "MultiPolygon" else [coords] if t == "Polygon" else []
    for poly in polys:
        for ring in poly:
            if len(ring) >= 2:
                yield tuple((float(x), float(y)) for x, y in ring)


_SQL_REGIONS = """
    SELECT region_name,
           ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom, :tol)) AS gj,
           ST_X(ST_PointOnSurface(geom)) AS lon,
           ST_Y(ST_PointOnSurface(geom)) AS lat
    FROM administrative_regions
    WHERE admin_level = 3 AND geom IS NOT NULL
    ORDER BY region_name
"""


def load_regions(db=None, *, refresh: bool = False) -> list[Region]:
    """Kecamatan (admin_level 3) beserta titik labelnya. Hasilnya di-cache per
    proses; daftar kosong (DB tidak terjangkau / batas belum dimuat) juga
    di-cache supaya tiap scene tidak mencoba menyambung ulang."""
    global _cache
    if _cache is not None and not refresh:
        return _cache
    from sqlalchemy import text

    out: list[Region] = []
    try:
        client = db or _default_db()
        with client.session() as sess:
            for r in sess.execute(text(_SQL_REGIONS), {"tol": SIMPLIFY_DEG}).mappings():
                rings = tuple(_rings(json.loads(r["gj"])))
                if rings:
                    out.append(Region(r["region_name"], rings, (float(r["lon"]), float(r["lat"]))))
    except Exception as exc:
        logger.warning("[ADM] batas wilayah tidak terbaca, preview garis wilayah dilewati: %s", exc)
        out = []
    _cache = out
    logger.info("[ADM] %d kecamatan dimuat untuk overlay garis wilayah", len(out))
    return _cache


def _default_db():
    """DatabaseClient role etl milik modul ini -- hanya dipakai pemanggil yang
    tidak punya koneksi sendiri (module10 lewat CLI/orchestrator)."""
    global _own_db
    if _own_db is None:
        from etl.database_client import DatabaseClient
        _own_db = DatabaseClient.from_env("etl")
    return _own_db


# --- menggambar ----------------------------------------------------------------

def _project(lons, lats, crs):
    """lon/lat -> koordinat CRS raster (identitas kalau rasternya sudah 4326)."""
    from rasterio.crs import CRS
    from rasterio.warp import transform as warp_transform
    wgs84 = CRS.from_epsg(4326)
    if crs is None or CRS.from_user_input(crs) == wgs84:
        return lons, lats
    return warp_transform(wgs84, crs, lons, lats)


def _to_pixels(regions, transform, crs):
    """[(wilayah, cincin piksel, titik label piksel)] pada grid PNG.

    Semua titik semua wilayah direproyeksi dalam SATU panggilan: transformasi
    koordinat rasterio punya biaya tetap per panggilan yang jauh lebih besar
    daripada per titik, dan satu kecamatan bisa punya ribuan simpul."""
    # Affine dipakai sebagai enam koefisien, bukan lewat operator `*` per
    # titik: satu kecamatan bisa punya ribuan simpul dan pemanggilan operator
    # itu mendominasi waktu render (plus memperingatkan deprecation).
    ia, ib, ic, id_, ie, if_ = (~transform)[:6]
    lons: list[float] = []
    lats: list[float] = []
    index: list[tuple[int, int]] = []
    for ri, reg in enumerate(regions):
        for ring in reg.rings:
            index.append((ri, len(ring)))
            lons.extend(p[0] for p in ring)
            lats.extend(p[1] for p in ring)
        index.append((ri, 1))           # titik label, selalu terakhir per wilayah
        lons.append(reg.label[0])
        lats.append(reg.label[1])
    if not lons:
        return []
    xs, ys = _project(lons, lats, crs)
    rings_of: dict[int, list] = {ri: [] for ri in range(len(regions))}
    label_of: dict[int, tuple | None] = {ri: None for ri in range(len(regions))}
    at = 0
    for ri, n in index:
        pts = [(ia * xs[i] + ib * ys[i] + ic, id_ * xs[i] + ie * ys[i] + if_)
               for i in range(at, at + n)]
        at += n
        if n == 1:
            label_of[ri] = pts[0]
        else:
            rings_of[ri].append(pts)
    return [(regions[ri], rings_of[ri], label_of[ri]) for ri in range(len(regions)) if rings_of[ri]]


def _nudge_inside(box, point, w: int, h: int, pad: int = 3):
    """Geser titik label secukupnya supaya seluruh teks masuk gambar.

    Wilayah yang titik tengahnya dekat tepi akan terpotong setengah huruf
    kalau digambar apa adanya -- nama yang terpotong lebih buruk daripada
    nama yang bergeser beberapa piksel dari pusat wilayahnya. Teks yang tetap
    tidak muat (lebih lebar dari gambarnya) dibuang: None."""
    bw, bh = box[2] - box[0], box[3] - box[1]
    if bw > w - 2 * pad or bh > h - 2 * pad:
        return None
    x, y = point
    x += max(0.0, pad - box[0]) - max(0.0, box[2] - (w - pad))
    y += max(0.0, pad - box[1]) - max(0.0, box[3] - (h - pad))
    return (x, y)


def _visible(rings, w: int, h: int, pad: int = 2) -> bool:
    return any(-pad <= x <= w + pad and -pad <= y <= h + pad
               for ring in rings for x, y in ring)


def _c(img, rgb):
    """Warna sesuai mode gambar: RGBA butuh alpha opak, RGB tiga kanal."""
    return (*rgb, 255) if img.mode == "RGBA" else rgb


def _font(size: int):
    """DejaVu Sans Bold (ikut matplotlib), font bitmap PIL bila tidak ada."""
    from PIL import ImageFont
    try:
        import matplotlib
        return ImageFont.truetype(
            str(Path(matplotlib.get_data_path()) / "fonts" / "ttf" / "DejaVuSans-Bold.ttf"), size)
    except Exception:
        return ImageFont.load_default()


def draw(img, transform, crs, regions=None) -> int:
    """Gambar batas + nama wilayah pada `img` (PIL Image, diubah di tempat).
    Mengembalikan jumlah wilayah yang tergambar."""
    from PIL import ImageDraw

    regions = load_regions() if regions is None else regions
    if not regions:
        return 0
    w, h = img.size
    longest = max(w, h)
    lw = max(1, round(longest / 500))
    pen = ImageDraw.Draw(img)
    font = _font(max(10, round(longest / 48)))
    boxes: list[tuple[float, float, float, float]] = []
    shown = [(reg, rings, label) for reg, rings, label in _to_pixels(regions, transform, crs)
             if _visible(rings, w, h)]
    drawn = len(shown)
    # Casing hitam SEMUA wilayah dulu, lalu garis putihnya: kalau digambar
    # berpasangan per wilayah, casing tetangga akan menimpa garis putih yang
    # sudah jadi di batas yang mereka bagi bersama.
    for _reg, rings, _label in shown:
        for ring in rings:
            pen.line(ring, fill=_c(img, CASING_RGB), width=lw + 2, joint="curve")
    for reg, rings, label in shown:
        for ring in rings:
            pen.line(ring, fill=_c(img, LINE_RGB), width=lw, joint="curve")
        if label is None or not (0 <= label[0] <= w and 0 <= label[1] <= h):
            continue
        label = _nudge_inside(pen.textbbox(label, reg.name.upper(), font=font, anchor="mm"),
                              label, w, h)
        if label is None:
            continue
        box = pen.textbbox(label, reg.name.upper(), font=font, anchor="mm")
        if any(box[0] < b[2] and b[0] < box[2] and box[1] < b[3] and b[1] < box[3] for b in boxes):
            continue   # nama bertumpuk: lebih baik hilang satu daripada dua-duanya tak terbaca
        boxes.append(box)
        pen.text(label, reg.name.upper(), font=font, anchor="mm", fill=_c(img, LABEL_RGB),
                 stroke_width=max(2, lw), stroke_fill=_c(img, CASING_RGB))
    return drawn


def write_variant(png_path: Path, transform, crs, regions=None) -> str | None:
    """Tulis `{stem}_adm.png` di samping `png_path`. Mengembalikan nama
    berkasnya, atau None kalau batas wilayah tidak ada / render gagal."""
    from PIL import Image

    png_path = Path(png_path)
    try:
        regions = load_regions() if regions is None else regions
        if not regions:
            return None
        with Image.open(png_path) as src:
            img = src.copy()
        if not draw(img, transform, crs, regions):
            return None
        out = png_path.with_name(adm_name(png_path.name))
        img.save(out, optimize=False)
        return out.name
    except Exception as exc:
        logger.warning("[ADM] varian garis wilayah %s gagal: %s", png_path.name, exc)
        return None
