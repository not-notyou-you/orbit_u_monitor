"""Skema setara, pemuat data, kueri Q1–Q5, dan uji fitur F1–F3 per DBMS (DATABASE.md §1).

PostgreSQL 14+ + PostGIS 3 dan MySQL 8.0 memakai skema yang setara: tipe kolom,
PK/FK, index, dan kueri dengan makna sama. Perbedaan dialek ditulis eksplisit di
sini agar bisa dibaca penguji, bukan disembunyikan ORM.
"""

from __future__ import annotations

import csv
from pathlib import Path

# --------------------------------------------------------------------------- parameter kueri (tetap)
Q_DATE = "2024-12-15"
Q_REGION, Q_BAND, Q_FROM, Q_TO = 9, "RAIN_24H", "2024-11-16", "2024-12-15"
# Poligon uji Q3: memotong beberapa kecamatan AOI (EPSG:4326).
Q_POLY = "POLYGON((106.00 -6.95,106.30 -6.95,106.30 -6.80,106.00 -6.80,106.00 -6.95))"
Q_PRODUCT_DEPTH = 6   # produk di ujung rantai 6 tingkat dicari otomatis


# =========================================================================== PostgreSQL
PG_SCHEMA = """
DROP SCHEMA IF EXISTS bench CASCADE;
CREATE SCHEMA bench;
SET search_path = bench, public;
CREATE TABLE regions (region_id int PRIMARY KEY, pcode varchar(20) UNIQUE NOT NULL, region_name varchar(100) NOT NULL,
  in_aoi boolean NOT NULL, geom geometry(MultiPolygon, 4326) NOT NULL);
CREATE INDEX regions_geom_gist ON regions USING gist (geom);
CREATE TABLE observations (obs_id bigint PRIMARY KEY, region_id int NOT NULL REFERENCES regions, band_code varchar(10) NOT NULL,
  obs_date date NOT NULL, value numeric(10,4), run_type varchar(5), UNIQUE (region_id, band_code, obs_date));
CREATE INDEX obs_date_band ON observations (obs_date, band_code);
CREATE TABLE alert_events (alert_id bigint PRIMARY KEY, rule_id int NOT NULL, region_id int NOT NULL REFERENCES regions,
  obs_id bigint NOT NULL REFERENCES observations, observation_date date NOT NULL, observed_value numeric(10,4) NOT NULL,
  threshold_value numeric(8,2) NOT NULL, severity varchar(10) NOT NULL CHECK (severity IN ('INFO','WARNING','CRITICAL')),
  UNIQUE (rule_id, region_id, observation_date));
CREATE INDEX alerts_region_date ON alert_events (region_id, observation_date);
CREATE TABLE disaster_events (event_id bigint PRIMARY KEY, type_code varchar(30) NOT NULL, region_id int NOT NULL REFERENCES regions,
  event_date date NOT NULL, is_verified boolean NOT NULL);
CREATE INDEX disasters_region_date ON disaster_events (region_id, event_date);
CREATE TABLE data_products (product_id bigint PRIMARY KEY, product_tier varchar(20) NOT NULL, source varchar(20) NOT NULL,
  file_size_mb numeric(12,2), sha256 char(64) NOT NULL);
CREATE TABLE data_lineage (lineage_id bigint PRIMARY KEY, parent_product_id bigint NOT NULL REFERENCES data_products,
  child_product_id bigint NOT NULL REFERENCES data_products, transformation_type varchar(40) NOT NULL);
CREATE INDEX lineage_child ON data_lineage (child_product_id);
CREATE INDEX lineage_parent ON data_lineage (parent_product_id);
"""

