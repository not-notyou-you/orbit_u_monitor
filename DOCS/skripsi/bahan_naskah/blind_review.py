"""Versi blind review skripsi dan artikel GaEE: tanpa nama orang, NIM, ORCID, e-mail, dan identitas institusi penulis.

Pemakaian: python blind_review.py
Masukan : naskah/SKRIPSI FINAL.docx, naskah/Ulinnuha_GaEE_Traceable_Spatial_Database.docx.docx (tidak diubah)
Keluaran: naskah/BLIND_REVIEW_SKRIPSI.docx, naskah/BLIND_REVIEW_ARTIKEL_GaEE.docx

Keputusan (12 Nov 2026):
- Nama penulis karya yang dirujuk (daftar pustaka, "Khan dkk.") dipertahankan.
- Skripsi: template prodi dipertahankan utuh (logo latar, sampul, halaman pernyataan sampai kata pengantar,
  footer, lampiran); hanya nama penulis dan NIM yang diganti "[Nama dianonimkan]" / "[NIM dianonimkan]".
- Di isi naskah, institusi penulis (universitas, fakultas, LPPM, program pengabdiannya) dan di artikel
  The IO Foundation dianonimkan; GMLS dan Lebak Selatan tetap karena objek penelitian.
  Nama narasumber (Ketua GMLS) diganti jabatannya, juga di kata pengantar.
- URL aplikasi dan repositori dibiarkan.
Skrip berhenti dengan galat bila setelah diproses masih ada jejak identitas (lihat FORBIDDEN).
"""
import copy, pathlib, re, zipfile
from lxml import etree

HERE = pathlib.Path(__file__).parent
NASKAH = HERE.parent / "naskah"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W}
q = lambda t: f"{{{W}}}{t}"

INST = "[institusi penulis]"
FORBIDDEN = re.compile(r"Muhammad|Faiq|Ulinnuha|00000110782|Multimedia Nusantara|\bUMN\b|Tangerang|Anis Faisal|"
                       r"Abah Lala|Humanity Project|LPPM|Fakultas Teknik|Fakultas Ilmu|Irena|Vanessa|Gunawan|Monika|"
                       r"Evelin|Johan|ORCID|0009-0008|0000-0003-2905|0000-0001-7984|gmail|umn\.ac\.id|maranatha|"
                       r"IO Foundation|agnieszka|Bieda|Nama Penulis", re.I)

PERSONAL_REPL = [
    ("Muhammad Faiq Hakim Ulinnuha", "[Nama dianonimkan]"),
    ("00000110782", "[NIM dianonimkan]"),
    ("Bapak Anis Faisal Reza (Abah Lala), selaku Ketua", "Ketua"),
]
FORBIDDEN_SKRIPSI = re.compile(r"Muhammad Faiq|Faiq|Ulinnuha|00000110782|Anis Faisal|Abah Lala|Humanity Project|LPPM")
SKRIPSI_REPL = [
    ("sedangkan ketua dan pendirinya, Anis Faisal Reza (Abah Lala), telah memulai",
     "sedangkan ketua dan pendirinya telah memulai"),
    ("GMLS bekerja sama secara resmi dengan Universitas Multimedia Nusantara melalui LPPM dengan nota kesepahaman (MoU). "
     "Kolaborasi ini dipimpin Fakultas Teknik dan Informatika dan didukung Fakultas Ilmu Komunikasi, dengan",
     f"GMLS bekerja sama secara resmi dengan {INST} melalui nota kesepahaman (MoU), dengan"),
    ("Aplikasi dalam Kerja Sama GMLS dan UMN", "Aplikasi dalam Kerja Sama GMLS dan [Institusi Penulis]"),
    ("kerja sama Humanity Project GMLS x UMN", f"kerja sama GMLS dan {INST}"),
    ("Kerja sama GMLS dan UMN sebelumnya", f"Kerja sama GMLS dan {INST} sebelumnya"),
    ("narasumber Anis Faisal Reza (Abah Lala), ketua dan pendiri GMLS, dengan didampingi dosen yang pernah "
     "melaksanakan Humanity Project di Lebak Selatan.",
     "narasumber ketua dan pendiri GMLS, dengan didampingi dosen yang pernah melaksanakan program pengabdian "
     "masyarakat di Lebak Selatan."),
    ("peserta Humanity Project di GMLS", "peserta program pengabdian masyarakat di GMLS"),
    ("3 peserta Humanity Project yang terlibat", "3 peserta program pengabdian masyarakat yang terlibat"),
    ("10 mahasiswa di luar Fakultas Teknik dan Informatika yang", "10 mahasiswa dari luar bidang teknik dan informatika yang"),
]
ARTIKEL_REPL = [
    ("on a Proxmox VE host provided by The IO Foundation,", "on a Proxmox VE host provided by an anonymised organisation,"),
]


