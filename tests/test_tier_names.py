"""
Kosakata tier D14: hanya nama D14 yang disimpan dan dikirim ke SQL; nama
warisan (BRONZE/SILVER/GOLD/FUSION) hanya diterima sebagai input.

Tiga hal yang dijaga di sini:
  1. filter baca menerjemahkan input lama ke nama D14 -- product_tier_enum
     Monitor tidak punya nilai warisan, jadi literal lama di klausa IN membuat
     kueri gagal (IMPLEMENTATION_NOTES K1);
  2. jalur tulis tidak pernah menyimpan nama warisan;
  3. whitelist `datasets.chk_required_tiers` dan `product_tier_enum` di
     database/monitor_schema.sql sama persis dengan etl/tier_names -- drift
     inilah yang dulu membuat POST /api/datasets 500 (CheckViolation).
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

from etl import tier_names as tn
from etl.database_client import ProductTierEnum

SCHEMA = Path(__file__).resolve().parent.parent / "database" / "monitor_schema.sql"


@pytest.mark.parametrize("tier, expected", [
    ("RAW", ("RAW",)),
    ("ALIGNED", ("ALIGNED",)),
    ("BRONZE", ("ALIGNED",)),
    ("COG", ("COG",)),
    ("gold", ("COG",)),
    ("FUSED", ("FUSED",)),
    ("FUSION", ("FUSED",)),
    ("INDICES", ("INDICES",)),
    ("SILVER", ("DESPECKLED", "INDICES", "ACCUMULATED")),
    (ProductTierEnum.COG, ("COG",)),
])
def test_equivalent_tiers(tier, expected):
    assert tn.equivalent_tiers(tier) == expected


def test_equivalent_tiers_rejects_unknown():
    with pytest.raises(ValueError):
        tn.equivalent_tiers("PLATINUM")


def test_sql_helpers_never_emit_legacy_names():
    emitted = set(tn.tiers_up_to_rank(4))
    for t in tn.ALL_TIERS:
        if t != tn.PREVIEW:
            emitted.update(tn.equivalent_tiers(t))
    assert emitted == set(tn.TIERS)


def test_tiers_up_to_rank_2_is_everything_before_cog():
    got = set(tn.tiers_up_to_rank(2))
    assert got == {"RAW", "ALIGNED", "DESPECKLED", "INDICES", "ACCUMULATED"}
    assert not got & set(tn.tiers_at_rank(3)) and not got & set(tn.tiers_at_rank(4))


def test_new_names_come_first():
    for t in tn.TIERS:
        assert tn.equivalent_tiers(t)[0] in tn.TIERS


def _schema_sql() -> str:
    return re.sub(r"--[^\n]*", "", SCHEMA.read_text(encoding="utf-8"))


def _required_tiers_whitelist() -> set[str]:
    m = re.search(r"CONSTRAINT\s+chk_required_tiers\s+CHECK\s*\((.*?)\]", _schema_sql(), re.S | re.I)
    assert m, "chk_required_tiers tidak ditemukan di monitor_schema.sql"
    return set(re.findall(r"'([A-Z]+)'", m.group(1)))


def _product_tier_enum_values() -> set[str]:
    m = re.search(r"CREATE\s+TYPE\s+product_tier_enum\s+AS\s+ENUM\s*\((.*?)\)", _schema_sql(), re.S | re.I)
    assert m, "product_tier_enum tidak ditemukan di monitor_schema.sql"
    return set(re.findall(r"'([A-Z]+)'", m.group(1)))


def test_required_tiers_constraint_matches_tier_names():
    assert _required_tiers_whitelist() == set(tn.TIERS)


def test_product_tier_enum_matches_tier_names():
    assert {e.value for e in ProductTierEnum} == set(tn.TIERS)
    assert _product_tier_enum_values() == set(tn.TIERS)


@pytest.mark.parametrize("legacy, source, expected", [
    ("BRONZE", "SENTINEL1", "ALIGNED"),
    ("SILVER", "MODIS", "INDICES"),
    ("GOLD", "GPM", "COG"),
])
def test_insert_never_stores_legacy_name(meta, sample_scene, legacy, source, expected):
    job_id = meta.insert_processing_job(sample_scene, "CROP")
    pid = meta.insert_data_product(
        scene_id=sample_scene, job_id=job_id,
        product_tier=legacy, source=source, product_type="T", band_name=f"B_{legacy}",
        file_path=f"/tmp/tn_{legacy}.tif", file_name=f"tn_{legacy}.tif", file_size_mb=1.0,
        data_hash_sha256=hashlib.sha256(legacy.encode()).hexdigest(),
    )
    new = [p for p in meta.get_products_by_scene(sample_scene, tier=expected) if p["product_id"] == pid]
    assert new and new[0]["product_tier"] == expected
    # Nama lama tetap bisa dipakai untuk mencari, dan menemukan baris yang sama.
    assert any(p["product_id"] == pid for p in meta.get_products_by_scene(sample_scene, tier=legacy))
