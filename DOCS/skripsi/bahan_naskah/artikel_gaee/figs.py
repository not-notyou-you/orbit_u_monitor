"""Gambar artikel GaEE dengan gaya visual yang sama dengan gambar BAB IV skripsi (teal, kotak membulat).

Pemakaian: python figs.py study_area.geojson <folder keluaran>
- fig1_study_area.png : peta 10 kecamatan wilayah kajian (study_area.geojson diekspor dari administrative_regions:
                         in_aoi = 10 kecamatan, ditambah kecamatan tetangga sebagai konteks)
- fig2_architecture.png, fig3_erd_core.png : diagram ortogonal, dirender oleh ../diagram_bab4.py
- fig4_benchmark.png  : median waktu kueri inti (benchmark/results/timing.csv, sama dengan Tabel 4.18 skripsi)
"""
import json, os, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.patches import Polygon
from matplotlib.ticker import FixedLocator, NullLocator

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import diagram_bab4 as DG  # noqa: E402

D, L = "#004e53", "#e5feff"
src, out = sys.argv[1], sys.argv[2]
plt.rcParams.update({"font.family": "DejaVu Sans", "text.color": D, "axes.labelcolor": D, "xtick.color": D,
                     "ytick.color": D, "axes.edgecolor": D})


# ---------------------------------------------------------------- Fig. 1 study area
def rings(g):
    return [p[0] for p in (g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]])]


def centroid(ring):
    a = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]):
        c = x0 * y1 - x1 * y0; a += c; cx += (x0 + x1) * c; cy += (y0 + y1) * c
    return cx / (3 * a), cy / (3 * a)


NUDGE = {"Wanasalam": (-0.012, -0.025), "Malingping": (0.012, 0.012)}  # label yang berdempetan
feats = json.load(open(src, encoding="utf-8"))["features"]
fig, ax = plt.subplots(figsize=(7.2, 5.4), dpi=300)
tot = 0
for f in sorted(feats, key=lambda f: f["properties"]["aoi"]):
    aoi = f["properties"]["aoi"]
    for r in rings(f["geometry"]):
        ax.add_patch(Polygon(r, closed=True, facecolor=L if aoi else "#f3f5f5",
                             edgecolor=D if aoi else "#c5cfd0", linewidth=1.0 if aoi else 0.5, zorder=2 if aoi else 1))
    if aoi:
        tot += f["properties"]["area_km2"]
        main = max(rings(f["geometry"]), key=len)
        x, y = centroid(main)
        dx, dy = NUDGE.get(f["properties"]["name"], (0, 0)); x += dx; y += dy
        ax.text(x, y, f["properties"]["name"], ha="center", va="center", fontsize=7, fontweight="bold", zorder=3,
                path_effects=[pe.withStroke(linewidth=2.2, foreground="white")])
pts = [c for f in feats if f["properties"]["aoi"] for r in rings(f["geometry"]) for c in r]
x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts); y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
ax.set_xlim(x0 - 0.04, x1 + 0.04); ax.set_ylim(y0 - 0.05, y1 + 0.04); ax.set_aspect("equal")
ax.set_facecolor("white")
ax.set_xlabel("Longitude (°E)", fontsize=8); ax.set_ylabel("Latitude (°)", fontsize=8); ax.tick_params(labelsize=7)
ax.text(0.5, 0.035, "Indian Ocean", transform=ax.transAxes, ha="center", fontsize=8, style="italic", color="#5f8f92")
ax.text(0.015, 0.97, "10 sub-districts, %.1f km$^2$ (WGS 84)" % tot, transform=ax.transAxes, fontsize=7, va="top")
ax.annotate("N", xy=(0.95, 0.96), xytext=(0.95, 0.85), xycoords="axes fraction", ha="center", va="center",
            fontsize=9, fontweight="bold", arrowprops=dict(arrowstyle="-|>", color=D, lw=1.4))
fig.tight_layout(); fig.savefig(out + "/fig1_study_area.png"); plt.close(fig)
print("luas wilayah kajian", round(tot, 1))

