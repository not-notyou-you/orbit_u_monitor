# etl/backfill_runs.py
"""Proses backfill yang dimulai dari halaman Data (M56, INTERFACE.md §4.6).

Backfill GPM/MODIS adalah Job Hidromet (``etl.hydromet_job``) yang berjalan
di thread latar dengan koneksi ``monitor_etl``. Modul ini memberi setiap
jalannya sebuah nomor, progres (hari ke-i dari n), dan baris log yang bisa
dibaca halaman Data selagi berjalan — sebelumnya baris itu hanya masuk log
server.

Penyimpanan:
* di memori: daftar jalan + 500 baris log terakhir per jalan (cepat dibaca
  polling UI);
* di disk: ``logs/backfill/backfill_<id>.log`` (utuh, bertahan setelah
  server dimulai ulang);
* di basis data: hasil per tanggal tetap di ``dataset_jobs``
  (``HYDROMET_DAILY``) — itu riwayat yang awet, ditampilkan di bawah log.

Satu backfill hidromet pada satu waktu: Job Hidromet memegang advisory lock
``hydromet`` sehingga jalan kedua akan langsung berhenti dengan pesan
"kunci sedang dipakai".
"""
from __future__ import annotations

import logging
import os
import re
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from itertools import count
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

MAX_LINES = 500
MAX_RUNS = 50
_PROGRESS = re.compile(r"^\[(\d+)/(\d+)\]")
_ids = count(1)
_lock = threading.Lock()
_runs: dict[int, "Run"] = {}


def _log_dir() -> Path:
    return Path(os.getenv("LOGS_DIR", "logs")) / "backfill"


@dataclass
class Run:
    run_id: int
    source: str
    date_from: date
    date_to: date
    started_by: int | None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    status: str = "RUNNING"           # RUNNING | COMPLETED | FAILED | SKIPPED
    done: int = 0
    total: int | None = None
    summary: dict | None = None
    lines: deque = field(default_factory=lambda: deque(maxlen=MAX_LINES))

    def echo(self, message: str) -> None:
        stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        line = f"{stamp} {message}"
        m = _PROGRESS.match(message)
        if m:
            self.done, self.total = int(m.group(1)), int(m.group(2))
        with _lock:
            self.lines.append(line)
        try:
            path = _log_dir() / f"backfill_{self.run_id}.log"
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            logger.exception("[BACKFILL] gagal menulis log berkas run %s", self.run_id)
        logger.info("[BACKFILL %s/%s] %s", self.run_id, self.source, message)

    def as_dict(self, with_lines: bool = False, since: int = 0) -> dict:
        d = {"run_id": self.run_id, "source": self.source, "date_from": self.date_from, "date_to": self.date_to,
             "started_by": self.started_by, "started_at": self.started_at, "finished_at": self.finished_at,
             "status": self.status, "done": self.done, "total": self.total, "summary": self.summary,
             "n_lines": len(self.lines)}
        if with_lines:
            with _lock:
                lines = list(self.lines)
            d["lines"] = lines[since:] if since < len(lines) else []
        return d


def start(source: str, date_from: date, date_to: date, started_by: int | None,
          work: Callable[[Callable[[str], None]], dict]) -> Run:
    """Jalankan ``work(echo)`` di thread latar; ``work`` mengembalikan ringkasan."""
    run = Run(next(_ids), source, date_from, date_to, started_by)
    with _lock:
        _runs[run.run_id] = run
        for old in sorted(_runs)[:-MAX_RUNS]:
            if _runs[old].status != "RUNNING":
                del _runs[old]

    def _target() -> None:
        run.echo(f"[START] backfill {source} {date_from}..{date_to}")
        try:
            summary = work(run.echo) or {}
            run.summary = summary
            if summary.get("locked"):
                run.status = "SKIPPED"
            elif summary.get("FAILED") and not summary.get("COMPLETED"):
                run.status = "FAILED"
            else:
                run.status = "COMPLETED"
        except Exception as exc:
            logger.exception("[BACKFILL] run %s gagal", run.run_id)
            run.echo(f"[ERROR] {type(exc).__name__}: {exc}")
            run.status = "FAILED"
        finally:
            run.finished_at = datetime.now(timezone.utc)
            run.echo(f"[END] {run.status}")

    threading.Thread(target=_target, name=f"backfill-{source}-{run.run_id}", daemon=True).start()
    return run


def runs(source: str | None = None) -> list[Run]:
    with _lock:
        items = list(_runs.values())
    return sorted((r for r in items if source is None or r.source == source),
                  key=lambda r: r.run_id, reverse=True)


def get(run_id: int) -> Run | None:
    return _runs.get(run_id)


def running(source: str | None = None) -> bool:
    return any(r.status == "RUNNING" for r in runs(source))


def reset() -> None:
    """Untuk tes."""
    with _lock:
        _runs.clear()
