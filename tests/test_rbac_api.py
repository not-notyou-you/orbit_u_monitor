# tests/test_rbac_api.py
"""Kontrol akses API: setiap endpoint × setiap role (INTERFACE.md §3, §4).

Tabel EXPECTED ditulis tangan dari INTERFACE.md, bukan dibaca dari kode,
supaya tes ini membuktikan kode sesuai dokumen. Endpoint baru yang belum
dicantumkan membuat test_every_route_is_declared gagal.

Lapis yang diuji (INTERFACE.md §3.2):
  * lapis 2 (API): anonim -> 401, role kurang -> 403 ROLE_FORBIDDEN, role
    cukup -> tidak pernah 401/403 karena role;
  * lapis 3 (DB): dengan require_role dimatikan, PostgreSQL sendiri menolak
    (403 DB_PERMISSION_DENIED) karena request berjalan dengan SET LOCAL ROLE.
"""

from __future__ import annotations

import re
import time
from datetime import date, timedelta

import pytest
from fastapi.routing import APIRoute
from sqlalchemy import text

ROLES = ("USER", "ANALYST", "DATA_ENGINEER", "ADMIN")
INCLUDES = {
    "PUBLIC": {"PUBLIC", "USER", "ANALYST", "DATA_ENGINEER", "ADMIN"},
    "USER": {"USER", "ANALYST", "DATA_ENGINEER", "ADMIN"},
    "ANALYST": {"ANALYST", "ADMIN"},
    "DATA_ENGINEER": {"DATA_ENGINEER", "ADMIN"},
    "ADMIN": {"ADMIN"},
}

P, U, AN, DE, A = "PUBLIC", "USER", "ANALYST", "DATA_ENGINEER", "ADMIN"
DL = "download"

