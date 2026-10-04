#!/usr/bin/env python
"""Benchmark DBMS Orbit-U: The Monitor (DATABASE.md §1, M29).

PostgreSQL + PostGIS vs MySQL 8.0 pada data sintetis yang sama (benchmark/generate.py):
Q1–Q5 (5 kali pemanasan, 30 kali ukur → median & p95, EXPLAIN disimpan) dan
uji fitur keamanan F1–F3. MongoDB 7 dinilai dari fitur saja.

Database yang dipakai SELALU terpisah dari produksi:
    PostgreSQL : database `themonitor_bench` (dibuat ulang), skema `bench`
    MySQL 8.0  : schema/database `themonitor_bench` (dibuat ulang)
Skrip menolak nama database `themonitor`.

Koneksi:
    PostgreSQL : BENCH_PG_URL atau DB_HOST/DB_PORT/DB_USER/DB_PASSWORD dari .env (superuser, untuk CREATE DATABASE)
    MySQL      : BENCH_MYSQL_HOST/PORT/USER/PASSWORD (driver: pymysql). Tanpa server/driver → baris
                 MySQL ditulis status "belum dijalankan" dengan alasannya.

Keluaran: benchmark/results/timing.csv, features.csv, environment.json, explain_<engine>_<Q>.txt

Pakai:
    python benchmark/generate.py
    python benchmark/run.py --engine all       # atau pg / mysql
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import engines as E  # noqa: E402

DATA, RESULTS = HERE / "data", HERE / "results"
DB = "themonitor_bench"
WARMUP, RUNS = 5, 30


def guard(name: str) -> None:
    if name == "themonitor":
        sys.exit("DITOLAK: benchmark tidak boleh memakai DB produksi `themonitor`.")


def p95(xs: list[float]) -> float:
    s = sorted(xs)
    k = 0.95 * (len(s) - 1)
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def time_query(cur, sql: str, params: dict) -> tuple[list[float], int]:
    for _ in range(WARMUP):
        cur.execute(sql, params)
        cur.fetchall()
    ms, n = [], 0
    for _ in range(RUNS):
        t = time.perf_counter()
        cur.execute(sql, params)
        n = len(cur.fetchall())
        ms.append((time.perf_counter() - t) * 1000)
    return ms, n


# --------------------------------------------------------------------------- PostgreSQL
def pg_conninfo() -> dict:
    from dotenv import load_dotenv
    load_dotenv(HERE.parent / ".env")
    return {"host": os.getenv("DB_HOST", "localhost"), "port": int(os.getenv("DB_PORT", "5432")),
            "user": os.getenv("DB_USER", "postgres"), "password": os.getenv("DB_PASSWORD", "")}


def run_pg() -> tuple[list[dict], list[dict], dict]:
    import psycopg2
    guard(DB)
    ci = pg_conninfo()
    admin = psycopg2.connect(dbname="postgres", **ci)
    admin.autocommit = True
    cur = admin.cursor()
    cur.execute(f"DROP DATABASE IF EXISTS {DB}")
    cur.execute(f"CREATE DATABASE {DB}")
    admin.close()
    conn = psycopg2.connect(dbname=DB, **ci)
    t = time.perf_counter()
    counts = E.pg_load(conn, DATA)
    load_s = time.perf_counter() - t
    cur = conn.cursor()
    cur.execute("SELECT version(), postgis_full_version()")
    ver, gis = cur.fetchone()
    pid = E.pg_deep_product(conn)
    timing = []
    for q, (desc, sql, params) in E.PG_QUERIES.items():
        params = dict(params)
        if "pid" in params:
            params["pid"] = pid
        ms, n = time_query(cur, sql, params)
        cur.execute("EXPLAIN (ANALYZE, BUFFERS) " + sql, params)
        (RESULTS / f"explain_postgresql_{q}.txt").write_text("\n".join(r[0] for r in cur.fetchall()), encoding="utf-8")
        timing.append({"engine": "PostgreSQL", "query": q, "description": desc, "status": "dijalankan", "rows": n,
                       "runs": RUNS, "median_ms": round(statistics.median(ms), 3), "p95_ms": round(p95(ms), 3),
                       "min_ms": round(min(ms), 3), "max_ms": round(max(ms), 3)})
        print(f"PostgreSQL {q}: median {timing[-1]['median_ms']} ms, p95 {timing[-1]['p95_ms']} ms, {n} baris")
    conn.rollback()
    features = [dict(engine="PostgreSQL", **f) for f in E.pg_features(conn)]
    conn.close()
    env = {"version": ver.split(",")[0], "postgis": gis.split(" ")[1].strip('"') if gis else None,
           "database": DB, "load_seconds": round(load_s, 2), "row_counts": counts, "q5_product_id": pid}
    return timing, features, env


# --------------------------------------------------------------------------- MySQL
def run_mysql() -> tuple[list[dict], list[dict], dict]:
    not_run = lambda why: ([{"engine": "MySQL 8.0", "query": q, "description": E.PG_QUERIES[q][0], "status": "belum dijalankan",  # noqa: E731
                             "note": why} for q in E.PG_QUERIES],
                           [{"engine": "MySQL 8.0", "feature": f, "name": n, "result": "belum dijalankan", "evidence": why}
                            for f, n in [("F1", "SET ROLE per transaksi"), ("F2", "Row-level security"),
                                         ("F3", "Trigger audit OLD/NEW sebagai JSON")]],
                           {"status": "belum dijalankan", "reason": why})
    try:
        import pymysql
    except ImportError:
        return not_run("driver pymysql belum terpasang")
    host = os.getenv("BENCH_MYSQL_HOST", "127.0.0.1")
    kw = {"host": host, "port": int(os.getenv("BENCH_MYSQL_PORT", "3306")), "user": os.getenv("BENCH_MYSQL_USER", "root"),
          "password": os.getenv("BENCH_MYSQL_PASSWORD", ""), "autocommit": False}
    try:
        admin = pymysql.connect(**kw)
    except Exception as e:  # noqa: BLE001
        return not_run(f"server MySQL tidak terjangkau di {host}: {e}")
    cur = admin.cursor()
    cur.execute("SELECT VERSION()")
    ver = cur.fetchone()[0]
    if "MariaDB" in ver or not ver.startswith("8."):
        return not_run(f"server bukan MySQL 8.0 ({ver}); hasil tidak setara")
    guard(DB)
    cur.execute(f"DROP DATABASE IF EXISTS {DB}")
    cur.execute(f"CREATE DATABASE {DB}")
    admin.close()
    conn = pymysql.connect(database=DB, **kw)
    t = time.perf_counter()
    counts = E.mysql_load(conn, DATA)
    load_s = time.perf_counter() - t
    cur = conn.cursor()
    cur.execute("SELECT product_id FROM data_products WHERE product_tier = 'DERIVED' ORDER BY product_id LIMIT 1")
    pid = cur.fetchone()[0]
    timing = []
    for q, sql in E.MYSQL_QUERIES.items():
        params = dict(E.PG_QUERIES[q][2])
        if "pid" in params:
            params["pid"] = pid
        ms, n = time_query(cur, sql, params)
        cur.execute("EXPLAIN ANALYZE " + sql, params)
        (RESULTS / f"explain_mysql_{q}.txt").write_text("\n".join(str(r[0]) for r in cur.fetchall()), encoding="utf-8")
        timing.append({"engine": "MySQL 8.0", "query": q, "description": E.PG_QUERIES[q][0], "status": "dijalankan", "rows": n,
                       "runs": RUNS, "median_ms": round(statistics.median(ms), 3), "p95_ms": round(p95(ms), 3),
                       "min_ms": round(min(ms), 3), "max_ms": round(max(ms), 3)})
        print(f"MySQL {q}: median {timing[-1]['median_ms']} ms, p95 {timing[-1]['p95_ms']} ms, {n} baris")
    features = [dict(engine="MySQL 8.0", **f) for f in E.mysql_features(conn, DB)]
    conn.close()
    return timing, features, {"version": ver, "database": DB, "load_seconds": round(load_s, 2), "row_counts": counts}


# --------------------------------------------------------------------------- lingkungan
def machine() -> dict:
    info = {"os": platform.platform(), "python": platform.python_version(), "cpu": platform.processor(),
            "logical_cpus": os.cpu_count()}
    try:
        import psutil
        info["ram_gb"] = round(psutil.virtual_memory().total / 2**30, 1)
    except ImportError:
        if sys.platform == "win32":
            out = subprocess.run(["powershell", "-NoProfile", "-Command",
                                  "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory;"
                                  "(Get-CimInstance Win32_Processor | Select-Object -First 1).Name"],
                                 capture_output=True, text=True).stdout.split("\n")
            info["ram_gb"] = round(int(out[0].strip()) / 2**30, 1) if out and out[0].strip().isdigit() else None
            if len(out) > 1 and out[1].strip():
                info["cpu"] = out[1].strip()
    return info


def write_csv(path: Path, rows: list[dict]) -> None:
    keys = []
    for r in rows:
        keys += [k for k in r if k not in keys]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", choices=["pg", "mysql", "all"], default="all")
    a = ap.parse_args(argv)
    if not (DATA / "meta.json").exists():
        sys.exit("Jalankan dulu: python benchmark/generate.py")
    RESULTS.mkdir(exist_ok=True)
    timing, features = [], []
    env = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "machine": machine(),
           "method": {"warmup": WARMUP, "runs": RUNS, "statistic": "median dan p95 waktu eksekusi + fetch di klien"},
           "data": json.loads((DATA / "meta.json").read_text(encoding="utf-8")), "engines": {}}
    if a.engine in ("pg", "all"):
        t, f, e = run_pg()
        timing += t; features += f; env["engines"]["PostgreSQL"] = e
    if a.engine in ("mysql", "all"):
        t, f, e = run_mysql()
        timing += t; features += f; env["engines"]["MySQL 8.0"] = e
    features += [dict(engine="MongoDB 7 (fitur saja)", **f) for f in E.MONGODB_FEATURES]
    write_csv(RESULTS / "timing.csv", timing)
    write_csv(RESULTS / "features.csv", features)
    (RESULTS / "environment.json").write_text(json.dumps(env, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"Hasil di {RESULTS}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
