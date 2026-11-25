"""Menyusun bagian LAMPIRAN pada naskah skripsi yang sudah dibangun.

Pemakaian:
    python lampiran.py <masukan.docx> <keluaran.docx> <folder ERD per modul>

Folder ERD dibangkitkan oleh erd_lampiran.py (erd_fisik_M1.png ... erd_fisik_M6.png).
Dijalankan SETELAH build_skripsi.py (dan langkah halaman awal); masukan harus naskah yang belum berlampiran.

Daftar lampiran mengikuti luaran wajib dan evaluasi minimum jalur Design and Implementation; isi yang sudah ada
di BAB I-V (struktur kuesioner, skenario uji, rekap hasil, matriks GRANT, hasil backup) tidak diulang.
  A Turnitin Similarity Report          (diisi mahasiswa)
  B Form Konsultasi Bimbingan           (formulir template)
  C Formulir Penggunaan Perangkat AI    (formulir template)
  D Notulen Wawancara dengan GMLS       lampiran/notulensiGMLS.txt bagian A-D
  E Jawaban Kuesioner Tinjauan Kebutuhan  lampiran/user_review_webapp/*.xlsx + Index.html
  F Jawaban Uji Coba Pengguna           lampiran/uat_webapp/*.xlsx
  G ERD Fisik Seluruh Modul             erd_lampiran.py
  H Kamus Data                          DOCS/generated/data_dictionary.md (tools/data_dictionary.py)
  I DDL Tabel Inti Modul M6             database/monitor_schema.sql
  J Kueri Uji Kinerja                   benchmark/engines.py, benchmark/extended.py
  K Rincian Hasil Pengujian Otomatis    DOCS/hasil_uji/pytest.xml
  L Tautan Formulir dan Video Demonstrasi  lampiran/link_penting.txt
Responden disebut dengan jabatan/kode, bukan nama.
"""
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from collections import OrderedDict
from xml.sax.saxutils import escape

import openpyxl
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
LAMP = os.path.join(ROOT, "DOCS", "skripsi", "lampiran")
SRC, OUT, ERD_DIR = sys.argv[1], sys.argv[2], sys.argv[3]

FONT = '<w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:cs="Times New Roman"/>'
MONO = '<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas" w:cs="Consolas"/>'
PAGEBREAK = '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'


# ------------------------------------------------------------------------------------------------ pembangun XML
def run(text, size=24, bold=False, italic=False, font=FONT, hl=False):
    rpr = font + ("<w:b/><w:bCs/>" if bold else "") + ("<w:i/><w:iCs/>" if italic else "")
    rpr += '<w:highlight w:val="yellow"/>' if hl else ""
    return (f'<w:r><w:rPr>{rpr}<w:sz w:val="{size}"/><w:szCs w:val="{size}"/></w:rPr>'
            f'<w:t xml:space="preserve">{escape(text)}</w:t></w:r>')


def para(text, indent=True, size=24, after=0, line=360, jc="both", **kw):
    ind = '<w:ind w:firstLine="567"/>' if indent else ""
    return (f'<w:p><w:pPr><w:spacing w:after="{after}" w:line="{line}" w:lineRule="auto"/>{ind}<w:jc w:val="{jc}"/></w:pPr>'
            + run(text, size=size, **kw) + "</w:p>")


def sub(text):
    """Judul bagian di dalam lampiran (tidak masuk daftar isi/tabel/gambar)."""
    return ('<w:p><w:pPr><w:keepNext/><w:spacing w:before="200" w:after="80" w:line="276" w:lineRule="auto"/></w:pPr>'
            + run(text, bold=True) + "</w:p>")


def bullets(texts, size=24):
    return "".join(
        '<w:p><w:pPr><w:spacing w:after="0" w:line="300" w:lineRule="auto"/><w:ind w:left="567" w:hanging="283"/>'
        f'<w:jc w:val="both"/></w:pPr>{run("–", size=size)}<w:r><w:tab/></w:r>{run(t, size=size)}</w:p>' for t in texts)


def item(mark, text, left):
    return ('<w:p><w:pPr><w:spacing w:after="0" w:line="300" w:lineRule="auto"/>'
            f'<w:ind w:left="{left}" w:hanging="284"/><w:jc w:val="both"/></w:pPr>'
            f'{run(mark)}<w:r><w:tab/></w:r>{run(text)}</w:p>')


