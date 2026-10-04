"""Uji statis + smoke UI Tahap 4 (INTERFACE.md §2, §5; DESIGN.md).

Tidak menjalankan browser (lihat tests/ui/screenshots.py untuk itu). Yang diuji:
* setiap rute router (js/app.js) punya fragmen pages/*.html dan skrip js/*.js,
  dan keduanya tersaji lewat FastAPI;
* setiap kode error yang dilempar API punya terjemahan Indonesia di js/ui.js (M21);
* fragmen tidak memuat border-radius / blur / emoji (DESIGN.md §2, §6, §8);
* /, /masuk, /app tersaji dan tidak menyimpan token di localStorage (INTERFACE §6).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"

ROUTE_RE = re.compile(r"\{ hash: '([\w-]+)'.*?file: '([\w-]+)'")


def routes() -> list[tuple[str, str]]:
    return ROUTE_RE.findall((WEB / "js" / "app.js").read_text(encoding="utf-8"))


def test_router_has_all_interface_pages():
    hashes = {h for h, _ in routes()}
    # INTERFACE §2: semua halaman /app#…
    assert hashes == {"pantauan", "hari-ini", "analitik", "kejadian", "katalog", "buat-dataset", "laporan", "admin", "akun"}


@pytest.mark.parametrize("file", sorted({f for _, f in routes()} | {"home-public", "login"}))
def test_page_fragment_and_script_exist(file):
    assert (WEB / "pages" / f"{file}.html").is_file()
    js = (WEB / "js" / f"{file}.js").read_text(encoding="utf-8")
    assert f"Pages['{file}']" in js


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


def test_no_token_in_local_storage():
    """Sesi hanya di cookie HttpOnly; JS tidak menyimpan token/JWT (INTERFACE §6, M20)."""
    for p in (WEB / "js").glob("*.js"):
        t = p.read_text(encoding="utf-8")
        assert not re.search(r"(local|session)Storage\.\w+\(\s*['\"][^'\"]*(token|jwt|session)", t, re.I), p.name
        assert "Authorization': `Bearer" not in t, p.name


def test_entry_pages_served(api_client):
    for path in ("/", "/masuk", "/app", "/pages/login.html", "/js/app.js", "/css/main.css", "/assets/img/favicon.svg"):
        r = api_client.get(path)
        assert r.status_code == 200, path
    assert "Shell.mountApp" in api_client.get("/app").text
    assert "home-public" in api_client.get("/").text
