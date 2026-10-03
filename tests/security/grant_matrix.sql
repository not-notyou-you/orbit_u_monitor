-- =============================================================================
-- tests/security/grant_matrix.sql — uji matriks GRANT (DATABASE.md §8.3, RM4)
-- =============================================================================
-- Jalankan sebagai pemilik skema pada database yang sudah memuat ketiga
-- berkas skema:
--     psql -v ON_ERROR_STOP=1 -d themonitor_test -f tests/security/grant_matrix.sql
-- (tests/security/test_grant_matrix.py menjalankannya di setiap run pytest.)
--
-- Bagian 1 membandingkan privilege EFEKTIF (termasuk yang diwarisi lewat
-- hierarki role) setiap tabel/VIEW untuk setiap role dengan matriks harapan.
-- Objek baru yang belum dicantumkan di matriks juga dianggap gagal.
-- Bagian 2 mencoba operasi sungguhan dengan SET ROLE: GRANT kolom, RLS,
-- append-only, fungsi auth, dan monitor_app tanpa SET ROLE.
--
-- Semua dijalankan dalam satu transaksi yang di-ROLLBACK: tidak meninggalkan
-- data. Ketidakcocokan apa pun -> RAISE EXCEPTION (psql keluar non-nol).
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- Bagian 1 — matriks privilege tabel/VIEW
-- -----------------------------------------------------------------------------
-- Huruf: S = SELECT, I = INSERT, U = UPDATE, D = DELETE; '' = tidak ada.
-- Kolom = privilege efektif role tersebut (sama dengan kolom matriks §8.3).
CREATE TEMP TABLE gm_expected (
    obj  text PRIMARY KEY,
    pub  text NOT NULL,   -- monitor_public
    usr  text NOT NULL,   -- monitor_user
    ana  text NOT NULL,   -- monitor_analyst
    eng  text NOT NULL,   -- monitor_data_engineer
    adm  text NOT NULL,   -- monitor_admin
    etl  text NOT NULL    -- monitor_etl
) ON COMMIT DROP;

