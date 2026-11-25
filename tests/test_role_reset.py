# tests/test_role_reset.py
"""Koneksi pool yang dipakai ulang tidak membawa hak peran transaksi sebelumnya (RM4).

API memakai satu login (monitor_app) dan pool koneksi. Setiap request mengganti
peran dengan set_config('role', ..., true) = SET LOCAL ROLE, yang berlaku hanya
sampai akhir transaksi. Tes ini memaksa dua transaksi berurutan memakai koneksi
fisik yang SAMA (pool 1, tanpa overflow; pg_backend_pid() dibandingkan) lalu
memeriksa bahwa peran dan app.user_id transaksi pertama tidak terbawa ke
transaksi kedua, baik setelah COMMIT maupun setelah ROLLBACK karena galat.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

DENIED = {"42501", "42P01"}  # insufficient_privilege; monitor_app tanpa USAGE skema -> tabel "tidak ada"
ACK_UPDATE = "UPDATE alert_events SET ack_note = 'x', acknowledged_by = NULL, acknowledged_at = NULL WHERE false"


@pytest.fixture
def one_connection(app_db_client):
    """Sesi monitor_app dengan tepat satu koneksi fisik."""
    url = app_db_client._engine.url.render_as_string(hide_password=False)
    engine = create_engine(url, poolclass=QueuePool, pool_size=1, max_overflow=0)
    try:
        yield sessionmaker(bind=engine)
    finally:
        engine.dispose()


def _apply(sess, role_code: str, user_id: int | None) -> None:
    from api.deps import _apply_db_role
    _apply_db_role(sess, role_code, user_id)


def _state(sess) -> tuple[int, str, str]:
    pid, user, uid = sess.execute(text(
        "SELECT pg_backend_pid(), current_user, coalesce(current_setting('app.user_id', true), '')")).one()
    return pid, user, uid


def _denied(sess, sql: str) -> str:
    """Kode SQLSTATE bila ditolak, 'OK' bila diizinkan. Transaksi di-rollback."""
    try:
        sess.execute(text(sql))
        return "OK"
    except DBAPIError as exc:
        return getattr(exc.orig, "pgcode", None) or "ERR"
    finally:
        sess.rollback()


def test_commit_does_not_carry_analyst_role_to_next_transaction(one_connection, role_users):
    Session = one_connection
    analyst = role_users["ANALYST"]

    # Transaksi 1: request Analis menulis kolom tindak lanjut (diizinkan), lalu COMMIT.
    s1 = Session()
    _apply(s1, "ANALYST", analyst)
    pid1, user1, uid1 = _state(s1)
    assert (user1, uid1) == ("monitor_analyst", str(analyst))
    s1.execute(text(ACK_UPDATE))
    s1.commit()
    s1.close()

    # Transaksi 2 pada koneksi yang sama, sebelum SET ROLE: kembali ke monitor_app tanpa hak apa pun.
    s2 = Session()
    pid2, user2, uid2 = _state(s2)
    assert pid2 == pid1, "koneksi fisik harus dipakai ulang"
    assert (user2, uid2) == ("monitor_app", "")
    assert _denied(s2, "SELECT 1 FROM alert_rules LIMIT 1") in DENIED
    s2.close()

    # Transaksi 3 pada koneksi yang sama sebagai Relawan: hak Analis tidak terbawa.
    s3 = Session()
    _apply(s3, "USER", role_users["USER"])
    pid3, user3, _ = _state(s3)
    assert pid3 == pid1 and user3 == "monitor_user"
    assert _denied(s3, ACK_UPDATE) == "42501"
    s3.close()


def test_rollback_after_error_does_not_carry_admin_role(one_connection, role_users):
    Session = one_connection

    # Transaksi 1: request Administrator berakhir dengan galat (ROLLBACK).
    s1 = Session()
    _apply(s1, "ADMIN", role_users["ADMIN"])
    pid1, user1, _ = _state(s1)
    assert user1 == "monitor_admin"
    with pytest.raises(DBAPIError):
        s1.execute(text("SELECT 1 / 0"))
    s1.rollback()
    s1.close()

    # Transaksi 2 pada koneksi yang sama sebagai Pengunjung: hak Administrator tidak terbawa.
    s2 = Session()
    _apply(s2, "PUBLIC", None)
    pid2, user2, uid2 = _state(s2)
    assert pid2 == pid1
    assert (user2, uid2) == ("monitor_public", "")
    assert _denied(s2, "SELECT count(*) FROM users") == "42501"
    s2.close()
