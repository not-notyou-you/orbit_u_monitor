"""Unduh PDF semua referensi di file RIS dari berbagai sumber open access.

Sumber (dicoba berurutan, berhenti di PDF valid pertama):
  mdpi        CDN mdpi-res.com (www.mdpi.com memblokir skrip)
  unpaywall   (butuh --email)          europepmc   Europe PMC / PubMed Central
  openalex                             core        (butuh env CORE_API_KEY)
  semantic    Semantic Scholar DOI     doaj
  crossref    link full-text penerbit  zenodo, arxiv, semantic-judul  (lewat judul)
  doi         halaman penerbit -> citation_pdf_url / link OJS
  scholar     Google Scholar (opsional, --scholar; bisa kena CAPTCHA)
  browser     (opsional, --browser) URL yang gagal dibuka ulang di Chromium sungguhan;
              menembus proteksi bot (Cloudflare, 403). CAPTCHA bisa diselesaikan manual.
  europepmc juga mengambil arsip PMC di AWS (pmc-oa-opendata), bebas Cloudflare.
Entri tanpa DOI dicari DOI-nya lewat judul (OpenAlex, lalu Crossref).

Pemakaian:
  python -m pip install requests
  python unduh_pdf.py "referensi_bab1,2,3.ris" --email anda@kampus.ac.id
  python unduh_pdf.py "referensi_bab1,2,3.ris" --email ... --hanya 3,7,12 -v
  python unduh_pdf.py "referensi_bab1,2,3.ris" --email ... --browser   (perlu playwright)

Keluaran (default di folder pdf/ di samping file RIS):
  *.pdf         PDF yang berhasil
  laporan.csv   status per entri + alasan gagal tiap sumber (ditulis per entri)
  unduh.log     log lengkap, termasuk detail tiap request
Jalankan ulang kapan saja: PDF yang sudah ada dan valid dilewati.
"""
import argparse
import base64
import csv
import logging
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError:
    sys.exit("Paket 'requests' belum terpasang. Jalankan: python -m pip install requests")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
MIN_PDF = 10_000            # byte; lebih kecil dari ini hampir pasti bukan artikel
MAX_PDF = 100_000_000       # byte; batas pengaman
TIMEOUT = (10, 60)          # (connect, read) detik

log = logging.getLogger("unduh")


class Gagal(Exception):
    """Alasan gagal yang dicatat di log dan laporan."""


def buat_session():
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "*/*",
                      "Accept-Language": "en-US,en;q=0.9,id;q=0.8"})
    retry = Retry(total=3, backoff_factor=2, status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=("GET", "HEAD"), respect_retry_after_header=True,
                  raise_on_status=False)
    s.mount("http://", HTTPAdapter(max_retries=retry))
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


SES = buat_session()


# ---------------------------------------------------------------- RIS

def baca_ris(path):
    entri, cur = [], {}
    for n, line in enumerate(Path(path).read_text(encoding="utf-8-sig").splitlines(), 1):
        m = re.match(r"^([A-Z][A-Z0-9])  -(?: (.*))?$", line)
        if not m:
            if line.strip():
                log.debug("RIS baris %d diabaikan: %r", n, line[:80])
            continue
        tag, val = m.group(1), (m.group(2) or "").strip()
        if tag == "ER":
            if cur:
                entri.append(cur)
            cur = {}
        elif val:
            cur.setdefault(tag, []).append(val)
    if cur:
        log.warning("Entri terakhir tanpa 'ER' tetap dipakai")
        entri.append(cur)
    return entri


def ambil(e, tag, default=""):
    return (e.get(tag) or [default])[0]


def bersihkan_doi(doi):
    if not doi:
        return None
    doi = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:\s*)", "", doi.strip(), flags=re.I)
    return doi.rstrip(".") or None


# ---------------------------------------------------------------- HTTP

