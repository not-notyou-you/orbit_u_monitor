"""Isi varian "garis wilayah" ({key}_adm.png) untuk scene Live yang sudah ada.

Varian itu baru ikut dirender sejak etl/admin_overlay.py ada, jadi scene yang
sudah terlanjur jadi hanya punya PNG polos dan checkbox "Garis wilayah" di
taskbar tidak berpengaruh untuknya. Skrip ini me-render ULANG preview scene
tersebut dari COG yang masih tersimpan -- hasil polosnya identik (perendernya
sama persis), yang bertambah hanya berkas _adm.png dan field "file_adm" di
live_scenes.previews.

Scene yang COG Sentinel-1 nya sudah dibersihkan retensi dilewati: tanpa raster
sumber, tidak ada grid untuk menempatkan garis wilayahnya.

    python -m scripts.backfill_admin_overlay [--area 1] [--limit 50] [--dry-run]

Prasyarat: batas wilayah sudah dimuat (scripts/load_regions.py), kalau belum
skrip berhenti dengan pesan -- bukan menulis preview tanpa garis diam-diam.
"""
from __future__ import annotations

import argparse
import logging
import sys

from sqlalchemy import select

from etl import admin_overlay
from etl import live_metrics as lmx
from etl.database_client import DatabaseClient, LiveArea, LiveScene
from etl.live_cycle import water_change_stage
from etl.live_monitor import LiveMonitor, _LiveFiles
from etl.live_preview import render_scene_previews

logger = logging.getLogger("backfill_admin_overlay")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--area", type=int, help="Hanya satu area_id")
    ap.add_argument("--limit", type=int, default=0, help="Maksimum scene (0 = semua)")
    ap.add_argument("--all", action="store_true",
                    help="Termasuk scene yang varian _adm nya sudah ada (render ulang)")
    ap.add_argument("--dry-run", action="store_true", help="Hanya daftar scene yang akan dikerjakan")
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
        q = select(LiveScene).where(LiveScene.deleted_at.is_(None),
                                    LiveScene.status.in_(("READY", "PARTIAL")))
        if args.area:
            q = q.where(LiveScene.area_id == args.area)
        scenes = [(s.area_id, s.scene_date, dict(s.previews or {}))
                  for s in sess.scalars(q.order_by(LiveScene.scene_date.desc())).all()]
        areas = {a.area_id: a.dataset_id for a in sess.scalars(select(LiveArea)).all()}

    todo = [s for s in scenes
            if args.all or not all(v.get("file_adm") for v in (s[2].get("items") or {}).values())]
    if args.limit:
        todo = todo[:args.limit]
    print(f"{len(todo)} scene akan dikerjakan (dari {len(scenes)} scene siap).")
    if args.dry_run:
        for area_id, d, _ in todo:
            print(f"  area {area_id} · {d}")
        return 0

    done = failed = 0
    for area_id, scene_date, _ in todo:
        info = mon._dataset_info(areas.get(area_id))
        if info is None:
            logger.warning("area %s: dataset tidak ada, dilewati", area_id)
            failed += 1
            continue
        try:
            files = _LiveFiles(*info)
            inputs = lmx.scene_inputs(files.root, scene_date)
            result = render_scene_previews(files, scene_date, inputs, regions)
            items = result.get("items") or {}
            if not items:
                logger.warning("area %s %s: tidak ada raster sumber lagi, dilewati",
                               area_id, scene_date)
                failed += 1
                continue
            with db.session() as sess:
                row = sess.scalar(select(LiveScene).where(
                    LiveScene.area_id == area_id, LiveScene.scene_date == scene_date))
                previews = dict(row.previews or {})
                merged = dict(previews.get("items") or {})
                # Hanya lapisan yang baru saja dirender yang ditimpa: entri
                # lain (mis. s1_water_change, yang bukan milik modul ini)
                # harus tetap apa adanya.
                merged.update({k: {**merged.get(k, {}), **v} for k, v in items.items()})
                previews["items"] = merged
                # Render ulang ini juga menghasilkan georeferensi grid, dan
                # PNG-nya baru ditulis dari grid itu -- jadi keduanya pasti
                # cocok. Menyimpannya di sini membuat halaman Relief 3D ikut
                # terisi tanpa perlu scripts.backfill_preview_grid menyusul.
                if result.get("grid"):
                    previews["grid"] = result["grid"]
                row.previews = previews
            # Tile "Perubahan air" bukan milik live_preview: dirender jalur
            # water_change. Tahapnya idempoten (metrik diganti, PNG ditimpa),
            # jadi dijalankan ulang untuk mendapat varian garis wilayahnya.
            try:
                water_change_stage(mon, area_id, scene_date, files, inputs)
            except Exception:
                logger.exception("area %s %s: tahap perubahan air gagal", area_id, scene_date)
            n = sum(1 for v in items.values() if v.get("file_adm"))
            logger.info("area %s %s: %d/%d varian garis wilayah", area_id, scene_date, n, len(items))
            done += 1
        except Exception:
            logger.exception("area %s %s gagal", area_id, scene_date)
            failed += 1

    print(f"Selesai: {done} scene diperbarui, {failed} dilewati/gagal.")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