INSERT INTO gm_expected VALUES
--   objek                      pub  usr    ana    eng    adm     etl
    ('v_public_live_latest',     'S', 'S',   'S',   'S',   'S',    ''),
    -- live_areas: PUBLIC hanya GRANT kolom (diuji di bagian 2)
    ('live_areas',               '',  'S',   'S',   'S',   'SIU',  'SIU'),
    ('live_scenes',              '',  'S',   'S',   'S',   'SIU',  'SIU'),
    ('live_events',              '',  'S',   'S',   'S',   'SIU',  'SIU'),
    -- etl D: metrik scene ditulis ulang per finalisasi (Tahap 3, T3-27)
    ('live_scene_metrics',       '',  'S',   'S',   'S',   'SIU',  'SIUD'),
    ('v_live_scenes_recent',     '',  'S',   'S',   'S',   'S',    'S'),
    ('v_hujan_harian_kecamatan', '',  'S',   'S',   'S',   'S',    'S'),
    ('v_statistik_hari_ini',     '',  'S',   'S',   'S',   'S',    'S'),
    ('v_alert_aktif',            '',  'S',   'S',   'S',   'S',    'S'),
    -- master referensi
    ('satellite_sources',        '',  'S',   'S',   'S',   'S',    'S'),
    ('spectral_bands',           '',  'S',   'S',   'S',   'S',    'S'),
    ('processing_stages',        '',  'S',   'S',   'S',   'S',    'S'),
    ('fusion_strategies',        '',  'S',   'S',   'S',   'S',    'S'),
    ('report_types',             '',  'S',   'S',   'S',   'S',    'S'),
    ('administrative_regions',   '',  'S',   'S',   'S',   'SIU',  'S'),
    ('regions_of_interest',      '',  'S',   'S',   'S',   'SIU',  'S'),
    ('alert_rules',              '',  'S',   'S',   'S',   'SIU',  'S'),
    ('quality_thresholds',       '',  'S',   'S',   'S',   'SIU',  'S'),
    ('disaster_types',           '',  'S',   'S',   'S',   'SIU',  'S'),
    ('app_settings',             '',  'S',   'S',   'S',   'SIU',  'S'),
    -- alert & kejadian; U(ack) analyst = GRANT kolom (bagian 2)
    ('alert_events',             '',  'S',   'S',   'S',   'SIUD', 'SI'),
    -- etl S: job laporan Hidromet (Tahap 3)
    ('disaster_events',          '',  '',    'SIU', '',    'SIU',  'S'),
    ('v_kejadian_dan_hujan',     '',  '',    'S',   '',    'S',    'S'),
    ('v_evaluasi_alert',         '',  '',    'S',   '',    'S',    'S'),
    ('region_observations',      '',  'S',   'S',   'S',   'S',    'SIU'),
    -- katalog dataset; D etl = penghapusan fisik dataset (Tahap 2 S1)
    ('datasets',                 '',  '',    '',    'SIU', 'SIUD', 'SIUD'),
    ('dataset_source_config',    '',  '',    '',    'SIU', 'SIUD', 'SIU'),
    ('dataset_jobs',             '',  '',    '',    'SIU', 'SIUD', 'SIU'),
    ('scene_job_state',          '',  '',    '',    'SIU', 'SIUD', 'SIU'),
    ('satellite_scenes',         '',  '',    '',    'S',   'SU',   'SIU'),
    ('nasa_scenes',              '',  '',    '',    'S',   'SU',   'SIU'),
    ('data_products',            '',  '',    '',    'S',   'S',    'SIUD'),
    ('data_lineage',             '',  '',    '',    'S',   'S',    'SIU'),
    ('quality_metrics',          '',  '',    '',    'S',   'S',    'SIU'),
    ('quality_alerts',           '',  '',    '',    'S',   'S',    'SIU'),
    ('fusion_products',          '',  '',    '',    'S',   'S',    'SIU'),
    ('processing_jobs',          '',  '',    '',    'S',   'S',    'SIUD'),
    ('processing_logs',          '',  '',    '',    'S',   'S',    'SIU'),
    ('cleanup_operations',       '',  '',    '',    'S',   'S',    'SIU'),
    -- etl S: job laporan Kesehatan Data (Tahap 3)
    ('v_ringkasan_kualitas',     '',  '',    '',    'S',   'S',    'S'),
    ('v_kelengkapan_data',       '',  '',    '',    'S',   'S',    'S'),
    ('v_unduhan_per_role',       '',  '',    '',    'S',   'S',    'S'),
    -- laporan (+ RLS, bagian 2)
    ('generated_reports',        '',  '',    'S',   'S',   'SIU',  'SIU'),
    -- akun & log
    ('users',                    '',  '',    '',    '',    'SIU',  ''),
    ('roles',                    '',  '',    '',    '',    'SIU',  ''),
    ('v_users_safe',             '',  'S',   'S',   'S',   'S',    ''),
    ('api_tokens',               '',  'SIU', 'SIU', 'SIU', 'SIU',  ''),
    ('user_activity_logs',       'I', 'I',   'I',   'I',   'SI',   'I'),
    ('audit_log',                '',  '',    '',    '',    'S',    ''),
    ('v_log_login',              '',  '',    '',    '',    'S',    ''),
    ('v_log_unduhan',            '',  '',    '',    '',    'S',    '');

DO $$
DECLARE
    rec       record;
    rl        text;
    want      text;
    got       text;
    problems  text[] := '{}';
    roles     text[] := ARRAY['monitor_public', 'monitor_user', 'monitor_analyst',
                              'monitor_data_engineer', 'monitor_admin', 'monitor_etl'];
    checked   int := 0;
BEGIN
    -- Setiap tabel/VIEW skema public (selain katalog PostGIS) wajib ada di matriks.
    FOR rec IN
        SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind IN ('r', 'v', 'm', 'p')
          AND c.relname NOT IN ('spatial_ref_sys', 'geometry_columns', 'geography_columns')
          AND c.relname NOT IN (SELECT obj FROM gm_expected)
    LOOP
        problems := problems || format('%s: object missing from the expected matrix', rec.relname);
    END LOOP;

    FOR rec IN SELECT * FROM gm_expected ORDER BY obj LOOP
        FOR i IN 1 .. array_length(roles, 1) LOOP
            rl := roles[i];
            want := CASE i WHEN 1 THEN rec.pub WHEN 2 THEN rec.usr WHEN 3 THEN rec.ana
                           WHEN 4 THEN rec.eng WHEN 5 THEN rec.adm ELSE rec.etl END;
            got := concat(
                CASE WHEN has_table_privilege(rl, 'public.' || rec.obj, 'SELECT') THEN 'S' END,
                CASE WHEN has_table_privilege(rl, 'public.' || rec.obj, 'INSERT') THEN 'I' END,
                CASE WHEN has_table_privilege(rl, 'public.' || rec.obj, 'UPDATE') THEN 'U' END,
                CASE WHEN has_table_privilege(rl, 'public.' || rec.obj, 'DELETE') THEN 'D' END);
            IF got IS DISTINCT FROM want THEN
                problems := problems || format('%s / %s: expected "%s", got "%s"', rec.obj, rl, want, got);
            END IF;
            checked := checked + 1;
        END LOOP;

        -- monitor_app (NOINHERIT) tidak punya hak apa pun tanpa SET ROLE.
        IF has_table_privilege('monitor_app', 'public.' || rec.obj, 'SELECT')
           OR has_table_privilege('monitor_app', 'public.' || rec.obj, 'INSERT')
           OR has_table_privilege('monitor_app', 'public.' || rec.obj, 'UPDATE')
           OR has_table_privilege('monitor_app', 'public.' || rec.obj, 'DELETE') THEN
            problems := problems || format('%s / monitor_app: has privileges without SET ROLE', rec.obj);
        END IF;
        -- TRUNCATE tidak diberikan ke role aplikasi mana pun.
        FOREACH rl IN ARRAY roles LOOP
            IF has_table_privilege(rl, 'public.' || rec.obj, 'TRUNCATE') THEN
                problems := problems || format('%s / %s: TRUNCATE granted', rec.obj, rl);
            END IF;
        END LOOP;
    END LOOP;

    IF array_length(problems, 1) > 0 THEN
        RAISE EXCEPTION E'GRANT matrix mismatch (% problems):\n%',
            array_length(problems, 1), array_to_string(problems, E'\n');
    END IF;
    RAISE NOTICE 'Part 1 OK: % object x role cells match DATABASE.md §8.3', checked;
