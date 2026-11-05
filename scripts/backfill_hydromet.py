#!/usr/bin/env python
"""Backfill Job Hidromet per tanggal UTC, berurutan dan bisa dilanjutkan (PIPELINE.md §10 langkah 6)."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def run(db, date_from: date, date_to: date, **kwargs) -> dict:
    """Lihat etl.hydromet_job.backfill (dipakai juga POST /admin/ingest)."""
    from etl.hydromet_job import backfill
    return backfill(db, date_from, date_to, **kwargs)


def main(argv: list[str]) -> int:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    from etl.database_client import DatabaseClient

    parser = argparse.ArgumentParser(description="Resumable Hydromet backfill (one UTC day at a time)")
    parser.add_argument("--from", dest="date_from", type=date.fromisoformat, required=True)
    parser.add_argument("--to", dest="date_to", type=date.fromisoformat, required=True)
    parser.add_argument("--no-modis", action="store_true", help="GPM only (faster; MODIS can be filled later)")
    parser.add_argument("--dry-run", action="store_true", help="list the dates that would be processed")
    parser.add_argument("--max-consecutive-failures", type=int, default=5, metavar="N",
                        help="stop after N consecutive FAILED days (0 = never stop; default 5). "
                             "Guards against a network outage burning through the whole range.")
    args = parser.parse_args(argv)
    if args.max_consecutive_failures < 0:
        print("[FAIL] --max-consecutive-failures must not be negative")
        return 2
    if args.date_to < args.date_from:
        print("[FAIL] --to must not be before --from")
        return 2
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    db = DatabaseClient.from_env("etl")
    try:
        summary = run(db, args.date_from, args.date_to, modis=not args.no_modis,
                      dry_run=args.dry_run,
                      max_consecutive_failures=args.max_consecutive_failures)
    except KeyboardInterrupt:
        print("\n[STOP] interrupted; run the same command again to resume")
        return 130
    finally:
        db.dispose()
    print(f"[DONE] {summary}")
    if summary["locked"]:
        return 3
    return 4 if summary.get("aborted_after") else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
