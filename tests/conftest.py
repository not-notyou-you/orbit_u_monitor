# tests/conftest.py
"""
pytest fixtures and test database setup/teardown.
Used by all test modules in the tests/ directory.

Author : Julius Marselinus (BRONTO) - NIM 00000111989
Program: Sistem Informasi - Universitas Multimedia Nusantara

Run:
    pytest tests/ -v --cov=etl --cov=api
"""

from __future__ import annotations

import os
import pytest
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

# Test tidak boleh melanjutkan job produksi saat lifespan API berjalan.
os.environ["AUTO_RESUME_JOBS"] = "false"
# M64: test TIDAK PERNAH mengirim email sungguhan walau .env berisi kredensial
# SMTP -- pesan ditulis sebagai .eml ke LOGS_DIR/mail (direktori sementara).
# Alamat uji @example.org memakai null MX, jadi cek DNS dimatikan di sini dan
# diuji tersendiri di tests/test_notify.py.
os.environ["MAIL_BACKEND"] = "file"
os.environ["MAIL_CHECK_DNS"] = "false"


@pytest.fixture(scope="session", autouse=True)
def _isolate_output_dirs(tmp_path_factory):
    """Log run dan folder dataset hasil test ditulis ke direktori sementara,
    bukan ke logs/ dan data/datasets/ produksi. Sebelumnya test menyisakan
    ratusan logs/*_PERSAT_*.txt dan folder {id}_dataset1 yang ID-nya
    bertabrakan dengan dataset sungguhan."""
    from etl import folder_manager as fm

    base = tmp_path_factory.mktemp("pipeline_output")
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("LOGS_DIR", str(base / "logs"))
        mp.setattr(fm, "DATA_ROOT", base / "datasets")
        yield


def _resolve_test_db_url() -> str:
    """URL database uji.

    Urutan: TEST_DATABASE_URL kalau di-set; kalau tidak, turunkan dari
    DATABASE_URL di .env dengan menambah akhiran `_test` pada nama database.
    Sebelumnya nilai default-nya dihardcode dengan password 'postgres', sehingga
    di mesin dengan kredensial lain seluruh test error saat setup.
    """
    explicit = os.getenv("TEST_DATABASE_URL")
    if explicit:
        return explicit

    main_url = os.getenv("DATABASE_URL")
    if not main_url:
        return "postgresql+psycopg2://postgres:postgres@localhost:5432/themonitor_test"

    base, _, dbname = main_url.rpartition("/")
    dbname, sep, query = dbname.partition("?")
    return f"{base}/{dbname}_test{sep}{query}"


TEST_DB_URL = _resolve_test_db_url()


def _guard_not_production(url: str) -> None:
    """Cegah test menghapus database produksi.

    Fixture db_client menjalankan DROP SCHEMA public CASCADE saat setup dan
    teardown, jadi kalau URL uji tidak sengaja menunjuk database utama, seluruh
    tabel produksi ikut terhapus. Lebih baik gagal keras di awal.
    """
    main_url = os.getenv("DATABASE_URL")
    if main_url and url.rstrip("/") == main_url.rstrip("/"):
        raise RuntimeError(
            "Test database URL sama dengan DATABASE_URL produksi. "
            "Test menjalankan DROP SCHEMA public CASCADE — batalkan. "
            "Set TEST_DATABASE_URL ke database terpisah."
        )
    if not url.rpartition("/")[2].partition("?")[0].endswith("_test"):
        raise RuntimeError(
            f"Nama database uji harus berakhiran '_test', dapat: {url.rpartition('/')[2]}"
        )


