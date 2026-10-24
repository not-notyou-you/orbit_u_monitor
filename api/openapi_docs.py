# api/openapi_docs.py
"""Pelengkap OpenAPI untuk developer (INTERFACE.md §6.1): deskripsi Bahasa
Inggris, contoh request/response, skema error, dan catatan role per operasi.

Dipanggil `custom_openapi()` di api/main.py setelah `x-min-role` diisi. Teks di
sini sengaja dipisah dari route supaya kontrak dokumentasi bisa diuji
(tests/test_openapi_docs.py) tanpa mengubah perilaku endpoint.
"""

from __future__ import annotations

ERROR_SCHEMA = {
    "type": "object",
    "required": ["detail", "code"],
    "properties": {
        "detail": {"type": "string", "description": "Human-readable message (English)."},
        "code": {"type": "string", "description": "Machine-readable code; the web UI translates it to Indonesian "
                                                  "(INTERFACE.md §5)."},
        "errors": {"type": "array", "items": {"type": "string"},
                   "description": "Only for IMPORT_ROWS_INVALID: one entry per invalid spreadsheet line."},
    },
}

_ERR = {
    401: ("Not signed in, session expired, or token invalid/revoked/expired", "SESSION_EXPIRED", "Session expired"),
    403: ("Role not allowed (API layer) or rejected by PostgreSQL GRANT/RLS; API tokens cannot write",
          "ROLE_FORBIDDEN", "This endpoint requires role ANALYST"),
    404: ("Not found, or you may not know it exists", "NOT_FOUND", "Not found"),
    409: ("Conflict with the current state", "CONFLICT", "Conflict"),
    422: ("Request body/query failed validation", "VALIDATION_ERROR", "date_end: date_end must be >= date_start"),
    429: ("More than 120 requests/minute with one API token (Retry-After: 60)", "RATE_LIMITED", "Rate limit exceeded"),
}

