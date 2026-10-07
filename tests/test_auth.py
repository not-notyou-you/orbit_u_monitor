# tests/test_auth.py
"""Autentikasi, sesi, token API, dan log aktivitas (INTERFACE.md §4.1, §6;
DATABASE.md §4.2.5, §4.2.8, §8.6)."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from sqlalchemy import text

from tests.conftest import TEST_PASSWORD, create_test_user


@pytest.fixture
def user_factory(db_client, test_password_hash):
    """Akun baru per tes (login gagal mengubah penghitung kunci)."""
    counter = {"n": 0}

    def _make(role="USER", is_active=True):
        counter["n"] += 1
        name = f"auth_{role.lower()}_{int(time.time() * 1000) % 10_000_000}_{counter['n']}"
        return name, create_test_user(db_client, name, role, test_password_hash, is_active)

    return _make


def _login(client, username, password=TEST_PASSWORD):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def _activity(db_client, action, user_id=None, username=None):
    q = "SELECT * FROM user_activity_logs WHERE action = :a"
    params = {"a": action}
    if user_id is not None:
        q += " AND user_id = :u"
        params["u"] = user_id
    if username is not None:
        q += " AND username_attempted = :n"
        params["n"] = username
    with db_client.session() as sess:
        return sess.execute(text(q + " ORDER BY log_id"), params).mappings().all()


def _db(db_client, sql, **params):
    with db_client.session() as sess:
        return sess.execute(text(sql), params)


# --- login --------------------------------------------------------------------

class TestLogin:

    def test_success_sets_secure_session_cookie(self, make_client, user_factory, db_client):
        name, uid = user_factory("ANALYST")
        client = make_client()
        resp = _login(client, name)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["user_id"] == uid and body["role_code"] == "ANALYST"
        assert "alerts.acknowledge" in body["permissions"]
        assert "datasets.manage" not in body["permissions"]

        cookie = resp.headers["set-cookie"]
        assert cookie.startswith("orbit_u_session=")
        lowered = cookie.lower()
        for attr in ("httponly", "secure", "samesite=strict", "path=/", "max-age=28800"):
            assert attr in lowered, cookie

        token = cookie.split(";")[0].split("=", 1)[1]
        header = jwt.get_unverified_header(token)
        claims = jwt.decode(token, options={"verify_signature": False})
        assert header["alg"] == "HS256"
        assert claims["sub"] == str(uid) and claims["role"] == "ANALYST"
        assert claims["exp"] - claims["iat"] == 8 * 3600

        [log] = _activity(db_client, "LOGIN_SUCCESS", user_id=uid)
        assert log["user_agent"]  # TestClient tidak punya IP sungguhan ("testclient")
        last_login = _db(db_client, "SELECT last_login_at FROM users WHERE user_id = :u", u=uid).scalar()
        assert last_login is not None

    def test_cookie_authenticates_following_requests(self, make_client, user_factory):
        name, uid = user_factory()
        client = make_client()
        _login(client, name)
        me = client.get("/api/auth/me")
        assert me.status_code == 200 and me.json()["user_id"] == uid
        assert me.json()["auth"] == "session"

    def test_password_hash_is_bcrypt_cost_12(self, test_password_hash):
        assert test_password_hash.startswith("$2b$12$")

    def test_login_requires_csrf_header(self, make_client, user_factory):
        name, _ = user_factory()
        resp = _login(make_client(csrf=False), name)
        assert resp.status_code == 403
        assert resp.json()["code"] == "CSRF_HEADER_REQUIRED"

    def test_wrong_password_401_and_logged(self, make_client, user_factory, db_client):
        name, uid = user_factory()
        resp = _login(make_client(), name, "wrong-password")
        assert resp.status_code == 401
        assert resp.json() == {"detail": "Invalid username or password", "code": "INVALID_CREDENTIALS"}
        [log] = _activity(db_client, "LOGIN_FAILED", user_id=uid)
        assert log["username_attempted"] == name
        assert log["detail"]["reason"] == "bad_password"
        count = _db(db_client, "SELECT failed_login_count FROM users WHERE user_id = :u", u=uid).scalar()
        assert count == 1

    def test_unknown_user_same_response_logged_without_user_id(self, make_client, db_client):
        resp = _login(make_client(), "no.such.user")
        assert resp.status_code == 401 and resp.json()["code"] == "INVALID_CREDENTIALS"
        [log] = _activity(db_client, "LOGIN_FAILED", username="no.such.user")[-1:]
        assert log["user_id"] is None

    def test_five_failures_lock_account_for_15_minutes(self, make_client, user_factory, db_client):
        name, uid = user_factory()
        client = make_client()
        codes = [_login(client, name, "wrong-password").status_code for _ in range(5)]
        assert codes == [401, 401, 401, 401, 423]

        # Percobaan keenam, walau sandinya benar, tetap ditolak (INTERFACE §8).
        sixth = _login(client, name)
        assert sixth.status_code == 423 and sixth.json()["code"] == "ACCOUNT_LOCKED"

        locked = _db(db_client, "SELECT locked_until - now() FROM users WHERE user_id = :u", u=uid).scalar()
        assert timedelta(minutes=14) < locked <= timedelta(minutes=15)
        assert len(_activity(db_client, "LOGIN_FAILED", user_id=uid)) == 6

    def test_login_works_after_lock_expires(self, make_client, user_factory, db_client):
        name, uid = user_factory()
        _db(db_client, "UPDATE users SET locked_until = now() - interval '1 second' WHERE user_id = :u", u=uid)
        assert _login(make_client(), name).status_code == 200

    def test_inactive_account_rejected(self, make_client, user_factory):
        name, _ = user_factory(is_active=False)
        resp = _login(make_client(), name)
        assert resp.status_code == 401 and resp.json()["code"] == "ACCOUNT_INACTIVE"

    def test_username_is_case_insensitive(self, make_client, user_factory):
        name, _ = user_factory()
        assert _login(make_client(), name.upper()).status_code == 200


# --- sesi ---------------------------------------------------------------------

class TestSession:

    def test_me_requires_login(self, make_client):
        resp = make_client().get("/api/auth/me")
        assert resp.status_code == 401 and resp.json()["code"] == "NOT_AUTHENTICATED"

    def test_tampered_cookie_rejected(self, make_client):
        client = make_client()
        client.cookies.set("orbit_u_session", "not-a-jwt")
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401 and resp.json()["code"] == "SESSION_EXPIRED"

    def test_expired_jwt_rejected(self, make_client, role_users):
        from api.security import JWT_ALGORITHM, jwt_secret
        past = datetime.now(timezone.utc) - timedelta(hours=9)
        token = jwt.encode({"sub": str(role_users["USER"]), "role": "USER", "iat": int(past.timestamp()),
                            "exp": int((past + timedelta(hours=8)).timestamp())}, jwt_secret(), JWT_ALGORITHM)
        client = make_client()
        client.cookies.set("orbit_u_session", token)
        assert client.get("/api/auth/me").json()["code"] == "SESSION_EXPIRED"

    def test_jwt_signed_with_other_secret_rejected(self, make_client, role_users):
        token = jwt.encode({"sub": str(role_users["ADMIN"]), "role": "ADMIN", "iat": int(time.time()),
                            "exp": int(time.time()) + 3600}, "x" * 40, "HS256")
        client = make_client()
        client.cookies.set("orbit_u_session", token)
        assert client.get("/api/auth/me").status_code == 401

    def test_role_change_applies_on_next_request(self, make_client, user_factory, db_client):
        _, uid = user_factory("USER")
        client = make_client(user_id=uid)
        assert client.get("/api/datasets").status_code == 403
        _db(db_client, "UPDATE users SET role_id = (SELECT role_id FROM roles WHERE role_code = 'DATA_ENGINEER') "
                       "WHERE user_id = :u", u=uid)
        assert client.get("/api/auth/me").json()["role_code"] == "DATA_ENGINEER"
        assert client.get("/api/datasets").status_code == 200

    def test_deactivation_applies_on_next_request(self, make_client, user_factory, db_client):
        _, uid = user_factory("USER")
        client = make_client(user_id=uid)
        assert client.get("/api/auth/me").status_code == 200
        _db(db_client, "UPDATE users SET is_active = false WHERE user_id = :u", u=uid)
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401 and resp.json()["code"] == "ACCOUNT_INACTIVE"

    def test_logout_clears_cookie_and_is_logged(self, make_client, user_factory, db_client):
        name, uid = user_factory()
        client = make_client()
        _login(client, name)
        resp = client.post("/api/auth/logout")
        assert resp.status_code == 200
        cookie = resp.headers["set-cookie"].lower()
        assert cookie.startswith("orbit_u_session=") and "max-age=0" in cookie
        assert len(_activity(db_client, "LOGOUT", user_id=uid)) == 1
        assert client.get("/api/auth/me").status_code == 401

    def test_write_without_csrf_header_rejected(self, make_client):
        client = make_client("ADMIN", csrf=False)
        resp = client.post("/api/auth/logout")
        assert resp.status_code == 403 and resp.json()["code"] == "CSRF_HEADER_REQUIRED"


class TestChangePassword:

    def test_change_password_flow(self, make_client, user_factory, db_client):
        name, uid = user_factory()
        client = make_client()
        _login(client, name)
        bad = client.post("/api/auth/change-password",
                          json={"old_password": "nope", "new_password": "new-password-456"})
        assert bad.status_code == 400 and bad.json()["code"] == "INVALID_OLD_PASSWORD"
        short = client.post("/api/auth/change-password",
                            json={"old_password": TEST_PASSWORD, "new_password": "short"})
        assert short.status_code == 400 and short.json()["code"] == "PASSWORD_POLICY"

        ok = client.post("/api/auth/change-password",
                         json={"old_password": TEST_PASSWORD, "new_password": "new-password-456"})
        assert ok.status_code == 200, ok.text
        assert _login(make_client(), name).status_code == 401
        assert _login(make_client(), name, "new-password-456").status_code == 200

        audit = _db(db_client, """SELECT changed_columns, app_user_id, new_data FROM audit_log
                                  WHERE table_name = 'users' AND row_pk = :pk AND operation = 'U'
                                  ORDER BY audit_id DESC LIMIT 1""", pk=str(uid)).mappings().one()
        assert "password_hash" in audit["changed_columns"]
        assert audit["app_user_id"] == uid
        assert "password_hash" not in audit["new_data"]


# --- token API ----------------------------------------------------------------

def _create_token(client, scope="READ", name="skrip", days=30):
    resp = client.post("/api/auth/tokens", json={"name": name, "scope": scope, "expires_in_days": days})
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestApiTokens:

    def test_create_returns_token_once_and_stores_hash_only(self, make_client, role_users, db_client):
        client = make_client("USER")
        created = _create_token(client)
        token = created["token"]
        assert token.startswith("trn_") and len(token) == 4 + 43
        assert created["prefix"] == token[:8]
        row = _db(db_client, "SELECT token_prefix, token_hash, scopes, expires_at - created_at AS life "
                             "FROM api_tokens WHERE token_id = :t", t=created["token_id"]).mappings().one()
        import hashlib
        assert row["token_hash"] == hashlib.sha256(token.encode()).hexdigest()
        assert row["life"] == timedelta(days=30)

        listing = client.get("/api/auth/tokens").json()
        item = next(i for i in listing["items"] if i["token_id"] == created["token_id"])
        assert "token" not in item and item["prefix"] == created["prefix"] and item["active"]

    def test_max_lifetime_180_days(self, make_client):
        resp = make_client("USER").post("/api/auth/tokens",
                                        json={"name": "x", "scope": "READ", "expires_in_days": 181})
        assert resp.status_code == 422 and resp.json()["code"] == "VALIDATION_ERROR"

    def test_bearer_token_reads_with_owner_role(self, make_client, role_users, db_client):
        token = _create_token(make_client("DATA_ENGINEER"))["token"]
        bearer = make_client(token=token)
        me = bearer.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json()["role_code"] == "DATA_ENGINEER" and me.json()["auth"] == "token"
        assert bearer.get("/api/datasets").status_code == 200
        # Role token = role pemilik: endpoint ADMIN tetap ditolak.
        assert bearer.get("/api/admin/users").status_code == 403

    def test_token_cannot_write(self, make_client):
        token = _create_token(make_client("ADMIN"))["token"]
        bearer = make_client(token=token, csrf=False)
        for method, path, body in (("post", "/api/auth/tokens", {"name": "x", "scope": "READ"}),
                                   ("post", "/api/auth/logout", None),
                                   ("delete", "/api/datasets/1", None),
                                   ("patch", "/api/admin/users/1", {"full_name": "x"})):
            resp = getattr(bearer, method)(path, **({"json": body} if body else {}))
            assert resp.status_code == 403, (method, path, resp.text)
            assert resp.json()["code"] == "TOKEN_WRITE_FORBIDDEN"

    def test_read_scope_cannot_download(self, make_client):
        read = make_client(token=_create_token(make_client("DATA_ENGINEER"), "READ")["token"])
        resp = read.get("/api/products/999999/download")
        assert resp.status_code == 403 and resp.json()["code"] == "TOKEN_SCOPE_FORBIDDEN"
        dl = make_client(token=_create_token(make_client("DATA_ENGINEER"), "READ_DOWNLOAD")["token"])
        assert dl.get("/api/products/999999/download").status_code == 404  # lolos auth

    def test_revoked_expired_invalid_tokens_rejected(self, make_client, db_client):
        owner = make_client("USER")
        revoked = _create_token(owner)
        assert owner.delete(f"/api/auth/tokens/{revoked['token_id']}").status_code == 200
        assert owner.delete(f"/api/auth/tokens/{revoked['token_id']}").json()["code"] == "TOKEN_ALREADY_REVOKED"
        resp = make_client(token=revoked["token"]).get("/api/auth/me")
        assert resp.status_code == 401 and resp.json()["code"] == "TOKEN_REVOKED"

        expired = _create_token(owner)
        _db(db_client, "UPDATE api_tokens SET created_at = now() - interval '10 days', "
                       "expires_at = now() - interval '1 second' WHERE token_id = :t", t=expired["token_id"])
        resp = make_client(token=expired["token"]).get("/api/auth/me")
        assert resp.status_code == 401 and resp.json()["code"] == "TOKEN_EXPIRED"

        for bad in (expired["token"][:-1] + ("A" if expired["token"][-1] != "A" else "B"), "trn_nonsense123", "abc"):
            resp = make_client(token=bad).get("/api/auth/me")
            assert resp.status_code == 401 and resp.json()["code"] == "TOKEN_INVALID", bad

    def test_inactive_owner_token_rejected(self, make_client, user_factory, db_client):
        _, uid = user_factory("USER")
        token = _create_token(make_client(user_id=uid))["token"]
        _db(db_client, "UPDATE users SET is_active = false WHERE user_id = :u", u=uid)
        resp = make_client(token=token).get("/api/auth/me")
        assert resp.status_code == 401 and resp.json()["code"] == "ACCOUNT_INACTIVE"

    def test_other_user_cannot_revoke_but_admin_can(self, make_client):
        mine = _create_token(make_client("ANALYST"))
        other = make_client("DATA_ENGINEER").delete(f"/api/auth/tokens/{mine['token_id']}")
        assert other.status_code == 404  # tidak membocorkan keberadaan (RLS)
        assert make_client("ADMIN").delete(f"/api/auth/tokens/{mine['token_id']}").status_code == 200

    def test_rate_limit_120_per_minute(self, make_client, monkeypatch):
        from api.security import token_rate_limiter
        assert token_rate_limiter.limit == 120 and token_rate_limiter.window_s == 60
        monkeypatch.setattr(token_rate_limiter, "limit", 3)
        bearer = make_client(token=_create_token(make_client("USER"))["token"])
        codes = [bearer.get("/api/auth/me").status_code for _ in range(4)]
        assert codes == [200, 200, 200, 429]
        resp = bearer.get("/api/auth/me")
        assert resp.json()["code"] == "RATE_LIMITED" and resp.headers["retry-after"] == "60"

    def test_token_use_logged_and_last_used_updated(self, make_client, db_client, role_users):
        created = _create_token(make_client("USER"))
        make_client(token=created["token"]).get("/api/auth/me")
        rows = _activity(db_client, "API_REQUEST", user_id=role_users["USER"])
        mine = [r for r in rows if r["detail"].get("token_id") == created["token_id"]]
        assert len(mine) == 1
        assert mine[0]["detail"]["auth"] == "token" and mine[0]["detail"]["path"] == "/api/auth/me"
        assert mine[0]["detail"]["status"] == 200
        used = _db(db_client, "SELECT last_used_at FROM api_tokens WHERE token_id = :t",
                   t=created["token_id"]).scalar()
        assert used is not None


# --- log unduhan --------------------------------------------------------------

@pytest.fixture
def product_file(db_client, sample_region, tmp_path):
    """Satu produk COG dengan berkas nyata di disk."""
    from etl.seed_data import seed
    ids = seed(db_client)
    path = tmp_path / "product.tif"
    path.write_bytes(b"x" * 12345)
    _db(db_client, "UPDATE data_products SET file_path = :p WHERE product_id = :i", p=str(path), i=ids["gold_fusion_id"])
    return ids["gold_fusion_id"], 12345


class TestDownloadLog:

    def test_session_download_logged_with_bytes(self, make_client, product_file, db_client, role_users):
        product_id, size = product_file
        resp = make_client("DATA_ENGINEER").get(f"/api/products/{product_id}/download")
        assert resp.status_code == 200 and len(resp.content) == size
        rows = [r for r in _activity(db_client, "DOWNLOAD_FUSION", user_id=role_users["DATA_ENGINEER"])
                + _activity(db_client, "DOWNLOAD_PRODUCT", user_id=role_users["DATA_ENGINEER"])
                if r["target_id"] == product_id]
        assert rows, "download not logged"
        log = rows[-1]
        assert log["bytes_sent"] == size
        assert log["target_type"] == "data_products"
        assert log["detail"]["complete"] is True and log["detail"]["auth"] == "session"

    def test_token_download_logged_once_with_auth_token(self, make_client, product_file, db_client, role_users):
        product_id, size = product_file
        created = _create_token(make_client("ADMIN"), "READ_DOWNLOAD")
        resp = make_client(token=created["token"]).get(f"/api/products/{product_id}/download")
        assert resp.status_code == 200
        uid = role_users["ADMIN"]
        downloads = [r for r in _activity(db_client, "DOWNLOAD_FUSION", user_id=uid)
                     + _activity(db_client, "DOWNLOAD_PRODUCT", user_id=uid)
                     if r["detail"].get("token_id") == created["token_id"]]
        assert len(downloads) == 1 and downloads[0]["bytes_sent"] == size
        assert downloads[0]["detail"]["auth"] == "token"
        api_rows = [r for r in _activity(db_client, "API_REQUEST", user_id=uid)
                    if r["detail"].get("token_id") == created["token_id"]]
        assert api_rows == []  # satu baris per pemakaian (S6)

    def test_failed_download_not_logged(self, make_client, db_client, role_users):
        before = len(_activity(db_client, "DOWNLOAD_PRODUCT", user_id=role_users["DATA_ENGINEER"]))
        assert make_client("DATA_ENGINEER").get("/api/products/999999/download").status_code == 404
        assert len(_activity(db_client, "DOWNLOAD_PRODUCT", user_id=role_users["DATA_ENGINEER"])) == before


def test_error_format_has_detail_and_code(make_client):
    resp = make_client("DATA_ENGINEER").get("/api/products/999999")
    assert resp.status_code == 404
    body = resp.json()
    assert set(body) == {"detail", "code"} and body["code"] == "NOT_FOUND"
    resp = make_client("DATA_ENGINEER").get("/api/products?tier=INVALID")
    assert "code" in resp.json() and "detail" in resp.json()


class TestRegisterAndSession:
    """Registrasi mandiri dan /auth/session (M56)."""

    @pytest.fixture(autouse=True)
    def _fresh_limiter(self):
        from api.routes.auth import register_rate_limiter
        register_rate_limiter.reset()
        yield
        register_rate_limiter.reset()

    @staticmethod
    def _body(name, **kw):
        return {"email": f"{name}@example.org", "username": name, "password": TEST_PASSWORD,
                "password_confirm": TEST_PASSWORD, **kw}

    def test_register_creates_signed_in_user(self, make_client, db_client):
        name = f"reg_{int(time.time() * 1000) % 10_000_000}"
        client = make_client(None)
        r = client.post("/api/auth/register", json=self._body(name, email=f"{name.upper()}@Example.org"))
        assert r.status_code == 201, r.text
        assert r.json()["role_code"] == "USER" and "account.manage" in r.json()["permissions"]
        assert "orbit_u_session" in r.cookies
        assert client.get("/api/auth/me").json()["username"] == name
        with db_client.session() as sess:
            row = sess.execute(text("""SELECT u.email, r.role_code, u.created_by FROM users u
                                       JOIN roles r USING (role_id) WHERE username = :u"""), {"u": name}).one()
        assert row == (f"{name}@example.org", "USER", None)
        assert _activity(db_client, "REGISTER", username=None, user_id=None) is not None

    def test_role_cannot_be_chosen(self, make_client, db_client):
        name = f"reg_{int(time.time() * 1000) % 10_000_000}r"
        r = make_client(None).post("/api/auth/register", json=self._body(name, role_code="ADMIN"))
        assert r.status_code == 201 and r.json()["role_code"] == "USER"

    def test_validation_and_duplicates(self, make_client):
        name = f"reg_{int(time.time() * 1000) % 10_000_000}d"
        anon = make_client(None)
        r = anon.post("/api/auth/register", json=self._body(name, password_confirm="beda-sekali-123"))
        assert (r.status_code, r.json()["code"]) == (400, "PASSWORD_MISMATCH")
        r = anon.post("/api/auth/register", json=self._body(name, password="pendek", password_confirm="pendek"))
        assert (r.status_code, r.json()["code"]) == (400, "PASSWORD_POLICY")
        assert anon.post("/api/auth/register", json=self._body(name, email="bukan-email")).status_code == 422
        assert anon.post("/api/auth/register", json=self._body(name)).status_code == 201
        r = make_client(None).post("/api/auth/register", json=self._body(name, email=f"lain_{name}@example.org"))
        assert (r.status_code, r.json()["code"]) == (409, "USERNAME_TAKEN")
        r = make_client(None).post("/api/auth/register", json=self._body(name + "x", email=f"{name}@EXAMPLE.org"))
        assert (r.status_code, r.json()["code"]) == (409, "EMAIL_TAKEN")

    def test_rate_limited_per_address(self, make_client):
        base = f"rl_{int(time.time() * 1000) % 10_000_000}"
        codes = [make_client(None).post("/api/auth/register", json=self._body(f"{base}_{i}")).status_code
                 for i in range(6)]
        assert codes[:5] == [201] * 5 and codes[5] == 429

    def test_session_endpoint_for_visitor_and_user(self, make_client):
        anon = make_client(None).get("/api/auth/session")
        assert anon.status_code == 200
        body = anon.json()
        assert body["authenticated"] is False and body["role_code"] == "PUBLIC" and body["user"] is None
        assert {"home.view", "citra.view", "disasters.view", "about.view"} <= set(body["permissions"])
        assert "aoi3d.view" not in body["permissions"]
        user = make_client("USER").get("/api/auth/session").json()
        assert user["authenticated"] is True and user["user"]["role_code"] == "USER"
        assert "aoi3d.view" in user["permissions"] and "diagram.view" not in user["permissions"]
        analyst = make_client("ANALYST").get("/api/auth/session").json()["permissions"]
        assert {"diagram.view", "disasters.manage", "logs.disasters"} <= set(analyst)
        assert "logs.data" not in analyst and "datasets.manage" not in analyst
        de = make_client("DATA_ENGINEER").get("/api/auth/session").json()["permissions"]
        assert {"datasets.manage", "eda.view", "logs.data"} <= set(de) and "diagram.view" not in de
