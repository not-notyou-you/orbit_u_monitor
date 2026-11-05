import json, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon

regs = json.load(open(sys.argv[1], encoding="utf-8"))

def rings(g):
    polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
    for p in polys:
        yield p[0]

fig, ax = plt.subplots(figsize=(7.2, 5.6), dpi=200)
aoi_area = 0
for r in regs:
    if r["lvl"] != 3:
        continue
    aoi = r["aoi"]
    for ring in rings(r["g"]):
        ax.add_patch(Polygon(ring, closed=True, facecolor="#8fd3c7" if aoi else "#eeeeee",
                             edgecolor="#1f2a5a" if aoi else "#aaaaaa", linewidth=0.8 if aoi else 0.4))
    if aoi:
        aoi_area += float(r["area"])
        xs = [c[0] for ring in rings(r["g"]) for c in ring]; ys = [c[1] for ring in rings(r["g"]) for c in ring]
        ax.text(sum(xs) / len(xs), sum(ys) / len(ys), r["name"], ha="center", va="center", fontsize=6.5,
                fontfamily="DejaVu Sans", color="#10183a")
pts = [c for r in regs if r["lvl"] == 3 and r["aoi"] for ring in rings(r["g"]) for c in ring]
x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts); y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
ax.set_xlim(x0 - 0.03, x1 + 0.03); ax.set_ylim(y0 - 0.03, y1 + 0.08)
ax.set_aspect("equal")
ax.set_xlabel("Bujur (°BT)", fontsize=8); ax.set_ylabel("Lintang (°)", fontsize=8)
ax.tick_params(labelsize=7)
from matplotlib.patches import Patch
ax.legend(handles=[Patch(facecolor="#8fd3c7", edgecolor="#1f2a5a", label="Kecamatan wilayah kajian (10)"),
                   Patch(facecolor="#eeeeee", edgecolor="#aaaaaa", label="Kecamatan lain di Kabupaten Lebak")],
          loc="upper right", fontsize=7, frameon=True)
ax.text(0.01, 0.01, "Sumber batas: COD-AB Indonesia tingkat kecamatan", transform=ax.transAxes, fontsize=6, color="#555")
fig.tight_layout()
fig.savefig(sys.argv[2])
print("luas AOI km2:", round(aoi_area, 1))
