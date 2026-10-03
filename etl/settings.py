# etl/settings.py
"""Baca ``app_settings`` (PIPELINE.md §11): nilai yang boleh diubah ADMIN tanpa restart.

Default di sini sama dengan seed ``monitor_seed.sql`` dan hanya dipakai bila
barisnya tidak ada (mis. database lama yang belum di-seed ulang), supaya kode
tidak gagal karena satu kunci hilang.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text

logger = logging.getLogger(__name__)

DEFAULTS: dict[str, Any] = {
    "live.max_areas": 5,
    "live.retention_max": 60,
    "live.retention_default": 6,
    "live.default_area_name": "Lebak Selatan",
    "report.timezone": "Asia/Jakarta",
    "water.vh_threshold_db": -20,
    "dataset.max_days": 366,
    "hydromet.min_valid_fraction": 0.1,
    "hydromet.waiting_max_days": 3,
    "report.wait_hydromet_minutes": 60,
}


def get_setting(sess, key: str, default: Any = None) -> Any:
    """Nilai JSON ``app_settings.setting_value`` (sudah di-decode psycopg2)."""
    try:
        value = sess.scalar(text("SELECT setting_value FROM app_settings WHERE setting_key = :k"), {"k": key})
    except Exception:
        logger.exception("[SETTINGS] gagal membaca %s", key)
        value = None
    if value is None:
        return DEFAULTS.get(key, default) if default is None else default
    return value


def read_setting(db, key: str, default: Any = None) -> Any:
    """Seperti get_setting, dengan session baru dari DatabaseClient."""
    with db.session() as sess:
        return get_setting(sess, key, default)