@pytest.fixture(scope="session")
def db_client():
    """
    Session-scoped DatabaseClient connected to the test database.
    Builds the schema from database/monitor_*.sql on setup, empties the
    schema on teardown.
    """
    from database.apply_schema import apply_files, set_role_passwords
    from etl.database_client import DatabaseClient

    _guard_not_production(TEST_DB_URL)
    client = DatabaseClient(TEST_DB_URL, pool_size=2, max_overflow=2)

    # Database uji dibangun dari ketiga berkas skema yang sama dengan produksi
    # (DATABASE.md §6, IMPLEMENTATION_NOTES K11), bukan dari ORM create_all:
    # dengan begitu setiap run tes juga membuktikan monitor_schema.sql,
    # monitor_security.sql, dan monitor_seed.sql jalan di database kosong,
    # dan constraint/FK/seed master yang dilihat tes identik dengan produksi.
    try:
        _reset_schema(client)
        raw = client._engine.raw_connection()
        try:
            apply_files(raw.driver_connection, echo=lambda _msg: None)
            # Role bersifat global untuk cluster: sandinya sama dengan yang
            # dipakai database utama (.env), jadi ini tidak mengubah apa pun
            # bagi aplikasi yang sedang berjalan.
            set_role_passwords(raw.driver_connection, echo=lambda _msg: None)
        finally:
            raw.close()
    except Exception as exc:  # pragma: no cover - hanya jalur pesan error
        pytest.exit(
            f"Tidak bisa menyiapkan database uji {TEST_DB_URL!r}: {exc}\n"
            "Buat dulu databasenya, mis.:\n"
            '  psql -U postgres -c "CREATE DATABASE themonitor_test"',
            returncode=1,
        )
    yield client
    # Teardown: kosongkan skema setelah seluruh sesi tes.
    _reset_schema(client)
    client.dispose()


def _reset_schema(client) -> None:
    """DROP SCHEMA public CASCADE + CREATE: database uji kembali kosong
    (termasuk ekstensi PostGIS, yang dipasang ulang oleh monitor_schema.sql)."""
    from sqlalchemy import text

    with client._engine.connect() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.commit()


@pytest.fixture(scope="function")
def db_session(db_client):
    """
    Function-scoped database session. Rolls back after each test
    so tests are fully isolated.
    """
    with db_client._SessionFactory() as session:
        yield session
        session.rollback()


@pytest.fixture(scope="function")
def meta(db_client):
    """MetadataManager instance for tests."""
    from etl.metadata_manager import MetadataManager
    return MetadataManager(db_client)


@pytest.fixture(scope="function")
def lineage(db_client):
    """LineageTracker instance for tests."""
    from etl.lineage_tracker import LineageTracker
    return LineageTracker(db_client)


@pytest.fixture(scope="function")
def plog(db_client):
    """PipelineLogManager instance for tests."""
    from etl.pipeline_logger import PipelineLogManager
    return PipelineLogManager(db_client)


@pytest.fixture(scope="session")
def sample_region(db_client):
    """
    Insert a Jabodetabek ROI once per session and return its region_id.
    """
    from sqlalchemy import text
    with db_client.session() as sess:
        existing = sess.scalar(
            text("SELECT region_id FROM regions_of_interest WHERE region_code = 'JABODTK'")
        )
        if existing:
            return existing

        sess.execute(text("""
            INSERT INTO regions_of_interest
                (region_code, name, description, bbox, area_km2, admin_level, country_code, is_active)
            VALUES (
                'JABODTK', 'Jabodetabek', 'Test AOI',
                ST_GeomFromText('POLYGON((106.4 -6.7, 107.2 -6.7, 107.2 -5.9, 106.4 -5.9, 106.4 -6.7))', 4326),
                6392.0, 2, 'ID', TRUE
            )
        """))
        return sess.scalar(
            text("SELECT region_id FROM regions_of_interest WHERE region_code = 'JABODTK'")
        )


@pytest.fixture(scope="function")
def sample_scene(meta, sample_region) -> int:
    """Insert a single test scene and return its scene_id."""
    return meta.insert_satellite_scene(
        product_identifier   = f"TEST_SCENE_{datetime.now().timestamp()}",
        acquisition_datetime = datetime(2024, 1, 15, 22, 50, 0, tzinfo=timezone.utc),
        region_id            = sample_region,
        bbox_wkt             = "POLYGON((106.4 -6.7, 107.2 -6.7, 107.2 -5.9, 106.4 -5.9, 106.4 -6.7))",
        orbit_direction      = "ASCENDING",
        orbit_number         = 52186,
        cloud_cover_percent  = 12.5,
        resolution_m         = 10,
    )