def get_json(nama, url, **kw):
    """GET JSON; None jika gagal. Alasan gagal masuk log, bukan dilempar."""
    try:
        r = SES.get(url, timeout=TIMEOUT, **kw)
    except requests.RequestException as ex:
        log.debug("  [%s] error koneksi: %s", nama, ex.__class__.__name__)
        return None
    if r.status_code == 404:
        log.debug("  [%s] tidak terdaftar (404)", nama)
        return None
    if not r.ok:
        log.debug("  [%s] HTTP %d", nama, r.status_code)
        return None
    try:
        return r.json()
    except ValueError:
        log.debug("  [%s] respons bukan JSON", nama)
        return None


def mirip(a, b):
    norm = lambda s: re.sub(r"[^a-z0-9]", "", (s or "").lower())
    a, b = norm(a), norm(b)
    return bool(a and b) and (a in b or b in a or a[:60] == b[:60])


# ---------------------------------------------------------------- sumber
# Tiap fungsi: (doi, judul, cfg) -> list URL kandidat.

def s_unpaywall(doi, judul, cfg):
    if not cfg.email or not doi:
        return []
    j = get_json("unpaywall", f"https://api.unpaywall.org/v2/{quote(doi)}",
                 params={"email": cfg.email})
    if not j:
        return []
    urls = []
    for loc in [j.get("best_oa_location")] + (j.get("oa_locations") or []):
        if loc:
            urls += [loc.get("url_for_pdf"), loc.get("url")]
    return urls


def s_openalex(doi, judul, cfg):
    if not doi:
        return []
    j = get_json("openalex", f"https://api.openalex.org/works/doi:{doi}",
                 params={"mailto": cfg.email} if cfg.email else None)
    if not j:
        return []
    urls = [(j.get("open_access") or {}).get("oa_url")]
    for loc in [j.get("best_oa_location"), j.get("primary_location")] + (j.get("locations") or []):
        if loc:
            urls.append(loc.get("pdf_url"))
    return urls


def s_semantic(doi, judul, cfg):
    if not doi:
        return []
    j = get_json("semantic", f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}",
                 params={"fields": "openAccessPdf,externalIds"})
    if not j:
        return []
    urls = [(j.get("openAccessPdf") or {}).get("url")]
    arx = (j.get("externalIds") or {}).get("ArXiv")
    if arx:
        urls.append(f"https://arxiv.org/pdf/{arx}")
    return urls


def s_crossref(doi, judul, cfg):
    if not doi:
        return []
    j = get_json("crossref", f"https://api.crossref.org/works/{quote(doi)}")
    links = ((j or {}).get("message") or {}).get("link") or []
    return [ln.get("URL") for ln in links
            if "pdf" in (ln.get("content-type") or "")
            or ln.get("intended-application") == "text-mining"]


def s_sciencedirect(doi, judul, cfg):
    """Elsevier: PII dari Crossref -> URL PDF ScienceDirect (terbuka bila OA / akses kampus;
    biasanya perlu --browser karena Cloudflare)."""
    if not (doi or "").startswith("10.1016/"):
        return []
    j = get_json("sciencedirect", f"https://api.crossref.org/works/{quote(doi)}")
    for ln in ((j or {}).get("message") or {}).get("link") or []:
        m = re.search(r"PII:(S[0-9X]+)", ln.get("URL") or "")
        if m:
            return [f"https://www.sciencedirect.com/science/article/pii/{m.group(1)}"
                    "/pdfft?isDTMRedir=true&download=true"]
    return []


def s_mdpi(doi, judul, cfg):
    """MDPI memblokir www.mdpi.com untuk skrip (403), tapi CDN mdpi-res.com tidak.
    DOI 10.3390/rs17081368 -> remotesensing-17-01368.pdf (vol 17, issue 08, artikel 1368)."""
    m = re.match(r"10\.3390/([a-z]+)(\d{2})(\d{2})(\d+)$", doi or "", re.I)
    if not m:
        return []
    j = get_json("mdpi", f"https://api.crossref.org/works/{quote(doi)}")
    jurnal = ambil((j or {}).get("message") or {}, "container-title")
    if not jurnal:
        return []
    slug = re.sub(r"[^a-z0-9]", "", jurnal.lower())
    nama = f"{slug}-{int(m.group(2))}-{int(m.group(4)):05d}"
    return [f"https://mdpi-res.com/d_attachment/{slug}/{nama}/article_deploy/{nama}.pdf"]


