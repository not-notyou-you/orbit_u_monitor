"""Bangkitkan assets/data.js untuk halaman visual skripsi.

Sumber: DOCS/generated/data_dictionary.md (dari skema), DOCS/generated/erd_physical.mmd (relasi),
benchmark/results/*.csv, DOCS/hasil_uji/pytest.xml, dan jumlah baris dari database (kalau bisa terhubung).

    venv\\Scripts\\python DOCS\\for_skripsi\\build_data.py
"""
import csv
import json
import os
import re
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
GEN = ROOT / "DOCS" / "generated"


def cell(s):
    s = s.strip()
    if s.startswith("`") and s.endswith("`"):
        s = s[1:-1]
    return s


def split_row(line):
    return [cell(c) for c in line.strip().strip("|").split("|")]


def parse_dictionary():
    text = (GEN / "data_dictionary.md").read_text(encoding="utf-8")
    tables, views = {}, []
    sections = re.split(r"^## ", text, flags=re.M)
    for sec in sections[1:]:
        title, _, body = sec.partition("\n")
        title = title.strip()
        if title == "VIEW":
            for line in body.splitlines():
                if line.startswith("| `v_"):
                    name, cols, desc = split_row(line)
                    views.append({"name": name, "cols": [c.strip(" `") for c in cols.split(",")], "desc": desc})
            continue
        if title == "Daftar tabel" or " " in title:
            continue
        lines = body.strip().splitlines()
        desc = lines[0].strip() if lines else ""
        cols, cons = [], []
        for line in lines:
            if line.startswith("| `") and line.count("|") >= 7:
                n, t, nul, d, k, ds = split_row(line)[:6]
                cols.append({"n": n, "t": t, "nn": nul == "NOT NULL", "d": d, "k": k, "ds": ds})
            m = re.match(r"- `([^`]+)` \(([A-Z]+)\): `(.*)`$", line.strip())
            if m:
                cons.append({"n": m.group(1), "type": m.group(2), "def": m.group(3)})
        tables[title] = {"desc": desc, "cols": cols, "cons": cons}
    return tables, views


