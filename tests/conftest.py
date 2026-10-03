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


@pytest.fixture(scope="function")
def api_client(db_client):
    """
    FastAPI TestClient with DB dependency override.
    Allows testing API endpoints without running a real server.
    """
    from fastapi.testclient import TestClient
    from api.main import app, get_db

    app.dependency_overrides[get_db] = lambda: db_client
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()
