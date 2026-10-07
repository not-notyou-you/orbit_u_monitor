# tests/test_diagram_api.py
"""Halaman Diagram (INTERFACE.md §4.5, M56): semua band 30 hari, analisa
daerah, laporan PDF semua band. ANALYST dan ADMIN."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from etl import hydromet_aggregate as ha


def _today():
    return datetime.now(timezone.utc).date()


@pytest.fixture(scope="module")
def diagram_obs(db_client, synthetic_aoi):
    """Hujan + NDVI 10 hari untuk dua kecamatan, VV dari satu scene Live."""
    days = [_today() - timedelta(days=k) for k in range(2, 12)]
    with db_client.session() as sess:
        for i, d in enumerate(days):
            # TST001 + TST003: TST002 dipakai tes hujan/kejadian lain dengan angka pasti.
            ha.upsert_observations(sess, "RAIN_24H", d, {synthetic_aoi["TST001"]: ha.ZonalResult(10.0 + i, 1.0, 1),
                                                         synthetic_aoi["TST003"]: ha.ZonalResult(60.0 + i, 1.0, 1)},
                                   run_type="L")
            ha.upsert_observations(sess, "NDVI", d, {synthetic_aoi["TST001"]: ha.ZonalResult(0.6, 1.0, 1)})
        area = sess.scalar(text("""INSERT INTO live_areas (name, bbox_wkt, status)
                                   VALUES ('diagram uji', 'POLYGON((0 0,1 0,1 1,0 1,0 0))', 'ACTIVE') RETURNING area_id"""))
        sid = sess.scalar(text("""INSERT INTO live_scenes (area_id, scene_date, status) VALUES (:a, :d, 'READY')
                                  RETURNING live_scene_id"""), {"a": area, "d": days[2]})
        sess.execute(text("""INSERT INTO live_scene_metrics (live_scene_id, band_id, metric_name, value)
                             SELECT :s, band_id, 'mean', -11.5 FROM spectral_bands WHERE band_code = 'VV'"""), {"s": sid})
    yield days
    with db_client.session() as sess:
        sess.execute(text("UPDATE live_areas SET deleted_at = now(), status = 'DELETED' WHERE area_id = :a"), {"a": area})


def test_bands_have_explanations_and_thresholds(make_client):
    items = make_client("ANALYST").get("/api/diagram/bands").json()["items"]
    codes = [b["band_code"] for b in items]
    assert {"VV", "VH", "RAIN_24H", "NDVI", "FLOOD"} <= set(codes)
    rain = next(b for b in items if b["band_code"] == "RAIN_24H")
    assert rain["about"] and rain["color"] and [t["label"] for t in rain["thresholds"]] == ["lebat", "sangat lebat"]
    assert next(b for b in items if b["band_code"] == "VV")["per_region"] is False
    assert len({b["color"] for b in items}) == len(items)          # satu warna per band


def test_latest_all_bands_one_response(make_client, diagram_obs):
    body = make_client("ANALYST").get("/api/diagram/latest").json()
    by = {b["band_code"]: b for b in body["bands"]}
    # Satu titik per hari untuk setiap band (null = hari tanpa data).
    assert all(len(b["points"]) == 30 for b in body["bands"])
    rain = {p["x"]: p for p in by["RAIN_24H"]["points"]}
    newest = rain[diagram_obs[0].isoformat()]
    assert newest["y"] == pytest.approx(35.0) and newest["source"] == "daily"   # (10 + 60) / 2
    vv = {p["x"]: p for p in by["VV"]["points"]}[diagram_obs[2].isoformat()]
    assert vv["y"] == -11.5 and vv["source"] == "scene" and by["VV"]["sparse"] is True
    lo, hi = by["RAIN_24H"]["range"]
    assert lo < hi and lo <= 40.0 <= hi          # rentang biasa (persentil 2–98)
    assert body["updated_at"] is not None and body["date_to"] == _today().isoformat()


def test_latest_falls_back_to_scene_metrics(make_client, db_client, diagram_obs):
    """Hari tanpa angka harian (Job Hidromet tertinggal) memakai metrik scene Live."""
    d = diagram_obs[2]
    with db_client.session() as sess:
        sid = sess.scalar(text("""SELECT live_scene_id FROM live_scenes s JOIN live_areas a USING (area_id)
                                  WHERE a.name = 'diagram uji' AND s.scene_date = :d"""), {"d": d})
        sess.execute(text("""INSERT INTO live_scene_metrics (live_scene_id, band_id, metric_name, value)
                             SELECT :s, band_id, 'mean', 0.42 FROM spectral_bands WHERE band_code = 'NDWI'"""), {"s": sid})
    body = make_client("ANALYST").get("/api/diagram/latest").json()
    ndwi = {p["x"]: p for p in next(b for b in body["bands"] if b["band_code"] == "NDWI")["points"]}
    assert ndwi[d.isoformat()]["source"] == "scene" and ndwi[d.isoformat()]["y"] == pytest.approx(0.42)
    # Hari dengan angka harian tetap memakai angka harian.
    rain = {p["x"]: p for p in next(b for b in body["bands"] if b["band_code"] == "RAIN_24H")["points"]}
    assert rain[d.isoformat()]["source"] == "daily"


def test_regions_series_and_validation(make_client, diagram_obs, synthetic_aoi):
    c = make_client("ANALYST")
    ids = f"{synthetic_aoi['TST001']},{synthetic_aoi['TST003']}"
    f, t = diagram_obs[-1].isoformat(), diagram_obs[0].isoformat()
    body = c.get(f"/api/diagram/regions?region_ids={ids}&bands=RAIN_24H,NDVI&date_from={f}&date_to={t}").json()
    assert [b["band_code"] for b in body["bands"]] == ["NDVI", "RAIN_24H"] or \
           {b["band_code"] for b in body["bands"]} == {"NDVI", "RAIN_24H"}
    rain = next(b for b in body["bands"] if b["band_code"] == "RAIN_24H")
    # Satu titik per hari (10 hari), semuanya terisi untuk kedua kecamatan.
    assert [len(s["points"]) for s in rain["series"]] == [10, 10]
    assert all(p["y"] is not None for s in rain["series"] for p in s["points"])
    r = c.get(f"/api/diagram/regions?region_ids={ids}&bands=VV&date_from={f}&date_to={t}")
    assert (r.status_code, r.json()["code"]) == (400, "INVALID_BAND")
    r = c.get(f"/api/diagram/regions?region_ids={ids}&date_from={t}&date_to={f}")
    assert (r.status_code, r.json()["code"]) == (400, "INVALID_DATE_RANGE")
    r = c.get(f"/api/diagram/regions?region_ids={synthetic_aoi['roi_id'] * 0 + 999999}&date_from={f}&date_to={t}")
    assert (r.status_code, r.json()["code"]) == (400, "NOT_KECAMATAN")


def test_report_pdf_contains_all_bands(make_client, diagram_obs, synthetic_aoi, db_client):
    ids = f"{synthetic_aoi['TST001']},{synthetic_aoi['TST003']}"
    f, t = diagram_obs[-1].isoformat(), diagram_obs[0].isoformat()
    r = make_client("ANALYST").get(f"/api/diagram/report.pdf?region_ids={ids}&date_from={f}&date_to={t}"
                                   "&colors=%23ffb000,%2333ff99")
    assert r.status_code == 200, r.text
    assert r.content[:4] == b"%PDF" and "analisa_daerah" in r.headers["content-disposition"]


def test_roles(make_client):
    for role, code in ((None, 401), ("USER", 403), ("DATA_ENGINEER", 403), ("ANALYST", 200), ("ADMIN", 200)):
        assert make_client(role).get("/api/diagram/bands").status_code == code, role


def test_printable_colours_are_darkened():
    from etl.report_diagram import _printable
    assert _printable("#1f77b4") == "#1f77b4"
    r, g, b = (int(_printable("#33ff99")[i:i + 2], 16) for i in (1, 3, 5))
    assert (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255 <= 0.56
