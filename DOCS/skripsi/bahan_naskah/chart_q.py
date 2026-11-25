"""Gambar Perbandingan Median Waktu Kueri Inti.

Pemakaian: python chart_q.py benchmark/results/timing.csv chart_q.png
Warna mengikuti gaya gambar BAB IV: batang gelap PostgreSQL, batang terang bergaris MySQL.
"""
import csv, sys
from decimal import Decimal, ROUND_HALF_UP
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator

DARK, LIGHT = "#004e53", "#e5feff"
rows = [r for r in csv.DictReader(open(sys.argv[1], encoding="utf-8")) if r["status"] == "dijalankan"]
qs = ["Q1", "Q2", "Q3", "Q4", "Q5"]
names = ["Pivot hujan", "Tren 30 hari", "Irisan spasial", "Evaluasi\nperingatan", "Lineage\nrekursif"]
pg = [float(next(r["median_ms"] for r in rows if r["engine"] == "PostgreSQL" and r["query"] == q)) for q in qs]
my = [float(next(r["median_ms"] for r in rows if r["engine"].startswith("MySQL") and r["query"] == q)) for q in qs]


def koma(v):
    return str(Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)).replace(".", ",")


plt.rcParams.update({"font.family": "DejaVu Sans", "text.color": DARK, "axes.labelcolor": DARK,
                     "xtick.color": DARK, "ytick.color": DARK, "axes.edgecolor": DARK})
fig, ax = plt.subplots(figsize=(9.0, 4.2), dpi=300)
x = range(len(qs)); w = 0.36
b1 = ax.bar([i - w / 2 for i in x], pg, w, label="PostgreSQL 18.6 + PostGIS 3.6.2", color=DARK, edgecolor=DARK, linewidth=1.4)
b2 = ax.bar([i + w / 2 for i in x], my, w, label="MySQL 8.0.40", color=LIGHT, edgecolor=DARK, linewidth=1.4)
ax.set_yscale("log"); ax.set_ylim(0.15, 60)
ticks = [0.2, 0.5, 1, 2, 5, 10, 20, 50]
ax.yaxis.set_major_locator(FixedLocator(ticks)); ax.yaxis.set_minor_locator(NullLocator())
ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}".replace(".", ",")))
ax.set_ylabel("Median waktu (ms, skala log)", fontsize=10)
ax.set_xticks(list(x)); ax.set_xticklabels([f"{q}\n{n}" for q, n in zip(qs, names)], fontsize=10)
ax.tick_params(axis="y", labelsize=10)
for bars in (b1, b2):
    for b in bars:
        ax.annotate(koma(b.get_height()), (b.get_x() + b.get_width() / 2, b.get_height()), ha="center", va="bottom",
                    fontsize=9, fontweight="bold", xytext=(0, 3), textcoords="offset points")
ax.spines[["top", "right"]].set_visible(False)
ax.legend(fontsize=10, frameon=False, loc="upper left")
fig.tight_layout(); fig.savefig(sys.argv[2])
