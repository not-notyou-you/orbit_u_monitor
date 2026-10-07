"""Audit ulang scene Live yang sudah terlanjur diunduh, terhadap gerbang
kelengkapan AOI (etl/aoi_coverage.py).

Gerbang itu baru ada sekarang, jadi scene yang dibuat sebelumnya tidak pernah
diuji: sebagian di antaranya hanya menutup sepotong AOI karena orbitnya cuma
menyerempet (AOI GMLS: ~30% vs ~99% untuk orbit yang melintas penuh). Skrip ini
memberi perlakuan yang akan diberikan gerbang itu seandainya sudah ada:

  cakupan < live.min_aoi_coverage -> berkasnya dihapus, barisnya ditandai
      INCOMPLETE. Bukan dicoba ulang: pada tanggal itu Sentinel-1 memang tidak
      melewati sisa AOI, jadi mengunduh ulang menghasilkan potongan yang sama.

  cakupan >= ambang -> preview dirender ULANG di grid tetap seluas AOI. Scene
      lama dirender di grid turunan footprint S1, jadi ukurannya berbeda-beda
      (768x633, 768x632, 438x768) dan tidak setumpuk antar tanggal. Isinya
      tidak berubah -- perendernya sama persis, yang berganti cuma bingkainya.

Idempoten: menjalankannya dua kali tidak mengubah apa pun pada jalan kedua.

    python -m scripts.repair_incomplete_scenes [--area 1] [--dry-run]

Prasyarat: batas wilayah sudah dimuat (scripts/load_regions.py), sama seperti
scripts/backfill_admin_overlay.py -- kalau belum, varian garis wilayah tidak
ikut ditulis dan skrip berhenti daripada diam-diam menghasilkan preview tanpa
garis.
"""
from __future__ import annotations

import argparse
import logging
import sys

from sqlalchemy import select

from etl import admin_overlay
from etl import aoi_coverage as aoi_cov
from etl import live_metrics as lmx
from etl.database_client import DatabaseClient, LiveArea, LiveScene
from etl.live_cycle import water_change_stage
from etl.live_monitor import LiveMonitor, _LiveFiles
from etl.live_preview import render_scene_previews

