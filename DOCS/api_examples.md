# Contoh Pemakaian API — Orbit-U: The Monitor

Alur lengkap untuk developer (INTERFACE.md §6.1): buat token → ambil observasi
hidromet → ekspor CSV → daftar dataset → unduh produk/fusion HDF5 → telusuri
lineage. Rujukan endpoint lengkap: `/docs` (Swagger) atau `/openapi.json`;
setiap operasi mencantumkan role minimum (`x-min-role`), contoh, dan skema error.
Klien Python siap pakai: [`examples/client.py`](../examples/client.py).

## 0. Aturan dasar

| Hal | Ketentuan |
|---|---|
| Base URL | `https://<host>/api` (contoh di bawah: `$ORBIT_U_URL`) |
| Autentikasi skrip | `Authorization: Bearer trn_…` (token pribadi) |
| Hak token | Hanya `GET`. Scope `READ` = data; `READ_DOWNLOAD` = data + unduhan berkas. Tulis → 403 `TOKEN_WRITE_FORBIDDEN` |
| Role | Token berjalan dengan role pemiliknya (USER/ANALYST/DATA_ENGINEER/ADMIN), termasuk GRANT dan RLS di basis data |
| Batas laju | 120 request/menit per token → 429 `RATE_LIMITED` + `Retry-After: 60` |
| Daftar | `{"items": [...], "total": N, "limit": L, "offset": O}` |
| Tanggal | `YYYY-MM-DD`; hari hidromet = hari UTC = 07.00–07.00 WIB |
| Error | `{"detail": "...", "code": "..."}` — gunakan `code`, bukan teks `detail` |
| Pencatatan | Setiap request bertoken dicatat (`API_REQUEST`); unduhan dicatat dengan byte yang benar-benar terkirim |

## 1. Buat token

Token dibuat lewat web (**Akun Saya → Token API**) karena hanya sesi web yang boleh menulis.
Nilai `trn_…` tampil **sekali**; simpan di variabel lingkungan:

```bash
export ORBIT_U_URL="https://monitor.example.org"
export ORBIT_U_TOKEN="trn_3fQ9…"
curl -s -H "Authorization: Bearer $ORBIT_U_TOKEN" "$ORBIT_U_URL/api/auth/me"
```

```json
{"user_id": 3, "username": "analis1", "role_code": "ANALYST", "auth": "token", "permissions": ["hydromet.today", "analytics.view"]}
```

Setara via browser (sesi web): `POST /api/auth/tokens` dengan header `X-Requested-With: orbit-u`,
body `{"name": "skrip analisis", "scope": "READ_DOWNLOAD", "expires_in_days": 90}` (≤ 180 hari).

## 2. Statistik hari ini dan observasi harian

```bash
curl -s -H "Authorization: Bearer $ORBIT_U_TOKEN" "$ORBIT_U_URL/api/hydromet/today"

curl -s -H "Authorization: Bearer $ORBIT_U_TOKEN" \
  "$ORBIT_U_URL/api/hydromet/observations?region_id=12&band=RAIN_24H&date_from=2025-01-01&date_to=2025-12-31&limit=500"
```

Band: `RAIN_24H RAIN_72H RAIN_7D RAIN_30D NDVI NDWI FLOOD`. USER hanya boleh data 30 hari
terakhir (403 `DATE_OUT_OF_RANGE`); ANALYST ke atas seluruh arsip.

```python
import os, requests
H = {"Authorization": "Bearer " + os.environ["ORBIT_U_TOKEN"]}
URL = os.environ["ORBIT_U_URL"]

rows, offset = [], 0
while True:
    r = requests.get(f"{URL}/api/hydromet/observations", headers=H, timeout=60,
                     params={"band": "RAIN_24H", "date_from": "2025-01-01", "date_to": "2025-12-31",
                             "limit": 5000, "offset": offset})
    r.raise_for_status()
    page = r.json()
    rows += page["items"]
    offset += len(page["items"])
    if not page["items"] or offset >= page["total"]:
        break
print(len(rows), "observasi")
```

Tren siap-grafik: `GET /api/hydromet/trend?band=RAIN_24H&days=30`. Batas kecamatan (GeoJSON):
`GET /api/regions` (`?all=true` untuk seluruh Kabupaten Lebak).

## 3. Ekspor CSV / Excel

