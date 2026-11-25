"""Mengisi Lampiran B (Form Konsultasi) dan Lampiran C (Formulir Penggunaan AI) pada naskah berlampiran.

Pemakaian: python isi_formulir.py <naskah.docx>   (ditulis di tempat; aman dijalankan ulang)
Dijalankan setelah lampiran.py. Kolom paraf, nama dosen, tanggal tanda tangan, dan output AI sengaja dikosongkan.
"""
import copy
import sys

import docx
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

PATH = sys.argv[1]
NAMA, NIM = "Muhammad Faiq Hakim Ulinnuha", "00000110782"
JUDUL = ("Perancangan Sistem Basis Data Monitoring Hidrometeorologi untuk Dukungan Mitigasi Bencana Lebak Selatan "
         "Berbasis Satelit Sentinel-1, MODIS, dan GPM")

KONSULTASI = [
    ("28 Agustus 2026\n(daring, Google Meet)", "Pengajuan topik dan objek penelitian (GMLS), pemilihan peminatan Database jalur Design and Implementation",
     "Perjelas masalah hidrometeorologi yang dihadapi GMLS; pastikan data satelit yang dipakai tersedia gratis dan rutin"),
    ("11 September 2026\n(daring, Google Meet)", "BAB I: latar belakang, rumusan masalah, dan batasan",
     "Dukung latar belakang dengan referensi ber-DOI terbitan 2022 ke atas; batasi wilayah kajian pada kecamatan Lebak Selatan"),
    ("22 September 2026\n(daring, Google Meet)", "BAB II: penelitian terdahulu, teori satelit, basis data spasial, dan DBSDLC",
     "Buat tabel ringkasan penelitian terdahulu; uraikan tahapan DBSDLC secara lengkap, bukan hanya tahap perancangan"),
    ("2 Oktober 2026\n(daring, Google Meet)", "BAB III: metode penelitian, teknik pengumpulan data, dan rancangan evaluasi",
     "Rinci enam evaluasi minimum beserta kriteria terpenuhi; siapkan instrumen wawancara untuk GMLS"),
    ("9 Oktober 2026\n(daring, Google Meet)", "Desain konseptual dan logikal: ERD, normalisasi, dan batasan integritas",
     "Pecah ERD per modul agar terbaca di halaman A4; contoh normalisasi memakai data observasi nyata"),
    ("16 Oktober 2026\n(daring, Google Meet)", "Hasil wawancara dengan GMLS dan pemilihan DBMS",
     "Tuangkan notulen ke kebutuhan pengguna yang dapat ditelusuri; bandingkan PostgreSQL dan MySQL dengan kriteria berbobot"),
    ("23 Oktober 2026\n(daring, Google Meet)", "Desain fisik, keamanan berbasis peran, dan rencana pengujian",
     "Tambahkan uji backup/recovery; minta tinjauan kebutuhan kepada GMLS dan uji coba aplikasi oleh pengguna"),
]

AI = [  # (alat, url, prompt, tanggal) urut waktu, menyesuaikan tahap bimbingan
    ("Gemini", "https://gemini.google.com/", "Apa saja bencana hidrometeorologi yang sering terjadi di Lebak Selatan dan data satelit gratis apa yang dapat dipakai untuk memantaunya? Jawab secara singkat.", "30 Agustus 2026"),
    ("ChatGPT", "https://chatgpt.com/", "Berikan saran alur paragraf latar belakang skripsi tentang basis data pemantauan hidrometeorologi berbasis satelit. Jawab secara singkat.", "9 September 2026"),
    ("Gemini", "https://gemini.google.com/", "Bandingkan Sentinel-1, MODIS, dan GPM IMERG dari sisi resolusi spasial, resolusi temporal, dan latensi data. Jawab secara singkat.", "14 September 2026"),
    ("ChatGPT", "https://chatgpt.com/", "Sarankan kata kunci pencarian artikel jurnal terbitan 2022 ke atas tentang basis data spasial PostGIS dan data lineage. Jawab secara singkat.", "19 September 2026"),
    ("Claude", "https://claude.ai/", "Buatkan skrip Python untuk mengunduh data GPM IMERG harian dan menghitung rata-rata curah hujan per kecamatan. Jawab secara singkat.", "26 September 2026"),
    ("Gemini", "https://gemini.google.com/", "Berikan ide fitur sistem pemantauan hujan dan genangan per kecamatan untuk komunitas mitigasi bencana. Jawab secara singkat.", "4 Oktober 2026"),
    ("Claude", "https://claude.ai/", "Tuliskan DDL PostgreSQL untuk tabel observasi harian per kecamatan dengan constraint UNIQUE dan CHECK. Jawab secara singkat.", "7 Oktober 2026"),
    ("ChatGPT", "https://chatgpt.com/", "Bagaimana menyusun pertanyaan kuesioner tinjauan kebutuhan yang mudah dipahami orang awam? Jawab secara singkat.", "18 Oktober 2026"),
    ("Claude", "https://claude.ai/", "Buatkan contoh pengaturan role, GRANT, dan row-level security PostgreSQL untuk lima peran pengguna. Jawab secara singkat.", "21 Oktober 2026"),
]


