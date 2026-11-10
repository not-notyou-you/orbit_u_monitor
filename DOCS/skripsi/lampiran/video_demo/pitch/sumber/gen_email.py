import sys, base64, re
from datetime import date, timedelta
sys.path.insert(0, r"D:\NOT-NOTYOU-YOU\themonitor")
from sqlalchemy import text
from etl.database_client import DatabaseClient
from etl import notify as n
from etl.mailer import MailConfig
db = DatabaseClient.from_env("etl")
cfg = MailConfig.from_env()
rid = 3
n.ld.sync_thresholds(db)
with db.session() as s:
    conds = n.ld.conditions(s, [rid])
    units = dict(s.execute(text("SELECT band_code, unit FROM spectral_bands")).all())
    c = conds[rid]; items = c["abnormal"]
    print("abnormal:", [(a["key"], a.get("date")) for a in items])
    imgs, scene_date = n._images(db, s, rid, items, {})
    block = {"region": c["region"], "status": c["status"], "items": items, "latest": c["latest"],
             "prev": c["prev"], "ranges": c["ranges"], "scene_date": scene_date, "images": imgs}
    subject, body_t, body_h, images = n.alert_message("Hakim Hakim", [block], cfg, units, n.bc.thresholds)
print(subject); print(len(images), type(images[0]) if images else None)
for im in images:
    cid, png = im[0], im[-1]
    body_h = body_h.replace("cid:"+cid, "data:image/png;base64,"+base64.b64encode(png).decode())
open(sys.argv[1], "w", encoding="utf-8").write(body_h)
open(sys.argv[1]+".subject.txt", "w", encoding="utf-8").write(subject)
