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
    assert next(b for b in items if b["band_code"] == "VV")["per_region"] is True   # M58: S1 per kecamatan
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
    r = c.get(f"/api/diagram/regions?region_ids={ids}&bands=WATER_CHANGE&date_from={f}&date_to={t}")
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


# -- forecast (M61) ----------------------------------------------------------

def test_forecast_endpoint_aoi_and_region(make_client, diagram_obs, synthetic_aoi):
    c = make_client("ANALYST")
    body = c.get("/api/diagram/forecast?band=RAIN_24H").json()
    assert body["band_code"] == "RAIN_24H" and body["region_id"] is None and body["horizon"] == 15
    if body["points"]:
        assert len(body["points"]) == 15 and all(p["lo"] <= p["mean"] <= p["hi"] and p["lo"] >= 0 for p in body["points"])
    rid = synthetic_aoi["TST001"]
    r = c.get(f"/api/diagram/forecast?band=NDVI&region_id={rid}&end={diagram_obs[0].isoformat()}&horizon=20").json()
    # Uji ini hanya punya 10 hari NDVI untuk TST001: cukup untuk forecast, tapi
    # terlalu pendek untuk backtest -> SES, keyakinan rendah.
    assert r["region_id"] == rid and r["n_obs"] >= 10 and r["last_obs_date"] == diagram_obs[0].isoformat()
    assert len(r["points"]) == 20 and r["points"][0]["x"] == (diagram_obs[0] + timedelta(days=1)).isoformat()
    assert r["confidence"] == "rendah"


def test_forecast_validation(make_client, synthetic_aoi):
    c = make_client("ANALYST")
    r = c.get(f"/api/diagram/forecast?band=WATER_CHANGE&region_id={synthetic_aoi['TST001']}")
    assert (r.status_code, r.json()["code"]) == (400, "INVALID_BAND")
    r = c.get("/api/diagram/forecast?band=RAIN_24H&region_id=999999")
    assert (r.status_code, r.json()["code"]) == (400, "NOT_KECAMATAN")
    assert c.get("/api/diagram/forecast?band=RAIN_24H&horizon=31").status_code == 422
    assert make_client("USER").get("/api/diagram/forecast?band=RAIN_24H").status_code == 403


def _synthetic(days: int, f, start=None):
    from datetime import date
    start = start or date(2023, 1, 1)
    return [(start + timedelta(days=k), f(k)) for k in range(days)]


def test_band_forecast_picks_seasonal_model_for_seasonal_series():
    import math

    import numpy as np

    from etl import band_forecast as bf
    rng = np.random.default_rng(1)
    pts = _synthetic(3 * 365, lambda k: 0.5 + 0.3 * math.sin(2 * math.pi * k / 365.25) + rng.normal(0, 0.03))
    r = bf.forecast(pts, "NDVI")
    assert r["model"] in ("clim", "clim_ar1") and r["backtest"]["skill"] > 0
    assert len(r["points"]) == 15 and all(-1 <= p["lo"] <= p["mean"] <= p["hi"] <= 1 for p in r["points"])
    widths = [p["hi"] - p["lo"] for p in r["points"]]
    assert all(b >= a - 1e-3 for a, b in zip(widths, widths[1:]))   # pita tidak menyempit ke depan


def test_band_forecast_rain_bounds_and_short_series():
    from etl import band_forecast as bf
    pts = _synthetic(800, lambda k: 0.0 if k % 3 else 40.0)
    r = bf.forecast(pts, "RAIN_24H")
    assert r["points"] and all(p["lo"] >= 0 for p in r["points"])
    # S1: < 1 tahun riwayat -> model musiman tidak ikut bersaing.
    s1 = bf.forecast(_synthetic(300, lambda k: -12.0 + 0.01 * k)[::12], "VV")
    assert s1["backtest"] and not {"clim", "clim_ar1"} & set(s1["backtest"]["mae_by_model"])
    assert any("celah" in n for n in s1["notes"])
    few = bf.forecast(_synthetic(5, lambda k: 1.0), "NDVI")
    assert few["points"] == [] and few["model"] is None and few["notes"]
    # Hari kosong (None) diabaikan, bukan dihitung nol.
    gaps = bf.forecast([(d, None if i % 2 else v) for i, (d, v) in enumerate(_synthetic(60, lambda k: 5.0))], "FLOOD")
    assert gaps["n_obs"] == 30 and all(abs(p["mean"] - 5.0) < 1e-6 for p in gaps["points"])