# ---------------------------------------------------------------- Fig. 4 benchmark
qs = ["Q1", "Q2", "Q3", "Q4", "Q5"]
names = ["Rainfall\npivot", "30-day\ntrend", "Spatial\nintersection", "Warning\nevaluation", "Recursive\nlineage"]
pg = [0.453, 0.307, 1.147, 1.057, 0.651]; my = [0.868, 0.677, 18.633, 15.131, 0.451]
fig, ax = plt.subplots(figsize=(6.4, 3.4), dpi=300); x = range(5); w = 0.36
b1 = ax.bar([i - w / 2 for i in x], pg, w, label="PostgreSQL 18.6 + PostGIS 3.6.2", color=D, edgecolor=D, linewidth=1.2)
b2 = ax.bar([i + w / 2 for i in x], my, w, label="MySQL 8.0.40", color=L, edgecolor=D, linewidth=1.2)
ax.set_yscale("log"); ax.set_ylim(0.15, 60)
ax.yaxis.set_major_locator(FixedLocator([0.2, 0.5, 1, 2, 5, 10, 20, 50])); ax.yaxis.set_minor_locator(NullLocator())
ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:g}"))
ax.set_ylabel("Median time (ms), log scale", fontsize=8)
ax.set_xticks(list(x)); ax.set_xticklabels([f"{q}\n{n}" for q, n in zip(qs, names)], fontsize=7.5)
ax.tick_params(axis="y", labelsize=7.5)
for bars in (b1, b2):
    for b in bars:
        ax.annotate("%.2f" % b.get_height(), (b.get_x() + b.get_width() / 2, b.get_height()), ha="center", va="bottom",
                    fontsize=6.5, fontweight="bold", xytext=(0, 2), textcoords="offset points")
ax.spines[["top", "right"]].set_visible(False); ax.legend(fontsize=7.5, frameon=False, loc="upper left")
fig.tight_layout(); fig.savefig(out + "/fig4_benchmark.png"); plt.close(fig)

# ---------------------------------------------------------------- Fig. 2 architecture
N = lambda x, y, w, h, label, shape="box": {"x": x, "y": y, "w": w, "h": h, "label": label, "shape": shape}
G = lambda name, x, y, w, h, label: {"name": name, "x": x, "y": y, "w": w, "h": h, "label": label}
E = DG.E
JOBS_Y = [140, 196, 252, 308, 364, 420]
ARCH = {"groups": [G("SRC", 20, 20, 240, 330, "OFFICIAL DATA PROVIDERS"),
                   G("ETL", 330, 20, 260, 470, "ETL LAYER (PYTHON)"),
                   G("STO", 660, 60, 250, 330, "STORAGE"),
                   G("APP", 980, 60, 260, 330, "APPLICATION LAYER")],
        "nodes": {
            "s1": N(40, 64, 200, 70, "ESA CDSE\nSentinel-1 GRD"),
            "mo": N(40, 154, 200, 70, "NASA LANCE / LAADS\nMODIS"),
            "gp": N(40, 244, 200, 70, "NASA GES DISC\nGPM IMERG"),
            "sch": N(355, 52, 210, 58, "APScheduler\nadvisory lock per job"),
            **{k: N(375, y, 190, 42, t) for k, y, t in zip(
                ["j1", "j2", "j3", "j4", "j6", "j5"], JOBS_Y,
                ["Daily hydromet job", "Sentinel-1 live cycle", "Periodic reports", "Stored forecasts",
                 "Dataset jobs (on demand)", "E-mail alerts"])},
            "pg": N(680, 100, 210, 120, "PostgreSQL 18 + PostGIS\n43 tables, 22 views\nGRANT, RLS, audit", "db"),
            "fs": N(680, 270, 210, 90, "File system\nCOG, HDF5, PNG, PDF", "db"),
            "api": N(1000, 100, 220, 70, "FastAPI REST API\nSET LOCAL ROLE per request"),
            "web": N(1000, 280, 220, 70, "Web client\nLeaflet, MapLibre 3D"),
            "smtp": N(375, 530, 190, 50, "SMTP server\n(external)", "dashed"),
            "users": N(1000, 530, 220, 50, "Users in five roles", "pill"),
            "scr": N(1290, 100, 170, 70, "Other scripts\n(API token)", "dashed"),
        },
        "edges": [
            E("SRC", "R", 185, "none", "ETL", "L", 185, "arrow", "download"),
            *[E("sch", "L", 81, "none", k, "L", y + 21, "arrow", via=[[345, 81], [345, y + 21]])
              for k, y in zip(["j1", "j2", "j3", "j4", "j6"], JOBS_Y[:5])],
            *[E(k, "R", y + 21, "none", "j5", "R", JOBS_Y[5] + 21, "arrow", via=[[577, y + 21], [577, JOBS_Y[5] + 21]])
              for k, y in (("j1", JOBS_Y[0]), ("j2", JOBS_Y[1]))],
            E("ETL", "R", 150, "none", "pg", "L", 150, "arrow", "monitor_etl", lp=[625, 136]),
            E("ETL", "R", 315, "none", "fs", "L", 315, "arrow", "files", lp=[625, 301]),
            E("pg", "R", 122, "arrow", "api", "L", 122, "arrow", "monitor_app", lp=[945, 108]),
            E("fs", "R", 315, "none", "api", "L", 158, "arrow", "read", via=[[945, 315], [945, 158]], lp=[945, 240]),
            E("api", "B", 1150, "arrow", "web", "T", 1150, "arrow", "HTTPS"),
            E("web", "B", 1110, "arrow", "users", "T", 1110, "arrow"),
            E("j5", "B", 470, "none", "smtp", "T", 470, "arrow"),
            E("smtp", "R", 555, "none", "users", "L", 555, "arrow", "e-mail"),
            E("scr", "L", 135, "arrow", "api", "R", 135, "arrow"),
        ]}

