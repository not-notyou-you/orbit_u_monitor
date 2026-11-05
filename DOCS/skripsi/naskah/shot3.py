import sys, json, pathlib
from playwright.sync_api import sync_playwright
root = pathlib.Path(sys.argv[1]); out = pathlib.Path(sys.argv[2]); out.mkdir(exist_ok=True)
pages = sorted(root.glob("[0-9][0-9]-*.html"))
css = (root / "assets" / "style.css").read_text(encoding="utf-8")
JS = """f => { const svgs=[...f.querySelectorAll('svg')]; if(!svgs.length) return null;
  const s=svgs.sort((a,b)=>b.getBoundingClientRect().width*b.getBoundingClientRect().height-a.getBoundingClientRect().width*a.getBoundingClientRect().height)[0];
  const vb=s.viewBox&&s.viewBox.baseVal&&s.viewBox.baseVal.width?s.viewBox.baseVal:null;
  let w=vb?vb.width:s.getBoundingClientRect().width, h=vb?vb.height:s.getBoundingClientRect().height;
  if(!vb){ try{const b=s.getBBox(); w=Math.max(w,b.x+b.width); h=Math.max(h,b.y+b.height);}catch(e){} }
  const c=s.cloneNode(true); c.removeAttribute('style'); c.setAttribute('width',w); c.setAttribute('height',h);
  return {html:c.outerHTML,w,h}; }"""
idx = []
with sync_playwright() as pw:
    b = pw.chromium.launch()
    pg = b.new_page(viewport={"width": 1600, "height": 1000})
    blank = b.new_page(device_scale_factor=2)
    for p in pages:
        pg.goto(p.as_uri()); pg.wait_for_timeout(5000)
        for i, f in enumerate(pg.query_selector_all(".fig")):
            cap = f.get_attribute("data-cap") or ""; kind = f.get_attribute("data-kind") or "Gambar"
            name = f"{p.stem[:2]}_{i:02d}.png"; st = "lewati"
            if kind == "Gambar":
                try:
                    r = f.evaluate(JS)
                    if r:
                        blank.set_viewport_size({"width": int(r["w"]) + 40, "height": int(r["h"]) + 40})
                        blank.set_content(f"<html><head><style>{css}</style><style>body{{margin:20px;background:#fff}}svg{{max-width:none!important}}</style></head><body>{r['html']}</body></html>")
                        blank.wait_for_timeout(300)
                        blank.locator("svg").first.screenshot(path=str(out / name), timeout=30000)
                        st = f"ok {int(r['w'])}x{int(r['h'])}"
                    else: st = "tanpa-svg"
                except Exception as e: st = "gagal " + str(e)[:60]
            idx.append({"file": name, "kind": kind, "cap": cap, "st": st})
            print(name, st, kind, cap[:85], flush=True)
    b.close()
json.dump(idx, open(out / "index.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)
