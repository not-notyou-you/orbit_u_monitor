import csv, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
rows = [r for r in csv.DictReader(open(sys.argv[1], encoding="utf-8")) if r["status"] == "dijalankan"]
qs = ["Q1", "Q2", "Q3", "Q4", "Q5"]
pg = [float(next(r["median_ms"] for r in rows if r["engine"] == "PostgreSQL" and r["query"] == q)) for q in qs]
my = [float(next(r["median_ms"] for r in rows if r["engine"].startswith("MySQL") and r["query"] == q)) for q in qs]
fig, ax = plt.subplots(figsize=(6.4, 3.0), dpi=220)
x = range(len(qs)); w = 0.38
b1 = ax.bar([i - w / 2 for i in x], pg, w, label="PostgreSQL 18.6 + PostGIS", color="#0b4f55")
b2 = ax.bar([i + w / 2 for i in x], my, w, label="MySQL 8.0.40", color="#7fd1d8", edgecolor="#0b4f55", linewidth=0.8)
ax.set_yscale("log"); ax.set_ylabel("median (ms), skala log", fontsize=8)
ax.set_xticks(list(x)); ax.set_xticklabels(qs, fontsize=9); ax.tick_params(axis="y", labelsize=8)
for bars in (b1, b2):
    for b in bars:
        ax.annotate(f"{__import__('decimal').Decimal(str(b.get_height())).quantize(__import__('decimal').Decimal('0.01'), rounding='ROUND_HALF_UP')}".replace(".", ","), (b.get_x() + b.get_width() / 2, b.get_height()),
                    ha="center", va="bottom", fontsize=7, xytext=(0, 2), textcoords="offset points")
ax.spines[["top", "right"]].set_visible(False); ax.legend(fontsize=8, frameon=False)
fig.tight_layout(); fig.savefig(sys.argv[2])
