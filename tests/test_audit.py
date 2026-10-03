# tests/test_audit.py
"""Audit trigger (DATABASE.md §8.5, M15).

Setiap tes berjalan dalam satu transaksi db_session yang di-rollback. Koneksi
db_session adalah pemilik skema tanpa SET ROLE, setara dengan orang yang
mengubah data lewat psql; tes yang memerlukan role aplikasi menjalankan
SET LOCAL ROLE + app.user_id persis seperti api/deps.py.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

AUDITED_TABLES = {
    "users", "api_tokens", "alert_rules", "alert_events", "disaster_events",
    "quality_thresholds", "disaster_types", "administrative_regions",
    "app_settings", "live_areas", "satellite_scenes", "nasa_scenes", "datasets",
}


def _audit_rows(sess, table, pk):
    return sess.execute(
        text("""SELECT operation, old_data, new_data, changed_columns, app_user_id, db_user
                FROM audit_log WHERE table_name = :t AND row_pk = :pk ORDER BY audit_id"""),
        {"t": table, "pk": str(pk)},
    ).mappings().all()


def _as_app_role(sess, db_role, user_id):
    sess.execute(text(f"SET LOCAL ROLE {db_role}"))  # literal tetap di tes
    sess.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(user_id)})


def _reset_role(sess):
    sess.execute(text("RESET ROLE"))
    sess.execute(text("SELECT set_config('app.user_id', '', true)"))


def _make_user(sess, username, role_code="USER"):
    return sess.scalar(text("""
        INSERT INTO users (role_id, username, password_hash, full_name)
        SELECT role_id, :u, 'secret-hash', :u FROM roles WHERE role_code = :r
        RETURNING user_id"""), {"u": username, "r": role_code})


def test_every_table_in_section_8_5_has_audit_trigger(db_session):
    rows = db_session.execute(text("""
        SELECT DISTINCT c.relname
        FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid
        JOIN pg_proc p ON p.oid = t.tgfoid
        WHERE p.proname = 'audit_row' AND NOT t.tgisinternal""")).scalars().all()
    assert set(rows) == AUDITED_TABLES


def test_update_via_psql_is_audited_without_app_user(db_session):
    owner = db_session.scalar(text("SELECT session_user"))
    rule_id = db_session.scalar(text("SELECT rule_id FROM alert_rules ORDER BY rule_id LIMIT 1"))
    db_session.execute(text("UPDATE alert_rules SET reference_source = 'audit test' WHERE rule_id = :r"),
                       {"r": rule_id})

    [row] = _audit_rows(db_session, "alert_rules", rule_id)[-1:]
    assert row["operation"] == "U"
    assert row["app_user_id"] is None
    assert row["db_user"] == owner
    assert row["changed_columns"] == ["reference_source"]
    assert row["new_data"]["reference_source"] == "audit test"
    assert row["old_data"]["reference_source"] != "audit test"


def test_app_change_records_app_user_and_db_role(db_session):
    admin_id = _make_user(db_session, "audit_admin", "ADMIN")
    target_id = _make_user(db_session, "audit_target")

    _as_app_role(db_session, "monitor_admin", admin_id)
    db_session.execute(text("UPDATE users SET full_name = 'Nama Baru', password_hash = 'new-hash' "
                            "WHERE user_id = :u"), {"u": target_id})
    _reset_role(db_session)

    rows = _audit_rows(db_session, "users", target_id)
    assert [r["operation"] for r in rows] == ["I", "U"]
    upd = rows[-1]
    assert upd["app_user_id"] == admin_id
    assert upd["db_user"] == "monitor_admin"
    # Perubahan hash terlihat sebagai nama kolom, nilainya tidak pernah disimpan.
    assert set(upd["changed_columns"]) == {"full_name", "password_hash"}
    for data in (upd["old_data"], upd["new_data"], rows[0]["new_data"]):
        assert "password_hash" not in data
    assert upd["new_data"]["full_name"] == "Nama Baru"


def test_login_bookkeeping_is_not_audited_but_lock_is(db_session):
    user_id = _make_user(db_session, "audit_login")
    db_session.execute(text("SET LOCAL ROLE monitor_public"))
    db_session.execute(text("SELECT * FROM auth_record_login(:u, true)"), {"u": user_id})
    for _ in range(4):
        db_session.execute(text("SELECT * FROM auth_record_login(:u, false)"), {"u": user_id})
    _reset_role(db_session)
    assert [r["operation"] for r in _audit_rows(db_session, "users", user_id)] == ["I"]

    # Gagal kelima: akun terkunci -> locked_until berubah -> tercatat.
    db_session.execute(text("SET LOCAL ROLE monitor_public"))
    locked = db_session.execute(text("SELECT * FROM auth_record_login(:u, false)"),
                                {"u": user_id}).mappings().one()
    _reset_role(db_session)
    assert locked["locked_until"] is not None
    rows = _audit_rows(db_session, "users", user_id)
    assert [r["operation"] for r in rows] == ["I", "U"]
    assert "locked_until" in rows[-1]["changed_columns"]


def test_token_hash_censored_and_last_used_not_audited(db_session):
    user_id = _make_user(db_session, "audit_token")
    token_id = db_session.scalar(text("""
        INSERT INTO api_tokens (user_id, token_name, token_prefix, token_hash, scopes, expires_at)
        VALUES (:u, 'tes', 'trn_aud1', repeat('a', 64), 'READ', now() + interval '1 day')
        RETURNING token_id"""), {"u": user_id})
    db_session.execute(text("UPDATE api_tokens SET last_used_at = now() WHERE token_id = :t"), {"t": token_id})
    db_session.execute(text("UPDATE api_tokens SET revoked_at = now() WHERE token_id = :t"), {"t": token_id})

    rows = _audit_rows(db_session, "api_tokens", token_id)
    assert [r["operation"] for r in rows] == ["I", "U"]
    assert rows[-1]["changed_columns"] == ["revoked_at"]
    for r in rows:
        assert "token_hash" not in (r["new_data"] or {})
        assert "token_hash" not in (r["old_data"] or {})


def test_scene_only_is_valid_changes_are_audited(db_session, sample_scene):
    db_session.execute(text("UPDATE satellite_scenes SET cloud_cover_percent = 1 WHERE scene_id = :s"),
                       {"s": sample_scene})
    assert _audit_rows(db_session, "satellite_scenes", sample_scene) == []
    db_session.execute(text("UPDATE satellite_scenes SET is_valid = false, invalid_reason = 'tes', "
                            "invalidated_at = now() "
                            "WHERE scene_id = :s"), {"s": sample_scene})
    [row] = _audit_rows(db_session, "satellite_scenes", sample_scene)
    assert "is_valid" in row["changed_columns"]


def test_region_in_aoi_audited(db_session):
    geom = "ST_Multi(ST_GeomFromText('POLYGON((106 -7, 106.1 -7, 106.1 -6.9, 106 -6.9, 106 -7))', 4326))"
    parent = db_session.scalar(text(f"""
        INSERT INTO administrative_regions (pcode, region_name, admin_level, geom, source_dataset)
        VALUES ('IDAUD2', 'Kab Uji', 2, {geom}, 'tes') RETURNING region_id"""))
    region = db_session.scalar(text(f"""
        INSERT INTO administrative_regions (parent_region_id, pcode, region_name, admin_level, geom, source_dataset)
        VALUES (:p, 'IDAUD3', 'Kec Uji', 3, {geom}, 'tes') RETURNING region_id"""), {"p": parent})
    db_session.execute(text("UPDATE administrative_regions SET region_name = 'X' WHERE region_id = :r"), {"r": region})
    assert _audit_rows(db_session, "administrative_regions", region) == []

    db_session.execute(text("UPDATE administrative_regions SET in_aoi = true WHERE region_id = :r"), {"r": region})
    [row] = _audit_rows(db_session, "administrative_regions", region)
    assert row["changed_columns"] == ["in_aoi"]
    assert "geom" not in row["new_data"]


def test_dataset_progress_counters_not_audited_status_is(db_session, sample_dataset):
    db_session.execute(text("UPDATE datasets SET completed_scenes = completed_scenes + 1, "
                            "total_size_bytes = 10 WHERE dataset_id = :d"), {"d": sample_dataset})
    before = len(_audit_rows(db_session, "datasets", sample_dataset))
    db_session.execute(text("UPDATE datasets SET status = 'QUEUED' WHERE dataset_id = :d"), {"d": sample_dataset})
    rows = _audit_rows(db_session, "datasets", sample_dataset)
    assert len(rows) == before + 1
    assert rows[-1]["changed_columns"] == ["status"]


def test_etl_insert_records_etl_role(db_session):
    # app_settings tidak bisa ditulis etl; alert_events butuh observasi.
    # Cukup periksa jalur INSERT trigger dengan role etl pada datasets.
    db_session.execute(text("SET LOCAL ROLE monitor_etl"))
    ds = db_session.scalar(text("""
        INSERT INTO datasets (name, bbox, bbox_wkt, date_start, date_end)
        VALUES ('audit-etl', ST_GeomFromText('POLYGON((0 0,1 0,1 1,0 1,0 0))', 4326),
                'POLYGON((0 0,1 0,1 1,0 1,0 0))', '2024-01-01', '2024-01-02')
        RETURNING dataset_id"""))
    _reset_role(db_session)
    [row] = _audit_rows(db_session, "datasets", ds)
    assert row["operation"] == "I"
    assert row["db_user"] == "monitor_etl"
    assert row["app_user_id"] is None


@pytest.mark.parametrize("db_role", ["monitor_admin", "monitor_etl", "monitor_analyst"])
def test_nobody_can_tamper_with_audit_log(db_session, db_role):
    from sqlalchemy.exc import ProgrammingError

    # Transaksi menjadi aborted setelah error; fixture db_session me-rollback.
    db_session.execute(text(f"SET LOCAL ROLE {db_role}"))
    with pytest.raises(ProgrammingError, match="permission denied"):
        db_session.execute(text("DELETE FROM audit_log"))
