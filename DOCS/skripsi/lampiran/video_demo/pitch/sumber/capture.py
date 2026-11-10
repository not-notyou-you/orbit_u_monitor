import sys, time, json
from playwright.sync_api import sync_playwright
OUT = sys.argv[1]; WHAT = sys.argv[2].split(",")
B = "http://127.0.0.1:8011"
CH = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
HOOK = """
(() => { let _v; Object.defineProperty(window,'maplibregl',{configurable:true,
  get(){return _v;}, set(v){ try{ const M=v.Map; const W=class extends M{constructor(...a){ if(a[0]) a[0].preserveDrawingBuffer=true; super(...a); window.__map=this; }}; 
  Object.defineProperty(v,'Map',{value:W,writable:true,configurable:true}); }catch(e){console.warn('hook',e);} _v=v; }}); })();
"""
def login(ctx, user):
    pg = ctx.new_page()
    pg.goto(B+"/masuk"); pg.fill("#username",user); pg.fill("#password","DevPassword!2026"); pg.click("#loginBtn")
    pg.wait_for_url("**/app**", timeout=15000); time.sleep(2); return pg
with sync_playwright() as p:
    br = p.chromium.launch(executable_path=CH, headless=True, args=["--headless=new","--use-angle=swiftshader","--enable-unsafe-swiftshader","--ignore-gpu-blocklist","--hide-scrollbars"])
    if "mobile" in WHAT:
        m = br.new_context(viewport={"width":390,"height":844}, device_scale_factor=2.5, is_mobile=True, has_touch=True, locale="id-ID")
        mp = m.new_page(); mp.goto(B+"/app#beranda"); time.sleep(6)
        mp.add_style_tag(content=".taskbar{display:none!important} body{padding-bottom:16px!important}")
        mp.screenshot(path=f"{OUT}/m_home.png", full_page=True)
        row = mp.get_by_text("Bayah", exact=True).first
        bb = row.bounding_box(); print("bayah row", bb, "scrollY", mp.evaluate("scrollY"))
        row.click(); time.sleep(8)
        print("scrollY after", mp.evaluate("scrollY"), "H", mp.evaluate("document.documentElement.scrollHeight"))
        mp.evaluate("scrollTo(0,0)"); time.sleep(1)
        mp.screenshot(path=f"{OUT}/m_bayah.png", full_page=True)
        info = mp.evaluate("""() => [...document.querySelectorAll('#pageRoot fieldset, #pageRoot section, #pageRoot img, #pageRoot svg.chart, #pageRoot h2, #pageRoot h3, #pageRoot legend')].map(e=>{const r=e.getBoundingClientRect();return [e.tagName,e.id||e.className&&String(e.className.baseVal||e.className).slice(0,30),Math.round(r.top+scrollY),Math.round(r.height),(e.textContent||'').trim().slice(0,40)]})""")
        json.dump(info, open(f"{OUT}/m_bayah.json","w"), indent=0)
        m.close()
    if any(w in WHAT for w in ("desk","t3d")):
        ctx = br.new_context(viewport={"width":1280,"height":720}, device_scale_factor=1.5, locale="id-ID")
        ctx.add_init_script(HOOK)
        pg = login(ctx, "dev_admin")
        if "desk" in WHAT:
            for name, h, wait in [("citra","citra",7),("citra_s1","citra/sentinel-1",7),("forecast","forecast",9),("kejadian","kejadian",7),
                                  ("laporan","laporan/keadaan-aoi",5),("data","data",5),("beranda","beranda",6)]:
                pg.goto(B+"/app#"+h); time.sleep(wait)
                print(name, pg.evaluate("location.hash"))
                pg.screenshot(path=f"{OUT}/d_{name}.png")
            pg.get_by_text("Bayah", exact=True).first.click(); time.sleep(8)
            pg.screenshot(path=f"{OUT}/d_bayah_full.png", full_page=True)
            pg.goto(B+"/docs"); time.sleep(6); pg.screenshot(path=f"{OUT}/d_docs.png")
        if "t3d" in WHAT:
            pg.goto(B+"/app#aoi-3d"); time.sleep(14)
            print("map?", pg.evaluate("!!window.__map"))
            try: pg.get_by_text("Pas ke area", exact=True).click(); time.sleep(5)
            except Exception as e: print("pas", e)
            st = pg.evaluate("(()=>{const m=window.__map;return {z:m.getZoom(),c:m.getCenter(),b:m.getBearing(),p:m.getPitch()}})()"); print(st)
            N = int(sys.argv[3]) if len(sys.argv)>3 else 150
            for i in range(N):
                u = i/(N-1); e = u*u*(3-2*u)
                pg.evaluate("""([b,z,pt]) => new Promise(res=>{const m=window.__map; m.jumpTo({bearing:b,zoom:z,pitch:pt}); let done=false; const f=()=>{if(!done){done=true;res(1)}}; m.once('idle',f); setTimeout(f,4000);})""",
                            [-28+56*e, st["z"]+0.25+0.35*e, 62])
                pg.screenshot(path=f"{OUT}/t3d/f{i:04d}.jpg", type="jpeg", quality=93)
                if i%25==0: print("f",i, flush=True)
    br.close()
