"""Path management utility untuk struktur penyimpanan data per dataset."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import date, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

TIERS: tuple[str, ...] = (
    "raw", "aligned", "despeckled", "indices", "accumulated", "cog",
    "preview", "fused",
)
LEGACY_TIERS: tuple[str, ...] = ("bronze", "silver", "gold", "fusion")
ALL_TIERS: tuple[str, ...] = TIERS + LEGACY_TIERS

SOURCES: tuple[str, ...] = ("sentinel1", "modis", "gpm")

TIER_SOURCES: dict[str, tuple[str, ...]] = {
    "raw": SOURCES,
    "aligned": SOURCES,
    "despeckled": ("sentinel1",),
    "indices": ("modis",),
    "accumulated": ("gpm",),
    "cog": SOURCES,
    "preview": (),
    "fused": (),
    "bronze": SOURCES,
    "silver": SOURCES,
    "gold": SOURCES,
    "fusion": (),
}

SOURCELESS_TIERS: tuple[str, ...] = tuple(t for t, s in TIER_SOURCES.items() if not s)

PREVIEW_KINDS: tuple[str, ...] = ("grayscale", "colored", "composite")

PREVIEW_LEVELS: tuple[str, ...] = ("RAW", "PROCESSED")
DEFAULT_PREVIEW_LEVEL = "PROCESSED"

FLAT_RAW_SOURCES: frozenset[str] = frozenset({"modis", "gpm"})

DATA_ROOT = Path("data") / "datasets"

GRANULE_CACHE_DIRNAME = "_granule_cache"
SCRATCH_DIRNAME = "_work"

GRANULE_CACHE_LABEL = "(granule cache)"

SOURCE_DB_VALUES: dict[str, str] = {
    "sentinel1": "SENTINEL1",
    "modis": "MODIS",
    "gpm": "GPM",
}
FUSION_DB_SOURCE = "FUSION"

LEVELS: tuple[str, ...] = ("RAW", "PROCESSED")

SOURCE_DIR_NAMES: dict[str, str] = {
    "sentinel1": "sentinel-1",
    "modis": "modis",
    "gpm": "gpm-imerg",
}
DIR_NAME_TO_SOURCE: dict[str, str] = {v: k for k, v in SOURCE_DIR_NAMES.items()}

LEVEL_BY_TIER: dict[str, str] = {
    "ALIGNED": "RAW",
    "COG": "PROCESSED",
    "BRONZE": "RAW",
    "GOLD": "PROCESSED",
}

FUSION_DIRNAME = "fusion"
PREVIEW_DIRNAME = "preview"

_FUSION_TIER_NAMES: frozenset[str] = frozenset({"fusion", "fused"})


def normalize_level(level: str) -> str:
    """Level pemrosesan kanonik (huruf besar). Menolak yang tidak dikenal:
    level yang salah ketik akan membuat berkas mendarat di laci yang tidak
    pernah dilihat siapa pun."""
    lv = str(level).strip().upper()
    if lv not in LEVELS:
        raise ValueError(f"Invalid level: {level!r}. Valid: {LEVELS}")
    return lv


def source_dir_name(source: str) -> str:
    """Nama folder untuk sebuah source."""
    return SOURCE_DIR_NAMES[normalize_source(source)]


def get_source_level_dir(
    dataset_id: int, dataset_name: str, source: str, level: str
) -> Path:
    """Laci satu sumber pada satu level: {source}/{RAW|PROCESSED}/."""
    return (
        get_dataset_root(dataset_id, dataset_name)
        / source_dir_name(source)
        / normalize_level(level)
    )


def ensure_source_level_dir(
    dataset_id: int, dataset_name: str, source: str, level: str
) -> Path:
    p = get_source_level_dir(dataset_id, dataset_name, source, level)
    p.mkdir(parents=True, exist_ok=True)
    return p


def level_for_tier(tier: str) -> str | None:
    """Laci tujuan untuk artefak di `tier`, atau None kalau tier itu artefak
    antara yang tidak disimpan (RAW/SILVER)."""
    return LEVEL_BY_TIER.get(str(tier).strip().upper())


def dated_filename(date_key_str: str, stem: str) -> str:
    """Nama berkas berprefiks tanggal, mis. "20240920_modis_ndvi.tif"."""
    if _DATE_IN_KEY_RE.search(stem):
        return stem
    return f"{date_key_str}_{stem}"


def date_from_filename(name: str) -> str | None:
    """Tanggal YYYYMMDD yang tertanam di nama berkas, atau None."""
    m = _DATE_IN_KEY_RE.search(str(name))
    return m.group(1) if m else None


_DATE_DIR_RE = re.compile(r"^\d{8}$")
_DATE_IN_KEY_RE = re.compile(r"(?<!\d)(\d{8})(?!\d)")


def slugify(name: str) -> str:
    """Nama dataset -> slug aman-filesystem, mis. "hakim d1" -> "hakim_d1".
    Dipakai untuk nama folder dataset dan nama file log run-nya
    (etl/pipeline_logger.py), jadi keduanya selalu konsisten."""
    slug = re.sub(r"[^A-Za-z0-9_.-]", "_", name).strip("_")
    return slug or "dataset"


def scene_slug(key: str) -> str:
    """Sanitasi kunci scene (product_identifier S1 atau tanggal YYYYMMDD)
    supaya aman jadi nama folder."""
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(key))


def date_key(d: date | datetime | str) -> str:
    """Normalisasi tanggal ke format kunci scene YYYYMMDD."""
    if isinstance(d, datetime):
        d = d.date()
    if isinstance(d, date):
        return d.strftime("%Y%m%d")
    s = str(d).replace("-", "")
    if len(s) != 8 or not s.isdigit():
        raise ValueError(
            f"invalid date: {d!r}. Use a date/datetime object or a "
            "'YYYYMMDD'/'YYYY-MM-DD' string."
        )
    return s


def _valid_date(s: str) -> bool:
    try:
        datetime.strptime(s, "%Y%m%d")
    except ValueError:
        return False
    return True


def scene_date_key(scene_key: str) -> str:
    """Folder tanggal untuk sebuah kunci scene."""
    key = str(scene_key)
    for candidate in _DATE_IN_KEY_RE.findall(key):
        if _valid_date(candidate):
            return candidate
    raise ValueError(
        f"Scene key {scene_key!r} does not contain a YYYYMMDD date — "
        "its date folder cannot be determined."
    )


def normalize_tier(tier: str) -> str:
    t = str(tier).lower()
    if t not in ALL_TIERS:
        raise ValueError(f"Invalid tier: {tier!r}. Valid: {ALL_TIERS}")
    return t


def normalize_source(source: str) -> str:
    s = str(source).lower()
    if s not in SOURCES:
        raise ValueError(f"Invalid source: {source!r}. Valid: {SOURCES}")
    return s


def sources_for_tier(tier: str) -> tuple[str, ...]:
    """Source yang absah untuk satu tier. Kosong untuk `fusion` (lintas-source)."""
    return TIER_SOURCES[normalize_tier(tier)]


def validate_tier_source(tier: str, source: str) -> tuple[str, str]:
    """Normalisasi + validasi pasangan tier/source. Menolak source untuk tier
    lintas-source dan source yang tidak dipakai tier itu."""
    tier = normalize_tier(tier)
    source = normalize_source(source)
    allowed = TIER_SOURCES[tier]
    if not allowed:
        raise ValueError(
            f"Tier {tier!r} has no per-source level (it combines all "
            f"sources). Use get_fusion_dir()/get_preview_dir()."
        )
    if source not in allowed:
        raise ValueError(
            f"Source {source!r} is not used in tier {tier!r}. Valid: {allowed}"
        )
    return tier, source


def db_source(source: str) -> str:
    """Nama folder source -> nilai kolom data_products.source."""
    return SOURCE_DB_VALUES[normalize_source(source)]


def dataset_dir_name(dataset_id: int, dataset_name: str) -> str:
    return f"{dataset_id}_{slugify(dataset_name)}"


def get_dataset_root(dataset_id: int, dataset_name: str) -> Path:
    """Folder root untuk sebuah dataset: data/datasets/{id}_{slug}/"""
    return DATA_ROOT / dataset_dir_name(dataset_id, dataset_name)


def get_dataset_metadata_path(dataset_id: int, dataset_name: str) -> Path:
    """Path ke metadata.json level-dataset."""
    return get_dataset_root(dataset_id, dataset_name) / "metadata.json"


def get_date_dir(dataset_id: int, dataset_name: str, date: date | datetime | str) -> Path:
    """Folder satu tanggal akuisisi: {id}_{slug}/{YYYYMMDD}/."""
    return get_dataset_root(dataset_id, dataset_name) / date_key(date)


def list_date_dirs(dataset_root: Path) -> list[Path]:
    """Folder tanggal warisan layout lama, urut kronologis."""
    if not dataset_root.is_dir():
        return []
    return sorted(
        d for d in dataset_root.iterdir() if d.is_dir() and _DATE_DIR_RE.match(d.name)
    )


def is_legacy_layout(dataset_root: Path) -> bool:
    """True kalau dataset ini memakai struktur folder sebelum relayout."""
    return bool(list_date_dirs(dataset_root))


def list_dates(dataset_id: int, dataset_name: str) -> list[str]:
    """Tanggal (YYYYMMDD) yang benar-benar punya berkas di dataset ini."""
    root = get_dataset_root(dataset_id, dataset_name)
    if not root.is_dir():
        return []
    if is_legacy_layout(root):
        return [d.name for d in list_date_dirs(root)]

    dates: set[str] = set()
    for source in SOURCES:
        src_root = root / SOURCE_DIR_NAMES[source]
        if not src_root.is_dir():
            continue
        for f in src_root.rglob("*"):
            if f.is_file():
                d = date_from_filename(f.name)
                if d:
                    dates.add(d)
    return sorted(dates)


def get_tier_dir(
    dataset_id: int, dataset_name: str, date: date | datetime | str, tier: str
) -> Path:
    """Folder satu tier pada satu tanggal: {YYYYMMDD}/{tier}/."""
    return get_date_dir(dataset_id, dataset_name, date) / normalize_tier(tier)


def get_source_dir(
    dataset_id: int, dataset_name: str, date: date | datetime | str, tier: str, source: str
) -> Path:
    """Folder satu source pada satu tier dan tanggal: {YYYYMMDD}/{tier}/{source}/."""
    tier, source = validate_tier_source(tier, source)
    return get_tier_dir(dataset_id, dataset_name, date, tier) / source


def get_scene_dir(
    dataset_id: int, dataset_name: str, tier: str, source: str, scene_key: str
) -> Path:
    """Path folder satu scene. Tanggal diturunkan dari kunci scene-nya."""
    tier_u = normalize_tier(tier).upper()
    level = level_for_tier(tier_u)
    if level is not None:
        return get_source_level_dir(dataset_id, dataset_name, source, level)

    return (
        get_scratch_dir(dataset_id, dataset_name, scene_key)
        / tier_u.lower()
        / normalize_source(source)
    )


def ensure_scene_dir(
    dataset_id: int, dataset_name: str, tier: str, source: str, scene_key: str
) -> Path:
    """Buat (jika belum ada) dan kembalikan folder satu scene."""
    p = get_scene_dir(dataset_id, dataset_name, tier, source, scene_key)
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_fusion_dir(dataset_id: int, dataset_name: str, scene_key: str) -> Path:
    """Folder output fusion: fusion/ di root dataset."""
    return get_dataset_root(dataset_id, dataset_name) / FUSION_DIRNAME


def ensure_fusion_dir(
    dataset_id: int, dataset_name: str, scene_key: str, strategy_subfolder: str | None = None
) -> Path:
    """Folder output fusion, opsional dipecah per strategi."""
    p = get_fusion_dir(dataset_id, dataset_name, scene_key)
    if strategy_subfolder:
        p = p / strategy_subfolder
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_preview_dir(dataset_id: int, dataset_name: str, scene_key: str) -> Path:
    """Folder preview: preview/ di root dataset."""
    return get_dataset_root(dataset_id, dataset_name) / PREVIEW_DIRNAME


def ensure_preview_dir(dataset_id: int, dataset_name: str, scene_key: str) -> Path:
    p = get_preview_dir(dataset_id, dataset_name, scene_key)
    p.mkdir(parents=True, exist_ok=True)
    return p


def normalize_preview_level(processing_level: str | None) -> str:
    """Validasi nama folder level preview. None -> PROCESSED."""
    if processing_level is None:
        return DEFAULT_PREVIEW_LEVEL
    level = str(processing_level).strip().upper()
    if level not in PREVIEW_LEVELS:
        raise ValueError(
            f"Invalid preview level: {processing_level!r}. Valid: {PREVIEW_LEVELS}"
        )
    return level


def get_preview_level_dir(
    dataset_id: int, dataset_name: str, scene_key: str,
    processing_level: str | None = None,
) -> Path:
    """Folder satu level pemrosesan: {YYYYMMDD}/preview/{RAW|PROCESSED}/."""
    return (
        get_preview_dir(dataset_id, dataset_name, scene_key)
        / normalize_preview_level(processing_level)
    )


def get_preview_kind_dir(
    dataset_id: int, dataset_name: str, scene_key: str, kind: str,
    processing_level: str | None = None,
) -> Path:
    """Subfolder satu jenis render:
    {YYYYMMDD}/preview/{RAW|PROCESSED}/{grayscale|colored|composite}/."""
    if kind not in PREVIEW_KINDS:
        raise ValueError(f"Invalid preview kind: {kind!r}. Valid: {PREVIEW_KINDS}")
    return get_preview_level_dir(
        dataset_id, dataset_name, scene_key, processing_level
    ) / kind


def ensure_preview_kind_dir(
    dataset_id: int, dataset_name: str, scene_key: str, kind: str,
    processing_level: str | None = None,
) -> Path:
    p = get_preview_kind_dir(dataset_id, dataset_name, scene_key, kind, processing_level)
    p.mkdir(parents=True, exist_ok=True)
    return p


def list_preview_levels(dataset_id: int, dataset_name: str, scene_key: str) -> list[str]:
    """Level yang benar-benar punya folder di disk untuk tanggal ini, urut
    RAW lalu PROCESSED. Kosong berarti belum ada preview untuk tanggal itu."""
    root = get_preview_dir(dataset_id, dataset_name, scene_key)
    if not root.is_dir():
        return []
    return [level for level in PREVIEW_LEVELS if (root / level).is_dir()]


def get_scratch_dir(dataset_id: int, dataset_name: str, scene_key: str) -> Path:
    """Folder kerja sementara (hasil kalibrasi radiometrik sebelum crop),
    dihapus otomatis setelah tahap CROP selesai — bukan bagian dari tier
    resmi, jadi diletakkan di luar folder tanggal."""
    return get_dataset_root(dataset_id, dataset_name) / SCRATCH_DIRNAME / scratch_slug(scene_key)


SCRATCH_SLUG_MAX = 32


def scratch_slug(key: str) -> str:
    """Nama folder scratch yang pendek dan deterministik untuk `key`."""
    slug = scene_slug(key)
    if len(slug) <= SCRATCH_SLUG_MAX:
        return slug
    digest = hashlib.sha1(str(key).encode("utf-8")).hexdigest()[:10]
    return f"{slug[:SCRATCH_SLUG_MAX - 11]}_{digest}"


def long_path(path: Path | str) -> Path:
    """Path aman dari batas MAX_PATH (260) Windows lewat prefix
    extended-length ``\\\\?\\``. LongPathsEnabled di registry sering dikunci
    kebijakan institusi, jadi jangan bergantung ke konfigurasi mesin.
    No-op di luar Windows. Hanya untuk API Python (open, zipfile, shutil);
    GDAL/rasterio tidak selalu menerima prefix ini."""
    path = Path(path)
    if os.name != "nt":
        return path
    s = str(path.resolve())
    prefix = "\\\\?\\"
    return Path(s) if s.startswith(prefix) else Path(prefix + s)


def get_granule_cache_root(dataset_root: Path) -> Path:
    """Folder induk cache granule di bawah satu root dataset."""
    return dataset_root / GRANULE_CACHE_DIRNAME


def get_granule_cache_dir(dataset_id: int, dataset_name: str, source: str) -> Path:
    """Folder cache granule mentah MODIS/GPM (.hdf/.nc4 sebelum
    di-mosaic/crop): _granule_cache/{source}/. Flat dan di luar folder
    tanggal: satu granule GPM harian ikut dipakai window 72h/7d
    tanggal-tanggal berikutnya, jadi tidak bisa dimiliki satu tanggal saja."""
    source = normalize_source(source)
    if source not in FLAT_RAW_SOURCES:
        raise ValueError(
            f"Source {source!r} does not use the flat granule cache. "
            f"Valid: {sorted(FLAT_RAW_SOURCES)}"
        )
    return get_granule_cache_root(get_dataset_root(dataset_id, dataset_name)) / source


def tier_dirs_under(dataset_root: Path, tier: str) -> list[Path]:
    """Semua folder yang menyimpan isi satu tier di bawah satu root dataset:
    {tanggal}/{tier}/ untuk tiap tanggal, ditambah _granule_cache/ untuk tier
    raw. Dipakai untuk menyapu satu tier lintas tanggal."""
    tier = normalize_tier(tier)

    dirs = [d / tier for d in list_date_dirs(dataset_root) if (d / tier).is_dir()]
    if dirs:
        if tier == "raw":
            cache = get_granule_cache_root(dataset_root)
            if cache.is_dir():
                dirs.append(cache)
        return dirs

    if tier in _FUSION_TIER_NAMES:
        p = dataset_root / FUSION_DIRNAME
        return [p] if p.is_dir() else []
    if tier == "preview":
        p = dataset_root / PREVIEW_DIRNAME
        return [p] if p.is_dir() else []

    level = level_for_tier(tier)
    if level is not None:
        return [
            d for d in (
                dataset_root / SOURCE_DIR_NAMES[src] / level for src in SOURCES
            ) if d.is_dir()
        ]

    if tier == "raw":
        cache = get_granule_cache_root(dataset_root)
        if cache.is_dir():
            return [cache]
    return []


def _source_dirs(dataset_id: int, dataset_name: str, tier: str, source: str) -> list[Path]:
    """Folder {tanggal}/{tier}/{source}/ yang ada di disk, lintas tanggal."""
    tier, source = validate_tier_source(tier, source)
    root = get_dataset_root(dataset_id, dataset_name)

    legacy = [
        d / tier / source for d in list_date_dirs(root) if (d / tier / source).is_dir()
    ]
    if legacy:
        return legacy

    level = level_for_tier(tier)
    if level is None:
        return []
    p = root / SOURCE_DIR_NAMES[source] / level
    return [p] if p.is_dir() else []


def list_sources(dataset_id: int, dataset_name: str, tier: str) -> list[str]:
    """Source yang benar-benar punya folder on-disk di satu tier (di tanggal
    mana pun, termasuk cache granule untuk tier raw)."""
    tier = normalize_tier(tier)
    allowed = TIER_SOURCES[tier]
    if not allowed:
        return []
    root = get_dataset_root(dataset_id, dataset_name)
    found = set()
    for d in tier_dirs_under(root, tier):
        found.update(s for s in allowed if (d / s).is_dir())
        src = DIR_NAME_TO_SOURCE.get(d.parent.name)
        if src in allowed and any(f.is_file() for f in d.iterdir()):
            found.add(src)
    return [s for s in allowed if s in found]


def list_scenes(dataset_id: int, dataset_name: str, tier: str, source: str) -> list[str]:
    """Semua kunci scene satu source pada satu tier, lintas tanggal."""
    scenes: set[str] = set()
    for src_dir in _source_dirs(dataset_id, dataset_name, tier, source):
        legacy_date = src_dir.parent.parent.name
        for entry in src_dir.iterdir():
            if entry.name.startswith(("_", ".")):
                continue
            if entry.is_dir():
                scenes.add(entry.name)
            elif entry.is_file():
                if _DATE_DIR_RE.match(legacy_date):
                    scenes.add(legacy_date)          # layout lama
                else:
                    d = date_from_filename(entry.name)
                    if d:
                        scenes.add(d)
    return sorted(scenes)


def list_loose_files(
    dataset_id: int, dataset_name: str, tier: str, source: str
) -> list[Path]:
    """Cache granule mentah `_granule_cache/modis/` dan `_granule_cache/gpm/`
    (lihat FLAT_RAW_SOURCES) — file tier raw yang tidak milik satu tanggal,
    jadi tidak pernah muncul lewat `list_scenes`. Kosong untuk kombinasi lain."""
    tier, source = validate_tier_source(tier, source)
    if tier != "raw" or source not in FLAT_RAW_SOURCES:
        return []
    p = get_granule_cache_dir(dataset_id, dataset_name, source)
    if not p.exists():
        return []
    return sorted(f for f in p.iterdir() if f.is_file() and not f.name.startswith("."))


def list_sourceless_scenes(dataset_id: int, dataset_name: str, tier: str) -> list[str]:
    """Tanggal yang punya folder satu tier lintas-source (`fusion`,
    `preview`), yang isinya langsung {tanggal}/{tier}/ tanpa level {source}."""
    tier = normalize_tier(tier)
    if TIER_SOURCES[tier]:
        raise ValueError(
            f"Tier {tier!r} has a per-source level — use list_scenes(tier, source)."
        )
    root = get_dataset_root(dataset_id, dataset_name)

    legacy = [d.name for d in list_date_dirs(root) if (d / tier).is_dir()]
    if legacy:
        return legacy

    base = root / (FUSION_DIRNAME if tier in _FUSION_TIER_NAMES else PREVIEW_DIRNAME)
    if not base.is_dir():
        return []
    return sorted({
        d for d in (date_from_filename(f.name) for f in base.rglob("*") if f.is_file())
        if d
    })


def list_fusion_scenes(dataset_id: int, dataset_name: str) -> list[str]:
    return list_sourceless_scenes(dataset_id, dataset_name, "fusion")


def list_preview_scenes(dataset_id: int, dataset_name: str) -> list[str]:
    return list_sourceless_scenes(dataset_id, dataset_name, "preview")


def _files_under(p: Path) -> list[Path]:
    if not p.exists():
        return []
    return sorted(f for f in p.rglob("*") if f.is_file())


def get_scene_files(
    dataset_id: int, dataset_name: str, tier: str, source: str, scene_key: str
) -> list[Path]:
    """Semua file di dalam satu scene pada satu source/tier."""
    p = get_scene_dir(dataset_id, dataset_name, tier, source, scene_key)
    if not p.exists():
        return []

    if level_for_tier(tier) is not None:
        slug = scene_slug(scene_key)
        want_date = scene_date_key(scene_key)
        return sorted(
            f for f in p.iterdir()
            if f.is_file() and (
                slug in f.name
                or f.name.startswith(slug.removesuffix(".SAFE"))
                or (_DATE_DIR_RE.match(slug) and date_from_filename(f.name) == want_date)
            )
        )

    if _DATE_DIR_RE.match(scene_slug(scene_key)):
        return sorted(f for f in p.iterdir() if f.is_file())
    return _files_under(p)


def get_preview_scene_files(dataset_id: int, dataset_name: str, scene_key: str) -> list[Path]:
    """Semua berkas satu scene preview, termasuk yang ada di dalam subfolder
    {LEVEL}/{grayscale,colored,composite}/ (_files_under rglob rekursif)."""
    return _files_under(get_preview_dir(dataset_id, dataset_name, scene_key))


def get_preview_date_files(
    dataset_id: int, dataset_name: str, date_key_str: str
) -> list[Path]:
    """Berkas preview yang benar-benar milik SATU tanggal."""
    want = scene_date_key(date_key_str)
    return [
        f for f in _files_under(get_preview_dir(dataset_id, dataset_name, date_key_str))
        if date_from_filename(f.name) == want
    ]


def get_sourceless_scene_files(
    dataset_id: int, dataset_name: str, tier: str, scene_key: str
) -> list[Path]:
    """Versi generik get_preview_scene_files (dan tier fusion), untuk
    pemanggil yang tier-nya baru diketahui saat runtime (mis. API listing)."""
    tier = normalize_tier(tier)
    if TIER_SOURCES[tier]:
        raise ValueError(f"Tier {tier!r} has a per-source level — use get_scene_files().")
    root = get_dataset_root(dataset_id, dataset_name)
    legacy_dir = root / scene_date_key(scene_key) / tier
    if legacy_dir.is_dir():
        return _files_under(legacy_dir)

    base = root / (FUSION_DIRNAME if tier in _FUSION_TIER_NAMES else PREVIEW_DIRNAME)
    want = scene_date_key(scene_key)
    return sorted(
        f for f in _files_under(base)
        if date_from_filename(f.name) in (want, None)
    )


def get_source_files(dataset_id: int, dataset_name: str, tier: str, source: str) -> list[Path]:
    """Semua file satu source di satu tier, lintas tanggal (semua scene +
    cache granule untuk raw)."""
    files: list[Path] = []
    for d in _source_dirs(dataset_id, dataset_name, tier, source):
        files.extend(_files_under(d))
    files.extend(list_loose_files(dataset_id, dataset_name, tier, source))
    return sorted(files)


def get_tier_files(dataset_id: int, dataset_name: str, tier: str) -> list[Path]:
    """Semua file di dalam satu tier, lintas tanggal dan source."""
    files: list[Path] = []
    for d in tier_dirs_under(get_dataset_root(dataset_id, dataset_name), tier):
        files.extend(_files_under(d))
    return sorted(files)


def _size_of(files: list[Path]) -> int:
    total = 0
    for f in files:
        try:
            total += f.stat().st_size
        except OSError:
            continue
    return total


def storage_breakdown(dataset_id: int, dataset_name: str) -> dict:
    """Ringkasan pemakaian disk satu dataset, dipecah per tier lalu per source."""
    tiers: dict[str, dict] = {}
    per_source: dict[str, dict] = {}

    for tier in TIERS:
        allowed = TIER_SOURCES[tier]
        sources: dict[str, dict] = {}

        if allowed:
            for source in allowed:
                files = get_source_files(dataset_id, dataset_name, tier, source)
                if not files:
                    continue
                size = _size_of(files)
                sources[source] = {
                    "size_bytes": size,
                    "file_count": len(files),
                    "scene_count": len(list_scenes(dataset_id, dataset_name, tier, source)),
                }
                agg = per_source.setdefault(source, {"size_bytes": 0, "file_count": 0})
                agg["size_bytes"] += size
                agg["file_count"] += len(files)
            scene_count = sum(v["scene_count"] for v in sources.values())
        else:
            scene_count = len(list_sourceless_scenes(dataset_id, dataset_name, tier))

        files = get_tier_files(dataset_id, dataset_name, tier)
        size = _size_of(files)
        tiers[tier] = {
            "size_bytes": size,
            "file_count": len(files),
            "scene_count": scene_count,
            "sources": sources,
        }
        if not allowed and files:
            agg = per_source.setdefault(tier, {"size_bytes": 0, "file_count": 0})
            agg["size_bytes"] += size
            agg["file_count"] += len(files)

    return {
        "tiers": tiers,
        "sources": per_source,
        "total_size_bytes": sum(t["size_bytes"] for t in tiers.values()),
        "total_file_count": sum(t["file_count"] for t in tiers.values()),
    }


def write_dataset_metadata(dataset_id: int, dataset_name: str, metadata: dict) -> Path:
    """Tulis metadata.json level-dataset (ringkasan, bukan sumber kebenaran —
    DB tetap authoritative)."""
    path = get_dataset_metadata_path(dataset_id, dataset_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(metadata, f, indent=2, default=str)
    tmp.replace(path)
    return path


def read_dataset_metadata(dataset_id: int, dataset_name: str) -> dict | None:
    """Baca metadata.json level-dataset, None kalau belum pernah ditulis."""
    path = get_dataset_metadata_path(dataset_id, dataset_name)
    if not path.exists():
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("[FM] metadata.json dataset_id=%d tidak terbaca: %s", dataset_id, exc)
        return None
