#!/usr/bin/env python
"""Backfill Job Hidromet per tanggal UTC, berurutan dan bisa dilanjutkan (PIPELINE.md §10 langkah 6).

Pakai:
    python scripts/backfill_hydromet.py --from 2023-01-01 --to 2025-12-31
    python scripts/backfill_hydromet.py --from 2024-01-01 --to 2024-01-31 --no-modis
    python scripts/backfill_hydromet.py --from 2024-01-01 --to 2024-01-31 --dry-run

Tanggal yang sudah COMPLETED dilewati, jadi bila proses dibunuh (Ctrl+C,
listrik padam) cukup jalankan perintah yang sama lagi. Tanggal yang sedang
dikerjakan saat mati diulang dari awal; semua tulisan idempoten.

Skrip memegang advisory lock ``hydromet`` selama berjalan, sehingga job
harian scheduler tidak berjalan bersamaan (job itu tercatat SKIPPED_LOCKED).
Butuh NASA_EARTHDATA_TOKEN di .env. Terkoneksi sebagai monitor_etl.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def run(db, date_from: date, date_to: date, *, modis: bool = True, fetchers=None,
        dry_run: bool = False, echo=print) -> dict:
    """Inti skrip (dipakai juga tes pemulihan). Mengembalikan ringkasan status."""
    from etl import hydromet_job as hj
    from etl.advisory_lock import advisory_lock

    summary = {"COMPLETED": 0, "WAITING_UPSTREAM": 0, "FAILED": 0, "skipped_done": 0, "locked": False}
    with advisory_lock(db, "hydromet") as got:
        if not got:
            summary["locked"] = True
            echo("[SKIP] another worker holds the 'hydromet' lock (scheduler or another backfill)")
            return summary
        pending = hj.pending_dates(db, date_from, date_to)
        total = (date_to - date_from).days + 1
        summary["skipped_done"] = total - len(pending)
        echo(f"[INFO] {total} days in range, {summary['skipped_done']} already COMPLETED, {len(pending)} to do")
        if dry_run:
            for d in pending:
                echo(f"  {d}")
            return summary
        if fetchers is None:
            fetchers = hj.Fetchers() if modis else hj.Fetchers(modis=None)
        ctx = hj.context(db)
        for i, d in enumerate(pending, 1):
            t0 = time.monotonic()
            res = hj.run_day(db, d, fetchers=fetchers, ctx=ctx)
            summary[res.status] = summary.get(res.status, 0) + 1
            echo(f"[{i}/{len(pending)}] {d} {res.status} ({time.monotonic() - t0:.0f}s) {res.message}")
    return summary


def main(argv: list[str]) -> int:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    from etl.database_client import DatabaseClient

    parser = argparse.ArgumentParser(description="Resumable Hydromet backfill (one UTC day at a time)")
    parser.add_argument("--from", dest="date_from", type=date.fromisoformat, required=True)
    parser.add_argument("--to", dest="date_to", type=date.fromisoformat, required=True)
    parser.add_argument("--no-modis", action="store_true", help="GPM only (faster; MODIS can be filled later)")
    parser.add_argument("--dry-run", action="store_true", help="list the dates that would be processed")
    args = parser.parse_args(argv)
    if args.date_to < args.date_from:
        print("[FAIL] --to must not be before --from")
        return 2
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    db = DatabaseClient.from_env("etl")
    try:
        summary = run(db, args.date_from, args.date_to, modis=not args.no_modis, dry_run=args.dry_run)
    except KeyboardInterrupt:
        print("\n[STOP] interrupted; run the same command again to resume")
        return 130
    finally:
        db.dispose()
    print(f"[DONE] {summary}")
    return 3 if summary["locked"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
