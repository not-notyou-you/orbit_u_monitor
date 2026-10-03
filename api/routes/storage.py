# api/routes/storage.py
"""
Storage API: informasi penggunaan disk per tier (hanya baca).

GET  /api/storage/summary        — ringkasan penggunaan per tier
GET  /api/storage/files/{tier}   — list file di tier tertentu

Cleanup tier lintas mesin (POST /cleanup, /cleanup/partial) warisan DataLab
sudah dihapus (README §5); berkas hanya dihapus lewat penghapusan dataset dan
retensi Live.

Author : Julius Marselinus (BRONTO) - NIM 00000111989
Program: Sistem Informasi - Universitas Multimedia Nusantara
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from etl import folder_manager as fm

router = APIRouter()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

StorageTier = Literal["raw", "bronze", "silver", "gold", "preview", "fusion", "partial"]


def _dataset_roots() -> list[Path]:
    """Semua folder dataset di data/datasets/. Endpoint di router ini
    lintas-dataset (ringkasan disk mesin), sementara
    /api/datasets/{id}/storage/summary adalah versi satu dataset."""
    if not fm.DATA_ROOT.exists():
        return []
    return sorted(d for d in fm.DATA_ROOT.iterdir() if d.is_dir())


def _get_tier_paths() -> dict[str, list[Path]]:
    """Folder per tier di layout dataset-tanggal-tier sekarang, dikumpulkan
    dari seluruh dataset: data/datasets/{id}_{slug}/{tanggal}/{tier}/ untuk
    tiap tanggal, ditambah _granule_cache/ untuk tier raw."""
    roots = _dataset_roots()
    paths = {
        tier: [d for r in roots for d in fm.tier_dirs_under(r, tier)] for tier in fm.TIERS
    }
    paths["partial"] = [d for tier in fm.TIERS for d in paths[tier]]
    return paths


def _dir_info(path: Path, ext_filter: str | None = None) -> dict:
    """Hitung jumlah file dan total ukuran di sebuah direktori."""
    if not path.exists():
        return {"path": str(path), "exists": False, "file_count": 0, "size_mb": 0.0, "files": []}

    files = []
    total_bytes = 0

    for f in sorted(path.rglob("*")):
        if f.is_file():
            if ext_filter and not f.name.endswith(ext_filter):
                continue
            size_mb = f.stat().st_size / (1024 ** 2)
            total_bytes += f.stat().st_size
            files.append({
                "name":    f.name,
                "path":    str(f),
                "size_mb": round(size_mb, 2),
            })

    return {
        "path":       str(path),
        "exists":     True,
        "file_count": len(files),
        "size_mb":    round(total_bytes / (1024 ** 2), 2),
        "files":      files,
    }


def _human(mb: float) -> str:
    return f"{mb / 1024:.2f} GB" if mb >= 1024 else f"{mb:.1f} MB"


# ---------------------------------------------------------------------------
# ROUTES
# ---------------------------------------------------------------------------

@router.get(
    "/summary",
    summary="Storage summary",
    description="Shows disk usage per tier, including file counts.",
)
async def storage_summary() -> JSONResponse:
    tier_paths = _get_tier_paths()
    tiers = {}
    by_source: dict[str, dict] = {}
    total_mb = 0.0

    for tier_name in fm.TIERS:
        size_mb = 0.0
        count   = 0
        sources: dict[str, dict] = {}

        for tier_dir in tier_paths[tier_name]:
            info = _dir_info(tier_dir)
            size_mb += info["size_mb"]
            count   += info["file_count"]
            # Pecahan per source dibaca dari subfolder source di dalam tier.
            # Tier fusion tidak punya level itu (isinya gabungan semua
            # source), jadi dilewati -- sama seperti folder_manager.
            for src in fm.sources_for_tier(tier_name):
                sub = _dir_info(tier_dir / src)
                if sub["file_count"] == 0:
                    continue
                agg = sources.setdefault(src, {"size_mb": 0.0, "file_count": 0})
                agg["size_mb"] += sub["size_mb"]
                agg["file_count"] += sub["file_count"]
                tot = by_source.setdefault(src, {"size_mb": 0.0, "file_count": 0})
                tot["size_mb"] += sub["size_mb"]
                tot["file_count"] += sub["file_count"]

        total_mb += size_mb
        tiers[tier_name] = {
            "size_mb":    round(size_mb, 2),
            "size_human": _human(size_mb),
            "file_count": count,
            "sources": {
                src: {
                    "size_mb": round(v["size_mb"], 2),
                    "size_human": _human(v["size_mb"]),
                    "file_count": v["file_count"],
                }
                for src, v in sources.items()
            },
        }

    # Hitung file .part (download tidak selesai). Sisa download terputus bisa
    # muncul di tier mana pun yang menulis lewat file .part, bukan cuma raw.
    partial_mb    = 0.0
    partial_count = 0
    seen_partial: set[Path] = set()
    for p in tier_paths["partial"]:
        if not p.exists():
            continue
        for f in p.rglob("*.part"):
            if f in seen_partial:
                continue
            seen_partial.add(f)
            partial_mb    += f.stat().st_size / (1024 ** 2)
            partial_count += 1

    return JSONResponse(content={
        "tiers": {
            "raw": {
                **tiers["raw"],
                "description": "Original downloaded ZIP files + extracted TIFs",
                "note":        "Delete this after the pipeline finishes (keep_raw=false)",
            },
            "bronze": {
                **tiers["bronze"],
                "description": "After cropping to the AOI (Module 2)",
                "note":        "±50 MB per scene per band",
            },
            "silver": {
                **tiers["silver"],
                "description": "After Lee-filter noise reduction (Module 3)",
                "note":        "±45 MB per scene per band",
            },
            "gold": {
                **tiers["gold"],
                "description": "Analysis-ready COG per source (Module 4) — the most important one",
                "note":        "DO NOT delete this unless the scene is no longer needed",
            },
            "fusion": {
                **tiers["fusion"],
                "description": "Multi-modal HDF5 combining all sources (Module 9)",
                "note":        "Final deliverable — not deleted by tier 'all'",
            },
        },
        "by_source": {
            src: {
                "size_mb": round(v["size_mb"], 2),
                "size_human": _human(v["size_mb"]),
                "file_count": v["file_count"],
            }
            for src, v in by_source.items()
        },
        "partial_downloads": {
            "size_mb":    round(partial_mb, 2),
            "size_human": _human(partial_mb),
            "file_count": partial_count,
            "note":       "A .part file is an interrupted download, which can be resumed automatically",
        },
        "total": {
            "size_mb":    round(total_mb, 2),
            "size_human": _human(total_mb),
        },
    })


@router.get(
    "/files/{tier}",
    summary="List file per tier",
    description="List all files in a given tier (raw/bronze/silver/gold).",
)
async def list_files(tier: StorageTier) -> JSONResponse:
    tier_paths = _get_tier_paths()
    paths = tier_paths.get(tier, [])

    result = []
    for p in paths:
        ext = ".part" if tier == "partial" else None
        info = _dir_info(p, ext_filter=ext)
        result.append(info)

    return JSONResponse(content={"tier": tier, "directories": result})