def table(widths, header, rows, size=20, font=FONT):
    total = sum(widths)
    grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in widths)

    def cell(text, w, hdr):
        shade = '<w:shd w:val="clear" w:color="auto" w:fill="D9E2F3"/>' if hdr else ""
        ps = "".join(
            f'<w:p><w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/>'
            f'<w:jc w:val="{"center" if hdr else "left"}"/></w:pPr>{run(t, size=size, bold=hdr, font=FONT if hdr else font)}</w:p>'
            for t in str(text).split("\n"))
        return f'<w:tc><w:tcPr><w:tcW w:w="{w}" w:type="dxa"/>{shade}</w:tcPr>{ps}</w:tc>'

    def row(cells, hdr=False):
        trpr = '<w:trPr><w:tblHeader/><w:cantSplit/></w:trPr>' if hdr else '<w:trPr><w:cantSplit/></w:trPr>'
        return "<w:tr>" + trpr + "".join(cell(c, w, hdr) for c, w in zip(cells, widths)) + "</w:tr>"

    return (f'<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/><w:tblW w:w="{total}" w:type="dxa"/>'
            '<w:jc w:val="center"/><w:tblLayout w:type="fixed"/>'
            '<w:tblCellMar><w:left w:w="70" w:type="dxa"/><w:right w:w="70" w:type="dxa"/></w:tblCellMar>'
            '<w:tblLook w:val="04A0" w:firstRow="1" w:lastRow="0" w:firstColumn="1" w:lastColumn="0" w:noHBand="0" w:noVBand="1"/>'
            f'</w:tblPr><w:tblGrid>{grid}</w:tblGrid>' + row(header, True) + "".join(row(r) for r in rows)
            + '</w:tbl><w:p><w:pPr><w:spacing w:after="0"/></w:pPr></w:p>')


def code(text, size=15):
    out = []
    for line in text.strip("\n").splitlines():
        out.append('<w:p><w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/><w:ind w:left="0"/></w:pPr>'
                   + run(line if line else " ", size=size, font=MONO) + "</w:p>")
    return "".join(out) + '<w:p><w:pPr><w:spacing w:after="120"/></w:pPr></w:p>'


SEQ = {}


def caption(letter, title, bookmark=None):
    rp = f'<w:rPr>{FONT}<w:b/><w:bCs/><w:i w:val="0"/><w:color w:val="auto"/><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr>'
    bs, be = (f'<w:bookmarkStart w:id="{bookmark[0]}" w:name="{bookmark[1]}"/>', f'<w:bookmarkEnd w:id="{bookmark[0]}"/>') \
        if bookmark else ("", "")
    return (f'<w:p><w:pPr><w:pStyle w:val="Caption"/><w:keepNext/><w:spacing w:before="0" w:after="240"/><w:jc w:val="center"/>'
            f'{rp}</w:pPr>{bs}<w:r>{rp}<w:t xml:space="preserve">Lampiran </w:t></w:r>'
            f'<w:r>{rp}<w:fldChar w:fldCharType="begin"/></w:r>'
            f'<w:r>{rp}<w:instrText xml:space="preserve"> SEQ Lampiran \\* ALPHABETIC </w:instrText></w:r>'
            f'<w:r>{rp}<w:fldChar w:fldCharType="separate"/></w:r><w:r>{rp}<w:t>{letter}</w:t></w:r>'
            f'<w:r>{rp}<w:fldChar w:fldCharType="end"/></w:r>'
            f'<w:r>{rp}<w:t xml:space="preserve"> {escape(title)}</w:t></w:r>{be}</w:p>')


IMAGES = []


def figure(path, width_cm=14.0, max_h_cm=21.5):
    w, h = Image.open(path).size
    wcm = min(width_cm, max_h_cm * w / h)
    cx = int(wcm * 360000)
    cy = int(cx * h / w)
    idx = len(IMAGES) + 1
    rid, name = f"rIdLamp{idx}", f"lampiran_{idx}_{os.path.basename(path)}"
    IMAGES.append((rid, name, path))
    return ('<w:p><w:pPr><w:keepNext/><w:spacing w:before="0" w:after="120"/><w:jc w:val="center"/></w:pPr><w:r><w:drawing>'
            f'<wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{cx}" cy="{cy}"/>'
            f'<wp:docPr id="{9500 + idx}" name="Gambar Lampiran {idx}"/>'
            '<wp:cNvGraphicFramePr><a:graphicFrameLocks xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" noChangeAspect="1"/></wp:cNvGraphicFramePr>'
            '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
            '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            '<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            f'<pic:nvPicPr><pic:cNvPr id="{9500 + idx}" name="{name}"/><pic:cNvPicPr/></pic:nvPicPr>'
            f'<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
            f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic></a:graphicData></a:graphic>'
            '</wp:inline></w:drawing></w:r></w:p>')