def pmc_s3(pmcid):
    """Arsip open access PMC di AWS (tanpa Cloudflare, beda dengan pmc.ncbi.nlm.nih.gov)."""
    try:
        r = SES.get("https://pmc-oa-opendata.s3.amazonaws.com/", timeout=TIMEOUT,
                    params={"list-type": "2", "prefix": f"{pmcid}."})
    except requests.RequestException as ex:
        log.debug("  [pmc-s3] error koneksi: %s", ex.__class__.__name__)
        return []
    pdfs = re.findall(r"<Key>([^<]+\.pdf)</Key>", r.text)
    utama = [k for k in pdfs if re.fullmatch(rf"{pmcid}\.\d+/{pmcid}\.\d+\.pdf", k)] or pdfs
    utama.sort(key=lambda k: int(re.search(r"\.(\d+)/", k).group(1)), reverse=True)
    return [f"https://pmc-oa-opendata.s3.amazonaws.com/{k}" for k in utama[:1]]


def s_europepmc(doi, judul, cfg):
    if not doi:
        return []
    j = get_json("europepmc", "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
                 params={"query": f'DOI:"{doi}"', "format": "json", "resultType": "core"})
    urls = []
    for r in ((j or {}).get("resultList") or {}).get("result", []):
        if r.get("pmcid"):
            urls += pmc_s3(r["pmcid"])
            urls.append(f"https://europepmc.org/articles/{r['pmcid']}?pdf=render")
        for ft in (r.get("fullTextUrlList") or {}).get("fullTextUrl", []):
            if ft.get("documentStyle") == "pdf" and ft.get("availabilityCode") in ("OA", "F"):
                urls.append(ft.get("url"))
    return urls


def s_core(doi, judul, cfg):
    key = os.environ.get("CORE_API_KEY")
    if not key:
        return []
    q = f'doi:"{doi}"' if doi else f'title:"{judul}"'
    j = get_json("core", "https://api.core.ac.uk/v3/search/works",
                 params={"q": q, "limit": 5}, headers={"Authorization": f"Bearer {key}"})
    urls = []
    for r in (j or {}).get("results", []):
        if doi or mirip(judul, r.get("title")):
            urls += [r.get("downloadUrl")] + (r.get("sourceFulltextUrls") or [])
    return urls


def s_doaj(doi, judul, cfg):
    if not doi:
        return []
    j = get_json("doaj", f"https://doaj.org/api/search/articles/doi:{quote(doi)}")
    return [ln.get("url") for r in (j or {}).get("results", [])
            for ln in (r.get("bibjson") or {}).get("link", [])]


def s_zenodo(doi, judul, cfg):
    if not judul:
        return []
    j = get_json("zenodo", "https://zenodo.org/api/records",
                 params={"q": f'title:"{judul}"', "size": 3})
    urls = []
    for r in ((j or {}).get("hits") or {}).get("hits", []):
        if mirip(judul, (r.get("metadata") or {}).get("title")):
            urls += [f["links"]["self"] for f in r.get("files", [])
                     if f.get("key", "").lower().endswith(".pdf")]
    return urls


def s_arxiv(doi, judul, cfg):
    if not judul:
        return []
    try:
        r = SES.get("https://export.arxiv.org/api/query", timeout=TIMEOUT,
                    params={"search_query": f'ti:"{judul}"', "max_results": 3})
    except requests.RequestException as ex:
        log.debug("  [arxiv] error koneksi: %s", ex.__class__.__name__)
        return []
    urls = []
    for blok in re.findall(r"<entry>(.*?)</entry>", r.text, re.S):
        t = re.search(r"<title>(.*?)</title>", blok, re.S)
        i = re.search(r"<id>https?://arxiv.org/abs/(.*?)</id>", blok)
        if t and i and mirip(judul, t.group(1)):
            urls.append(f"https://arxiv.org/pdf/{i.group(1)}")
    return urls


def s_semantic_judul(doi, judul, cfg):
    if not judul:
        return []
    j = get_json("semantic-judul", "https://api.semanticscholar.org/graph/v1/paper/search",
                 params={"query": judul, "limit": 3, "fields": "title,openAccessPdf"})
    return [(r.get("openAccessPdf") or {}).get("url")
            for r in (j or {}).get("data", []) if mirip(judul, r.get("title"))]


