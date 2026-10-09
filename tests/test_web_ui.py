"""Uji statis + smoke UI Tahap 4 (INTERFACE.md §2, §5; DESIGN.md).

Tidak menjalankan browser (lihat tests/ui/screenshots.py untuk itu). Yang diuji:
* setiap tujuan dan tab router (js/app.js) punya fragmen pages/*.html dan skrip
  js/*.js, dan keduanya tersaji lewat FastAPI;
* susunan halaman = rancangan pemilik proyek (M56): Beranda, 3D AOI, Citra,
  Forecast (dulu Diagram, M61), Kejadian, Data, Laporan, Sistem;
* hash susunan lama (M53 dan sebelumnya) masih dipetakan ALIASES;
* setiap kode error yang dilempar API punya terjemahan Indonesia di js/ui.js (M21);
* fragmen tidak memuat border-radius / blur / emoji (DESIGN.md §2, §6, §8);
  tema non-bawaan di css/tema/ dikecualikan tetapi wajib tercakup selektor
  temanya sendiri, dan Orbital 95 tetap bawaan (M57);
* /, /app, /masuk, /daftar tersaji; /kondisi dan /relief dialihkan; tidak ada
  token di localStorage (INTERFACE §6).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"

# Halaman entry di luar aplikasi: Masuk dan Daftar (INTERFACE §2 halaman 0 dan -0).
PUBLIC_PAGES = {"/masuk": "login", "/daftar": "register"}
# Delapan halaman rancangan pemilik proyek (INTERFACE §2, M56).
DESTINATIONS = {"beranda", "aoi-3d", "citra", "forecast", "kejadian", "data", "laporan", "sistem"}
# Hash susunan lama yang harus tetap hidup lewat ALIASES (M53 dan sebelumnya).
LEGACY_HASHES = {"diagram", "kondisi", "kondisi/citra", "kondisi/kecamatan", "kondisi/relief", "riwayat",
                 "riwayat/grafik", "riwayat/laporan", "pengaturan", "pengaturan/akses", "akun",
                 "pantauan", "hari-ini", "statistik", "analitik", "katalog", "buat-dataset", "admin"}

APP_JS = (WEB / "js" / "app.js").read_text(encoding="utf-8")


def destinations() -> set[str]:
    """Hash tujuan utama: `hash: 'x'` yang diikuti `title:` pada baris yang sama."""
    return set(re.findall(r"hash: '([\w-]+)', (?:alias|title|file)", APP_JS))


def page_files() -> set[str]:
    """Setiap `file: 'x'` di ROUTES — baik pada tujuan maupun pada tabnya."""
    return set(re.findall(r"file: '([\w-]+)'", APP_JS))


def aliases() -> dict[str, str]:
    block = APP_JS.split("const ALIASES = {")[1].split("};")[0]
    return dict(re.findall(r"'([\w/-]+)': '([\w/-]+)'", block))


def test_router_has_all_interface_destinations():
    assert destinations() == DESTINATIONS


def test_legacy_hashes_still_resolve():
    """Tautan dan bookmark susunan lama tidak boleh mati (M53)."""
    al = aliases()
    assert LEGACY_HASHES <= set(al), sorted(LEGACY_HASHES - set(al))
    for old, target in al.items():
        dest = target.split("/")[0]
        assert dest in DESTINATIONS, f"{old} → {target}"


@pytest.mark.parametrize("file", sorted(page_files() | {"login", "register"}))
def test_page_fragment_and_script_exist(file):
    assert (WEB / "pages" / f"{file}.html").is_file()
    js = (WEB / "js" / f"{file}.js").read_text(encoding="utf-8")
    assert f"Pages['{file}']" in js


def test_every_destination_has_a_lede():
    """Tiap tujuan wajib punya satu baris instruksi; tujuan bertab satu per tab (M53)."""
    assert APP_JS.count("lede: '") >= len(DESTINATIONS)
    for dest in DESTINATIONS:
        # Wilayah teks milik tujuan ini: sampai `hash:` berikutnya (tab memakai `key:`).
        block = APP_JS.split(f"hash: '{dest}'")[1].split("hash: '")[0]
        assert "lede: '" in block, dest


def test_error_codes_translated():
    """Setiap code=... yang dipakai API punya pesan Indonesia (INTERFACE §5)."""
    used: set[str] = set()
    for p in list((ROOT / "api").rglob("*.py")):
        used |= set(re.findall(r'"([A-Z][A-Z_]{3,})"\)', p.read_text(encoding="utf-8")))
        used |= set(re.findall(r'code="([A-Z][A-Z_]+)"', p.read_text(encoding="utf-8")))
        used |= set(re.findall(r', "([A-Z][A-Z_]+_[A-Z_]+)"[,)]', p.read_text(encoding="utf-8")))
    ui = (WEB / "js" / "ui.js").read_text(encoding="utf-8")
    translated = set(re.findall(r"^\s+([A-Z][A-Z_]+): '", ui, re.M))
    interface = (ROOT / "DOCS" / "INTERFACE.md").read_text(encoding="utf-8")
    documented = set(re.findall(r"`([A-Z][A-Z_]{3,})`", interface.split("Kode spesifik:")[1].split("| HTTP")[0]))
    missing_doc = documented - translated
    assert not missing_doc, f"kode di INTERFACE §5 tanpa terjemahan: {sorted(missing_doc)}"
    # Kode dari api/ yang tampak seperti kode error (bukan nama tabel/kolom).
    errorish = {c for c in used if any(c.endswith(s) for s in ("_FORBIDDEN", "_REQUIRED", "_TAKEN", "_INVALID", "_EXPIRED",
                                                                 "_REVOKED", "_LOCKED", "_RANGE", "_NOT_FOUND", "_MISSING"))}
    assert not (errorish - translated), sorted(errorish - translated)


def test_fragments_follow_design_rules():
    bad = []
    emoji = re.compile("[\U0001F300-\U0001FAFF☀-⛿✀-➿]")
    for p in list((WEB / "pages").glob("*.html")) + list((WEB / "css").glob("*.css")):
        t = p.read_text(encoding="utf-8")
        if re.search(r"border-radius:\s*(?!0\b|0;|0px)[\d.]+", t):
            bad.append(f"{p.name}: border-radius")
        if re.search(r"blur\(", t) or re.search(r"box-shadow:[^;]*\d+px\s+\d+px\s+[1-9]\d*px", t):
            bad.append(f"{p.name}: blur")
        if p.suffix == ".html" and emoji.search(t.replace("⚠", "")):
            bad.append(f"{p.name}: emoji")
    assert not bad, bad


THEME_JS = (WEB / "js" / "theme.js").read_text(encoding="utf-8")
THEMES = {"o95", "mint", "pasir", "piksel"}
ENTRY_HTML = ("app.html", "masuk.html", "daftar.html")


def _selectors(css: str) -> list[str]:
    """Selektor tingkat atas tiap blok aturan; isi @media/@keyframes ikut diurai."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    css = re.sub(r"@keyframes[^{]+\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", "", css)
    css = re.sub(r"@media[^{]+\{", "", css)
    return [s.strip() for s in re.findall(r"([^{}]+)\{", css) if s.strip()]


def test_themes_listed_with_orbital95_default():
    """Empat tema (M57); Orbital 95 tetap bawaan bila belum ada pilihan."""
    assert set(re.findall(r"\{ key: '([\w-]+)'", THEME_JS)) == THEMES
    assert "const DEFAULT = 'o95';" in THEME_JS
    for key in THEMES - {"o95"}:
        assert (WEB / "css" / "tema" / f"{key}.css").is_file(), key


def test_theme_css_is_scoped():
    """Aturan siku Orbital 95 (test_fragments_follow_design_rules) hanya berlaku
    untuk css/*.css. Tema lain di css/tema/ boleh membulat dan memakai blur, asal
    setiap selektornya tercakup tema itu — jadi tidak pernah bocor ke Orbital 95."""
    tema = WEB / "css" / "tema"
    scopes = {"umum.css": "html.tema-alt"} | {f"{k}.css": f'html[data-theme="{k}"]' for k in THEMES - {"o95"}}
    for name, scope in scopes.items():
        for sel in _selectors((tema / name).read_text(encoding="utf-8")):
            # Koma di dalam :is()/:not() bukan pemisah selektor.
            for part in re.split(r",(?![^()]*\))", sel):
                assert part.strip().startswith(scope), f"{name}: {part.strip()}"


def test_entry_pages_load_theme_before_body():
    """theme.js dimuat di <head> supaya tema terpasang sebelum halaman digambar."""
    for f in ENTRY_HTML:
        html = (WEB / f).read_text(encoding="utf-8")
        head = html.split("<body")[0]
        assert "js/theme.js" in head, f
        for key in THEMES - {"o95"}:
            assert f"css/tema/{key}.css" in head, (f, key)
        assert head.index("css/tema/umum.css") > head.index("css/pages.css"), f
    home = (WEB / "pages" / "home.html").read_text(encoding="utf-8")
    assert 'id="hoThemes"' in home and "css/tema/pilihan.css" in (WEB / "app.html").read_text(encoding="utf-8")


def test_no_token_in_local_storage():
    """Sesi hanya di cookie HttpOnly; JS tidak menyimpan token/JWT (INTERFACE §6, M20)."""
    for p in (WEB / "js").glob("*.js"):
        t = p.read_text(encoding="utf-8")
        assert not re.search(r"(local|session)Storage\.\w+\(\s*['\"][^'\"]*(token|jwt|session)", t, re.I), p.name
        assert "Authorization': `Bearer" not in t, p.name


def test_entry_pages_served(api_client):
    for path in ("/", "/masuk", "/daftar", "/app", "/pages/login.html", "/pages/register.html", "/js/app.js",
                 "/js/home.js", "/js/citra-state.js", "/css/main.css", "/css/pages.css", "/css/terrain3d.css",
                 "/js/theme.js", "/css/tema/umum.css", "/css/tema/pilihan.css",
                 "/assets/img/favicon.svg", "/assets/img/logo.svg"):
        r = api_client.get(path)
        assert r.status_code == 200, path
    # Aplikasi terbuka untuk pengunjung (M56): "/" = "/app" = Beranda.
    for path in ("/", "/app"):
        html = api_client.get(path).text
        assert "Shell.mountApp" in html and 'data-requires-auth="false"' in html, path
    # Halaman publik lama dialihkan ke tab padanannya.
    for old, new in (("/kondisi", "/app#citra"), ("/relief", "/app#aoi-3d")):
        r = api_client.get(old, follow_redirects=False)
        assert r.status_code == 301 and r.headers["location"] == new, old
    # Masuk dan Daftar berada di luar aplikasi dan tidak butuh sesi.
    for path, page in PUBLIC_PAGES.items():
        html = api_client.get(path).text
        assert page in html, path
        assert 'data-requires-auth="false"' in html, path