# ------------------------------------------------------------------------------------------------ D Notulen
def lamp_d():
    t = open(os.path.join(LAMP, "notulensiGMLS.txt"), encoding="utf-8").read()
    body = t[t.index("A. PROFIL DAN KERJA SAMA"):t.index("E. CATATAN UNTUK PENGEMBANGAN")]
    x = [caption("D", "Notulen Wawancara dengan GMLS"),
         table([2600, 6000], ["Keterangan", "Isi"], [
             ["Tanggal dan tempat", "16 Oktober 2026, daring melalui Zoom Meeting"],
             ["Narasumber", "Anis Faisal Reza (Abah Lala), Ketua dan pendiri GMLS"],
             ["Pendamping", "Dosen yang pernah melaksanakan Humanity Project di Lebak Selatan"],
             ["Bentuk", "Diskusi terbuka satu sesi, tidak direkam"],
             ["Penyusunan notulen", "Gabungan catatan pewawancara dan catatan rekan peneliti, dikonfirmasi oleh pewawancara"]])]
    for sec in re.split(r"\n(?=[A-D]\. [A-Z])", body.strip()):
        lines = sec.splitlines()
        judul = lines[0].strip().title()
        for a, b in (("Gmls", "GMLS"), ("Dan ", "dan "), ("Untuk ", "untuk "), ("Yang ", "yang "),
                     ("Orbit-U: The Monitor", "Orbit-U: The Monitor")):
            judul = judul.replace(a, b)
        x.append(sub(judul))
        qa, cur = [], None
        for ln in lines[1:]:
            s = ln.strip()
            if not s or set(s) <= {"-"}:
                continue
            if s.startswith("P:"):
                cur = [s[2:].strip(), ""]
                qa.append(cur)
            elif s.startswith("J:"):
                cur[1] = s[2:].strip()
            elif cur is not None:
                if cur[1]:
                    sep = "\n" if re.match(r"^(\d+\.|-)\s", s) else " "
                    cur[1] += sep + s
                else:
                    cur[0] += " " + s
        for q, a in qa:
            a = re.sub(r"\s*\(lihat bagian C\)", "", a)
            x.append('<w:p><w:pPr><w:keepNext/><w:spacing w:before="120" w:after="0" w:line="300" w:lineRule="auto"/>'
                     f'<w:jc w:val="both"/></w:pPr>{run("Pertanyaan: ", bold=True)}{run(q, italic=True)}</w:p>')
            parts = a.split("\n")
            x.append(para("Jawaban: " + parts[0], indent=False, line=300))
            numbered = False
            for p in parts[1:]:
                if re.match(r"^\d+\.", p):
                    numbered = True
                    num, rest = p.split(" ", 1)
                    x.append(item(num, rest, 567))
                else:
                    x.append(item("–", re.sub(r"^-\s*", "", p), 851 if numbered else 567))
    return "".join(x)