def s_doi(doi, judul, cfg):
    return [f"https://doi.org/{doi}"] if doi else []


def s_scholar(doi, judul, cfg):
    if not cfg.scholar or not judul:
        return []
    time.sleep(5)  # Google cepat memblokir request beruntun
    try:
        r = SES.get("https://scholar.google.com/scholar", timeout=TIMEOUT,
                    params={"q": f'"{judul}"', "hl": "en"})
    except requests.RequestException as ex:
        log.debug("  [scholar] error koneksi: %s", ex.__class__.__name__)
        return []
    if r.status_code == 429 or "captcha" in r.text.lower() or "unusual traffic" in r.text:
        log.warning("  [scholar] diblokir/CAPTCHA, Google Scholar dimatikan untuk sisa run")
        cfg.scholar = False
        return []
    return re.findall(r'<div class="gs_or_ggsm"[^>]*>\s*<a href="([^"]+)"', r.text)[:3]


SUMBER = [
    ("mdpi", s_mdpi), ("unpaywall", s_unpaywall), ("openalex", s_openalex), ("semantic", s_semantic),
    ("crossref", s_crossref), ("sciencedirect", s_sciencedirect), ("europepmc", s_europepmc), ("core", s_core),
    ("doaj", s_doaj), ("zenodo", s_zenodo), ("arxiv", s_arxiv),
    ("semantic-judul", s_semantic_judul), ("doi", s_doi), ("scholar", s_scholar),
]


def cari_doi(judul, cfg):
    j = get_json("openalex-cari", "https://api.openalex.org/works",
                 params={"search": judul, "per-page": 3, "mailto": cfg.email or None})
    for r in (j or {}).get("results", []):
        if r.get("doi") and mirip(judul, r.get("title")):
            return bersihkan_doi(r["doi"]), "openalex"
    j = get_json("crossref-cari", "https://api.crossref.org/works",
                 params={"query.title": judul, "rows": 3})
    for it in ((j or {}).get("message") or {}).get("items", []):
        if mirip(judul, ambil(it, "title")):
            return bersihkan_doi(it.get("DOI")), "crossref"
    return None, None


# ---------------------------------------------------------------- unduh

def pdf_valid(path):
    try:
        if path.stat().st_size < MIN_PDF:
            return False
        with open(path, "rb") as f:
            head = f.read(1024)
            f.seek(-2048, os.SEEK_END)
            tail = f.read()
        return b"%PDF-" in head and b"%%EOF" in tail
    except OSError:
        return False


def cari_link_pdf(html, base):
    pola = [r'<meta[^>]+name=["\']citation_pdf_url["\'][^>]+content=["\']([^"\']+)',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']citation_pdf_url',
            r'href=["\']([^"\']*/article/download/[^"\']+)["\']',     # OJS
            r'href=["\']([^"\']*/article/view/\d+/\d+)["\']',         # OJS galley
            r'href=["\']([^"\']+\.pdf(?:\?[^"\']*)?)["\']']
    hasil = []
    for p in pola:
        for m in re.findall(p, html, re.I)[:3]:
            u = urljoin(base, m.replace("&amp;", "&"))
            if u not in hasil:
                hasil.append(u)
    return hasil[:6]


