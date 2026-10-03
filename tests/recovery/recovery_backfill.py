#!/usr/bin/env python
"""Helper tests/recovery/kill_and_resume.sh: backfill hidromet tiruan yang bisa dibunuh di tengah.

    python tests/recovery/recovery_backfill.py setup
    python tests/recovery/recovery_backfill.py run   --from 2024-01-01 --to 2024-01-10 --delay 1.0
    python tests/recovery/recovery_backfill.py check --from 2024-01-01 --to 2024-01-10 [--expect-partial]

Selalu memakai database UJI (``*_test``, sama dengan pytest) dan membangun
ulang skemanya pada ``setup``. Pengambil GPM/MODIS diganti raster sintetis
yang ditulis lewat atomic_path, dengan jeda per tanggal supaya proses bisa
dibunuh (kill -9) saat tanggal sedang dikerjakan.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from tests.conftest import (  # noqa: E402
    SYNTH_GRID, SYNTH_KECAMATAN, TEST_DB_URL, _guard_not_production, _reset_schema,
)

WORK = ROOT / "tests" / "recovery" / "_work"
N_GPM_BANDS = 4


def _client():
    from etl.database_client import DatabaseClient
    _guard_not_production(TEST_DB_URL)
    return DatabaseClient(TEST_DB_URL, pool_size=2, max_overflow=2)


def setup() -> None:
    from shapely.geometry import box

    from database.apply_schema import apply_files, set_role_passwords
    from etl import regions as rg

    db = _client()
    _reset_schema(db)
    raw = db._engine.raw_connection()
    try:
        apply_files(raw.driver_connection, echo=lambda _m: None)
        set_role_passwords(raw.driver_connection, echo=lambda _m: None)
    finally:
        raw.close()
    feats = [rg.RegionFeature("TST00", "Kabupaten Uji", 2, None, box(105.9, -7.0, 106.5, -6.4).wkb_hex)]
    feats += [rg.RegionFeature(p, p, 3, "TST00", box(*b).wkb_hex) for p, b in SYNTH_KECAMATAN.items()]
    with db.session() as sess:
        rg.upsert_regions(sess, feats, source_dataset="uji pemulihan")
        rg.set_aoi(sess, rg.resolve_kecamatan(sess, list(SYNTH_KECAMATAN)))
        rg.rebuild_monitor_aoi(sess)
    db.dispose()
    print("[setup] test database rebuilt with 3 synthetic kecamatan")


def _fetchers(delay: float):
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin

    from etl import hydromet_job as hj
    from etl.atomic_write import atomic_path

    def gpm(ctx, d, rebuild):
        layers = []
        for i, (window, band) in enumerate(hj.GPM_BANDS.items()):
            out = WORK / f"{d:%Y%m%d}" / f"gpm_rain_{window}.tif"
            if not out.exists():
                g = SYNTH_GRID
                with atomic_path(out) as tmp, rasterio.open(
                        tmp, "w", driver="GTiff", height=4, width=4, count=1, dtype="float32", crs="EPSG:4326",
                        transform=from_origin(g["x0"], g["y0"], g["res"], g["res"]), nodata=-9999.9) as dst:
                    dst.write(np.full((4, 4), float(d.day) * (i + 1), dtype="float32"), 1)
                    # Jeda DI TENGAH penulisan: kill -9 di sini meninggalkan
                    # berkas .tmp, bukan berkas final yang separuh jadi.
                    time.sleep(delay / N_GPM_BANDS)
            layers.append(hj.Layer(band, out, "L", None))
        return layers

    return hj.Fetchers(gpm=gpm, modis=None)


def run(date_from: date, date_to: date, delay: float) -> None:
    from etl.hydromet_job import backfill
    db = _client()
    try:
        backfill(db, date_from, date_to, fetchers=_fetchers(delay), echo=lambda m: print(m, flush=True))
    finally:
        db.dispose()


def check(date_from: date, date_to: date, expect_partial: bool) -> int:
    from sqlalchemy import text

    from etl import hydromet_job as hj
    db = _client()
    n_days = (date_to - date_from).days + 1
    with db.session() as sess:
        dup = sess.scalar(text("""SELECT count(*) FROM (SELECT date_range_start FROM dataset_jobs
                                  WHERE job_type = 'HYDROMET_DAILY' GROUP BY 1 HAVING count(*) > 1) q"""))
        done = sess.scalar(text("""SELECT count(*) FROM dataset_jobs WHERE job_type = 'HYDROMET_DAILY'
                                   AND status = 'COMPLETED' AND date_range_start BETWEEN :a AND :b"""),
                           {"a": date_from, "b": date_to})
        obs = sess.scalar(text("SELECT count(*) FROM region_observations WHERE obs_date BETWEEN :a AND :b"),
                          {"a": date_from, "b": date_to})
        bad_obs = sess.scalar(text("""SELECT count(*) FROM region_observations o JOIN spectral_bands b USING (band_id)
                                      WHERE b.band_code = 'RAIN_24H' AND o.value <> extract(day FROM o.obs_date)"""))
    pending = hj.pending_dates(db, date_from, date_to)
    db.dispose()
    finals = list(WORK.rglob("*.tif"))
    print(f"[check] completed={done}/{n_days} pending={len(pending)} observations={obs} "
          f"duplicate_job_dates={dup} wrong_values={bad_obs} final_tifs={len(finals)}")
    ok = dup == 0 and bad_obs == 0 and obs == done * len(SYNTH_KECAMATAN) * N_GPM_BANDS or (
        expect_partial and dup == 0 and bad_obs == 0)
    for f in finals:     # berkas final harus utuh (bisa dibuka), tidak pernah separuh jadi
        import rasterio
        with rasterio.open(f) as src:
            src.read(1)
    if expect_partial:
        ok = ok and 0 < done < n_days
    else:
        ok = ok and done == n_days and not pending
    print("[check] OK" if ok else "[check] FAILED")
    return 0 if ok else 1


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["setup", "run", "check"])
    p.add_argument("--from", dest="date_from", type=date.fromisoformat, default=date(2024, 1, 1))
    p.add_argument("--to", dest="date_to", type=date.fromisoformat, default=date(2024, 1, 10))
    p.add_argument("--delay", type=float, default=1.0)
    p.add_argument("--expect-partial", action="store_true")
    a = p.parse_args(argv)
    if a.cmd == "setup":
        import shutil
        shutil.rmtree(WORK, ignore_errors=True)
        setup()
        return 0
    if a.cmd == "run":
        run(a.date_from, a.date_to, a.delay)
        return 0
    return check(a.date_from, a.date_to, a.expect_partial)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