END $$;

-- -----------------------------------------------------------------------------
-- Bagian 2 — perilaku dengan SET ROLE sungguhan
-- -----------------------------------------------------------------------------
-- pg_temp.gm_try(role, user_id, sql): jalankan sql sebagai role dengan
-- app.user_id terisi. 'OK' bila berhasil, 'DENIED' bila insufficient_privilege
-- (GRANT) atau pelanggaran policy RLS. Perubahan SET LOCAL ikut dibatalkan
-- subtransaksi blok EXCEPTION.
CREATE FUNCTION pg_temp.gm_try(p_role text, p_uid int, p_sql text) RETURNS text
LANGUAGE plpgsql AS $$
BEGIN
    BEGIN
        PERFORM set_config('app.user_id', COALESCE(p_uid::text, ''), true);
        EXECUTE format('SET LOCAL ROLE %I', p_role);
        EXECUTE p_sql;
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'gm_rollback_ok';
    EXCEPTION
        WHEN insufficient_privilege THEN RETURN 'DENIED';
        WHEN raise_exception THEN
            IF SQLERRM = 'gm_rollback_ok' THEN RETURN 'OK'; END IF;
            RAISE;
    END;
END $$;

-- pg_temp.gm_count(role, user_id, sql): jumlah baris yang terlihat role.
CREATE FUNCTION pg_temp.gm_count(p_role text, p_uid int, p_sql text) RETURNS bigint
LANGUAGE plpgsql AS $$
DECLARE n bigint;
BEGIN
    PERFORM set_config('app.user_id', COALESCE(p_uid::text, ''), true);
    EXECUTE format('SET LOCAL ROLE %I', p_role);
    EXECUTE p_sql INTO n;
    RESET ROLE;
    PERFORM set_config('app.user_id', '', true);
    RETURN n;
END $$;

-- Data uji (sebagai pemilik; di-ROLLBACK di akhir).
INSERT INTO users (role_id, username, password_hash, full_name)
SELECT role_id, v.username, 'x', v.username
FROM (VALUES ('USER', 'gm_user'), ('USER', 'gm_user2'), ('ANALYST', 'gm_analyst')) v(code, username)
JOIN roles r ON r.role_code = v.code;

INSERT INTO api_tokens (user_id, token_name, token_prefix, token_hash, scopes, expires_at)
SELECT u.user_id, 'gm', 'trn_' || substr(md5(u.username), 1, 4), repeat('0', 64), 'READ', now() + INTERVAL '1 day'
FROM users u WHERE u.username IN ('gm_user', 'gm_user2');

INSERT INTO generated_reports (report_type_id, period_start, period_end, file_path,
                               file_size_bytes, checksum_sha256, status)
SELECT t.report_type_id, DATE '2020-01-06', DATE '2020-01-12', '/tmp/gm.pdf', 1, repeat('0', 64), 'READY'
FROM report_types t WHERE t.report_code IN ('HYDROMET_WEEKLY', 'DATAHEALTH_WEEKLY');

DO $$
DECLARE
    u1 int := (SELECT user_id FROM users WHERE username = 'gm_user');
    u2 int := (SELECT user_id FROM users WHERE username = 'gm_user2');
    problems text[] := '{}';
    rec record;
    got text;
    n bigint;
