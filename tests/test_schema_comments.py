"""
M34 / DATABASE.md §6: setiap tabel, kolom, dan VIEW di skema Monitor wajib
punya COMMENT ON, karena kamus data dibangkitkan dari komentar itu
(tools/data_dictionary.py). Database uji dibangun dari
database/monitor_schema.sql (tests/conftest.py), jadi tes ini memeriksa
berkas skema yang sesungguhnya.
"""

from __future__ import annotations

import pytest

from tools.data_dictionary import read_catalog, render_dictionary, render_erd


@pytest.fixture(scope="module")
def catalog(db_client):
    with db_client._engine.connect() as conn:
        return read_catalog(conn)


def test_every_table_has_a_comment(catalog):
    tables, _ = catalog
    missing = [t.name for t in tables if not (t.comment or "").strip()]
    assert not missing, f"tabel tanpa COMMENT ON TABLE: {missing}"


def test_every_column_has_a_comment(catalog):
    tables, _ = catalog
    missing = [f"{t.name}.{c.name}" for t in tables for c in t.columns
               if not (c.comment or "").strip()]
    assert not missing, f"kolom tanpa COMMENT ON COLUMN: {missing}"


def test_every_view_has_a_comment(catalog):
    _, views = catalog
    missing = [v.name for v in views if not (v.comment or "").strip()]
    assert not missing, f"VIEW tanpa COMMENT ON VIEW: {missing}"


def test_master_and_new_tables_are_present(catalog):
    tables, views = catalog
    names = {t.name for t in tables}
    masters = {"roles", "users", "satellite_sources", "spectral_bands",
               "administrative_regions", "regions_of_interest", "processing_stages",
               "quality_thresholds", "disaster_types", "alert_rules",
               "fusion_strategies", "report_types"}
    new = {"region_observations", "alert_events", "disaster_events", "generated_reports",
           "user_activity_logs", "audit_log", "api_tokens", "live_scene_metrics",
           "quality_alerts", "app_settings"}
    dropped = {"dataset_versions", "api_access_logs", "processing_rules",
               "live_dataset_sources", "reference_land_polygons"}
    assert masters <= names and new <= names
    assert not dropped & names
    assert "v_evaluasi_alert" in {v.name for v in views}


def test_generators_cover_every_table(catalog):
    tables, views = catalog
    md = render_dictionary(tables, views)
    erd = render_erd(tables)
    for t in tables:
        assert f"## {t.name}" in md
        assert f"    {t.name} {{" in erd
    assert erd.startswith("erDiagram")
