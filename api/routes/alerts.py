# api/routes/alerts.py
"""Alert hujan dan aturan alert (INTERFACE.md §4.5).

``/alerts`` dibaca USER; acknowledge dan evaluasi ANALYST (GRANT kolom
``alert_events``: analyst hanya boleh mengisi kolom acknowledge). Aturan alert
tidak pernah dihapus: dinonaktifkan dengan ``is_active = false``.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.deps import Principal, current_principal, get_session, require_role
from api.errors import ApiError
from api.schemas_monitor import AcknowledgeRequest, AlertRuleCreate, AlertRuleUpdate

router = APIRouter()          # /api/alerts
rules_router = APIRouter()    # /api/alert-rules

ANALYST = [Depends(require_role("ANALYST"))]
ADMIN = [Depends(require_role("ADMIN"))]

_ALERT_SELECT = """
    SELECT a.alert_id, a.observation_date, a.region_id, r.pcode, r.region_name, a.rule_id, ru.rule_code,
           dt.type_code AS disaster_type_code, b.band_code, a.observed_value, a.threshold_value, a.severity,
           a.triggered_at, a.acknowledged_by, u.username AS acknowledged_by_username, a.acknowledged_at, a.ack_note
    FROM alert_events a
    JOIN administrative_regions r ON r.region_id = a.region_id
    JOIN alert_rules ru ON ru.rule_id = a.rule_id
    JOIN disaster_types dt ON dt.disaster_type_id = ru.disaster_type_id
    JOIN spectral_bands b ON b.band_id = ru.band_id
    LEFT JOIN v_users_safe u ON u.user_id = a.acknowledged_by
"""


def _alert(row) -> dict:
    d = dict(row)
    for k in ("observed_value", "threshold_value"):
        d[k] = None if d[k] is None else float(d[k])
    return d


@router.get("", summary="Rain alerts")
def list_alerts(sess: Session = Depends(get_session),
                status: str | None = Query(None, pattern="^(active|acknowledged)$"),
                severity: str | None = Query(None, pattern="^(INFO|WARNING|CRITICAL)$"),
                region_id: int | None = None,
                date_from: date | None = None, date_to: date | None = None,
                limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)) -> dict:
    where, params = ["true"], {}
    if status == "active":
        where.append("a.acknowledged_at IS NULL")
    elif status == "acknowledged":
        where.append("a.acknowledged_at IS NOT NULL")
    if severity:
        where.append("a.severity = :sev")
        params["sev"] = severity
    if region_id is not None:
        where.append("a.region_id = :rid")
        params["rid"] = region_id
    if date_from:
        where.append("a.observation_date >= :a")
        params["a"] = date_from
    if date_to:
        where.append("a.observation_date <= :b")
        params["b"] = date_to
    cond = " AND ".join(where)
    total = sess.scalar(text(f"SELECT count(*) FROM alert_events a WHERE {cond}"), params)
    rows = sess.execute(text(f"{_ALERT_SELECT} WHERE {cond} ORDER BY a.observation_date DESC, "
                             "CASE a.severity WHEN 'CRITICAL' THEN 3 WHEN 'WARNING' THEN 2 ELSE 1 END DESC, "
                             "a.alert_id DESC LIMIT :limit OFFSET :offset"),
                        {**params, "limit": limit, "offset": offset}).mappings().all()
    return {"items": [_alert(r) for r in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/evaluation", summary="Alert evaluation: hit / miss / false alarm", dependencies=ANALYST)
def evaluation(sess: Session = Depends(get_session), date_from: date | None = None,
               date_to: date | None = None) -> dict:
    where, params = ["true"], {}
    if date_from:
        where.append("ref_date >= :a")
        params["a"] = date_from
    if date_to:
        where.append("ref_date <= :b")
        params["b"] = date_to
    counts = dict(sess.execute(text(f"SELECT outcome, count(*) FROM v_evaluasi_alert WHERE {' AND '.join(where)} "
                                    "GROUP BY outcome"), params).all())
    hit, miss, fa = (int(counts.get(k, 0)) for k in ("HIT", "MISS", "FALSE_ALARM"))
    # Rincian per aturan (INTERFACE §2.4 "tabel per aturan"). MISS tidak punya
    # alert, jadi tidak punya aturan: dikelompokkan dengan rule_code NULL.
    by_rule: dict = {}
    for code, outcome, n in sess.execute(text(f"""
            SELECT ru.rule_code, v.outcome, count(*)
            FROM v_evaluasi_alert v
            LEFT JOIN alert_events a ON a.alert_id = v.alert_id
            LEFT JOIN alert_rules ru ON ru.rule_id = a.rule_id
            WHERE {' AND '.join(w.replace('ref_date', 'v.ref_date') for w in where)}
            GROUP BY ru.rule_code, v.outcome ORDER BY ru.rule_code NULLS LAST"""), params).all():
        r = by_rule.setdefault(code, {"rule_code": code, "hit": 0, "miss": 0, "false_alarm": 0})
        r[{"HIT": "hit", "MISS": "miss", "FALSE_ALARM": "false_alarm"}[outcome]] = int(n)
    pod = hit / (hit + miss) if hit + miss else None
    far = fa / (hit + fa) if hit + fa else None
    return {"hit": hit, "miss": miss, "false_alarm": fa,
            # Probability of detection & false alarm ratio; None bila penyebut nol
            # (tidak ada angka karangan).
            "pod": None if pod is None else round(pod, 4), "far": None if far is None else round(far, 4),
            "by_rule": list(by_rule.values()),
            "definition": "WARNING+ alerts vs verified events of the same type in the same kecamatan, "
                          "alert 0-3 days before the event (DATABASE.md §7)"}


@router.post("/{alert_id}/acknowledge", summary="Mark an alert as read", dependencies=ANALYST)
def acknowledge(alert_id: int, req: AcknowledgeRequest, sess: Session = Depends(get_session),
                principal: Principal = Depends(current_principal)) -> dict:
    row = sess.execute(text("SELECT acknowledged_at FROM alert_events WHERE alert_id = :a FOR UPDATE"),
                       {"a": alert_id}).first()
    if row is None:
        raise ApiError(404, f"Alert {alert_id} not found", "NOT_FOUND")
    if row.acknowledged_at is not None:
        raise ApiError(409, "Alert has already been acknowledged", "ALERT_ALREADY_ACKED")
    sess.execute(text("""UPDATE alert_events SET acknowledged_by = :u, acknowledged_at = now(), ack_note = :n
                         WHERE alert_id = :a"""),
                 {"u": principal.user_id, "n": (req.note or "").strip() or None, "a": alert_id})
    return _alert(sess.execute(text(_ALERT_SELECT + " WHERE a.alert_id = :a"), {"a": alert_id}).mappings().one())


# --- aturan alert -----------------------------------------------------------

_RULE_SELECT = """
    SELECT ru.rule_id, ru.rule_code, dt.type_code AS disaster_type_code, b.band_code, ru.comparator,
           ru.threshold_value, ru.severity, ru.reference_source, ru.is_active, ru.updated_by, ru.updated_at
    FROM alert_rules ru
    JOIN disaster_types dt ON dt.disaster_type_id = ru.disaster_type_id
    JOIN spectral_bands b ON b.band_id = ru.band_id