def unduh(url, tujuan, kedalaman=0):
    """Simpan PDF ke tujuan (atomik lewat .part). Lempar Gagal berisi alasannya."""
    try:
        r = SES.get(url, timeout=TIMEOUT, stream=True, allow_redirects=True,
                    headers={"Referer": f"{urlparse(url).scheme}://{urlparse(url).netloc}/"})
    except requests.exceptions.Timeout:
        raise Gagal("timeout")
    except requests.exceptions.SSLError:
        raise Gagal("SSL error")
    except requests.RequestException as ex:
        raise Gagal(f"koneksi: {ex.__class__.__name__}")
    with r:
        if r.status_code in (401, 403):
            raise Gagal(f"HTTP {r.status_code} (paywall/blokir bot)")
        if not r.ok:
            raise Gagal(f"HTTP {r.status_code}")
        ctype = r.headers.get("Content-Type", "").lower()
        it = r.iter_content(64 * 1024)
        try:
            awal = next(it, b"")
        except requests.RequestException as ex:
            raise Gagal(f"putus saat baca: {ex.__class__.__name__}")

        if awal.lstrip()[:5] == b"%PDF-":
            part = tujuan.with_suffix(".part")
            ukuran = 0
            try:
                with open(part, "wb") as f:
                    f.write(awal)
                    ukuran = len(awal)
                    for chunk in it:
                        f.write(chunk)
                        ukuran += len(chunk)
                        if ukuran > MAX_PDF:
                            raise Gagal("file terlalu besar")
            except requests.RequestException as ex:
                part.unlink(missing_ok=True)
                raise Gagal(f"putus saat unduh: {ex.__class__.__name__}")
            except Gagal:
                part.unlink(missing_ok=True)
                raise
            if not pdf_valid(part):
                part.unlink(missing_ok=True)
                raise Gagal(f"PDF rusak/terpotong ({ukuran} byte)")
            os.replace(part, tujuan)
            return r.url, ukuran

        if "html" not in ctype and b"<html" not in awal[:2048].lower():
            raise Gagal(f"bukan PDF ({ctype or 'tanpa Content-Type'})")
        if kedalaman >= 1:
            raise Gagal("halaman HTML, bukan PDF")
        html = (awal + b"".join(c for _, c in zip(range(30), it))).decode(r.encoding or "utf-8", "replace")
        if "captcha" in html.lower() or "cf-challenge" in html or "Just a moment" in html:
            raise Gagal("diblokir CAPTCHA/Cloudflare")
        links = cari_link_pdf(html, r.url)
        if not links:
            raise Gagal("halaman HTML tanpa link PDF")
        alasan = []
        for u in links:
            try:
                return unduh(u, tujuan, kedalaman + 1)
            except Gagal as g:
                log.debug("      link di halaman %s -> %s", u, g)
                alasan.append(str(g))
        raise Gagal(f"{len(links)} link PDF di halaman gagal ({alasan[-1]})")


def simpan_pdf(data, tujuan):
    part = tujuan.with_suffix(".part")
    part.write_bytes(data)
    if not pdf_valid(part):
        part.unlink(missing_ok=True)
        raise Gagal(f"PDF rusak/terpotong ({len(data)} byte)")
    os.replace(part, tujuan)
    return len(data)


def buka_browser(cfg):
    """(Re)launch Chromium. Profil tetap di pdf/.browser: cookie lolos-Cloudflare dipakai ulang."""
    if cfg.ctx:
        try:
            cfg.ctx.close()
        except Exception:
            pass
    cfg.ctx = cfg.pw.chromium.launch_persistent_context(
        str(cfg.profil), headless=False, accept_downloads=True,
        args=["--disable-blink-features=AutomationControlled"])
    # Tab penjaga: menutup tab terakhir menutup seluruh Chromium (dan cookie-nya).
    cfg.penjaga = cfg.ctx.pages[0] if cfg.ctx.pages else cfg.ctx.new_page()


