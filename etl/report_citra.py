# etl/report_citra.py
"""Laporan PDF halaman Citra Satelit (M56, INTERFACE.md §4.3).

Pengguna memilih halaman mana yang dicetak — Ringkasan, Sentinel-1, MODIS,
GPM — satu, beberapa, atau semuanya, dan semuanya masuk ke SATU berkas PDF.
Isi per satelit sama dengan halamannya di web: penjelasan satelit, gambar
PNG, kalimat kondisi, tabel angka, dan (bila dipilih) perbandingan dua
tanggal berdampingan.

Data sudah disaring route (VIEW ``v_citra_*`` di bawah role pemanggil), jadi
modul ini tidak membuka koneksi sendiri dan tidak pernah memuat scene di luar
batas waktu role itu.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable

from reportlab.platypus import Image, KeepTogether, Table, TableStyle

from etl import report_generator as rg
from etl.report_periodic import DASH, Doc, build_pdf, num

_IMG_W = rg._TEXT_W / 2 - 6


_MAX_PX = 900          # setengah lebar A4 pada ±200 dpi
_tmpdir: list[Path] = []


def _image(path: Path | None, width: float):
    """PNG pratinjau sebagai JPEG kecil di folder sementara: PNG lossless
    citra radar 3 satelit x 2 tanggal membuat PDF >15 MB."""
    if path is None or not path.is_file():
        return None
    from PIL import Image as PILImage
    with PILImage.open(path) as im:
        w, h = im.size
        if _tmpdir:
            k = min(1.0, _MAX_PX / max(w, 1))
            rgb = im.convert("RGBA")
            flat = PILImage.new("RGB", rgb.size, (255, 255, 255))
            flat.paste(rgb, mask=rgb.split()[3])
            if k < 1.0:
                flat = flat.resize((round(w * k), max(1, round(h * k))))
            out = _tmpdir[0] / f"img_{len(list(_tmpdir[0].glob('img_*')))}.jpg"
            flat.save(out, "JPEG", quality=85, optimize=True)
            path = out
    return Image(str(path), width=width, height=width * h / max(w, 1))


def _window_text(window: dict) -> str:
    if window.get("days") is None:
        return "Seluruh arsip yang tersedia (peran " + window.get("role_code", "") + ")."
    return f"{window['days']} hari terakhir (batas peran {window.get('role_code', '')}); scene terbaru selalu disertakan."


def _metric_rows(metrics: list[dict]) -> list[list]:
    return [[m["band_name"], m["metric_label"], num(m["value"], _nd(m["value"]), m.get("metric_unit") or ""),
             m["source_date"].isoformat() if m.get("source_date") else DASH] for m in metrics]


def _nd(v) -> int:
    """Angka bulat (jumlah frame, piksel valid) tanpa desimal."""
    return 0 if v is not None and float(v).is_integer() else 2


def _sentences(doc: Doc, interp: dict) -> None:
    lines = [v.get("text") for v in interp.values() if isinstance(v, dict) and v.get("text")]
    if lines:
        doc.bullets(lines)
    else:
        doc.note("Tidak ada kalimat kondisi untuk satelit ini pada tanggal tersebut.")


def build(out: Path, *, area: dict, window: dict, summary: dict | None, sections: list[dict],
          png: Callable[[dict, str], Path | None], generated_at: datetime, workdir: Path) -> None:
    _tmpdir[:] = [workdir]
    dates = [s["main"]["date"] for s in sections] or [str(area.get("latest_date") or "")]
    doc = Doc(title="Laporan Citra Satelit",
              subtitle=f"{area['area_name']} — Sentinel-1, MODIS, GPM",
              period=(area.get("latest_date"), area.get("latest_date")), workdir=workdir)

    if summary is not None:
        doc.h1("Ringkasan")
        doc.p("Rekap scene yang tersedia per satelit untuk area ini. " + _window_text(window))
        st = summary.get("area_status") or {}
        if st.get("label"):
            doc.p(f"Status area terakhir: {st['label']}. {st.get('text') or ''}")
        doc.table(["Satelit", "Tanggal tersedia", "Bergambar", "Scene bergambar terakhir", "Resolusi"],
                  [[s["label"], s["n_dates"], s["n_dates_with_images"],
                    s["latest_date"].isoformat() if s["latest_date"] else DASH, s["resolution"]]
                   for s in summary["sources"]],
                  widths=[90, 80, 70, 120, rg._TEXT_W - 360])

    for sec in sections:
        src, main, cmp = sec["source"], sec["main"], sec["compare"]
        doc.h1(src["label"])
        doc.p(src["about"])
        doc.kv([("Lintasan", src["revisit"]), ("Resolusi", src["resolution"]),
                ("Informasi yang bisa diambil", " ".join(src["extractable"])), ("Keterbatasan", src["limits"])])

        doc.h2(f"Tanggal {main['date']}")
        if not main.get("has_scene", True):
            doc.note("Tidak ada scene Sentinel-1/Live pada tanggal ini, jadi tidak ada gambar. "
                     "Angka di bawah berasal dari Job Hidromet harian (termasuk backfill).")
        elif not main["files_available"]:
            doc.note("Berkas gambar scene ini sudah dihapus retensi; hanya angkanya yang tersimpan.")
        imgs = [(p["label"] or k, _image(png(main, k), _IMG_W)) for k, p in main["previews"].items()]
        imgs = [(lbl, im) for lbl, im in imgs if im is not None]
        for i in range(0, len(imgs), 2):
            pair = imgs[i:i + 2]
            t = Table([[im for _, im in pair], [rg._e(lbl) for lbl, _ in pair]],
                      colWidths=[_IMG_W + 6] * len(pair))
            t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                   ("FONTSIZE", (0, 1), (-1, 1), 8)]))
            doc.story.append(KeepTogether([t]))
            doc.spacer(4)
        if not imgs:
            doc.note("Tidak ada gambar untuk satelit ini pada tanggal tersebut.")
        doc.h2("Kondisi")
        _sentences(doc, main["interpretations"])
        doc.h2("Angka")
        doc.table(["Band", "Metrik", "Nilai", "Tanggal data"], _metric_rows(main["metrics"]),
                  widths=[150, 150, 90, rg._TEXT_W - 390], empty="Tidak ada angka untuk satelit ini.")

        per = main.get("per_region")
        if per:
            bands = sorted({b for r in per for b in r["values"]})
            doc.h2("Angka per kecamatan")
            doc.table(["Kecamatan"] + bands, [[r["region_name"]] + [num(r["values"].get(b), 2) for b in bands] for r in per])

        if cmp is not None:
            doc.h2(f"Perbandingan {main['date']} dan {cmp['date']}")
            keys = sorted(set(main["previews"]) & set(cmp["previews"]))
            for k in keys:
                a, b = _image(png(main, k), _IMG_W), _image(png(cmp, k), _IMG_W)
                if a is None or b is None:
                    continue
                t = Table([[a, b], [f"{main['date']}", f"{cmp['date']}"]], colWidths=[_IMG_W + 6] * 2)
                t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("FONTSIZE", (0, 1), (-1, 1), 8)]))
                doc.story.append(KeepTogether([doc.para(main["previews"][k].get("label") or k), t]))
                doc.spacer(4)
            by = {(m["band_code"], m["metric_name"]): m for m in cmp["metrics"]}
            rows = []
            for m in main["metrics"]:
                o = by.get((m["band_code"], m["metric_name"]))
                if o is None:
                    continue
                delta = None if m["value"] is None or o["value"] is None else m["value"] - o["value"]
                rows.append([m["band_name"], m["metric_label"], num(o["value"], 2), num(m["value"], 2),
                             num(delta, 2) if delta is not None else DASH])
            doc.table(["Band", "Metrik", cmp["date"], main["date"], "Selisih"], rows,
                      widths=[130, 130, 70, 70, rg._TEXT_W - 400],
                      empty="Kedua tanggal tidak punya angka yang sama untuk dibandingkan.")

    doc.h1("Catatan")
    doc.bullets(["Ini bukan peringatan dini resmi. Untuk keputusan evakuasi, ikuti BMKG dan BPBD.",
                 "Tile kosong berarti data belum ada, bukan berarti kondisi aman.",
                 "Batas waktu: " + _window_text(window)])
    label = "Tanggal scene: " + ", ".join(sorted(set(d for d in dates if d)))
    build_pdf(doc, out, generated_at, period_label=label)