# (metode, path) -> role minimum [, "download"]
EXPECTED: dict[tuple[str, str], tuple] = {
    # info & health (§4.2)
    ("GET", "/api"): (P,),
    ("GET", "/api/health"): (P,),
    # autentikasi (§4.1)
    ("POST", "/api/auth/login"): (P,),
    ("POST", "/api/auth/logout"): (U,),
    ("GET", "/api/auth/me"): (U,),
    ("POST", "/api/auth/change-password"): (U,),
    ("GET", "/api/auth/tokens"): (U,),
    ("POST", "/api/auth/tokens"): (U,),
    ("DELETE", "/api/auth/tokens/{token_id}"): (U,),
    # administrasi akun & log (§4.9)
    ("GET", "/api/admin/users"): (A,),
    ("POST", "/api/admin/users"): (A,),
    ("PATCH", "/api/admin/users/{user_id}"): (A,),
    ("POST", "/api/admin/users/{user_id}/reset-password"): (A,),
    ("POST", "/api/admin/users/{user_id}/unlock"): (A,),
    ("GET", "/api/admin/tokens"): (A,),
    ("GET", "/api/admin/logs/login"): (A,),
    ("GET", "/api/admin/logs/download"): (A,),
    ("GET", "/api/admin/audit"): (A,),
    # dataset, scene, produk, kualitas, lineage, pipeline (§4.7)
    ("GET", "/api/scenes"): (DE,),
    ("GET", "/api/scenes/{scene_id}"): (DE,),
    ("GET", "/api/scenes/{scene_id}/status"): (DE,),
    ("GET", "/api/products"): (DE,),
    ("GET", "/api/products/{product_id}"): (DE,),
    ("GET", "/api/products/{product_id}/download"): (DE, DL),
    ("GET", "/api/products/{product_id}/verify"): (DE,),
    ("GET", "/api/quality/{scene_id}"): (DE,),
    ("GET", "/api/quality/summary/stats"): (DE,),
    ("GET", "/api/quality/dataset/{dataset_id}/by-source"): (DE,),
    ("GET", "/api/metadata/lineage/{product_id}"): (DE,),
    ("GET", "/api/pipeline/status/current"): (DE,),
    ("POST", "/api/pipeline/trigger"): (DE,),
    ("POST", "/api/datasets"): (DE,),
    ("GET", "/api/datasets/last-config"): (DE,),
    ("GET", "/api/datasets"): (DE,),
    ("GET", "/api/datasets/{dataset_id}"): (DE,),
    ("GET", "/api/datasets/{dataset_id}/status"): (DE,),
    ("POST", "/api/datasets/{dataset_id}/pause"): (DE,),
    ("POST", "/api/datasets/{dataset_id}/resume"): (DE,),
    ("POST", "/api/datasets/{dataset_id}/cancel"): (DE,),
    ("GET", "/api/datasets/{dataset_id}/logs"): (DE,),
    ("DELETE", "/api/datasets/{dataset_id}"): (DE,),   # + pembuat/ADMIN (tes terpisah)
    ("GET", "/api/datasets/{dataset_id}/deletion-progress"): (DE,),
    ("GET", "/api/datasets/{dataset_id}/download"): (DE, DL),
    ("GET", "/api/datasets/{dataset_id}/metadata"): (DE,),
    ("GET", "/api/datasets/{dataset_id}/preview"): (DE,),
    ("GET", "/api/datasets/{dataset_id}/preview/{scene}/{level}/{kind}/{filename}"): (DE,),
    ("GET", "/api/datasets/{dataset_id}/preview/{scene}/{kind}/{filename}"): (DE,),
    ("GET", "/api/datasets/{dataset_id}/storage/by-source"): (DE,),
    ("GET", "/api/datasets/{dataset_id}/storage/summary"): (DE,),
    ("GET", "/api/datasets/{dataset_id}/storage/files/{tier}"): (DE,),
    ("GET", "/api/datasets/{dataset_id}/report"): (DE, DL),
    ("GET", "/api/datasets/{dataset_id}/report/json"): (DE, DL),
    # storage seluruh mesin (Tahap 2, S5)
    ("GET", "/api/storage/summary"): (A,),
    ("GET", "/api/storage/files/{tier}"): (A,),
    # Live (§4.3)
    ("GET", "/api/live/areas"): (U,),
    ("POST", "/api/live/areas"): (A,),
    ("GET", "/api/live/areas/{area_id}"): (U,),
    ("PATCH", "/api/live/areas/{area_id}"): (A,),
    ("DELETE", "/api/live/areas/{area_id}"): (A,),
    ("POST", "/api/live/areas/{area_id}/check"): (A,),
    ("GET", "/api/live/areas/{area_id}/card"): (U,),
    ("GET", "/api/live/areas/{area_id}/preview/{scene_date}/{key}.png"): (U,),
    ("GET", "/api/live/areas/{area_id}/events"): (A,),
    ("GET", "/api/live/areas/{area_id}/activity"): (A,),
    ("GET", "/api/live/areas/{area_id}/log"): (A,),
    ("POST", "/api/live/areas/{area_id}/scenes/{scene_date}/retry"): (A,),
    # wilayah (§4.4)
    ("GET", "/api/regions"): (U,),
    ("GET", "/api/rois"): (U,),
    # publik (§4.2, Tahap 3)
    ("GET", "/api/public/live"): (P,),
    ("GET", "/api/public/live/{area_id}/preview/{key}.png"): (P,),
    # hidromet (§4.4)
    ("GET", "/api/hydromet/today"): (U,),
    ("GET", "/api/hydromet/observations"): (U,),
    ("GET", "/api/hydromet/trend"): (U,),
    ("GET", "/api/hydromet/observations.csv"): (AN, DL),
    # alert (§4.5)
    ("GET", "/api/alerts"): (U,),
    ("GET", "/api/alerts/evaluation"): (AN,),
    ("POST", "/api/alerts/{alert_id}/acknowledge"): (AN,),
    ("GET", "/api/alert-rules"): (U,),
    ("POST", "/api/alert-rules"): (A,),
    ("PUT", "/api/alert-rules/{rule_id}"): (A,),
    # kejadian bencana (§4.6)
    ("GET", "/api/disasters"): (AN,),
    ("POST", "/api/disasters"): (AN,),
    ("GET", "/api/disasters/{event_id}"): (AN,),
    ("PUT", "/api/disasters/{event_id}"): (AN,),
    ("DELETE", "/api/disasters/{event_id}"): (AN,),
    ("GET", "/api/disaster-types"): (U,),
    ("POST", "/api/disaster-types"): (A,),
    ("PUT", "/api/disaster-types/{type_id}"): (A,),
    # laporan periodik (§4.8): audiens ANALYST/DATA_ENGINEER dicek di route
    # (REPORT_AUDIENCE) karena keduanya tidak bertingkat.
    ("GET", "/api/reports"): (U,),
    ("GET", "/api/reports/{report_id}/download"): (U, DL),
    ("POST", "/api/reports/regenerate"): (A,),
    # administrasi wilayah & ingest (§4.9)
    ("GET", "/api/admin/regions"): (A,),
    ("PATCH", "/api/admin/regions/{region_id}"): (A,),
    ("POST", "/api/admin/rois"): (A,),
    ("POST", "/api/admin/ingest"): (A,),
    ("PATCH", "/api/admin/scenes/{source}/{scene_id}"): (A,),
    ("POST", "/api/admin/scenes/{source}/{scene_id}/reprocess"): (A,),
    ("GET", "/api/admin/quality-thresholds"): (A,),
    ("PUT", "/api/admin/quality-thresholds"): (A,),
    ("GET", "/api/admin/settings"): (A,),
    ("PUT", "/api/admin/settings"): (A,),
    ("GET", "/api/admin/pipeline/status"): (A,),
    ("GET", "/api/admin/archive/stats"): (A,),
    ("POST", "/api/admin/archive/verify"): (A,),
    # ekspor/impor Excel (Tahap 3): role per jenis data dicek di route (ENTITY_FORBIDDEN)
    ("GET", "/api/excel"): (U,),
    ("GET", "/api/excel/{entity}.xlsx"): (U, DL),
    ("GET", "/api/excel/{entity}/template.xlsx"): (U,),
    ("POST", "/api/excel/{entity}/import"): (U,),
}

