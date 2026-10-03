#!/usr/bin/env python
"""Muat batas COD-AB Kabupaten Lebak dan tandai AOI GMLS (PIPELINE.md §10, langkah 2–4 dan 8).

Pakai:
    python scripts/load_regions.py
    python scripts/load_regions.py --aoi "Bayah,Panggarangan,Cihara,..."
    python scripts/load_regions.py --aoi-only --aoi "ID3602030,ID3602020"
    python scripts/load_regions.py --adm2 path/idn_admin2.shp --adm3 path/idn_admin3.shp

Langkah:
  1. adm2 + adm3 dengan ADM2_PCODE Lebak -> administrative_regions (upsert per
     pcode, ST_Multi(ST_MakeValid)). in_aoi yang sudah ada tidak diubah.
  2. --aoi: kecamatan (nama atau pcode) yang in_aoi; sisanya false.
  3. ROI AOI GMLS (is_monitor_aoi) + ROI per kecamatan AOI + dataset sistem
     HYDROMET_AOI dibangun ulang dari kecamatan in_aoi.
  4. Live Area default ("Lebak Selatan", app_settings) dibuat bila belum ada
     area untuk ROI AOI. Backfill-nya dimulai scheduler saat API berjalan
     (status BACKFILLING dilanjutkan otomatis), bukan oleh skrip ini.

Terkoneksi sebagai pemilik skema (DB_USER), seperti skrip setup lain.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def ensure_default_live_area(db, roi_id: int) -> int | None:
    """Buat Live Area default untuk ROI AOI bila belum ada (tanpa memulai siklus)."""
    from sqlalchemy import text

    from etl.live_monitor import LiveMonitor
    from etl.settings import get_setting

    with db.session() as sess:
        existing = sess.scalar(text("SELECT area_id FROM live_areas WHERE region_id = :r AND deleted_at IS NULL"),
                               {"r": roi_id})
        name = get_setting(sess, "live.default_area_name")
        retention = get_setting(sess, "live.retention_default")
    if existing:
        return None
    area = LiveMonitor(db).create_area(roi_id, name=name, retention=retention, start=False)
    return area["area_id"]


def main(argv: list[str]) -> int:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    from etl import regions
    from etl.database_client import DatabaseClient

    parser = argparse.ArgumentParser(description="Load COD-AB boundaries for Kabupaten Lebak and mark the GMLS AOI")
    parser.add_argument("--adm2", type=Path, default=regions.DEFAULT_COD_AB_DIR / "idn_admin2.shp")
    parser.add_argument("--adm3", type=Path, default=regions.DEFAULT_COD_AB_DIR / "idn_admin3.shp")
    parser.add_argument("--adm2-pcode", default=regions.LEBAK_ADM2_PCODE)
    parser.add_argument("--aoi", help="comma-separated kecamatan names or P-codes that form the GMLS AOI")
    parser.add_argument("--aoi-only", action="store_true", help="skip loading shapefiles; only (re)mark the AOI")
    parser.add_argument("--no-live-area", action="store_true", help="do not create the default Live Area")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    features = []
    if not args.aoi_only:
        for p in (args.adm2, args.adm3):
            if not p.exists():
                print(f"[FAIL] shapefile not found: {p}")
                return 2
        features = (regions.read_cod_ab(args.adm2, 2, args.adm2_pcode)
                    + regions.read_cod_ab(args.adm3, 3, args.adm2_pcode))

    db = DatabaseClient.from_env("owner")
    try:
        with db.session() as sess:
            if features:
                counts = regions.upsert_regions(sess, features)
                print(f"[OK] administrative_regions: {counts['inserted']} new, {counts['updated']} updated "
                      f"({sum(f.admin_level == 3 for f in features)} kecamatan)")
            if args.aoi:
                ids = regions.resolve_kecamatan(sess, args.aoi.split(","))
                regions.set_aoi(sess, ids)
                print(f"[OK] in_aoi: {len(ids)} kecamatan")
            roi_id = regions.rebuild_monitor_aoi(sess)
        if roi_id is None:
            print("[INFO] no kecamatan is in_aoi yet; run again with --aoi to build the AOI ROI")
            return 0
        print(f"[OK] AOI ROI region_id={roi_id} ({regions.AOI_ROI_CODE}), dataset {regions.HYDROMET_DATASET_NAME} ready")
        if not args.no_live_area:
            area_id = ensure_default_live_area(db, roi_id)
            if area_id:
                print(f"[OK] default Live Area created (area_id={area_id}); backfill starts when the API runs")
    except ValueError as exc:
        print(f"[FAIL] {exc}")
        return 2
    finally:
        db.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
