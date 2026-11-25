"""Metadata CSL-JSON daftar pustaka untuk sitasi Mendeley Cite di naskah.

Rujukan ber-DOI diambil dari Crossref (doi.org, content negotiation CSL-JSON), lalu dibersihkan agar sesuai
bentuk itemData yang disimpan Mendeley Cite. Rujukan tanpa DOI (dokumen BMKG dan dataset COD-AB) disusun dari
teks daftar pustaka di build_skripsi.py. Hasil disimpan di assets/referensi_csl.json, yang dibaca build_skripsi.py
tanpa akses jaringan.

Pemakaian (perlu internet): python csl_referensi.py
"""
import json, pathlib, re, time, urllib.request, uuid

HERE = pathlib.Path(__file__).parent
OUT = HERE / "assets" / "referensi_csl.json"
NS = uuid.UUID("6f1c1d1e-7b8a-4a52-9d0e-2f6c0a5d4b11")  # ruang nama tetap -> id item stabil antar-build

# Koreksi data Crossref yang keliru (diperiksa terhadap daftar pustaka naskah).
FIX_AUTHOR = {"kovacs": {0: {"family": "Kovács", "given": "Dávid D."}}}

MANUAL = {
    "bmkg_sumsel": {
        "type": "report",
        "title": "Buletin Iklim Edisi Desember 2024: Analisis hujan November 2024 dan prediksi hujan Januari, "
                 "Februari, dan Maret 2025 di Sumatera Selatan",
        "author": [{"literal": "Stasiun Klimatologi Kelas I Sumatera Selatan"}],
        "publisher": "Badan Meteorologi, Klimatologi, dan Geofisika", "publisher-place": "Palembang, Indonesia",
        "issued": {"date-parts": [[2024, 12]]},
        "URL": "https://staklim-sumsel.bmkg.go.id/wp-content/uploads/2023/09/BULETIN-BMKG-EDISI-DESEMBER-2024.pdf"},
    "bmkg_kalsel": {
        "type": "report",
        "title": "Peringatan dini cuaca dan iklim Provinsi Kalimantan Selatan periode Dasarian III Maret 2026",
        "author": [{"literal": "Stasiun Klimatologi Kalimantan Selatan"}],
        "publisher": "Badan Meteorologi, Klimatologi, dan Geofisika", "number": "e.T/ME.01.02/073/KBB3/III/2026",
        "issued": {"date-parts": [[2026, 3, 21]]},
        "URL": "https://staklim-kalsel.bmkg.go.id/wp-content/uploads/2026/03/Kalsel-Dasarian-III-Maret-2026-TTE-1_signed.pdf"},
    "perban": {
        "type": "legislation",
        "title": "Peraturan Badan Meteorologi, Klimatologi, dan Geofisika Nomor 9 Tahun 2022 tentang Penyediaan dan "
                 "Penyebarluasan Peringatan Dini Cuaca Ekstrem",
        "author": [{"literal": "Badan Meteorologi, Klimatologi, dan Geofisika"}],
        "container-title": "Berita Negara Republik Indonesia Tahun 2022 Nomor 891",
        "issued": {"date-parts": [[2022]]}},
    "codab": {
        "type": "dataset",
        "title": "Indonesia – Subnational administrative boundaries (COD-AB)",
        "author": [{"literal": "OCHA Field Information Services Section (FISS)"}],
        "publisher": "Humanitarian Data Exchange", "issued": {"date-parts": [[2025]]},
        "URL": "https://data.humdata.org/dataset/cod-ab-idn"},
}


def refs():
    src = (HERE / "build_skripsi.py").read_text(encoding="utf-8")
    ns = {}
    exec(src[src.index("REF = {"):src.index("ORDER = []")], ns)
    return ns["REF"]


def first(v):
    return v[0] if isinstance(v, list) else v


def person(a):
    if "literal" in a:
        return {"literal": a["literal"]}
    return {"family": a["family"], "given": a.get("given", ""), "parse-names": False,
            "dropping-particle": "", "non-dropping-particle": ""}


def clean(key, raw):
    authors = [a for a in raw.get("author", []) if "family" in a]       # buang "penulis" berupa teks afiliasi
    for i, fix in FIX_AUTHOR.get(key, {}).items():
        authors[i] = dict(authors[i], **fix)
    item = {"type": {"proceedings-article": "paper-conference"}.get(raw["type"], raw["type"]),
            "title": first(raw.get("title", "")), "author": [person(a) for a in authors]}
    for f in ("container-title", "container-title-short", "publisher", "volume", "issue", "page", "DOI", "URL"):
        v = first(raw.get(f, ""))
        if v:
            item[f] = v
    if raw.get("ISSN"):
        item["ISSN"] = first(raw["ISSN"])
    if raw.get("article-number"):
        item["number"] = raw["article-number"]
    item["issued"] = {"date-parts": [[raw["issued"]["date-parts"][0][0]]]}
    return item


def main():
    out = {}
    for key, text in refs().items():
        if key in MANUAL:
            item = dict(MANUAL[key])
            item["author"] = [person(a) for a in item["author"]]
        else:
            doi = re.search(r"doi:\s*(10\.\S+?)\.?$", text.strip()).group(1)
            req = urllib.request.Request("https://doi.org/" + doi, headers={
                "Accept": "application/vnd.citationstyles.csl+json", "User-Agent": "skripsi-build/1.0"})
            item = clean(key, json.loads(urllib.request.urlopen(req, timeout=30).read().decode("utf-8")))
            time.sleep(0.2)
        item["id"] = str(uuid.uuid5(NS, item.get("DOI", key)))
        out[key] = {k: item[k] for k in ["type", "id"] + [k for k in item if k not in ("type", "id")]}
        print(key, item["id"])
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(out)} rujukan -> {OUT}")


if __name__ == "__main__":
    main()