PATH_VALUES = {
    "scene_date": "2026-01-01", "key": "vv", "tier": "raw", "scene": "20260101",
    "level": "processed", "kind": "grayscale", "filename": "x.png", "entity": "alerts", "source": "GPM",
}
# 403 yang sah walau role cukup: aturan bisnis, bukan role.
BUSINESS_403 = {"NOT_DATASET_OWNER", "SCENE_OUT_OF_RANGE", "CANNOT_MODIFY_SELF", "REPORT_AUDIENCE",
                "DATE_OUT_OF_RANGE", "SCENE_NOT_PUBLIC", "ENTITY_FORBIDDEN"}
ROLE_DENIAL_CODES = {"NOT_AUTHENTICATED", "ROLE_FORBIDDEN", "DB_PERMISSION_DENIED"}


def _api_routes():
    from api.main import app
    out = []
    for r in app.routes:
        if isinstance(r, APIRoute) and r.path.startswith("/api"):
            for m in sorted(r.methods):
                out.append((m, r.path, r))
    return out


def _fill(path: str) -> str:
    def repl(m):
        name = m.group(1)
        return "999999" if name.endswith("_id") else PATH_VALUES[name]
    return re.sub(r"\{(\w+)\}", repl, path)


def _call(client, method: str, path: str):
    url = _fill(path)
    if method in ("GET", "DELETE"):
        return getattr(client, method.lower())(url)
    return client.request(method, url, json={})


ALL_ROUTES = [(m, p) for m, p, _ in _api_routes()]


def test_every_route_is_declared():
    """Setiap route /api punya role eksplisit di kode dan di tabel EXPECTED."""
    from api.main import route_min_roles
    order = ("PUBLIC", "USER", "ANALYST", "DATA_ENGINEER", "ADMIN")
    actual = {}
    for method, path, route in _api_routes():
        roles = route_min_roles(route)
        assert roles, f"{method} {path} has no require_role dependency"
        strongest = max((r for r, _ in roles), key=order.index)
        download = any(d for _, d in roles)
        actual[(method, path)] = (strongest, DL) if download else (strongest,)
    assert set(actual) == set(EXPECTED), (
        f"undeclared: {sorted(set(actual) - set(EXPECTED))}; stale: {sorted(set(EXPECTED) - set(actual))}")
    mismatched = {k: (EXPECTED[k], v) for k, v in actual.items() if EXPECTED[k] != v}
    assert not mismatched, mismatched


