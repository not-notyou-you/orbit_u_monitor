# etl/tier_names.py
"""
Kosakata tier — satu tempat yang tahu nama tier, peringkatnya, dan bagaimana
nama lama dipetakan ke nama baru.

Latar (DOCS/DECISIONS.md D14, diamandemen D15): kosakata medallion
(BRONZE/SILVER/GOLD) sudah tidak berarti apa yang dijanjikannya. GOLD bukan
mutu lebih tinggi dari SILVER — pikselnya identik, hanya dibungkus ulang jadi
COG, jadi itu keputusan FORMAT bukan kualitas. Dan SILVER adalah satu nama
untuk tiga operasi yang tidak sejenis: Lee filter memperbaiki variabel yang
sama, NDVI/NDWI menciptakan variabel baru, akumulasi membuat agregat temporal
baru. Itu konsekuensi langsung dari D2 (processing level per-satelit): begitu
"PROCESSED" didefinisikan per-sensor, tier hasilnya juga tidak bisa satu nama.

Karena itu tier dinamai menurut KONTRAK yang dipenuhi artefaknya, dan khusus
rank 2 namanya bercabang per-source:

    rank 0  RAW                                   format native vendor
    rank 1  ALIGNED                               EPSG:4326 + crop AOI + satuan fisis
    rank 2  DESPECKLED | INDICES | ACCUMULATED    nilai tambah spesifik source
    rank 3  COG                                   analysis-ready, HTTP range-readable
    rank 4  FUSED                                 HDF5 multi-modal
            PREVIEW                               turunan, DI LUAR rantai lineage

Rank 1 dan 3 sengaja TIDAK dipecah per-source: ketiga satelit menjamin hal
yang identik di sana, dan memberi tiga nama berbeda akan mengarang perbedaan
yang tidak ada — kesalahan cermin dari yang sedang diperbaiki.

Karena rank 2 bercabang, `TIER_ORDER` sebagai list datar tidak lagi memadai:
`rank()` yang menggantikannya.

Monitor (DATABASE.md §6, M34): product_tier_enum hanya berisi nama D14 --
skema dibangun dari nol, tidak ada baris pra-D14 yang perlu dibaca. Nama lama
masih DITERIMA sebagai input (API/CLI lama, `canonical_tier`, `rank`), tetapi
helper yang hasilnya masuk ke klausa SQL (`tiers_at_rank`, `equivalent_tiers`,
`tiers_up_to_rank`) hanya mengembalikan nama D14: literal enum yang tidak ada
di tipe PostgreSQL membuat kueri gagal (IMPLEMENTATION_NOTES K1).

Modul ini sengaja tidak mengimpor apa pun dari modul ETL lain — dia dipakai
API, orchestrator, dan skrip perawatan.
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

# Kosakata pra-D14. Hanya diterima sebagai input; tidak pernah ditulis dan
# tidak pernah dikirim ke SQL.
LEGACY_RANK: dict[str, int] = {
    "RAW": 0, "BRONZE": 1, "SILVER": 2, "GOLD": 3, "FUSION": 4,
}

LEGACY_TO_NEW: dict[str, str] = {
    "BRONZE": ALIGNED, "GOLD": COG, "FUSION": FUSED,
    # SILVER sengaja TIDAK di sini: dia bercabang tiga dan butuh source.
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
    # Enum ber-mixin str: str(ProductTierEnum.COG) = "ProductTierEnum.COG" di
    # Python 3.11+, jadi ambil .value-nya.
    return str(getattr(tier, "value", tier)).strip().upper()


def rank(tier: str) -> int:
    """Posisi lineage sebuah tier. Menerima KEDUA kosakata.

    rank("ALIGNED") == rank("BRONZE") == 1
    rank("INDICES") == rank("DESPECKLED") == rank("SILVER") == 2

    Raises ValueError untuk PREVIEW (di luar rantai lineage — dia turunan
    render, bukan mata rantai) dan untuk nama yang tidak dikenal. Sengaja
    tidak punya fallback: tier salah ketik yang diam-diam dianggap rank 0
    akan membuat compute_tiers_to_delete menghapus hal yang salah.
    """
    t = _upper(tier)
    if t in RANK:
        return RANK[t]
    if t in LEGACY_RANK:
        return LEGACY_RANK[t]
    raise ValueError(
        f"Unknown tier: {tier!r}. Valid: {sorted(set(RANK) | set(LEGACY_RANK))}"
    )


def canonical_tier(tier: str, source: str | None = None) -> str:
    """Nama D14 untuk sebuah tier. Nama baru dikembalikan apa adanya.

    `source` wajib untuk SILVER karena rank 2 bercabang tiga. Dipakai di jalur
    TULIS, di mana source selalu diketahui.
    """
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
    """Semua nama D14 yang menempati rank ini, untuk klausa SQL `IN (...)`.

    tiers_at_rank(3) -> ("COG",)
    tiers_at_rank(2) -> ("DESPECKLED", "INDICES", "ACCUMULATED")
    """
    return tuple(t for t, rr in RANK.items() if rr == r)


def sort_key(tier: str) -> tuple[int, str]:
    """Kunci urut: rank dulu, lalu nama. Nama jadi pemecah seri supaya tiga
    tier rank 2 punya urutan yang stabil antar-run."""
    return (rank(tier), _upper(tier))


def equivalent_tiers(tier: str) -> tuple[str, ...]:
    """Nama D14 yang menunjuk artefak yang sama, untuk filter baca `IN (...)`.

    Input boleh nama lama; keluaran selalu nama D14. Berbeda dari
    tiers_at_rank: INDICES tidak menjaring DESPECKLED (beda artefak, cuma satu
    rank). SILVER tidak punya padanan tunggal, jadi menjaring ketiganya.

    equivalent_tiers("COG")     -> ("COG",)
    equivalent_tiers("GOLD")    -> ("COG",)
    equivalent_tiers("INDICES") -> ("INDICES",)
    equivalent_tiers("SILVER")  -> ("DESPECKLED", "INDICES", "ACCUMULATED")
    """
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
