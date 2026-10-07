"""Backfill berhenti lebih awal saat hari FAILED menumpuk berurutan.

Kenapa ada: gangguan jaringan membuat setiap tanggal gagal di tahap download.
Tanpa penjaga ini, satu rentang 2 tahun menyapu ~730 tanggal dalam keadaan
jaringan mati, menghabiskan berjam-jam tanpa menghasilkan satu baris pun
(backfill 2026-10-05 harus dihentikan manual). Tanggal yang belum COMPLETED
tidak hilang, jadi berhenti lebih awal tidak merugikan.

Tidak menyentuh database: pending_dates/context/run_day dan advisory_lock
disulih, karena yang diuji murni logika pengulangan di backfill().
"""

from __future__ import annotations

import contextlib
from datetime import date, timedelta

import pytest

from etl import advisory_lock as al
from etl import hydromet_job as hj


@pytest.fixture(autouse=True)
def _no_db(monkeypatch):
    """Lepaskan backfill() dari PostgreSQL: lock selalu didapat, konteks kosong."""
    @contextlib.contextmanager
    def _always_got(_db, _name):
        yield True

    monkeypatch.setattr(al, "advisory_lock", _always_got)
    monkeypatch.setattr(hj, "context", lambda _db: object())


def _dates(n: int) -> list[date]:
    start = date(2024, 1, 1)
    return [start + timedelta(days=i) for i in range(n)]


def _stub_run_day(monkeypatch, statuses: list[str]) -> list[date]:
    """run_day mengembalikan `statuses` berurutan; mencatat tanggal yang dikerjakan."""
    seen: list[date] = []
    seq = iter(statuses)

    def fake(_db, obs_date, **_kw):
        seen.append(obs_date)
        return hj.DayResult(obs_date=obs_date, status=next(seq), message="stub")

    monkeypatch.setattr(hj, "run_day", fake)
    return seen


def _pending(monkeypatch, days: list[date]) -> None:
    monkeypatch.setattr(hj, "pending_dates", lambda *_a, **_k: list(days))


def test_berhenti_setelah_lima_gagal_berurutan(monkeypatch):
    days = _dates(30)
    _pending(monkeypatch, days)
    seen = _stub_run_day(monkeypatch, ["FAILED"] * 30)

    summary = hj.backfill(None, days[0], days[-1], echo=lambda *_: None)

    # Berhenti tepat di hari kelima, bukan menyapu 30 tanggal.
    assert len(seen) == 5
    assert summary["FAILED"] == 5
    assert summary["aborted_after"] == str(days[4])


def test_gagal_terputus_tidak_memicu_berhenti(monkeypatch):
    # 4 gagal, 1 sukses (reset), 4 gagal lagi: tidak pernah 5 berurutan.
    statuses = ["FAILED"] * 4 + ["COMPLETED"] + ["FAILED"] * 4
    days = _dates(len(statuses))
    _pending(monkeypatch, days)
    seen = _stub_run_day(monkeypatch, statuses)

    summary = hj.backfill(None, days[0], days[-1], echo=lambda *_: None)

    assert len(seen) == len(statuses)
    assert "aborted_after" not in summary
    assert summary["FAILED"] == 8
    assert summary["COMPLETED"] == 1


def test_waiting_upstream_bukan_kegagalan(monkeypatch):
    """Granule yang belum terbit itu normal, bukan tanda jaringan rusak."""
    days = _dates(10)
    _pending(monkeypatch, days)
    seen = _stub_run_day(monkeypatch, ["WAITING_UPSTREAM"] * 10)

    summary = hj.backfill(None, days[0], days[-1], echo=lambda *_: None)

    assert len(seen) == 10
    assert "aborted_after" not in summary
    assert summary["WAITING_UPSTREAM"] == 10


def test_nol_mematikan_penjaga(monkeypatch):
    days = _dates(12)
    _pending(monkeypatch, days)
    seen = _stub_run_day(monkeypatch, ["FAILED"] * 12)

    summary = hj.backfill(None, days[0], days[-1], max_consecutive_failures=0,
                          echo=lambda *_: None)

    assert len(seen) == 12
    assert "aborted_after" not in summary


def test_ambang_bisa_diatur(monkeypatch):
    days = _dates(12)
    _pending(monkeypatch, days)
    seen = _stub_run_day(monkeypatch, ["FAILED"] * 12)

    summary = hj.backfill(None, days[0], days[-1], max_consecutive_failures=2,
                          echo=lambda *_: None)

    assert len(seen) == 2
    assert summary["aborted_after"] == str(days[1])