def test_openapi_documents_min_role():
    from api.main import app
    app.openapi_schema = None
    schema = app.openapi()
    op = schema["paths"]["/api/datasets/{dataset_id}/download"]["get"]
    assert op["x-min-role"] == "DATA_ENGINEER" and op["x-download"] is True
    assert schema["paths"]["/api/admin/audit"]["get"]["x-min-role"] == "ADMIN"


@pytest.mark.parametrize("method,path", ALL_ROUTES, ids=[f"{m} {p}" for m, p in ALL_ROUTES])
def test_endpoint_x_role(method, path, make_client, monkeypatch):
    """Satu endpoint dipanggil anonim dan oleh keempat role login."""
    # Endpoint tulis tidak boleh benar-benar memulai job/siklus di tes ini.
    from etl.dataset_manager import DatasetManager
    from etl.live_monitor import LiveMonitor
    monkeypatch.setattr(DatasetManager, "_spawn_job_runner", lambda self, job_id: None)
    monkeypatch.setattr(DatasetManager, "_spawn_deletion_runner", lambda self, *a, **k: None)
    monkeypatch.setattr(LiveMonitor, "start_cycle", lambda self, area_id: False)
    monkeypatch.setattr(LiveMonitor, "retry_scene", lambda self, area_id, d: False)

    min_role = EXPECTED[(method, path)][0]
    results = {}
    for who in (None, *ROLES):
        resp = _call(make_client(who), method, path)
        body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        code = body.get("code") if isinstance(body, dict) else None
        results[who or "ANON"] = (resp.status_code, code)

        assert resp.status_code != 500, (who, resp.text)
        allowed = (who or "PUBLIC") in INCLUDES[min_role]
        if allowed:
            assert resp.status_code != 401, (who, resp.text)
            assert code not in ROLE_DENIAL_CODES, (who, resp.text)
            if resp.status_code == 403:
                assert code in BUSINESS_403, (who, resp.text)
        elif who is None:
            assert resp.status_code == 401 and code == "NOT_AUTHENTICATED", resp.text
        else:
            assert resp.status_code == 403 and code == "ROLE_FORBIDDEN", (who, resp.text)


def test_read_token_respects_scope_and_write_ban(make_client, monkeypatch):
    """Token READ milik ADMIN: GET non-unduhan lolos, unduhan 403 scope,
    semua aksi tulis 403 TOKEN_WRITE_FORBIDDEN."""
    from etl.live_monitor import LiveMonitor
    monkeypatch.setattr(LiveMonitor, "start_cycle", lambda self, area_id: False)
    created = make_client("ADMIN").post("/api/auth/tokens", json={"name": "rbac", "scope": "READ"}).json()
    bearer = make_client(token=created["token"], csrf=False)
    for method, path in ALL_ROUTES:
        expected = EXPECTED[(method, path)]
        if path == "/api/auth/login":
            continue
        resp = _call(bearer, method, path)
        body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else None
        code = body.get("code") if isinstance(body, dict) else None
        if method != "GET":
            assert (resp.status_code, code) == (403, "TOKEN_WRITE_FORBIDDEN"), (method, path, resp.text)
        elif DL in expected:
            assert (resp.status_code, code) == (403, "TOKEN_SCOPE_FORBIDDEN"), (method, path, resp.text)
        else:
            assert resp.status_code not in (401, 403, 429, 500), (method, path, resp.text)


# --- lapis 3: PostgreSQL menolak walau lapis API dimatikan --------------------

LAYER3_CASES = [
    ("USER", "GET", "/api/datasets"),
    ("USER", "GET", "/api/products"),
    ("USER", "GET", "/api/scenes"),
    ("USER", "GET", "/api/admin/users"),
    ("USER", "GET", "/api/admin/audit"),
    ("USER", "GET", "/api/admin/logs/login"),
    ("ANALYST", "GET", "/api/datasets"),
    ("ANALYST", "GET", "/api/metadata/lineage/1"),
    ("DATA_ENGINEER", "GET", "/api/admin/users"),
    ("DATA_ENGINEER", "GET", "/api/admin/logs/download"),
]