# ------------------------------------------------------------------------------------------------ E Tinjauan
def lamp_e():
    html = open(os.path.join(LAMP, "user_review_webapp", "Index.html"), encoding="utf-8").read()
    fitur = re.findall(r'\["k(\d)", "\w+", "([^"]+)",\s*"([^"]+)"\]', html)
    assert len(fitur) == 6, fitur
    wb = openpyxl.load_workbook(os.path.join(LAMP, "user_review_webapp",
                                             "Jawaban Tinjauan Kebutuhan GMLS – Orbit-U.xlsx"), data_only=True)
    ws = wb.worksheets[0]
    hdr = [c.value for c in ws[1]]
    data = [dict(zip(hdr, [("" if v is None else str(v).strip()) for v in r])) for r in ws.iter_rows(min_row=2, values_only=True)]
    assert len(data) == 3
    jab = ["Ketua GMLS", "Relawan GMLS", "Relawan GMLS"]
    tgl = [d["Waktu"][:10] for d in data]
    assert set(tgl) == {"2026-10-27"}
    x = [caption("E", "Jawaban Kuesioner Tinjauan Kebutuhan"),
         para("Kuesioner diisi melalui formulir web pada 27 Oktober 2026 oleh tiga responden dari GMLS. Responden "
              "ditulis dengan kode dan jabatan; nama tidak dicantumkan. R1 adalah Ketua GMLS, sedangkan R2 dan R3 "
              "adalah Relawan GMLS. Struktur kuesioner ditunjukkan pada Tabel 3.3 dan rekapitulasinya pada Tabel 4.30."),
         sub("E.1 Butir Kebutuhan yang Ditinjau"),
         table([700, 2500, 5400], ["Kode", "Fitur", "Uraian pada Formulir"],
               [[f"K{k}", j, u.replace("“", "“").replace("”", "”")] for k, j, u in fitur]),
         sub("E.2 Jawaban Pilihan per Responden")]
    keys = [("K1 Kondisi di lokasi sendiri", "K1 Kondisi di lokasi sendiri"),
            ("K2 Peringatan hujan lebat + email", "K2 Peringatan hujan lebat dan surel"),
            ("K3 Bahasa peringatan dan tampilan awam", "K3 Bahasa peringatan dan tampilan awam"),
            ("K4 Pemantauan genangan dan perkiraan 15 hari", "K4 Pemantauan genangan dan perkiraan 15 hari"),
            ("K5 Arsip kejadian dari sumber resmi", "K5 Arsip kejadian dari sumber resmi"),
            ("K6 Akses sesuai peran", "K6 Akses sesuai peran"),
            ("Data yang dicatat", "Informasi yang dicatat"), ("Aturan pencatatan", "Aturan pencatatan"),
            ("Batasan sistem", "Batasan sistem"), ("10 kecamatan sesuai", "Sepuluh kecamatan wilayah kajian"),
            ("Persetujuan akhir", "Persetujuan akhir")]
    x.append(table([3500, 1700, 1700, 1700], ["Butir", "R1 Ketua", "R2 Relawan", "R3 Relawan"],
                   [[lbl] + [d[k] or "—" for d in data] for k, lbl in keys]))
    x.append(sub("E.3 Jawaban Isian"))
    anon = {"Saya saja dayah, bisa": "Saya saja, bisa"}
    rows = []
    for k, lbl in [("Catatan kebutuhan", "Catatan kebutuhan"), ("Catatan data", "Informasi yang perlu ditambah"),
                   ("Catatan aturan", "Catatan aturan"), ("Catatan batasan", "Catatan batasan"),
                   ("Peran Analis", "Calon peran Analis"), ("Peran Data Engineer", "Calon peran Data Engineer"),
                   ("Peran Administrator", "Calon peran Administrator"), ("Catatan wilayah", "Catatan wilayah"),
                   ("Saran", "Saran")]:
        for i, d in enumerate(data):
            v = d[k]
            if v and v != "-":
                rows.append([lbl, f"R{i + 1}", anon.get(v, v)])
    x.append(table([2400, 600, 5600], ["Isian", "Resp.", "Jawaban (sesuai aslinya)"], rows))
    return "".join(x)


# ------------------------------------------------------------------------------------------------ F Uji coba
def lamp_f():
    wb = openpyxl.load_workbook(os.path.join(LAMP, "uat_webapp", "Jawaban UAT – Orbit-U.xlsx"), data_only=True)
    ws = wb.worksheets[0]
    hdr = [c.value for c in ws[1]]
    data = [dict(zip(hdr, [("" if v is None else str(v).strip()) for v in r])) for r in ws.iter_rows(min_row=2, values_only=True)]
    assert len(data) == 13
    kode = {"Berhasil": "B", "Berhasil dengan kesulitan": "BK", "Tidak berhasil": "TB", "Tidak dicoba": "TD"}
    asal = {"Mahasiswa Humanity Project": "Humanity Project", "Masyarakat umum": "Masyarakat umum", "Lainnya": "Lainnya"}
    alat = {"Ponsel": "Ponsel", "Komputer/laptop": "Laptop", "Keduanya": "Keduanya"}
    rows = []
    for i, d in enumerate(data, 1):
        cells = [f"R{i}", d["Waktu"][:10], asal[d["Asal"]], alat[d["Perangkat"]]]
        for s in range(1, 7):
            h = d[f"S{s} Hasil"]
            m = d[f"S{s} Kemudahan (1-5)"] if h != "Tidak dicoba" else ""
            cells.append(kode[h] + (f" ({m})" if m else ""))
        cells.append({"Layak": "Layak", "Layak dengan perbaikan": "Dengan perbaikan"}[d["Layak dipakai"]])
        rows.append(cells)
    x = [caption("F", "Jawaban Uji Coba Pengguna"),
         para("Formulir uji coba diisi oleh 13 responden pada 27 Oktober hingga 5 November 2026. Nama responden tidak "
              "dicantumkan. Skenario S1–S6 ditunjukkan pada Tabel 3.7 dan rekapitulasinya pada Tabel 4.32. Kode hasil: "
              "B = berhasil, BK = berhasil dengan kesulitan, TB = tidak berhasil, TD = tidak dicoba; angka dalam kurung "
              "adalah nilai kemudahan 1 (sangat sulit) hingga 5 (sangat mudah)."),
         sub("F.1 Hasil per Responden"),
         table([560, 1000, 1150, 820, 680, 680, 680, 680, 680, 680, 990],
               ["Resp.", "Tanggal", "Asal", "Perangkat", "S1", "S2", "S3", "S4", "S5", "S6", "Penilaian"], rows, size=17),
         sub("F.2 Kendala dan Saran (sesuai aslinya)")]
    rows = []
    for i, d in enumerate(data, 1):
        for s in range(1, 7):
            v = d[f"S{s} Kendala"]
            if v and len(v) > 5:
                rows.append([f"R{i}", f"Kendala S{s}", v])
        if d["Saran"]:
            rows.append([f"R{i}", "Saran", d["Saran"]])
    x.append(table([700, 1400, 6500], ["Resp.", "Jenis", "Isi"], rows))
    return "".join(x)