BEGIN
    -- (role, user_id, sql, harapan)
    FOR rec IN SELECT * FROM (VALUES
        -- GRANT kolom acknowledge: hanya tiga kolom ack.
        ('monitor_analyst', NULL::int, 'UPDATE alert_events SET ack_note = ''x'', acknowledged_by = NULL, acknowledged_at = NULL', 'OK'),
        ('monitor_analyst', NULL, 'UPDATE alert_events SET severity = ''INFO''', 'DENIED'),
        ('monitor_user',    NULL, 'UPDATE alert_events SET ack_note = ''x''', 'DENIED'),
        ('monitor_data_engineer', NULL, 'UPDATE alert_events SET ack_note = ''x''', 'DENIED'),
        -- Robustness INTERFACE §8: analyst mengubah password_hash lewat psql.
        ('monitor_analyst', NULL, 'UPDATE users SET password_hash = ''y''', 'DENIED'),
        ('monitor_analyst', NULL, 'SELECT password_hash FROM users', 'DENIED'),
        ('monitor_user',    NULL, 'SELECT count(*) FROM v_users_safe', 'OK'),
        -- Hapus fisik: tidak untuk role non-admin; users tanpa D sama sekali.
        ('monitor_admin',   NULL, 'DELETE FROM users WHERE false', 'DENIED'),
        ('monitor_data_engineer', NULL, 'DELETE FROM datasets WHERE false', 'DENIED'),
        ('monitor_analyst', NULL, 'DELETE FROM disaster_events WHERE false', 'DENIED'),
        -- PUBLIC: kolom publik live_areas saja.
        ('monitor_public',  NULL, 'SELECT area_id, name, status FROM live_areas', 'OK'),
        ('monitor_public',  NULL, 'SELECT bbox_wkt FROM live_areas', 'DENIED'),
        ('monitor_public',  NULL, 'SELECT * FROM v_public_live_latest', 'OK'),
        ('monitor_public',  NULL, 'SELECT * FROM v_live_scenes_recent', 'DENIED'),
        -- Append-only: tidak ada UPDATE/DELETE, audit_log tidak bisa ditulis.
        ('monitor_admin',   NULL, 'UPDATE user_activity_logs SET action = ''X''', 'DENIED'),
        ('monitor_admin',   NULL, 'DELETE FROM user_activity_logs WHERE false', 'DENIED'),
        ('monitor_admin',   NULL, 'INSERT INTO audit_log (table_name, row_pk, operation) VALUES (''x'', ''1'', ''I'')', 'DENIED'),
        ('monitor_admin',   NULL, 'UPDATE audit_log SET row_pk = ''0''', 'DENIED'),
        ('monitor_etl',     NULL, 'DELETE FROM audit_log WHERE false', 'DENIED'),
        ('monitor_public',  NULL, 'INSERT INTO user_activity_logs (action) VALUES (''LOGIN_FAILED'')', 'OK'),
        ('monitor_public',  NULL, 'SELECT count(*) FROM user_activity_logs', 'DENIED'),
        -- Fungsi auth: PUBLIC boleh memanggil, tapi tidak membaca users langsung.
        ('monitor_public',  NULL, 'SELECT * FROM auth_get_user(''gm_user'')', 'OK'),
        ('monitor_public',  NULL, 'SELECT * FROM users', 'DENIED'),
        ('monitor_etl',     NULL, 'SELECT * FROM auth_get_user(''gm_user'')', 'DENIED'),
        -- RLS api_tokens: tidak bisa membuat token atas nama orang lain.
        ('monitor_user', u1, format('INSERT INTO api_tokens (user_id, token_name, token_prefix, token_hash, scopes, expires_at) VALUES (%s, ''x'', ''trn_gm01'', repeat(''0'', 64), ''READ'', now() + interval ''1 day'')', u1), 'OK'),
        ('monitor_user', u1, format('INSERT INTO api_tokens (user_id, token_name, token_prefix, token_hash, scopes, expires_at) VALUES (%s, ''x'', ''trn_gm02'', repeat(''0'', 64), ''READ'', now() + interval ''1 day'')', u2), 'DENIED'),
        -- RLS generated_reports: penulis hanya etl/admin.
        ('monitor_etl',   NULL, 'UPDATE generated_reports SET status = ''SUPERSEDED''', 'OK'),
        ('monitor_analyst', NULL, 'UPDATE generated_reports SET status = ''SUPERSEDED''', 'DENIED')
    ) v(role, uid, sql, expect) LOOP
        BEGIN
            got := pg_temp.gm_try(rec.role, rec.uid, rec.sql);
        EXCEPTION WHEN check_violation OR insufficient_privilege THEN
            got := 'DENIED';
        END;
        -- Pelanggaran WITH CHECK RLS dilaporkan sebagai insufficient_privilege (42501).
        IF got <> rec.expect THEN
            problems := problems || format('%s: %s -> expected %s, got %s', rec.role, rec.sql, rec.expect, got);
        END IF;
    END LOOP;

    -- RLS api_tokens: pengguna hanya melihat tokennya sendiri; ADMIN semua.
    n := pg_temp.gm_count('monitor_user', u1, 'SELECT count(*) FROM api_tokens WHERE token_name = ''gm''');
    IF n <> 1 THEN problems := problems || format('api_tokens RLS: user sees %s rows, expected 1', n); END IF;
    n := pg_temp.gm_count('monitor_user', NULL, 'SELECT count(*) FROM api_tokens WHERE token_name = ''gm''');
    IF n <> 0 THEN problems := problems || format('api_tokens RLS: user without app.user_id sees %s rows', n); END IF;
    n := pg_temp.gm_count('monitor_admin', NULL, 'SELECT count(*) FROM api_tokens WHERE token_name = ''gm''');
    IF n <> 2 THEN problems := problems || format('api_tokens RLS: admin sees %s rows, expected 2', n); END IF;
    n := pg_temp.gm_count('monitor_user', u1, format('UPDATE api_tokens SET revoked_at = now() WHERE user_id = %s RETURNING 1', u2));
    IF n IS NOT NULL THEN problems := problems || 'api_tokens RLS: user revoked another user''s token'; END IF;

    -- RLS generated_reports: audiens.
    n := pg_temp.gm_count('monitor_analyst', NULL, 'SELECT count(*) FROM generated_reports g JOIN report_types t USING (report_type_id) WHERE t.report_code LIKE ''HYDROMET%''');
    IF n <> 1 THEN problems := problems || format('reports RLS: analyst sees %s hydromet rows, expected 1', n); END IF;
    n := pg_temp.gm_count('monitor_analyst', NULL, 'SELECT count(*) FROM generated_reports g JOIN report_types t USING (report_type_id) WHERE t.report_code LIKE ''DATAHEALTH%''');
    IF n <> 0 THEN problems := problems || format('reports RLS: analyst sees %s data-health rows, expected 0', n); END IF;
    n := pg_temp.gm_count('monitor_data_engineer', NULL, 'SELECT count(*) FROM generated_reports g JOIN report_types t USING (report_type_id) WHERE t.report_code LIKE ''HYDROMET%''');
    IF n <> 0 THEN problems := problems || format('reports RLS: data engineer sees %s hydromet rows, expected 0', n); END IF;
    n := pg_temp.gm_count('monitor_data_engineer', NULL, 'SELECT count(*) FROM generated_reports g JOIN report_types t USING (report_type_id) WHERE t.report_code LIKE ''DATAHEALTH%''');
    IF n <> 1 THEN problems := problems || format('reports RLS: data engineer sees %s data-health rows, expected 1', n); END IF;
    n := pg_temp.gm_count('monitor_admin', NULL, 'SELECT count(*) FROM generated_reports WHERE file_path = ''/tmp/gm.pdf''');
    IF n <> 2 THEN problems := problems || format('reports RLS: admin sees %s rows, expected 2', n); END IF;

    IF array_length(problems, 1) > 0 THEN
        RAISE EXCEPTION E'Behavioural security checks failed (% problems):\n%',
            array_length(problems, 1), array_to_string(problems, E'\n');
    END IF;
    RAISE NOTICE 'Part 2 OK: column grants, RLS, append-only, auth functions';
END $$;

-- monitor_app tanpa SET ROLE: tidak bisa membaca apa pun (bahkan tidak punya
-- USAGE skema, jadi tabel tampak tidak ada); dengan SET ROLE bisa.
SET SESSION AUTHORIZATION monitor_app;
DO $$
DECLARE denied boolean := false;
BEGIN
    BEGIN
        PERFORM 1 FROM alert_rules LIMIT 1;
    EXCEPTION WHEN insufficient_privilege OR undefined_table THEN denied := true;
    END;
    IF NOT denied THEN
        RAISE EXCEPTION 'monitor_app can read alert_rules without SET ROLE';
    END IF;
    SET LOCAL ROLE monitor_user;
    PERFORM 1 FROM alert_rules LIMIT 1;
    RESET ROLE;
    RAISE NOTICE 'Part 3 OK: monitor_app has no privileges without SET ROLE';
END $$;
RESET SESSION AUTHORIZATION;

ROLLBACK;
