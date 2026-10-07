# etl/band_catalog.py
"""Penjelasan satelit dan band untuk halaman Citra dan Diagram (M56).

Satu tempat untuk teks yang dibaca pengguna awam: satelit ini mengukur apa,
band ini berarti apa, dan garis ambang mana yang digambar di grafik. Nama
band, satuan, dan sumbernya tetap dari tabel ``spectral_bands``; modul ini
hanya menambah teks, warna garis, dan ambang.

Ambang TIDAK ditulis ulang di sini: semuanya dibaca dari
``etl.live_interpret.THRESHOLDS``, satu-satunya tempat ambang kalimat kondisi
Live (dan, lewat ``sync_bmkg_thresholds``, ambang hujan BMKG dari
``alert_rules``). Jadi garis ambang di Diagram selalu sama dengan angka yang
dipakai kalimat kondisi dan alert.
"""
from __future__ import annotations

from etl.live_interpret import THRESHOLDS

# Kunci halaman Citra (hash #citra/<kunci>) -> source_code + awalan preview.
SOURCES: dict[str, dict] = {
    "s1": {
        "source_code": "SENTINEL1",
        "label": "Sentinel-1",
        "prefix": "s1_",
        "about": ("Satelit radar (SAR) milik ESA. Radar memancarkan gelombang mikro sendiri, jadi tetap "
                  "melihat permukaan saat berawan dan malam hari. Permukaan air yang tenang memantulkan "
                  "gelombang menjauh dari satelit sehingga tampak gelap; karena itu Sentinel-1 dipakai "
                  "untuk menandai genangan."),
        "revisit": "±6–12 hari sekali di Lebak Selatan",
        "resolution": "10 m",
        "extractable": [
            "Backscatter VV dan VH (dB): kekasaran dan kebasahan permukaan.",
            "Persen piksel air (VH di bawah ambang): perkiraan luas air terbuka.",
            "Perubahan air antar dua lintasan: air baru, surut, dan tetap (km²).",
        ],
        "limits": "Tidak menangkap banjir yang naik-surut dalam beberapa jam di antara dua lintasan. "
                  "Relief 3D memakai DEM, bukan radar — GRD tidak mengukur tinggi.",
    },
    "modis": {
        "source_code": "MODIS",
        "label": "MODIS",
        "prefix": "modis_",
        "about": ("Sensor optik di satelit Terra dan Aqua (NASA) yang memotret seluruh bumi setiap hari "
                  "pada resolusi 250–500 m. Seperti kamera, MODIS tidak menembus awan: saat musim hujan "
                  "tile sering kosong justru ketika paling dibutuhkan."),
        "revisit": "harian (komposit 8 hari untuk indeks)",
        "resolution": "250–500 m",
        "extractable": [
            "Genangan MCDWD (%): bagian area teramati yang diklasifikasikan banjir oleh NASA.",
            "NDVI: kehijauan vegetasi; penurunan tajam menandakan tekanan atau kerusakan tanaman.",
            "NDWI: kebasahan/air permukaan; nilai di atas 0 umumnya air terbuka.",
        ],
        "limits": "Tertutup awan berarti tidak ada data, bukan berarti aman.",
    },
    "gpm": {
        "source_code": "GPM",
        "label": "GPM IMERG",
        "prefix": "gpm_",
        "about": ("Perkiraan curah hujan dari konstelasi satelit GPM (NASA/JAXA), digabung menjadi "
                  "produk IMERG setiap 30 menit pada petak ±10 km. Dipakai untuk akumulasi hujan 24 jam, "
                  "72 jam, dan 7 hari per kecamatan."),
        "revisit": "setiap 30 menit (diringkas harian, hari UTC)",
        "resolution": "±10 km",
        "extractable": [
            "Hujan 24 jam dengan kategori BMKG (ringan s.d. ekstrem).",
            "Akumulasi 72 jam dan 7 hari: seberapa jenuh tanah.",
            "Alert hujan per kecamatan saat ambang BMKG terlampaui.",
        ],
        "limits": "Perkiraan satelit yang belum dikalibrasi penakar hujan lapangan; run Late bisa "
                  "berbeda dari run Final beberapa bulan kemudian.",
    },
}

# Satu warna per band, dipakai sama di semua grafik supaya band yang sama
# selalu dikenali dari warnanya. Kontras diuji terhadap layar CRT gelap.
BANDS: dict[str, dict] = {
    "VV": {"color": "#4de1ff", "about": "Pantulan radar polarisasi VV. Turun bila permukaan menjadi lebih basah atau halus "
                                       "(genangan, tanah jenuh). Penurunan rata-rata ≥ {s1_vv_drop_db} dB antar scene ditandai."},
    "VH": {"color": "#2a9df4", "about": "Pantulan radar polarisasi silang VH, peka terhadap vegetasi dan air. Piksel di bawah "
                                       "{s1_vh_water_db} dB dihitung sebagai air terbuka."},
    "WATER_PCT": {"color": "#8f9bff", "about": "Persen piksel AOI dengan VH di bawah ambang air. Badan air permanen (laut, sungai) "
                                              "selalu ikut terhitung, jadi yang dibaca adalah perubahannya."},
    "WATER_CHANGE": {"color": "#c08cff", "about": "Luas perubahan air dibanding scene Sentinel-1 sebelumnya (km²)."},
    "FLOOD": {"color": "#ff6b6b", "about": "Persen area teramati yang diklasifikasikan banjir oleh produk MODIS MCDWD."},
    "NDVI": {"color": "#33ff99", "about": "Indeks kehijauan vegetasi (-1 s.d. 1). Turun ≥ {ndvi_drop} antar komposit "
                                         "menandakan tekanan vegetasi."},
    "NDWI": {"color": "#00d1b2", "about": "Indeks air permukaan (-1 s.d. 1). Di atas {ndwi_water} umumnya air terbuka."},
    "RAIN_24H": {"color": "#ffb000", "about": "Curah hujan satu hari UTC (07.00–07.00 WIB). Kategori BMKG: lebat ≥ "
                                             "{rain_24h_warn_mm} mm, sangat lebat ≥ {rain_24h_high_mm} mm."},
    "RAIN_72H": {"color": "#ff8a00", "about": "Akumulasi hujan tiga hari. Menunjukkan seberapa jenuh tanah menjelang longsor/banjir."},
    "RAIN_7D": {"color": "#ff5fa2", "about": "Akumulasi hujan tujuh hari."},
    "RAIN_30D": {"color": "#d9d9d9", "about": "Akumulasi hujan tiga puluh hari, untuk melihat musim basah/kering."},
}

