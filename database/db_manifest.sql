-- database/db_manifest.sql — sidik jari isi database, untuk membuktikan dua
-- mesin punya database yang identik (DATABASE.md §10).
--
-- Kueri inventarisnya sama dengan tests/recovery/backup_restore.sh langkah 4,
-- tetapi dipisah sebagai berkas BACA-SAJA: skrip uji itu menghapus database
-- target, jadi sengaja menolak `themonitor`. Berkas ini tidak menulis apa pun,
-- jadi aman dijalankan pada produksi.
--
-- Pakai (sama persis di PowerShell maupun bash):
--     psql -U postgres -d themonitor -f database/db_manifest.sql > manifest.txt
--
-- Jalankan di laptop lama dan laptop baru, lalu bandingkan:
--     diff manifest_lama.txt manifest_baru.txt      # bash
--     Compare-Object (gc manifest_lama.txt) (gc manifest_baru.txt)   # PowerShell
--
-- Keluaran tidak mengandung data, hanya nama objek dan jumlah baris — aman
-- dikirim lewat chat atau dilampirkan ke laporan.

\pset format unaligned
\pset tuples_only on
\pset fieldsep '|'

SELECT 'objek|tabel|' || count(*) FROM pg_tables WHERE schemaname = 'public'
UNION ALL SELECT 'objek|view|' || count(*) FROM pg_views WHERE schemaname = 'public'
UNION ALL SELECT 'objek|fungsi|' || count(*) FROM pg_proc p
          JOIN pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname = 'public'
UNION ALL SELECT 'objek|trigger|' || count(*) FROM pg_trigger t
          JOIN pg_class c ON c.oid = t.tgrelid
          JOIN pg_namespace n ON n.oid = c.relnamespace
          WHERE n.nspname = 'public' AND NOT t.tgisinternal
UNION ALL SELECT 'objek|policy|' || count(*) FROM pg_policies WHERE schemaname = 'public'
UNION ALL SELECT 'objek|grant|' || count(*) FROM information_schema.role_table_grants
          WHERE table_schema = 'public' AND grantee LIKE 'monitor_%'
UNION ALL SELECT 'objek|ekstensi|' || string_agg(extname || ' ' || extversion, ', ' ORDER BY extname)
          FROM pg_extension WHERE extname <> 'plpgsql'
ORDER BY 1;

-- Satu baris "baris|<tabel>|<jumlah>" per tabel, urut nama tabel.
SELECT format('SELECT %L || count(*) FROM public.%I', 'baris|' || tablename || '|', tablename)
FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename
\gexec
