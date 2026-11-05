"""Strategi fusi — terjemahan `datasets.fusion_strategy` menjadi dua keputusan
konkret yang selama ini tercampur jadi satu.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date as date_type, timedelta

logger = logging.getLogger(__name__)

CO_OCCURRENCE = "CO_OCCURRENCE"
FULL_COVERAGE = "FULL_COVERAGE"
HYBRID = "HYBRID"

DEFAULT_S1_MATCH_TOLERANCE_DAYS = 2

SUBFOLDER: dict[str, str] = {
    CO_OCCURRENCE: "co-occurrence",
    FULL_COVERAGE: "full-coverage",
    HYBRID: "hybrid",
}

FILENAME_SUFFIX: dict[str, str] = {
    CO_OCCURRENCE: "cooccurrence",
    FULL_COVERAGE: "fullcoverage",
    HYBRID: "hybrid",
}


@dataclass(frozen=True)
class FusionPlan:
    """Keputusan kedua sumbu untuk satu dataset, sudah jadi tanggal konkret."""

    strategy: str
    subfolder: str
    fusion_dates: tuple[date_type, ...]
    aux_dates: tuple[date_type, ...]
    anchor_for: dict[date_type, date_type | None]
    tolerance_days: int

    def anchor(self, fusion_date: date_type) -> date_type | None:
        return self.anchor_for.get(fusion_date)

    def offset_days(self, fusion_date: date_type) -> int | None:
        """Selisih hari antara tanggal fusi dan scene S1 yang dipakai."""
        anchor = self.anchor_for.get(fusion_date)
        if anchor is None:
            return None
        return abs((fusion_date - anchor).days)

    @property
    def requires_s1(self) -> bool:
        """True kalau S1 yang hilang membatalkan tanggal fusi."""
        return self.strategy in (CO_OCCURRENCE, HYBRID)


def _daterange(date_from: date_type, date_to: date_type) -> tuple[date_type, ...]:
    if date_to < date_from:
        return ()
    span = (date_to - date_from).days
    return tuple(date_from + timedelta(days=i) for i in range(span + 1))


def _nearest_s1(
    target: date_type, s1_dates: tuple[date_type, ...], tolerance_days: int
) -> date_type | None:
    """Scene S1 terdekat dari `target` dalam toleransi, atau None."""
    best: date_type | None = None
    best_gap: int | None = None
    for candidate in s1_dates:
        gap = abs((target - candidate).days)
        if gap > tolerance_days:
            continue
        if best_gap is None or gap < best_gap or (gap == best_gap and candidate < best):
            best, best_gap = candidate, gap
    return best


def _normalize_s1_dates(s1_dates) -> tuple[date_type, ...]:
    """Buang duplikat lalu urutkan. Satu tanggal bisa punya lebih dari satu
    scene S1 (orbit menaik + menurun), tapi untuk perencanaan temporal yang
    dihitung adalah tanggalnya, bukan jumlah scene-nya."""
    return tuple(sorted({d for d in s1_dates if d is not None}))


def plan_fusion(
    strategy: str,
    s1_dates,
    date_from: date_type,
    date_to: date_type,
    tolerance_days: int = DEFAULT_S1_MATCH_TOLERANCE_DAYS,
) -> FusionPlan:
    """Susun FusionPlan untuk satu dataset."""
    s1 = _normalize_s1_dates(s1_dates)
    strategy = str(strategy).strip().upper()

    if strategy == CO_OCCURRENCE:
        fusion_dates = s1
        aux_dates = s1
        anchor_for = {d: d for d in s1}

    elif strategy == HYBRID:
        fusion_dates = s1
        aux_dates = _daterange(date_from, date_to)
        anchor_for = {d: d for d in s1}

    elif strategy == FULL_COVERAGE:
        fusion_dates = _daterange(date_from, date_to)
        aux_dates = fusion_dates
        anchor_for = {d: _nearest_s1(d, s1, tolerance_days) for d in fusion_dates}

    else:
        raise ValueError(
            f"unknown fusion_strategy: {strategy!r} "
            f"(pilihan: {CO_OCCURRENCE}, {FULL_COVERAGE}, {HYBRID})"
        )

    plan = FusionPlan(
        strategy=strategy,
        subfolder=SUBFOLDER[strategy],
        fusion_dates=tuple(fusion_dates),
        aux_dates=tuple(aux_dates),
        anchor_for=anchor_for,
        tolerance_days=tolerance_days,
    )

    logger.info(
        "[FUSION] strategi=%s tanggal_fusi=%d tanggal_aux=%d tanpa_s1=%d toleransi=%d",
        strategy, len(plan.fusion_dates), len(plan.aux_dates),
        sum(1 for v in anchor_for.values() if v is None), tolerance_days,
    )
    return plan
