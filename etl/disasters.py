# etl/disasters.py
"""Tulis/baca ``disaster_events`` (INTERFACE.md §4.6, PIPELINE.md §10 langkah 7).

Dipakai bersama endpoint ``/api/disasters`` dan ``scripts/import_disasters.py``
supaya aturan validasinya satu: jenis dari master ``disaster_types``, wilayah
harus kecamatan (level 3) ``administrative_regions``, tanpa data pribadi.
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from sqlalchemy import text

EVENT_SELECT = """
    SELECT e.event_id, dt.type_code AS disaster_type_code, dt.type_name AS disaster_type_name,
           e.region_id, r.pcode, r.region_name, e.village_name,
           ST_Y(e.location) AS lat, ST_X(e.location) AS lon,
           e.event_date, e.event_end_date, e.description, e.impact_summary, e.info_source,
           e.source_reference, e.is_verified, e.verified_by, e.recorded_by, e.recorded_at, e.updated_at
    FROM disaster_events e
    JOIN disaster_types dt ON dt.disaster_type_id = e.disaster_type_id
    JOIN administrative_regions r ON r.region_id = e.region_id
"""

INFO_SOURCES = ("GMLS", "BPBD_LEBAK", "BNPB_DIBI", "MEDIA", "LAINNYA")


def event_dict(row) -> dict:
    d = dict(row)
    lat, lon = d.pop("lat"), d.pop("lon")
    d["location"] = None if lat is None else {"lat": float(lat), "lon": float(lon)}
    return d


def get_event(sess, event_id: int) -> dict | None:
    row = sess.execute(text(EVENT_SELECT + " WHERE e.event_id = :e AND e.deleted_at IS NULL"),
                       {"e": event_id}).mappings().first()
    return None if row is None else event_dict(row)


def _type_id(sess, code: str) -> int:
    tid = sess.scalar(text("SELECT disaster_type_id FROM disaster_types WHERE type_code = :c AND is_active"),
                      {"c": code})
    if tid is None:
        raise ValueError(f"unknown or inactive disaster type {code!r}")
    return tid


def _check_region(sess, region_id: int) -> None:
    if not sess.scalar(text("SELECT 1 FROM administrative_regions WHERE region_id = :r AND admin_level = 3"),
                       {"r": region_id}):
        raise ValueError(f"region_id {region_id} is not a kecamatan")


def insert_event(sess, data: dict, recorded_by: int) -> int:
    """data: field DisasterCreate (location = {lat, lon} | None)."""
    _check_region(sess, data["region_id"])
    if data.get("event_end_date") and data["event_end_date"] < data["event_date"]:
        raise ValueError("event_end_date must not be before event_date")
    loc = data.get("location") or None
    return sess.scalar(text("""
        INSERT INTO disaster_events (disaster_type_id, region_id, village_name, location, event_date, event_end_date,
                                     description, impact_summary, info_source, source_reference, is_verified,
                                     verified_by, recorded_by)
        VALUES (:dt, :r, :village,
                CASE WHEN CAST(:lon AS float8) IS NULL THEN NULL
                     ELSE ST_SetSRID(ST_MakePoint(CAST(:lon AS float8), CAST(:lat AS float8)), 4326) END,
                :d0, :d1, :descr, :impact, :src, :ref, :ver, CASE WHEN :ver THEN :by END, :by)
        RETURNING event_id"""), {
        "dt": _type_id(sess, data["disaster_type_code"]), "r": data["region_id"],
        "village": data.get("village_name"), "lat": loc and loc["lat"], "lon": loc and loc["lon"],
        "d0": data["event_date"], "d1": data.get("event_end_date"), "descr": data["description"].strip(),
        "impact": data.get("impact_summary"), "src": data["info_source"], "ref": data.get("source_reference"),
        "ver": bool(data.get("is_verified")), "by": recorded_by})


_SIMPLE = ("village_name", "event_date", "event_end_date", "description", "impact_summary", "info_source",
           "source_reference")


def update_event(sess, event_id: int, fields: dict, user_id: int) -> None:
    if "event_date" in fields or "event_end_date" in fields:
        cur = sess.execute(text("SELECT event_date, event_end_date FROM disaster_events WHERE event_id = :e"),
                           {"e": event_id}).one()
        start = fields.get("event_date", cur.event_date)
        end = fields.get("event_end_date", cur.event_end_date)
        if start is None:
            raise ValueError("event_date must not be empty")
        if end is not None and end < start:
            raise ValueError("event_end_date must not be before event_date")
    sets, params = [], {"e": event_id}
    if "disaster_type_code" in fields:
        sets.append("disaster_type_id = :dt")
        params["dt"] = _type_id(sess, fields["disaster_type_code"])
    if "region_id" in fields:
        _check_region(sess, fields["region_id"])
        sets.append("region_id = :r")
        params["r"] = fields["region_id"]
    for k in _SIMPLE:
        if k in fields:
            sets.append(f"{k} = :{k}")
            params[k] = fields[k]
    if "location" in fields:
        loc = fields["location"]
        if loc is None:
            sets.append("location = NULL")
        else:
            sets.append("location = ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)")
            params.update(lat=loc["lat"], lon=loc["lon"])
    if "is_verified" in fields:
        sets.append("is_verified = :ver, verified_by = CASE WHEN :ver THEN :by END")
        params.update(ver=bool(fields["is_verified"]), by=user_id)
    if not sets:
        return
    sess.execute(text(f"UPDATE disaster_events SET {', '.join(sets)}, updated_at = now() WHERE event_id = :e"), params)


# --- impor CSV ------------------------------------------------------------------

CSV_COLUMNS = ("tanggal", "tanggal_selesai", "jenis", "kecamatan", "desa", "lat", "lon",
               "keterangan", "dampak", "sumber", "referensi", "terverifikasi")
REQUIRED = ("tanggal", "jenis", "kecamatan", "keterangan", "sumber")
_TRUE = {"1", "true", "ya", "y", "yes"}


def _resolve_kecamatan(sess, value: str) -> int:
    rows = sess.scalars(text("""
        SELECT region_id FROM administrative_regions
        WHERE admin_level = 3 AND (upper(pcode) = upper(:v) OR lower(region_name) = lower(:v))"""),
        {"v": value.strip()}).all()
    if len(rows) != 1:
        raise ValueError(f"kecamatan {value!r} {'is ambiguous' if rows else 'not found'}")
    return rows[0]


def parse_row(sess, row: dict) -> dict:
    """Satu baris CSV -> dict DisasterCreate. ValueError dengan pesan yang bisa
    ditunjukkan ke pengguna bila ada kolom yang salah."""
    row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
    missing = [c for c in REQUIRED if not row.get(c)]
    if missing:
        raise ValueError("missing column value(s): " + ", ".join(missing))
    source = row["sumber"].upper()
    if source not in INFO_SOURCES:
        raise ValueError(f"sumber must be one of {', '.join(INFO_SOURCES)}")
    lat, lon = row.get("lat"), row.get("lon")
    if bool(lat) != bool(lon):
        raise ValueError("lat and lon must both be filled or both empty")
    location = None
    if lat:
        location = {"lat": float(lat), "lon": float(lon)}
        if not (-90 <= location["lat"] <= 90 and -180 <= location["lon"] <= 180):
            raise ValueError("lat/lon out of range")
    if len(row["keterangan"]) < 10:
        raise ValueError("keterangan must be at least 10 characters")
    return {
        "disaster_type_code": row["jenis"].upper(),
        "region_id": _resolve_kecamatan(sess, row["kecamatan"]),
        "village_name": row.get("desa") or None,
        "location": location,
        "event_date": date.fromisoformat(row["tanggal"]),
        "event_end_date": date.fromisoformat(row["tanggal_selesai"]) if row.get("tanggal_selesai") else None,
        "description": row["keterangan"],
        "impact_summary": row.get("dampak") or None,
        "info_source": source,
        "source_reference": row.get("referensi") or None,
        "is_verified": row.get("terverifikasi", "").lower() in _TRUE,
    }


def _is_duplicate(sess, data: dict) -> bool:
    """Kejadian yang sama (jenis, kecamatan, tanggal, keterangan) sudah ada:
    impor ulang berkas yang sama tidak menggandakan baris."""
    return bool(sess.scalar(text("""
        SELECT 1 FROM disaster_events e JOIN disaster_types dt USING (disaster_type_id)
        WHERE dt.type_code = :t AND e.region_id = :r AND e.event_date = :d AND e.description = :descr
          AND e.deleted_at IS NULL"""),
        {"t": data["disaster_type_code"], "r": data["region_id"], "d": data["event_date"],
         "descr": data["description"]}))


def import_csv(sess, path: Path, recorded_by: int, dry_run: bool = False) -> dict:
    """Impor seluruh berkas dalam satu transaksi pemanggil: satu baris salah ->
    tidak ada yang ditulis (laporan error per nomor baris)."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        header = {h.strip().lower() for h in (reader.fieldnames or [])}
        unknown = header - set(CSV_COLUMNS)
        if not set(REQUIRED) <= header:
            raise ValueError("CSV header must contain: " + ", ".join(REQUIRED))
        if unknown:
            raise ValueError("unknown CSV column(s): " + ", ".join(sorted(unknown)))
        parsed, errors = [], []
        for n, row in enumerate(reader, start=2):
            try:
                parsed.append((n, parse_row(sess, row)))
            except ValueError as exc:
                errors.append(f"line {n}: {exc}")
    if errors:
        return {"inserted": 0, "duplicates": 0, "errors": errors}
    inserted = duplicates = 0
    for n, data in parsed:
        if _is_duplicate(sess, data):
            duplicates += 1
            continue
        if not dry_run:
            try:
                insert_event(sess, data, recorded_by)
            except ValueError as exc:
                errors.append(f"line {n}: {exc}")
                continue
        inserted += 1
    return {"inserted": inserted, "duplicates": duplicates, "errors": errors}