def test_forecast_mean_of_several_kecamatan(make_client, diagram_obs, synthetic_aoi):
    """Grafik rerata kecamatan terpilih (Tren & evaluasi alert, CH-03)."""
    c = make_client("ANALYST")
    a, b = synthetic_aoi["TST001"], synthetic_aoi["TST003"]
    end = diagram_obs[0].isoformat()
    body = c.get(f"/api/diagram/forecast?band=RAIN_24H&region_ids={b},{a}&end={end}").json()
    assert body["region_ids"] == sorted([a, b]) and body["region_id"] is None and len(body["points"]) == 15
    # Rerata TST001 (10 + i) dan TST003 (60 + i) = 35 + i: forecast di sekitar itu, bukan nol.
    assert 20 < body["points"][0]["mean"] < 60
    single = c.get(f"/api/diagram/forecast?band=RAIN_24H&region_ids={a}&end={end}").json()
    assert single["region_id"] == a
    r = c.get("/api/diagram/forecast?band=RAIN_24H&region_ids=" + ",".join(str(a) for _ in range(1)) + ",x")
    assert (r.status_code, r.json()["code"]) == (400, "BAD_REQUEST")


# -- forecast tersimpan (M62) ---------------------------------------------------

def test_forecast_store_refresh_skips_unchanged_and_api_reads_it(make_client, db_client, diagram_obs, synthetic_aoi):
    from etl import forecast_store as fs
    from etl import hydromet_aggregate as ha

    bands = ("RAIN_24H", "RAIN_30D")
    first = fs.refresh(db_client, bands=bands)
    assert first["failed"] == 0 and first["computed"] + first["skipped"] > 0
    again = fs.refresh(db_client, bands=bands)
    assert again["computed"] == 0 and again["skipped"] > 0            # data tidak berubah -> tidak dihitung ulang

    c = make_client("ANALYST")
    rid = synthetic_aoi["TST001"]
    body = c.get(f"/api/diagram/forecast?band=RAIN_24H&region_id={rid}").json()
    assert body["stored"] is True and body["computed_at"] and len(body["points"]) == 15
    with db_client.session() as sess:
        n_pts, _ = sess.execute(text("""
            SELECT (SELECT count(*) FROM band_forecast_points p WHERE p.forecast_id = f.forecast_id),
                   (SELECT count(*) FROM band_forecast_scores s WHERE s.forecast_id = f.forecast_id)
            FROM band_forecasts f JOIN spectral_bands b USING (band_id)
            WHERE b.band_code = 'RAIN_24H' AND f.region_id = :r ORDER BY f.computed_at DESC LIMIT 1"""), {"r": rid}).one()
    assert n_pts == 15

    # Rentang yang memotong data (end sebelum observasi terakhir) dihitung di tempat.
    past = c.get(f"/api/diagram/forecast?band=RAIN_24H&region_id={rid}&end={diagram_obs[3].isoformat()}").json()
    assert past["stored"] is False and past["last_obs_date"] == diagram_obs[3].isoformat()

    # Data baru masuk -> cap band berubah -> forecast tersimpan basi sampai refresh berikutnya.
    with db_client.session() as sess:
        ha.upsert_observations(sess, "RAIN_30D", _today() - timedelta(days=400), {rid: ha.ZonalResult(5.0, 1.0, 1)})
    stale = c.get(f"/api/diagram/forecast?band=RAIN_30D&region_id={rid}").json()
    assert stale["stored"] is False
    redo = fs.refresh(db_client, bands=("RAIN_30D",))
    assert redo["computed"] > 0
    assert c.get(f"/api/diagram/forecast?band=RAIN_30D&region_id={rid}").json()["stored"] is True
