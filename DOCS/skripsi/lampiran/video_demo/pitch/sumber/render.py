import sys, subprocess, pathlib, time
S = pathlib.Path(sys.argv[1]); t0=float(sys.argv[2]); t1=float(sys.argv[3]); out=sys.argv[4]
mode = sys.argv[5] if len(sys.argv)>5 else "video"
sys.path.insert(0, str(S/"pylib"))
import imageio_ffmpeg
from playwright.sync_api import sync_playwright
FPS=30
CH = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
with sync_playwright() as p:
    br = p.chromium.launch(executable_path=CH, headless=True, args=["--headless=new","--allow-file-access-from-files","--hide-scrollbars","--force-color-profile=srgb"])
    pg = br.new_page(viewport={"width":1920,"height":1080}, device_scale_factor=1)
    pg.on("console", lambda m: print("[console]", m.text) if m.type in ("error","warning") else None)
    pg.on("pageerror", lambda e: print("[pageerror]", e))
    pg.goto((S/"film.html").as_uri()); pg.evaluate("window.ready")
    if mode == "stills":
        for t in [float(x) for x in out.split(",")]:
            pg.evaluate("t=>seek(t)", t); pg.screenshot(path=str(S/"shots"/f"st_{t:07.2f}.jpg"), type="jpeg", quality=80)
        br.close(); sys.exit()
    ff = subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(),"-y","-loglevel","error","-f","image2pipe","-framerate",str(FPS),"-c:v","mjpeg","-i","-",
        "-c:v","libx264","-preset","medium","-crf","15","-pix_fmt","yuv420p","-color_range","tv","-vf","scale=in_range=pc:out_range=tv","-r",str(FPS),out], stdin=subprocess.PIPE)
    n0=round(t0*FPS); n1=round(t1*FPS); st=time.time()
    for n in range(n0,n1):
        pg.evaluate("t=>seek(t)", n/FPS)
        ff.stdin.write(pg.screenshot(type="jpeg", quality=97))
        if (n-n0)%150==0: print(f"{out[-12:]} {n-n0}/{n1-n0} {time.time()-st:.0f}s", flush=True)
    ff.stdin.close(); ff.wait(); br.close(); print("done", out)