# ------------------------------------------------------------------------------------------------ G ERD
MODUL = [("M1", "Pengguna, Laporan, dan Audit"), ("M2", "Rujukan Wilayah dan Sensor"),
         ("M3", "Akuisisi, Pemrosesan, dan Mutu"), ("M4", "Dataset dan Fusion"), ("M5", "Live Monitoring"),
         ("M6", "Observasi, Peringatan, dan Kejadian")]


def lamp_g():
    x = [caption("G", "ERD Fisik Seluruh Modul"),
         para("ERD fisik berikut menampilkan seluruh 43 tabel dalam enam modul (Gambar 4.16) beserta tipe data "
              "PostgreSQL, digambar dari skema basis data yang berjalan. Relasi di dalam modul digambar dengan notasi "
              "Crow's Foot; foreign key ke tabel modul lain ditandai FK pada kolomnya tanpa garis, dan kolom pencatat "
              "(created_by, updated_by, verified_by, dan sejenisnya) tidak digambar sebagai garis agar diagram terbaca.")]
    for k, (mid, nama) in enumerate(MODUL):
        if k:
            x.append(PAGEBREAK)
        x.append(sub(f"G.{k + 1} Modul {mid} {nama}"))
        x.append(figure(os.path.join(ERD_DIR, f"erd_fisik_{mid}.png"), 14.0, 15.0 if k == 0 else 21.0))
    return "".join(x)


# ------------------------------------------------------------------------------------------------ H Kamus data
def cells(line):
    parts = re.split(r"(?<!\\)\|", line.strip())[1:-1]
    return [p.strip().replace("\\|", "|").replace("`", "") for p in parts]


