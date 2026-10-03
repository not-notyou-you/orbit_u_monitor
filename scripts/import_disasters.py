#!/usr/bin/env python
"""Impor catatan kejadian bencana dari CSV terstruktur (PIPELINE.md §10 langkah 7).

Pakai:
    python scripts/import_disasters.py kejadian.csv --username analis1
    python scripts/import_disasters.py kejadian.csv --username analis1 --dry-run

Format (UTF-8, baris pertama header; urutan kolom bebas):

    tanggal,tanggal_selesai,jenis,kecamatan,desa,lat,lon,keterangan,dampak,sumber,referensi,terverifikasi
    2024-01-12,,BANJIR,Bayah,Bayah Barat,-6.928,106.226,Luapan Sungai Cimadur merendam permukiman,± 40 rumah,GMLS,,ya

Wajib: tanggal (YYYY-MM-DD), jenis (type_code master, mis. BANJIR), kecamatan
(nama atau P-code COD-AB), keterangan (>= 10 karakter), sumber (GMLS |
BPBD_LEBAK | BNPB_DIBI | MEDIA | LAINNYA). Tanpa data pribadi.

Satu berkas = satu transaksi: bila ada baris yang salah tidak ada yang
ditulis, dan setiap kesalahan dilaporkan dengan nomor barisnya. Baris yang
sudah ada (jenis + kecamatan + tanggal + keterangan sama) dilewati, jadi
berkas yang sama aman diimpor ulang.

Terkoneksi sebagai monitor_app lalu SET LOCAL ROLE sesuai role pengguna
(ANALYST/ADMIN), sehingga GRANT/RLS dan audit_log sama dengan input lewat UI.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class _Rollback(Exception):
    pass


def run(client, csv_path: Path, username: str, dry_run: bool = False) -> dict:
    from sqlalchemy import text

    from api.deps import ROLE_TO_DB
    from etl.disasters import import_csv

    try:
        with client.session() as sess:
            # Seperti alur login: monitor_app tanpa SET ROLE tidak punya hak;
            # auth_get_user (SECURITY DEFINER) boleh dipanggil monitor_public.
            sess.execute(text("SET LOCAL ROLE " + ROLE_TO_DB["PUBLIC"]))
            row = sess.execute(text("SELECT user_id, role_code, is_active FROM auth_get_user(:u)"),
                               {"u": username}).first()
            if row is None or not row.is_active:
                raise ValueError(f"user {username!r} not found or inactive")
            if row.role_code not in ("ANALYST", "ADMIN"):
                raise ValueError(f"user {username!r} has role {row.role_code}; ANALYST or ADMIN required")
            sess.execute(text("SET LOCAL ROLE " + ROLE_TO_DB[row.role_code]))
            sess.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(row.user_id)})
            summary = import_csv(sess, csv_path, recorded_by=row.user_id, dry_run=dry_run)
            if summary["errors"] or dry_run:
                raise _Rollback(summary)
            return summary
    except _Rollback as rb:
        summary = rb.args[0]
        if summary["errors"]:
            summary["inserted"] = 0
        return summary


def main(argv: list[str]) -> int:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    from etl.database_client import DatabaseClient

    parser = argparse.ArgumentParser(description="Import disaster events from a structured CSV")
    parser.add_argument("csv", type=Path)
    parser.add_argument("--username", required=True, help="ANALYST/ADMIN account recorded as recorded_by")
    parser.add_argument("--dry-run", action="store_true", help="validate only; write nothing")
    args = parser.parse_args(argv)
    if not args.csv.exists():
        print(f"[FAIL] file not found: {args.csv}")
        return 2

    db = DatabaseClient.from_env("app")
    try:
        summary = run(db, args.csv, args.username.strip().lower(), args.dry_run)
    except ValueError as exc:
        print(f"[FAIL] {exc}")
        return 2
    finally:
        db.dispose()
    for e in summary["errors"]:
        print(f"[ERROR] {e}")
    if summary["errors"]:
        print("[FAIL] nothing imported; fix the lines above and run again")
        return 1
    verb = "would import" if args.dry_run else "imported"
    print(f"[OK] {verb} {summary['inserted']} event(s), {summary['duplicates']} already present")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