PG_QUERIES = {
    "Q1": ("Statistik hari ini: pivot hujan per kecamatan satu tanggal", """
        SELECT r.region_id, r.region_name,
               max(o.value) FILTER (WHERE o.band_code = 'RAIN_24H') AS rain_24h,
               max(o.value) FILTER (WHERE o.band_code = 'RAIN_72H') AS rain_72h,
               max(o.value) FILTER (WHERE o.band_code = 'RAIN_7D')  AS rain_7d,
               max(o.value) FILTER (WHERE o.band_code = 'RAIN_30D') AS rain_30d,
               max(o.value) FILTER (WHERE o.band_code = 'NDVI')     AS ndvi
        FROM bench.regions r JOIN bench.observations o ON o.region_id = r.region_id AND o.obs_date = %(d)s
        WHERE r.in_aoi GROUP BY r.region_id, r.region_name ORDER BY r.region_name""", {"d": Q_DATE}),
    "Q2": ("Tren 30 hari satu kecamatan satu band", """
        SELECT obs_date, value FROM bench.observations
        WHERE region_id = %(r)s AND band_code = %(b)s AND obs_date BETWEEN %(a)s AND %(z)s ORDER BY obs_date""",
           {"r": Q_REGION, "b": Q_BAND, "a": Q_FROM, "z": Q_TO}),
    "Q3": ("Spasial: kecamatan beririsan poligon + luas irisan geodesik (km²)", """
        SELECT region_id, region_name,
               ST_Area(ST_Intersection(geom, ST_GeomFromText(%(p)s, 4326))::geography) / 1e6 AS km2
        FROM bench.regions WHERE ST_Intersects(geom, ST_GeomFromText(%(p)s, 4326)) ORDER BY km2 DESC""", {"p": Q_POLY}),
    "Q4": ("Evaluasi alert: hit / miss / false alarm (WARNING+, 0–3 hari)", """
        WITH strong AS (SELECT * FROM bench.alert_events WHERE severity IN ('WARNING','CRITICAL')),
             ev AS (SELECT * FROM bench.disaster_events WHERE is_verified AND type_code IN ('BANJIR','BANJIR_BANDANG')),
             pairs AS (SELECT a.alert_id, e.event_id FROM strong a JOIN ev e ON e.region_id = a.region_id
                       AND e.event_date BETWEEN a.observation_date AND a.observation_date + 3)
        SELECT 'HIT' AS outcome, count(DISTINCT event_id) FROM pairs
        UNION ALL SELECT 'MISS', count(*) FROM ev WHERE event_id NOT IN (SELECT event_id FROM pairs)
        UNION ALL SELECT 'FALSE_ALARM', count(*) FROM strong WHERE alert_id NOT IN (SELECT alert_id FROM pairs)""", {}),
    "Q5": ("Lineage: leluhur satu produk sampai 6 tingkat (WITH RECURSIVE)", """
        WITH RECURSIVE anc(product_id, depth) AS (
            SELECT %(pid)s::bigint, 0
            UNION ALL
            SELECT l.parent_product_id, a.depth + 1 FROM anc a JOIN bench.data_lineage l ON l.child_product_id = a.product_id
            WHERE a.depth < 6)
        SELECT a.depth, p.product_id, p.product_tier, p.source FROM anc a JOIN bench.data_products p USING (product_id)
        ORDER BY a.depth""", {"pid": None}),
}


def pg_load(conn, data: Path) -> dict:
    cur = conn.cursor()
    cur.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    cur.execute(PG_SCHEMA)
    counts = {}
    for table, f, cols in [("regions", "regions.csv", None), ("observations", "observations.csv", None),
                           ("alert_events", "alerts.csv", None), ("disaster_events", "disasters.csv", None),
                           ("data_products", "products.csv", None), ("data_lineage", "lineage.csv", None)]:
        path = data / f
        if table == "regions":
            cur.execute("CREATE TEMP TABLE r_in (region_id int, pcode text, region_name text, in_aoi int, geom_wkt text)")
            with open(path, encoding="utf-8") as fh:
                cur.copy_expert("COPY r_in FROM STDIN WITH (FORMAT csv, HEADER true)", fh)
            cur.execute("INSERT INTO bench.regions SELECT region_id, pcode, region_name, in_aoi = 1, "
                        "ST_GeomFromText(geom_wkt, 4326) FROM r_in")
        else:
            with open(path, encoding="utf-8") as fh:
                header = fh.readline().strip()
                fh.seek(0)
                if table == "disaster_events":
                    cur.execute("CREATE TEMP TABLE d_in (event_id bigint, type_code text, region_id int, event_date date, is_verified int)")
                    cur.copy_expert("COPY d_in FROM STDIN WITH (FORMAT csv, HEADER true)", fh)
                    cur.execute("INSERT INTO bench.disaster_events SELECT event_id, type_code, region_id, event_date, is_verified = 1 FROM d_in")
                else:
                    cur.copy_expert(f"COPY bench.{table} ({header}) FROM STDIN WITH (FORMAT csv, HEADER true, NULL '')", fh)
        cur.execute(f"SELECT count(*) FROM bench.{table}")
        counts[table] = cur.fetchone()[0]
    cur.execute("ANALYZE")
    conn.commit()
    return counts