def lamp_h():
    md = open(os.path.join(ROOT, "DOCS", "generated", "data_dictionary.md"), encoding="utf-8").read()
    stamp = re.search(r"\(database `themonitor`, ([0-9-]+)", md).group(1)
    tables = re.split(r"\n## ", md[md.index("\n## administrative_regions"):md.index("\n## VIEW")])
    x = [caption("H", "Kamus Data"),
         para(f"Kamus data dibangkitkan oleh tools/data_dictionary.py dari katalog PostgreSQL basis data themonitor "
              f"({stamp}), yaitu dari COMMENT pada setiap tabel dan kolom, sehingga isinya sama dengan skema. Kolom Kunci: "
              "PK = primary key, FK→tabel = foreign key ke tabel tersebut, UNIQUE = bagian dari alternate key. Nilai bawaan "
              "ditulis di bawah tipe data, kecuali nilai urutan (sequence) primary key. Batasan CHECK dan UNIQUE gabungan "
              "dicantumkan di bawah setiap tabel; primary key dan foreign key sudah tampak pada kolom Kunci.")]
    n_tab = n_col = 0
    for k, blk in enumerate(t for t in tables if t.strip()):
        name = blk.split("\n", 1)[0].strip()
        desc = re.search(r"\n\n(.+?)\n\n\|", blk, re.S).group(1).strip().replace("`", "")
        rows = []
        for ln in blk.splitlines():
            if ln.startswith("| ") and not ln.startswith("| Kolom") and not ln.startswith("|---"):
                c = cells(ln)
                col, typ, nul, dflt, key, ket = c
                if dflt == "GENERATED":
                    typ += "\ngenerated"
                elif dflt and not dflt.startswith("nextval("):
                    typ += f"\ndefault {dflt}"
                rows.append([col, typ, "Ya" if nul == "NULL" else "Tidak", key.replace("FK→", "FK→"), ket])
        n_tab += 1
        n_col += len(rows)
        x.append(sub(f"H.{k + 1} {name}"))
        x.append(para(desc, indent=False, size=20, after=80, line=240))
        x.append(table([1900, 1800, 600, 1500, 2800], ["Kolom", "Tipe", "Null", "Kunci", "Keterangan"], rows, size=16))
        cons = re.findall(r"^- `([^`]+)` \((CHECK|UNIQUE)\): `(.+)`$", blk, re.M)
        cons = [c for c in cons if c[1] == "CHECK" or "," in c[2]]
        if cons:
            x.append(para("Batasan:", indent=False, size=18, line=240, bold=True))
            x.append("".join('<w:p><w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/><w:ind w:left="284"/></w:pPr>'
                             + run(f"{n}: ", size=15, font=MONO, bold=True) + run(d, size=15, font=MONO) + "</w:p>"
                             for n, _, d in cons))
    assert n_tab == 43 and n_col == 528, (n_tab, n_col)
    vrows = [cells(ln) for ln in md[md.index("\n## VIEW"):].splitlines()
             if ln.startswith("| `v_")]
    assert len(vrows) == 22
    x.append(PAGEBREAK)
    x.append(sub("H.44 VIEW"))
    x.append(table([2000, 3300, 3300], ["VIEW", "Kolom", "Keterangan"],
                   [[v, c.replace(", ", ", "), k] for v, c, k in vrows], size=16))
    return "".join(x)


# ------------------------------------------------------------------------------------------------ I DDL
CORE = ["disaster_types", "alert_rules", "region_observations", "alert_events", "disaster_events"]


def lamp_i():
    s = open(os.path.join(ROOT, "database", "monitor_schema.sql"), encoding="utf-8").read()
    x = [caption("I", "DDL Tabel Inti Modul M6"),
         para("DDL berikut dikutip apa adanya dari database/monitor_schema.sql untuk lima relasi inti modul M6 yang "
              "ditunjukkan pada Gambar 4.17 dan Gambar 4.21. DDL lengkap ke-43 tabel, VIEW, trigger, dan indeks berada pada "
              "berkas yang sama, sedangkan role, GRANT, dan row-level security berada pada database/monitor_security.sql di "
              "repositori kode sumber.")]
    for t in CORE:
        m = re.search(r"CREATE TABLE (?:IF NOT EXISTS )?%s\b.*?\n\);" % t, s, re.S)
        assert m, t
        x.append(sub(t))
        x.append(code(m.group(0)))
    return "".join(x)


# ------------------------------------------------------------------------------------------------ J Kueri
def lamp_j():
    src = open(os.path.join(ROOT, "benchmark", "engines.py"), encoding="utf-8").read()
    pg = src[src.index("PG_QUERIES = {"):src.index("\n}\n", src.index("PG_QUERIES = {"))]
    qs = re.findall(r'"(Q\d)": \("([^"]+)", """(.*?)"""', pg, re.S)
    assert [q for q, _, _ in qs] == ["Q1", "Q2", "Q3", "Q4", "Q5"], qs
    ext = open(os.path.join(ROOT, "benchmark", "extended.py"), encoding="utf-8").read()
    q6 = re.search(r'^Q6 = """(.*?)"""', ext, re.S | re.M).group(1)
    x = [caption("J", "Kueri Uji Kinerja"),
         para("Kueri berikut dipakai pada perbandingan PostgreSQL dan MySQL (subbab 4.2.2.3, Tabel 4.18), dikutip dari "
              "benchmark/engines.py (Q1–Q5) dan benchmark/extended.py (Q6). Skema bench adalah salinan setara dari tabel "
              "produksi yang dimuat dengan data sintetis deterministik; parameter %(…)s diisi oleh skrip benchmark. "
              "Versi MySQL memakai logika yang sama dengan sintaks MySQL dan berada pada berkas yang sama.")]
    import textwrap
    for q, desc, sql in qs + [("Q6", "Rekap bulanan hujan per kecamatan pada seluruh observasi", q6)]:
        x.append(sub(f"{q} {desc}"))
        x.append(code(textwrap.dedent(sql).strip()))
    return "".join(x)