def unduh_browser(url, tujuan, cfg):
    """Buka URL di Chromium sungguhan (lolos sebagian besar proteksi bot/Cloudflare).
    Jendela browser terlihat; kalau muncul CAPTCHA, selesaikan manual dalam --tunggu detik."""
    try:
        page = cfg.ctx.new_page()
    except Exception:
        log.warning("      jendela browser tertutup/crash, membuka ulang...")
        buka_browser(cfg)
        page = cfg.ctx.new_page()
    pdf = {}

    def tangkap(resp):
        if not pdf and "application/pdf" in resp.headers.get("content-type", "").lower():
            try:
                pdf.update(data=resp.body(), url=resp.url)
            except Exception:
                pass

    def selesai():
        """Tangkapan dari penampil PDF Chrome kadang cuma stub kecil; ambil ulang pakai cookie browser."""
        if len(pdf["data"]) < MIN_PDF:
            # fetch() dari dalam halaman: lewat jaringan browser asli, lolos Cloudflare
            try:
                b64 = page.evaluate("""async u => {
                    const r = await fetch(u, {credentials: 'include'});
                    const b = new Uint8Array(await r.arrayBuffer());
                    let s = ''; for (let i = 0; i < b.length; i += 32768)
                        s += String.fromCharCode.apply(null, b.subarray(i, i + 32768));
                    return btoa(s);
                }""", pdf["url"])
                data = base64.b64decode(b64)
                if data[:5] == b"%PDF-":
                    pdf["data"] = data
            except Exception as ex:
                log.debug("      fetch dalam halaman gagal: %s", ex)
            if len(pdf["data"]) < MIN_PDF:
                try:
                    r = cfg.ctx.request.get(pdf["url"], timeout=60_000)
                    if r.ok and r.body()[:5] == b"%PDF-":
                        pdf["data"] = r.body()
                except Exception:
                    pass
        return pdf["url"], simpan_pdf(pdf["data"], tujuan)

    def unduhan(dl):
        tmp = tujuan.with_suffix(".dl")
        try:
            dl.save_as(tmp)
            data = tmp.read_bytes()
            if data[:5] == b"%PDF-":
                pdf.update(data=data, url=dl.url)
        except Exception:
            pass
        finally:
            tmp.unlink(missing_ok=True)

    def buka(u):
        try:
            page.goto(u, wait_until="domcontentloaded", timeout=60_000)
        except Exception as ex:
            if "Download is starting" not in str(ex) and "net::ERR_ABORTED" not in str(ex):
                raise

    def tunggu_pdf(detik):
        for _ in range(int(detik * 2)):
            if pdf:
                return True
            page.wait_for_timeout(500)
        return bool(pdf)

    def kena_tantangan():
        try:
            return bool(re.search(r"just a moment|captcha|verify you are human|attention required",
                                  page.title() + " " + page.inner_text("body")[:3000], re.I))
        except Exception:
            return False

    page.on("response", tangkap)
    page.on("download", unduhan)
    try:
        buka(url)
        if tunggu_pdf(3):
            return selesai()
        if kena_tantangan():
            log.info("      >>> CAPTCHA di browser! Selesaikan di jendela Chromium "
                     "(menunggu s/d %d detik)", cfg.tunggu)
            try:
                page.bring_to_front()
                import winsound
                for _ in range(3):
                    winsound.Beep(1000, 300)
            except Exception:
                print("\a", end="", flush=True)
            for _ in range(cfg.tunggu):
                if pdf or not kena_tantangan():
                    break
                page.wait_for_timeout(1000)
            if tunggu_pdf(3):
                return selesai()
            if kena_tantangan():
                raise Gagal("browser: CAPTCHA tidak terselesaikan")
        try:
            page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:
            pass
        links = page.evaluate(r"""() => {
            const m = document.querySelector('meta[name=citation_pdf_url]');
            const a = [...document.querySelectorAll('a[href]')].map(x => x.href).filter(h =>
              /\.pdf($|\?)|\/article\/download\/|\/pdfft|\/doi\/pdf\/|\/epdf\/|stamp\.jsp|\/article\/pdf/i.test(h));
            const dom = h => { try { return new URL(h).hostname.split('.').slice(-2).join('.'); } catch (e) { return ''; } };
            const sini = dom(location.href);
            const b = a.filter(h => dom(h) === sini);
            return [...new Set([m && m.content].concat(b).filter(Boolean))].slice(0, 6);
        }""")
        log.debug("      link PDF di halaman: %s", links)
        for ln in links:
            # pakai cookie browser (sudah lolos tantangan) untuk ambil langsung
            try:
                r = cfg.ctx.request.get(ln, timeout=60_000)
                body = r.body() if r.ok else b""
            except Exception:
                body = b""
            if body[:5] == b"%PDF-":
                pdf.update(data=body, url=ln)
                break
            buka(ln)
            if tunggu_pdf(8):
                break
        if not pdf and not tunggu_pdf(10):  # redirect PDF lambat (mis. ScienceDirect pdfft)
            raise Gagal("browser: tidak menemukan PDF di halaman")
        return selesai()
    except Gagal:
        raise
    except Exception as ex:
        raise Gagal(f"browser: {ex.__class__.__name__}: {str(ex).splitlines()[0][:80]}")
    finally:
        page.close()


