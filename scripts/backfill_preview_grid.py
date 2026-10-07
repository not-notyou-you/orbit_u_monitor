"""Isi georeferensi preview (`previews.grid`) untuk scene Live yang sudah ada.

Georeferensi empat sudut baru ikut dicatat sejak etl/live_preview.py
menyimpannya, jadi scene yang sudah terlanjur jadi tidak punya field itu.
Akibatnya halaman Relief 3D (`/app#kondisi/relief` dan `/relief`) tidak bisa
menempatkan citranya di atas DEM: versi masuk jatuh ke bbox daerah (posisi
perkiraan, dan mengatakannya), versi publik tidak punya jalan mundur sama
sekali. Skrip ini mengisinya untuk scene lama.

TIDAK me-render ulang PNG apa pun. Grid dihitung dari raster sumber yang masih
tersimpan -- cuma membaca metadata, jadi hitungan detik per scene, bukan menit.
Yang berubah hanya satu field JSON di live_scenes.previews.

PENJAGA UKURAN
Grid hasil hitung diperiksa terhadap ukuran PNG yang BENAR-BENAR ada di disk.
Kalau tidak sama, scene itu dilewati alih-alih ditulis: ukuran yang berbeda
berarti PNG-nya dirender dari susunan raster yang berbeda (mis. jumlah frame
Sentinel-1 berubah setelah scene itu dibuat), dan menulis grid baru ke PNG lama
akan menggeser citranya di peta tanpa ada yang menyadarinya. Scene seperti itu
perlu dirender ulang, bukan ditambal:

    python -m scripts.backfill_admin_overlay --area <id>

Scene yang COG Sentinel-1 nya sudah dibersihkan retensi juga dilewati -- tanpa
raster sumber tidak ada grid yang bisa dihitung.

    python -m scripts.backfill_preview_grid [--area 1] [--limit 50] [--dry-run] [--all]
"""
from __future__ import annotations

import argparse
import logging

from sqlalchemy import select

from etl import live_metrics as lmx
from etl import live_preview as lp
from etl.database_client import DatabaseClient, LiveArea, LiveScene
from etl.live_monitor import LiveMonitor, _LiveFiles

logger = logging.getLogger("backfill_preview_grid")


def _png_size(path):
    """(width, height) PNG, atau None kalau tidak terbaca."""
    from PIL import Image
    try:
        with Image.open(path) as img:
            return img.size
    except Exception:
        return None


def _existing_png(files, scene_date, items):
    """Satu PNG scene itu yang ada di disk -- pembanding ukuran. Varian garis
    wilayah tidak dipakai: ukurannya sama, tapi tidak semua scene punya."""
    pdir = files.preview_dir(scene_date)
    for item in items.values():
        name = item.get("file")
        if not name:
            continue
        p = pdir / name
        if p.is_file():
            return p
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--area", type=int, help="Hanya satu area_id")
    ap.add_argument("--limit", type=int, default=0, help="Maksimum scene (0 = semua)")
    ap.add_argument("--all", action="store_true",
                    help="Termasuk scene yang sudah punya previews.grid (hitung ulang)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Hanya daftar scene yang akan dikerjakan, tanpa menulis")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    db = DatabaseClient.from_env("etl")
    mon = LiveMonitor(db)
    with db.session() as sess:
        q = select(LiveScene).where(LiveScene.deleted_at.is_(None),
                                    LiveScene.status.in_(("READY", "PARTIAL")))
        if args.area:
            q = q.where(LiveScene.area_id == args.area)
        scenes = [(s.area_id, s.scene_date, dict(s.previews or {}))
                  for s in sess.scalars(q.order_by(LiveScene.scene_date.desc())).all()]
        areas = {a.area_id: a.dataset_id for a in sess.scalars(select(LiveArea)).all()}

    # Scene tanpa PNG sama sekali tidak ada yang bisa digeoreferensi.
    todo = [s for s in scenes
            if (s[2].get("items") or {}) and (args.all or not s[2].get("grid"))]
    if args.limit:
        todo = todo[:args.limit]
    print(f"{len(todo)} scene akan dikerjakan (dari {len(scenes)} scene siap).")
    if args.dry_run:
        for area_id, d, pv in todo:
            print(f"  area {area_id} · {d} · grid {'ADA' if pv.get('grid') else 'belum'}")
        return 0

    done = skipped = failed = 0
    for area_id, scene_date, previews in todo:
        info = mon._dataset_info(areas.get(area_id))
        if info is None:
            logger.warning("area %s: dataset tidak ada, dilewati", area_id)
            failed += 1
            continue
        try:
            files = _LiveFiles(*info)
            inputs = lmx.scene_inputs(files.root, scene_date)
            grid, why = lp.scene_grid(files, scene_date, inputs)
            if grid is None:
                logger.info("area %s %s: dilewati (%s)", area_id, scene_date, why)
                skipped += 1
                continue

            # Penjaga ukuran: grid ini harus milik PNG yang ada, bukan milik
            # susunan raster yang sekarang kebetulan ada di disk.
            png = _existing_png(files, scene_date, previews.get("items") or {})
            if png is None:
                logger.info("area %s %s: dilewati (PNG preview tidak ada di disk)",
                            area_id, scene_date)
                skipped += 1
                continue
            size = _png_size(png)
            if size != (grid.width, grid.height):
                logger.warning(
                    "area %s %s: DILEWATI -- grid %sx%s tidak cocok dengan %s (%s). "
                    "PNG-nya dirender dari susunan raster lain; render ulang dengan "
                    "scripts.backfill_admin_overlay, jangan ditambal.",
                    area_id, scene_date, grid.width, grid.height, png.name,
                    "x".join(map(str, size)) if size else "tidak terbaca")
                skipped += 1
                continue

            with db.session() as sess:
                row = sess.scalar(select(LiveScene).where(
                    LiveScene.area_id == area_id, LiveScene.scene_date == scene_date))
                pv = dict(row.previews or {})
                pv["grid"] = lp.grid_dict(grid)
                row.previews = pv
            logger.info("area %s %s: grid %sx%s %s", area_id, scene_date,
                        grid.width, grid.height, grid.crs)
            done += 1
        except Exception:
            logger.exception("area %s %s gagal", area_id, scene_date)
            failed += 1

    print(f"Selesai: {done} scene diisi, {skipped} dilewati, {failed} gagal.")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
