# tests/security/test_grant_matrix.py
"""Menjalankan tests/security/grant_matrix.sql pada database uji.

Skrip SQL itu adalah artefak uji keamanan (INTERFACE.md §8, DATABASE.md §8.3)
yang juga bisa dijalankan langsung dengan psql. Di sini ia dijalankan sebagai
pemilik skema; kegagalan apa pun muncul sebagai RAISE EXCEPTION yang memuat
daftar sel matriks yang tidak cocok.
"""

from __future__ import annotations

from pathlib import Path

SQL_FILE = Path(__file__).with_name("grant_matrix.sql")


def test_grant_matrix(db_client):
    raw = db_client._engine.raw_connection()
    conn = raw.driver_connection
    previous = conn.autocommit
    conn.autocommit = True  # berkas mengatur BEGIN/ROLLBACK sendiri
    try:
        with conn.cursor() as cur:
            try:
                cur.execute(SQL_FILE.read_text(encoding="utf-8"))
            except Exception:
                # Transaksi BEGIN di berkas tertinggal aborted; rollback()
                # psycopg2 tidak berbuat apa-apa dalam mode autocommit.
                cur.execute("ROLLBACK")
                raise
        notices = [n.strip() for n in conn.notices if "OK" in n]
    finally:
        conn.autocommit = previous
        raw.close()
    assert any("Part 1 OK" in n for n in notices), notices
    assert any("Part 2 OK" in n for n in notices), notices
    assert any("Part 3 OK" in n for n in notices), notices