# (METHOD, path) -> description / request example / response example.
DOCS: dict[tuple[str, str], dict] = {
    ("POST", "/api/auth/login"): {
        "description": "Sign in. On success sets the `orbit_u_session` cookie (HttpOnly, SameSite=Strict, 8 h). "
                       "Browsers must also send `X-Requested-With: orbit-u`. Five failures lock the account for "
                       "15 minutes (423 `ACCOUNT_LOCKED`).",
        "request": {"username": "analis1", "password": "correct horse battery"},
        "response": {"user_id": 3, "username": "analis1", "full_name": "Analis GMLS", "role_code": "ANALYST",
                     "auth": "session", "permissions": ["hydromet.today", "alerts.acknowledge", "analytics.view"]},
    },
    ("GET", "/api/auth/me"): {
        "description": "The signed-in principal and the UI feature keys it may use (`permissions`). "
                       "Use it to check that a token works.",
        "response": {"user_id": 3, "username": "analis1", "full_name": "Analis GMLS", "organization": "GMLS",
                     "role_code": "ANALYST", "auth": "token", "permissions": ["live.recent", "hydromet.today"]},
    },
    ("POST", "/api/auth/tokens"): {
        "description": "Create a personal API token (web session only). The full `token` value is returned **once**; "
                       "store it securely. Scope `READ` allows GET endpoints, `READ_DOWNLOAD` also file downloads. "
                       "Tokens can never write (403 `TOKEN_WRITE_FORBIDDEN`).",
        "request": {"name": "analysis script", "scope": "READ_DOWNLOAD", "expires_in_days": 90},
        "response": {"token_id": 7, "token": "trn_3fQ9…", "prefix": "trn_3fQ9", "scope": "READ_DOWNLOAD",
                     "expires_at": "2027-01-02T09:00:00+07:00"},
    },
    ("GET", "/api/public/live"): {
        "description": "Latest READY scene of every enabled Live Area, without history or forecast. No sign-in.",
        "response": {"items": [{"area_id": 1, "area_name": "Lebak Selatan", "scene_date": "2026-09-27", "status": "READY",
                                "area_status": {"label": "Waspada", "level": 1, "text": "Waspada — …"},
                                "previews": {"s1_vh": {"label": "Sentinel-1 VH", "url": "/api/public/live/1/preview/s1_vh.png"}}}],
                     "total": 1},
    },
    ("GET", "/api/public/lokasi"): {
        "description": "Monitored kecamatan (AOI) with a short condition status for the Beranda location picker. "
                       "No sign-in. Device coordinates are never sent: the browser matches them against "
                       "`GET /api/regions` itself.",
        "response": {"items": [{"region_id": 6, "pcode": "ID3602140", "name": "Cibeber", "area_km2": 401.2,
                                "status": {"label": "Waspada", "level": 1, "text": "Waspada — curah hujan 7 hari melewati ambang"},
                                "abnormal": 1, "alert": None,
                                "dates": {"s1": "2026-10-12", "modis": "2026-10-07", "gpm": "2026-10-07"}}],
                     "total": 10},
    },
    ("GET", "/api/public/lokasi/{region_id}"): {
        "description": "Condition of one kecamatan: status, what is abnormal (sentences + rain alerts of the last "
                       "7 days), latest value per band with the previous one and the usual range (2nd–98th "
                       "percentile, 365 days), and the latest Live scene previews cropped to the kecamatan. "
                       "Numbers come from `v_public_lokasi_obs`: visitors see 30 days, but the two latest "
                       "observations per band are always visible. `updated_at` = when this kecamatan's numbers were "
                       "last computed.",
        "response": {"region": {"region_id": 6, "name": "Cibeber", "area_km2": 401.2},
                     "status": {"label": "Waspada", "level": 1, "text": "Waspada — curah hujan 7 hari melewati ambang"},
                     "abnormal": [{"key": "gpm_rain_7d", "what": "curah hujan 7 hari", "category": "alert", "level": 1,
                                   "because": "rata-rata akumulasi 81,5 mm, di atas ambang waspada 75 mm"}],
                     "stats": [{"band_code": "RAIN_7D", "unit": "mm", "value": 81.5, "obs_date": "2026-10-07",
                                "prev_value": 76.2, "range": {"p02": 0.0, "p98": 226.2}}],
                     "imagery": {"area_id": 1, "scene_date": "2026-10-12", "cropped": True,
                                 "previews": {"s1_vh": {"url": "/api/public/lokasi/6/preview/s1_vh.png"}}},
                     "updated_at": "2026-10-12T23:41:05+07:00"},
    },
    ("GET", "/api/live/areas/{area_id}/card"): {
        "description": "Everything the Live card shows for one area: selected scene (default latest) with metrics, "
                       "sentences, 9 preview URLs and `water_change` (new/receded/persistent km² vs the previous "
                       "scene, `same_orbit`), stored dates and the statistical forecast. Non-ADMIN callers only see "
                       "scenes from the last 30 days plus the latest (403 `SCENE_OUT_OF_RANGE`).",
        "response": {"area": {"area_id": 1, "name": "Lebak Selatan", "retention": 6}, "scene": {
            "date": "2026-09-27", "water_change": {"new_km2": 20.33, "receded_km2": 2.31, "persistent_km2": 488.58,
                                                   "ref_date": "2026-09-22", "same_orbit": 0.0}},
            "dates": [{"date": "2026-09-27", "status": "READY", "level": 1}], "forecast": {"n_scenes": 2}},
    },
    ("GET", "/api/hydromet/today"): {
        "description": "Latest day with rainfall per AOI kecamatan (`v_statistik_hari_ini`). The day is a UTC day "
                       "= 07:00–07:00 WIB. `bmkg_category` follows BMKG 24 h rain classes; `gpm_run` F/L/E "
                       "(Late/Early are provisional).",
        "response": {"obs_date": "2026-09-30", "window_wib": "2026-09-30T07:00+07:00/2026-10-01T07:00+07:00",
                     "regions": [{"region_id": 12, "pcode": "ID3602030", "name": "Bayah", "rain_24h_mm": 63.4,
                                  "rain_72h_mm": 118.0, "rain_7d_mm": 160.2, "rain_30d_mm": 402.7,
                                  "bmkg_category": "LEBAT", "gpm_run": "L", "ndvi": 0.61, "modis_flood_pct": 0.8,
                                  "active_alert": {"alert_id": 881, "severity": "INFO", "rule_code": "FLOOD_RAIN24_HEAVY"}}]},
    },
    ("GET", "/api/hydromet/observations"): {
        "description": "Daily values per kecamatan and band, paginated `{items,total,limit,offset}`. USER may only "
                       "read data from the last 30 days (403 `DATE_OUT_OF_RANGE`); ANALYST and above read the full "
                       "archive (2023 onwards).",
        "response": {"items": [{"obs_date": "2025-01-01", "region_id": 12, "pcode": "ID3602030", "region_name": "Bayah",
                                "band_code": "RAIN_24H", "unit": "mm", "value": 14.08, "valid_fraction": 1.0,
                                "run_type": "F", "source_product_id": 5}], "total": 3650, "limit": 500, "offset": 0},
    },
    ("GET", "/api/hydromet/observations.csv"): {
        "description": "Same filters as `/observations`, as CSV (UTF-8, header row). Every export is logged as "
                       "`EXPORT_CSV`.",
    },
    ("GET", "/api/hydromet/trend"): {
        "description": "Last-N-days series per AOI kecamatan for charts, ending at the latest observed day. "
                       "`days` > 30 requires ANALYST.",
        "response": {"band": "RAIN_24H", "dates": ["2025-12-30", "2025-12-31"],
                     "series": [{"region_id": 12, "pcode": "ID3602030", "name": "Bayah", "values": [3.1, None]}]},
    },
    ("GET", "/api/regions"): {
        "description": "GeoJSON FeatureCollection of AOI kecamatan (simplified with ST_SimplifyPreserveTopology). "
                       "`?all=true` returns every kecamatan of Kabupaten Lebak.",
    },
    ("GET", "/api/alerts"): {
        "description": "Rain alerts, newest first. `status=active` = not yet acknowledged.",
        "response": {"items": [{"alert_id": 881, "observation_date": "2026-09-30", "region_name": "Bayah",
                                "rule_code": "FLOOD_RAIN24_HEAVY", "observed_value": 63.4, "threshold_value": 50.0,
                                "severity": "INFO", "acknowledged_at": None}], "total": 1, "limit": 100, "offset": 0},
    },
    ("POST", "/api/alerts/{alert_id}/acknowledge"): {
        "description": "Mark an alert as read (ANALYST/ADMIN, web session). 409 `ALERT_ALREADY_ACKED` if someone "
                       "already did.",
        "request": {"note": "Checked with BPBD, no flooding reported"},
    },
    ("GET", "/api/alerts/evaluation"): {
        "description": "Hit / miss / false alarm of WARNING+ alerts against verified disaster events "
                       "(`v_evaluasi_alert`), with POD and FAR (null when the denominator is zero) and a per-rule "
                       "breakdown (`by_rule`; misses have `rule_code: null`).",
        "response": {"hit": 4, "miss": 2, "false_alarm": 3, "pod": 0.6667, "far": 0.4286,
                     "by_rule": [{"rule_code": "FLOOD_RAIN24_VHEAVY", "hit": 4, "miss": 0, "false_alarm": 3},
                                 {"rule_code": None, "hit": 0, "miss": 2, "false_alarm": 0}]},
    },
    ("POST", "/api/disasters"): {
        "description": "Record a disaster event. The type must be active, the region a kecamatan, the description "
                       "10–4000 characters and `event_end_date ≥ event_date` (400 `INVALID_DISASTER`). Do not put "
                       "personal data in `impact_summary`. Every change is written to `audit_log`.",
        "request": {"disaster_type_code": "BANJIR", "region_id": 12, "village_name": "Bayah Barat",
                    "location": {"lat": -6.928, "lon": 106.226}, "event_date": "2026-09-30",
                    "description": "Luapan Sungai Cimadur merendam permukiman tepi sungai.",
                    "impact_summary": "± 40 rumah tergenang 30–50 cm", "info_source": "GMLS",
                    "source_reference": None, "is_verified": False},
        "response": {"event_id": 57, "disaster_type_code": "BANJIR", "region_name": "Bayah", "event_date": "2026-09-30"},
    },
    ("GET", "/api/disasters/{event_id}"): {
        "description": "One event plus rainfall of its kecamatan on H-0, H-1 and H-2 (`v_kejadian_dan_hujan`).",
        "response": {"event_id": 57, "disaster_type_name": "Banjir", "region_name": "Bayah", "event_date": "2026-09-30",
                     "rain": [{"day": "H-0", "rain_24h_mm": 63.4, "rain_72h_mm": 118.0, "rain_7d_mm": 160.2}]},
    },
    ("GET", "/api/datasets"): {
        "description": "Catalog datasets (system datasets excluded) with per-source configuration, counts and "
                       "creator.",
    },
    ("POST", "/api/datasets"): {
        "description": "Create a historical dataset and start its pipeline job immediately (downloads satellite "
                       "data). One source → no fusion; more sources → `fusion_strategy` required. Date range ≤ 366 "
                       "days.",
        "request": {"region_id": 1, "name": "Musim hujan 2024", "date_start": "2024-01-01", "date_end": "2024-03-31",
                    "sources": {"sentinel1": {"processing": ["PROCESSED"]}, "gpm": {"processing": ["RAW", "PROCESSED"]}},
                    "fusion_strategy": "HYBRID", "preview_options": ["COLORED"]},
        "response": {"dataset_id": 12, "job_id": 40, "status": "QUEUED"},
    },
    ("GET", "/api/datasets/{dataset_id}/download"): {
        "description": "Whole dataset as a streamed ZIP. Logged as `DOWNLOAD_DATASET` with the bytes actually sent. "
                       "Token scope `READ_DOWNLOAD` required.",
    },
    ("GET", "/api/products"): {
        "description": "Data products; combine `dataset_id`, `source` and `tier`. Origin: `scene_id` (Sentinel-1) "
                       "or `nasa_scene_id` (MODIS/GPM granule); FUSION has neither.",
    },
    ("GET", "/api/products/{product_id}/download"): {
        "description": "One product file (GeoTIFF/COG or fusion HDF5), streamed. Logged as `DOWNLOAD_PRODUCT` "
                       "(or `DOWNLOAD_FUSION`). Token scope `READ_DOWNLOAD` required.",
    },
    ("GET", "/api/metadata/lineage/{product_id}"): {
        "description": "Provenance chain of a product: `direction=ancestors` back to RAW, or `descendants`.",
        "response": {"product_id": 88, "direction": "ancestors", "total_steps": 2, "chain": [
            {"parent_product_id": 61, "child_product_id": 88, "transformation_type": "COG_EXPORT", "source": "SENTINEL1",
             "parent_tier": "DESPECKLED", "child_tier": "COG"}]},
    },
    ("GET", "/api/reports"): {
        "description": "Periodic PDF reports of your audience (RLS): Hidromet for ANALYST, Data Health for "
                       "DATA_ENGINEER, both for ADMIN. Other roles get 403 `REPORT_AUDIENCE`.",
    },
    ("POST", "/api/reports/regenerate"): {
        "description": "Regenerate a report in the background (202). Weekly periods start on Monday, monthly on the "
                       "1st (400 `INVALID_PERIOD`). The previous row becomes SUPERSEDED; its file is kept.",
        "request": {"report_code": "HYDROMET_WEEKLY", "period_start": "2024-01-01"},
        "response": {"accepted": True, "report_code": "HYDROMET_WEEKLY", "period_start": "2024-01-01", "period_end": "2024-01-07"},
    },
    ("GET", "/api/excel"): {
        "description": "Data types your role may export/import, with their URLs.",
    },
    ("POST", "/api/excel/{entity}/import"): {
        "description": "Body = raw .xlsx (≤ 10 MB, `Content-Type: application/vnd.openxmlformats-officedocument."
                       "spreadsheetml.sheet`). All rows or nothing; `?dry_run=true` validates only. 422 "
                       "`IMPORT_ROWS_INVALID` lists every bad line in `errors`.",
        "response": {"inserted": 3, "updated": 0, "duplicates": 1, "errors": [], "rows": 4, "dry_run": True},
    },
    ("POST", "/api/admin/ingest"): {
        "description": "Start the Hydromet job for a date range (≤ 366 days, under the `hydromet` lock) or a Live "
                       "cycle now. Downloads satellite data. Returns 202.",
        "request": {"job": "HYDROMET", "date_from": "2025-01-01", "date_to": "2025-01-31"},
    },
    ("PATCH", "/api/admin/scenes/{source}/{scene_id}"): {
        "description": "Soft-delete or restore a scene/granule. A reason is required when `is_valid` is false "
                       "(400 `REASON_REQUIRED`).",
        "request": {"is_valid": False, "reason": "Striping artefact over the AOI"},
    },
    ("GET", "/api/admin/pipeline/status"): {
        "description": "Operational overview: latest job per kind, hydromet status, Live Areas, latest reports, "
                       "`SKIPPED_LOCKED` runs of the last 7 days, queue, whether NASA/Copernicus credentials are "
                       "present (never their values) and the scheduler plan.",
    },
    ("GET", "/api/admin/audit"): {
        "description": "Rows of `audit_log` (trigger-based, includes changes made directly in psql). Secrets "
                       "(`password_hash`, `token_hash`) are redacted.",
    },
}


