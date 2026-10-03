# tests/test_fusion_product_identity.py
"""
Identitas produk FUSION adalah BERKASNYA, bukan scene primary-nya.

Regresi nyata, terukur di dua dataset sekaligus:

    dataset 26  fusion_20251201_cooccurrence_processed.h5
                dua baris is_latest, satu mengaku 32040x103630 padahal
                berkasnya 31922x103248
    dataset 25  fusion_20250204_hybrid_processed.h5
                dua baris is_latest, tidak kelihatan karena bentuknya sama

Mekanismenya: nama berkas fusion cuma memuat tanggal
(`fusion_{tanggal}_{strategi}_{level}.h5`), tapi produknya didaftarkan atas
nama scene "primary" — anggota pertama tanggal itu setelah diurutkan per pid.
Kalau job terputus lalu dilanjutkan, himpunan anggota yang sudah selesai
berbeda, primary-nya berganti, dan dedup `insert_data_product` yang berkunci
pada scene_id tidak mengenali keduanya sebagai artefak yang sama. Berkasnya
tertimpa, barisnya menumpuk.

Yang dijaga: mendaftarkan stack kedua ke path yang sama harus memadamkan
baris pertama, apa pun scene-nya.
"""
from __future__ import annotations

import uuid

import pytest

from etl import tier_names as tn


# Fixture `meta` dari conftest: DATABASE UJI (*_test). Dulu tes ini membuat
# DatabaseClient sendiri dari TEST_DATABASE_URL *atau DATABASE_URL* -- tanpa
# TEST_DATABASE_URL ia menulis ke database PRODUKSI, dan hanya "aman" karena
# database itu kebetulan belum punya scene (tes ter-skip). Ketahuan di Tahap 3
# setelah uji Live mengisi satellite_scenes produksi (IMPLEMENTATION_NOTES T3-30).


@pytest.fixture
def anchors(meta, sample_dataset):
    """Dataset uji + job FUSION tanpa jangkar. Produk FUSION tidak menempel
    pada scene (M30/K2: scene_id dan nasa_scene_id NULL), jadi identitasnya
    memang hanya berkasnya. band_name/file_path unik per tes."""
    job = meta.insert_processing_job(None, "FUSION", parameters={"test": "fusion_identity"})
    tag = uuid.uuid4().hex[:8]
    return {
        "dataset_id": sample_dataset,
        "job_id": job,
        "band": f"UJI_{tag}",
        "path": f"data/_uji/{tag}/fusion_19990101_processed.h5",
    }


def _cleanup(meta, dataset_id, band):
    from etl.database_client import DataProduct

    with meta._db.session() as sess:
        sess.query(DataProduct).filter(
            DataProduct.dataset_id == dataset_id,
            DataProduct.band_name == band,
        ).delete(synchronize_session=False)
        sess.commit()


def _rows(meta, dataset_id, band):
    from etl.database_client import DataProduct

    with meta._db.session() as sess:
        return [
            (r.product_id, r.scene_id, r.is_latest)
            for r in sess.query(DataProduct).filter(
                DataProduct.dataset_id == dataset_id,
                DataProduct.band_name == band,
            ).all()
        ]


def _insert(meta, a, **kw):
    return meta.insert_data_product(
        scene_id=None, job_id=a["job_id"], dataset_id=a["dataset_id"],
        product_tier=tn.FUSED, source="FUSION", product_type="FUSION_H5",
        band_name=a["band"], file_path=a["path"],
        file_name="fusion_19990101_processed.h5",
        file_size_mb=1.0, data_hash_sha256="x" * 64,
        file_format="HDF5", rows=10, cols=20, processing_level="PROCESSED",
        **kw,
    )


class TestSupersedeByPath:
    def test_same_path_from_another_run_supersedes(self, meta, anchors):
        """Inti perbaikannya: dua pendaftaran berkas yang sama -> yang lama padam."""
        try:
            ids = [_insert(meta, anchors, supersede_same_path=True) for _ in range(2)]
            latest = [r for r in _rows(meta, anchors["dataset_id"], anchors["band"])
                      if r[2]]
            assert len(latest) == 1, "hanya stack terbaru yang boleh is_latest"
            assert latest[0][0] == ids[-1]
        finally:
            _cleanup(meta, anchors["dataset_id"], anchors["band"])

    def test_fusion_dedups_by_path_even_without_the_flag(self, meta, anchors):
        """Dulu (DataLab) tanpa bendera kedua baris tetap is_latest. Sejak K3
        produk FUSION (tanpa scene) SELALU didedup per file_path, jadi bentuk
        bug lama tidak bisa terjadi lagi."""
        try:
            for _ in range(2):
                _insert(meta, anchors)
            latest = [r for r in _rows(meta, anchors["dataset_id"], anchors["band"])
                      if r[2]]
            assert len(latest) == 1
        finally:
            _cleanup(meta, anchors["dataset_id"], anchors["band"])

    def test_reregistering_the_same_scene_still_supersedes(self, meta, anchors):
        """Jalur lama tidak boleh rusak: scene yang sama didaftarkan ulang
        tetap memadamkan barisnya sendiri."""
        try:
            _insert(meta, anchors, supersede_same_path=True)
            second = _insert(meta, anchors, supersede_same_path=True)
            latest = [r for r in _rows(meta, anchors["dataset_id"], anchors["band"])
                      if r[2]]
            assert len(latest) == 1
            assert latest[0][0] == second
        finally:
            _cleanup(meta, anchors["dataset_id"], anchors["band"])
