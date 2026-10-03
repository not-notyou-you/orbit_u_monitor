# etl/report_periodic.py
"""Kerangka laporan periodik (PIPELINE.md §6): periode, penyimpanan, registrasi, PDF.

Dua template (``etl/report_hydromet.py``, ``etl/report_datahealth.py``)
dibangun di atas gaya/font/tabel ``etl/report_generator.py`` warisan (reportlab,
A4, DejaVu). Modul ini mengurus hal yang sama untuk keduanya:

* periode WIB: minggu lalu (Senin–Minggu) atau bulan lalu; data hidromet
  per tanggal UTC dipetakan ke periode lewat ``obs_date`` (§6.1);
* berkas ``data/reports/{report_code}/{YYYY}/{report_code}_{period_start}.pdf``
  ditulis lewat ``atomic_path()``; regenerasi menulis berkas baru
  (``…_v2.pdf``, ``…_v3.pdf``) supaya berkas lama dipertahankan (§6.4);
* ``generated_reports``: baris READY lama -> SUPERSEDED dalam transaksi yang
  sama dengan INSERT baris baru; kegagalan -> baris FAILED + pesan (§8);
* tidak ada angka karangan: nilai kosong ditulis "—" (DataLab D27).
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer
from sqlalchemy import text

from etl import report_generator as rg
from etl.atomic_write import atomic_path

logger = logging.getLogger(__name__)

WIB = ZoneInfo("Asia/Jakarta")
DASH = "—"
SOFTWARE = "Orbit-U: The Monitor 1.0.0"
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()

REPORT_CODES = ("HYDROMET_WEEKLY", "HYDROMET_MONTHLY", "DATAHEALTH_WEEKLY", "DATAHEALTH_MONTHLY")


def reports_root() -> Path:
    """data/reports (``REPORTS_DIR`` menimpanya, mis. di tes)."""
    env = os.getenv("REPORTS_DIR")
    return Path(env) if env else Path(__file__).resolve().parent.parent / "data" / "reports"


# --- periode -----------------------------------------------------------------------

def is_monthly(code: str) -> bool:
    return code.endswith("_MONTHLY")


def period_for(code: str, period_start: date) -> tuple[date, date]:
    """(start, end) inklusif. Mingguan harus Senin; bulanan tanggal 1."""
    if is_monthly(code):
        if period_start.day != 1:
            raise ValueError("monthly period_start must be the 1st of a month")
        nxt = date(period_start.year + (period_start.month == 12), period_start.month % 12 + 1, 1)
        return period_start, nxt - timedelta(days=1)
    if period_start.weekday() != 0:
        raise ValueError("weekly period_start must be a Monday")
    return period_start, period_start + timedelta(days=6)


def previous_period(code: str, now: datetime | None = None) -> date:
    """period_start minggu/bulan lalu menurut kalender WIB."""
    today = (now or datetime.now(timezone.utc)).astimezone(WIB).date()
    if is_monthly(code):
        first = date(today.year, today.month, 1)
        prev_last = first - timedelta(days=1)
        return date(prev_last.year, prev_last.month, 1)
    this_monday = today - timedelta(days=today.weekday())
    return this_monday - timedelta(days=7)


# --- format nilai ------------------------------------------------------------------

def num(v, nd: int = 1, unit: str = "") -> str:
    """Angka gaya Indonesia, atau "—" bila kosong. Tidak pernah mengarang."""
    if v is None:
        return DASH
    try:
        f = float(v)
    except (TypeError, ValueError):
        return DASH
    s = f"{f:,.{nd}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{s}{(' ' + unit) if unit else ''}"


def txt(v) -> str:
    return DASH if v is None or v == "" else str(v)


def pct(part, whole, nd: int = 1) -> str:
    if part is None or not whole:
        return DASH
    return num(100.0 * float(part) / float(whole), nd, "%")


# --- dokumen -----------------------------------------------------------------------

@dataclass
class Doc:
    """Pengumpul flowable untuk satu laporan."""
    title: str
    subtitle: str
    period: tuple[date, date]
    S: rg._Styles = field(default_factory=lambda: (rg._register_fonts(), rg._styles())[1])
    story: list = field(default_factory=list)
    charts: list[Path] = field(default_factory=list)
    sections: list[str] = field(default_factory=list)
    workdir: Path | None = None

    def h1(self, title: str) -> None:
        self.sections.append(title)
        self.story.append(Paragraph(rg._e(title), self.S.section))

    def h2(self, title: str) -> None:
        self.story.append(Paragraph(rg._e(title), self.S.sub))

    def p(self, body: str) -> None:
        self.story.append(Paragraph(rg._e(body), self.S.body))

    def note(self, body: str) -> None:
        self.story.append(Paragraph(rg._e(body), self.S.note))

    def bullets(self, items: list[str]) -> None:
        for it in items:
            self.story.append(Paragraph("• " + rg._e(it), self.S.bullet))

    def table(self, header: list[str], rows: list[list], widths: list[float] | None = None,
              empty: str = "Tidak ada data pada periode ini.") -> None:
        """Tabel; tanpa baris -> satu baris "—" + catatan (bukan contoh)."""
        if not rows:
            rows = [[DASH] * len(header)]
            self.story.append(rg._table([header] + rows, widths or [rg._TEXT_W / len(header)] * len(header), self.S))
            self.note(empty)
            return
        cells = [[Paragraph(rg._e(str(c)), self.S.cell) for c in r] for r in rows]
        self.story.append(rg._table([header] + cells, widths or [rg._TEXT_W / len(header)] * len(header), self.S))

    def kv(self, pairs: list[tuple[str, str]]) -> None:
        self.story.append(rg._kv_table(pairs, self.S))

    def chart(self, fig, caption: str) -> None:
        import matplotlib.pyplot as plt
        assert self.workdir is not None
        path = self.workdir / f"chart_{len(self.charts) + 1}.png"
        fig.tight_layout()
        fig.savefig(path, dpi=150)
        plt.close(fig)
        self.charts.append(path)
        w = rg._TEXT_W
        self.story.append(Image(str(path), width=w, height=w * 3.1 / 6.8))
        self.story.append(Paragraph(rg._e(caption), self.S.caption))

    def spacer(self, h: float = 6) -> None:
        self.story.append(Spacer(1, h))


def _decorator(title: str, generated_at: datetime):
    def _draw(canvas, doc):
        canvas.saveState()
        canvas.setFont(rg._FONTS["body"], 8)
        canvas.setFillColor(colors.grey)
        canvas.drawString(0.75 * inch, A4[1] - 0.55 * inch, f"Orbit-U: The Monitor — {title}")
        canvas.drawRightString(A4[0] - 0.75 * inch, A4[1] - 0.55 * inch,
                               f"Dibuat {generated_at.astimezone(WIB):%Y-%m-%d %H:%M} WIB")
        canvas.setStrokeColor(colors.HexColor("#DDDDDD"))
        canvas.line(0.75 * inch, A4[1] - 0.62 * inch, A4[0] - 0.75 * inch, A4[1] - 0.62 * inch)
        canvas.drawCentredString(A4[0] / 2, 0.5 * inch, f"Halaman {doc.page}")
        canvas.restoreState()
    return _draw


def build_pdf(doc: Doc, out_path: Path, generated_at: datetime) -> None:
    """Sampul singkat + isi, ditulis atomik."""
    S = doc.S
    head = [Paragraph(rg._e(doc.title), S.title), Spacer(1, 6),
            Paragraph(rg._e(doc.subtitle), S.cover_subtitle), Spacer(1, 4),
            Paragraph(rg._e(f"Periode: {doc.period[0]:%d-%m-%Y} s.d. {doc.period[1]:%d-%m-%Y} "
                            "(tanggal data hidromet = hari UTC)"), S.body),
            Paragraph(rg._e(f"Dibuat: {generated_at.astimezone(WIB):%Y-%m-%d %H:%M} WIB oleh {SOFTWARE}"), S.note),
            Spacer(1, 12)]
    with atomic_path(out_path) as tmp:
        pdf = SimpleDocTemplate(str(tmp), pagesize=A4, title=doc.title, author=SOFTWARE,
                                leftMargin=0.75 * inch, rightMargin=0.75 * inch,
                                topMargin=0.85 * inch, bottomMargin=0.8 * inch)
        deco = _decorator(doc.title, generated_at)
        pdf.build(head + doc.story, onFirstPage=deco, onLaterPages=deco)


# --- registrasi --------------------------------------------------------------------

def _report_type(sess, code: str) -> int:
    tid = sess.scalar(text("SELECT report_type_id FROM report_types WHERE report_code = :c"), {"c": code})
    if tid is None:
        raise ValueError(f"unknown report_code {code!r}")
    return tid


def target_path(code: str, period_start: date) -> Path:
    """Path berkas baru; versi berikutnya bila berkas lama sudah ada (regenerasi)."""
    base = reports_root() / code / f"{period_start:%Y}"
    p = base / f"{code}_{period_start.isoformat()}.pdf"
    n = 2
    while p.exists():
        p = base / f"{code}_{period_start.isoformat()}_v{n}.pdf"
        n += 1
    return p


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class ReportResult:
    report_id: int
    status: str
    path: Path | None
    error: str | None = None


def builder_for(code: str) -> Callable:
    if code.startswith("HYDROMET"):
        from etl.report_hydromet import build
    elif code.startswith("DATAHEALTH"):
        from etl.report_datahealth import build
    else:
        raise ValueError(f"unknown report_code {code!r}")
    return build


def generate_report(db, code: str, period_start: date, *, generated_by: int | None = None,
                    notes: list[str] | None = None) -> ReportResult:
    """Buat satu laporan dan catat di generated_reports. Tidak melempar untuk
    kegagalan pembuatan: hasilnya baris FAILED (panel Admin: "Buat ulang")."""
    import tempfile

    if code not in REPORT_CODES:
        raise ValueError(f"unknown report_code {code!r}")
    start, end = period_for(code, period_start)
    out = target_path(code, start)
    generated_at = datetime.now(timezone.utc)
    try:
        with tempfile.TemporaryDirectory(prefix="orbit_u_report_") as wd:
            with db.session() as sess:
                doc = builder_for(code)(sess, code, start, end, Path(wd), notes or [])
            build_pdf(doc, out, generated_at)
        size, digest = out.stat().st_size, _sha256(out)
        with db.session() as sess:
            tid = _report_type(sess, code)
            sess.execute(text("""UPDATE generated_reports SET status = 'SUPERSEDED'
                                 WHERE report_type_id = :t AND period_start = :s AND status = 'READY'"""),
                         {"t": tid, "s": start})
            rid = sess.scalar(text("""
                INSERT INTO generated_reports (report_type_id, period_start, period_end, file_path, file_size_bytes,
                                               checksum_sha256, status, generated_by)
                VALUES (:t, :s, :e, :p, :n, :h, 'READY', :by) RETURNING report_id"""),
                {"t": tid, "s": start, "e": end, "p": str(out), "n": size, "h": digest, "by": generated_by})
        logger.info("[REPORT] %s %s READY -> %s", code, start, out)
        return ReportResult(rid, "READY", out)
    except Exception as exc:
        logger.exception("[REPORT] %s %s gagal", code, start)
        out.unlink(missing_ok=True)
        # Berkas tidak ada: ukuran 0 dan checksum SHA-256 berkas kosong
        # (kolom NOT NULL), path = path yang dituju.
        with db.session() as sess:
            rid = sess.scalar(text("""
                INSERT INTO generated_reports (report_type_id, period_start, period_end, file_path, file_size_bytes,
                                               checksum_sha256, status, error_message, generated_by)
                VALUES (:t, :s, :e, :p, 0, :h, 'FAILED', :err, :by) RETURNING report_id"""),
                {"t": _report_type(sess, code), "s": start, "e": end, "p": str(out), "h": EMPTY_SHA256,
                 "err": f"{type(exc).__name__}: {exc}"[:2000], "by": generated_by})
        return ReportResult(rid, "FAILED", None, str(exc))
