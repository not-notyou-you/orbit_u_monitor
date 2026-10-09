#!/usr/bin/env python
"""Benchmark lanjutan PostgreSQL vs MySQL 8.0 — melengkapi run.py (Q1–Q5, F1–F3).

Dijalankan SETELAH `run.py --engine all`, karena memakai database
`themonitor_bench` yang sudah dimuat run.py di kedua DBMS.

    E3  Tulis (beban ETL): insert batch 50.000 baris dan upsert 20.000 baris
        (separuh konflik), keduanya INSERT multi-baris per 1.000 baris —
        metode yang sama di kedua DBMS. 3 ulangan, median.
    E2  Konkurensi: 1/4/8/16 klien, masing-masing koneksi sendiri, campuran
        Q1 (tanggal acak) dan Q2 (kecamatan + jendela acak) selama 10 detik.
        Throughput (kueri/detik) dan latensi median/p95.
    E1  Skalabilitas: observations ×1 → ×10 → ×30 (salinan bergeser 3 tahun),
        ANALYZE, lalu Q1, Q2, Q6 (agregasi bulanan seluruh tabel) dan ukuran
        tabel + index.

Keluaran: results/extended_write.csv, extended_concurrency.csv,
extended_scaling.csv. E1 mengubah tabel observations di DB benchmark;
jalankan run.py lagi untuk kembali ke ×1.

Pakai:  python benchmark/extended.py   (MySQL dari BENCH_MYSQL_*, seperti run.py)
"""

from __future__ import annotations

import os
import random
import statistics
import sys
import threading
import time
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run as R  # noqa: E402

DB = R.DB
SCALES = [1, 10, 30]
CLIENTS = [1, 4, 8, 16]
CONC_SECONDS = 10
SHIFT_DAYS = 1096  # 3 tahun: salinan ke-k bergeser k × 1096 hari, UNIQUE tetap terjaga


# --------------------------------------------------------------------------- koneksi
def pg_connect():
    import psycopg2
    c = psycopg2.connect(dbname=DB, **R.pg_conninfo())
    c.cursor().execute("SET search_path = bench, public")
    c.commit()  # tanpa commit, rollback() pertama ikut membatalkan SET
    return c


def my_connect():
    import pymysql
    return pymysql.connect(host=os.getenv("BENCH_MYSQL_HOST", "127.0.0.1"),
                           port=int(os.getenv("BENCH_MYSQL_PORT", "3306")),
                           user=os.getenv("BENCH_MYSQL_USER", "root"),
                           password=os.getenv("BENCH_MYSQL_PASSWORD", ""), database=DB, autocommit=False)


def my_connect_c():
    """mysqlclient (driver C, setara psycopg2) — memisahkan efek driver dari efek DBMS."""
    import MySQLdb
    c = MySQLdb.connect(host=os.getenv("BENCH_MYSQL_HOST", "127.0.0.1"),
                        port=int(os.getenv("BENCH_MYSQL_PORT", "3306")),
                        user=os.getenv("BENCH_MYSQL_USER", "root"),
                        password=os.getenv("BENCH_MYSQL_PASSWORD", ""), database=DB)
    c.autocommit(False)
    return c


ENGINES = {"PostgreSQL": pg_connect, "MySQL 8.0": my_connect}
if os.getenv("BENCH_MYSQL_DRIVER") == "mysqlclient":
    ENGINES = {"PostgreSQL": pg_connect, "MySQL 8.0 (mysqlclient)": my_connect_c}

# Kueri dengan teks yang sama di kedua dialek (tanpa skema; search_path/database sudah diatur).
Q1 = """SELECT r.region_id, r.region_name,
       max(CASE WHEN o.band_code = 'RAIN_24H' THEN o.value END), max(CASE WHEN o.band_code = 'RAIN_72H' THEN o.value END),
       max(CASE WHEN o.band_code = 'RAIN_7D' THEN o.value END), max(CASE WHEN o.band_code = 'RAIN_30D' THEN o.value END),
       max(CASE WHEN o.band_code = 'NDVI' THEN o.value END)
FROM regions r JOIN observations o ON o.region_id = r.region_id AND o.obs_date = %(d)s
WHERE r.in_aoi GROUP BY r.region_id, r.region_name ORDER BY r.region_name"""
Q2 = """SELECT obs_date, value FROM observations
WHERE region_id = %(r)s AND band_code = 'RAIN_24H' AND obs_date BETWEEN %(a)s AND %(z)s ORDER BY obs_date"""
Q6 = """SELECT region_id, EXTRACT(YEAR FROM obs_date) AS y, EXTRACT(MONTH FROM obs_date) AS m, avg(value), max(value)
FROM observations WHERE band_code = 'RAIN_24H' GROUP BY region_id, EXTRACT(YEAR FROM obs_date), EXTRACT(MONTH FROM obs_date)"""


def p95(xs):
    return R.p95(xs)


def aoi_regions(conn) -> list[int]:
    cur = conn.cursor()
    cur.execute("SELECT region_id FROM regions WHERE in_aoi ORDER BY region_id")
    ids = [r[0] for r in cur.fetchall()]
    conn.rollback()
    return ids


