#!/usr/bin/env python
"""Data sintetis deterministik untuk benchmark DBMS (DATABASE.md §1, M29).

BUKAN data produksi: bentuk dan volumenya meniru DB Monitor setelah backfill
2023–2025 (DATABASE.md §4.3), nilainya dibangkitkan dengan seed tetap supaya
setiap DBMS menerima baris yang persis sama dan hasil bisa diulang.

Keluaran di benchmark/data/ (CSV, geometri sebagai WKT EPSG:4326):
    regions.csv            28 kecamatan sintetis (10 AOI) — poligon grid di sekitar Lebak
    observations.csv       3 tahun × 10 kecamatan AOI × 7 band  (≈ 76.700 baris)
    alerts.csv             dari aturan BMKG 50/100/150 mm pada RAIN_24H
    disasters.csv          ±150 kejadian (sebagian terverifikasi)
    products.csv, lineage.csv  rantai produk sampai 6 tingkat (RAW → … → FUSED)

Pakai:  python benchmark/generate.py [--seed 20260929] [--out benchmark/data]
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
from datetime import date, timedelta
from pathlib import Path

BANDS = ["RAIN_24H", "RAIN_72H", "RAIN_7D", "RAIN_30D", "NDVI", "NDWI", "FLOOD"]
RULES = [(1, "FLOOD_RAIN24_HEAVY", 50.0, "INFO"), (2, "FLOOD_RAIN24_VHEAVY", 100.0, "WARNING"),
         (3, "FLOOD_RAIN24_EXTREME", 150.0, "CRITICAL")]
TYPES = ["BANJIR", "BANJIR_BANDANG", "LONGSOR", "KEKERINGAN"]
START, END = date(2023, 1, 1), date(2025, 12, 31)


def regions(rng: random.Random) -> list[dict]:
    """Grid 7 × 4 sel ±0,09° di sekitar Lebak; sel bergerigi agar poligon tidak trivial."""
    out, rid = [], 1
    x0, y0, dx, dy = 105.86, -7.00, 0.095, 0.09
    for j in range(4):
        for i in range(7):
            pts = []
            cx, cy = x0 + i * dx, y0 + j * dy
            # 4 sisi × 6 titik dengan jitter kecil (deterministik)
            corners = [(cx, cy), (cx + dx, cy), (cx + dx, cy + dy), (cx, cy + dy)]
            for k in range(4):
                (ax, ay), (bx, by) = corners[k], corners[(k + 1) % 4]
                for t in range(6):
                    f = t / 6
                    jx = rng.uniform(-0.004, 0.004) if 0 < t else 0
                    jy = rng.uniform(-0.004, 0.004) if 0 < t else 0
                    pts.append((ax + (bx - ax) * f + jx, ay + (by - ay) * f + jy))
            pts.append(pts[0])
            wkt = "MULTIPOLYGON(((" + ",".join(f"{x:.5f} {y:.5f}" for x, y in pts) + ")))"
            out.append({"region_id": rid, "pcode": f"IDBENCH{rid:03d}", "region_name": f"Kecamatan {rid:02d}",
                        "in_aoi": j < 2 and 1 <= i <= 5, "geom_wkt": wkt})
            rid += 1
    return out


def observations(rng: random.Random, aoi: list[int]) -> list[dict]:
    rows, obs_id = [], 1
    days = (END - START).days + 1
    rain = {r: [] for r in aoi}
    for r in aoi:
        wet = 0.0
        for d in range(days):
            day = START + timedelta(days=d)
            season = 0.5 + 0.5 * math.cos(2 * math.pi * (day.timetuple().tm_yday - 15) / 365)  # basah Des–Feb
            p_rain = 0.25 + 0.5 * season
            v = 0.0
            if rng.random() < p_rain:
                v = rng.gammavariate(0.9, 12 + 25 * season)
                if rng.random() < 0.01:
                    v += rng.uniform(80, 180)  # kejadian ekstrem
            rain[r].append(min(v, 400.0))
            wet = 0.8 * wet + v
    for d in range(days):
        day = (START + timedelta(days=d)).isoformat()
        for r in aoi:
            s = rain[r]
            acc = lambda n: sum(s[max(0, d - n + 1):d + 1])  # noqa: E731
            vals = {"RAIN_24H": s[d], "RAIN_72H": acc(3), "RAIN_7D": acc(7), "RAIN_30D": acc(30),
                    "NDVI": round(0.55 + 0.25 * rng.random(), 4) if rng.random() > 0.35 else None,
                    "NDWI": round(-0.75 + 0.3 * rng.random(), 4) if rng.random() > 0.35 else None,
                    "FLOOD": round(rng.random() * (s[d] / 40), 4) if rng.random() > 0.5 else None}
            for b in BANDS:
                v = vals[b]
                rows.append({"obs_id": obs_id, "region_id": r, "band_code": b, "obs_date": day,
                             "value": None if v is None else round(v, 4), "run_type": "F"})
                obs_id += 1
    return rows


def alerts(obs: list[dict]) -> list[dict]:
    out, aid = [], 1
    for o in obs:
        if o["band_code"] != "RAIN_24H" or o["value"] is None:
            continue
        for rule_id, _code, thr, sev in RULES:
            if o["value"] >= thr:
                out.append({"alert_id": aid, "rule_id": rule_id, "region_id": o["region_id"], "obs_id": o["obs_id"],
                            "observation_date": o["obs_date"], "observed_value": o["value"], "threshold_value": thr,
                            "severity": sev})
                aid += 1
    return out


def disasters(rng: random.Random, aoi: list[int], al: list[dict]) -> list[dict]:
    out, eid = [], 1
    # Sebagian kejadian mengikuti alert WARNING+ (hit), sebagian acak (miss/false alarm).
    strong = [a for a in al if a["severity"] != "INFO"]
    rng.shuffle(strong)
    for a in strong[:90]:
        d = date.fromisoformat(a["observation_date"]) + timedelta(days=rng.randint(0, 3))
        out.append({"event_id": eid, "type_code": "BANJIR", "region_id": a["region_id"], "event_date": d.isoformat(),
                    "is_verified": rng.random() < 0.8})
        eid += 1
    for _ in range(60):
        d = START + timedelta(days=rng.randrange((END - START).days))
        out.append({"event_id": eid, "type_code": rng.choice(TYPES), "region_id": rng.choice(aoi),
                    "event_date": d.isoformat(), "is_verified": rng.random() < 0.6})
        eid += 1
    return out


def products(rng: random.Random, n_chains: int = 1200) -> tuple[list[dict], list[dict]]:
    """Rantai RAW → ALIGNED → DESPECKLED → COG → FUSED (+ satu tingkat turunan) = 6 tingkat."""
    tiers = ["RAW", "ALIGNED", "DESPECKLED", "COG", "FUSED", "DERIVED"]
    prods, lin, pid, lid = [], [], 1, 1
    for c in range(n_chains):
        depth = 6 if c % 3 == 0 else rng.randint(2, 5)
        parent = None
        for t in range(depth):
            prods.append({"product_id": pid, "product_tier": tiers[t], "source": rng.choice(["SENTINEL1", "MODIS", "GPM"]),
                          "file_size_mb": round(rng.uniform(0.1, 900), 2), "sha256": f"{rng.getrandbits(256):064x}"})
            if parent is not None:
                lin.append({"lineage_id": lid, "parent_product_id": parent, "child_product_id": pid,
                            "transformation_type": f"{tiers[t - 1]}_TO_{tiers[t]}"})
                lid += 1
            parent = pid
            pid += 1
    return prods, lin


def write(path: Path, rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if v is None else (int(v) if isinstance(v, bool) else v)) for k, v in r.items()})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20260929)
    ap.add_argument("--out", default=str(Path(__file__).parent / "data"))
    a = ap.parse_args()
    rng = random.Random(a.seed)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    reg = regions(rng)
    aoi = [r["region_id"] for r in reg if r["in_aoi"]]
    obs = observations(rng, aoi)
    al = alerts(obs)
    dz = disasters(rng, aoi, al)
    pr, li = products(rng)
    for name, rows in [("regions", reg), ("observations", obs), ("alerts", al), ("disasters", dz),
                       ("products", pr), ("lineage", li)]:
        write(out / f"{name}.csv", rows)
    meta = {"seed": a.seed, "period": [START.isoformat(), END.isoformat()], "rows": {
        "regions": len(reg), "observations": len(obs), "alerts": len(al), "disasters": len(dz),
        "products": len(pr), "lineage": len(li)}, "note": "DATA SINTETIS — bukan data produksi"}
    (out / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(json.dumps(meta["rows"]))


if __name__ == "__main__":
    main()
