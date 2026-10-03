#!/usr/bin/env python
"""
Terapkan skema Monitor (monitor_schema.sql -> monitor_security.sql ->
monitor_seed.sql) ke database kosong memakai kredensial dari .env.

Kenapa ada: `psql "$DATABASE_URL"` adalah sintaks bash. Di PowerShell
`$DATABASE_URL` adalah variabel PowerShell yang kosong, jadi psql diam-diam
jatuh ke default dan gagal autentikasi. Skrip ini memakai jalur yang sama
dengan pipeline (etl.config -> load_dotenv), jadi kredensialnya dijamin sama
dengan yang dipakai ETL dan API.

Setara dengan:
    psql -v ON_ERROR_STOP=1 -d themonitor -f database/monitor_schema.sql
    psql -v ON_ERROR_STOP=1 -d themonitor -f database/monitor_security.sql
    psql -v ON_ERROR_STOP=1 -d themonitor -f database/monitor_seed.sql

Pakai:
    python database/apply_schema.py           # terapkan ketiga berkas
    python database/apply_schema.py --check   # cek koneksi saja

Berkas skema mengasumsikan database kosong; skrip ini berhenti di berkas
pertama yang gagal. tests/conftest.py memakai apply_files() yang sama untuk
membangun database uji.
"""

from __future__ import annotations

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
    """Jalankan berkas SQL berurutan pada koneksi DB-API (psycopg2).

    Koneksi dipakai dalam mode autocommit: tiap berkas mengatur transaksinya
    sendiri (monitor_seed.sql memakai BEGIN/COMMIT). Isi berkas dikirim utuh;
    psycopg2 menjalankan banyak pernyataan sekaligus, termasuk blok DO $$.
    """
    # Dikembalikan setelahnya: koneksi bisa milik pool SQLAlchemy, dan koneksi
    # pool yang tertinggal autocommit membuat rollback session berikutnya
    # tidak membatalkan apa pun.
    previous = dbapi_connection.autocommit
    dbapi_connection.autocommit = True
    try:
        with dbapi_connection.cursor() as cur:
            for name in files:
                sql = (SCHEMA_DIR / name).read_text(encoding="utf-8")
                if not _has_statements(sql):
                    # psql menerima berkas yang isinya komentar saja; psycopg2
                    # menolaknya ("can't execute an empty query").
                    echo(f"[SKIP] {name} (comments only)")
                    continue
                echo(f"[RUN ] {name} ({len(sql)} bytes)")
                cur.execute(sql)
                echo(f"[DONE] {name}")
    finally:
        dbapi_connection.autocommit = previous


def main(argv: list[str]) -> int:
    sys.path.insert(0, str(SCHEMA_DIR.parent))
    from sqlalchemy import create_engine, text

    from etl.config import DatabaseConfig  # memicu load_dotenv

    cfg = DatabaseConfig()
    # Password tidak pernah ikut dicetak.
    print(f"[DB] {cfg.user}@{cfg.host}:{cfg.port}/{cfg.name}")
    engine = create_engine(cfg.url)

    if argv[:1] == ["--check"]:
        with engine.connect() as conn:
            ver = conn.scalar(text("SELECT version()"))
        print(f"[OK] connected — {str(ver).split(',')[0]}")
        return 0
    if argv:
        print(__doc__)
        return 2

    raw = engine.raw_connection()
    try:
        apply_files(raw.driver_connection)
    except Exception as exc:
        print(f"[FAIL] {exc}")
        return 1
    finally:
        raw.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
