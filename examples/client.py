#!/usr/bin/env python
"""Klien Python kecil untuk API Orbit-U: The Monitor (INTERFACE.md §6.1).

Membungkus token API (`Authorization: Bearer trn_...`), pagination kontrak
`{items, total, limit, offset}`, unduhan streaming, dan pesan error `{detail, code}`.
Hanya butuh `requests`.

    export ORBIT_U_URL=https://monitor.example.org ORBIT_U_TOKEN=trn_...
    python examples/client.py                      # demo singkat
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Iterator

import requests


class OrbitUError(RuntimeError):
    def __init__(self, status: int, code: str, detail: str):
        super().__init__(f"{status} {code}: {detail}")
        self.status, self.code, self.detail = status, code, detail


class OrbitUClient:
    def __init__(self, base_url: str, token: str, timeout: float = 60):
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.s = requests.Session()
        self.s.headers["Authorization"] = f"Bearer {token}"

    # -- dasar ----------------------------------------------------------------
    def _check(self, r: requests.Response) -> requests.Response:
        if r.status_code >= 400:
            try:
                body = r.json()
            except ValueError:
                body = {"detail": r.text[:200], "code": f"HTTP_{r.status_code}"}
            raise OrbitUError(r.status_code, body.get("code", ""), body.get("detail", ""))
        return r

    def get(self, path: str, **params: Any) -> Any:
        params = {k: v for k, v in params.items() if v is not None}
        return self._check(self.s.get(self.base + path, params=params, timeout=self.timeout)).json()

    def paginate(self, path: str, limit: int = 500, **params: Any) -> Iterator[dict]:
        """Semua item dari endpoint daftar, halaman demi halaman."""
        offset = 0
        while True:
            page = self.get(path, limit=limit, offset=offset, **params)
            yield from page["items"]
            offset += len(page["items"])
            if not page["items"] or offset >= page["total"]:
                return

    def download(self, path: str, dest: str | Path, **params: Any) -> Path:
        """Unduhan streaming (butuh token ber-scope READ_DOWNLOAD). Nama berkas dari server bila `dest` folder."""
        with self._check(self.s.get(self.base + path, params=params, stream=True, timeout=self.timeout)) as r:
            dest = Path(dest)
            if dest.is_dir():
                cd = r.headers.get("content-disposition", "")
                name = cd.split("filename=")[-1].strip('"; ') if "filename=" in cd else path.rsplit("/", 1)[-1]
                dest = dest / name
            tmp = dest.with_suffix(dest.suffix + ".part")
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
            tmp.replace(dest)
        return dest

    # -- pintasan -------------------------------------------------------------
    def me(self) -> dict:
        return self.get("/api/auth/me")

    def observations(self, band: str = "RAIN_24H", **filters: Any) -> list[dict]:
        return list(self.paginate("/api/hydromet/observations", band=band, **filters))

    def lineage(self, product_id: int, direction: str = "ancestors") -> list[dict]:
        return self.get(f"/api/metadata/lineage/{product_id}", direction=direction)["chain"]


def main() -> int:
    url, token = os.environ.get("ORBIT_U_URL", "http://127.0.0.1:8000"), os.environ.get("ORBIT_U_TOKEN")
    if not token:
        print("Set ORBIT_U_TOKEN (Akun Saya → Token API).", file=sys.stderr)
        return 2
    c = OrbitUClient(url, token)
    me = c.me()
    print(f"Masuk sebagai {me['username']} ({me['role_code']})")
    today = c.get("/api/hydromet/today")
    print(f"Hujan {today['obs_date']}:")
    for r in today["regions"]:
        print(f"  {r['name']:<14} {r['rain_24h_mm'] if r['rain_24h_mm'] is not None else '—':>7} mm  {r['bmkg_category'] or ''}")
    try:
        rows = c.observations("RAIN_24H", date_from="2024-01-01", date_to="2024-01-31")
        print(f"{len(rows)} observasi RAIN_24H Januari 2024")
    except OrbitUError as e:  # USER: hanya 30 hari terakhir
        print(f"Observasi arsip ditolak: {e.code}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
