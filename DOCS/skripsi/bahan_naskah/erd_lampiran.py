"""ERD fisik per modul (M1-M6) untuk lampiran skripsi, dari skema nyata di assets/data.js.

Pemakaian: python erd_lampiran.py <folder bahan_naskah> <folder keluaran>
Menghasilkan erd_fisik_M1.png ... erd_fisik_M6.png (semua tabel dan kolom setiap modul, tipe PostgreSQL).
Cara render sama dengan erdcore.py; FK ke tabel modul lain tidak digambar sebagai garis.
"""
import pathlib
import sys

from playwright.sync_api import sync_playwright

root = pathlib.Path(sys.argv[1])
out = pathlib.Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
css = (root / "assets" / "style.css").read_text(encoding="utf-8")
JS = """(id) => {
  const m = ERDSVG.MODULES.find(x => x.id === id);
  const d = document.createElement('div'); d.className = 'body white'; d.style.width = '3000px'; document.body.append(d);
  ERDSVG.render(d, {tables: m.tables, ext: {}, mode: 'all', hideBook: true, key: 'lamp' + id + Date.now(),
                    layout: ERDSVG.layoutOne(m), legendModules: [m]});
  const s = d.querySelector('svg'); const vb = s.viewBox.baseVal; const c = s.cloneNode(true);
  c.removeAttribute('style'); c.setAttribute('width', vb.width); c.setAttribute('height', vb.height);
  d.remove();
  return {html: c.outerHTML, w: vb.width, h: vb.height}; }"""
with sync_playwright() as pw:
    b = pw.chromium.launch()
    pg = b.new_page(viewport={"width": 1600, "height": 1000})
    blank = b.new_page(device_scale_factor=2)
    pg.goto((root / "07-erd-fisik.html").as_uri())
    pg.wait_for_timeout(5000)
    for mid in ["M1", "M2", "M3", "M4", "M5", "M6"]:
        r = pg.evaluate(JS, mid)
        blank.set_viewport_size({"width": int(r["w"]) + 40, "height": int(r["h"]) + 40})
        blank.set_content(f"<html><head><style>{css}</style><style>body{{margin:20px;background:#fff}}</style></head>"
                          f"<body>{r['html']}</body></html>")
        blank.wait_for_timeout(300)
        blank.locator("svg").first.screenshot(path=str(out / f"erd_fisik_{mid}.png"))
        print(mid, int(r["w"]), int(r["h"]))
    b.close()
