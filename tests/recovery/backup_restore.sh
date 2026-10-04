#!/usr/bin/env bash
# tests/recovery/backup_restore.sh — uji recoverability "restore pg_dump ke DB kosong"
# (INTERFACE.md §8, PIPELINE.md §13).
#
#   SRC_DB=themonitor_dev bash tests/recovery/backup_restore.sh
#
# 1. pg_dump -Fc dari DB sumber (default themonitor_dev; baca saja).
# 2. DB target kosong (default themonitor_restore_test) dibuat ulang.
# 3. pg_restore ke target.
# 4. Bandingkan jumlah baris setiap tabel public, jumlah objek (tabel, VIEW,
#    fungsi, trigger, policy RLS) dan GRANT ke role monitor_*.
# 5. Target dihapus lagi (KEEP=1 untuk mempertahankannya).
#
# PENGAMAN: skrip menolak berjalan bila sumber ATAU target adalah DB produksi
# `themonitor` — backup produksi bukan tugas skrip uji ini.
#
# Koneksi memakai PGHOST/PGPORT/PGUSER/PGPASSWORD (atau DB_HOST/DB_PORT/DB_USER/
# DB_PASSWORD dari .env bila PG* kosong). Role monitor_* bersifat cluster-wide,
# jadi GRANT ikut ter-restore apa adanya.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
if [ -f .env ]; then
    eval "$(grep -E '^(DB_HOST|DB_PORT|DB_USER|DB_PASSWORD)=' .env | sed 's/\r$//; s/^/export /')"
fi
export PGHOST="${PGHOST:-${DB_HOST:-localhost}}" PGPORT="${PGPORT:-${DB_PORT:-5432}}"
export PGUSER="${PGUSER:-${DB_USER:-postgres}}" PGPASSWORD="${PGPASSWORD:-${DB_PASSWORD:-}}"

SRC_DB="${SRC_DB:-themonitor_dev}"
TARGET_DB="${TARGET_DB:-themonitor_restore_test}"
for db in "$SRC_DB" "$TARGET_DB"; do
    if [ "$db" = "themonitor" ]; then
        echo "DITOLAK: '$db' adalah DB produksi. Gunakan themonitor_dev/themonitor_test." >&2
        exit 2
    fi
done
if [ "$SRC_DB" = "$TARGET_DB" ]; then echo "DITOLAK: sumber dan target sama." >&2; exit 2; fi

WORK="${TMPDIR:-${TEMP:-/tmp}}/orbit_u_backup_restore_$$"
mkdir -p "$WORK"
DUMP="$WORK/$SRC_DB.dump"
trap 'rm -rf "$WORK"' EXIT

# Kueri inventaris: satu baris "jenis|nama|nilai" per objek, diurutkan agar bisa di-diff.
INVENTORY_SQL=$(cat <<'SQL'
SELECT 'objek|tabel|' || count(*) FROM pg_tables WHERE schemaname = 'public'
UNION ALL SELECT 'objek|view|' || count(*) FROM pg_views WHERE schemaname = 'public'
UNION ALL SELECT 'objek|fungsi|' || count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname = 'public'
UNION ALL SELECT 'objek|trigger|' || count(*) FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid
          JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public' AND NOT t.tgisinternal
UNION ALL SELECT 'objek|policy|' || count(*) FROM pg_policies WHERE schemaname = 'public'
UNION ALL SELECT 'objek|grant|' || count(*) FROM information_schema.role_table_grants
          WHERE table_schema = 'public' AND grantee LIKE 'monitor_%'
ORDER BY 1;
SQL
)
ROWCOUNT_SQL=$(cat <<'SQL'
SELECT format('SELECT %L || count(*) FROM public.%I', 'baris|' || tablename || '|', tablename)
FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename
\gexec
SQL
)

inventory() {  # $1 = db
    { psql -X -q -At -v ON_ERROR_STOP=1 -d "$1" -c "$INVENTORY_SQL"
      printf '%s\n' "$ROWCOUNT_SQL" | psql -X -q -At -v ON_ERROR_STOP=1 -d "$1"; } | sed 's/\r$//' | sort
}

echo "[1] pg_dump $SRC_DB"
t0=$(date +%s)
pg_dump -Fc -d "$SRC_DB" -f "$DUMP"
echo "    ukuran dump: $(du -h "$DUMP" | cut -f1), $(( $(date +%s) - t0 )) s"

echo "[2] DB kosong $TARGET_DB"
dropdb --if-exists "$TARGET_DB"
createdb "$TARGET_DB"

echo "[3] pg_restore"
t1=$(date +%s)
pg_restore -d "$TARGET_DB" --exit-on-error "$DUMP"
echo "    restore selesai dalam $(( $(date +%s) - t1 )) s"

echo "[4] bandingkan isi"
inventory "$SRC_DB" > "$WORK/src.txt"
inventory "$TARGET_DB" > "$WORK/dst.txt"
if diff -u "$WORK/src.txt" "$WORK/dst.txt" > "$WORK/diff.txt"; then
    TABLES=$(grep -c '^baris|' "$WORK/src.txt")
    ROWS=$(grep '^baris|' "$WORK/src.txt" | awk -F'|' '{s += $3} END {print s}')
    grep '^objek|' "$WORK/src.txt" | sed 's/^objek|/    /; s/|/ = /'
    echo "    $TABLES tabel, $ROWS baris — identik dengan sumber"
    RESULT=PASS
else
    echo "    PERBEDAAN:"; sed 's/^/    /' "$WORK/diff.txt"
    RESULT=FAIL
fi

if [ "${KEEP:-0}" != "1" ]; then dropdb "$TARGET_DB"; echo "[5] $TARGET_DB dihapus"; fi
echo "HASIL: $RESULT"
[ "$RESULT" = PASS ]
