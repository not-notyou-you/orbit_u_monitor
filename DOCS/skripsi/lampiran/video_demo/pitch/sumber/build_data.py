import sys, json, glob
S = sys.argv[1].replace("\\","/")
man = {}
for f in ("man_mobile.json","man_mail.json"):
    man.update(json.load(open(S+"/assets/"+f)))
reg = json.load(open(S+"/assets/regions.json", encoding="utf-8"))
n = len(glob.glob(S+"/assets/t3d/*.jpg"))
open(S+"/assets/data.js","w",encoding="utf-8").write("window.DATA="+json.dumps({"man":man,"regions":reg,"t3d":n})+";")
print({k:round(v["dur"],1) for k,v in man.items()}, n)