def proses(no, e, cfg, out):
    judul = ambil(e, "TI")
    doi = bersihkan_doi(ambil(e, "DO"))
    tujuan = out / nama_file(e, no)
    hasil = {"no": no, "judul": judul, "doi": doi or "", "status": "", "sumber": "",
             "url": "", "file": tujuan.name, "percobaan": ""}

    if tujuan.exists():
        if pdf_valid(tujuan):
            log.info("  sudah ada, dilewati")
            hasil["status"] = "sudah ada"
            return hasil
        log.warning("  file lama rusak, diunduh ulang")
        tujuan.unlink()

    if not doi:
        doi, dari = cari_doi(judul, cfg)
        if doi:
            log.info("  DOI tidak ada di RIS, ditemukan lewat %s: %s", dari, doi)
            hasil["doi"] = f"{doi} (dari judul)"
        else:
            log.info("  DOI tidak ada di RIS dan tidak ketemu lewat judul; lanjut cari lewat judul")

    dicoba, catatan = {}, []   # dict = set yang menjaga urutan
    for nama, fn in SUMBER:
        try:
            urls = [u for u in dict.fromkeys(fn(doi, judul, cfg)) if u and u not in dicoba]
        except Exception as ex:  # satu sumber error tidak boleh menghentikan entri
            log.debug("  [%s] error tak terduga: %r", nama, ex)
            catatan.append(f"{nama}: error {ex.__class__.__name__}")
            continue
        if not urls:
            log.debug("  [%s] tidak ada kandidat", nama)
            continue
        for u in urls:
            dicoba[u] = None
            try:
                url_akhir, ukuran = unduh(u, tujuan)
            except Gagal as g:
                log.info("  [%-14s] gagal: %s  <%s>", nama, g, u)
                catatan.append(f"{nama}: {g}")
                time.sleep(cfg.jeda)
                continue
            log.info("  [%-14s] OK %.1f MB  <%s>", nama, ukuran / 1e6, url_akhir)
            hasil.update(status="ok", sumber=nama, url=url_akhir)
            hasil["percobaan"] = " | ".join(catatan)
            return hasil

    if cfg.browser and dicoba:
        log.info("  mencoba ulang lewat browser (%d URL)...", len(dicoba))
        for u in dicoba:
            try:
                url_akhir, ukuran = unduh_browser(u, tujuan, cfg)
            except Gagal as g:
                log.info("  [%-14s] gagal: %s  <%s>", "browser", g, u)
                catatan.append(f"browser: {g}")
                continue
            log.info("  [%-14s] OK %.1f MB  <%s>", "browser", ukuran / 1e6, url_akhir)
            hasil.update(status="ok", sumber="browser", url=url_akhir)
            hasil["percobaan"] = " | ".join(catatan)
            return hasil

    hasil["status"] = "gagal" if dicoba else "tidak ada sumber OA"
    hasil["percobaan"] = " | ".join(catatan)
    log.info("  -> %s (%d URL dicoba)", hasil["status"].upper(), len(dicoba))
    return hasil


def nama_file(e, no):
    au = ambil(e, "AU", "anon").split(",")[0]
    s = f"{no:02d}_{au}_{ambil(e, 'PY', 'nd')}_{ambil(e, 'TI')}"
    s = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", s)
    return re.sub(r"\s+", "_", s).strip("._")[:120] + ".pdf"


# ---------------------------------------------------------------- main

