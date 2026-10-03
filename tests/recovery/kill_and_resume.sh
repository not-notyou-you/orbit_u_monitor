#!/usr/bin/env bash
# tests/recovery/kill_and_resume.sh — uji pemulihan backfill hidromet (PIPELINE.md §8 "Pipeline mati di tengah").
#
#   bash tests/recovery/kill_and_resume.sh
#
# 1. Bangun ulang database UJI (*_test) + 3 kecamatan sintetis.
# 2. Jalankan backfill 10 tanggal (pengambil tiruan, ±1 detik per tanggal).
# 3. kill -9 di tengah jalan -> harus tersisa sebagian tanggal COMPLETED.
# 4. Jalankan perintah yang sama lagi -> semua tanggal COMPLETED, tanpa
#    baris dataset_jobs ganda, tanpa nilai salah, tanpa GeoTIFF separuh jadi.
# 5. Jalankan sekali lagi -> 0 tanggal dikerjakan (idempoten).
#
# Kunci advisory 'hydromet' milik proses yang dibunuh lepas sendiri karena
# koneksinya putus; proses kedua harus bisa langsung memperolehnya.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
if [ -x venv/Scripts/python.exe ]; then PY=venv/Scripts/python.exe; else PY=${PYTHON:-venv/bin/python}; fi
HELPER=tests/recovery/recovery_backfill.py
RANGE=(--from 2024-01-01 --to 2024-01-10)
LOG=tests/recovery/_work_run1.log

"$PY" "$HELPER" setup

echo "[1] backfill dimulai, akan dibunuh setelah 4 detik"
"$PY" "$HELPER" run "${RANGE[@]}" --delay 1.0 > "$LOG" 2>&1 &
PID=$!
sleep 4
if command -v taskkill >/dev/null 2>&1; then
    taskkill //F //PID "$(ps -p $PID -o winpid= 2>/dev/null || echo $PID)" >/dev/null 2>&1 || kill -9 $PID
else
    kill -9 $PID
fi
wait $PID 2>/dev/null || true
echo "[1] proses dibunuh; log:"; tail -n 5 "$LOG" || true

"$PY" "$HELPER" check "${RANGE[@]}" --expect-partial

echo "[2] perintah yang sama dijalankan ulang"
"$PY" "$HELPER" run "${RANGE[@]}" --delay 0.1 | tee tests/recovery/_work_run2.log
"$PY" "$HELPER" check "${RANGE[@]}"

echo "[3] dijalankan sekali lagi: tidak ada yang dikerjakan"
"$PY" "$HELPER" run "${RANGE[@]}" --delay 0.1 | tee tests/recovery/_work_run3.log
grep -q "0 to do" tests/recovery/_work_run3.log
echo "[OK] kill_and_resume lulus"
