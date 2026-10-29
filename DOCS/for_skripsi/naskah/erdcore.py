import sys, pathlib
from playwright.sync_api import sync_playwright
root = pathlib.Path(sys.argv[1]); out = pathlib.Path(sys.argv[2])
css = (root / "assets" / "style.css").read_text(encoding="utf-8")
JS = """([logical, tables]) => {
  const base = ERDSVG.MODULES.find(x => x.id === 'M6');
  const m = Object.assign({}, base, {tables});
  const d = document.createElement('div'); d.className = 'body white'; d.style.width = '3000px'; document.body.append(d);
  const opts = {tables: m.tables, ext: {}, mode: 'all', hideBook: true, key: 'core' + logical + Date.now(), layout: ERDSVG.layoutOne(m), legendModules: [m]};
  if (logical) opts.typeFn = (t) => ERD.shortType(t, false);
  ERDSVG.render(d, opts);
  const s = d.querySelector('svg'); const vb = s.viewBox.baseVal; const c = s.cloneNode(true);
  c.removeAttribute('style'); c.setAttribute('width', vb.width); c.setAttribute('height', vb.height);
  return {html: c.outerHTML, w: vb.width, h: vb.height}; }"""
core = ["region_observations", "alert_rules", "alert_events", "disaster_types", "disaster_events"]
with sync_playwright() as pw:
    b = pw.chromium.launch(); pg = b.new_page(viewport={"width": 1600, "height": 1000}); blank = b.new_page(device_scale_factor=2)
    pg.goto((root / "07-erd-fisik.html").as_uri()); pg.wait_for_timeout(5000)
    for logical, name in ((True, "erd_logikal_core.png"), (False, "erd_fisik_core.png")):
        r = pg.evaluate(JS, [logical, core])
        blank.set_viewport_size({"width": int(r["w"]) + 40, "height": int(r["h"]) + 40})
        blank.set_content(f"<html><head><style>{css}</style><style>body{{margin:20px;background:#fff}}</style></head><body>{r['html']}</body></html>")
        blank.wait_for_timeout(300); blank.locator("svg").first.screenshot(path=str(out / name)); print(name, int(r["w"]), int(r["h"]))
    b.close()
