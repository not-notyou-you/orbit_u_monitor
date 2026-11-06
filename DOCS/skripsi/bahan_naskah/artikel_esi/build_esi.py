"""Bangun naskah Earth Science Informatics (Springer) dari nol sebagai .docx polos sesuai submission guidelines:
Word, Times 10 pt, tanpa field kecuali nomor halaman otomatis, maksimal 3 tingkat judul, sitasi penulis-tahun,
daftar pustaka alfabetis dengan DOI penuh, "Fig." tebal, gambar dalam teks.
python build_esi.py ../artikel_gaee/refs.json ../artikel_gaee out.docx"""
import html, json, os, re, struct, sys, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import content_esi as C

refs_p, figdir, out = sys.argv[1:4]
REFS = json.load(open(refs_p, encoding="utf-8"))
fig_no, tab_no, eq_no = {}, {}, {}
for k, v in C.BODY:
    if k == "FIG": fig_no[v] = len(fig_no) + 1
    if k == "TAB": tab_no[v] = len(tab_no) + 1
    if k == "EQ": eq_no[v] = len(eq_no) + 1
cited = set()


HL = '<w:highlight w:val="green"/>'


def esc(s): return html.escape(s, quote=False)


def surname(k):
    if k in C.MANUAL: return C.MANUAL[k][0], C.MANUAL[k][1]
    m = REFS[k]; a = m["authors"]
    n = a[0][0] if len(a) == 1 else (f"{a[0][0]} and {a[1][0]}" if len(a) == 2 else f"{a[0][0]} et al.")
    return html.unescape(n), str(m["year"])


def cite(m):
    narr = m.group(1).startswith("@!")
    keys = [k.strip().lstrip("@!") for k in m.group(1).split(",")]
    cited.update(keys)
    if narr:
        n, y = surname(keys[0]); return f"{n} ({y})"
    keys.sort(key=lambda k: (surname(k)[0].lower(), surname(k)[1]))
    return "(" + "; ".join(" ".join(surname(k)) for k in keys) + ")"


def text(s):
    s = re.sub(r"\[(@[^\]]+)\]", cite, s)
    s = re.sub(r"\{F:(\w+)\}", lambda m: f"Fig. {fig_no[m.group(1)]}", s)
    s = re.sub(r"\{T:(\w+)\}", lambda m: f"Table {tab_no[m.group(1)]}", s)
    return s


def runs(s, base=""):
    out = []
    s = text(s)
    if "highlight" not in base: s = re.sub(r"(\[[^\]]*(?:to be|To be|Supervisor|supervisor)[^\]]*\])", r"==\1==", s)
    for tok in re.split(r"(==[^=]+==|\*\*[^*]+\*\*|\*[^*]+\*|~[^~]+~|\^[^^]+\^)", s):
        if not tok: continue
        rp = base
        if tok.startswith("=="):
            out.append(runs_hl(tok[2:-2], base)); continue
        if tok.startswith("**"): rp += "<w:b/>"; tok = tok[2:-2]
        elif tok[0] == "*": rp += "<w:i/>"; tok = tok[1:-1]
        elif tok[0] == "~": rp += '<w:vertAlign w:val="subscript"/>'; tok = tok[1:-1]
        elif tok[0] == "^": rp += '<w:vertAlign w:val="superscript"/>'; tok = tok[1:-1]
        out.append(f'<w:r>{"<w:rPr>" + rp + "</w:rPr>" if rp else ""}<w:t xml:space="preserve">{esc(tok)}</w:t></w:r>')
    return "".join(out)


def runs_hl(s, base=""):
    return runs(s.replace("==", ""), base + HL) if "==" not in s else runs(s, base)


def P(s, style="Normal", ppr="", hl=False):
    return f'<w:p><w:pPr><w:pStyle w:val="{style}"/>{ppr}</w:pPr>{runs(s, HL if hl else "")}</w:p>'


rels, media = [], []


def png_size(fn):
    with open(fn, "rb") as f: d = f.read(24)
    return struct.unpack(">II", d[16:24])


def caption_src(src):
    return "" if src.strip() == "Own elaboration" else f" ({src.replace('Own elaboration based on', 'Based on')})"


