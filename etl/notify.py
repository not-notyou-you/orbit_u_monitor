# etl/notify.py
"""Peringatan email kondisi tidak normal per kecamatan (M64).

Dipanggil di akhir job Hidromet harian dan siklus Live (etl/scheduler.py),
setelah data barunya tersimpan. Satu putaran:

1. penerima = notify_recipients(): akun aktif dengan email yang lolos
   pengecekan dan minimal satu kecamatan langganan;
2. kondisi tiap kecamatan langganan dihitung dengan aturan yang SAMA dengan
   Beranda (etl/lokasi_data.py + etl/lokasi_interpret.py);
3. butir "tidak normal" dikirim bila tanggal datanya baru (paling lama
   app_settings notify.max_age_days, supaya backfill tanggal lampau tidak
   memicu email) dan belum ada di notify_sent untuk pengguna itu. Kondisi
   yang sama pada data baru tetap dikirim; data yang sama tidak pernah dua kali;
4. satu email per pengguna, semua kecamatan pilihannya digabung, maksimal
   MAIL_MAX_PER_RUN email per putaran.

Kegagalan mengirim ke satu pengguna dicatat (EMAIL_ALERT_FAILED) dan tidak
menghentikan yang lain; butirnya tidak dicatat terkirim sehingga dicoba lagi
di putaran berikutnya selama datanya masih dalam jendela.

CLI:
    python -m etl.notify --once            # satu putaran sekarang
    python -m etl.notify --once --to-file  # tulis .eml ke logs/mail, tanpa mengirim
    python -m etl.notify --test you@example.org
"""
from __future__ import annotations

import argparse
import json
import logging
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text

from etl import band_catalog as bc
from etl import lokasi_data as ld
from etl.mailer import MailConfig, MailError, build_message, send
from etl.notify_email import IMAGE_KEYS, alert_message, confirmation_message

logger = logging.getLogger(__name__)

MAX_IMAGES_PER_REGION = 3


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _log(db, user_id: int | None, action: str, detail: dict) -> None:
    try:
        with db.session() as s:
            s.execute(text("""INSERT INTO user_activity_logs (user_id, action, target_type, detail)
                              VALUES (:u, :a, 'notify', CAST(:d AS jsonb))"""),
                      {"u": user_id, "a": action, "d": json.dumps(detail, default=str)})
    except Exception:
        logger.exception("[NOTIFY] gagal mencatat %s", action)


def _images(db, sess, rid: int, items: list[dict], cache: dict) -> tuple[list, object]:
    """[(cid, key, label, png)] untuk butir-butir ini + tanggal scene."""
    if rid not in cache:
        try:
            cache[rid] = ld.scene(sess, db, rid, base_tables=True)
        except Exception:
            logger.exception("[NOTIFY] scene kecamatan %s tidak terbaca", rid)
            cache[rid] = None
    scene = cache[rid]
    if scene is None:
        return [], None
    present = ((scene["previews"] or {}).get("items") or {})
    keys: list[str] = []
    for it in items:
        for k in IMAGE_KEYS.get(it["key"], ()):
            if k in present and k not in keys:
                keys.append(k)
    out = []
    for k in keys[:MAX_IMAGES_PER_REGION]:
        try:
            path, _why = ld.cropped_preview(sess, db, rid, scene, k)
            png = path.read_bytes() if path is not None else None
        except Exception:      # satu gambar rusak tidak boleh menggagalkan putaran
            logger.exception("[NOTIFY] potongan %s kecamatan %s gagal", k, rid)
            png = None
        if png:
            out.append((f"r{rid}_{k}", k, f"{present[k].get('label') or k} · {scene['scene_date']}", png))
    return out, scene["scene_date"]


def run(db, *, source: str = "manual", cfg: MailConfig | None = None, today: date | None = None) -> dict:
    """Satu putaran notifikasi, di bawah kunci 'notify': dua putaran bersamaan
    (scheduler + tombol Admin) bisa mengirim butir yang sama dua kali, karena
    notify_sent baru ditulis setelah email terkirim. Menunggu sampai 10 menit."""
    from etl.advisory_lock import advisory_lock
    with advisory_lock(db, "notify", wait_seconds=600, poll_seconds=5) as got:
        if not got:
            return {"status": "SKIPPED_LOCKED"}
        return _run(db, source=source, cfg=cfg, today=today)


