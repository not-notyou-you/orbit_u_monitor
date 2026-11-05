import json, sys, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon
out = sys.argv[2]
d = json.load(open(sys.argv[1], encoding="utf-8"))
fig, ax = plt.subplots(figsize=(7.2, 5.4), dpi=300)
tot = 0
for f in d["features"]:
    g = f["geometry"]; polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
    xs = []; ys = []
    for p in polys:
        ax.add_patch(Polygon(p[0], closed=True, facecolor="#d9d9d9", edgecolor="#000000", linewidth=0.7))
        xs += [c[0] for c in p[0]]; ys += [c[1] for c in p[0]]
    tot += f["properties"]["area_km2"]
    ax.text(sum(xs)/len(xs), sum(ys)/len(ys), f["properties"]["name"], ha="center", va="center", fontsize=7)
ax.autoscale_view(); ax.set_aspect("equal")
ax.set_xlabel("Longitude (°E)", fontsize=8); ax.set_ylabel("Latitude (°)", fontsize=8); ax.tick_params(labelsize=7)
ax.text(0.01, 0.01, "10 sub-districts, %.1f km$^2$ (WGS 84)" % tot, transform=ax.transAxes, fontsize=7)
fig.tight_layout(); fig.savefig(out + "/fig1_study_area.png"); print("area", tot)

qs = ["Q1", "Q2", "Q3", "Q4", "Q5"]; pg = [0.45, 0.29, 1.34, 1.76, 0.82]; my = [1.14, 0.67, 22.57, 16.64, 0.43]
fig, ax = plt.subplots(figsize=(6.4, 3.0), dpi=300); x = range(5); w = 0.38
b1 = ax.bar([i - w/2 for i in x], pg, w, label="PostgreSQL 18.6 + PostGIS 3.6.2", color="#333333")
b2 = ax.bar([i + w/2 for i in x], my, w, label="MySQL 8.0.40", color="#ffffff", edgecolor="#333333", hatch="///", linewidth=0.8)
ax.set_yscale("log"); ax.set_ylabel("median time (ms), log scale", fontsize=8)
ax.set_xticks(list(x)); ax.set_xticklabels(qs, fontsize=9); ax.tick_params(axis="y", labelsize=8)
for bars in (b1, b2):
    for b in bars:
        ax.annotate("%.2f" % b.get_height(), (b.get_x()+b.get_width()/2, b.get_height()), ha="center", va="bottom", fontsize=7, xytext=(0, 2), textcoords="offset points")
ax.spines[["top", "right"]].set_visible(False); ax.legend(fontsize=8, frameon=False)
fig.tight_layout(); fig.savefig(out + "/fig4_benchmark.png")