def parse_relations():
    rels = []
    for line in (GEN / "erd_physical.mmd").read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*(\w+) (\|\||\|o)--(o\{|\|\{) (\w+) : \"(\w+)\"", line)
        if m:
            rels.append({"parent": m.group(1), "child": m.group(4), "fk": m.group(5),
                         "mandatory": m.group(3) == "|{"})
    return rels


def read_csv(name):
    p = ROOT / "benchmark" / "results" / name
    if not p.exists():
        return []
    with p.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def pytest_summary():
    p = ROOT / "DOCS" / "hasil_uji" / "pytest.xml"
    if not p.exists():
        return {}
    root = ET.parse(p).getroot()
    suite = root.find("testsuite") if root.tag == "testsuites" else root
    per = Counter()
    failed = Counter()
    skipped = Counter()
    for tc in suite.iter("testcase"):
        mod = tc.get("classname", "").split(".")
        key = next((m for m in mod if m.startswith("test_")), mod[-1] if mod else "?")
        per[key] += 1
        if tc.find("failure") is not None or tc.find("error") is not None:
            failed[key] += 1
        if tc.find("skipped") is not None:
            skipped[key] += 1
    return {
        "tests": int(suite.get("tests", 0)), "failures": int(suite.get("failures", 0)),
        "errors": int(suite.get("errors", 0)), "skipped": int(suite.get("skipped", 0)),
        "time": float(suite.get("time", 0)), "timestamp": suite.get("timestamp", ""),
        "files": [{"file": k, "n": v, "fail": failed[k], "skip": skipped[k]} for k, v in per.most_common()],
    }


def row_counts():
    try:
        import psycopg2
        env = {}
        for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
        conn = psycopg2.connect(host=env.get("DB_HOST", "localhost"), port=env.get("DB_PORT", "5432"),
                                dbname=env.get("DB_NAME", "themonitor"), user=env.get("DB_USER"),
                                password=env.get("DB_PASSWORD"))
        cur = conn.cursor()
        cur.execute("select tablename from pg_tables where schemaname='public' and tablename<>'spatial_ref_sys'")
        out = {}
        for (t,) in cur.fetchall():
            cur.execute(f'select count(*) from "{t}"')
            out[t] = cur.fetchone()[0]
        cur.execute("select region_name from administrative_regions where in_aoi order by 1")
        aoi = [r[0] for r in cur.fetchall()]
        cur.execute("select min(obs_date)::text, max(obs_date)::text from region_observations")
        rng = cur.fetchone()
        cur.execute("""select tablename, indexname, indexdef from pg_indexes
                       where schemaname='public' and tablename<>'spatial_ref_sys' order by 1, 2""")
        indexes = [{"t": t, "n": n, "def": d} for t, n, d in cur.fetchall()]
        cur.execute("""select grantee, table_name, string_agg(privilege_type, ',' order by privilege_type)
                       from information_schema.role_table_grants
                       where table_schema='public' and grantee like 'monitor\\_%'
                       group by 1, 2 order by 2, 1""")
        grants = [{"role": g, "obj": t, "priv": p} for g, t, p in cur.fetchall()]
        cur.execute("""select grantee, table_name, column_name, privilege_type
                       from information_schema.column_privileges
                       where table_schema='public' and grantee like 'monitor\\_%' and privilege_type='UPDATE'
                         and (grantee, table_name) not in (select grantee, table_name from information_schema.role_table_grants
                                                           where privilege_type='UPDATE' and table_schema='public')
                       order by 2, 1, 3""")
        colgrants = [{"role": g, "obj": t, "col": c, "priv": p} for g, t, c, p in cur.fetchall()]
        cur.execute("""select r.rolname, m.rolname from pg_auth_members am join pg_roles r on r.oid=am.roleid
                       join pg_roles m on m.oid=am.member where r.rolname like 'monitor\\_%' and m.rolname like 'monitor\\_%'""")
        members = [{"role": r, "member": m} for r, m in cur.fetchall()]
        cur.execute("""select tablename, policyname, cmd, array_to_string(roles, ','), coalesce(qual, ''), coalesce(with_check, '')
                       from pg_policies where schemaname='public' order by 1, 2""")
        policies = [{"t": t, "n": n, "cmd": c, "roles": r, "using": q, "check": w} for t, n, c, r, q, w in cur.fetchall()]
        cur.execute("""select event_object_table, trigger_name, string_agg(event_manipulation, '/' order by event_manipulation),
                              action_timing, action_statement
                       from information_schema.triggers where trigger_schema='public'
                       group by 1, 2, 4, 5 order by 1, 2""")
        triggers = [{"t": t, "n": n, "ev": e, "timing": ti, "stmt": s} for t, n, e, ti, s in cur.fetchall()]
        conn.close()
        return {"counts": out, "aoi": aoi, "obs_range": rng, "at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "indexes": indexes, "grants": grants, "colgrants": colgrants, "members": members,
                "policies": policies, "triggers": triggers}
    except Exception as e:  # database tidak wajib
        print("jumlah baris dilewati:", e)
        return None


def main():
    tables, views = parse_dictionary()
    data = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "tables": tables,
        "views": views,
        "rels": parse_relations(),
        "bench": {
            "timing": read_csv("timing.csv"),
            "features": read_csv("features.csv"),
            "scaling": read_csv("extended_scaling.csv"),
            # PERBANDINGAN_DBMS.md §3.4/§3.6 memakai run driver C (mysqlclient) untuk kedua DBMS
            "concurrency": read_csv("extended_concurrency_mysqlclient.csv"),
            "write": read_csv("extended_write_mysqlclient.csv"),
        },
        "pytest": pytest_summary(),
        "db": row_counts(),
    }
    out = HERE / "assets" / "data.js"
    out.parent.mkdir(exist_ok=True)
    out.write_text("window.SKRIPSI_DATA = " + json.dumps(data, ensure_ascii=False, indent=1) + ";\n",
                   encoding="utf-8")
    print(f"{out}: {len(tables)} tabel, {len(views)} VIEW, {len(data['rels'])} relasi")


if __name__ == "__main__":
    main()
