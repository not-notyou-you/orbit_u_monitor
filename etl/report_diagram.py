# etl/report_diagram.py
"""Laporan PDF "Analisa daerah" halaman Diagram (M56, INTERFACE.md §4.5).

Kecamatan dan rentang tanggal mengikuti pilihan pengguna, tetapi isinya
SEMUA band per kecamatan (hujan 24 jam/72 jam/7 hari/30 hari, genangan MODIS,
NDVI, NDWI) — tidak hanya band yang sedang tampil di layar. Satu grafik per
band dengan satu garis per kecamatan (warna sama dengan di layar bila
dikirim), garis ambang dari ``etl.band_catalog``, lalu tabel ringkas.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from etl import report_generator as rg
from etl.report_periodic import DASH, Doc, build_pdf, num

# Warna cadangan bila UI tidak mengirim warna kecamatan (tab10, terbaca di kertas).
_FALLBACK = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b",
             "#e377c2", "#7f7f7f", "#bcbd22", "#17becf", "#393b79", "#637939"]


def _printable(hex_color: str) -> str:
    """Warna layar CRT (terang) digelapkan supaya terbaca di kertas putih."""
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
    if lum <= 0.55:
        return hex_color
    k = 0.55 / lum
    return "#{:02x}{:02x}{:02x}".format(int(r * k), int(g * k), int(b * k))


def build(out: Path, *, regions: list[dict], colours: dict[int, str | None], bands: list[dict],
          data: dict, date_from: date, date_to: date, generated_at: datetime, workdir: Path) -> None:
    doc = Doc(title="Analisa Daerah",
              subtitle=", ".join(r["region_name"] for r in regions),
              period=(date_from, date_to), workdir=workdir)
    colour = {r["region_id"]: _printable(colours.get(r["region_id"]) or _FALLBACK[i % len(_FALLBACK)])
              for i, r in enumerate(regions)}

    doc.h1("Ringkasan")
    doc.p(f"{len(regions)} kecamatan, {date_from:%d-%m-%Y} s.d. {date_to:%d-%m-%Y}. Laporan ini memuat semua band "
          "yang dihitung per kecamatan oleh Job Hidromet (GPM dan MODIS). Sentinel-1 tidak dihitung per kecamatan "
          "sehingga tidak termasuk di sini; lihat Laporan Citra.")
    rows = []
    for b in bands:
        for r in regions:
            vals = [p["y"] for p in data[b["band_code"]][r["region_id"]] if p["y"] is not None]
            thr = b["thresholds"]
            above = sum(1 for v in vals if thr and v >= thr[0]["value"]) if thr else None
            rows.append([b["band_name"], r["region_name"], len(vals),
                         num(min(vals), 2) if vals else DASH, num(sum(vals) / len(vals), 2) if vals else DASH,
                         num(max(vals), 2) if vals else DASH,
                         DASH if above is None else f"{above} (≥ {num(thr[0]['value'], 2)})"])
    doc.table(["Band", "Kecamatan", "Hari", "Min", "Rerata", "Maks", "Hari ≥ ambang"], rows,
              widths=[95, 95, 35, 50, 55, 50, rg._TEXT_W - 380])

    for b in bands:
        doc.h1(b["band_name"])
        doc.p(b["about"])
        series = data[b["band_code"]]
        if not any(any(p["y"] is not None for p in pts) for pts in series.values()):
            doc.note("Tidak ada data band ini untuk kecamatan dan rentang tanggal yang dipilih.")
            continue
        fig, ax = rg._fig()
        for r in regions:
            pts = [p for p in series[r["region_id"]] if p["y"] is not None]
            if not pts:
                continue
            ax.plot([date.fromisoformat(p["x"]) for p in pts], [p["y"] for p in pts],
                    color=colour[r["region_id"]], linewidth=1.1, marker="o" if len(pts) <= 40 else None,
                    markersize=2.5, label=r["region_name"])
        for t in b["thresholds"]:
            ax.axhline(t["value"], linestyle="--", linewidth=0.8, color="#C44E52")
            ax.text(date_from, t["value"], f" ambang {t['label']} {num(t['value'], 2)}", fontsize=6,
                    va="bottom", color="#555555")
        ax.set_ylabel(b["unit"] or "", fontsize=8)
        ax.legend(fontsize=7, frameon=False, ncol=min(4, len(regions)))
        fig.autofmt_xdate()
        doc.chart(fig, f"{b['band_name']} per kecamatan; garis putus = ambang.")

    doc.h1("Catatan")
    doc.bullets(["Nilai harian = hari UTC (07.00–07.00 WIB).",
                 "Kosong berarti data belum ada (mis. MODIS tertutup awan), bukan nol.",
                 "Ini bukan peringatan dini resmi. Untuk keputusan evakuasi, ikuti BMKG dan BPBD."])
    build_pdf(doc, out, generated_at)
