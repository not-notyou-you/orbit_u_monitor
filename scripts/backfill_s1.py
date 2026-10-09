#!/usr/bin/env python
"""Backfill Sentinel-1 dataset utama: 1 tahun terakhir (M58).

Pakai:
    python scripts/backfill_s1.py                  # semua Live Area aktif, sampai jendela penuh
    python scripts/backfill_s1.py --area 1
    python scripts/backfill_s1.py --aggregate-only # hanya tulis ulang S1 per kecamatan
                                                   # dari scene yang berkasnya masih ada

Backfill adalah siklus Live biasa (etl/live_cycle.py): discovery melihat
seluruh jendela ``storage.raster_retention_days``, tanggal terbaru dikerjakan
lebih dulu per 3 tanggal, dan tiap scene yang lolos ditulis ke
region_observations (VV, VH, WATER_PCT). Siklus diulang sampai tidak ada
tanggal baru, jadi scene yang gagal sementara dicoba lagi (maks 3 kali).

Bisa dibunuh kapan saja: scene yang sudah READY tidak diunduh ulang; jalankan
perintah yang sama untuk melanjutkan. JobLock per area mencegah siklus
terjadwal di proses API mengerjakan area yang sama bersamaan (dilewati).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def aggregate_only(db, mon, area_ids: list[int]) -> int:
    from sqlalchemy import select

    from etl import live_metrics as lmx
    from etl import s1_observations
    from etl.database_client import LiveScene
    from etl.live_cycle import _area_files

    total = 0
    for area_id in area_ids:
        files = _area_files(mon, area_id)
        if files is None:
            continue
        with db.session() as sess:
            dates = sess.scalars(select(LiveScene.scene_date).where(
                LiveScene.area_id == area_id, LiveScene.deleted_at.is_(None),
                LiveScene.status.in_(("READY", "PARTIAL"))).order_by(LiveScene.scene_date)).all()
        for d in dates:
            n = s1_observations.record_scene(db, d, lmx.s1_frames(files.root, d))
            print(f"[S1OBS] area={area_id} {d}: {n} rows")
            total += n
    return total


def main(argv: list[str]) -> int:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    from etl.database_client import DatabaseClient
    from etl.live_monitor import LiveMonitor

    parser = argparse.ArgumentParser(description="Sentinel-1 2-year backfill via the Live cycle")
    parser.add_argument("--area", type=int, action="append", help="Live Area id (default: all enabled)")
    parser.add_argument("--aggregate-only", action="store_true",
                        help="only (re)write per-kecamatan S1 values for stored scenes")
    parser.add_argument("--max-cycles", type=int, default=20,
                        help="stop after N cycles even if dates remain (default 20)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    db = DatabaseClient.from_env("etl")
    mon = LiveMonitor(db)
    try:
        area_ids = args.area or [a["area_id"] for a in mon.list_areas() if a["enabled"]]
        if args.aggregate_only:
            print(f"[DONE] {aggregate_only(db, mon, area_ids)} rows written")
            from etl import forecast_store
            print(f"[FORECAST] {forecast_store.refresh(db)}")
            return 0
        from etl.live_cycle import backfill_s1
        print(f"[DONE] {backfill_s1(mon, area_ids, max_cycles=args.max_cycles)}")
    except KeyboardInterrupt:
        print("\n[STOP] interrupted; run the same command again to resume")
        return 130
    finally:
        db.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
