"""Data lineage tracking: SHA-256 hashing, parent→child product linking,
and provenance query for audit trail.
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

from sqlalchemy import select

from etl.database_client import (
    DataLineage,
    DataProduct,
    DatabaseClient,
    ProcessingStage,
)

logger = logging.getLogger(__name__)

_HASH_CHUNK_BYTES = 8 * 1024 * 1024


class LineageTracker:
    """Tracks data provenance across ETL pipeline stages."""

    _TRANSFORM_STAGE_MAP: dict[str, str] = {
        "CROP":        "CROP",
        "LEE_FILTER":  "LEE_FILTER",
        "COG_EXPORT":  "COG_EXPORT",
        "GOLD_EXPORT": "GOLD_EXPORT",
        "FUSION":      "FUSION",
        "ANALYTICS":   "QUALITY_ANALYTICS",
    }

    def __init__(self, db: DatabaseClient) -> None:
        self._db = db

    @staticmethod
    def compute_sha256(file_path: str | Path) -> str:
        """Compute SHA-256 hash of a file using streaming reads.
        Handles large GeoTIFF files (multiple GB) without loading into RAM.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found for hashing: {path}")

        h = hashlib.sha256()
        file_size = path.stat().st_size

        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(_HASH_CHUNK_BYTES), b""):
                h.update(chunk)

        digest = h.hexdigest()
        logger.debug("[HASH] %s → %s (%.2f MB)", path.name, digest[:12] + "...",
                     file_size / (1024 ** 2))
        return digest

    @staticmethod
    def compute_sha256_from_bytes(data: bytes) -> str:
        """Compute SHA-256 from an in-memory bytes object."""
        return hashlib.sha256(data).hexdigest()

    def record_transformation(
        self,
        parent_product_id: int,
        child_product_id: int,
        transformation_type: str,
        job_id: int,
        params: dict | None = None,
    ) -> int:
        """Record a parent→child product transformation in data_lineage."""
        stage_name = self._TRANSFORM_STAGE_MAP.get(transformation_type)
        if not stage_name:
            raise ValueError(
                f"Unknown transformation_type: '{transformation_type}'. "
                f"Valid: {list(self._TRANSFORM_STAGE_MAP.keys())}"
            )

        with self._db.session() as sess:
            stage_id = sess.scalar(
                select(ProcessingStage.stage_id).where(
                    ProcessingStage.stage_name == stage_name
                )
            )
            if not stage_id:
                raise ValueError(f"Stage '{stage_name}' not found in processing_stages")

            parent = sess.get(DataProduct, parent_product_id)
            child  = sess.get(DataProduct, child_product_id)
            if not parent:
                raise ValueError(f"parent_product_id={parent_product_id} not found")
            if not child:
                raise ValueError(f"child_product_id={child_product_id} not found")

            lineage = DataLineage(
                parent_product_id    = parent_product_id,
                child_product_id     = child_product_id,
                transformation_type  = transformation_type,
                stage_id             = stage_id,
                job_id               = job_id,
                transformation_params = params or {},
                input_checksum       = parent.data_hash_sha256,
                output_checksum      = child.data_hash_sha256,
            )
            sess.add(lineage)
            sess.flush()
            lineage_id = lineage.lineage_id

        logger.info("[LINEAGE] lineage_id=%d parent=%d →[%s]→ child=%d",
                    lineage_id, parent_product_id, transformation_type, child_product_id)
        return lineage_id

    def get_lineage_chain(self, product_id: int, direction: str = "ancestors") -> list[dict]:
        """Recursively trace the transformation chain for a product."""
        chain = []
        visited = set()

        with self._db.session() as sess:
            self._trace_recursive(sess, product_id, direction, chain, visited)

        logger.info("[LINEAGE] Chain for product=%d direction=%s → %d steps",
                    product_id, direction, len(chain))
        return chain

    def _trace_recursive(
        self,
        sess,
        product_id: int,
        direction: str,
        chain: list,
        visited: set,
    ) -> None:
        """Internal recursive lineage traversal."""
        if product_id in visited:
            return
        visited.add(product_id)

        if direction == "ancestors":
            lineages = sess.scalars(
                select(DataLineage).where(DataLineage.child_product_id == product_id)
            ).all()
            for lin in lineages:
                chain.insert(0, self._lineage_to_dict(lin, sess))
                self._trace_recursive(sess, lin.parent_product_id, direction, chain, visited)
        else:
            lineages = sess.scalars(
                select(DataLineage).where(DataLineage.parent_product_id == product_id)
            ).all()
            for lin in lineages:
                chain.append(self._lineage_to_dict(lin, sess))
                self._trace_recursive(sess, lin.child_product_id, direction, chain, visited)

    def _lineage_to_dict(self, lin: DataLineage, sess=None) -> dict:
        """Serialize a DataLineage ORM object to dict."""
        out = {
            "lineage_id":             lin.lineage_id,
            "parent_product_id":      lin.parent_product_id,
            "child_product_id":       lin.child_product_id,
            "transformation_type":    lin.transformation_type,
            "stage_id":               lin.stage_id,
            "job_id":                 lin.job_id,
            "transformation_params":  lin.transformation_params,
            "input_checksum":         lin.input_checksum,
            "output_checksum":        lin.output_checksum,
            "created_at":             lin.created_at.isoformat(),
            "source":                 None,
            "parent_tier":            None,
            "child_tier":             None,
        }
        if sess is not None:
            parent = sess.get(DataProduct, lin.parent_product_id)
            child = sess.get(DataProduct, lin.child_product_id)
            if child is not None:
                out["source"] = child.source
                out["child_tier"] = child.product_tier.value
            if parent is not None:
                out["parent_tier"] = parent.product_tier.value
                if out["source"] is None:
                    out["source"] = parent.source
        return out

    def verify_integrity(self, product_id: int, file_path: str) -> dict:
        """Verify a file's current SHA-256 against the stored hash."""
        with self._db.session() as sess:
            product = sess.get(DataProduct, product_id)
            if not product:
                raise ValueError(f"product_id={product_id} not found")
            stored_hash = product.data_hash_sha256

        computed_hash = self.compute_sha256(file_path)
        file_size_mb  = os.path.getsize(file_path) / (1024 ** 2)
        integrity_ok  = stored_hash == computed_hash

        result = {
            "product_id":   product_id,
            "file_path":    file_path,
            "stored_hash":  stored_hash,
            "computed_hash": computed_hash,
            "integrity_ok": integrity_ok,
            "file_size_mb": round(file_size_mb, 3),
        }

        if integrity_ok:
            logger.info("[INTEGRITY] product_id=%d ✓ hash match", product_id)
        else:
            logger.error("[INTEGRITY] product_id=%d ✗ HASH MISMATCH stored=%s computed=%s",
                         product_id, stored_hash[:12], computed_hash[:12])

        return result
