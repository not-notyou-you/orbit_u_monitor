# tests/test_admin_api.py
"""Endpoint /api/admin bagian akun & log (INTERFACE.md §4.9)."""

from __future__ import annotations

import time

from sqlalchemy import text

from tests.conftest import TEST_PASSWORD


def _uname(prefix="adm"):
    return f"{prefix}_{time.time_ns() % 10**10}"


def _scalar(db_client, sql, **params):
    with db_client.session() as sess:
        return sess.scalar(text(sql), params)


def test_create_list_update_user(make_client, db_client, role_users):
    admin = make_client("ADMIN")
    name = _uname()
    resp = admin.post("/api/admin/users", json={"username": name, "full_name": "Relawan Uji",
                                                "organization": "GMLS", "role_code": "USER",
                                                "password": "password-12345"})
    assert resp.status_code == 201, resp.text
    user = resp.json()
    assert user["role_code"] == "USER" and user["created_by"] == role_users["ADMIN"]
    assert "password_hash" not in user

    dup = admin.post("/api/admin/users", json={"username": name, "full_name": "x", "role_code": "USER",
                                               "password": "password-12345"})
    assert dup.status_code == 409 and dup.json()["code"] == "USERNAME_TAKEN"
    weak = admin.post("/api/admin/users", json={"username": _uname(), "full_name": "x", "role_code": "USER",
                                                "password": "short"})
    assert weak.status_code == 400 and weak.json()["code"] == "PASSWORD_POLICY"
    public = admin.post("/api/admin/users", json={"username": _uname(), "full_name": "x",
                                                  "role_code": "PUBLIC", "password": "password-12345"})
    assert public.status_code == 422

    listing = admin.get(f"/api/admin/users?q={name}").json()
    assert listing["total"] == 1 and listing["items"][0]["username"] == name

    upd = admin.patch(f"/api/admin/users/{user['user_id']}",
                      json={"role_code": "ANALYST", "full_name": "Analis Uji", "is_active": False})
    assert upd.status_code == 200
    assert upd.json()["role_code"] == "ANALYST" and upd.json()["is_active"] is False

    audit = admin.get(f"/api/admin/audit?table=users&operation=U&user_id={role_users['ADMIN']}").json()
    rows = [r for r in audit["items"] if r["row_pk"] == str(user["user_id"])]
    assert rows and {"role_id", "full_name", "is_active"} <= set(rows[0]["changed_columns"])
    assert rows[0]["db_user"] == "monitor_admin"


def test_admin_cannot_demote_or_deactivate_self(make_client, role_users):
    admin = make_client("ADMIN")
    me = role_users["ADMIN"]
    for body in ({"is_active": False}, {"role_code": "USER"}):
        resp = admin.patch(f"/api/admin/users/{me}", json=body)
        assert resp.status_code == 409 and resp.json()["code"] == "CANNOT_MODIFY_SELF"


def test_unlock_and_reset_password(make_client, db_client):
    admin = make_client("ADMIN")
    name = _uname("lock")
    uid = admin.post("/api/admin/users", json={"username": name, "full_name": "x", "role_code": "USER",
                                               "password": TEST_PASSWORD}).json()["user_id"]
    anon = make_client()
    for _ in range(5):
        anon.post("/api/auth/login", json={"username": name, "password": "wrong-password"})
    assert anon.post("/api/auth/login", json={"username": name, "password": TEST_PASSWORD}).status_code == 423
    listed = admin.get(f"/api/admin/users?q={name}").json()["items"][0]
    assert listed["is_locked"] is True

    assert admin.post(f"/api/admin/users/{uid}/unlock").status_code == 200
    assert anon.post("/api/auth/login", json={"username": name, "password": TEST_PASSWORD}).status_code == 200

    assert admin.post(f"/api/admin/users/{uid}/reset-password",
                      json={"new_password": "brand-new-pass-1"}).status_code == 200
    assert make_client().post("/api/auth/login", json={"username": name, "password": TEST_PASSWORD}).status_code == 401
    assert make_client().post("/api/auth/login",
                              json={"username": name, "password": "brand-new-pass-1"}).status_code == 200
    assert admin.post("/api/admin/users/999999/unlock").status_code == 404


def test_login_and_download_logs(make_client, db_client):
    admin = make_client("ADMIN")
    name = _uname("log")
    uid = admin.post("/api/admin/users", json={"username": name, "full_name": "x", "role_code": "USER",
                                               "password": TEST_PASSWORD}).json()["user_id"]
    make_client().post("/api/auth/login", json={"username": name, "password": "wrong-password"})
    make_client().post("/api/auth/login", json={"username": name, "password": TEST_PASSWORD})

    logs = admin.get(f"/api/admin/logs/login?user_id={uid}").json()
    assert [r["action"] for r in logs["items"]] == ["LOGIN_SUCCESS", "LOGIN_FAILED"]
    assert logs["total"] == 2 and logs["limit"] == 50 and logs["offset"] == 0
    failed = admin.get(f"/api/admin/logs/login?user_id={uid}&action=LOGIN_FAILED").json()
    assert failed["total"] == 1 and failed["items"][0]["username"] == name

    page2 = admin.get(f"/api/admin/logs/login?user_id={uid}&limit=1&page=2").json()
    assert page2["offset"] == 1 and len(page2["items"]) == 1

    bad = admin.get("/api/admin/logs/login?date_from=2026-02-01&date_to=2026-01-01")
    assert bad.status_code == 400 and bad.json()["code"] == "INVALID_DATE_RANGE"
    assert admin.get("/api/admin/logs/download").status_code == 200


def test_admin_token_listing_shows_owner(make_client, role_users):
    created = make_client("ANALYST").post("/api/auth/tokens", json={"name": "lihat-admin", "scope": "READ"}).json()
    items = make_client("ADMIN").get(f"/api/admin/tokens?user_id={role_users['ANALYST']}").json()["items"]
    row = next(i for i in items if i["token_id"] == created["token_id"])
    assert row["username"] == "t_analyst" and row["prefix"] == created["prefix"] and "token" not in row