logger = logging.getLogger("repair_incomplete_scenes")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--area", type=int, help="Hanya satu area_id")
    ap.add_argument("--dry-run", action="store_true",
                    help="Hanya laporkan cakupan tiap scene, tidak mengubah apa pun")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    db = DatabaseClient.from_env("etl")
    regions = admin_overlay.load_regions(db)
    if not regions:
        print("Batas wilayah belum ada di administrative_regions — jalankan "
              "scripts/load_regions.py dulu.", file=sys.stderr)
        return 2

    mon = LiveMonitor(db)
    with db.session() as sess:
        min_cov = aoi_cov.min_coverage(sess)
        areas = {a.area_id: (a.dataset_id, a.bbox_wkt)
                 for a in sess.scalars(select(LiveArea)).all()}
        # FAILED ikut diperiksa, bukan cuma READY/PARTIAL: baris FAILED tidak
        # pernah tersapu enforce_retention (yang hanya menghitung
        # READY/PARTIAL), jadi COG-nya menginap selamanya. Kalau cakupannya
        # memang di bawah ambang, berkas itu tidak akan pernah berguna dan
        # dibersihkan di sini. FAILED yang cakupannya baik tidak disentuh --
        # gagalnya karena sebab lain dan masih dalam jatah percobaan ulang.
        q = select(LiveScene).where(LiveScene.deleted_at.is_(None),
                                    LiveScene.status.in_(("READY", "PARTIAL", "FAILED")))
        if args.area:
            q = q.where(LiveScene.area_id == args.area)
        scenes = [(s.area_id, s.scene_date, s.status)
                  for s in sess.scalars(q.order_by(LiveScene.scene_date)).all()]

    print(f"Ambang cakupan AOI: {min_cov * 100:.0f}% — {len(scenes)} scene diperiksa.\n")

    rejected = rerendered = skipped = failed = 0
    for area_id, scene_date, status in scenes:
        dataset_id, bbox_wkt = areas.get(area_id, (None, None))
        info = mon._dataset_info(dataset_id)
        if info is None or not bbox_wkt:
            logger.warning("area %s: dataset atau AOI tidak ada, dilewati", area_id)
            skipped += 1
            continue
        try:
            files = _LiveFiles(*info)
            inputs = lmx.scene_inputs(files.root, scene_date)
            coverage = aoi_cov.scene_coverage(inputs.get("s1"), bbox_wkt)
            if coverage is None:
                # Raster S1 sudah kena retensi: tanpa piksel tidak ada yang
                # bisa diukur maupun dirender ulang. Dibiarkan apa adanya.
                print(f"  area {area_id} · {scene_date}: raster S1 sudah tidak ada — dilewati")
                skipped += 1
                continue

            if coverage >= min_cov and status == "FAILED":
                print(f"  area {area_id} · {scene_date}: cakupan {coverage * 100:5.1f}%  "
                      f"FAILED karena sebab lain — tidak disentuh")
                skipped += 1
                continue
            verdict = "TOLAK" if coverage < min_cov else "ok"
            print(f"  area {area_id} · {scene_date}: cakupan {coverage * 100:5.1f}%  {verdict}")
            if args.dry_run:
                rejected += verdict == "TOLAK"
                rerendered += verdict == "ok"
                continue

            if coverage < min_cov:
                mon.delete_scene(area_id, scene_date,
                                 reason=f"AOI coverage {coverage * 100:.1f}% below "
                                        f"{min_cov * 100:.0f}%")
                with db.session() as sess:
                    row = sess.scalar(select(LiveScene).where(
                        LiveScene.area_id == area_id, LiveScene.scene_date == scene_date))
                    if row is not None:
                        row.status = "INCOMPLETE"
                        src = dict(row.source_status or {})
                        s1 = dict(src.get("sentinel1") or {})
                        s1.update({"status": "INCOMPLETE",
                                   "aoi_coverage": round(coverage, 4),
                                   "aoi_coverage_min": min_cov})
                        src["sentinel1"] = s1
                        row.source_status = src
                rejected += 1
                continue

            result = render_scene_previews(files, scene_date, inputs, regions,
                                           bbox_wkt=bbox_wkt)
            items = result.get("items") or {}
            if not items:
                logger.warning("area %s %s: tidak ada raster sumber lagi, dilewati",
                               area_id, scene_date)
                skipped += 1
                continue
            with db.session() as sess:
                row = sess.scalar(select(LiveScene).where(
                    LiveScene.area_id == area_id, LiveScene.scene_date == scene_date))
                previews = dict(row.previews or {})
                merged = dict(previews.get("items") or {})
                merged.update({k: {**merged.get(k, {}), **v} for k, v in items.items()})
                previews["items"] = merged
                if result.get("grid"):
                    previews["grid"] = result["grid"]
                row.previews = previews
                src = dict(row.source_status or {})
                s1 = dict(src.get("sentinel1") or {})
                s1.update({"aoi_coverage": round(coverage, 4), "aoi_coverage_min": min_cov})
                src["sentinel1"] = s1
                row.source_status = src
            # PNG perubahan air punya jalur sendiri dan harus ikut pindah ke
            # grid baru, kalau tidak ia jadi satu-satunya tile yang tidak
            # setumpuk dengan yang lain. Tahapnya idempoten.
            try:
                water_change_stage(mon, area_id, scene_date, files, inputs)
            except Exception:
                logger.exception("area %s %s: tahap perubahan air gagal", area_id, scene_date)
            rerendered += 1
        except Exception:
            logger.exception("area %s %s gagal", area_id, scene_date)
            failed += 1

    verb = "akan " if args.dry_run else ""
    print(f"\nSelesai: {rejected} scene {verb}ditolak (INCOMPLETE), "
          f"{rerendered} {verb}dirender ulang, {skipped} dilewati, {failed} gagal.")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
