"""Tulis berkas keluaran lewat berkas sementara, lalu pindahkan sekali jalan."""

from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from pathlib import Path
from collections.abc import Iterator


@contextmanager
def atomic_path(final_path: Path | str) -> Iterator[Path]:
    """Berikan path sementara untuk ditulis; dipindahkan ke `final_path` saat blok selesai tanpa error."""
    final = Path(final_path)
    final.parent.mkdir(parents=True, exist_ok=True)
    tmp = final.with_name(
        f"{final.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    )
    tmp.unlink(missing_ok=True)
    try:
        yield tmp
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    os.replace(tmp, final)