# Garis ambang per band: (label, kunci THRESHOLDS). Band tanpa ambang mutlak
# (VV, NDVI: ambangnya berupa PERUBAHAN antar scene) tidak diberi garis.
_THRESHOLD_KEYS: dict[str, list[tuple[str, str]]] = {
    "VH": [("air", "s1_vh_water_db")],
    "WATER_PCT": [("waspada", "s1_vh_first_scene_warn_pct")],
    "FLOOD": [("waspada", "modis_flood_warn_pct"), ("tinggi", "modis_flood_high_pct")],
    "NDWI": [("air", "ndwi_water")],
    "RAIN_24H": [("lebat", "rain_24h_warn_mm"), ("sangat lebat", "rain_24h_high_mm")],
    "RAIN_72H": [("waspada", "rain_72h_warn_mm"), ("tinggi", "rain_72h_high_mm")],
    "RAIN_7D": [("waspada", "rain_7d_warn_mm"), ("tinggi", "rain_7d_high_mm")],
}

# Label + satuan metrik live_scene_metrics untuk tabel "angka" halaman Citra.
# Satuan None = pakai satuan band (spectral_bands.unit).
METRICS: dict[str, tuple[str, str | None]] = {
    "mean": ("rata-rata", None),
    "max": ("maksimum", None),
    "pct_below_threshold": ("piksel di bawah ambang air", "%"),
    "threshold_db": ("ambang air", "dB"),
    "frames": ("jumlah frame", ""),
    "valid_pixels": ("piksel valid", ""),
    "valid_pct": ("piksel teramati", "%"),
    "cloud_pct": ("tertutup awan", "%"),
    "flood_pct": ("genangan tidak biasa", "%"),
    "recurring_pct": ("genangan musiman", "%"),
    "water_pct": ("air", "%"),
    "age_days_median": ("umur komposit (median)", "hari"),
    "lookback_days": ("jendela komposit", "hari"),
    "new_km2": ("air baru", "km²"),
    "receded_km2": ("air surut", "km²"),
    "persistent_km2": ("air tetap", "km²"),
    "valid_km2": ("luas teramati", "km²"),
    "same_orbit": ("orbit sama dengan pembanding (1 = ya)", ""),
    # Angka harian Job Hidromet (v_citra_obs_aoi), lintas kecamatan AOI.
    "aoi_mean": ("rata-rata kecamatan AOI", None),
    "aoi_max": ("tertinggi antar kecamatan", None),
    "aoi_min": ("terendah antar kecamatan", None),
    "n_regions": ("kecamatan bernilai", ""),
}
METRIC_LABELS = {k: v[0] for k, v in METRICS.items()}


def metric_unit(metric_name: str, band_unit: str | None) -> str:
    unit = METRICS.get(metric_name, (None, ""))[1]
    return (band_unit or "") if unit is None else unit


# Band per kecamatan (region_observations, Job Hidromet) vs band tingkat AOI
# (live_scene_metrics, siklus Live). Sentinel-1 tidak dihitung per kecamatan.
REGION_BANDS = ("RAIN_24H", "RAIN_72H", "RAIN_7D", "RAIN_30D", "FLOOD", "NDVI", "NDWI")
AOI_BANDS = ("VV", "VH")


def thresholds(band_code: str) -> list[dict]:
    return [{"label": label, "value": THRESHOLDS[key]}
            for label, key in _THRESHOLD_KEYS.get(band_code, []) if key in THRESHOLDS]


def about(band_code: str) -> str:
    text = BANDS.get(band_code, {}).get("about", "")
    try:
        return text.format(**{k: _fmt(v) for k, v in THRESHOLDS.items()})
    except (KeyError, IndexError):
        return text


def color(band_code: str) -> str:
    return BANDS.get(band_code, {}).get("color", "#cccccc")


def band_info(row) -> dict:
    """Satu band untuk UI dari baris {band_code, band_name, unit, source_code}."""
    code = row["band_code"]
    return {"band_code": code, "band_name": row["band_name"], "unit": row["unit"],
            "source_code": row["source_code"], "color": color(code), "about": about(code),
            "thresholds": thresholds(code),
            "per_region": code in REGION_BANDS}


def source_key(source_code: str) -> str | None:
    return next((k for k, v in SOURCES.items() if v["source_code"] == source_code), None)


def _fmt(v: float) -> str:
    s = f"{v:g}".replace(".", ",")
    return s.replace("-", "−")