@pytest.mark.parametrize("role,method,path", LAYER3_CASES, ids=[f"{r}-{p}" for r, _, p in LAYER3_CASES])
def test_layer3_database_rejects_when_api_check_disabled(role, method, path, make_client, monkeypatch, seeded_product):
    from api import deps
    client = make_client(role)
    # Lapis 2 aktif: ditolak API.
    resp = client.request(method, path)
    assert (resp.status_code, resp.json()["code"]) == (403, "ROLE_FORBIDDEN")
    # Lapis 2 dimatikan: PostgreSQL yang menolak.
    monkeypatch.setattr(deps, "ROLE_CHECKS_ENABLED", False)
    resp = client.request(method, path)
    assert resp.status_code == 403, resp.text
    assert resp.json()["code"] == "DB_PERMISSION_DENIED", resp.text


def test_layer3_rls_hides_other_users_tokens(make_client, monkeypatch, role_users):
    """api_tokens: DATA_ENGINEER punya GRANT (token miliknya), jadi tanpa
    lapis API penolakannya datang dari RLS tok_owner: hanya baris sendiri."""
    from api import deps
    make_client("ANALYST").post("/api/auth/tokens", json={"name": "rls", "scope": "READ"})
    mine = make_client("DATA_ENGINEER").post("/api/auth/tokens", json={"name": "rls", "scope": "READ"}).json()
    monkeypatch.setattr(deps, "ROLE_CHECKS_ENABLED", False)
    items = make_client("DATA_ENGINEER").get("/api/admin/tokens?limit=500").json()["items"]
    assert items and {i["user_id"] for i in items} == {role_users["DATA_ENGINEER"]}
    assert mine["token_id"] in {i["token_id"] for i in items}


def test_layer3_write_rejected_by_database(make_client, monkeypatch, sample_region):
    """USER mencoba membuat Live Area (aksi ADMIN) tanpa lapis API."""
    from api import deps
    monkeypatch.setattr(deps, "ROLE_CHECKS_ENABLED", False)
    resp = make_client("USER").post("/api/live/areas", json={"region_id": sample_region, "name": "x"})
    assert resp.status_code == 403 and resp.json()["code"] == "DB_PERMISSION_DENIED", resp.text


def test_layer3_analyst_cannot_create_dataset(make_client, monkeypatch, sample_region):
    from api import deps
    monkeypatch.setattr(deps, "ROLE_CHECKS_ENABLED", False)
    body = {"name": f"rbac-{time.time()}", "region_id": sample_region, "date_start": "2024-01-01",
            "date_end": "2024-01-05", "sources": {"sentinel1": {"processing": ["PROCESSED"]}}}
    resp = make_client("ANALYST").post("/api/datasets", json=body)
    assert resp.status_code == 403 and resp.json()["code"] == "DB_PERMISSION_DENIED", resp.text


@pytest.fixture(scope="module")
def seeded_product(db_client, sample_region):
    from etl.seed_data import seed
    return seed(db_client)


# --- aturan dataset (§4.7) ----------------------------------------------------

def _insert_dataset(db_client, sample_region, created_by, is_system=False, name=None):
    with db_client.session() as sess:
        return sess.scalar(text("""
            INSERT INTO datasets (name, region_id, bbox, bbox_wkt, date_start, date_end, created_by, is_system)
            VALUES (:n, :r, ST_GeomFromText('POLYGON((106 -7,106.1 -7,106.1 -6.9,106 -6.9,106 -7))', 4326),
                    'POLYGON((106 -7,106.1 -7,106.1 -6.9,106 -6.9,106 -7))', '2024-01-01', '2024-01-02', :c, :s)
            RETURNING dataset_id"""),
            {"n": name or f"rbac_ds_{time.time_ns()}", "r": sample_region, "c": created_by, "s": is_system})