def text(el):
    return "".join(t.text or "" for t in el.iter(q("t")))


def replace_text(root, pairs):
    """Ganti frasa per paragraf, juga bila frasa melintasi beberapa run (mis. kata miring di tengahnya).
    Teks pengganti masuk ke w:t tempat frasa dimulai; sisa frasa di w:t berikutnya dihapus.
    Setiap frasa wajib ditemukan agar perubahan naskah tidak terlewat diam-diam."""
    for old, new in pairs:
        n = 0
        for p in root.iter(q("p")):
            while True:
                ts = list(p.iter(q("t")))
                full = "".join(t.text or "" for t in ts)
                k = full.find(old)
                if k < 0:
                    break
                n += 1
                pos, end = 0, k + len(old)
                for t in ts:
                    s = t.text or ""; a, b = pos, pos + len(s); pos = b
                    if b <= k or a >= end:
                        continue
                    lo, hi = max(k, a) - a, min(end, b) - a
                    t.text = s[:lo] + (new if a <= k < b else "") + s[hi:]
                    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        if not n:
            raise SystemExit(f"frasa tidak ditemukan: {old[:70]}")


def set_para_text(p, s):
    """Kosongkan isi paragraf dan isi dengan satu run (format run pertama dipertahankan)."""
    runs = p.findall(q("r"))
    rpr = runs[0].find(q("rPr")) if runs else None
    for ch in list(p):
        if ch.tag != q("pPr"):
            p.remove(ch)
    r = etree.SubElement(p, q("r"))
    if rpr is not None:
        r.append(copy.deepcopy(rpr))
    t = etree.SubElement(r, q("t")); t.text = s


def strip_pictures(root):
    for tag in ("drawing", "pict"):
        for el in list(root.iter(q(tag))):
            r = el.getparent(); r.getparent().remove(r) if r.tag == q("r") else r.remove(el)


def has_sect(el):
    return el.tag == q("sectPr") or el.find(".//w:sectPr", NS) is not None


def skripsi(body):
    """Template dipertahankan; hanya data pribadi dan identitas institusi di isi naskah yang diganti."""
    replace_text(body, PERSONAL_REPL + SKRIPSI_REPL)
    return 0


def strip_pictures_in(body, upto_text):
    """Hapus gambar (logo) yang masih tersisa di halaman sebelum judul tertentu."""
    for k in body:
        if text(k).strip() == upto_text:
            break
        strip_pictures(k)


def artikel(body, footnotes):
    kids = list(body)
    authors = kids[0]
    assert authors.find(".//w:pStyle[@w:val='GaEEAuthors']", NS) is not None
    set_para_text(authors, "[Authors removed for blind review]")
    texts = [text(k).strip() for k in kids]
    i = texts.index("CRediT Author Contribution")
    set_para_text(kids[i + 1], "[Removed for blind review]")
    replace_text(body, ARTIKEL_REPL)
    for fn in list(footnotes.findall("w:footnote", NS)):
        if int(fn.get(q("id"))) > 0:                        # 0 dan -1 adalah pemisah bawaan Word
            footnotes.remove(fn)