def atur_log(out, verbose):
    log.setLevel(logging.DEBUG)
    con = logging.StreamHandler(sys.stdout)
    con.setLevel(logging.DEBUG if verbose else logging.INFO)
    con.setFormatter(logging.Formatter("%(message)s"))
    fil = logging.FileHandler(out / "unduh.log", encoding="utf-8")
    fil.setLevel(logging.DEBUG)
    fil.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s"))
    log.addHandler(con)
    log.addHandler(fil)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("ris", help="file .ris")
    ap.add_argument("--email", default="", help="email untuk Unpaywall/OpenAlex (disarankan)")
    ap.add_argument("--out", help="folder hasil (default: pdf/ di samping file RIS)")
    ap.add_argument("--scholar", action="store_true", help="aktifkan Google Scholar sebagai cadangan")
    ap.add_argument("--browser", action="store_true",
                    help="entri yang gagal dicoba ulang di Chromium sungguhan (butuh playwright)")
    ap.add_argument("--tunggu", type=int, default=60,
                    help="detik menunggu CAPTCHA diselesaikan manual di mode --browser")
    ap.add_argument("--hanya", help="nomor entri saja, mis. 3,7,12")
    ap.add_argument("--jeda", type=float, default=1.0, help="jeda antar request unduh (detik)")
    ap.add_argument("-v", "--verbose", action="store_true", help="tampilkan detail tiap sumber")
    cfg = ap.parse_args()

    ris = Path(cfg.ris)
    if not ris.is_file():
        sys.exit(f"File RIS tidak ditemukan: {ris.resolve()}")
    out = Path(cfg.out) if cfg.out else ris.resolve().parent / "pdf"
    out.mkdir(parents=True, exist_ok=True)
    atur_log(out, cfg.verbose)

    entri = baca_ris(ris)
    pilih = {int(x) for x in cfg.hanya.split(",")} if cfg.hanya else None
    log.info("RIS: %s | %d entri (%d ber-DOI) | output: %s", ris.name, len(entri),
             sum(1 for e in entri if e.get("DO")), out)
    cfg.ctx = pw = None
    if cfg.browser:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            sys.exit("Mode --browser butuh Playwright:\n"
                     "  python -m pip install playwright\n  python -m playwright install chromium")
        cfg.pw = pw = sync_playwright().start()
        cfg.profil = out / ".browser"
        buka_browser(cfg)
    log.info("Unpaywall: %s | CORE: %s | Scholar: %s | Browser: %s",
             "aktif" if cfg.email else "MATI (isi --email)",
             "aktif" if os.environ.get("CORE_API_KEY") else "mati (tanpa CORE_API_KEY)",
             "aktif" if cfg.scholar else "mati", "aktif" if cfg.browser else "mati")

    kolom = ["no", "judul", "doi", "status", "sumber", "url", "file", "percobaan"]
    lap_path = out / "laporan.csv"
    rekap, mulai = [], time.time()
    try:
        with open(lap_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=kolom)
            w.writeheader()
            for no, e in enumerate(entri, 1):
                if pilih and no not in pilih:
                    continue
                log.info("\n[%d/%d] %s", no, len(entri), ambil(e, "TI")[:90])
                try:
                    h = proses(no, e, cfg, out)
                except Exception as ex:
                    log.exception("  error tak terduga, entri dilewati")
                    h = {"no": no, "judul": ambil(e, "TI"), "doi": ambil(e, "DO"),
                         "status": "error", "percobaan": repr(ex)}
                w.writerow(h)
                f.flush()
                rekap.append(h)
    except KeyboardInterrupt:
        log.warning("\nDihentikan pengguna. Laporan sampai entri terakhir tetap tersimpan.")
    except PermissionError:
        sys.exit(f"Tidak bisa menulis {lap_path} — tutup dulu di Excel lalu jalankan ulang.")
    finally:
        if cfg.ctx:
            try:
                cfg.ctx.close()
            except Exception:
                pass
            pw.stop()

    hitung = {}
    for h in rekap:
        hitung[h["status"]] = hitung.get(h["status"], 0) + 1
    log.info("\n=== Selesai dalam %.0f detik ===", time.time() - mulai)
    for k, v in sorted(hitung.items()):
        log.info("  %-20s %d", k, v)
    gagal = [h for h in rekap if h["status"] not in ("ok", "sudah ada")]
    if gagal:
        log.info("\nPerlu diunduh manual (akses kampus / minta ke penulis):")
        for h in gagal:
            log.info("  %02d  %s  %s", h["no"], h.get("doi") or "-", h["judul"][:70])
    log.info("\nLaporan: %s\nLog    : %s", lap_path, out / "unduh.log")


if __name__ == "__main__":
    main()