@pytest.fixture(scope="function")
def sample_dataset(db_client, sample_region) -> int:
    """
    Insert a minimal Dataset row directly (bypassing DatasetManager.create_dataset,
    which spawns a background job runner thread) and return its dataset_id.
    """
    from etl.database_client import Dataset

    with db_client.session() as sess:
        ds = Dataset(
            name=f"TEST_DATASET_{datetime.now().timestamp()}",
            location_label="Test AOI",
            region_id=sample_region,
            bbox="SRID=4326;POLYGON((106.4 -6.7, 107.2 -6.7, 107.2 -5.9, 106.4 -5.9, 106.4 -6.7))",
            bbox_wkt="POLYGON((106.4 -6.7, 107.2 -6.7, 107.2 -5.9, 106.4 -5.9, 106.4 -6.7))",
            date_start=datetime(2024, 1, 1, tzinfo=timezone.utc).date(),
            date_end=datetime(2024, 1, 31, tzinfo=timezone.utc).date(),
            required_tiers=["RAW", "COG"],
            dataset_kind="STANDARD",
            status="DRAFT",
        )
        sess.add(ds)
        sess.flush()
        return ds.dataset_id


# ---------------------------------------------------------------------------
# API: koneksi monitor_app / monitor_etl dan klien per role (Tahap 2)
# ---------------------------------------------------------------------------
# Aplikasi tidak pernah terkoneksi sebagai superuser: tes API memakai role
# login yang sama dengan produksi pada database uji. Fixture db_client
# (pemilik skema) tetap dipakai untuk menyiapkan data.

ROLE_USERNAMES = {
    "USER": "t_user",
    "ANALYST": "t_analyst",
    "DATA_ENGINEER": "t_engineer",
    "ADMIN": "t_admin",
}
TEST_PASSWORD = "test-password-123"


def _login_url(username: str, password_env: str) -> str:
    from sqlalchemy.engine import make_url

    password = os.getenv(password_env)
    if not password:
        pytest.exit(f"{password_env} kosong di .env; dibutuhkan tes API (Tahap 2)", returncode=1)
    return make_url(TEST_DB_URL).set(username=username, password=password).render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def app_db_client(db_client):
    from etl.database_client import DatabaseClient
    client = DatabaseClient(_login_url("monitor_app", "MONITOR_APP_PASSWORD"), pool_size=4, max_overflow=4)
    yield client
    client.dispose()


@pytest.fixture(scope="session")
def etl_db_client(db_client):
    from etl.database_client import DatabaseClient
    client = DatabaseClient(_login_url("monitor_etl", "MONITOR_ETL_PASSWORD"), pool_size=4, max_overflow=4)
    yield client
    client.dispose()


@pytest.fixture(scope="session")
def test_password_hash():
    """Hash bcrypt cost 12 dihitung sekali per sesi (mahal)."""
    from api.security import hash_password
    return hash_password(TEST_PASSWORD)


def create_test_user(db_client, username: str, role_code: str, password_hash: str,
                     is_active: bool = True) -> int:
    from sqlalchemy import text
    with db_client.session() as sess:
        return sess.scalar(text("""
            INSERT INTO users (role_id, username, password_hash, full_name, is_active)
            SELECT role_id, :u, :h, :n, :a FROM roles WHERE role_code = :r
            ON CONFLICT (username) DO UPDATE SET role_id = EXCLUDED.role_id, is_active = EXCLUDED.is_active,
                password_hash = EXCLUDED.password_hash, failed_login_count = 0, locked_until = NULL
            RETURNING user_id"""),
            {"u": username, "h": password_hash, "n": username.replace("_", " ").title(),
             "a": is_active, "r": role_code})


@pytest.fixture(scope="session")
def role_users(db_client, test_password_hash) -> dict[str, int]:
    """Satu akun per role login: {role_code: user_id}."""
    return {role: create_test_user(db_client, name, role, test_password_hash)
            for role, name in ROLE_USERNAMES.items()}


@pytest.fixture(scope="function")
def make_client(app_db_client, etl_db_client, role_users):
    """Pabrik TestClient: make_client("ANALYST"), make_client(None) (anonim),
    make_client(token="trn_...") (Bearer). Sesi dibuat langsung sebagai JWT
    (alur login sendiri diuji tests/test_auth.py) supaya tidak membayar
    bcrypt di setiap tes."""
    from fastapi.testclient import TestClient

    from api import deps
    from api.main import app
    from api.security import SESSION_COOKIE, create_session_jwt, token_rate_limiter

    deps.set_clients(app_db_client, etl_db_client)
    token_rate_limiter.reset()
    clients = []

    def _make(role: str | None = None, *, token: str | None = None, user_id: int | None = None,
              csrf: bool = True) -> TestClient:
        # https: cookie sesi ber-flag Secure hanya dikirim lewat https.
        client = TestClient(app, base_url="https://testserver", raise_server_exceptions=False)
        if csrf:
            client.headers["X-Requested-With"] = "orbit-u"
        if token:
            client.headers["Authorization"] = f"Bearer {token}"
        elif role or user_id:
            uid = user_id if user_id is not None else role_users[role]
            jwt_token, _ = create_session_jwt(uid, role or "USER")
            client.cookies.set(SESSION_COOKIE, jwt_token)
        clients.append(client)
        return client

    yield _make
    for c in clients:
        c.close()
    deps.set_clients(None, None)