# ---------------------------------------------------------------- Fig. 3 core ERD
def ent(x, y, *rows):
    return {"x": x, "y": y, "rows": [r.split("|") for r in rows]}


C0, C1, C2 = 30, 440, 850
ERD = {"w": 290, "kw": 66, "nodes": {
    "data_lineage": ent(C0, 30, "PK|lineage_id|bigint", "FK,UK|parent_product_id|bigint", "FK,UK|child_product_id|bigint",
                        "|transformation_type|varchar", "|output_checksum|varchar"),
    "data_products": ent(C1, 30, "PK|product_id|bigint", "|file_path|text", "FK|job_id|bigint", "|data_hash_sha256|varchar"),
    "spectral_bands": ent(C2, 30, "PK|band_id|smallint", "UK|band_code|varchar"),
    "administrative_regions": ent(C0, 278, "PK|region_id|int", "UK|pcode|varchar"),
    "region_observations": ent(C1, 278, "PK|obs_id|bigint", "FK,UK|region_id|int", "FK,UK|band_id|smallint",
                               "UK|obs_date|date", "|value|numeric", "|valid_fraction|numeric", "FK|source_product_id|bigint"),
    "alert_rules": ent(C2, 278, "PK|rule_id|int", "UK|rule_code|varchar", "FK|band_id|smallint", "FK|disaster_type_id|smallint"),
    "disaster_events": ent(C0, 574, "PK|event_id|bigint", "FK|disaster_type_id|smallint", "FK|region_id|int",
                           "|event_date|date", "|info_source|varchar", "|is_verified|boolean"),
    "alert_events": ent(C1, 574, "PK|alert_id|bigint", "FK,UK|rule_id|int", "FK,UK|region_id|int",
                        "UK|observation_date|date", "FK|obs_id|bigint", "|observed_value|numeric", "|acknowledged_at|timestamptz"),
    "disaster_types": ent(C2, 574, "PK|disaster_type_id|smallint", "UK|type_code|varchar"),
}, "edges": [
    E("data_products", "L", 90, "one", "data_lineage", "R", 90, "zero_many", "parent"),
    E("data_products", "L", 140, "one", "data_lineage", "R", 140, "zero_many", "child"),
    E("data_products", "B", C1 + 145, "zero_one", "region_observations", "T", C1 + 145, "zero_many"),
    E("spectral_bands", "L", 90, "one", "region_observations", "R", 328, "zero_many", via=[[C1 + 290 + 50, 90], [C1 + 290 + 50, 328]]),
    E("spectral_bands", "B", C2 + 145, "one", "alert_rules", "T", C2 + 145, "zero_many"),
    E("alert_rules", "L", 378, "one", "alert_events", "R", 634, "zero_many", via=[[C1 + 290 + 80, 378], [C1 + 290 + 80, 634]]),
    E("disaster_types", "T", C2 + 145, "one", "alert_rules", "B", C2 + 145, "zero_many"),
    E("disaster_types", "B", C2 + 145, "one", "disaster_events", "B", C0 + 145, "zero_many",
      via=[[C2 + 145, 830], [C0 + 145, 830]]),
    E("administrative_regions", "R", 318, "one", "region_observations", "L", 318, "zero_many"),
    E("administrative_regions", "R", 352, "one", "alert_events", "L", 634, "zero_many", via=[[C0 + 290 + 60, 352], [C0 + 290 + 60, 634]]),
    E("administrative_regions", "B", C0 + 145, "one", "disaster_events", "T", C0 + 145, "zero_many"),
    E("region_observations", "B", C1 + 145, "zero_one", "alert_events", "T", C1 + 145, "zero_many"),
]}

DG.render([("fig2_architecture.png", "arch", ARCH), ("fig3_erd_core.png", "erd", ERD)], out)