# ------------------------------------------------------------------------------------------------ K pytest
def lamp_k():
    r = ET.parse(os.path.join(ROOT, "DOCS", "hasil_uji", "pytest.xml")).getroot()
    c = OrderedDict()
    for tc in r.iter("testcase"):
        cls = tc.get("classname") or ""
        f = cls.split(".")[1] if cls.startswith("tests.") else cls.split(".")[0]
        k = c.setdefault(f, [0, 0, 0, 0])
        k[0] += 1
        if tc.find("skipped") is not None:
            k[3] += 1
        elif tc.find("failure") is not None or tc.find("error") is not None:
            k[2] += 1
        else:
            k[1] += 1
    tot = [sum(v[i] for v in c.values()) for i in range(4)]
    assert tot == [1185, 1183, 0, 2], tot
    ts = r.find("testsuite") if r.tag == "testsuites" else r
    rows = [[("tests/security/grant_matrix" if f == "security" else f"tests/{f}.py")] + [str(n) for n in v] for f, v in c.items()]
    rows.append(["Jumlah"] + [f"{n:,}".replace(",", ".") for n in tot])
    return (caption("K", "Rincian Hasil Pengujian Otomatis")
            + para(f"Tabel berikut merinci hasil pytest pada {ts.get('timestamp', '')[:10]} terhadap basis data uji "
                   f"(berkas DOCS/hasil_uji/pytest.xml), dengan waktu eksekusi {float(ts.get('time')):.0f} detik. Dua kasus "
                   "yang dilewati pada test_hydromet_aggregate membutuhkan berkas shapefile COD-AB yang tidak disertakan pada "
                   "lingkungan uji.")
            + table([4600, 1000, 1000, 1000, 1000], ["Berkas Uji", "Kasus", "Lulus", "Gagal", "Dilewati"], rows, size=17))


# ------------------------------------------------------------------------------------------------ L Tautan
def lamp_l():
    t = open(os.path.join(LAMP, "link_penting.txt"), encoding="utf-8").read()
    url = lambda key: re.search(re.escape(key) + r"\s*:?\s*\n?\s*(https?://\S+)", t).group(1)
    vids = [("S1", "Melihat keadaan di tempat pengguna berada", "01_lokasi_saya_desktop.mp4"),
            ("S2", "Mengatur pemberitahuan melalui surel", "02_email_peringatan_desktop.mp4"),
            ("S3", "Melihat citra satelit", "03_citra_satelit_desktop.mp4"),
            ("S4", "Melihat riwayat kejadian bencana", "04_riwayat_kejadian_desktop.mp4"),
            ("S5", "Mencatat kejadian bencana baru", "05_catat_kejadian_desktop.mp4"),
            ("S6", "Menindaklanjuti peringatan hujan", "06_tindak_lanjut_peringatan_desktop.mp4")]
    rows = [["Aplikasi Orbit-U: The Monitor", url("link deployment")],
            ["Repositori kode sumber", "https://github.com/not-notyou-you/orbit_u_monitor"],
            ["Formulir tinjauan kebutuhan", url("form user requirement")],
            ["Formulir uji coba pengguna", url("form UAT")],
            ["Seluruh video demonstrasi", url("seluruh video demo")]]
    rows += [[f"Video {k}: {n}", url(f)] for k, n, f in vids]
    return (caption("L", "Tautan Aplikasi, Formulir, dan Video Demonstrasi")
            + para("Video demonstrasi S1–S6 adalah video contoh yang ditampilkan pada formulir uji coba pengguna. Jawaban "
                   "kedua formulir tersimpan di Google Sheet dan disajikan pada Lampiran E dan Lampiran F.")
            + table([3300, 5300], ["Butir", "Tautan"], rows, size=18))


# ------------------------------------------------------------------------------------------------ rakit
REPL = [
    ("ERD logikal lengkap kelima modul lain tersedia pada repositori kode sumber penelitian.",
     "ERD keenam modul secara lengkap disajikan pada Lampiran G."),
    ("ERD fisik seluruh modul dan kamus data lengkap tersedia pada repositori kode sumber penelitian.",
     "ERD fisik seluruh modul disajikan pada Lampiran G, kamus data lengkap pada Lampiran H, dan DDL tabel inti pada Lampiran I."),
    ("lalu dikonfirmasi oleh pewawancara.", "lalu dikonfirmasi oleh pewawancara. Notulen wawancara disajikan pada Lampiran D."),
    ("Rekapitulasi jawabannya ditunjukkan pada Tabel 4.30.",
     "Rekapitulasi jawabannya ditunjukkan pada Tabel 4.30, sedangkan jawaban setiap responden disajikan pada Lampiran E."),
    ("tidak ada responden yang menilai tidak layak.",
     "tidak ada responden yang menilai tidak layak. Jawaban setiap responden disajikan pada Lampiran F."),
    ("dengan selisih maksimum 0,1%.", "dengan selisih maksimum 0,1%. Teks SQL kueri Q1–Q6 disajikan pada Lampiran J."),
    ("keduanya diperbaiki sebelum run akhir.",
     "keduanya diperbaiki sebelum run akhir. Rincian jumlah kasus uji per berkas disajikan pada Lampiran K."),
]