@pytest.fixture(scope="function")
def api_client(make_client):
    """TestClient sebagai ADMIN. Dipakai tes API Tahap 1: endpoint warisan
    kini membutuhkan login, dan dengan ADMIN tes itu sekaligus berjalan di
    bawah SET LOCAL ROLE monitor_admin."""
    return make_client("ADMIN")


# ---------------------------------------------------------------------------
# Tahap 3: kecamatan sintetis untuk tes hidromet/alert/laporan
# ---------------------------------------------------------------------------
# Grid uji GPM-like: origin (106.0, -6.5), sel 0.1 derajat, 4x4.
#   TST001  box(106.075,-6.6, 106.175,-6.5)   1/4 sel (0,0) + 3/4 sel (0,1)
#   TST002  box(106.2,  -6.7, 106.3,  -6.6)   tepat sel (1,2)
#   TST003  box(106.05, -6.75,106.15, -6.65)  seperempat dari 4 sel (1..2, 0..1)
SYNTH_GRID = {"x0": 106.0, "y0": -6.5, "res": 0.1, "shape": (4, 4)}
SYNTH_KECAMATAN = {
    "TST001": (106.075, -6.6, 106.175, -6.5),
    "TST002": (106.2, -6.7, 106.3, -6.6),
    "TST003": (106.05, -6.75, 106.15, -6.65),
}


@pytest.fixture(scope="session")
def synthetic_aoi(db_client):
    """Kabupaten TST00 + 3 kecamatan in_aoi + ROI AOI + dataset HYDROMET_AOI.
    {pcode: region_id} + 'roi_id' + 'dataset_id'. Dibersihkan di akhir sesi."""
    from shapely.geometry import box
    from sqlalchemy import text

    from etl import regions as rg

    feats = [rg.RegionFeature("TST00", "Kabupaten Uji", 2, None, box(105.9, -7.0, 106.5, -6.4).wkb_hex)]
    feats += [rg.RegionFeature(p, f"Kecamatan {p[-1]}", 3, "TST00", box(*b).wkb_hex)
              for p, b in SYNTH_KECAMATAN.items()]
    with db_client.session() as sess:
        rg.upsert_regions(sess, feats, source_dataset="uji sintetis")
        ids = rg.resolve_kecamatan(sess, list(SYNTH_KECAMATAN))
        rg.set_aoi(sess, ids)
        roi_id = rg.rebuild_monitor_aoi(sess)
        out = dict(sess.execute(text("SELECT pcode, region_id FROM administrative_regions WHERE pcode LIKE 'TST%'")).all())
        out["roi_id"] = roi_id
        out["dataset_id"] = rg.hydromet_dataset(sess)["dataset_id"]
    yield out
    with db_client.session() as sess:
        sess.execute(text("DELETE FROM alert_events"))
        sess.execute(text("DELETE FROM disaster_events"))
        sess.execute(text("DELETE FROM region_observations"))
        sess.execute(text("UPDATE administrative_regions SET in_aoi = false"))


def write_synthetic_raster(path, values, *, nodata=-9999.9, dtype="float32", grid=None, tags=None):
    """GeoTIFF EPSG:4326 pada SYNTH_GRID (atau `grid`) dengan isi `values`."""
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin

    g = grid or SYNTH_GRID
    arr = np.asarray(values, dtype=dtype)
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1,
                       dtype=dtype, crs="EPSG:4326", transform=from_origin(g["x0"], g["y0"], g["res"], g["res"]),
                       nodata=nodata) as dst:
        dst.write(arr, 1)
        if tags:
            dst.update_tags(**tags)
    return path