def test_dataset_list_hides_system_and_shows_creator(make_client, db_client, sample_region, role_users):
    de = role_users["DATA_ENGINEER"]
    mine = _insert_dataset(db_client, sample_region, de)
    system = _insert_dataset(db_client, sample_region, None, is_system=True)
    items = make_client("DATA_ENGINEER").get("/api/datasets?limit=200").json()["items"]
    by_id = {i["dataset_id"]: i for i in items}
    assert system not in by_id
    assert by_id[mine]["created_by"] == de and by_id[mine]["created_by_name"]


def test_dataset_delete_only_by_creator_or_admin(make_client, db_client, sample_region, role_users, user_factory_de):
    owner = role_users["DATA_ENGINEER"]
    ds = _insert_dataset(db_client, sample_region, owner)
    other = make_client(user_id=user_factory_de)
    resp = other.delete(f"/api/datasets/{ds}")
    assert resp.status_code == 403 and resp.json()["code"] == "NOT_DATASET_OWNER"

    resp = make_client("DATA_ENGINEER").delete(f"/api/datasets/{ds}")
    assert resp.status_code == 200 and resp.json()["status"] == "DELETING", resp.text
    # Penghapusan fisik oleh pipeline (monitor_etl) setelah commit (S1).
    assert _wait_gone(db_client, ds), "dataset row not deleted by the ETL deletion runner"

    ds2 = _insert_dataset(db_client, sample_region, owner)
    assert make_client("ADMIN").delete(f"/api/datasets/{ds2}").status_code == 200
    assert _wait_gone(db_client, ds2)

    audit = _scalar(db_client, """SELECT db_user FROM audit_log WHERE table_name = 'datasets'
                                  AND row_pk = :pk AND operation = 'D'""", pk=str(ds))
    assert audit == "monitor_etl"
    status_change = _scalar(db_client, """SELECT app_user_id FROM audit_log WHERE table_name = 'datasets'
                                          AND row_pk = :pk AND operation = 'U' ORDER BY audit_id LIMIT 1""",
                            pk=str(ds))
    assert status_change == owner


@pytest.fixture
def user_factory_de(db_client, test_password_hash):
    from tests.conftest import create_test_user
    return create_test_user(db_client, f"de_other_{time.time_ns() % 10**9}", "DATA_ENGINEER", test_password_hash)


def _scalar(db_client, sql, **params):
    with db_client.session() as sess:
        return sess.scalar(text(sql), params)


