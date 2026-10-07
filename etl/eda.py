# etl/eda.py
"""Exploratory Data Analysis halaman Data (M56, INTERFACE.md §4.6).

Tahap *data understanding* sebelum membuat model data: per variabel —
jumlah, kekosongan, statistik deskriptif, sebaran (histogram), pencilan
(aturan 1,5 × IQR) — lalu korelasi antar variabel dan kelengkapan per hari.

Fungsi di sini murni (list angka masuk, dict keluar) supaya mudah diuji;
pengambilan data ada di ``api/routes/data.py``.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date

import numpy as np

HIST_BINS = 12


def describe(values: list[float | None], expected: int | None = None) -> dict:
    """Statistik satu variabel. ``expected`` = jumlah sel yang seharusnya
    terisi (hari × wilayah), untuk menghitung kekosongan termasuk baris
    yang tidak pernah ditulis sama sekali."""
    present = [float(v) for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))]
    n_rows = len(values)
    total = max(expected or 0, n_rows)
    out = {"n": len(present), "n_null": n_rows - len(present), "expected": total,
           "missing": total - len(present),
           "missing_pct": round((total - len(present)) / total * 100, 2) if total else None}
    if not present:
        return {**out, "mean": None, "std": None, "min": None, "q1": None, "median": None, "q3": None,
                "max": None, "skew": None, "outliers": 0, "outlier_bounds": None, "histogram": []}
    a = np.asarray(present)
    q1, med, q3 = (float(x) for x in np.percentile(a, [25, 50, 75]))
    iqr = q3 - q1
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    std = float(a.std(ddof=1)) if len(a) > 1 else 0.0
    skew = float(((a - a.mean()) ** 3).mean() / (a.std() ** 3)) if len(a) > 2 and a.std() > 0 else None
    counts, edges = np.histogram(a, bins=min(HIST_BINS, max(1, len(np.unique(a)))))
    return {**out, "mean": float(a.mean()), "std": std, "min": float(a.min()), "q1": q1, "median": med,
            "q3": q3, "max": float(a.max()), "skew": skew,
            "outliers": int(((a < lo) | (a > hi)).sum()), "outlier_bounds": [lo, hi],
            "histogram": [{"from": float(edges[i]), "to": float(edges[i + 1]), "count": int(c)}
                          for i, c in enumerate(counts)]}


def correlation(table: dict[tuple, dict[str, float | None]], variables: list[str]) -> dict:
    """Korelasi Pearson berpasangan. ``table`` = {kunci_baris: {variabel: nilai}};
    setiap pasangan memakai baris yang kedua nilainya ada (pairwise)."""
    matrix = []
    for a in variables:
        row = []
        for b in variables:
            pairs = [(r[a], r[b]) for r in table.values() if r.get(a) is not None and r.get(b) is not None]
            if len(pairs) < 3:
                row.append({"r": None, "n": len(pairs)})
                continue
            x, y = np.asarray(pairs, dtype=float).T
            if x.std() == 0 or y.std() == 0:
                row.append({"r": None, "n": len(pairs)})
                continue
            row.append({"r": round(float(np.corrcoef(x, y)[0, 1]), 3), "n": len(pairs)})
        matrix.append(row)
    return {"variables": variables, "matrix": matrix}


def daily_completeness(rows: list[tuple[date, str, float | None]], variables: list[str],
                       date_from: date, date_to: date, per_day_expected: int) -> list[dict]:
    """[{date, <variabel>: persen terisi}] untuk grafik kelengkapan."""
    filled: dict[tuple[date, str], int] = defaultdict(int)
    for d, var, v in rows:
        if v is not None:
            filled[(d, var)] += 1
    out = []
    n_days = (date_to - date_from).days + 1
    for i in range(n_days):
        d = date.fromordinal(date_from.toordinal() + i)
        out.append({"date": d.isoformat(),
                    **{v: round(filled[(d, v)] / per_day_expected * 100, 1) if per_day_expected else None
                       for v in variables}})
    return out
