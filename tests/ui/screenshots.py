#!/usr/bin/env python
"""Tangkapan layar + pemeriksaan otomatis UI Tahap 4 lewat Chrome headless (CDP).

Bukan bagian suite pytest: butuh API yang sedang berjalan (mis. terhadap
`themonitor_dev` dengan SCHEDULER_ENABLED=false, AUTO_RESUME_JOBS=false) dan
Chrome/Edge terpasang. Tidak mengunduh apa pun.

Untuk setiap (halaman, role, lebar) skrip ini:
  * login lewat POST /api/auth/login di konteks halaman (cookie HttpOnly),
  * membuka URL, menunggu jaringan tenang, menyimpan PNG ke tests/screenshots/,
  * mencatat error konsol/JS, request gagal (≥ 400 selain yang diharapkan),
    elemen ber-border-radius ≠ 0, dan scroll horizontal halaman.
Hasil ringkas ditulis ke tests/screenshots/report.json.

Pakai:
    python tests/ui/screenshots.py --base http://127.0.0.1:8011 \
        --password-env UJI_PASSWORD [--pages pantauan,akun] [--widths 320,768,1920]
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests
import websocket

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "tests" / "screenshots"

# (nama berkas, URL, role yang dipakai untuk tangkapan utama)
PAGES = [
    ("home-public", "/", None),
    ("login", "/masuk", None),
    ("monitoring", "/app#pantauan", "user"),
    ("statistics", "/app#hari-ini", "analyst"),
    ("analytics", "/app#analitik", "analyst"),
    ("disasters", "/app#kejadian", "analyst"),
    ("catalog", "/app#katalog", "data_engineer"),
    ("create-dataset", "/app#buat-dataset", "data_engineer"),
    ("reports", "/app#laporan", "admin"),
    ("admin", "/app#admin", "admin"),
    ("account", "/app#akun", "user"),
]
WIDTH_NAME = {320: "mobile", 768: "tablet", 1920: "desktop"}

CHECK_JS = r"""
(() => {
  const rounded = [];
  for (const el of document.querySelectorAll('body *')) {
    if (el.closest('.leaflet-container')) continue;   // kontrol Leaflet dikecualikan
    const r = getComputedStyle(el).borderTopLeftRadius;
    if (r && r !== '0px') rounded.push(el.tagName.toLowerCase() + '.' + el.className);
    if (rounded.length > 10) break;
  }
  return {
    title: document.title,
    hscroll: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
    rounded,
    dialogs: Array.from(document.querySelectorAll('.dialog-backdrop .dialog-msg .txt')).map(e => e.textContent.slice(0, 200)),
    taskbar: !!document.querySelector('.taskbar'),
    unlabeled: Array.from(document.querySelectorAll('input:not([type=hidden]), select, textarea')).filter(i =>
      !(i.labels && i.labels.length) && !i.getAttribute('aria-label') && !i.getAttribute('aria-labelledby')).map(i => i.id || i.name || i.type).slice(0, 10),
    imgNoAlt: document.querySelectorAll('img:not([alt])').length,
  };
})()
"""


def free_port() -> int:
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def find_browser() -> str:
    for p in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              shutil.which("chrome") or "", shutil.which("chromium") or "", shutil.which("google-chrome") or ""):
        if p and Path(p).exists():
            return p
    sys.exit("Chrome/Edge tidak ditemukan")


class CDP:
    def __init__(self, ws_url: str):
        self.ws = websocket.create_connection(ws_url, timeout=60, suppress_origin=True)
        self.i = 0
        self.events: list[dict] = []

    def call(self, method: str, **params):
        self.i += 1
        my = self.i
        self.ws.send(json.dumps({"id": my, "method": method, "params": params}))
        while True:
            m = json.loads(self.ws.recv())
            if m.get("id") == my:
                if "error" in m:
                    raise RuntimeError(f"{method}: {m['error']}")
                return m.get("result", {})
            self.events.append(m)

    def drain(self, seconds: float) -> None:
        end = time.time() + seconds
        self.ws.settimeout(0.2)
        try:
            while time.time() < end:
                try:
                    self.events.append(json.loads(self.ws.recv()))
                except websocket.WebSocketTimeoutException:
                    pass
        finally:
            self.ws.settimeout(60)

    def eval(self, expr: str, await_promise: bool = False):
        r = self.call("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=await_promise)
        return r.get("result", {}).get("value")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8013")
    ap.add_argument("--password-env", default="UJI_PASSWORD")
    ap.add_argument("--pages", default="")
    ap.add_argument("--widths", default="320,768,1920")
    ap.add_argument("--roles", default="", help="role tambahan per halaman, mis. user,analyst (uji RBAC)")
    ap.add_argument("--wait", type=float, default=2.5)
    args = ap.parse_args(argv)
    password = os.environ.get(args.password_env)
    if not password:
        sys.exit(f"Set {args.password_env}")
    widths = [int(w) for w in args.widths.split(",") if w]
    only = set(filter(None, args.pages.split(",")))
    extra_roles = [r for r in args.roles.split(",") if r]
    OUT.mkdir(parents=True, exist_ok=True)

    port = free_port()
    profile = tempfile.mkdtemp(prefix="orbit_u_cdp_")
    proc = subprocess.Popen([find_browser(), "--headless=new", f"--remote-debugging-port={port}",
                             f"--user-data-dir={profile}", "--no-first-run", "--disable-gpu",
                             "--hide-scrollbars", "--force-device-scale-factor=1", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    report = []
    try:
        for _ in range(50):
            try:
                tabs = requests.get(f"http://127.0.0.1:{port}/json", timeout=1).json()
                page = next(t for t in tabs if t["type"] == "page"); break
            except Exception:
                time.sleep(0.2)
        cdp = CDP(page["webSocketDebuggerUrl"])
        for d in ("Page", "Runtime", "Network", "Log"):
            cdp.call(f"{d}.enable")
        # Tanpa cache: gambar yang di-cache sesi role lain bisa menutupi 403.
        cdp.call("Network.setCacheDisabled", cacheDisabled=True)

        current_role = "∅"

        def login(role):
            nonlocal current_role
            if role == current_role:
                return
            cdp.call("Network.clearBrowserCookies")
            cdp.call("Page.navigate", url=args.base + "/masuk"); cdp.drain(1.0)
            if role:
                ok = cdp.eval(f"""fetch('/api/auth/login', {{method:'POST', headers:{{'Content-Type':'application/json','X-Requested-With':'orbit-u'}},
                    body: JSON.stringify({{username:'uji_{role}', password:{json.dumps(password)}}})}}).then(r => r.status)""", True)
                if ok != 200:
                    raise RuntimeError(f"login uji_{role} gagal: {ok}")
            current_role = role

        jobs = []
        for name, url, role in PAGES:
            if only and name not in only:
                continue
            for w in widths:
                jobs.append((name, url, role, w, True))
            for r in extra_roles:
                if url.startswith("/app") and r != role:
                    jobs.append((name, url, r, 1920, False))
        for name, url, role, w, save in jobs:
            login(role)
            cdp.call("Emulation.setDeviceMetricsOverride", width=w, height=900, deviceScaleFactor=1, mobile=w < 800)
            cdp.events.clear()
            cdp.call("Page.navigate", url="about:blank")
            cdp.call("Page.navigate", url=args.base + url)
            cdp.drain(args.wait)
            checks = cdp.eval(CHECK_JS) or {}
            errors = []
            for ev in cdp.events:
                m = ev.get("method")
                if m == "Runtime.exceptionThrown":
                    d = ev["params"]["exceptionDetails"]
                    errors.append("JS: " + (d.get("exception", {}).get("description") or d.get("text", ""))[:300])
                elif m == "Log.entryAdded" and ev["params"]["entry"]["level"] == "error":
                    errors.append("LOG: " + ev["params"]["entry"]["text"][:300] + " " + ev["params"]["entry"].get("url", ""))
                elif m == "Network.responseReceived":
                    st = ev["params"]["response"]["status"]
                    if st >= 400:
                        errors.append(f"HTTP {st}: {ev['params']['response']['url']}")
            # 401 /auth/me untuk pengunjung = cara UI mendeteksi "belum login" (diharapkan).
            errors = [e for e in errors if not (role is None and "/api/auth/me" in e and "401" in e)]
            entry = {"page": name, "role": role or "public", "width": w, **checks, "errors": errors}
            if save:
                # Viewport setinggi halaman agar taskbar (position: fixed) tergambar di bawah.
                h = min(6000, max(600, cdp.eval("document.documentElement.scrollHeight") or 900))
                cdp.call("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=1, mobile=w < 800)
                cdp.drain(0.6)
                shot = cdp.call("Page.captureScreenshot", format="png")
                fn = OUT / f"{name}-{WIDTH_NAME.get(w, w)}.png"
                fn.write_bytes(base64.b64decode(shot["data"]))
                entry["file"] = fn.name
            report.append(entry)
            flag = "OK " if not errors and not checks.get("hscroll") and not checks.get("rounded") else "!! "
            print(flag, name, role or "public", w, checks.get("title"), errors[:3], "hscroll" if checks.get("hscroll") else "",
                  checks.get("rounded") or "", checks.get("dialogs") or "", checks.get("unlabeled") or "")
    finally:
        proc.terminate()
        try:
            proc.wait(5)
        except Exception:
            proc.kill()
        shutil.rmtree(profile, ignore_errors=True)
    rp = OUT / "report.json"
    old = json.loads(rp.read_text(encoding="utf-8")) if rp.exists() else []
    keep = [e for e in old if (e["page"], e["role"], e["width"]) not in {(r["page"], r["role"], r["width"]) for r in report}]
    rp.write_text(json.dumps(keep + report, indent=1, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