def figure(key):
    fn, title, src, alt = C.FIGS[key]
    w, h = png_size(os.path.join(figdir, fn))
    cx = int(160 / 25.4 * 914400); cy = int(cx * h / w)          # lebar 160 mm (< 174 mm satu kolom)
    if cy > int(130 / 25.4 * 914400): cy = int(130 / 25.4 * 914400); cx = int(cy * w / h)
    n = len(media) + 1; rid = f"rIdImg{n}"; media.append(fn); rels.append((rid, "image", f"media/{os.path.basename(fn)}"))
    a = html.escape(alt)
    drw = (f'<w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{cx}" cy="{cy}"/>'
           f'<wp:docPr id="{n}" name="Fig{fig_no[key]}" descr="{a}"/><wp:cNvGraphicFramePr>'
           '<a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr><a:graphic><a:graphicData '
           'uri="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:pic><pic:nvPicPr>'
           f'<pic:cNvPr id="{n}" name="{os.path.basename(fn)}" descr="{a}"/><pic:cNvPicPr/></pic:nvPicPr><pic:blipFill>'
           f'<a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill><pic:spPr><a:xfrm>'
           f'<a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/>'
           '</a:prstGeom></pic:spPr></pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r>')
    return (f'<w:p><w:pPr><w:pStyle w:val="Figure"/><w:keepNext/></w:pPr>{drw}</w:p>'
            + P(f"**Fig. {fig_no[key]}** {title}{caption_src(src)}", "Caption"))


HR = '<w:{0} w:val="single" w:sz="8" w:space="0" w:color="000000"/>'


def table(key):
    title, src, widths, head, rows = C.TABLES[key]
    sc = 9638 / sum(widths); widths = [int(w * sc) for w in widths]
    grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in widths)

    def row(cells, hdr=False, last=False):
        b = (HR.format("top") + HR.format("bottom")) if hdr else (HR.format("bottom") if last else "")
        tc = "".join(f'<w:tc><w:tcPr><w:tcW w:w="{w}" w:type="dxa"/><w:tcBorders>{b}</w:tcBorders></w:tcPr>'
                     f'{P(f"**{c}**" if hdr and c else c, "TableText")}</w:tc>' for w, c in zip(widths, cells))
        return f'<w:tr>{"<w:trPr><w:tblHeader/></w:trPr>" if hdr else ""}{tc}</w:tr>'
    body = row(head, True) + "".join(row(r, last=(i == len(rows) - 1)) for i, r in enumerate(rows))
    tbl = (f'<w:tbl><w:tblPr><w:tblW w:w="{sum(widths)}" w:type="dxa"/><w:tblLayout w:type="fixed"/>'
           '<w:tblCellMar><w:left w:w="57" w:type="dxa"/><w:right w:w="57" w:type="dxa"/></w:tblCellMar>'
           f'<w:tblLook w:val="0000"/></w:tblPr><w:tblGrid>{grid}</w:tblGrid>{body}</w:tbl>')
    return P(f"**Table {tab_no[key]}** {title}{caption_src(src)}", "Caption", "<w:keepNext/>") + tbl + P("", "Normal")


def mr(t, sty=None):
    s = f'<m:rPr><m:sty m:val="{sty}"/></m:rPr>' if sty else ""
    return f'<m:r>{s}<w:rPr><w:rFonts w:ascii="Cambria Math" w:hAnsi="Cambria Math"/></w:rPr><m:t>{esc(t)}</m:t></m:r>'


def msub(b, s): return f"<m:sSub><m:e>{b}</m:e><m:sub>{s}</m:sub></m:sSub>"


def nary(sub, body, sup=None):
    hide = "" if sup else '<m:supHide m:val="1"/>'
    return (f'<m:nary><m:naryPr><m:chr m:val="∑"/><m:limLoc m:val="undOvr"/>{hide}</m:naryPr>'
            f"<m:sub>{sub}</m:sub><m:sup>{sup or ''}</m:sup><m:e>{body}</m:e></m:nary>")


EQ = {
    "zonal": msub(mr("x̄"), mr("r,b,t")) + mr("=", "p") + "<m:f><m:num>"
             + nary(mr("c∈") + msub(mr("V"), mr("r")), msub(mr("w"), mr("c")) + mr("·", "p") + msub(mr("x"), mr("c")))
             + "</m:num><m:den>" + nary(mr("c∈") + msub(mr("V"), mr("r")), msub(mr("w"), mr("c"))) + "</m:den></m:f>"
             + mr(",", "p") + mr("  ", "p") + msub(mr("w"), mr("c")) + mr("=", "p") + msub(mr("a"), mr("r,c"))
             + mr("·", "p") + mr("cos", "p") + msub(mr("φ"), mr("c")),
    "score": mr("S") + mr("=", "p") + nary(mr("i=1"), msub(mr("w"), mr("i")) + mr("·", "p") + msub(mr("s"), mr("i")),
                                            mr("7", "p")),
}


def equation(key):
    return (f'<w:p><w:pPr><w:pStyle w:val="Equation"/></w:pPr><m:oMath>{EQ[key]}</m:oMath>'
            f'<w:r><w:tab/><w:t>({eq_no[key]})</w:t></w:r></w:p>')


