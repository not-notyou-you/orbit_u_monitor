"""Evaluasi ``alert_rules`` terhadap ``region_observations`` -> ``alert_events`` (PIPELINE.md §3.5)."""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import text

logger = logging.getLogger(__name__)

COMPARATORS = (">=", ">", "<=", "<")


def _check_sql(comparator: str) -> str:
    if comparator not in COMPARATORS:
        raise ValueError(f"unsupported comparator {comparator!r}")
    return f"""
        INSERT INTO alert_events (rule_id, region_id, obs_id, observation_date, observed_value,
                                  threshold_value, severity)
        SELECT r.rule_id, o.region_id, o.obs_id, o.obs_date, o.value, r.threshold_value, r.severity
        FROM alert_rules r
        JOIN region_observations o ON o.band_id = r.band_id
        JOIN administrative_regions ar ON ar.region_id = o.region_id AND ar.in_aoi
        WHERE r.is_active AND r.threshold_value IS NOT NULL AND r.comparator = '{comparator}'
          AND o.obs_date = :d AND o.value IS NOT NULL
          AND o.value {comparator} r.threshold_value
        ON CONFLICT (rule_id, region_id, observation_date) DO NOTHING
        RETURNING alert_id
    """


def check_alerts(sess, obs_date: date) -> list[int]:
    """Evaluasi semua aturan aktif untuk satu tanggal UTC; mengembalikan
    alert_id yang BARU dibuat (yang sudah ada tidak dihitung)."""
    created: list[int] = []
    for comparator in COMPARATORS:
        created.extend(sess.execute(text(_check_sql(comparator)), {"d": obs_date}).scalars().all())
    if created:
        logger.info("[ALERT] %s: %d alert baru", obs_date, len(created))
    return created


def bmkg_rain24_thresholds(sess) -> list[tuple[float, str]]:
    """[(ambang mm, severity)] aturan aktif RAIN_24H, naik. Dipakai Live untuk
    menyelaraskan kalimat hujan dengan ambang BMKG (PIPELINE §4)."""
    rows = sess.execute(text("""
        SELECT r.threshold_value, r.severity FROM alert_rules r
        JOIN spectral_bands b ON b.band_id = r.band_id
        WHERE b.band_code = 'RAIN_24H' AND r.is_active AND r.threshold_value IS NOT NULL
          AND r.comparator IN ('>=', '>')
        ORDER BY r.threshold_value
    """)).all()
    return [(float(t), s) for t, s in rows]
