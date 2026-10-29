import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

INK, PANEL, BOX = "#0b4f55", "#e3fbfb", "#ffffff"
fig, ax = plt.subplots(figsize=(10, 5.2), dpi=220)
ax.set_xlim(0, 200); ax.set_ylim(0, 104); ax.axis("off")


def rbox(x, y, w, h, fill, lw=2.0, r=2.2):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}",
                                linewidth=lw, edgecolor=INK, facecolor=fill))


def box(cx, cy, w, h, text, size=8.2):
    rbox(cx - w / 2, cy - h / 2, w, h, BOX)
    ax.text(cx, cy, text, ha="center", va="center", fontsize=size, color=INK, fontweight="bold", linespacing=1.15)


def panel(x, y, w, h, title):
    rbox(x, y, w, h, PANEL, lw=2.4, r=3)
    ax.text(x + w / 2, y + h - 5, title, ha="center", va="center", fontsize=9.5, color=INK, fontweight="bold")


def path(*pts):
    xs, ys = zip(*pts)
    ax.plot(xs[:-1] + (xs[-1],), ys, color=INK, lw=2.0, solid_joinstyle="round", solid_capstyle="round")
    arrow(pts[-2], pts[-1])


def arrow(p0, p1, conn="arc3"):
    ax.annotate("", xy=p1, xytext=p0, arrowprops=dict(arrowstyle="-|>,head_length=0.55,head_width=0.32",
                                                      color=INK, lw=2.0, connectionstyle=conn, shrinkA=0, shrinkB=0))


BW, BH = 36, 9.5
# Panel 1: pra-pengembangan
panel(2, 4, 44, 96, "Identifikasi Masalah")
p1 = [(80, "Analisis sistem berjalan\n(wawancara, dokumen)"), (61, "Identifikasi masalah\n(5W1H)"),
      (42, "Studi pustaka dan\nresearch gap"), (23, "Rumusan masalah\nRM1–RM4")]
for y, t in p1:
    box(24, y, BW, BH + 2, t)
for (y0, _), (y1, _) in zip(p1, p1[1:]):
    arrow((24, y0 - (BH + 2) / 2), (24, y1 + (BH + 2) / 2))

# Panel 2: DBSDLC dua kolom
panel(52, 4, 100, 96, "DBSDLC")
c1 = ["1. Database Planning", "2. System Definition", "3. Requirement\nCollection & Analysis",
      "4. Database Design\n(konseptual, logikal, fisik)", "5. DBMS Selection", "6. Pemodelan Sistem"]
c2 = ["7. Desain Antarmuka", "8. Prototyping", "9. Implementation", "10. Data Conversion\nand Loading",
      "11. Testing\n(enam evaluasi)"]
ys1 = [84 - i * 14.6 for i in range(6)]
ys2 = [84 - i * 17.2 for i in range(5)]
X1, X2, H, CW = 74, 118, 10.5, 36
for y, t in zip(ys1, c1):
    box(X1, y, CW, H, t, size=7.6)
for y, t in zip(ys2, c2):
    box(X2, y, CW, H, t, size=7.6)
for a, b in zip(ys1, ys1[1:]):
    arrow((X1, a - H / 2), (X1, b + H / 2))
for a, b in zip(ys2, ys2[1:]):
    arrow((X2, a - H / 2), (X2, b + H / 2))
mx = (X1 + X2) / 2
path((X1 + CW / 2, ys1[-1]), (mx, ys1[-1]), (mx, ys2[0]), (X2 - CW / 2, ys2[0]))  # 6 -> 7
# umpan balik
path((X2 + CW / 2, ys2[1]), (X2 + CW / 2 + 4, ys2[1]), (X2 + CW / 2 + 4, ys2[0]), (X2 + CW / 2, ys2[0]))
ax.text(X2 + CW / 2 + 5.5, (ys2[0] + ys2[1]) / 2, "umpan\nbalik", fontsize=7, color=INK, va="center", ha="left")
path((X2 + CW / 2, ys2[4] + 2), (X2 + CW / 2 + 4, ys2[4] + 2), (X2 + CW / 2 + 4, ys2[2]), (X2 + CW / 2, ys2[2]))
ax.text(X2 + CW / 2 + 5.5, (ys2[4] + ys2[2]) / 2, "belum\nlulus", fontsize=7, color=INK, va="center", ha="left")

# RM -> DBSDLC
path((24 + BW / 2, 23), (49, 23), (49, ys1[0]), (X1 - CW / 2, ys1[0]))

# Panel 3: hasil
panel(158, 4, 40, 96, "Hasil")
p3 = [(61, "Pembahasan hasil\nterhadap RM1–RM4"), (42, "Simpulan\ndan saran")]
for y, t in p3:
    box(178, y, 32, BH + 2, t)
arrow((178, 61 - (BH + 2) / 2), (178, 42 + (BH + 2) / 2))
path((X2, ys2[4] - H / 2), (X2, 6.5), (155, 6.5), (155, 61), (178 - 16, 61))

fig.tight_layout(pad=0.1)
fig.savefig(sys.argv[1])
