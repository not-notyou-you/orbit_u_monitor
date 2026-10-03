"""
M31: metrik scene Live disimpan 1NF di live_scene_metrics, bukan JSONB
live_scenes.metrics. Yang dijaga: dict yang disusun ulang dari tabel sama
persis dengan keluaran compute_metrics(), sehingga live_interpret,
live_forecast, dan kartu Live tidak berubah perilakunya.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import func, select

from etl import live_metrics as lmx
from etl.database_client import LiveScene, LiveSceneMetric

SCENE = date(2026, 9, 24)


def _metrics() -> dict:
    """Bentuk keluaran compute_metrics() untuk satu scene lengkap."""
    return {
        "sentinel1": {
            "vv_mean_db": -9.12, "vh_mean_db": -16.4, "vh_water_pct": 3.25,
            "vh_water_threshold_db": -20.0, "frames": 2, "valid_pixels": 1048576,
        },
        "modis": {
            "flood": {
                "matched_date": "2026-09-24", "observation_date": "2026-09-24",
                "valid_pct": 61.2, "cloud_pct": 38.8, "flood_pct": 0.8,
                "recurring_pct": 0.1, "water_pct": 2.4, "nearest": False,
            },
            "ndvi": {
                "matched_date": "2026-09-23", "valid_pct": 70.0, "cloud_pct": 30.0,
                "mean": 0.612, "age_days_median": 3.5, "composite_period": "2026-09-14",
                "lookback_days": 24, "nearest": True,
            },
            "ndwi": {
                "matched_date": "2026-09-23", "valid_pct": 70.0, "cloud_pct": 30.0,
                "mean": -0.214, "age_days_median": 3.5, "composite_period": "2026-09-14",
                "lookback_days": 24, "water_pct": 4.1, "nearest": True,
            },
        },
        "gpm": {
            f"rain_{w}": {
                "matched_date": "2026-09-24", "mean_mm": mm, "max_mm": mm * 2,
                "imerg_runs": "L", "window_start": "2026-09-22T00:00:00Z",
                "window_end": "2026-09-25T00:00:00Z", "nearest": False,
            }
            for w, mm in (("24h", 12.5), ("72h", 63.4), ("7d", 118.0))
        },
    }


def test_round_trip_is_lossless():
    rows, meta = lmx.metric_rows(_metrics(), SCENE)
    assert lmx.metrics_from_rows(rows, meta, SCENE) == _metrics()


def test_text_descriptors_go_to_meta_not_rows():
    rows, meta = lmx.metric_rows(_metrics(), SCENE)
    assert all(isinstance(v, (int, float)) or v is None for _, _, v, _ in rows)
    assert meta["gpm"]["rain_72h"]["imerg_runs"] == "L"
    assert meta["modis"]["ndvi"]["composite_period"] == "2026-09-14"


def test_scene_without_sentinel1_stays_none():
    m = {"sentinel1": None, "modis": {}, "gpm": {}}
    rows, meta = lmx.metric_rows(m, SCENE)
    assert rows == [] and meta == {}
    assert lmx.metrics_from_rows(rows, meta, SCENE) == m


def test_null_values_keep_their_entry():
    m = _metrics()
    m["modis"]["flood"]["flood_pct"] = None
    rows, meta = lmx.metric_rows(m, SCENE)
    assert lmx.metrics_from_rows(rows, meta, SCENE)["modis"]["flood"]["flood_pct"] is None


@pytest.fixture
def live_scene(db_client):
    with db_client.session() as sess:
        row = LiveScene(area_id=990001, scene_date=SCENE, status="READY",
                        source_status={}, interpretations={}, area_status={},
                        previews={}, deleted_files=[])
        sess.add(row)
        sess.flush()
        sid = row.live_scene_id
    yield sid
    with db_client.session() as sess:
        sess.delete(sess.get(LiveScene, sid))


def test_database_round_trip_and_replace(db_client, live_scene):
    with db_client.session() as sess:
        meta = lmx.save_scene_metrics(sess, live_scene, SCENE, _metrics())
        row = sess.get(LiveScene, live_scene)
        row.source_status = {src: {"status": "OK", "meta": m} for src, m in meta.items()}
    # Disimpan ulang (mis. retry sumber): baris diganti, bukan digandakan.
    with db_client.session() as sess:
        lmx.save_scene_metrics(sess, live_scene, SCENE, _metrics())
    with db_client.session() as sess:
        n = sess.scalar(select(func.count()).select_from(LiveSceneMetric)
                        .where(LiveSceneMetric.live_scene_id == live_scene))
        loaded = lmx.load_scene_metrics(sess, [sess.get(LiveScene, live_scene)])
    assert n == len(lmx.metric_rows(_metrics(), SCENE)[0])
    assert loaded[live_scene] == _metrics()
