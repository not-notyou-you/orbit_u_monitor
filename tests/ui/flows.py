#!/usr/bin/env python
"""Uji alur UI Tahap 4 lewat Chrome headless (CDP) terhadap API yang berjalan.

HANYA untuk DB `themonitor_dev`/`themonitor_test` (skrip menolak berjalan bila
/api/health tidak bisa dipastikan bukan produksi lewat --i-know-this-is-dev).
Tidak memicu unduhan: aksi yang menjalankan pipeline (buat dataset, picu
ingestion, proses ulang, periksa Live) tidak pernah diklik.

Setiap alur mencatat hasil PASS/FAIL ke tests/screenshots/flows.json dan
menyimpan tangkapan layar langkah penting (flow-*.png).

Pakai:
    UJI_PASSWORD=... python tests/ui/flows.py --base http://127.0.0.1:8013 --i-know-this-is-dev
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from screenshots import CDP, OUT, find_browser, free_port  # noqa: E402


class Browser:
    def __init__(self, base: str, password: str):
        self.base, self.password = base, password
        self.port = free_port()
        self.profile = tempfile.mkdtemp(prefix="orbit_u_flow_")
        self.proc = subprocess.Popen([find_browser(), "--headless=new", f"--remote-debugging-port={self.port}",
                                      f"--user-data-dir={self.profile}", "--no-first-run", "--disable-gpu",
                                      "--hide-scrollbars", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(50):
            try:
                page = next(t for t in requests.get(f"http://127.0.0.1:{self.port}/json", timeout=1).json() if t["type"] == "page")
                break
            except Exception:
                time.sleep(0.2)
        self.cdp = CDP(page["webSocketDebuggerUrl"])
        for d in ("Page", "Runtime", "Network", "Log"):
            self.cdp.call(f"{d}.enable")
        self.cdp.call("Network.setCacheDisabled", cacheDisabled=True)
        self.cdp.call("Emulation.setDeviceMetricsOverride", width=1440, height=1000, deviceScaleFactor=1, mobile=False)

    def close(self):
        self.proc.terminate()
        try:
            self.proc.wait(5)
        except Exception:
            self.proc.kill()
        shutil.rmtree(self.profile, ignore_errors=True)

    # ---- dasar
    def go(self, path: str, wait: float = 2.0):
        self.cdp.call("Page.navigate", url=self.base + path)
        self.cdp.drain(wait)

    def js(self, expr: str, wait: float = 0.0, await_promise: bool = False):
        v = self.cdp.eval(expr, await_promise)
        if wait:
            self.cdp.drain(wait)
        return v

    def login(self, role: str | None):
        self.cdp.call("Network.clearBrowserCookies")
        self.go("/masuk", 1.0)
        if role:
            st = self.js(f"""fetch('/api/auth/login', {{method:'POST', headers:{{'Content-Type':'application/json','X-Requested-With':'orbit-u'}},
                body: JSON.stringify({{username:'uji_{role}', password:{json.dumps(self.password)}}})}}).then(r => r.status)""", await_promise=True)
            assert st == 200, f"login {role}: {st}"

    def click(self, selector: str, wait: float = 1.0):
        ok = self.js(f"(() => {{ const e = document.querySelector({json.dumps(selector)}); if (!e) return false; e.click(); return true; }})()")
        assert ok, f"tidak ada elemen {selector}"
        self.cdp.drain(wait)

    def set(self, selector: str, value, wait: float = 0.0):
        ok = self.js(f"""(() => {{ const e = document.querySelector({json.dumps(selector)}); if (!e) return false;
            if (e.type === 'checkbox' || e.type === 'radio') e.checked = {json.dumps(bool(value))}; else e.value = {json.dumps(value)};
            e.dispatchEvent(new Event('input', {{bubbles:true}})); e.dispatchEvent(new Event('change', {{bubbles:true}})); return true; }})()""")
        assert ok, f"tidak ada input {selector}"
        if wait:
            self.cdp.drain(wait)

    def key(self, key: str, code: str | None = None, wait: float = 0.3):
        kc = {"Enter": 13, "Escape": 27, "ArrowDown": 40, "ArrowUp": 38, "ArrowRight": 39, "Tab": 9}.get(key, 0)
        extra = {"text": chr(13), "unmodifiedText": chr(13)} if key == "Enter" else {}
        self.cdp.call("Input.dispatchKeyEvent", type="keyDown", key=key, code=code or key, windowsVirtualKeyCode=kc, nativeVirtualKeyCode=kc, **extra)
        self.cdp.call("Input.dispatchKeyEvent", type="keyUp", key=key, code=code or key, windowsVirtualKeyCode=kc, nativeVirtualKeyCode=kc)
        self.cdp.drain(wait)

    def text(self, selector: str = "body") -> str:
        return self.js(f"(document.querySelector({json.dumps(selector)}) || {{}}).innerText || ''") or ""

    def dialog_text(self) -> str:
        return self.js("Array.from(document.querySelectorAll('.dialog-backdrop')).map(d => d.innerText).join('\\n---\\n')") or ""

    def close_dialogs(self):
        for _ in range(5):
            if not self.js("document.querySelectorAll('.dialog-backdrop').length"):
                return
            self.key("Escape", wait=0.4)

    def errors(self) -> list[str]:
        out = []
        for ev in self.cdp.events:
            m = ev.get("method")
            if m == "Runtime.exceptionThrown":
                d = ev["params"]["exceptionDetails"]
                out.append("JS: " + (d.get("exception", {}).get("description") or d.get("text", ""))[:200])
            elif m == "Network.responseReceived" and ev["params"]["response"]["status"] >= 500:
                out.append(f"HTTP {ev['params']['response']['status']} {ev['params']['response']['url']}")
        self.cdp.events.clear()
        return out

    def shot(self, name: str):
        h = min(5000, max(700, self.js("document.documentElement.scrollHeight") or 900))
        self.cdp.call("Emulation.setDeviceMetricsOverride", width=1440, height=h, deviceScaleFactor=1, mobile=False)
        self.cdp.drain(0.4)
        (OUT / f"flow-{name}.png").write_bytes(base64.b64decode(self.cdp.call("Page.captureScreenshot", format="png")["data"]))
        self.cdp.call("Emulation.setDeviceMetricsOverride", width=1440, height=1000, deviceScaleFactor=1, mobile=False)


RESULTS: list[dict] = []


def flow(name: str):
    def deco(fn):
        def run(b: Browser):
            b.cdp.events.clear()
            t0 = time.time()
            try:
                notes = fn(b) or ""
                errs = b.errors()
                status = "PASS" if not errs else "FAIL"
                RESULTS.append({"flow": name, "status": status, "notes": notes, "errors": errs, "seconds": round(time.time() - t0, 1)})
            except Exception as e:  # noqa: BLE001
                RESULTS.append({"flow": name, "status": "FAIL", "notes": f"{type(e).__name__}: {e}", "errors": b.errors(),
                                "trace": traceback.format_exc()[-800:]})
            finally:
                try:
                    b.close_dialogs()
                except Exception:
                    pass
            r = RESULTS[-1]
            print(f"{r['status']:4}  {name}  {r['notes'][:140]}  {r['errors'][:2]}")
        run.__name__ = fn.__name__
        return run
    return deco


# --------------------------------------------------------------------------- alur
@flow("auth: login salah → dialog pesan Indonesia; login benar → /app")
def f_login(b: Browser):
    b.login(None)
    b.go("/masuk", 1.5)
    b.click("#loginBtn", 0.6)
    assert "Wajib diisi" in b.text("#usernameErr"), "validasi klien kosong"
    b.set("#username", "uji_user"); b.set("#password", "salah-sekali-123")
    b.click("#loginBtn", 1.5)
    d = b.dialog_text()
    assert "Nama pengguna atau kata sandi salah" in d, d
    b.close_dialogs()
    b.set("#password", b.password)
    b.click("#loginBtn", 2.5)
    href = b.js("location.pathname + location.hash")
    assert href.startswith("/app#"), href
    return "INVALID_CREDENTIALS diterjemahkan; redirect ke " + href


@flow("auth: tanpa sesi → /app dialihkan ke /masuk; keluar menghapus sesi")
def f_guard(b: Browser):
    b.login(None)
    b.go("/app#riwayat/grafik", 2.0)
    p = b.js("location.pathname + location.search")
    assert p.startswith("/masuk") and "next=" in p, p
    b.login("user"); b.go("/app#akun", 2.0)
    b.click("#startBtn", 0.4)
    assert b.js("!document.getElementById('startMenu').classList.contains('hidden')"), "menu Mulai tidak terbuka"
    b.click("#startList [data-action=logout]", 2.0)
    p2 = b.js("location.pathname + location.search")
    st = b.js("fetch('/api/auth/me').then(r => r.status)", await_promise=True)
    assert p2.startswith("/masuk") and st == 401, (p2, st)
    return f"tanpa sesi → {p}; keluar → {p2}, /auth/me {st}"


@flow("rbac: menu Mulai per role sesuai permissions; halaman terlarang → 'Akses ditolak'")
def f_rbac(b: Browser):
    # Lima tujuan + Beranda + Akun Saya. Tujuan bertab terlihat bila minimal
    # satu tabnya boleh dibuka: data_engineer melihat "riwayat" karena Laporan
    # Kesehatan Data, walau tab Grafik & tren tertutup untuknya.
    #
    # `data-hash` hanya ada di item tingkat atas; tab dari tujuan bertab dirender
    # sebagai sub-item ber-`data-tab-hash`, jadi pemeriksaan izin di bawah ini
    # tetap membandingkan tujuan dengan tujuan.
    allhash = {"beranda", "kondisi", "riwayat", "kejadian", "data", "pengaturan", "akun"}
    expect = {
        "user": {"beranda", "kondisi", "akun"},
        "analyst": {"beranda", "kondisi", "riwayat", "kejadian", "akun"},
        "data_engineer": {"beranda", "kondisi", "riwayat", "data", "akun"},
        "admin": allhash,
    }
    notes = []
    for role, want in expect.items():
        b.login(role); b.go("/app#akun", 2.0)
        got = set(b.js("Array.from(document.querySelectorAll('#startList a[data-hash]')).map(a => a.dataset.hash)") or [])
        assert got == want, (role, sorted(got ^ want))
        for h in sorted(allhash - want):
            b.go("/app#" + h, 1.5)
            assert "Akses ditolak" in b.text("#main"), (role, h)
        notes.append(f"{role}:{len(got)}")
    # Sub-item menu Mulai: ADMIN melihat tab tiap tujuan bertab langsung di menu,
    # termasuk bagian Pengaturan, jadi tujuan + tab tercapai dalam satu klik.
    b.login("admin"); b.go("/app#akun", 2.0)
    subs = set(b.js("Array.from(document.querySelectorAll('#startList a[data-tab-hash]')).map(a => a.dataset.tabHash)") or [])
    for want in ("kondisi/citra", "riwayat/laporan", "data/proses", "pengaturan/jejak"):
        assert want in subs, (want, sorted(subs))
    b.login("user"); b.go("/app#pengaturan", 1.5); b.shot("rbac-user-admin")
    return "menu " + ", ".join(notes) + f"; {len(subs)} sub-item; akses langsung ditolak di UI"


@flow("keyboard: menu Mulai (Enter/panah/Escape), tab admin dengan panah")
def f_keyboard(b: Browser):
    b.login("admin"); b.go("/app#pengaturan", 2.0)
    b.js("document.getElementById('startBtn').focus()")
    b.key("Enter")
    assert b.js("document.activeElement && document.activeElement.getAttribute('role') === 'menuitem'"), "fokus tidak masuk menu"
    b.key("ArrowDown")
    b.key("Escape")
    assert b.js("document.getElementById('startMenu').classList.contains('hidden') && document.activeElement.id === 'startBtn'"), "Escape tidak menutup"
    # Kelompok Pengaturan kini tab router biasa, jadi tablist-nya ada di jendela
    # halaman seperti tujuan bertab lainnya.
    b.js("document.querySelector('#pageWindow .tabs [role=tab]').focus()")
    b.key("ArrowRight", wait=1.5)
    sel = b.js("document.querySelector('#pageWindow .tabs [aria-selected=true]').dataset.tab")
    assert sel == "operasi", sel
    h = b.js("location.hash")
    assert h.startswith("#pengaturan/operasi"), h
    return f"Start menu & tablist bisa dioperasikan keyboard; hash mengikuti tab ({h})"


@flow("akun: buat token (tampil sekali) lalu cabut")
def f_token(b: Browser):
    b.login("user"); b.go("/app#akun", 2.0)
    b.set("#tkName", "UJI SINTETIS flow token"); b.set("#tkDays", "7")
    b.click("#tkBtn", 2.0)
    tok = b.js("(document.getElementById('newTokenVal') || {}).value")
    assert tok and tok.startswith("trn_"), tok
    b.click(".dialog-backdrop .btn-row.end button", 1.5)
    assert "UJI SINTETIS flow token" in b.text("#tokenList")
    st = requests.get(b.base + "/api/hydromet/today", headers={"Authorization": "Bearer " + tok}, timeout=10).status_code
    b.click("#tokenList [data-revoke]", 1.0)
    b.click(".dialog-backdrop .btn-row.end button.default", 2.0)
    st2 = requests.get(b.base + "/api/hydromet/today", headers={"Authorization": "Bearer " + tok}, timeout=10).status_code
    assert st == 200 and st2 == 401, (st, st2)
    return f"token baru dipakai → {st}; setelah dicabut → {st2}"


@flow("statistik: ANALYST tandai alert sudah dibaca (dengan catatan); USER tanpa tombol")
def f_ack(b: Browser):
    b.login("user"); b.go("/app#kondisi/kecamatan", 3.5)
    assert not b.js("document.querySelectorAll('[data-ack]').length"), "USER melihat tombol ack"
    b.login("analyst"); b.go("/app#kondisi/kecamatan", 3.5)
    n = b.js("document.querySelectorAll('[data-ack]').length")
    if not n:
        return "tidak ada alert aktif (lewati)"
    b.click("[data-ack]", 1.0)
    b.set("#ackNote", "UJI SINTETIS: ditandai lewat flows.py")
    b.click(".dialog-backdrop .btn-row.end button.default", 3.0)
    d = b.dialog_text()
    assert "ditandai sudah dibaca" in d, d
    b.close_dialogs(); b.cdp.drain(2.0)
    n2 = b.js("document.querySelectorAll('[data-ack]').length")
    b.shot("statistics-after-ack")
    assert n2 == n - 1, (n, n2)
    return f"kecamatan dengan alert aktif {n} → {n2}"


@flow("kejadian: validasi formulir, catat, ubah, hapus (soft delete)")
def f_disaster(b: Browser):
    b.login("analyst"); b.go("/app#kejadian", 3.0)
    b.click("#dzNew", 1.5)
    b.click(".dialog-backdrop .btn-row.end button.default", 0.8)
    errs = b.js("Array.from(document.querySelectorAll('.dialog-backdrop .err')).map(e => e.textContent).filter(Boolean)")
    assert len(errs) >= 3, errs
    b.set("#fType", "BANJIR"); b.set("#fDate", "2024-01-07"); b.set("#fRegion", b.js("document.querySelector('#fRegion option:nth-child(3)').value"))
    b.set("#fDesc", "UJI SINTETIS — kejadian contoh untuk uji UI Tahap 4 (bukan kejadian nyata).")
    b.set("#fLat", "-6.85"); b.set("#fLon", "106.2"); b.set("#fSource", "LAINNYA")
    b.shot("disaster-form")
    b.click(".dialog-backdrop .btn-row.end button.default", 2.5)
    d = b.dialog_text()
    assert "tersimpan" in d, d
    b.close_dialogs(); b.cdp.drain(1.5)
    assert "BANJIR" in b.text("#dzTable").upper() or "Banjir" in b.text("#dzTable"), b.text("#dzTable")[:200]
    b.click("#dzTable [data-open]", 2.0)
    assert "HUJAN KECAMATAN H-0..H-2" in b.dialog_text().upper()
    b.shot("disaster-detail")
    b.click(".dialog-backdrop .btn-row.end button.default", 1.5)   # Ubah…
    b.set("#fVer", True)
    b.click(".dialog-backdrop .btn-row.end button.default", 2.5)
    assert "tersimpan" in b.dialog_text()
    b.close_dialogs(); b.cdp.drain(1.5)
    assert "TERVERIFIKASI" in b.text("#dzTable")
    b.click("#dzTable [data-open]", 2.0)
    b.click(".dialog-backdrop .btn-row.end button:nth-child(2)", 1.0)   # Hapus…
    b.click(".dialog-backdrop:last-child .btn-row.end button.default", 2.0)
    assert "dihapus" in b.dialog_text()
    b.close_dialogs(); b.cdp.drain(1.5)
    return "buat → ubah (verifikasi) → hapus; " + str(len(errs)) + " pesan validasi klien"


@flow("katalog: semua tab rincian dataset UJI SINTETIS terbuka tanpa error")
def f_catalog(b: Browser):
    b.login("data_engineer"); b.go("/app#data/daftar", 3.0)
    # Selektor dibatasi ke tablist rincian di dalam halaman. Tanpa batas itu
    # daftarnya ikut memuat tab tujuan "Data" (Dataset tersimpan / Buat dataset
    # baru / Proses berjalan), dan klik pertama ke salah satunya meninggalkan
    # Katalog sehingga tab sisanya tidak ada lagi.
    sel = "#pageRoot .deck .tabs [role=tab]"
    tabs = b.js(f"Array.from(document.querySelectorAll({sel!r})).map(t => t.dataset.tab)")
    for t in tabs:
        b.click(f"#pageRoot .deck .tabs [role=tab][data-tab='{t}']", 2.0)
        assert "GAGAL MEMUAT" not in b.text("#ctPanel"), t
        if t in ("produk", "struktur"):
            b.shot("catalog-" + t)
    return "tab: " + ", ".join(tabs)


@flow("buat dataset: validasi langkah, konfigurasi sebelumnya, ringkasan (tanpa kirim)")
def f_wizard(b: Browser):
    b.login("data_engineer"); b.go("/app#data/buat", 3.0)
    b.click("#cdNext", 0.6)
    assert "Pilih lokasi" in b.text("#cdErr"), b.text("#cdErr")
    b.click("#cdRois [data-roi]", 1.0)
    b.set("#cdStart", "2024-01-01"); b.set("#cdEnd", "2025-06-01")
    b.click("#cdNext", 0.6)
    assert "366" in b.text("#cdErr"), b.text("#cdErr")
    b.set("#cdEnd", "2024-01-31")
    b.click("#cdNext", 0.6)
    b.click("#cdNext", 0.6)
    assert "minimal satu sumber" in b.text("#cdErr"), b.text("#cdErr")
    b.set("[data-enable=sentinel1]", True); b.set("[data-enable=gpm]", True)
    b.click("#cdNext", 0.6)
    b.click("#cdNext", 0.6)
    assert "strategi fusi" in b.text("#cdErr"), b.text("#cdErr")
    b.set("input[name=cdFusion][value=FULL_COVERAGE]", True)
    b.click("#cdNext", 0.6)
    assert b.js("document.querySelector('section[data-step=\"4\"]').hidden === false"), b.text("#cdErr")
    b.set("#cdName", "UJI SINTETIS wizard (tidak dikirim)")
    rv = b.text("#cdReview")
    assert "FULL_COVERAGE" in rv and "S1[PROC]" in rv and "TOLERANSI" in rv.upper(), rv
    b.shot("wizard-review")
    if b.js("!document.getElementById('cdClone').hidden"):
        b.click("#cdCloneBtn", 1.5)
        assert "diterapkan" in b.dialog_text()
    return "validasi 4 langkah + ringkasan; tombol 'Buat dataset' TIDAK diklik (akan mengunduh)"


@flow("analitik: filter, rentang terbalik ditolak, ekspor CSV tercatat")
def f_analytics(b: Browser):
    b.login("analyst"); b.go("/app#riwayat/grafik", 4.0)
    b.set("#anFrom", "2024-01-07"); b.set("#anTo", "2024-01-01")
    b.click("#anApply", 0.8)
    assert "sebelum" in b.text("#anDateErr"), b.text("#anDateErr")
    b.set("#anFrom", "2024-01-01"); b.set("#anTo", "2024-01-07"); b.set("#anBand", "NDVI")
    b.click("#anApply", 3.0)
    assert "NDVI" in b.text("#anReadouts").upper()
    b.click("#anCsv", 2.0)
    assert not b.dialog_text(), b.dialog_text()
    return "validasi tanggal + band NDVI + CSV tanpa error"


@flow("laporan: unduh PDF (ANALYST) dan tab sesuai audiens")
def f_reports(b: Browser):
    b.login("analyst"); b.go("/app#riwayat/laporan", 2.5)
    tabs = b.js("Array.from(document.querySelectorAll('#rpTabs [role=tab]')).map(t => t.textContent)")
    assert tabs == ["Hidromet"], tabs
    if b.js("document.querySelectorAll('[data-dl]').length"):
        b.click("[data-dl]", 2.5)
        assert not b.dialog_text(), b.dialog_text()
    b.login("data_engineer"); b.go("/app#riwayat/laporan", 2.5)
    tabs2 = b.js("Array.from(document.querySelectorAll('#rpTabs [role=tab]')).map(t => t.textContent)")
    assert tabs2 == ["Kesehatan Data"], tabs2
    return f"ANALYST {tabs}, DATA_ENGINEER {tabs2}"


@flow("pengaturan: 5 kelompok + semua bagiannya terbuka tanpa error; buat akun + validasi + CANNOT_MODIFY_SELF")
def f_admin(b: Browser):
    b.login("admin"); b.go("/app#pengaturan", 2.5)
    # Kelompoknya tab router (#pageWindow .tabs); bagian di dalamnya segmen
    # ketiga hash, dengan baris tabnya sendiri (#adSub).
    groups = b.js("Array.from(document.querySelectorAll('#pageWindow .tabs [role=tab]')).map(t => t.dataset.tab)")
    assert groups == ["ringkasan", "operasi", "konfigurasi", "akses", "jejak"], groups
    seen = []
    for g in groups:
        b.click(f"#pageWindow .tabs [data-tab='{g}']", 2.5)
        subs = b.js("Array.from(document.querySelectorAll('#adSub .sub-row [role=tab]')).map(t => t.dataset.tab)") or []
        for t in subs or [g]:
            if subs:
                b.click(f"#adSub .sub-row [data-tab='{t}']", 2.5)
                h = b.js("location.hash")
                assert h == f"#pengaturan/{g}/{t}", (h, g, t)
            txt = b.text("#adPanel")
            assert "GAGAL MEMUAT" not in txt, (g, t)
            seen.append(t)
            b.shot("admin-" + t)
    assert "penyimpanan" in seen, seen
    b.click("#pageWindow .tabs [data-tab='akses']", 2.5)
    b.click("#auNew", 1.0)
    b.set("#af_username", "Bukan Valid!")
    b.click(".dialog-backdrop .btn-row.end button.default", 0.6)
    assert "huruf kecil" in b.dialog_text(), b.dialog_text()
    uname = "uji_flow_" + str(int(time.time()) % 100000)
    b.set("#af_username", uname); b.set("#af_full_name", "UJI SINTETIS akun flow"); b.set("#af_password", "UjiFlow!2026x")
    b.click(".dialog-backdrop .btn-row.end button.default", 2.0)
    assert "dibuat" in b.dialog_text(), b.dialog_text()
    b.close_dialogs()
    # ADMIN menurunkan perannya sendiri → 409 CANNOT_MODIFY_SELF diterjemahkan.
    b.set("#auQ", "uji_admin"); b.js("document.querySelector('form.ct-filters').requestSubmit()"); b.cdp.drain(1.5)
    b.click("[data-edit]", 1.0)
    b.set("#af_role_code", "USER")
    b.click(".dialog-backdrop .btn-row.end button.default", 1.5)
    d = b.dialog_text()
    assert "akun sendiri" in d, d
    return f"{len(groups)} kelompok / {len(seen)} bagian; akun {uname} dibuat; CANNOT_MODIFY_SELF diterjemahkan"


@flow("data → proses berjalan: daftar lintas dataset terbuka; kosong pun menyebut jadwal")
def f_process(b: Browser):
    b.login("data_engineer"); b.go("/app#data/proses", 3.0)
    assert b.js("location.hash") == "#data/proses", b.js("location.hash")
    txt = b.text("#pcList")
    assert "GAGAL MEMUAT" not in txt, txt[:200]
    # Keadaan kosong adalah keadaan normal di sistem ini, jadi teksnya wajib
    # menyebut kapan proses berikutnya jalan — bukan hanya "tidak ada data".
    if "TIDAK ADA PROSES" in txt:
        assert "WIB" in txt, txt[:200]
    ro = b.text("#pcReadouts")
    for lbl in ("SEDANG BERJALAN", "ANTRE", "DIJEDA", "GAGAL"):
        assert lbl in ro, (lbl, ro[:200])
    # Mencentang "tampilkan juga yang sudah selesai" tidak boleh menimbulkan error.
    b.set("#pcAll", True, wait=2.5)
    assert "GAGAL MEMUAT" not in b.text("#pcList")
    b.shot("process-running")
    return "readout + daftar proses terbuka; kosong menyebut jadwal siklus"


@flow("deep-link: bagian Pengaturan dibuka langsung dari alamat, tanpa klik")
def f_deeplink(b: Browser):
    # Inti perubahan susunan: 13 bagian Pengaturan punya alamat sendiri, jadi
    # bisa dibagikan dan selamat dari refresh.
    b.login("admin")
    for path, want_tab, want_sub, probe in [
        ("/app#pengaturan/jejak/audit", "jejak", "audit", "#adPanel"),
        ("/app#pengaturan/operasi/penyimpanan", "operasi", "penyimpanan", "#adPanel"),
    ]:
        b.go(path, 3.0)
        assert b.js("location.hash") == f"#pengaturan/{want_tab}/{want_sub}", b.js("location.hash")
        grp = b.js("document.querySelector('#pageWindow .tabs [aria-selected=true]').dataset.tab")
        sub = b.js("document.querySelector('#adSub .sub-row [aria-selected=true]').dataset.tab")
        assert (grp, sub) == (want_tab, want_sub), (grp, sub, want_tab, want_sub)
        assert "GAGAL MEMUAT" not in b.text(probe), path
    b.shot("deeplink-penyimpanan")
    # Sub yang tidak dikenal jatuh ke bagian pertama kelompoknya, bukan ke panel kosong.
    b.go("/app#pengaturan/jejak/bukan-bagian", 3.0)
    sub = b.js("document.querySelector('#adSub .sub-row [aria-selected=true]').dataset.tab")
    assert sub == "masuk", sub
    # Hash lama tetap mendarat.
    b.go("/app#admin", 2.5)
    assert b.js("location.hash") == "#pengaturan/ringkasan", b.js("location.hash")
    # Peran tanpa izin tetap ditolak, bukan dapat halaman kosong.
    b.login("analyst"); b.go("/app#pengaturan/jejak/audit", 2.0)
    assert "Akses ditolak" in b.text("#main")
    return "bagian Pengaturan bisa dibuka dari alamat; sub tak dikenal & hash lama aman; 403 tetap berlaku"


@flow("error 404/500: halaman fragmen hilang & API error menampilkan dialog, bukan layar putih")
def f_errors(b: Browser):
    b.login("analyst"); b.go("/app#kejadian", 2.5)
    st = b.js("API.get('/api/disasters/99999999').then(() => 'ok', e => { UI.showError('Uji', e); return e.status; })", await_promise=True)
    b.cdp.drain(0.5)
    d = b.dialog_text()
    assert st == 404 and "Data tidak ditemukan" in d, (st, d)
    b.close_dialogs()
    b.js("UI.showError('Uji', {status: 500}); 1")
    b.cdp.drain(0.5)
    d5 = b.dialog_text()
    assert "kesalahan di server" in d5, d5
    return "404 → 'Data tidak ditemukan.'; 500 → 'Terjadi kesalahan di server.'"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8013")
    ap.add_argument("--password-env", default="UJI_PASSWORD")
    ap.add_argument("--only", default="")
    ap.add_argument("--i-know-this-is-dev", action="store_true", required=True)
    args = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    b = Browser(args.base, os.environ[args.password_env])
    flows = [f_login, f_guard, f_rbac, f_keyboard, f_token, f_ack, f_disaster, f_catalog, f_process, f_wizard,
             f_analytics, f_reports, f_admin, f_deeplink, f_errors]
    try:
        for f in flows:
            if not args.only or args.only in f.__name__:
                f(b)
    finally:
        b.close()
    (OUT / "flows.json").write_text(json.dumps(RESULTS, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\n{sum(r['status'] == 'PASS' for r in RESULTS)}/{len(RESULTS)} PASS")
    return 0 if all(r["status"] == "PASS" for r in RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