# ---------------- isi
x = []
x.append(P(C.ARTICLE_TYPE, "Normal"))
x.append(P(C.TITLE, "Title"))
au = []
for i, (n, a, corr) in enumerate(C.AUTHORS):
    if i: au.append('<w:r><w:t xml:space="preserve"> · </w:t></w:r>')
    au.append(runs(n) + f'<w:r><w:rPr><w:vertAlign w:val="superscript"/></w:rPr>'
              f'<w:t>{a}{"*" if corr else ""}</w:t></w:r>')
x.append(f'<w:p><w:pPr><w:pStyle w:val="Authors"/></w:pPr>{"".join(au)}</w:p>')
for i, a in enumerate(C.AFFIL):
    x.append(f'<w:p><w:pPr><w:pStyle w:val="Affil"/></w:pPr><w:r><w:rPr><w:vertAlign w:val="superscript"/></w:rPr>'
             f'<w:t>{i + 1}</w:t></w:r>{runs(" " + a)}</w:p>')
x.append(P("* Corresponding author: " + C.CORRESP, "Affil"))
x.append(P("**ORCID**", "Affil"))
for o in C.ORCID: x.append(P(o, "Affil"))
x.append(P("**Acknowledgements** " + C.ACK, "Affil"))
x.append(P("**Abstract** " + C.ABSTRACT, "Abstract"))
x.append(P("**Keywords** " + C.KEYWORDS, "Abstract"))

h1 = h2 = 0
for kind, val in C.BODY:
    if kind == "H1":
        h1 += 1; h2 = 0; x.append(P(f"{h1} {val}", "Heading1"))
    elif kind == "H2":
        h2 += 1; x.append(P(f"{h1}.{h2} {val}", "Heading2"))
    elif kind == "P": x.append(P(val))
    elif kind == "FIG": x.append(figure(val))
    elif kind == "TAB": x.append(table(val))
    elif kind == "EQ": x.append(equation(val))

h1 += 1; x.append(P(f"{h1} Availability and requirements", "Heading1"))
for k, v in C.AVAILABILITY: x.append(P(f"**{k}:** {v}", "List"))
x.append(P("Abbreviations", "Heading1U"))
for k, v in C.ABBREV: x.append(P(f"**{k}** {v}", "List"))
x.append(P("Declarations", "Heading1U"))
for k, v in C.DECLARATIONS: x.append(P(f"**{k}** {v}", hl=True))
x.append(P("References", "Heading1U"))


def initials(g):
    return "".join(p[0] for p in re.split(r"[ .\-]+", g) if p)


def ref(k):
    if k in C.MANUAL: return C.MANUAL[k][2]
    m = REFS[k]
    names = [f"{html.unescape(f)} {initials(html.unescape(g))}".strip() for f, g in m["authors"]]
    au = ", ".join(names) if len(names) <= 10 else ", ".join(names[:3]) + " et al"
    t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", m["title"]))).strip().rstrip(".")
    j = html.unescape(m["journal"])
    s = f"{au} ({m['year']}) {t}. "
    pg = (m.get("pages") or m.get("art") or "").replace("-", "–")
    if m["type"] == "proceedings-article":
        s += f"In: {j}" + (f", pp {pg}" if pg else "")
    else:
        s += f"{j}" + (f" {m['vol']}" if m.get("vol") else "") + (f":{pg}" if pg else "")
    return s + f". https://doi.org/{m['doi']}"


# kumpulkan sitasi dari keterangan gambar/tabel juga (sudah lewat text()), lalu urut alfabetis
def key_sort(k):
    s = ref(k); return (s.lower(), )


for k in sorted(cited, key=key_sort):
    x.append(P(ref(k), "Reference"))
x.append(P("Software files", "Heading1U"))
x.append(P(C.SOFTWARE_FILES, hl=True))

# ---------------- paket docx
NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
      'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
      'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
      'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture" '
      'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"')
rels.append(("rIdFtr", "footer", "footer1.xml")); rels.append(("rIdSty", "styles", "styles.xml"))
rels.append(("rIdSet", "settings", "settings.xml"))
sect = ('<w:sectPr><w:footerReference w:type="default" r:id="rIdFtr"/><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1417" w:right="1417" w:bottom="1417" w:left="1417" w:header="709" w:footer="709" w:gutter="0"/>'
        '<w:lnNumType w:countBy="1" w:restart="continuous"/></w:sectPr>')
doc = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {NS}><w:body>{"".join(x)}{sect}</w:body></w:document>'


def sty(sid, name, ppr="", rpr="", based="Normal", typ="paragraph", outline=None):
    o = f'<w:outlineLvl w:val="{outline}"/>' if outline is not None else ""
    b = f'<w:basedOn w:val="{based}"/>' if based else ""
    return (f'<w:style w:type="{typ}" w:styleId="{sid}"><w:name w:val="{name}"/>{b}<w:qFormat/>'
            f'<w:pPr>{ppr}{o}</w:pPr><w:rPr>{rpr}</w:rPr></w:style>')


