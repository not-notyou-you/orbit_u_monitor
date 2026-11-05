"""Bangun artikel GaEE dari template resmi: python build_article.py template.docx refs.json figdir out.docx"""
import html, json, re, sys, zipfile
from PIL import Image
sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
import content as C

tpl, refs_p, figdir, out = sys.argv[1:5]
REFS = json.load(open(refs_p, encoding="utf-8"))
order, num = [], {}
fig_no, tab_no, eq_no = {}, {}, {}
for kind, val in C.BODY:  # nomor gambar/tabel/persamaan menurut urutan penempatan
    if kind == "FIG": fig_no[val] = len(fig_no) + 1
    if kind == "TAB": tab_no[val] = len(tab_no) + 1
    if kind == "EQ": eq_no[val] = len(eq_no) + 1


def esc(s): return html.escape(s, quote=False)


def cite(m):
    keys = [k.strip().lstrip("@") for k in m.group(1).split(",")]
    ns = []
    for k in keys:
        if k not in num:
            order.append(k); num[k] = len(order)
        ns.append(num[k])
    ns = sorted(ns); parts, i = [], 0
    while i < len(ns):
        j = i
        while j + 1 < len(ns) and ns[j + 1] == ns[j] + 1: j += 1
        parts.append(str(ns[i]) if j == i else (f"{ns[i]}, {ns[j]}" if j == i + 1 else f"{ns[i]}–{ns[j]}")); i = j + 1
    return "[" + ", ".join(parts) + "]"


def text(s):
    s = re.sub(r"\[(@[^\]]+)\]", cite, s)
    s = re.sub(r"\{F:(\w+)\}", lambda m: f"Fig. {fig_no[m.group(1)]}", s)
    s = re.sub(r"\{T:(\w+)\}", lambda m: f"Table {tab_no[m.group(1)]}", s)
    return s


def runs(s, base=""):
    s = text(s); out = []
    for tok in re.split(r"(\*[^*]+\*|~[^~]+~|\^[^^]+\^)", s):
        if not tok: continue
        rp = base
        if tok[0] == "*": rp += "<w:i/>"; tok = tok[1:-1]
        elif tok[0] == "~": rp += '<w:vertAlign w:val="subscript"/>'; tok = tok[1:-1]
        elif tok[0] == "^": rp += '<w:vertAlign w:val="superscript"/>'; tok = tok[1:-1]
        out.append(f'<w:r>{"<w:rPr>" + rp + "</w:rPr>" if rp else ""}<w:t xml:space="preserve">{esc(tok)}</w:t></w:r>')
    return "".join(out)


def P(style, s, extra=""):
    return f'<w:p><w:pPr><w:pStyle w:val="{style}"/>{extra}</w:pPr>{runs(s)}</w:p>'


def H(level, s):
    return P("GaEESectionTitle", s, f'<w:numPr><w:ilvl w:val="{level}"/><w:numId w:val="11"/></w:numPr>')


rels_add, rid = [], [100]


def figure(key):
    fn, title, src, alt = C.FIGS[key]
    w, h = Image.open(f"{figdir}/{fn}").size
    cx = 5760000; cy = int(cx * h / w)
    if cy > 7200000: cy = 7200000; cx = int(cy * w / h)
    rid[0] += 1; r = f"rIdImg{rid[0]}"; rels_add.append((r, fn))
    n = rid[0]
    drw = (f'<w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{cx}" cy="{cy}"/>'
           f'<wp:docPr id="{n}" name="Figure {fig_no[key]}" descr="{html.escape(alt)}"/>'
           '<wp:cNvGraphicFramePr><a:graphicFrameLocks xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" noChangeAspect="1"/></wp:cNvGraphicFramePr>'
           '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
           f'<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:nvPicPr><pic:cNvPr id="{n}" name="{fn}" descr="{html.escape(alt)}"/><pic:cNvPicPr/></pic:nvPicPr>'
           f'<pic:blipFill><a:blip r:embed="{r}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
           f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
           '</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r>')
    return (f'<w:p><w:pPr><w:pStyle w:val="GaEEFigure"/><w:keepNext/></w:pPr>{drw}</w:p>'
            + P("GaEEFigureTitle", f"Fig. {fig_no[key]}. {title}", "<w:keepNext/>")
            + P("GaEEFigureSource", f"Source: {src}"))


DBL = "".join(f'<w:{s} w:val="double" w:sz="4" w:space="0" w:color="auto"/>' for s in ("top", "left", "bottom", "right"))


