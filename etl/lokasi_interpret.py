# etl/lokasi_interpret.py
"""Kalimat kondisi SATU kecamatan untuk Pantau Lokasi di Beranda (M63).

Kalimat Live (etl/live_interpret.py) dibuat per scene untuk seluruh Live Area.
Pantau Lokasi butuh kalimat yang sama untuk satu kecamatan, dari deret waktu
dataset utama (``region_observations``: GPM/MODIS harian, Sentinel-1 per
lintasan). Ambang, format kalimat, dan aturan status gabungan TIDAK ditulis
ulang: semuanya dipakai dari live_interpret, jadi Beranda, kartu Live, garis
ambang Forecast, dan alert hidromet selalu memakai angka yang sama.

Yang berbeda dari kalimat Live hanya bentuk masukannya:
* MODIS per kecamatan berupa rerata indeks (NDWI) dan persen genangan
  (FLOOD) dengan ``valid_fraction``, bukan statistik piksel scene;
* pembanding = observasi SEBELUMNYA kecamatan itu (lintasan S1 sebelumnya,
  komposit MODIS sebelumnya), bukan scene Live sebelumnya;
* alert hujan 7 hari terakhir kecamatan itu ikut menaikkan status.
"""
from __future__ import annotations

from etl.live_interpret import (
    GENANGAN, NA, NORMAL, THRESHOLDS, TINGGI, WASPADA,
    _change_phrase, _modis_ndvi, _rain, _s1_vh, _s1_vv, _sentence, area_status, fmt,
)

# Urutan tampil = urutan baris tile (Sentinel-1, MODIS, GPM).
KEYS = ("s1_vv", "s1_vh", "modis_flood", "modis_ndvi", "modis_ndwi",
        "gpm_rain_24h", "gpm_rain_72h", "gpm_rain_7d")
# Band yang angkanya menjadi dasar tiap kalimat: tanggal observasinya adalah
# "tanggal data" butir itu (kunci anti-duplikat peringatan email, M64).
BAND_OF = {"s1_vv": "VV", "s1_vh": "WATER_PCT", "modis_flood": "FLOOD", "modis_ndvi": "NDVI",
           "modis_ndwi": "NDWI", "gpm_rain_24h": "RAIN_24H", "gpm_rain_72h": "RAIN_72H",
           "gpm_rain_7d": "RAIN_7D"}
_SEV_RANK = {"INFO": 1, "WARNING": 2, "CRITICAL": 3}
_SEV_LABEL = {"INFO": "hujan lebat", "WARNING": "hujan sangat lebat", "CRITICAL": "hujan ekstrem"}


def _v(obs: dict, band: str):
    e = obs.get(band)
    return None if not e else e.get("value")


def _valid_pct(obs: dict, band: str):
    e = obs.get(band) or {}
    vf = e.get("valid_fraction")
    return None if vf is None else float(vf) * 100.0


def _flood(latest: dict) -> dict:
    what = "peta genangan optik MODIS"
    v = _v(latest, "FLOOD")
    if v is None:
        return _sentence(what, NA, "belum ada angka genangan MODIS untuk kecamatan ini (tertutup awan atau belum diolah)")
    warn, high = THRESHOLDS["modis_flood_warn_pct"], THRESHOLDS["modis_flood_high_pct"]
    cat = GENANGAN if v >= high else WASPADA if v >= warn else NORMAL
    seen = _valid_pct(latest, "FLOOD")
    return _sentence(what, cat, f"{fmt(v)}% area teramati berkelas genangan (ambang waspada {fmt(warn, 0)}%)"
                     + (f", dengan {fmt(seen, 0)}% kecamatan teramati" if seen is not None else ""))


def _ndwi(latest: dict, prev: dict, rng: dict) -> dict:
    """Per kecamatan NDWI berupa rerata indeks, bukan persen piksel air: rerata
    satu kecamatan di atas ambang air (0) berarti sebagian besar permukaannya
    tampak basah -- jauh dari biasa untuk wilayah berbukit dan bervegetasi."""
    what = "indikasi air permukaan (NDWI)"
    v = _v(latest, "NDWI")
    if v is None:
        return _sentence(what, NA, "belum ada angka NDWI untuk kecamatan ini (tertutup awan atau belum diolah)")
    thr = THRESHOLDS["ndwi_water"]
    hi = (rng.get("NDWI") or {}).get("p98")
    # Tiga desimal bila dua desimal membuat nilai dan batasnya tampak sama
    # ("-0,59, di atas rentang biasa s.d. -0,59" membingungkan pembaca).
    nd = 3 if hi is not None and fmt(v, 2) == fmt(hi, 2) else 2
    base = f"rata-rata NDWI {fmt(v, nd)}"
    if v > thr:
        return _sentence(what, GENANGAN, f"{base}, di atas ambang air {fmt(thr, 0)}")
    if hi is not None and v > hi:
        return _sentence(what, WASPADA, f"{base}, di atas rentang biasa kecamatan ini (s.d. {fmt(hi, nd)})")
    return _sentence(what, NORMAL, f"{base}, " + _change_phrase(v, _v(prev, "NDWI"), "", 2, "pengamatan sebelumnya"))


