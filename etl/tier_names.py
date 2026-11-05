"""Kosakata tier — satu tempat yang tahu nama tier, peringkatnya, dan bagaimana
nama lama dipetakan ke nama baru.
"""

from __future__ import annotations

RAW = "RAW"
ALIGNED = "ALIGNED"
DESPECKLED = "DESPECKLED"
INDICES = "INDICES"
ACCUMULATED = "ACCUMULATED"
COG = "COG"
FUSED = "FUSED"
PREVIEW = "PREVIEW"

RANK: dict[str, int] = {
    RAW: 0,
    ALIGNED: 1,
    DESPECKLED: 2, INDICES: 2, ACCUMULATED: 2,
    COG: 3,
    FUSED: 4,
}

LEGACY_RANK: dict[str, int] = {
    "RAW": 0, "BRONZE": 1, "SILVER": 2, "GOLD": 3, "FUSION": 4,
}

LEGACY_TO_NEW: dict[str, str] = {
    "BRONZE": ALIGNED, "GOLD": COG, "FUSION": FUSED,
}

RANK2_BY_SOURCE: dict[str, str] = {
    "SENTINEL1": DESPECKLED,
    "MODIS": INDICES,
    "GPM": ACCUMULATED,
}

TIERS: tuple[str, ...] = (RAW, ALIGNED, DESPECKLED, INDICES, ACCUMULATED, COG, FUSED)
LEGACY_TIERS: tuple[str, ...] = ("BRONZE", "SILVER", "GOLD", "FUSION")
ALL_TIERS: tuple[str, ...] = TIERS + LEGACY_TIERS + (PREVIEW,)


def _upper(tier: str) -> str:
    return str(getattr(tier, "value", tier)).strip().upper()


def rank(tier: str) -> int:
    """Posisi lineage sebuah tier. Menerima KEDUA kosakata."""
    t = _upper(tier)
    if t in RANK:
        return RANK[t]
    if t in LEGACY_RANK:
        return LEGACY_RANK[t]
    raise ValueError(
        f"Unknown tier: {tier!r}. Valid: {sorted(set(RANK) | set(LEGACY_RANK))}"
    )


def canonical_tier(tier: str, source: str | None = None) -> str:
    """Nama D14 untuk sebuah tier. Nama baru dikembalikan apa adanya."""
    t = _upper(tier)
    if t in RANK or t == PREVIEW:
        return t
    if t == "SILVER":
        if source is None:
            raise ValueError(
                "SILVER needs `source` to be mapped: rank 2 branches into "
                f"{sorted(RANK2_BY_SOURCE.values())}"
            )
        return RANK2_BY_SOURCE[_upper(source)]
    if t in LEGACY_TO_NEW:
        return LEGACY_TO_NEW[t]
    raise ValueError(f"Unknown tier: {tier!r}")


def tiers_at_rank(r: int) -> tuple[str, ...]:
    """Semua nama D14 yang menempati rank ini, untuk klausa SQL `IN (...)`."""
    return tuple(t for t, rr in RANK.items() if rr == r)


def sort_key(tier: str) -> tuple[int, str]:
    """Kunci urut: rank dulu, lalu nama. Nama jadi pemecah seri supaya tiga
    tier rank 2 punya urutan yang stabil antar-run."""
    return (rank(tier), _upper(tier))


def equivalent_tiers(tier: str) -> tuple[str, ...]:
    """Nama D14 yang menunjuk artefak yang sama, untuk filter baca `IN (...)`."""
    t = _upper(tier)
    if t == PREVIEW:
        return (PREVIEW,)
    r = rank(t)  # melempar untuk nama tak dikenal
    if t == "SILVER":
        return tiers_at_rank(r)
    return (LEGACY_TO_NEW.get(t, t),)


def tiers_up_to_rank(r: int) -> tuple[str, ...]:
    """Semua nama D14 dengan rank <= r."""
    return tuple(t for i in range(r + 1) for t in tiers_at_rank(i))