def rand_params(rng: random.Random, regions: list[int], days: int) -> tuple[str, dict]:
    start = date(2023, 1, 1)
    if rng.random() < 0.5:
        return Q1, {"d": (start + timedelta(days=rng.randrange(days))).isoformat()}
    a = start + timedelta(days=rng.randrange(days - 30))
    return Q2, {"r": rng.choice(regions), "a": a.isoformat(), "z": (a + timedelta(days=29)).isoformat()}


# --------------------------------------------------------------------------- E3 tulis
def ingest_rows(n: int, offset: int) -> list[tuple]:
    rng = random.Random(7 + offset)
    start = date(2030, 1, 1)
    bands = ["RAIN_24H", "RAIN_72H", "RAIN_7D", "RAIN_30D", "NDVI", "NDWI", "FLOOD"]
    # Kunci diturunkan dari id global j: (region, band, tanggal) unik untuk setiap j
    return [(j, 1 + j % 28, bands[(j // 28) % 7], (start + timedelta(days=j // 196)).isoformat(),
             round(rng.uniform(0, 200), 4), "FINAL") for j in range(offset, offset + n)]


def e3_write() -> list[dict]:
    out = []
    ddl = """CREATE TABLE ingest (obs_id bigint PRIMARY KEY, region_id int NOT NULL, band_code varchar(10) NOT NULL,
             obs_date date NOT NULL, value numeric(10,4), run_type varchar(5), UNIQUE (region_id, band_code, obs_date))"""
    rows = ingest_rows(50_000, 0)
    upd = [(r[0], r[1], r[2], r[3], r[4] + 1, r[5]) for r in rows[:10_000]] + ingest_rows(10_000, 50_000)
    for eng, connect in ENGINES.items():
        conn = connect()
        cur = conn.cursor()
        ins_s, ups_s = [], []
        for _ in range(3):
            cur.execute("DROP TABLE IF EXISTS ingest")
            cur.execute(ddl)
            conn.commit()
            t = time.perf_counter()
            if eng == "PostgreSQL":
                from psycopg2.extras import execute_values
                execute_values(cur, "INSERT INTO ingest VALUES %s", rows, page_size=1000)
            else:
                for i in range(0, len(rows), 1000):
                    cur.executemany("INSERT INTO ingest VALUES (%s,%s,%s,%s,%s,%s)", rows[i:i + 1000])
            conn.commit()
            ins_s.append(time.perf_counter() - t)
            t = time.perf_counter()
            if eng == "PostgreSQL":
                execute_values(cur, """INSERT INTO ingest VALUES %s ON CONFLICT (obs_id)
                                       DO UPDATE SET value = EXCLUDED.value""", upd, page_size=1000)
            else:
                for i in range(0, len(upd), 1000):
                    # VALUES(col) (bukan alias "AS new"): hanya bentuk ini yang ditulis ulang
                    # pymysql menjadi INSERT multi-baris; alias membuatnya per baris.
                    cur.executemany("""INSERT INTO ingest VALUES (%s,%s,%s,%s,%s,%s)
                                       ON DUPLICATE KEY UPDATE value = VALUES(value)""", upd[i:i + 1000])
            conn.commit()
            ups_s.append(time.perf_counter() - t)
        cur.execute("SELECT count(*) FROM ingest")
        n = cur.fetchone()[0]
        cur.execute("DROP TABLE ingest")
        conn.commit()
        conn.close()
        for test, xs, k in (("Insert batch 50.000 baris", ins_s, 50_000), ("Upsert 20.000 baris (50% konflik)", ups_s, 20_000)):
            med = statistics.median(xs)
            out.append({"engine": eng, "test": test, "runs": len(xs), "median_s": round(med, 3),
                        "rows_per_s": round(k / med), "final_rows": n})
            print(f"E3 {eng}: {test}: {med:.3f} s ({k / med:,.0f} baris/s)")
    return out


# --------------------------------------------------------------------------- E2 konkurensi
def e2_concurrency() -> list[dict]:
    out = []
    for eng, connect in ENGINES.items():
        c0 = connect()
        regions = aoi_regions(c0)
        c0.close()
        for n in CLIENTS:
            lat: list[float] = []
            errs = [0]
            lock = threading.Lock()
            stop = time.perf_counter() + CONC_SECONDS + 1  # 1 detik pertama pemanasan, tidak dihitung
            t_measure = stop - CONC_SECONDS

            def worker(seed: int):
                conn = connect()
                cur = conn.cursor()
                rng = random.Random(seed)
                mine = []
                while (now := time.perf_counter()) < stop:
                    sql, params = rand_params(rng, regions, 3 * 365)
                    t = time.perf_counter()
                    try:
                        cur.execute(sql, params)
                        cur.fetchall()
                        conn.rollback()
                    except Exception:  # noqa: BLE001
                        errs[0] += 1
                        conn.rollback()
                        continue
                    if t >= t_measure:
                        mine.append((time.perf_counter() - t) * 1000)
                conn.close()
                with lock:
                    lat.extend(mine)

            ths = [threading.Thread(target=worker, args=(1000 * n + i,)) for i in range(n)]
            for th in ths:
                th.start()
            for th in ths:
                th.join()
            qps = len(lat) / CONC_SECONDS
            out.append({"engine": eng, "clients": n, "seconds": CONC_SECONDS, "queries": len(lat), "qps": round(qps, 1),
                        "median_ms": round(statistics.median(lat), 3), "p95_ms": round(p95(lat), 3), "errors": errs[0]})
            print(f"E2 {eng}: {n:2d} klien → {qps:8.1f} kueri/s, p95 {out[-1]['p95_ms']} ms, galat {errs[0]}")
    return out


# --------------------------------------------------------------------------- E1 skalabilitas
def grow(eng: str, conn, frm: int, to: int) -> float:
    cur = conn.cursor()
    t = time.perf_counter()
    for k in range(frm, to):
        if eng == "PostgreSQL":
            cur.execute("""INSERT INTO observations SELECT obs_id + %(k)s * 10000000, region_id, band_code,
                           obs_date + %(k)s * 1096, value, run_type FROM observations WHERE obs_id < 10000000""", {"k": k})
        else:
            cur.execute("""INSERT INTO observations SELECT obs_id + %(k)s * 10000000, region_id, band_code,
                           DATE_ADD(obs_date, INTERVAL %(k)s * 1096 DAY), value, run_type FROM observations
                           WHERE obs_id < 10000000""", {"k": k})
        conn.commit()
    cur.execute("ANALYZE observations" if eng == "PostgreSQL" else "ANALYZE TABLE observations")
    cur.fetchall() if eng != "PostgreSQL" else None
    conn.commit()
    return time.perf_counter() - t


def size_mb(eng: str, conn) -> tuple[float, float]:
    cur = conn.cursor()
    if eng == "PostgreSQL":
        cur.execute("SELECT pg_relation_size('bench.observations'), pg_indexes_size('bench.observations')")
    else:
        cur.execute("""SELECT data_length, index_length FROM information_schema.tables
                       WHERE table_schema = %s AND table_name = 'observations'""", (DB,))
    d, i = cur.fetchone()
    conn.rollback()
    return round(d / 2**20, 1), round(i / 2**20, 1)


def timed(cur, conn, sql, params, warm=3, runs=15) -> tuple[list[float], int]:
    for _ in range(warm):
        cur.execute(sql, params)
        cur.fetchall()
    ms, n = [], 0
    for _ in range(runs):
        t = time.perf_counter()
        cur.execute(sql, params)
        n = len(cur.fetchall())
        ms.append((time.perf_counter() - t) * 1000)
    conn.rollback()
    return ms, n


def e1_scaling() -> list[dict]:
    out = []
    for eng, connect in ENGINES.items():
        conn = connect()
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM observations WHERE obs_id >= 10000000")
        if cur.fetchone()[0]:
            sys.exit(f"{eng}: observations sudah diperbesar; jalankan run.py --engine all dulu.")
        conn.rollback()
        prev = 1
        for s in SCALES:
            grow_s = grow(eng, conn, prev, s) if s > prev else 0.0
            prev = s
            cur.execute("SELECT count(*) FROM observations")
            total = cur.fetchone()[0]
            conn.rollback()
            data_mb, idx_mb = size_mb(eng, conn)
            for q, sql, params in (("Q1", Q1, {"d": "2024-12-15"}),
                                   ("Q2", Q2, {"r": 9, "a": "2024-11-16", "z": "2024-12-15"}),
                                   ("Q6", Q6, {})):
                ms, n = timed(cur, conn, sql, params)
                out.append({"engine": eng, "scale": s, "rows": total, "query": q, "result_rows": n,
                            "median_ms": round(statistics.median(ms), 3), "p95_ms": round(p95(ms), 3),
                            "data_mb": data_mb, "index_mb": idx_mb, "grow_seconds": round(grow_s, 1)})
                print(f"E1 {eng} ×{s} ({total:,} baris): {q} median {out[-1]['median_ms']} ms, {n} baris")
        conn.close()
    return out


def main() -> int:
    # BENCH_TESTS=e2,e3 membatasi uji; BENCH_SUFFIX membedakan berkas keluaran (mis. _mysqlclient)
    tests = os.getenv("BENCH_TESTS", "e1,e2,e3").split(",")
    sfx = os.getenv("BENCH_SUFFIX", "")
    R.RESULTS.mkdir(exist_ok=True)
    if "e3" in tests:
        R.write_csv(R.RESULTS / f"extended_write{sfx}.csv", e3_write())
    if "e2" in tests:
        R.write_csv(R.RESULTS / f"extended_concurrency{sfx}.csv", e2_concurrency())
    if "e1" in tests:
        R.write_csv(R.RESULTS / f"extended_scaling{sfx}.csv", e1_scaling())
    print(f"Hasil di {R.RESULTS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