def interpret_region(latest: dict, prev: dict, ranges: dict | None = None,
                     alerts: list[dict] | None = None) -> dict:
    """latest/prev: {band_code: {value, obs_date, valid_fraction, run_type}}.
    ranges: {band_code: {p02, p98}}. alerts: baris v_public_lokasi_alert.

    Hasil: {status: {label, level, text}, items: {key: kalimat},
    abnormal: [kalimat yang tidak normal + alert, masing-masing dengan `band` dan
    `date` = tanggal data yang mendasarinya], dates: {s1, modis, gpm}}."""
    ranges = ranges or {}
    alerts = alerts or []

    def m_s1(obs):
        return {"sentinel1": {"vv_mean_db": _v(obs, "VV"), "vh_water_pct": _v(obs, "WATER_PCT")}}

    def m_modis(obs):
        return {"modis": {"ndvi": {"mean": _v(obs, "NDVI"), "valid_pct": _valid_pct(obs, "NDVI")}
                          if _v(obs, "NDVI") is not None else None}}

    def m_gpm(obs):
        out = {}
        for w, band in (("24h", "RAIN_24H"), ("72h", "RAIN_72H"), ("7d", "RAIN_7D")):
            v = _v(obs, band)
            if v is not None:
                out[f"rain_{w}"] = {"mean_mm": v, "imerg_runs": (obs.get(band) or {}).get("run_type")}
        return {"gpm": out}

    prev_s1 = m_s1(prev) if (_v(prev, "VV") is not None or _v(prev, "WATER_PCT") is not None) else None
    prev_modis = m_modis(prev) if _v(prev, "NDVI") is not None else None
    items = {
        "s1_vv": _s1_vv(m_s1(latest), prev_s1, None),
        "s1_vh": _s1_vh(m_s1(latest), prev_s1, None),
        "modis_flood": _flood(latest),
        "modis_ndvi": _modis_ndvi(m_modis(latest), prev_modis, None),
        "modis_ndwi": _ndwi(latest, prev, ranges),
        "gpm_rain_24h": _rain("24h", "24 jam")(m_gpm(latest), None, None),
        "gpm_rain_72h": _rain("72h", "72 jam")(m_gpm(latest), None, None),
        "gpm_rain_7d": _rain("7d", "7 hari")(m_gpm(latest), None, None),
    }
    # Kalimat Live menyebut "scene"; untuk satu kecamatan pembandingnya adalah
    # lintasan/komposit sebelumnya kecamatan itu sendiri.
    for it in items.values():
        it["text"] = it["text"].replace("scene sebelumnya", "pengamatan sebelumnya")
        it["because"] = it["because"].replace("scene sebelumnya", "pengamatan sebelumnya")

    st = area_status(items)
    abnormal = [{"key": k, "what": it["what"], "because": it["because"], "category": it["category"],
                 "level": it["level"], "band": BAND_OF[k],
                 "date": (latest.get(BAND_OF[k]) or {}).get("obs_date")}
                for k, it in items.items() if it["level"] >= 1]

    worst = max(alerts, key=lambda a: (_SEV_RANK.get(a.get("severity"), 0), a.get("observation_date") or ""),
                default=None)
    if worst is not None:
        sev = worst.get("severity")
        abnormal.append({
            "key": "alert", "what": "alert hujan BMKG 7 hari terakhir", "category": "alert",
            "level": 2 if sev == "CRITICAL" else 1, "band": worst.get("band_code") or "RAIN_24H",
            # Tanggal = alert TERBARU, bukan yang terparah: kunci anti-duplikat
            # email (M64) harus berganti saat alert baru masuk, walau alert
            # lama yang lebih parah masih dalam jendela 7 hari.
            "date": max((a.get("observation_date") for a in alerts if a.get("observation_date")),
                        default=worst.get("observation_date")),
            "severity": sev,
            "observed_value": worst.get("observed_value"), "threshold_value": worst.get("threshold_value"),
            "because": (f"{_SEV_LABEL.get(sev, 'hujan lebat')} {fmt(worst.get('observed_value'))} mm pada "
                        f"{worst.get('observation_date')} (ambang {fmt(worst.get('threshold_value'), 0)} mm)"
                        + (f"; {len(alerts)} alert dalam 7 hari" if len(alerts) > 1 else "")),
        })
        lvl = 2 if sev == "CRITICAL" else 1
        if st["level"] < lvl:
            label = "Tinggi" if lvl == 2 else "Waspada"
            reasons = [] if st["level"] <= 0 else [st["text"].split(" — ", 1)[-1]]
            reasons.append("ada alert hujan BMKG dalam 7 hari terakhir")
            st = {**st, "label": label, "level": lvl, "text": f"{label} — " + " dan ".join(reasons)}

    # Status gabungan Live hanya membaca VH, indeks air, dan hujan 72 jam.
    # Untuk satu lokasi, setiap kalimat yang tidak normal (mis. hujan 7 hari,
    # NDVI turun) harus tercermin di status, karena Beranda menjelaskannya
    # sebagai "yang tidak normal" tepat di bawah status itu.
    if abnormal and st["level"] <= 0:
        worst_lvl = 2 if any(a["level"] >= 2 for a in abnormal) else 1
        label = "Tinggi" if worst_lvl == 2 else "Waspada"
        st = {**st, "label": label, "level": worst_lvl,
              "text": f"{label} — " + ", ".join(a["what"] for a in abnormal) + " melewati ambang"}

    def last(*bands):
        ds = [str((latest.get(b) or {}).get("obs_date")) for b in bands if (latest.get(b) or {}).get("obs_date")]
        return max(ds) if ds else None

    return {
        "status": {"label": st["label"], "level": st["level"], "text": st["text"]},
        "items": items,
        "abnormal": abnormal,
        "dates": {"s1": last("VV", "VH", "WATER_PCT"), "modis": last("FLOOD", "NDVI", "NDWI"),
                  "gpm": last("RAIN_24H", "RAIN_72H", "RAIN_7D")},
    }