def _role_line(op: dict) -> str:
    role = op.get("x-min-role", "PUBLIC")
    parts = [f"**Minimum role:** `{role}`."]
    if op.get("x-download"):
        parts.append("Download: logged in `user_activity_logs`; API tokens need scope `READ_DOWNLOAD`.")
    return " ".join(parts)


def enrich(schema: dict) -> dict:
    comps = schema.setdefault("components", {})
    comps.setdefault("schemas", {})["ErrorResponse"] = ERROR_SCHEMA
    for path, methods in schema.get("paths", {}).items():
        for method, op in methods.items():
            if method not in ("get", "post", "put", "patch", "delete"):
                continue
            doc = DOCS.get((method.upper(), path), {})
            base = doc.get("description") or op.get("description") or (op.get("summary", "") + ".")
            extra = []
            if method != "get" and op.get("x-min-role", "PUBLIC") != "PUBLIC":
                extra.append("Write operation: web session + `X-Requested-With: orbit-u`; API tokens get 403 "
                             "`TOKEN_WRITE_FORBIDDEN`.")
            op["description"] = "\n\n".join([base.strip(), _role_line(op)] + extra)
            if "request" in doc:
                content = op.get("requestBody", {}).get("content", {}).get("application/json")
                if content is not None:
                    content["example"] = doc["request"]
            if "response" in doc:
                for code in ("200", "201", "202"):
                    resp = op.get("responses", {}).get(code)
                    if resp is not None:
                        resp.setdefault("content", {}).setdefault("application/json", {})["example"] = doc["response"]
                        break
            responses = op.setdefault("responses", {})
            codes = [401, 403] if op.get("x-min-role", "PUBLIC") != "PUBLIC" else []
            codes += [404] if "{" in path else []
            codes += [409] if method in ("post", "put", "patch", "delete") else []
            codes += [422]
            codes += [429] if method == "get" else []
            for c in codes:
                desc, code, detail = _ERR[c]
                responses[str(c)] = {"description": desc, "content": {"application/json": {
                    "schema": {"$ref": "#/components/schemas/ErrorResponse"},
                    "example": {"detail": detail, "code": code}}}}
    return schema
