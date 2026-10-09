# etl/band_forecast.py
"""Forecast 15 hari per band untuk halaman Forecast (M61).

Satu deret = satu band, rerata AOI atau satu kecamatan, SELURUH riwayat di
database (bukan hanya 30 hari yang digambar). Lima model bersaing:

    naive           nilai terakhir berlanjut
    SES             simple exponential smoothing, alpha dipilih dari grid
    Holt damped     level + tren teredam (phi 0,9)
    musiman         klimatologi hari-dalam-tahun (rerata ±15 hari, semua tahun)
    musiman+AR1     klimatologi + anomali hari terakhir yang meluruh phi^k
                    (phi = autokorelasi lag-1 anomali)

Model dipilih per deret lewat backtest rolling-origin: titik asal mundur
tiap 30 hari sampai 12 kali (setahun penuh, semua musim), tiap asal meramal 15 hari, error dihitung hanya
pada hari yang benar-benar teramati (hari hasil interpolasi tidak dinilai).
Model dengan MAE rata-rata terkecil menang; skill = 1 - MAE/MAE naive.

Pita 80% = kuantil 10–90% error backtest model terpilih per langkah (dikumpul
dari langkah ±2 di sekitarnya), dibuat tidak menyempit ke depan, lalu dijepit
ke rentang fisik band. Hujan dimodelkan di ruang log1p (miring, banyak nol).

Klimatologi butuh ≥ 1 tahun riwayat, jadi Sentinel-1 (riwayat < 1 tahun)
otomatis hanya memakai naive/SES/Holt. SES/Holt dilatih pada 365 hari terakhir:
dengan alpha ≥ 0,05 data yang lebih tua praktis tidak berpengaruh, dan
memangkasnya membuat satu deret selesai dalam puluhan milidetik.

Modul murni numerik (numpy): tanpa DB, tanpa disk.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np

HORIZON = 15
FIT_WINDOW = 365
ORIGINS = 12
ORIGIN_STEP = 30
MIN_OBS = 10
MIN_TRAIN = 30
CLIM_MIN_DAYS = 395
CLIM_HALF_WINDOW = 15
INTERVAL = 80

LOG_BANDS = {"RAIN_24H", "RAIN_72H", "RAIN_7D", "RAIN_30D"}
BOUNDS: dict[str, tuple[float | None, float | None]] = {
    "RAIN_24H": (0.0, None), "RAIN_72H": (0.0, None), "RAIN_7D": (0.0, None), "RAIN_30D": (0.0, None),
    "FLOOD": (0.0, 100.0), "WATER_PCT": (0.0, 100.0),
    "NDVI": (-1.0, 1.0), "NDWI": (-1.0, 1.0),
    "VV": (-40.0, 10.0), "VH": (-40.0, 10.0),
}

MODEL_LABELS = {
    "naive": "Naive (nilai terakhir)",
    "ses": "Exponential smoothing (SES)",
    "holt": "Holt tren teredam",
    "clim": "Musiman (klimatologi)",
    "clim_ar1": "Musiman + anomali AR(1)",
}


# -- model ---------------------------------------------------------------------
# fit(y, doy) -> objek dengan predict(doy_future) dan sigma(h). `doy` = indeks
# hari-dalam-tahun 0..365 untuk tiap titik grid harian.

class _Naive:
    def __init__(self, y, doy):
        self.last = float(y[-1])
        d = np.diff(y[-FIT_WINDOW:])
        self.s = float(np.std(d)) if len(d) > 1 else 0.0

    def predict(self, doy_f):
        return np.full(len(doy_f), self.last)

    def sigma(self, h):
        return self.s * np.sqrt(np.arange(1, h + 1))


class _SES:
    ALPHAS = np.arange(0.05, 1.0, 0.05)

    def __init__(self, y, doy):
        y = y[-FIT_WINDOW:]
        level = np.full(len(self.ALPHAS), y[0])
        sse = np.zeros(len(self.ALPHAS))
        for v in y[1:]:
            e = v - level
            sse += e * e
            level += self.ALPHAS * e
        k = int(np.argmin(sse))
        self.a, self.level = float(self.ALPHAS[k]), float(level[k])
        self.s = float(np.sqrt(sse[k] / max(1, len(y) - 1)))

    def predict(self, doy_f):
        return np.full(len(doy_f), self.level)

    def sigma(self, h):
        k = np.arange(1, h + 1)
        return self.s * np.sqrt(1 + (k - 1) * self.a ** 2)


class _Holt:
    PHI = 0.9
    GRID = np.array([(a, b) for a in (0.1, 0.2, 0.3, 0.5, 0.7) for b in (0.05, 0.1, 0.2)])

    def __init__(self, y, doy):
        y = y[-FIT_WINDOW:]
        a, b = self.GRID[:, 0], self.GRID[:, 1]
        level = np.full(len(a), y[0])
        trend = np.full(len(a), y[1] - y[0] if len(y) > 1 else 0.0)
        sse = np.zeros(len(a))
        for v in y[1:]:
            f = level + self.PHI * trend
            e = v - f
            sse += e * e
            level = f + a * e
            trend = self.PHI * trend + b * a * e
        k = int(np.argmin(sse))
        self.a, self.b = float(a[k]), float(b[k])
        self.level, self.trend = float(level[k]), float(trend[k])
        self.s = float(np.sqrt(sse[k] / max(1, len(y) - 1)))

    def predict(self, doy_f):
        k = np.arange(1, len(doy_f) + 1)
        return self.level + np.cumsum(self.PHI ** k) * self.trend

    def sigma(self, h):
        k = np.arange(1, h + 1)
        return self.s * np.sqrt(1 + (k - 1) * (self.a ** 2) * (1 + self.b) ** 2)


def _climatology(y, doy) -> np.ndarray:
    """Rerata per hari-dalam-tahun, dihaluskan jendela melingkar ±15 hari."""
    sums = np.bincount(doy, weights=y, minlength=366)
    cnts = np.bincount(doy, minlength=366).astype(float)
    w = np.ones(2 * CLIM_HALF_WINDOW + 1)
    pad = CLIM_HALF_WINDOW
    s = np.convolve(np.concatenate([sums[-pad:], sums, sums[:pad]]), w, mode="valid")
    c = np.convolve(np.concatenate([cnts[-pad:], cnts, cnts[:pad]]), w, mode="valid")
    return np.where(c > 0, s / np.maximum(c, 1), float(np.mean(y)))


class _Clim:
    def __init__(self, y, doy):
        self.clim = _climatology(y, doy)
        self.s = float(np.std(y - self.clim[doy]))

    def predict(self, doy_f):
        return self.clim[doy_f]

    def sigma(self, h):
        return np.full(h, self.s)


class _ClimAR1:
    def __init__(self, y, doy):
        self.clim = _climatology(y, doy)
        an = y - self.clim[doy]
        a0, a1 = an[:-1] - an[:-1].mean(), an[1:] - an[1:].mean()
        den = float(np.sqrt(np.sum(a0 * a0) * np.sum(a1 * a1)))
        self.phi = float(np.clip(np.sum(a0 * a1) / den, 0.0, 0.99)) if den > 0 else 0.0
        self.last = float(an[-1])
        self.s = float(np.std(an))

    def predict(self, doy_f):
        k = np.arange(1, len(doy_f) + 1)
        return self.clim[doy_f] + self.last * self.phi ** k

    def sigma(self, h):
        k = np.arange(1, h + 1)
        return self.s * np.sqrt(1 - self.phi ** (2 * k))


_MODELS = {"naive": _Naive, "ses": _SES, "holt": _Holt, "clim": _Clim, "clim_ar1": _ClimAR1}
_SEASONAL = {"clim", "clim_ar1"}


# -- inti ----------------------------------------------------------------------

def _doy(d: date) -> int:
    return d.timetuple().tm_yday - 1


def _grid(pts: list[tuple[date, float]]):
    """Observasi tak beraturan -> grid harian (interpolasi linier) + mask hari teramati."""
    first = pts[0][0]
    x = np.array([(d - first).days for d, _ in pts])
    v = np.array([val for _, val in pts], dtype=float)
    idx = np.arange(0, x[-1] + 1)
    observed = np.zeros(len(idx), dtype=bool)
    observed[x] = True
    days = [first + timedelta(days=int(i)) for i in idx]
    max_gap = int(np.max(np.diff(x))) if len(x) > 1 else 0
    return days, np.interp(idx, x, v), observed, max_gap


def forecast(points: list[tuple[date, float | None]], band_code: str, horizon: int = HORIZON) -> dict:
    """Forecast satu deret. points: [(tanggal, nilai)] boleh tak urut dan
    berisi None. Hasil siap JSON: {model, model_label, confidence, backtest,
    points:[{x, mean, lo, hi}], notes, ...}."""
    pts = sorted((d, float(v)) for d, v in points if v is not None and np.isfinite(v))
    out = {"band_code": band_code, "horizon": horizon, "interval": INTERVAL, "n_obs": len(pts),
           "history_from": pts[0][0].isoformat() if pts else None,
           "last_obs_date": pts[-1][0].isoformat() if pts else None,
           "model": None, "model_label": None, "confidence": None, "backtest": None, "points": [], "notes": []}
    if len(pts) < MIN_OBS:
        out["notes"].append(f"Baru {len(pts)} titik data; forecast butuh minimal {MIN_OBS}.")
        return out

    log = band_code in LOG_BANDS
    days, raw, observed, max_gap = _grid(pts)
    y = np.log1p(np.clip(raw, 0, None)) if log else raw
    doy = np.array([_doy(d) for d in days])
    n = len(y)
    back = (lambda a: np.expm1(a)) if log else (lambda a: a)

    clim_ok = n - horizon - (ORIGINS - 1) * ORIGIN_STEP >= CLIM_MIN_DAYS
    candidates = [m for m in _MODELS if m not in _SEASONAL or clim_ok]
    origins = [o for o in (n - horizon - j * ORIGIN_STEP for j in range(ORIGINS)) if o >= MIN_TRAIN]

    errs: dict[str, list[np.ndarray]] = {m: [] for m in candidates}
    abs_err: dict[str, list[float]] = {m: [] for m in candidates}
    for o in origins:
        mask = observed[o:o + horizon]
        if not mask.any():
            continue
        truth = y[o:o + horizon]
        for m in candidates:
            pred = _MODELS[m](y[:o], doy[:o]).predict(doy[o:o + horizon])
            e = np.where(mask, truth - pred, np.nan)
            errs[m].append(e)
            abs_err[m].extend(np.abs(back(truth[mask]) - back(pred[mask])).tolist())

    n_bt = len(errs[candidates[0]])
    if n_bt:
        mae = {m: float(np.mean(abs_err[m])) for m in candidates}
        best = min(mae, key=mae.get)
        skill = 1 - mae[best] / mae["naive"] if mae["naive"] > 0 else 0.0
        out["backtest"] = {"origins": n_bt, "horizon": horizon, "mae": round(mae[best], 4),
                           "mae_naive": round(mae["naive"], 4), "skill": round(skill, 3),
                           "mae_by_model": {m: round(v, 4) for m, v in mae.items()}}
    else:
        best, skill = "ses", None
        out["notes"].append("Riwayat terlalu pendek untuk backtest; dipakai SES tanpa pembanding.")

    fut_days = [days[-1] + timedelta(days=k) for k in range(1, horizon + 1)]
    model = _MODELS[best](y, doy)
    pred = model.predict(np.array([_doy(d) for d in fut_days]))

    lo_q, hi_q = _interval(errs.get(best) or [], model.sigma(horizon), horizon)
    lo_b, hi_b = BOUNDS.get(band_code, (None, None))
    lo_b = -np.inf if lo_b is None else lo_b
    hi_b = np.inf if hi_b is None else hi_b
    clip = lambda a: np.clip(back(a), lo_b, hi_b)  # noqa: E731
    mean, lo, hi = clip(pred), clip(pred + lo_q), clip(pred + hi_q)
    out["points"] = [{"x": d.isoformat(), "mean": round(float(m), 4), "lo": round(float(a), 4), "hi": round(float(b), 4)}
                     for d, m, a, b in zip(fut_days, mean, lo, hi)]
    out["model"], out["model_label"] = best, MODEL_LABELS[best]
    out["confidence"] = ("rendah" if skill is None or skill < 0.05 or n_bt < 4
                         else "tinggi" if skill >= 0.2 and n_bt >= 8 else "sedang")
    if skill is not None and skill <= 0:
        out["notes"].append("Tidak ada model yang mengalahkan naive di backtest; forecast setara \"keadaan terakhir berlanjut\".")
    if max_gap > 10:
        out["notes"].append(f"Ada celah data {max_gap} hari yang diisi interpolasi linier.")
    return out


def _interval(errs: list[np.ndarray], sigma: np.ndarray, h: int) -> tuple[np.ndarray, np.ndarray]:
    """Kuantil 10/90% error backtest per langkah (± 2 langkah tetangga);
    jatuh ke ±1,2816σ model bila error backtest terlalu sedikit."""
    z = 1.2816
    lo, hi = -z * sigma, z * sigma
    if errs:
        e = np.vstack(errs)
        for k in range(h):
            pool = e[:, max(0, k - 2):k + 3].ravel()
            pool = pool[~np.isnan(pool)]
            if len(pool) >= 8:
                lo[k], hi[k] = min(np.quantile(pool, 0.1), 0.0), max(np.quantile(pool, 0.9), 0.0)
    return np.minimum.accumulate(lo), np.maximum.accumulate(hi)