def table(key):
    title, src, widths, head, rows = C.TABLES[key]
    tw = sum(widths)
    grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in widths)

    def row(cells, style, hdr=False):
        tc = "".join(f'<w:tc><w:tcPr><w:tcW w:w="{w}" w:type="dxa"/><w:tcBorders>{DBL}</w:tcBorders></w:tcPr>'
                     f'{P(style, c)}</w:tc>' for w, c in zip(widths, cells))
        return f'<w:tr>{"<w:trPr><w:tblHeader/></w:trPr>" if hdr else ""}{tc}</w:tr>'
    body = row(head, "GaEETableHeader", True) + "".join(row(r, "GaEETableContent") for r in rows)
    tbl = (f'<w:tbl><w:tblPr><w:tblW w:w="{tw}" w:type="dxa"/><w:jc w:val="center"/><w:tblBorders>{DBL}'
           '<w:insideH w:val="double" w:sz="4" w:space="0" w:color="auto"/><w:insideV w:val="double" w:sz="4" w:space="0" w:color="auto"/>'
           f'</w:tblBorders><w:tblLook w:val="01E0"/></w:tblPr><w:tblGrid>{grid}</w:tblGrid>{body}</w:tbl>')
    return P("GaEETableTitle", f"Table {tab_no[key]}. {title}", "<w:keepNext/>") + tbl + P("GaEETableSource", f"Source: {src}")


M = 'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"'


def mr(t, sty=None):
    s = f'<m:rPr><m:sty m:val="{sty}"/></m:rPr>' if sty else ""
    return f'<m:r>{s}<w:rPr><w:rFonts w:ascii="Cambria Math" w:hAnsi="Cambria Math"/></w:rPr><m:t>{esc(t)}</m:t></m:r>'


def msub(base, sub):
    return f"<m:sSub><m:e>{base}</m:e><m:sub>{sub}</m:sub></m:sSub>"


def nary(sub, body):
    return (f'<m:nary><m:naryPr><m:chr m:val="∑"/><m:limLoc m:val="undOvr"/><m:supHide m:val="1"/></m:naryPr>'
            f"<m:sub>{sub}</m:sub><m:sup/><m:e>{body}</m:e></m:nary>")


EQ = {
    "zonal": msub(mr("x̄"), mr("r,b,t")) + mr("=", "p") + "<m:f><m:num>"
             + nary(mr("c∈") + msub(mr("C"), mr("r")), msub(mr("A"), mr("r,c")) + mr("·", "p") + msub(mr("x"), mr("c")))
             + "</m:num><m:den>" + nary(mr("c∈") + msub(mr("C"), mr("r")), msub(mr("A"), mr("r,c"))) + "</m:den></m:f>",
    "score": mr("S") + mr("=", "p") + '<m:nary><m:naryPr><m:chr m:val="∑"/><m:limLoc m:val="undOvr"/></m:naryPr>'
             + "<m:sub>" + mr("i=1") + "</m:sub><m:sup>" + mr("7", "p") + "</m:sup><m:e>"
             + msub(mr("w"), mr("i")) + mr("·", "p") + msub(mr("s"), mr("i")) + "</m:e></m:nary>",
}


def equation(key):
    return (f'<w:p><w:pPr><w:pStyle w:val="GaEEEquation"/></w:pPr><m:oMath {M}>{EQ[key]}</m:oMath>'
            f'<w:r><w:tab/><w:t>({eq_no[key]})</w:t></w:r></w:p>')


# --- dokumen
x = []
au = []
for i, (name, aff) in enumerate(C.AUTHORS):
    if i: au.append('<w:r><w:t xml:space="preserve">, </w:t></w:r>')
    au.append(f'<w:r><w:t>{esc(name)}</w:t></w:r>')
    au.append(f'<w:r><w:rPr><w:rStyle w:val="Odwoanieprzypisudolnego"/></w:rPr><w:footnoteReference w:id="{i + 1}"/></w:r>')
x.append(f'<w:p><w:pPr><w:pStyle w:val="GaEEAuthors"/></w:pPr>{"".join(au)}</w:p>')
x.append(P("GaEETitle", C.TITLE))
x.append(P("GaEEAbstractWord", "Abstract:"))
x.append(P("GaEENormal", C.ABSTRACT))
x.append(f'<w:p><w:pPr><w:pStyle w:val="GaEEKeywords"/></w:pPr><w:r><w:rPr><w:b/></w:rPr><w:t xml:space="preserve">Keywords: </w:t></w:r>{runs(C.KEYWORDS)}</w:p>')
for kind, val in C.BODY:
    x.append({"H1": lambda v: H(0, v), "H2": lambda v: H(1, v), "P": lambda v: P("GaEENormal", v),
              "FIG": figure, "TAB": table, "EQ": equation}[kind](val))