def clean_meta(name, data):
    s = data.decode("utf-8")
    if name == "docProps/core.xml":
        s = re.sub(r"<dc:creator>[^<]*</dc:creator>", "<dc:creator></dc:creator>", s)
        s = re.sub(r"<cp:lastModifiedBy>[^<]*</cp:lastModifiedBy>", "<cp:lastModifiedBy></cp:lastModifiedBy>", s)
    if name.startswith("customXml/item"):                 # properti sampul template terikat ke footer
        s = re.sub(r"<Abstract>[^<]*</Abstract>", "<Abstract></Abstract>", s)
    if name == "docProps/app.xml":
        s = re.sub(r"<Company>[^<]*</Company>", "<Company></Company>", s)
        s = re.sub(r"<Manager>[^<]*</Manager>", "<Manager></Manager>", s)
    return s.encode("utf-8")


def process(src, out, kind):
    z = zipfile.ZipFile(src)
    parts = {n: z.read(n) for n in z.namelist()}
    doc = etree.fromstring(parts["word/document.xml"])
    body = doc.find("w:body", NS)
    if kind == "skripsi":
        skripsi(body)
    else:
        fn = etree.fromstring(parts["word/footnotes.xml"])
        artikel(body, fn)
        parts["word/footnotes.xml"] = etree.tostring(fn, xml_declaration=True, encoding="UTF-8", standalone=True)
    parts["word/document.xml"] = etree.tostring(doc, xml_declaration=True, encoding="UTF-8", standalone=True)
    meta = ["docProps/core.xml", "docProps/app.xml"]
    if kind == "artikel":
        meta += [n for n in parts if re.match(r"customXml/item\d+\.xml$", n)]
    for name in meta:
        if name in parts:
            parts[name] = clean_meta(name, parts[name])
    # buang relasi gambar dan berkas media yang tidak lagi dirujuk (logo, tanda tangan)
    used_media = set()
    for name in [n for n in parts if n.startswith("word/_rels/") and n.endswith(".rels")]:
        owner = "word/" + name[len("word/_rels/"):-len(".rels")]
        if owner not in parts:
            continue
        own = parts[owner].decode("utf-8")
        rels = parts[name].decode("utf-8")
        for m in list(re.finditer(r'<Relationship [^>]*Id="([^"]+)"[^>]*Target="media/([^"]+)"[^>]*/>', rels)):
            if f'"{m.group(1)}"' in own:
                used_media.add(m.group(2))
            else:
                rels = rels.replace(m.group(0), "")
        parts[name] = rels.encode("utf-8")
    for name in [n for n in parts if n.startswith("word/media/") and n[len("word/media/"):] not in used_media]:
        del parts[name]
    # pemeriksaan akhir: tidak boleh ada jejak identitas (URL dibiarkan sesuai keputusan)
    leaks = []
    for name, data in parts.items():
        if not name.endswith((".xml", ".rels")) or "webextension" in name:
            continue
        s = re.sub(r"https?://\S+", "", data.decode("utf-8", "ignore"))
        if name in ("word/document.xml", "word/footnotes.xml") or re.match(r"word/(header|footer)", name):
            s = " ".join(text(p) for p in etree.fromstring(data).iter(q("p")))
            s = re.sub(r"https?://\S+", "", s)
            if kind == "skripsi" and name == "word/document.xml":
                s = s[:s.rfind("DAFTAR PUSTAKA")]           # nama penulis karya rujukan dipertahankan
        for m in (FORBIDDEN_SKRIPSI if kind == "skripsi" else FORBIDDEN).finditer(s):
            leaks.append(f"{name}: …{s[max(0, m.start() - 60):m.end() + 40]}…")
    if leaks:
        raise SystemExit("masih ada jejak identitas:\n" + "\n".join(leaks[:20]))
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zo:
        for info in z.infolist():
            if info.filename in parts:
                zo.writestr(info, parts[info.filename])
    print(f"{out.name}: bersih; media {len(used_media)} berkas")


if __name__ == "__main__":
    process(NASKAH / "SKRIPSI FINAL.docx", NASKAH / "BLIND_REVIEW_SKRIPSI.docx", "skripsi")
    process(NASKAH / "Ulinnuha_GaEE_Traceable_Spatial_Database.docx.docx", NASKAH / "BLIND_REVIEW_ARTIKEL_GaEE.docx", "artikel")
