"""Lock lintas-PROSES untuk job dataset."""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

LOCK_DIRNAME = "_job_locks"

if os.name == "nt":
    import msvcrt

    def _try_lock(fd: int) -> bool:
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False

    def _unlock(fd: int) -> None:
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
else:
    import fcntl

    def _try_lock(fd: int) -> bool:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def _unlock(fd: int) -> None:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass


class JobLock:
    """Kepemilikan eksklusif satu job_id lintas proses."""

    def __init__(self, key: str, lock_dir: Path) -> None:
        self._key = key
        self._path = lock_dir / f"{key}.lock"
        self._fd: int | None = None

    @classmethod
    def acquire(cls, job_id: int, lock_dir: Path) -> JobLock | None:
        return cls.acquire_key(f"job-{job_id}", lock_dir)

    @classmethod
    def acquire_key(cls, key: str, lock_dir: Path) -> JobLock | None:
        """Sama seperti `acquire()`, tapi untuk pemanggil yang bukan job
        dataset biasa -- kuncinya string bebas (mis. "live-area-{id}"), bukan
        job_id. Nama filenya persis `key`, dan pemanggil bertanggung jawab
        memilih awalan yang tidak pernah bertabrakan dengan "job-{job_id}"."""
        lock = cls(key, lock_dir)
        try:
            lock_dir.mkdir(parents=True, exist_ok=True)
            fd = os.open(lock._path, os.O_RDWR | os.O_CREAT, 0o644)
        except OSError:
            logger.warning(
                "[JOBLOCK] key=%s tidak bisa membuka berkas lock, lanjut tanpa lock",
                key, exc_info=True,
            )
            return lock

        if not _try_lock(fd):
            os.close(fd)
            return None

        lock._fd = fd
        try:
            os.write(fd, f"pid={os.getpid()}".ljust(32)[:32].encode())
        except OSError:
            pass
        return lock

    def release(self) -> None:
        if self._fd is None:
            return
        _unlock(self._fd)
        try:
            os.close(self._fd)
        except OSError:
            pass
        self._fd = None

    def __repr__(self) -> str:
        return f"<JobLock key={self._key} held={self._fd is not None}>"