zin = zipfile.ZipFile(SRC)
doc = zin.read("word/document.xml").decode("utf-8")
assert "Lampiran D" not in doc and "Notulen Wawancara dengan GMLS" not in doc, "naskah sudah berlampiran"

for old, new in REPL:
    assert doc.count(old) == 1, old
    doc = doc.replace(old, new)

# 1) Bagian awal LAMPIRAN: judul + daftar A-C template diganti caption A + catatan, lalu caption B di halaman formulir B
h = doc.rfind(">LAMPIRAN<")
h_end = doc.index("</w:p>", h) + len("</w:p>")
form_b = doc.index("FORMULIR KONSULTASI SKRIPSI", h_end)
form_b_p = doc.rfind("<w:p ", 0, form_b)
pb = doc.rfind("<w:p ", 0, form_b_p)
assert '<w:br w:type="page"/>' in doc[pb:form_b_p]
head_part = (caption("A", "Turnitin Similarity Report", (220, "_Toc71293273"))
             + para("Sisipkan halaman laporan Turnitin Similarity Report di sini.", indent=False, jc="center", hl=True)
             + PAGEBREAK + caption("B", "Form Konsultasi Bimbingan"))
doc = doc[:h_end] + head_part + doc[form_b_p:]

# 2) caption C di awal formulir AI
fc = doc.index("FORMULIR PENGGUNAAN PERANGKAT")
fc_p = doc.rfind("<w:p ", 0, fc)
line = doc.rfind("_________________________", 0, fc_p)
line_end = doc.index("</w:p>", line) + len("</w:p>")
assert re.fullmatch(r"(<w:p [^>]*>(<w:pPr>.*?</w:pPr>)?</w:p>)*", doc[line_end:fc_p], re.S), "isi tak terduga sebelum formulir C"
capc = caption("C", "Formulir Penggunaan Perangkat Kecerdasan Artifisial (AI)").replace("<w:keepNext/>", "<w:keepNext/><w:pageBreakBefore/>", 1)
doc = doc[:line_end] + capc + doc[fc_p:]

# 3) lampiran D-L sebelum sectPr terakhir
body = PAGEBREAK.join([lamp_d(), lamp_e(), lamp_f(), lamp_g(), lamp_h(), lamp_i(), lamp_j(), lamp_k(), lamp_l()])
last = doc.rfind("<w:sectPr")
tail = re.search(r"(?:<w:p [^>]*>(?:<w:pPr>(?:(?!</w:p>).)*?</w:pPr>)?</w:p>)*$", doc[:last], re.S)
doc = doc[:tail.start()] + body.replace("<w:keepNext/>", "<w:keepNext/><w:pageBreakBefore/>", 1) + doc[last:]

rels = zin.read("word/_rels/document.xml.rels").decode("utf-8")
rels = rels.replace("</Relationships>", "".join(
    f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
    f'Target="media/{name}"/>' for rid, name, _ in IMAGES) + "</Relationships>")
ct = zin.read("[Content_Types].xml").decode("utf-8")
if 'Extension="png"' not in ct:
    ct = ct.replace("<Default ", '<Default Extension="png" ContentType="image/png"/><Default ', 1)

with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zout:
    for item in zin.infolist():
        data = zin.read(item.filename)
        if item.filename == "word/document.xml":
            data = doc.encode("utf-8")
        elif item.filename == "word/_rels/document.xml.rels":
            data = rels.encode("utf-8")
        elif item.filename == "[Content_Types].xml":
            data = ct.encode("utf-8")
        zout.writestr(item, data)
    for _, name, path in IMAGES:
        zout.write(path, f"word/media/{name}")
print(f"lampiran A-L tersusun; gambar: {len(IMAGES)}; rujukan teks diperbarui: {len(REPL)}")
