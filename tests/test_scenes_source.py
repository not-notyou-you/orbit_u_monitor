# tests/test_scenes_source.py
"""GET /api/scenes?source=S1|MODIS|GPM&include_invalid= (INTERFACE.md §4.7, K12)."""

from __future__ import annotations

import time

import pytest
from sqlalchemy import text


@pytest.fixture
def scenes(db_client, sample_region, sample_scene):
    tile = f"t{time.time_ns() % 10**8}"
    with db_client.session() as sess:
        invalid_s1 = sess.scalar(text("""
            INSERT INTO satellite_scenes (product_identifier, acquisition_datetime, bbox, region_id,
                                          is_valid, invalidated_at, invalid_reason)
            VALUES (:p, '2024-02-01T00:00:00Z',
                    ST_GeomFromText('POLYGON((106 -7,106.1 -7,106.1 -6.9,106 -6.9,106 -7))', 4326),
                    :r, false, now(), 'noise') RETURNING scene_id"""),
            {"p": f"INVALID_{tile}", "r": sample_region})
        modis = sess.scalar(text("""
            INSERT INTO nasa_scenes (source, tile_id, product_short_name, acquisition_date, region_id)
            VALUES ('MODIS', :t, 'MOD09A1', '2025-03-01', :r) RETURNING nasa_scene_id"""),
            {"t": tile, "r": sample_region})
        modis_invalid = sess.scalar(text("""
            INSERT INTO nasa_scenes (source, tile_id, product_short_name, acquisition_date, region_id,
                                     is_valid, invalidated_at, invalid_reason)
            VALUES ('MODIS', :t, 'MOD09A1', '2025-03-09', :r, false, now(), 'cloud') RETURNING nasa_scene_id"""),
            {"t": tile, "r": sample_region})
        gpm = sess.scalar(text("""
            INSERT INTO nasa_scenes (source, tile_id, product_short_name, acquisition_date, region_id, run_type)
            VALUES ('GPM', :t, 'GPM_3IMERGDF', '2025-03-01', :r, 'F') RETURNING nasa_scene_id"""),
            {"t": tile, "r": sample_region})
    return {"valid_s1": sample_scene, "invalid_s1": invalid_s1, "modis": modis,
            "modis_invalid": modis_invalid, "gpm": gpm}


def _ids(resp, key):
    assert resp.status_code == 200, resp.text
    return {i[key] for i in resp.json()["items"]}


def test_default_is_s1_without_invalid(make_client, scenes):
    ids = _ids(make_client("DATA_ENGINEER").get("/api/scenes?limit=200"), "scene_id")
    assert scenes["valid_s1"] in ids and scenes["invalid_s1"] not in ids


def test_source_modis_and_gpm_read_nasa_scenes(make_client, scenes):
    de = make_client("DATA_ENGINEER")
    modis = de.get("/api/scenes?source=MODIS&limit=200").json()["items"]
    ids = {i["nasa_scene_id"] for i in modis}
    assert scenes["modis"] in ids and scenes["modis_invalid"] not in ids and scenes["gpm"] not in ids
    assert all(i["source"] == "MODIS" for i in modis)
    gpm = de.get("/api/scenes?source=GPM&date_from=2025-03-01T00:00:00&date_to=2025-03-01T23:59:59").json()["items"]
    row = next(i for i in gpm if i["nasa_scene_id"] == scenes["gpm"])
    assert row["run_type"] == "F"


def test_include_invalid_admin_only(make_client, scenes):
    resp = make_client("DATA_ENGINEER").get("/api/scenes?include_invalid=true")
    assert resp.status_code == 403 and resp.json()["code"] == "ROLE_FORBIDDEN"
    admin = make_client("ADMIN")
    s1 = admin.get("/api/scenes?include_invalid=true&limit=200").json()["items"]
    invalid = next(i for i in s1 if i["scene_id"] == scenes["invalid_s1"])
    assert invalid["is_valid"] is False and invalid["invalid_reason"] == "noise"
    assert scenes["modis_invalid"] in _ids(admin.get("/api/scenes?source=MODIS&include_invalid=true&limit=200"),
                                           "nasa_scene_id")


def test_unknown_source_rejected(make_client):
    assert make_client("DATA_ENGINEER").get("/api/scenes?source=LANDSAT").status_code == 422
