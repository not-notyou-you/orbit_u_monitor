#!/usr/bin/env python
"""Buat akun ADMIN (admin pertama, README §9 langkah 5).

Terkoneksi sebagai monitor_app lalu SET LOCAL ROLE monitor_admin, persis
seperti request API ADMIN: tidak memakai superuser, dan pembuatan akun
tercatat audit_log (app_user_id NULL = dibuat skrip).

Pakai:
    python scripts/create_admin.py --username admin --full-name "Admin GMLS"
    python scripts/create_admin.py --username admin --password-stdin < pw.txt

Sandi diminta lewat prompt tersembunyi (getpass) kecuali --password-stdin.
Kebijakan sandi sama dengan API: minimal 10 karakter.
"""

from __future__ import annotations

import argparse
import getpass
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

USERNAME_RE = re.compile(r"^[a-z0-9_.]{3,50}$")


def create_admin(client, username: str, full_name: str, organization: str | None, password: str) -> int:
    from sqlalchemy import text

    from api.deps import ROLE_TO_DB
    from api.security import hash_password

    with client.session() as sess:
        sess.execute(text("SET LOCAL ROLE " + ROLE_TO_DB["ADMIN"]))
        if sess.scalar(text("SELECT 1 FROM users WHERE username = :u"), {"u": username}):
            raise ValueError(f"username {username!r} already exists")
        return sess.scalar(text("""
            INSERT INTO users (role_id, username, password_hash, full_name, organization)
            SELECT role_id, :u, :h, :n, :o FROM roles WHERE role_code = 'ADMIN'
            RETURNING user_id"""),
            {"u": username, "h": hash_password(password), "n": full_name, "o": organization})


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Create an ADMIN account for Orbit-U: The Monitor")
    parser.add_argument("--username", required=True)
    parser.add_argument("--full-name", default="Administrator")
    parser.add_argument("--organization", default="GMLS")
    parser.add_argument("--password-stdin", action="store_true",
                        help="read the password from the first line of stdin")
    args = parser.parse_args(argv)

    username = args.username.strip().lower()
    if not USERNAME_RE.match(username):
        print("[FAIL] username must match ^[a-z0-9_.]{3,50}$")
        return 2

    from api.security import password_policy_error
    if args.password_stdin:
        password = sys.stdin.readline().rstrip("\r\n")
    else:
        password = getpass.getpass("Password: ")
        if getpass.getpass("Repeat password: ") != password:
            print("[FAIL] passwords do not match")
            return 2
    problem = password_policy_error(password)
    if problem:
        print(f"[FAIL] {problem}")
        return 2

    from etl.database_client import DatabaseClient  # memuat .env lewat etl/__init__
    client = DatabaseClient.from_env("app")
    try:
        user_id = create_admin(client, username, args.full_name.strip(), args.organization or None, password)
    except Exception as exc:
        print(f"[FAIL] {exc}")
        return 1
    finally:
        client.dispose()
    print(f"[OK] ADMIN {username!r} created (user_id={user_id})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