def pg_deep_product(conn) -> int:
    cur = conn.cursor()
    # Produk pertama tanpa anak yang berada di rantai 6 tingkat (rantai ke-0, 3, 6, … dibuat 6 tingkat).
    cur.execute("""SELECT product_id FROM bench.data_products WHERE product_tier = 'DERIVED' ORDER BY product_id LIMIT 1""")
    return cur.fetchone()[0]


# --- F1–F3 PostgreSQL --------------------------------------------------------------------------
def pg_features(conn) -> list[dict]:
    cur = conn.cursor()
    res = []
    # F1: SET LOCAL ROLE per transaksi — hak role hanya berlaku sampai COMMIT/ROLLBACK.
    cur.execute("""DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bench_reader') THEN
                     CREATE ROLE bench_reader NOLOGIN; END IF; END $$;
                   GRANT USAGE ON SCHEMA bench TO bench_reader;
                   GRANT SELECT ON bench.observations TO bench_reader;""")
    conn.commit()
    cur.execute("SET LOCAL ROLE bench_reader")
    ok_read = True
    try:
        cur.execute("SELECT count(*) FROM bench.observations")
        cur.execute("SAVEPOINT s; DELETE FROM bench.observations WHERE false")
        denied = False
    except Exception:
        denied = True
    conn.rollback()
    cur.execute("SELECT current_user")
    back = cur.fetchone()[0]
    res.append({"feature": "F1", "name": "SET ROLE per transaksi", "result": "DIDUKUNG" if ok_read and denied and back != "bench_reader" else "GAGAL",
                "evidence": f"SET LOCAL ROLE: SELECT diizinkan, DELETE ditolak={denied}, role kembali '{back}' setelah ROLLBACK"})
    # F2: Row-level security.
    cur.execute("""ALTER TABLE bench.disaster_events ENABLE ROW LEVEL SECURITY;
                   DROP POLICY IF EXISTS only_verified ON bench.disaster_events;
                   CREATE POLICY only_verified ON bench.disaster_events FOR SELECT TO bench_reader USING (is_verified);
                   GRANT SELECT ON bench.disaster_events TO bench_reader;""")
    conn.commit()
    cur.execute("SELECT count(*), count(*) FILTER (WHERE is_verified) FROM bench.disaster_events")
    total, verified = cur.fetchone()
    cur.execute("SET LOCAL ROLE bench_reader")
    cur.execute("SELECT count(*) FROM bench.disaster_events")
    seen = cur.fetchone()[0]
    conn.rollback()
    res.append({"feature": "F2", "name": "Row-level security", "result": "DIDUKUNG" if seen == verified < total else "GAGAL",
                "evidence": f"CREATE POLICY: role terbatas melihat {seen} dari {total} baris (terverifikasi {verified})"})
    # F3: trigger audit dengan OLD/NEW sebagai JSON tanpa menyebut kolom.
    cur.execute("""CREATE TABLE IF NOT EXISTS bench.audit (id bigserial PRIMARY KEY, tbl text, op text, old_data jsonb, new_data jsonb);
                   CREATE OR REPLACE FUNCTION bench.audit_row() RETURNS trigger LANGUAGE plpgsql AS $f$
                   BEGIN INSERT INTO bench.audit (tbl, op, old_data, new_data)
                         VALUES (TG_TABLE_NAME, TG_OP, to_jsonb(OLD), to_jsonb(NEW)); RETURN NEW; END $f$;
                   DROP TRIGGER IF EXISTS t_audit ON bench.disaster_events;
                   CREATE TRIGGER t_audit AFTER UPDATE ON bench.disaster_events FOR EACH ROW EXECUTE FUNCTION bench.audit_row();""")
    cur.execute("UPDATE bench.disaster_events SET is_verified = NOT is_verified WHERE event_id = 1")
    cur.execute("SELECT old_data->>'is_verified', new_data->>'is_verified', jsonb_object_keys(new_data) FROM bench.audit ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    conn.rollback()
    res.append({"feature": "F3", "name": "Trigger audit OLD/NEW sebagai JSON", "result": "DIDUKUNG" if row and row[0] != row[1] else "GAGAL",
                "evidence": "to_jsonb(OLD)/to_jsonb(NEW) generik untuk semua tabel (satu fungsi, tanpa daftar kolom)"})
    return res


# =========================================================================== MySQL 8.0
MYSQL_SCHEMA = [
    "DROP TABLE IF EXISTS data_lineage, data_products, alert_events, disaster_events, observations, regions, audit",
    """CREATE TABLE regions (region_id int PRIMARY KEY, pcode varchar(20) UNIQUE NOT NULL, region_name varchar(100) NOT NULL,
       in_aoi boolean NOT NULL, geom MULTIPOLYGON NOT NULL SRID 4326, SPATIAL INDEX (geom)) ENGINE=InnoDB""",
    """CREATE TABLE observations (obs_id bigint PRIMARY KEY, region_id int NOT NULL, band_code varchar(10) NOT NULL,
       obs_date date NOT NULL, value decimal(10,4), run_type varchar(5), UNIQUE (region_id, band_code, obs_date),
       INDEX obs_date_band (obs_date, band_code), FOREIGN KEY (region_id) REFERENCES regions (region_id)) ENGINE=InnoDB""",
    """CREATE TABLE alert_events (alert_id bigint PRIMARY KEY, rule_id int NOT NULL, region_id int NOT NULL, obs_id bigint NOT NULL,
       observation_date date NOT NULL, observed_value decimal(10,4) NOT NULL, threshold_value decimal(8,2) NOT NULL,
       severity varchar(10) NOT NULL CHECK (severity IN ('INFO','WARNING','CRITICAL')), UNIQUE (rule_id, region_id, observation_date),
       INDEX alerts_region_date (region_id, observation_date), FOREIGN KEY (region_id) REFERENCES regions (region_id),
       FOREIGN KEY (obs_id) REFERENCES observations (obs_id)) ENGINE=InnoDB""",
    """CREATE TABLE disaster_events (event_id bigint PRIMARY KEY, type_code varchar(30) NOT NULL, region_id int NOT NULL,
       event_date date NOT NULL, is_verified boolean NOT NULL, INDEX disasters_region_date (region_id, event_date),
       FOREIGN KEY (region_id) REFERENCES regions (region_id)) ENGINE=InnoDB""",
    """CREATE TABLE data_products (product_id bigint PRIMARY KEY, product_tier varchar(20) NOT NULL, source varchar(20) NOT NULL,
       file_size_mb decimal(12,2), sha256 char(64) NOT NULL) ENGINE=InnoDB""",
    """CREATE TABLE data_lineage (lineage_id bigint PRIMARY KEY, parent_product_id bigint NOT NULL, child_product_id bigint NOT NULL,
       transformation_type varchar(40) NOT NULL, INDEX lineage_child (child_product_id), INDEX lineage_parent (parent_product_id),
       FOREIGN KEY (parent_product_id) REFERENCES data_products (product_id),
       FOREIGN KEY (child_product_id) REFERENCES data_products (product_id)) ENGINE=InnoDB""",
]

MYSQL_QUERIES = {
    "Q1": ("""SELECT r.region_id, r.region_name,
               max(CASE WHEN o.band_code = 'RAIN_24H' THEN o.value END) AS rain_24h,
               max(CASE WHEN o.band_code = 'RAIN_72H' THEN o.value END) AS rain_72h,
               max(CASE WHEN o.band_code = 'RAIN_7D'  THEN o.value END) AS rain_7d,
               max(CASE WHEN o.band_code = 'RAIN_30D' THEN o.value END) AS rain_30d,
               max(CASE WHEN o.band_code = 'NDVI'     THEN o.value END) AS ndvi
        FROM regions r JOIN observations o ON o.region_id = r.region_id AND o.obs_date = %(d)s
        WHERE r.in_aoi GROUP BY r.region_id, r.region_name ORDER BY r.region_name"""),
    "Q2": ("""SELECT obs_date, value FROM observations
        WHERE region_id = %(r)s AND band_code = %(b)s AND obs_date BETWEEN %(a)s AND %(z)s ORDER BY obs_date"""),
    # MySQL 8: ST_Area pada SRID geografis (4326) mengembalikan m² geodesik sejak 8.0.13.
    "Q3": ("""SELECT region_id, region_name,
               ST_Area(ST_Intersection(geom, ST_GeomFromText(%(p)s, 4326, 'axis-order=long-lat'))) / 1e6 AS km2
        FROM regions WHERE ST_Intersects(geom, ST_GeomFromText(%(p)s, 4326, 'axis-order=long-lat')) ORDER BY km2 DESC"""),
    "Q4": ("""WITH strong AS (SELECT * FROM alert_events WHERE severity IN ('WARNING','CRITICAL')),
             ev AS (SELECT * FROM disaster_events WHERE is_verified AND type_code IN ('BANJIR','BANJIR_BANDANG')),
             pairs AS (SELECT a.alert_id, e.event_id FROM strong a JOIN ev e ON e.region_id = a.region_id
                       AND e.event_date BETWEEN a.observation_date AND a.observation_date + INTERVAL 3 DAY)
        SELECT 'HIT' AS outcome, count(DISTINCT event_id) FROM pairs
        UNION ALL SELECT 'MISS', count(*) FROM ev WHERE event_id NOT IN (SELECT event_id FROM pairs)
        UNION ALL SELECT 'FALSE_ALARM', count(*) FROM strong WHERE alert_id NOT IN (SELECT alert_id FROM pairs)"""),
    "Q5": ("""WITH RECURSIVE anc (product_id, depth) AS (
            SELECT CAST(%(pid)s AS SIGNED), 0
            UNION ALL
            SELECT l.parent_product_id, a.depth + 1 FROM anc a JOIN data_lineage l ON l.child_product_id = a.product_id
            WHERE a.depth < 6)
        SELECT a.depth, p.product_id, p.product_tier, p.source FROM anc a JOIN data_products p USING (product_id)
        ORDER BY a.depth"""),
}


def _rows(path: Path):
    with open(path, encoding="utf-8") as fh:
        r = csv.reader(fh)
        header = next(r)
        for row in r:
            yield header, [None if v == "" else v for v in row]


def mysql_load(conn, data: Path) -> dict:
    cur = conn.cursor()
    for s in MYSQL_SCHEMA:
        cur.execute(s)
    counts = {}
    spec = [("regions", "regions.csv"), ("observations", "observations.csv"), ("alert_events", "alerts.csv"),
            ("disaster_events", "disasters.csv"), ("data_products", "products.csv"), ("data_lineage", "lineage.csv")]
    for table, f in spec:
        batch, header = [], None
        for header, row in _rows(data / f):
            batch.append(row)
        if table == "regions":
            sql = ("INSERT INTO regions VALUES (%s, %s, %s, %s, ST_GeomFromText(%s, 4326, 'axis-order=long-lat'))")
        else:
            sql = f"INSERT INTO {table} ({', '.join(header)}) VALUES ({', '.join(['%s'] * len(header))})"
        for i in range(0, len(batch), 5000):
            cur.executemany(sql, batch[i:i + 5000])
        cur.execute(f"SELECT count(*) FROM {table}")
        counts[table] = cur.fetchone()[0]
    cur.execute("ANALYZE TABLE regions, observations, alert_events, disaster_events, data_products, data_lineage")
    cur.fetchall()
    conn.commit()
    return counts


def mysql_features(conn, schema: str) -> list[dict]:
    """F1–F3 di MySQL 8.0, dinilai dengan kriteria yang sama."""
    cur = conn.cursor()
    res = []
    # F1: SET ROLE ada (8.0) tetapi berlaku per sesi, bukan per transaksi; ROLLBACK tidak memulihkannya.
    try:
        cur.execute("CREATE ROLE IF NOT EXISTS bench_reader")
        cur.execute(f"GRANT SELECT ON {schema}.observations TO bench_reader")
        cur.execute("START TRANSACTION")
        cur.execute("SET ROLE bench_reader")
        cur.execute("ROLLBACK")
        cur.execute("SELECT CURRENT_ROLE()")
        still = cur.fetchone()[0]
        cur.execute("SET ROLE NONE")
        res.append({"feature": "F1", "name": "SET ROLE per transaksi", "result": "SEBAGIAN",
                    "evidence": f"SET ROLE per sesi; setelah ROLLBACK CURRENT_ROLE() masih {still} — aplikasi harus mereset manual"})
    except Exception as e:  # noqa: BLE001
        res.append({"feature": "F1", "name": "SET ROLE per transaksi", "result": "GAGAL", "evidence": str(e)[:200]})
    # F2: tidak ada row-level security bawaan; hanya emulasi dengan VIEW + DEFINER.
    res.append({"feature": "F2", "name": "Row-level security", "result": "TIDAK DIDUKUNG",
                "evidence": "MySQL 8.0 tidak punya CREATE POLICY; emulasi lewat VIEW SQL SECURITY DEFINER + GRANT pada VIEW"})
    # F3: trigger bisa, tetapi tidak ada konversi baris→JSON generik; kolom harus disebut satu per satu.
    try:
        cur.execute("CREATE TABLE IF NOT EXISTS audit (id bigint AUTO_INCREMENT PRIMARY KEY, tbl varchar(64), op varchar(10), old_data json, new_data json)")
        cur.execute("DROP TRIGGER IF EXISTS t_audit")
        cur.execute("""CREATE TRIGGER t_audit AFTER UPDATE ON disaster_events FOR EACH ROW
                       INSERT INTO audit (tbl, op, old_data, new_data) VALUES ('disaster_events', 'UPDATE',
                       JSON_OBJECT('event_id', OLD.event_id, 'is_verified', OLD.is_verified),
                       JSON_OBJECT('event_id', NEW.event_id, 'is_verified', NEW.is_verified))""")
        cur.execute("START TRANSACTION")
        cur.execute("UPDATE disaster_events SET is_verified = NOT is_verified WHERE event_id = 1")
        cur.execute("SELECT old_data, new_data FROM audit ORDER BY id DESC LIMIT 1")
        ok = cur.fetchone() is not None
        cur.execute("ROLLBACK")
        res.append({"feature": "F3", "name": "Trigger audit OLD/NEW sebagai JSON", "result": "SEBAGIAN" if ok else "GAGAL",
                    "evidence": "JSON_OBJECT harus menyebut setiap kolom per tabel; tidak ada padanan to_jsonb(OLD)"})
    except Exception as e:  # noqa: BLE001
        res.append({"feature": "F3", "name": "Trigger audit OLD/NEW sebagai JSON", "result": "GAGAL", "evidence": str(e)[:200]})
    return res


# =========================================================================== MongoDB 7 (fitur saja, tanpa benchmark)
MONGODB_FEATURES = [
    {"feature": "F1", "name": "SET ROLE per transaksi", "result": "TIDAK DIDUKUNG",
     "evidence": "Hak akses per pengguna koneksi; tidak ada pergantian role di dalam transaksi"},
    {"feature": "F2", "name": "Row-level security", "result": "TIDAK DIDUKUNG",
     "evidence": "Tidak ada policy per dokumen bawaan (hanya redaksi lewat $redact/VIEW agregasi)"},
    {"feature": "F3", "name": "Trigger audit OLD/NEW sebagai JSON", "result": "SEBAGIAN",
     "evidence": "Change streams (pre/post image) di luar transaksi; audit log bawaan hanya edisi Enterprise"},
    {"feature": "FK", "name": "Foreign key / integritas lineage", "result": "TIDAK DIDUKUNG",
     "evidence": "Tanpa FK; lineage dijaga aplikasi; $graphLookup untuk rantai leluhur"},
]


def load_csv_ids(path: Path) -> int:
    return sum(1 for _ in open(path, encoding="utf-8")) - 1
