import json, urllib.request, sys
dois = dict(khan="10.3390/land12081514", wang="10.1007/s13753-025-00644-3", hidayah="10.2166/wpt.2024.240",
 ansori="10.3390/su18094550", kovacs="10.1038/s41597-026-06765-8", tarpanelli="10.5194/nhess-22-2473-2022",
 roman="10.1016/j.rse.2023.113963", zhu="10.1088/1748-9326/ad984e", liu="10.3390/rs15215125", castro="10.3390/rs17132145",
 weiss="10.21105/joss.03337", upadhyay="10.3390/rs14051120", dev="10.31018/jans.v15i4.5084", gopaluni="10.22399/ijcesen.4742",
 purwitasari="10.34151/script.v13i2.5464", tilung="10.1109/CONMEDIA67140.2025.11290328", wong="10.70609/gtech.v8i4.4763",
 kaptosv="10.37547/tajet/volume07issue08-28", papasani="10.7717/peerj-cs.3220", tran="10.3390/rs14225721",
 alonso="10.3390/rs17081368", misra="10.1038/s41467-025-60973-1", klein="10.1038/s41597-024-03328-7", tang="10.5194/essd-16-387-2024",
 skavantzos="10.1007/s00778-025-00902-2", zhang="10.1145/3725362", huang="10.1145/3575693.3575699", kanwal="10.14569/IJACSA.2025.0160696",
 ahmad="10.3390/electronics13234723", balsam="10.1016/j.jss.2024.112186", alyami="10.7717/peerj-cs.1444", halder="10.3390/su151411413")
out = {}
for k, d in dois.items():
    try:
        r = urllib.request.Request("https://api.crossref.org/works/" + d, headers={"User-Agent": "thesis-ref-check/1.0"})
        m = json.load(urllib.request.urlopen(r, timeout=30))["message"]
        out[k] = dict(doi=d, title=m.get("title", [""])[0], journal=(m.get("container-title") or [""])[0],
            authors=[(a.get("family", ""), a.get("given", "")) for a in m.get("author", [])], vol=m.get("volume"), no=m.get("issue"),
            pages=m.get("page"), art=m.get("article-number"), year=(m.get("published-print") or m.get("published-online") or m.get("issued"))["date-parts"][0][0], type=m.get("type"))
        print(k, "ok", len(out[k]["authors"]), out[k]["year"])
    except Exception as e:
        print(k, "FAIL", e)
json.dump(out, open("refs.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
