#!/usr/bin/env python
"""
Kamus data + ERD fisik Orbit-U: The Monitor, dibangkitkan dari katalog
PostgreSQL (DATABASE.md §6, M34) — bukan ditulis tangan, sehingga rancangan
database selalu sama dengan database nyata.

Keluaran:
    DOCS/generated/data_dictionary.md   tabel, kolom, tipe, null, default,
                                        PK/FK/UNIQUE/CHECK, komentar; VIEW
    DOCS/generated/erd_physical.mmd     Mermaid erDiagram (entitas + FK)

(DATABASE.md menulis `docs/generated/`; di repo ini foldernya `DOCS/`, yang di
Windows adalah folder yang sama — IMPLEMENTATION_NOTES K10.)

Pakai:
    python tools/data_dictionary.py                    # DB dari .env (DB_*)
    python tools/data_dictionary.py --url postgresql://user:pw@host/db
    python tools/data_dictionary.py --out DOCS/generated

Sumber metadata: pg_class/pg_attribute (tipe lengkap lewat format_type,
termasuk geometry(Polygon,4326)), pg_attrdef (default), pg_constraint
(PK/FK/UNIQUE/CHECK lewat pg_get_constraintdef), dan pg_description
(COMMENT ON).
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "DOCS" / "generated"

# Objek milik ekstensi (spatial_ref_sys, geometry_columns, ... dari PostGIS)
# bukan bagian rancangan Monitor; disaring lewat pg_depend deptype 'e'.
_NOT_EXTENSION = """NOT EXISTS (SELECT 1 FROM pg_depend dep
                        WHERE dep.classid = 'pg_class'::regclass
                          AND dep.objid = c.oid AND dep.deptype = 'e')"""


@dataclass
class Column:
    name: str
    type: str
    not_null: bool
    default: str | None
    generated: bool
    comment: str | None


@dataclass
class Constraint:
    name: str
    kind: str          # PK | FK | UNIQUE | CHECK
    columns: list[str]
    definition: str
    ref_table: str | None = None


@dataclass
class Table:
    name: str
    comment: str | None
    columns: list[Column] = field(default_factory=list)
    constraints: list[Constraint] = field(default_factory=list)


@dataclass
class View:
    name: str
    comment: str | None
    columns: list[str] = field(default_factory=list)


_KIND = {"p": "PK", "f": "FK", "u": "UNIQUE", "c": "CHECK"}


def read_catalog(conn, schema: str = "public") -> tuple[list[Table], list[View]]:
    """Baca tabel, kolom, constraint, dan VIEW skema `schema`.

    `conn` adalah koneksi DB-API (psycopg2) atau SQLAlchemy Connection
    (yang punya exec_driver_sql); keduanya dipakai lewat _rows()."""
    tables: dict[str, Table] = {}
    views: dict[str, View] = {}

    for name, kind, comment in _rows(conn, """
        SELECT c.relname, c.relkind, obj_description(c.oid, 'pg_class')
        FROM   pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE  n.nspname = %(schema)s AND c.relkind IN ('r', 'v')
          AND  """ + _NOT_EXTENSION + """
        ORDER  BY c.relname
    """, schema):
        if kind == "r":
            tables[name] = Table(name, comment)
        else:
            views[name] = View(name, comment)

    for rel, col, typ, not_null, default, generated, comment in _rows(conn, """
        SELECT c.relname, a.attname, format_type(a.atttypid, a.atttypmod),
               a.attnotnull, pg_get_expr(d.adbin, d.adrelid),
               a.attgenerated <> '', col_description(c.oid, a.attnum)
        FROM   pg_attribute a
        JOIN   pg_class c     ON c.oid = a.attrelid
        JOIN   pg_namespace n ON n.oid = c.relnamespace
        LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
        WHERE  n.nspname = %(schema)s AND c.relkind IN ('r', 'v')
          AND  a.attnum > 0 AND NOT a.attisdropped
        ORDER  BY c.relname, a.attnum
    """, schema):
        if rel in tables:
            tables[rel].columns.append(Column(col, typ, not_null, default, generated, comment))
        elif rel in views:
            views[rel].columns.append(col)

    for rel, name, kind, cols, definition, ref in _rows(conn, """
        SELECT c.relname, con.conname, con.contype,
               ARRAY(SELECT a.attname FROM unnest(con.conkey) k
                     JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k),
               pg_get_constraintdef(con.oid), rc.relname
        FROM   pg_constraint con
        JOIN   pg_class c     ON c.oid = con.conrelid
        JOIN   pg_namespace n ON n.oid = c.relnamespace
        LEFT JOIN pg_class rc ON rc.oid = con.confrelid
        WHERE  n.nspname = %(schema)s AND con.contype IN ('p', 'f', 'u', 'c')
        ORDER  BY c.relname, con.contype, con.conname
    """, schema):
        if rel in tables:
            tables[rel].constraints.append(
                Constraint(name, _KIND[kind], list(cols or []), definition, ref))

    return list(tables.values()), list(views.values())


def _rows(conn, sql: str, schema: str):
    if hasattr(conn, "exec_driver_sql"):           # SQLAlchemy Connection
        return conn.exec_driver_sql(sql, {"schema": schema}).all()
    with conn.cursor() as cur:                     # psycopg2
        cur.execute(sql, {"schema": schema})
        return cur.fetchall()


# ---------------------------------------------------------------------------
# Kamus data (Markdown)
# ---------------------------------------------------------------------------

def _md(text: str | None) -> str:
    return (text or "").replace("|", "\\|").replace("\n", " ")


def render_dictionary(tables: list[Table], views: list[View], source: str = "") -> str:
    out = [
        "# Kamus Data — Orbit-U: The Monitor",
        "",
        "> Dibangkitkan otomatis oleh `tools/data_dictionary.py` dari katalog PostgreSQL"
        + (f" ({source})" if source else "") + ". Jangan disunting manual; ubah "
        "`database/monitor_schema.sql` (termasuk `COMMENT ON`) lalu bangkitkan ulang.",
        "",
        f"Jumlah: **{len(tables)} tabel**, **{len(views)} VIEW**.",
        "",
        "## Daftar tabel",
        "",
        "| Tabel | Keterangan |",
        "|---|---|",
    ]
    out += [f"| [`{t.name}`](#{t.name}) | {_md(t.comment)} |" for t in tables]
    for t in tables:
        keys: dict[str, list[str]] = defaultdict(list)
        for con in t.constraints:
            if con.kind in ("PK", "UNIQUE") or (con.kind == "FK" and con.ref_table):
                for col in con.columns:
                    keys[col].append(f"FK→{con.ref_table}" if con.kind == "FK" else con.kind)
        out += ["", f"## {t.name}", "", _md(t.comment) or "_(tanpa komentar)_", "",
                "| Kolom | Tipe | Null | Default | Kunci | Keterangan |",
                "|---|---|---|---|---|---|"]
        for c in t.columns:
            default = "GENERATED" if c.generated else (c.default or "")
            out.append(
                f"| `{c.name}` | `{c.type}` | {'NOT NULL' if c.not_null else 'NULL'} | "
                f"{_md(default) and f'`{_md(default)}`'} | {', '.join(keys.get(c.name, []))} | "
                f"{_md(c.comment)} |"
            )
        if t.constraints:
            out += ["", "**Constraint**", ""]
            out += [f"- `{con.name}` ({con.kind}): `{_md(con.definition)}`" for con in t.constraints]
    if views:
        out += ["", "## VIEW", "", "| VIEW | Kolom | Keterangan |", "|---|---|---|"]
        out += [f"| `{v.name}` | {', '.join(f'`{c}`' for c in v.columns)} | {_md(v.comment)} |"
                for v in views]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# ERD fisik (Mermaid)
# ---------------------------------------------------------------------------

def _mermaid_type(typ: str) -> str:
    base = typ.split("(")[0].strip()
    short = {"character varying": "varchar", "timestamp with time zone": "timestamptz",
             "timestamp without time zone": "timestamp", "double precision": "float8",
             "character": "char"}.get(base, base)
    return re.sub(r"[^A-Za-z0-9_]", "_", short.replace("[]", "_array"))


def render_erd(tables: list[Table]) -> str:
    out = ["erDiagram"]
    for t in tables:
        pk = {c for con in t.constraints if con.kind == "PK" for c in con.columns}
        fk = {c for con in t.constraints if con.kind == "FK" for c in con.columns}
        uk = {c for con in t.constraints if con.kind == "UNIQUE" and len(con.columns) == 1
              for c in con.columns}
        out.append(f"    {t.name} {{")
        for c in t.columns:
            marks = [m for m, s in (("PK", pk), ("FK", fk), ("UK", uk)) if c.name in s]
            out.append(f"        {_mermaid_type(c.type)} {c.name}"
                       + (f" {','.join(marks)}" if marks else ""))
        out.append("    }")
    for t in tables:
        not_null = {c.name for c in t.columns if c.not_null}
        for con in t.constraints:
            if con.kind != "FK" or not con.ref_table:
                continue
            # Anak wajib punya induk bila semua kolom FK NOT NULL.
            child = "|{" if all(c in not_null for c in con.columns) else "o{"
            out.append(f'    {con.ref_table} ||--{child} {t.name} : "{",".join(con.columns)}"')
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------

def generate(conn, out_dir: Path = DEFAULT_OUT, source: str = "") -> tuple[Path, Path]:
    tables, views = read_catalog(conn)
    out_dir.mkdir(parents=True, exist_ok=True)
    dict_path = out_dir / "data_dictionary.md"
    erd_path = out_dir / "erd_physical.mmd"
    dict_path.write_text(render_dictionary(tables, views, source), encoding="utf-8")
    erd_path.write_text(render_erd(tables), encoding="utf-8")
    return dict_path, erd_path


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--url", help="URL database (default: DB_* dari .env)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)

    sys.path.insert(0, str(ROOT))
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url

    if args.url:
        url = args.url
    else:
        from etl.config import DatabaseConfig  # memicu load_dotenv

        url = DatabaseConfig().url
    engine = create_engine(url)
    with engine.connect() as conn:
        db = make_url(url).database
        paths = generate(conn, args.out, source=f"database `{db}`, "
                         f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC")
    for p in paths:
        print(f"[OK] {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