def _wait_gone(db_client, dataset_id, timeout=20.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if _scalar(db_client, "SELECT count(*) FROM datasets WHERE dataset_id = :d", d=dataset_id) == 0:
            return True
        time.sleep(0.2)
    return False


def test_last_config_is_per_user(make_client, db_client, sample_region, role_users, user_factory_de):
    _insert_dataset(db_client, sample_region, role_users["DATA_ENGINEER"], name=f"lc_{time.time_ns()}")
    assert make_client(user_id=user_factory_de).get("/api/datasets/last-config").status_code == 404
    assert make_client("DATA_ENGINEER").get("/api/datasets/last-config").status_code == 200


# --- Live: USER dibatasi 30 hari (§4.3) ---------------------------------------

@pytest.fixture
def live_area_with_scenes(db_client):
    today = date.today()
    with db_client.session() as sess:
        area = sess.scalar(text("""
            INSERT INTO live_areas (name, bbox_wkt, status) VALUES ('rbac area', 'POLYGON((0 0,1 0,1 1,0 1,0 0))', 'ACTIVE')
            RETURNING area_id"""))
        for d in (today - timedelta(days=5), today - timedelta(days=45), today - timedelta(days=90)):
            sess.execute(text("INSERT INTO live_scenes (area_id, scene_date, status) VALUES (:a, :d, 'READY')"),
                         {"a": area, "d": d})
    return area, today


def test_live_card_user_window(make_client, live_area_with_scenes):
    area, today = live_area_with_scenes
    recent, old = (today - timedelta(days=5)).isoformat(), (today - timedelta(days=45)).isoformat()

    user = make_client("USER")
    card = user.get(f"/api/live/areas/{area}/card").json()
    assert [d["date"] for d in card["dates"]] == [recent]
    resp = user.get(f"/api/live/areas/{area}/card?date={old}")
    assert resp.status_code == 403 and resp.json()["code"] == "SCENE_OUT_OF_RANGE"
    resp = user.get(f"/api/live/areas/{area}/preview/{old}/vv.png")
    assert resp.status_code == 403

    admin = make_client("ADMIN")
    assert len(admin.get(f"/api/live/areas/{area}/card").json()["dates"]) == 3
    assert admin.get(f"/api/live/areas/{area}/card?date={old}").status_code == 200


def test_live_area_backed_by_dataset_readable_by_user(make_client, db_client, sample_region, role_users):
    """Tahap 4: area Live nyata selalu punya `dataset_id`; USER tidak punya SELECT
    pada `datasets` (§8.3), jadi daftar/kartu tidak boleh membaca tabel itu untuknya
    (dulu 403 DB_PERMISSION_DENIED). Ukuran berkas hanya untuk role yang berhak."""
    ds = _insert_dataset(db_client, sample_region, role_users["ADMIN"], is_system=True, name="rbac live ds")
    with db_client.session() as sess:
        sess.execute(text("UPDATE datasets SET total_size_bytes = 4096 WHERE dataset_id = :d"), {"d": ds})
        area = sess.scalar(text("""
            INSERT INTO live_areas (dataset_id, name, bbox_wkt, status)
            VALUES (:d, 'rbac live ds area', 'POLYGON((0 0,1 0,1 1,0 1,0 0))', 'ACTIVE') RETURNING area_id"""), {"d": ds})
        sess.execute(text("INSERT INTO live_scenes (area_id, scene_date, status) VALUES (:a, CURRENT_DATE, 'READY')"), {"a": area})
    for role, size in (("USER", 0), ("ANALYST", 0), ("ADMIN", 4096)):
        c = make_client(role)
        r = c.get("/api/live/areas")
        assert r.status_code == 200, (role, r.text)
        mine = next(a for a in r.json() if a["area_id"] == area)
        assert mine["total_size_bytes"] == size, role
        card = c.get(f"/api/live/areas/{area}/card")
        assert card.status_code == 200, (role, card.text)
        assert "water_change" in card.json()["scene"]


def test_live_preview_readable_by_user_and_analyst(make_client, db_client, etl_db_client, sample_region, role_users, tmp_path, monkeypatch):
    """Tahap 4: preview Live untuk USER/ANALYST dulu 403 DB_PERMISSION_DENIED karena
    path dicari lewat `datasets`. Kini path dicari koneksi etl setelah scene terbukti terlihat."""
    from etl import live_monitor as lm

    ds = _insert_dataset(db_client, sample_region, role_users["ADMIN"], is_system=True, name="rbac preview ds")
    with db_client.session() as sess:
        area = sess.scalar(text("""
            INSERT INTO live_areas (dataset_id, name, bbox_wkt, status)
            VALUES (:d, 'rbac preview area', 'POLYGON((0 0,1 0,1 1,0 1,0 0))', 'ACTIVE') RETURNING area_id"""), {"d": ds})
        sess.execute(text("INSERT INTO live_scenes (area_id, scene_date, status) VALUES (:a, CURRENT_DATE, 'READY')"), {"a": area})
    png = tmp_path / "s1_vv.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    seen = {}

    def fake_preview_path(self, area_id, scene_date, key):
        # Tanpa SET ROLE: koneksi etl boleh membaca datasets.
        with self._db.session() as s:
            seen["folder_ok"] = s.scalar(text("SELECT count(*) FROM datasets WHERE dataset_id = :d"), {"d": ds}) == 1
        return png

    monkeypatch.setattr(lm.LiveMonitor, "preview_path", fake_preview_path)
    for role in ("USER", "ANALYST"):
        r = make_client(role).get(f"/api/live/areas/{area}/preview/{date.today().isoformat()}/s1_vv.png")
        assert r.status_code == 200, (role, r.text)
        assert seen.pop("folder_ok")
    r = make_client("USER").get(f"/api/live/areas/{area}/preview/{(date.today() - timedelta(days=1)).isoformat()}/s1_vv.png")
    assert r.status_code == 404
