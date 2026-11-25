"""Sitasi dan daftar pustaka berformat Mendeley Cite (add-in Word) untuk naskah yang dibangun skrip.

Bentuknya meniru dokumen yang dibuat Mendeley Cite (naskah/thesis with mendeley.docx):
- setiap sitasi adalah content control (w:sdt) bertag MENDELEY_CITATION_v3_<base64 JSON>; JSON memuat
  itemData CSL tiap rujukan dan teks tampilan ("[1]");
- daftar pustaka adalah satu content control bertag MENDELEY_BIBLIOGRAPHY;
- add-in didaftarkan di word/webextensions/ (webextension1.xml memuat MENDELEY_CITATIONS dan gaya IEEE).
Setelah dibuka di Word, panel Mendeley Cite dapat memperbarui sitasi dan daftar pustaka dari data ini.
Metadata rujukan: assets/referensi_csl.json (dibuat csl_referensi.py).
"""
import base64, html, json, pathlib, time, uuid

HERE = pathlib.Path(__file__).parent
ITEMS = json.loads((HERE / "assets" / "referensi_csl.json").read_text(encoding="utf-8"))
NS = uuid.UUID("0b5d3a52-2f0e-4f7e-9a3c-6c1e8f2b7d40")
STYLE = {"id": "https://www.zotero.org/styles/ieee", "title": "IEEE Reference Guide version 11.29.2023",
         "format": "numeric", "defaultLocale": None, "isLocaleCodeValid": True}
WEBEXT_ID = "{A988B64B-8210-4C03-8AD7-DB4408392722}"


class Registry:
    """Mencatat sitasi dalam urutan kemunculan untuk webextension1.xml."""

    def __init__(self, prefix, items=None):
        self.prefix, self.cites, self.items = prefix, [], items or ITEMS

    def citation(self, keys, text, rpr):
        n = len(self.cites)
        cid = "MENDELEY_CITATION_" + str(uuid.uuid5(NS, f"{self.prefix}/{n}/{','.join(keys)}"))
        items = [{"id": self.items[k]["id"], "itemData": self.items[k], "isTemporary": False} for k in keys]
        obj = {"citationID": cid, "properties": {"noteIndex": 0}, "isEdited": False,
               "manualOverride": {"isManuallyOverridden": False, "citeprocText": text, "manualOverrideText": ""},
               "citationItems": items}
        tag = "MENDELEY_CITATION_v3_" + base64.b64encode(json.dumps(obj, ensure_ascii=False,
                                                                    separators=(",", ":")).encode()).decode()
        self.cites.append({**{k: obj[k] for k in ("citationID", "properties", "isEdited", "manualOverride")},
                           "citationTag": tag, "citationItems": items})
        sid = 300000000 + int(uuid.uuid5(NS, cid).int % 600000000)
        return (f'<w:sdt><w:sdtPr><w:rPr>{rpr}</w:rPr><w:tag w:val="{tag}"/><w:id w:val="{sid}"/></w:sdtPr>'
                f'<w:sdtContent><w:r><w:rPr>{rpr}</w:rPr><w:t>{html.escape(text, quote=False)}</w:t></w:r>'
                f'</w:sdtContent></w:sdt>')

    def webextension_xml(self):
        prop = lambda n, v: f'<we:property name="{n}" value="{html.escape(v, quote=True)}"/>'
        props = [prop("MENDELEY_BIBLIOGRAPHY_IS_DIRTY", "false"),
                 prop("MENDELEY_BIBLIOGRAPHY_LAST_MODIFIED", str(int(time.time() * 1000))),
                 prop("MENDELEY_CITATIONS", json.dumps(self.cites, ensure_ascii=False, separators=(",", ":"))),
                 prop("MENDELEY_CITATIONS_STYLE", json.dumps(STYLE, separators=(",", ":")))]
        return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                '<we:webextension xmlns:we="http://schemas.microsoft.com/office/webextensions/webextension/2010/11" '
                f'id="{WEBEXT_ID}"><we:reference id="wa104382081" version="1.55.1.0" store="en-US" storeType="OMEX"/>'
                '<we:alternateReferences><we:reference id="WA104382081" version="1.55.1.0" store="" storeType="OMEX"/>'
                f'</we:alternateReferences><we:properties>{"".join(props)}</we:properties><we:bindings/><we:snapshot '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/></we:webextension>')


def bibliography(paragraphs_xml, rpr):
    return (f'<w:sdt><w:sdtPr><w:rPr>{rpr}</w:rPr><w:tag w:val="MENDELEY_BIBLIOGRAPHY"/><w:id w:val="1411113486"/>'
            f'</w:sdtPr><w:sdtContent>{paragraphs_xml}</w:sdtContent></w:sdt>')


TASKPANES = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
             '<wetp:taskpanes xmlns:wetp="http://schemas.microsoft.com/office/webextensions/taskpanes/2010/11">'
             '<wetp:taskpane dockstate="right" visibility="0" width="525" row="2"><wetp:webextensionref '
             'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" r:id="rId1"/>'
             '</wetp:taskpane></wetp:taskpanes>')
TASKPANES_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                  '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                  '<Relationship Id="rId1" Type="http://schemas.microsoft.com/office/2011/relationships/webextension" '
                  'Target="webextension1.xml"/></Relationships>')


def package_parts(registry, content_types, root_rels):
    """Bagian paket yang ditambahkan/diubah: {nama: bytes}. Menimpa pendaftaran add-in yang sudah ada."""
    ct = content_types
    for part, typ in (("/word/webextensions/taskpanes.xml", "application/vnd.ms-office.webextensiontaskpanes+xml"),
                      ("/word/webextensions/webextension1.xml", "application/vnd.ms-office.webextension+xml")):
        if part not in ct:
            ct = ct.replace("</Types>", f'<Override PartName="{part}" ContentType="{typ}"/></Types>')
    rr = root_rels
    if "webextensiontaskpanes" not in rr:
        rr = rr.replace("</Relationships>", '<Relationship Id="rIdMendeleyTp" Type="http://schemas.microsoft.com/'
                        'office/2011/relationships/webextensiontaskpanes" Target="word/webextensions/taskpanes.xml"/>'
                        "</Relationships>")
    return {"[Content_Types].xml": ct.encode("utf-8"), "_rels/.rels": rr.encode("utf-8"),
            "word/webextensions/taskpanes.xml": TASKPANES.encode("utf-8"),
            "word/webextensions/_rels/taskpanes.xml.rels": TASKPANES_RELS.encode("utf-8"),
            "word/webextensions/webextension1.xml": registry.webextension_xml().encode("utf-8")}
