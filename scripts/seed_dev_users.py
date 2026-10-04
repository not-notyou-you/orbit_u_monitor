#!/usr/bin/env python
"""Seed akun dummy satu per role untuk DEVELOPMENT SAJA.

Terkoneksi sebagai monitor_app lalu SET LOCAL ROLE monitor_admin, sama seperti
scripts/create_admin.py. Idempoten: akun yang sudah ada dikembalikan ke role,
sandi, dan status aktif bawaan, serta penghitung gagal-login direset.

JANGAN dijalankan di produksi: sandinya tertulis di berkas ini.

Pakai:
    python scripts/seed_dev_users.py --i-know-this-is-dev
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEV_PASSWORD = "DevPassword!2026"
DEV_USERS = [
    ("dev_user", "USER", "Dev Relawan"),
    ("dev_analyst", "ANALYST", "Dev Analis"),
    ("dev_engineer", "DATA_ENGINEER", "Dev Data Engineer"),
    ("dev_admin", "ADMIN", "Dev Administrator"),
]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Seed dev accounts, one per login role")
    parser.add_argument("--i-know-this-is-dev", action="store_true", help="wajib: konfirmasi ini bukan produksi")
    args = parser.parse_args(argv)
    if not args.i_know_this_is_dev:
        print("[FAIL] tambahkan --i-know-this-is-dev (skrip ini hanya untuk development)")
        return 2

    from sqlalchemy import text

    from api.deps import ROLE_TO_DB
    from api.security import hash_password
    from etl.database_client import DatabaseClient  # memuat .env lewat etl/__init__

    pw_hash = hash_password(DEV_PASSWORD)
    client = DatabaseClient.from_env("app")
    try:
        with client.session() as sess:
            sess.execute(text("SET LOCAL ROLE " + ROLE_TO_DB["ADMIN"]))
            for username, role_code, full_name in DEV_USERS:
                uid = sess.scalar(text("""
                    INSERT INTO users (role_id, username, password_hash, full_name, organization, is_active)
                    SELECT role_id, :u, :h, :n, 'DEV', true FROM roles WHERE role_code = :r
                    ON CONFLICT (username) DO UPDATE SET role_id = EXCLUDED.role_id,
                        password_hash = EXCLUDED.password_hash, is_active = true,
                        failed_login_count = 0, locked_until = NULL
                    RETURNING user_id"""),
                    {"u": username, "h": pw_hash, "n": full_name, "r": role_code})
                print(f"[OK] {role_code:<14} {username:<13} user_id={uid}")
    except Exception as exc:
        print(f"[FAIL] {exc}")
        return 1
    finally:
        client.dispose()
    print(f"Password semua akun: {DEV_PASSWORD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