```bash
curl -s -H "Authorization: Bearer $ORBIT_U_TOKEN" -o hujan_2025.csv \
  "$ORBIT_U_URL/api/hydromet/observations.csv?band=RAIN_24H&date_from=2025-01-01&date_to=2025-12-31"

curl -s -H "Authorization: Bearer $ORBIT_U_TOKEN" "$ORBIT_U_URL/api/excel"          # jenis data per role
curl -s -H "Authorization: Bearer $ORBIT_U_TOKEN" -o kejadian.xlsx \
  "$ORBIT_U_URL/api/excel/disasters.xlsx?date_from=2025-01-01&date_to=2025-12-31"
```

CSV dicatat `EXPORT_CSV`, Excel `DOWNLOAD_XLSX` (ANALYST ke atas untuk observasi).

## 4. Alert dan kejadian

```bash
curl -s -H "Authorization: Bearer $ORBIT_U_TOKEN" "$ORBIT_U_URL/api/alerts?status=active"
curl -s -H "Authorization: Bearer $ORBIT_U_TOKEN" "$ORBIT_U_URL/api/alerts/evaluation?date_from=2024-01-01&date_to=2025-12-31"
curl -s -H "Authorization: Bearer $ORBIT_U_TOKEN" "$ORBIT_U_URL/api/disasters/57"     # + hujan H-0..H-2
```

Menandai alert dibaca dan mencatat kejadian adalah aksi tulis → hanya lewat web (ANALYST).

## 5. Dataset historis (DATA_ENGINEER)

```bash
curl -s -H "Authorization: Bearer $ORBIT_U_TOKEN" "$ORBIT_U_URL/api/datasets?limit=50"
curl -s -H "Authorization: Bearer $ORBIT_U_TOKEN" "$ORBIT_U_URL/api/datasets/12/status"
curl -s -H "Authorization: Bearer $ORBIT_U_TOKEN" "$ORBIT_U_URL/api/products?dataset_id=12&source=FUSION&tier=FUSED&limit=200"
```

Asal produk: `scene_id` (Sentinel-1), `nasa_scene_id` (granule MODIS/GPM), keduanya kosong untuk FUSION.

## 6. Unduh produk / fusion HDF5 (scope `READ_DOWNLOAD`)

```bash
curl -s -H "Authorization: Bearer $ORBIT_U_TOKEN" -OJ "$ORBIT_U_URL/api/products/88/download"
curl -s -H "Authorization: Bearer $ORBIT_U_TOKEN" -OJ "$ORBIT_U_URL/api/datasets/12/download"   # ZIP seluruh dataset
```

```python
from examples.client import OrbitUClient
import h5py

c = OrbitUClient(URL, os.environ["ORBIT_U_TOKEN"])
fused = next(c.paginate("/api/products", dataset_id=12, source="FUSION", tier="FUSED"))
path = c.download(f"/api/products/{fused['product_id']}/download", ".")
with h5py.File(path) as f:
    print(list(f.keys()))                       # lapisan per sumber (S1 VV/VH, MODIS, GPM)
    print(dict(f.attrs))                        # strategi fusi, tanggal, coverage_quality
```

Token ber-scope `READ` → 403 `TOKEN_SCOPE_FORBIDDEN`.

## 7. Telusuri lineage

```bash
curl -s -H "Authorization: Bearer $ORBIT_U_TOKEN" "$ORBIT_U_URL/api/metadata/lineage/88"
curl -s -H "Authorization: Bearer $ORBIT_U_TOKEN" "$ORBIT_U_URL/api/metadata/lineage/61?direction=descendants"
```

```python
for step in c.lineage(fused["product_id"]):
    print(step["source"], step["parent_tier"], "→", step["child_tier"], step["transformation_type"])
```

## 8. Penanganan error

| HTTP | `code` contoh | Tindakan skrip |
|---|---|---|
| 401 | `TOKEN_INVALID`, `TOKEN_REVOKED`, `TOKEN_EXPIRED` | Buat token baru |
| 403 | `ROLE_FORBIDDEN`, `DATE_OUT_OF_RANGE`, `TOKEN_SCOPE_FORBIDDEN`, `TOKEN_WRITE_FORBIDDEN`, `DB_PERMISSION_DENIED` | Periksa role/scope; jangan ulangi |
| 404 | `NOT_FOUND`, `FILE_MISSING` | Objek tidak ada (atau bukan untuk Anda) |
| 422 | `VALIDATION_ERROR` | Perbaiki parameter |
| 429 | `RATE_LIMITED` | Tunggu `Retry-After` detik |

Daftar lengkap kode: INTERFACE.md §5.
