# etl/advisory_lock.py
"""Satu worker per jenis job lewat PostgreSQL advisory lock (PIPELINE.md §7, M22).

``pg_try_advisory_lock(hashtext('orbit-u:' || key))`` dipegang di koneksi
khusus selama job berjalan. Bila gagal, worker lain sedang menjalankannya ->
pemanggil melewati job dan mencatat ``SKIPPED_LOCKED``. Kunci lepas sendiri
bila prosesnya mati karena koneksinya putus. Ini melengkapi ``job_lock``
berkas (per job/area), bukan menggantikannya.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import text

logger = logging.getLogger(__name__)

KEYS = ("hydromet", "live", "report")


@contextmanager
def advisory_lock(db, key: str, wait_seconds: float = 0, poll_seconds: float = 30) -> Iterator[bool]:
    """``with advisory_lock(db, "hydromet") as got:`` -> ``got`` False bila
    kunci dipegang worker lain (setelah menunggu ``wait_seconds``)."""
    conn = db._engine.connect()
    got = False
    try:
        deadline = time.monotonic() + max(0.0, wait_seconds)
        while True:
            got = bool(conn.execute(text("SELECT pg_try_advisory_lock(hashtext(:k))"),
                                    {"k": f"orbit-u:{key}"}).scalar())
            conn.commit()
            if got or time.monotonic() >= deadline:
                break
            time.sleep(min(poll_seconds, max(0.0, deadline - time.monotonic())))
        if not got:
            logger.info("[LOCK] %s dipegang worker lain", key)
        yield got
    finally:
        if got:
            try:
                conn.execute(text("SELECT pg_advisory_unlock(hashtext(:k))"), {"k": f"orbit-u:{key}"})
                conn.commit()
            except Exception:
                logger.exception("[LOCK] gagal melepas %s; koneksi ditutup", key)
                conn.invalidate()
        conn.close()


def is_locked(db, key: str) -> bool:
    """True bila ada sesi lain yang memegang kunci ``key`` (untuk status/tes)."""
    with db._engine.connect() as conn:
        return bool(conn.execute(text("""
            SELECT EXISTS (SELECT 1 FROM pg_locks
                           WHERE locktype = 'advisory' AND granted
                             AND database = (SELECT oid FROM pg_database WHERE datname = current_database())
                             AND objid = (hashtext(:k)::bigint & 4294967295)::oid)
        """), {"k": f"orbit-u:{key}"}).scalar())