SP = lambda b, a, line=360: f'<w:spacing w:before="{b}" w:after="{a}" w:line="{line}" w:lineRule="auto"/>'
styles = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
          '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" '
          'w:eastAsia="Times New Roman" w:cs="Times New Roman"/><w:sz w:val="20"/><w:szCs w:val="20"/><w:lang w:val="en-GB"/>'
          '</w:rPr></w:rPrDefault><w:pPrDefault><w:pPr>' + SP(0, 120) + '</w:pPr></w:pPrDefault></w:docDefaults>'
          + sty("Normal", "Normal", '<w:jc w:val="both"/>', based=None)
          + sty("Title", "Title", SP(240, 240) + '<w:jc w:val="left"/>', '<w:b/><w:sz w:val="28"/><w:szCs w:val="28"/>')
          + sty("Authors", "Authors", SP(0, 120) + '<w:jc w:val="left"/>', '<w:sz w:val="22"/>')
          + sty("Affil", "Affiliation", SP(0, 60) + '<w:jc w:val="left"/>', '<w:sz w:val="18"/>')
          + sty("Abstract", "Abstract", SP(120, 120), "")
          + sty("Heading1", "heading 1", '<w:keepNext/>' + SP(360, 120) + '<w:jc w:val="left"/>', '<w:b/><w:sz w:val="22"/>', outline=0)
          + sty("Heading1U", "Heading unnumbered", '<w:keepNext/>' + SP(360, 120) + '<w:jc w:val="left"/>', '<w:b/><w:sz w:val="22"/>', outline=0)
          + sty("Heading2", "heading 2", '<w:keepNext/>' + SP(240, 120) + '<w:jc w:val="left"/>', '<w:b/>', outline=1)
          + sty("Figure", "Figure", SP(120, 60, 240) + '<w:jc w:val="center"/>')
          + sty("Caption", "caption", SP(60, 240, 240) + '<w:jc w:val="left"/>', '<w:sz w:val="18"/>')
          + sty("TableText", "Table text", SP(20, 20, 240) + '<w:jc w:val="left"/>', '<w:sz w:val="18"/>')
          + sty("Equation", "Equation", SP(120, 120) + '<w:tabs><w:tab w:val="center" w:pos="4536"/><w:tab w:val="right" w:pos="9072"/></w:tabs><w:jc w:val="center"/>')
          + sty("List", "List entry", SP(0, 40) + '<w:ind w:left="284" w:hanging="284"/><w:jc w:val="left"/>')
          + sty("Reference", "Reference", SP(0, 80) + '<w:ind w:left="284" w:hanging="284"/><w:jc w:val="left"/>')
          + '</w:styles>')
footer = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
          '<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
          '<w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>1</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p></w:ftr>')
settings = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:defaultTabStop w:val="709"/><w:compat><w:compatSetting w:name="compatibilityMode" w:uri="http://schemas.microsoft.com/office/word" w:val="15"/></w:compat></w:settings>')
T = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
drels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
         + "".join(f'<Relationship Id="{i}" Type="{T}{t}" Target="{g}"/>' for i, t, g in rels) + '</Relationships>')
ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
      '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
      '<Default Extension="png" ContentType="image/png"/>'
      '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
      '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
      '<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>'
      '<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
      '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/></Types>')
root = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'<Relationship Id="rId1" Type="{T}officeDocument" Target="word/document.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/></Relationships>')
core = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        f'xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>{esc(C.TITLE)}</dc:title><dc:creator>Muhammad Faiq Hakim Ulinnuha</dc:creator></cp:coreProperties>')

with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for n, d in [("[Content_Types].xml", ct), ("_rels/.rels", root), ("word/document.xml", doc), ("word/styles.xml", styles),
                 ("word/settings.xml", settings), ("word/footer1.xml", footer), ("word/_rels/document.xml.rels", drels),
                 ("docProps/core.xml", core)]:
        z.writestr(n, d.encode("utf-8"))
    for f in media: z.write(os.path.join(figdir, f), f"word/media/{os.path.basename(f)}")

from xml.dom import minidom
for d in (doc, styles, footer, drels, ct): minidom.parseString(d.encode("utf-8"))
body = re.sub(r"\*|~|\^", "", " ".join(text(v) for k, v in C.BODY if k == "P"))
print("referensi:", len(cited), "| kata isi:", len(body.split()), "| kata abstrak:", len(C.ABSTRACT.split()),
      "| keyword:", len(C.KEYWORDS.split("·")))
print("di refs.json tapi tidak dikutip:", [k for k in REFS if k not in cited])
