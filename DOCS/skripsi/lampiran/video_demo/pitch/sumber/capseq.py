import sys, time, json, pathlib
from playwright.sync_api import sync_playwright
OUT = pathlib.Path(sys.argv[1]); WHAT = sys.argv[2].split(",")
B = "http://127.0.0.1:8011"
CH = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
FPS = 30
man = {}
def ease(u): return u*u*(3-2*u)
class Clip:
    def __init__(s, pg, name, sub): s.pg=pg; s.name=name; s.sub=sub; s.segs=[]; s.n=0; s.y=0; s.marks={}
    def snap(s):
        f=f"{s.sub}/{s.name}_{s.n:04d}.jpg"; s.n+=1
        s.pg.screenshot(path=str(OUT/f), type="jpeg", quality=92); return f
    def hold(s, dur): s.segs.append({"dur":dur,"frames":[s.snap()]})
    def scroll(s, y, dur):
        n=max(2,int(dur*FPS)); fr=[]
        for i in range(n):
            yy=s.y+(y-s.y)*ease(i/(n-1)); s.pg.evaluate("y=>window.scrollTo(0,y)", yy); fr.append(s.snap())
        s.y=y; s.segs.append({"dur":dur,"frames":fr})
    def jump(s, y): s.pg.evaluate("y=>window.scrollTo(0,y)", y); s.y=y; time.sleep(.4)
    def t(s): return sum(x["dur"] for x in s.segs)
    def mark(s, k, extra=None): s.marks[k]={"t":s.t(), **(extra or {})}
    def done(s): man[s.name]={"segs":s.segs,"marks":s.marks,"dur":s.t()}
def top(pg, sel): return pg.evaluate("s=>{const e=document.querySelector(s);return e?e.getBoundingClientRect().top+scrollY:null}", sel)
with sync_playwright() as p:
    br = p.chromium.launch(executable_path=CH, headless=True, args=["--headless=new","--hide-scrollbars"])
    if "mobile" in WHAT:
        m = br.new_context(viewport={"width":390,"height":844}, device_scale_factor=2, is_mobile=True, has_touch=True, locale="id-ID")
        pg = m.new_page(); pg.goto(B+"/app#beranda"); time.sleep(7)
        a = Clip(pg,"mobA","mob"); a.hold(1.4)
        row = pg.get_by_text("Bayah", exact=True).first
        ry = row.evaluate("e=>e.getBoundingClientRect().top+scrollY")
        a.scroll(ry-420, 1.6); a.hold(0.9)
        bb = row.bounding_box(); a.mark("tap", {"x":bb["x"]+60, "y":bb["y"]+bb["height"]/2})
        row.click(); time.sleep(8); pg.evaluate("y=>window.scrollTo(0,y)", a.y); time.sleep(.5)
        a.hold(0.8)
        ty = top(pg,"#hoPantauTitle"); a.scroll(ty-110, 1.5); a.hold(2.6)
        my = pg.evaluate("()=>{const e=document.querySelector('#pageRoot .leaflet-container');return e.getBoundingClientRect().top+scrollY}")
        a.scroll(my-150, 1.6); a.hold(2.0); a.done()
        c = Clip(pg,"mobC","mob"); dy = top(pg,"#hoDetail"); c.jump(dy-100); c.hold(1.2)
        rb = pg.get_by_text("MODIS (optik)").first; bb = rb.bounding_box()
        c.mark("tap", {"x":bb["x"]+10, "y":bb["y"]+bb["height"]/2}); rb.click(); time.sleep(6)
        pg.evaluate("y=>window.scrollTo(0,y)", c.y); time.sleep(.4); c.hold(0.9)
        iy = pg.evaluate("()=>{const e=document.querySelector('#hoDetail img');return e.getBoundingClientRect().top+scrollY}")
        c.scroll(iy-170, 1.6); c.hold(2.8)
        sy = top(pg,"#hoStatsTitle"); c.scroll(sy-110, 1.6); c.hold(1.2)
        H = pg.evaluate("document.documentElement.scrollHeight"); c.scroll(min(sy+620, H-844), 2.6); c.hold(1.6); c.done()
        print("mobile", a.t(), c.t(), a.n, c.n)
    if "mail" in WHAT:
        m = br.new_context(viewport={"width":390,"height":844}, device_scale_factor=2, is_mobile=True, has_touch=True, locale="id-ID")
        pg2 = m.new_page(); pg2.goto((OUT.parent/"mailview.html").as_uri()); time.sleep(2)
        e = Clip(pg2,"mail","mail"); e.hold(1.6)
        H = pg2.evaluate("document.documentElement.scrollHeight"); print("mail H", H)
        y1 = min(520, H-844); e.scroll(y1, 2.0); e.hold(2.2)
        y2 = min(1250, H-844); e.scroll(y2, 2.4); e.hold(2.0)
        if H-844 > y2+100: e.scroll(H-844, 2.4); e.hold(1.4)
        e.done(); print("mail", e.t(), e.n)
    json.dump(man, open(OUT/("man_"+"_".join(WHAT)+".json"),"w"))
    br.close()