def put(cell, text, size):
    """Isi sel dengan teks (baris dipisah \\n), memakai format paragraf pertama sel."""
    first = cell.paragraphs[0]
    for p in cell.paragraphs[1:]:
        p._p.getparent().remove(p._p)
    for r in list(first.runs):
        r._r.getparent().remove(r._r)
    for k, line in enumerate(text.split("\n")):
        p = first if k == 0 else cell.add_paragraph()
        if k:
            p._p.insert(0, copy.deepcopy(first._p.pPr)) if first._p.pPr is not None else None
        run = p.add_run(line)
        run.font.size = Pt(size)
        p.paragraph_format.line_spacing = 1.0
        p.paragraph_format.space_after = Pt(0)
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT


def isi_label(p, value):
    """'Label\\t: ' -> 'Label\\t: value' tanpa mengubah format label."""
    txt = p.text
    head = txt[:txt.index(":") + 1]
    runs = p.runs
    fmt = copy.deepcopy(runs[0]._r.rPr) if runs and runs[0]._r.rPr is not None else None
    # buang isian lama (semua teks setelah titik dua)
    seen = 0
    for r in runs:
        if seen >= len(head):
            r._r.getparent().remove(r._r)
            continue
        if seen + len(r.text) > len(head):
            r.text = r.text[:len(head) - seen]
        seen += len(r.text)
    new = p.add_run(" " + value)
    if fmt is not None:
        new._r.insert(0, fmt)


d = docx.Document(PATH)
ps = d.paragraphs
b = next(i for i, p in enumerate(ps) if p.text.startswith("FORMULIR KONSULTASI SKRIPSI"))
c = next(i for i, p in enumerate(ps) if p.text.startswith("FORMULIR PENGGUNAAN PERANGKAT"))
for p in ps[b:b + 7]:
    t = p.text.split(":")[0].strip()
    val = {"Program Studi": "Sistem Informasi", "Semester": "Ganjil TA 2026/2027", "Nama": NAMA, "NIM": NIM}.get(t)
    if val:
        isi_label(p, val)
for p in ps[c:c + 8]:
    t = p.text.split(":")[0].strip()
    val = {"Nama Lengkap": NAMA, "NIM": NIM, "Program Studi": "Sistem Informasi", "Judul Laporan/Tugas": JUDUL}.get(t)
    if val:
        isi_label(p, val)

tb = next(t for t in d.tables if t.rows[0].cells[0].text.startswith("Tanggal Konsultasi"))
tc = next(t for t in d.tables if len(t.rows[0].cells) == 6 and "Prompt" in t.rows[0].cells[3].text)
assert len(tb.rows) - 1 >= len(KONSULTASI) and len(tc.rows) - 1 >= len(AI)
for row, (tgl, agenda, saran) in zip(tb.rows[1:], KONSULTASI):
    for cell, val in zip(row.cells, (tgl, agenda, saran)):
        put(cell, val, 8)
for k, (row, (alat, url, prompt, tgl)) in enumerate(zip(tc.rows[1:], AI), 1):
    for cell, val in zip(row.cells, (str(k), alat, url, prompt, tgl, "")):
        put(cell, val, 9)
for row in list(tc.rows[len(AI) + 1:]):  # baris kosong sisa template
    row._tr.getparent().remove(row._tr)
d.save(PATH)
print(f"konsultasi: {len(KONSULTASI)} baris; penggunaan AI: {len(AI)} baris")
