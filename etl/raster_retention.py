# etl/raster_retention.py
"""Jendela berkas raster bergulir dataset utama HYDROMET_AOI (M58).

Berkas raster GPM/MODIS (COG PROCESSED + antara ``_work/YYYYMMDD``) yang
tanggalnya lebih tua dari ``storage.raster_retention_days`` (365 hari) dihapus.
Yang TIDAK pernah dihapus: angka per kecamatan (``region_observations``),
baris ``nasa_scenes``/``data_products`` (produk ditandai ``is_valid = false``
supaya lineage tetap terbaca), dan dataset buatan pengguna. Scene S1 Live
memakai jendela yang sama lewat ``LiveMonitor.enforce_retention``.

Aman bagi job harian: akumulasi 30 hari dan komposit MODIS membaca granule
mentah (``_granule_cache``, 45 hari), bukan COG lama; pembaruan Late -> Final
hanya menyentuh 153 hari terakhir.
"""

from __future__ import annotations

import logging
import re
import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import text

from etl import folder_manager as fm
from etl import regions as rg
from etl.settings import get_setting

logger = logging.getLogger(__name__)

_DATE_IN_NAME = re.compile(r"_(\d{8})(?=[_.])")


def _file_date(name: str) -> date | None:
    m = _DATE_IN_NAME.search(name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y%m%d").date()
    except ValueError:
        return None


def _dir_date(name: str) -> date | None:
    try:
        return datetime.strptime(name, "%Y%m%d").date() if len(name) == 8 else None
    except ValueError:
        return None


def prune_main_rasters(db, today: date | None = None, dry_run: bool = False) -> dict:
    """Hapus raster dataset utama yang lebih tua dari jendela. Idempoten."""
    today = today or datetime.now(timezone.utc).date()
    with db.session() as sess:
        ds = rg.hydromet_dataset(sess)
        days = int(get_setting(sess, "storage.raster_retention_days"))
    if ds is None:
        return {"removed": 0, "freed_bytes": 0, "cutoff": None}
    cutoff = today - timedelta(days=days)
    root = fm.get_dataset_root(ds["dataset_id"], ds["name"])
    removed, freed, names = 0, 0, []

    for src in ("gpm", "modis"):
        base = root / fm.SOURCE_DIR_NAMES[src]
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            d = _file_date(p.name) if p.is_file() else None
            if d is None or d >= cutoff:
                continue
            size = p.stat().st_size
            if not dry_run:
                try:
                    p.unlink()
                except OSError:
                    logger.warning("[RETENTION] gagal menghapus %s", p)
                    continue
            removed += 1
            freed += size
            names.append(p.name)

    work = root / "_work"
    if work.is_dir():
        for sub in work.iterdir():
            d = _dir_date(sub.name) if sub.is_dir() else None
            if d is None or d >= cutoff:
                continue
            files = [p for p in sub.rglob("*") if p.is_file()]
            size = sum(p.stat().st_size for p in files)
            if not dry_run:
                shutil.rmtree(sub, ignore_errors=True)
            removed += len(files)
            freed += size
            names += [p.name for p in files]

    if names and not dry_run:
        with db.session() as sess:
            sess.execute(text("""
                UPDATE data_products SET is_valid = false, updated_at = now()
                WHERE dataset_id = :d AND is_valid AND file_name = ANY(:n)"""),
                {"d": ds["dataset_id"], "n": sorted(set(names))})
    if removed:
        logger.info("[RETENTION] raster dataset utama < %s: %d berkas (%.1f MB)%s",
                    cutoff, removed, freed / 2 ** 20, " [dry-run]" if dry_run else "")
    return {"removed": removed, "freed_bytes": freed, "cutoff": cutoff.isoformat()}
