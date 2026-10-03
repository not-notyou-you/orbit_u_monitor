# tests/test_deletion_manager.py
"""
Tests untuk penghapusan dataset (etl/deletion_manager.py dan
DatasetManager._spawn_deletion_runner): file yang ditulis job yang telat
berhenti, dan produk MODIS/GPM/FUSION dataset itu tidak boleh tertinggal
yatim (M30: tanpa scene placeholder NASA_AUX_*).
"""

from __future__ import annotations

import hashlib
import threading
import time
from datetime import datetime, timezone

import pytest

from etl import dataset_manager as dsm
from etl import folder_manager as fm
from etl.database_client import DataProduct, Dataset, NasaScene
from etl.deletion_manager import DeletionManager

BBOX_WKT = "POLYGON((106.4 -6.7, 107.2 -6.7, 107.2 -5.9, 106.4 -5.9, 106.4 -6.7))"


@pytest.fixture
def data_root(tmp_path, monkeypatch):
    root = tmp_path / "data" / "datasets"
    monkeypatch.setattr(fm, "DATA_ROOT", root)
    return root


def _dataset_name(db_client, dataset_id):
    with db_client.session() as sess:
        return sess.get(Dataset, dataset_id).name


def test_delete_all_sweeps_files_written_after_manifest(
    db_client, sample_dataset, data_root, monkeypatch
):
    """Job yang telat berhenti menulis file setelah manifest dibuat; file
    itu harus ikut terhapus dan folder dataset hilang."""
    name = _dataset_name(db_client, sample_dataset)
    base = fm.get_dataset_root(sample_dataset, name)
    (base / "20240115" / "raw").mkdir(parents=True)
    (base / "20240115" / "raw" / "early.tif").write_bytes(b"x" * 10)

    original = DeletionManager._delete_files
    calls = {"n": 0}

    def delete_then_late_write(self, manifest, op_id):
        result = original(self, manifest, op_id)
        calls["n"] += 1
        if calls["n"] == 1:
            late = base / "_work" / "late_calibrated.tif"
            late.parent.mkdir(parents=True, exist_ok=True)
            late.write_bytes(b"y" * 20)
        return result

    monkeypatch.setattr(DeletionManager, "_delete_files", delete_then_late_write)

    result = DeletionManager(db_client, sample_dataset, name).delete_all()

    assert not base.exists()
    assert result["deleted_count"] == 2
    with db_client.session() as sess:
        assert sess.get(Dataset, sample_dataset) is None


def _aux_product(meta, dataset_id, nasa_scene_id, tag):
    """Produk MODIS/GPM berjangkar granule (M30) milik `dataset_id`."""
    job_id = meta.insert_processing_job(None, "DOWNLOAD", nasa_scene_id=nasa_scene_id)
    return meta.insert_data_product(
        scene_id=None, nasa_scene_id=nasa_scene_id, job_id=job_id, dataset_id=dataset_id,
        product_tier="INDICES", source="MODIS", product_type="MODIS_NDVI",
        band_name="NDVI", file_path=f"/tmp/del_{tag}.tif", file_name=f"del_{tag}.tif",
        file_size_mb=1.0, data_hash_sha256=hashlib.sha256(tag.encode()).hexdigest(),
    )


def test_delete_all_removes_own_aux_products_keeps_shared_granule(
    db_client, meta, sample_dataset, sample_region, data_root
):
    """M30: produk MODIS/GPM dataset ini ikut terhapus bersama datasetnya;
    granule nasa_scenes (dipakai bersama antar dataset) dan produk dataset
    lain pada granule yang sama tetap ada. Menggantikan tes placeholder
    NASA_AUX_* yang sudah tidak ada."""
    name = _dataset_name(db_client, sample_dataset)
    stamp = datetime.now().strftime("%H%M%S%f")
    nasa_id = meta.insert_nasa_scene(
        source="MODIS", tile_id="MOSAIC", product_short_name=f"MOD09A1_{stamp}"[:50],
        acquisition_date=datetime(2024, 1, 15).date(), region_id=sample_region,
    )
    with db_client.session() as sess:
        other = Dataset(
            name=f"OTHER_{stamp}", region_id=sample_region,
            bbox=f"SRID=4326;{BBOX_WKT}", bbox_wkt=BBOX_WKT,
            date_start=datetime(2024, 1, 1).date(), date_end=datetime(2024, 1, 31).date(),
            required_tiers=["COG"], dataset_kind="STANDARD", status="DRAFT",
        )
        sess.add(other)
        sess.flush()
        other_id = other.dataset_id
    own = _aux_product(meta, sample_dataset, nasa_id, f"own_{stamp}")
    kept = _aux_product(meta, other_id, nasa_id, f"kept_{stamp}")

    DeletionManager(db_client, sample_dataset, name).delete_all()
    with db_client.session() as sess:
        assert sess.get(DataProduct, own) is None
        assert sess.get(DataProduct, kept) is not None
        assert sess.get(NasaScene, nasa_id) is not None


def test_wait_thread_exit_waits_for_job_thread():
    stop = threading.Event()
    t = threading.Thread(target=stop.wait, daemon=True)
    dsm._register_thread("job-test-wait", t)
    t.start()
    try:
        assert dsm._wait_thread_exit("job-test-wait", timeout_s=0.05) is False
        threading.Timer(0.05, stop.set).start()
        started = time.monotonic()
        assert dsm._wait_thread_exit("job-test-wait", timeout_s=5) is True
        assert time.monotonic() - started < 5
    finally:
        stop.set()
    assert dsm._wait_thread_exit("tidak-terdaftar", timeout_s=0) is True