def _run(db, *, source, cfg, today) -> dict:
    from etl.settings import read_setting
    cfg = cfg or MailConfig.from_env()
    if not read_setting(db, "notify.enabled"):
        return {"status": "DISABLED"}
    if not cfg.configured:
        return {"status": "NOT_CONFIGURED"}
    today = today or _today()
    max_age = int(read_setting(db, "notify.max_age_days"))
    cutoff = today - timedelta(days=max_age)

    with db.session() as s:
        recipients = [dict(r) for r in s.execute(text("SELECT * FROM notify_recipients()")).mappings()]
    if not recipients:
        return {"status": "OK", "recipients": 0, "sent": 0, "failed": 0}
    wanted = sorted({rid for r in recipients for rid in r["region_ids"]})

    ld.sync_thresholds(db)
    sent = failed = 0
    with db.session() as s:
        conds = ld.conditions(s, wanted)
        done = set(s.execute(text("""SELECT user_id, region_id, item_key, data_date FROM notify_sent
                                     WHERE data_date >= :d"""), {"d": cutoff}).all())
        units = dict(s.execute(text("SELECT band_code, unit FROM spectral_bands")).all())
        fresh = {rid: [a for a in c["abnormal"] if a.get("date") and a["date"] >= cutoff]
                 for rid, c in conds.items()}
        scenes: dict = {}
        image_cache: dict = {}

        for u in recipients:
            if sent >= cfg.max_per_run:
                logger.warning("[NOTIFY] batas MAIL_MAX_PER_RUN=%s tercapai; sisanya di putaran berikutnya",
                               cfg.max_per_run)
                break
            blocks = []
            for rid in u["region_ids"]:
                items = [a for a in fresh.get(rid, [])
                         if (u["user_id"], rid, a["key"], a["date"]) not in done]
                if not items:
                    continue
                c = conds[rid]
                if rid not in image_cache:
                    image_cache[rid] = _images(db, s, rid, fresh[rid], scenes)
                imgs, scene_date = image_cache[rid]
                # Hanya gambar yang menjelaskan butir untuk pengguna ini.
                own = {k for it in items for k in IMAGE_KEYS.get(it["key"], ())}
                blocks.append({"region": c["region"], "status": c["status"], "items": items,
                               "latest": c["latest"], "prev": c["prev"], "ranges": c["ranges"],
                               "scene_date": scene_date,
                               "images": [i for i in imgs if i[1] in own]})
            if not blocks:
                continue
            name = u["full_name"] or u["username"]
            subject, body_t, body_h, images = alert_message(name, blocks, cfg, units, bc.thresholds)
            summary = {"source": source, "regions": [b["region"]["name"] for b in blocks],
                       "items": [{"region_id": b["region"]["region_id"], "key": i["key"], "date": i["date"]}
                                 for b in blocks for i in b["items"]]}
            try:
                where = send(cfg, build_message(cfg, u["email"], subject, body_t, body_h, images))
            except MailError as exc:
                failed += 1
                logger.warning("[NOTIFY] kirim ke user %s gagal: %s", u["user_id"], exc.detail)
                _log(db, u["user_id"], "EMAIL_ALERT_FAILED", {**summary, "error": exc.code, "detail": exc.detail})
                continue
            sent += 1
            with db.session() as w:
                for b in blocks:
                    for i in b["items"]:
                        w.execute(text("""INSERT INTO notify_sent (user_id, region_id, item_key, data_date, level)
                                          VALUES (:u, :r, :k, :d, :l) ON CONFLICT DO NOTHING"""),
                                  {"u": u["user_id"], "r": b["region"]["region_id"], "k": i["key"],
                                   "d": i["date"], "l": min(2, max(1, int(i["level"])))})
            _log(db, u["user_id"], "EMAIL_ALERT_SENT", {**summary, "subject": subject,
                                                         "backend": "file" if cfg.backend == "file" else "smtp"})
            logger.info("[NOTIFY] peringatan terkirim ke user %s (%s) via %s", u["user_id"],
                        ", ".join(summary["regions"]), where)
    return {"status": "OK", "recipients": len(recipients), "sent": sent, "failed": failed}


def run_quietly(db, source: str) -> dict:
    """Untuk scheduler: notifikasi tidak boleh menggagalkan job datanya."""
    try:
        res = run(db, source=source)
        logger.info("[NOTIFY] %s: %s", source, res)
        return res
    except Exception as exc:
        logger.exception("[NOTIFY] putaran %s gagal", source)
        return {"status": "FAILED", "error": str(exc)}


def send_test(to: str, name: str, cfg: MailConfig | None = None) -> str:
    """Email uji (tombol Admin): isinya sama dengan email konfirmasi."""
    cfg = cfg or MailConfig.from_env()
    subject, body_t, body_h = confirmation_message(name, to, cfg)
    return send(cfg, build_message(cfg, to, "[UJI] " + subject, body_t, body_h))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Peringatan email kondisi tidak normal (M64)")
    p.add_argument("--once", action="store_true", help="jalankan satu putaran sekarang")
    p.add_argument("--to-file", action="store_true", help="tulis .eml ke LOGS_DIR/mail, jangan kirim")
    p.add_argument("--test", metavar="EMAIL", help="kirim email uji ke alamat ini")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg = MailConfig.from_env()
    if a.to_file:
        cfg = replace(cfg, backend="file")
    if a.test:
        print(send_test(a.test, "Penguji", cfg))
        return 0
    if a.once:
        from etl.database_client import DatabaseClient
        print(run(DatabaseClient.from_env("etl"), source="cli", cfg=cfg))
        return 0
    p.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
