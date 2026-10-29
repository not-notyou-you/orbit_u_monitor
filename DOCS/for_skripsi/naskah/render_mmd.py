import sys, json, pathlib
from playwright.sync_api import sync_playwright
jobs = json.loads(sys.argv[1]); outdir = pathlib.Path(sys.argv[2]); ERDIR = sys.argv[3] if len(sys.argv) > 3 else "TB"
CFG = {"startOnLoad": False, "theme": "base", "securityLevel": "loose",
       "themeVariables": {"fontFamily": "Arial", "fontSize": "16px", "primaryColor": "#ffffff", "primaryBorderColor": "#1f2a5a",
                          "primaryTextColor": "#111111", "lineColor": "#333333", "clusterBkg": "#eef6f8", "clusterBorder": "#1f2a5a"},
       "flowchart": {"useMaxWidth": False, "htmlLabels": True, "nodeSpacing": 28, "rankSpacing": 38, "padding": 8},
       "er": {"useMaxWidth": False, "layoutDirection": ERDIR, "entityPadding": 12, "fontSize": 16},
       "sequence": {"useMaxWidth": False, "actorMargin": 45, "width": 190, "boxMargin": 6, "messageMargin": 22, "wrap": True, "mirrorActors": False, "noteMargin": 6}}
with sync_playwright() as pw:
    b = pw.chromium.launch(); pg = b.new_page(device_scale_factor=2, viewport={"width": 2400, "height": 1200})
    pg.set_content('<html><body style="margin:20px;background:#fff"><div id="o"></div><script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"></script></body></html>')
    pg.wait_for_function("window.mermaid !== undefined", timeout=60000)
    for name, src in jobs:
        text = pathlib.Path(src).read_text(encoding="utf-8")
        pg.evaluate("c => mermaid.initialize(c)", CFG)
        r = pg.evaluate("""async t => { const {svg} = await mermaid.render('g'+Date.now(), t); const o=document.getElementById('o'); o.innerHTML=svg;
              const s=o.querySelector('svg'); const bb=s.getBoundingClientRect(); return [bb.width,bb.height]; }""", text)
        pg.locator("#o svg").screenshot(path=str(outdir / name))
        print(name, [round(v) for v in r], flush=True)
    b.close()