for t, body in C.CLOSING:
    x.append(P("GaEEClosingSectionTitle", t)); x.append(P("GaEENormal", body))
x.append(P("GaEEClosingSectionTitle", "References"))


def ref(k):
    if k in C.MANUAL: return C.MANUAL[k]
    m = REFS[k]
    names = [f"{f} {''.join(p[0] + '.' for p in re.split(r'[ -]', g) if p)}".strip() for f, g in m["authors"]]
    au = ", ".join(names[:6]) + (" et al." if len(names) > 6 else "")
    t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", m["title"]))).strip()
    j = html.unescape(m["journal"])
    if m["type"] == "proceedings-article":
        s = f"{au}: *{t}*. [in:] {j}, {m['year']}" + (f", pp. {m['pages'].replace('-', '–')}" if m.get("pages") else "")
    else:
        s = f"{au}: *{t}*. {j}" + (f", vol. {m['vol']}" if m.get("vol") else "") + (f", no. {m['no']}" if m.get("no") else "")
        s += f", {m['year']}"
        if m.get("pages") and "-" in m["pages"]: s += f", pp. {m['pages'].replace('-', '–')}"
        elif m.get("art") or m.get("pages"): s += f", {m.get('art') or m['pages']}"
    return s + f". https://doi.org/{m['doi']}"


for k in order:
    x.append(f'<w:p><w:pPr><w:pStyle w:val="GaEEReferences"/></w:pPr>{runs(ref(k))}</w:p>')

z = zipfile.ZipFile(tpl)
doc = z.read("word/document.xml").decode("utf-8")
b0 = doc.index("<w:body>") + len("<w:body>")
sect = re.search(r"<w:sectPr[ >].*?</w:sectPr>\s*</w:body>", doc, re.S).group(0)
doc = doc[:b0] + "".join(x) + sect + doc[doc.index("</w:body>") + len("</w:body>"):]

fn = z.read("word/footnotes.xml").decode("utf-8")
for i, (name, aff) in enumerate(C.AUTHORS):
    new = (f'<w:footnote w:id="{i + 1}"><w:p><w:pPr><w:pStyle w:val="GaEEFootnote"/></w:pPr><w:r><w:rPr>'
           f'<w:rStyle w:val="Odwoanieprzypisudolnego"/><w:vertAlign w:val="baseline"/></w:rPr><w:footnoteRef/></w:r>'
           f'<w:r><w:t xml:space="preserve"> {esc(aff)}</w:t></w:r></w:p></w:footnote>')
    fn = re.sub(rf'<w:footnote w:id="{i + 1}">.*?</w:footnote>', new, fn, flags=re.S)
rels = z.read("word/_rels/document.xml.rels").decode("utf-8")
rels = rels.replace("</Relationships>", "".join(
    f'<Relationship Id="{r}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/{f}"/>'
    for r, f in rels_add) + "</Relationships>")
ct = z.read("[Content_Types].xml").decode("utf-8")
if 'Extension="png"' not in ct:
    ct = ct.replace("<Default ", '<Default Extension="png" ContentType="image/png"/><Default ', 1)
core = z.read("docProps/core.xml").decode("utf-8")
core = re.sub(r"<dc:title>.*?</dc:title>|<dc:title/>", f"<dc:title>{esc(C.TITLE)}</dc:title>", core)

zo = zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED)
for it in z.infolist():
    if it.filename == "word/media/image1.wmf": continue
    data = {"word/document.xml": doc, "word/footnotes.xml": fn, "word/_rels/document.xml.rels": rels,
            "[Content_Types].xml": ct, "docProps/core.xml": core}.get(it.filename)
    zo.writestr(it, data.encode("utf-8") if data is not None else z.read(it.filename))
for r, f in rels_add:
    zo.write(f"{figdir}/{f}", f"word/media/{f}")
zo.close()
# hapus relasi ke image1.wmf yang tidak dipakai lagi
import shutil
zz = zipfile.ZipFile(out); tmp = out + ".tmp"; zt = zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED)
for it in zz.infolist():
    d = zz.read(it.filename)
    if it.filename == "word/_rels/document.xml.rels":
        d = re.sub(rb'<Relationship [^>]*Target="media/image1\.wmf"/>', b"", d)
    zt.writestr(it, d)
zt.close(); zz.close(); shutil.move(tmp, out)

plain = re.sub(r"\*|~|\^", "", "".join(text(v) for k, v in C.BODY if k == "P"))
print("referensi:", len(order), "| karakter isi (paragraf):", len(plain))
print("tidak dikutip:", [k for k in REFS if k not in num])
