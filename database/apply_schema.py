#!/usr/bin/env python
"""Terapkan skema Monitor (monitor_schema.sql -> monitor_security.sql ->
monitor_seed.sql) ke database kosong memakai kredensial dari .env.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

SCHEMA_DIR = Path(__file__).resolve().parent
SCHEMA_FILES: tuple[str, ...] = (
    "monitor_schema.sql",
    "monitor_security.sql",
    "monitor_seed.sql",
)


def _has_statements(sql: str) -> bool:
    """True bila berkas memuat sesuatu selain baris kosong dan komentar `--`."""
    return any(
        line.strip() and not line.strip().startswith("--")
        for line in sql.splitlines()
    )


def apply_files(dbapi_connection, files: tuple[str, ...] = SCHEMA_FILES, echo=print) -> None:
    """Jalankan berkas SQL berurutan pada koneksi DB-API (psycopg2)."""
    previous = dbapi_connection.autocommit
    dbapi_connection.autocommit = True
    try:
        with dbapi_connection.cursor() as cur:
            for name in files:
                sql = (SCHEMA_DIR / name).read_text(encoding="utf-8")
                if not _has_statements(sql):
                    echo(f"[SKIP] {name} (comments only)")
                    continue
                echo(f"[RUN ] {name} ({len(sql)} bytes)")
                cur.execute(sql)
                echo(f"[DONE] {name}")
    finally:
        dbapi_connection.autocommit = previous


LOGIN_ROLE_PASSWORD_ENV: dict[str, str] = {
    "monitor_app": "MONITOR_APP_PASSWORD",
    "monitor_etl": "MONITOR_ETL_PASSWORD",
}


def set_role_passwords(dbapi_connection, echo=print) -> list[str]:
    """ALTER ROLE ... PASSWORD untuk role login yang sandinya ada di env."""
    skipped = []
    previous = dbapi_connection.autocommit
    dbapi_connection.autocommit = True
    try:
        with dbapi_connection.cursor() as cur:
            for role, env in LOGIN_ROLE_PASSWORD_ENV.items():
                password = os.getenv(env)
                if not password:
                    skipped.append(role)
                    echo(f"[WARN] {env} kosong: sandi {role} tidak diubah")
                    continue
                cur.execute("SELECT format('ALTER ROLE %%I PASSWORD %%L', %s, %s)", (role, password))
                cur.execute(cur.fetchone()[0])
                echo(f"[DONE] password {role}")
    finally:
        dbapi_connection.autocommit = previous
    return skipped


def main(argv: list[str]) -> int:
    sys.path.insert(0, str(SCHEMA_DIR.parent))
    from sqlalchemy import create_engine, text

    from etl.config import DatabaseConfig  # memicu load_dotenv

    cfg = DatabaseConfig()
    print(f"[DB] {cfg.user}@{cfg.host}:{cfg.port}/{cfg.name}")
    engine = create_engine(cfg.url)

    if argv[:1] == ["--check"]:
        with engine.connect() as conn:
            ver = conn.scalar(text("SELECT version()"))
        print(f"[OK] connected — {str(ver).split(',')[0]}")
        return 0
    if argv[:1] == ["--migrate"] and len(argv) == 2:
        raw = engine.raw_connection()
        try:
            apply_files(raw.driver_connection, (f"migrations/{argv[1]}",))
        except Exception as exc:
            print(f"[FAIL] {exc}")
            return 1
        finally:
            raw.close()
        return 0
    if argv:
        print(__doc__)
        return 2

    raw = engine.raw_connection()
    try:
        apply_files(raw.driver_connection)
        set_role_passwords(raw.driver_connection)
    except Exception as exc:
        print(f"[FAIL] {exc}")
        return 1
    finally:
        raw.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