"""


def _rule(row) -> dict:
    d = dict(row)
    d["threshold_value"] = None if d["threshold_value"] is None else float(d["threshold_value"])
    return d


def _get_rule(sess: Session, rule_id: int) -> dict:
    row = sess.execute(text(_RULE_SELECT + " WHERE ru.rule_id = :r"), {"r": rule_id}).mappings().first()
    if row is None:
        raise ApiError(404, f"Alert rule {rule_id} not found", "NOT_FOUND")
    return _rule(row)


def _active_needs_threshold(is_active: bool, threshold) -> None:
    if is_active and threshold is None:
        raise ApiError(400, "An active rule needs threshold_value", "THRESHOLD_REQUIRED")


@rules_router.get("", summary="List alert rules")
def list_rules(sess: Session = Depends(get_session)) -> dict:
    rows = sess.execute(text(_RULE_SELECT + " ORDER BY b.band_code, ru.threshold_value NULLS LAST")).mappings().all()
    return {"items": [_rule(r) for r in rows], "total": len(rows)}


@rules_router.post("", status_code=201, summary="Add an alert rule", dependencies=ADMIN)
def create_rule(req: AlertRuleCreate, sess: Session = Depends(get_session),
                principal: Principal = Depends(current_principal)) -> dict:
    _active_needs_threshold(req.is_active, req.threshold_value)
    ids = sess.execute(text("""
        SELECT (SELECT disaster_type_id FROM disaster_types WHERE type_code = :t) AS dt,
               (SELECT band_id FROM spectral_bands WHERE band_code = :b) AS band"""),
        {"t": req.disaster_type_code, "b": req.band_code}).one()
    if ids.dt is None or ids.band is None:
        raise ApiError(400, "Unknown disaster_type_code or band_code", "UNKNOWN_REFERENCE")
    try:
        with sess.begin_nested():
            rule_id = sess.scalar(text("""
                INSERT INTO alert_rules (rule_code, disaster_type_id, band_id, comparator, threshold_value,
                                         severity, reference_source, is_active, updated_by)
                VALUES (:code, :dt, :band, :cmp, :thr, :sev, :ref, :act, :u) RETURNING rule_id"""),
                {"code": req.rule_code, "dt": ids.dt, "band": ids.band, "cmp": req.comparator,
                 "thr": req.threshold_value, "sev": req.severity, "ref": req.reference_source,
                 "act": req.is_active, "u": principal.user_id})
    except IntegrityError:
        raise ApiError(409, f"Rule code {req.rule_code} already exists", "RULE_CODE_TAKEN")
    return _get_rule(sess, rule_id)


@rules_router.put("/{rule_id}", summary="Change an alert rule (deactivate instead of delete)", dependencies=ADMIN)
def update_rule(rule_id: int, req: AlertRuleUpdate, sess: Session = Depends(get_session),
                principal: Principal = Depends(current_principal)) -> dict:
    current = _get_rule(sess, rule_id)
    fields = req.model_dump(exclude_unset=True)
    threshold = fields.get("threshold_value", current["threshold_value"])
    active = fields.get("is_active", current["is_active"])
    _active_needs_threshold(active, threshold)
    if fields:
        sets = ", ".join(f"{k} = :{k}" for k in fields)
        sess.execute(text(f"UPDATE alert_rules SET {sets}, updated_by = :u, updated_at = now() WHERE rule_id = :r"),
                     {**fields, "u": principal.user_id, "r": rule_id})
    return _get_rule(sess, rule_id)
