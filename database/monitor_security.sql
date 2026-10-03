-- =============================================================================
-- database/monitor_security.sql — Orbit-U: The Monitor
-- =============================================================================
-- Keamanan fisik basis data (DATABASE.md §8, RM4). Dijalankan setelah
-- monitor_schema.sql dan sebelum monitor_seed.sql, oleh pemilik skema.
--
--   §8.1  Role PostgreSQL + hierarki
--   §8.2  Fungsi SECURITY DEFINER untuk autentikasi
--   §8.3  Matriks GRANT
--   §8.4  Row-Level Security (generated_reports, api_tokens)
--   §8.5  Audit trigger
--
-- Role bersifat global untuk seluruh cluster, sedangkan tabel milik satu
-- database. Karena itu bagian role ditulis idempoten (database uji dibangun
-- ulang berkali-kali di cluster yang sama), sedangkan sisanya mengasumsikan
-- skema baru saja dibuat.
--
-- Sandi role LOGIN TIDAK ditulis di sini (IMPLEMENTATION_NOTES Tahap 2, S3).
-- database/apply_schema.py mengisinya dari .env (MONITOR_APP_PASSWORD,
-- MONITOR_ETL_PASSWORD). Lewat psql, setelah berkas ini:
--     ALTER ROLE monitor_app PASSWORD '...';
--     ALTER ROLE monitor_etl PASSWORD '...';
-- =============================================================================

-- =============================================================================
-- §8.1 ROLE
-- =============================================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'monitor_public') THEN
        CREATE ROLE monitor_public NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'monitor_user') THEN
        CREATE ROLE monitor_user NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'monitor_analyst') THEN
        CREATE ROLE monitor_analyst NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'monitor_data_engineer') THEN
        CREATE ROLE monitor_data_engineer NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'monitor_admin') THEN
        CREATE ROLE monitor_admin NOLOGIN;
    END IF;
    -- Dipakai FastAPI. NOINHERIT: tanpa SET ROLE tidak punya hak apa pun.
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'monitor_app') THEN
        CREATE ROLE monitor_app LOGIN NOINHERIT;
    END IF;
    -- Dipakai scheduler/pipeline.
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'monitor_etl') THEN
        CREATE ROLE monitor_etl LOGIN;
    END IF;
END $$;

-- Atribut ditegakkan ulang walau role sudah ada dari build sebelumnya.
ALTER ROLE monitor_public        NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT;
ALTER ROLE monitor_user          NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT;
ALTER ROLE monitor_analyst       NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT;
ALTER ROLE monitor_data_engineer NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT;
ALTER ROLE monitor_admin         NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT;
ALTER ROLE monitor_app           LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
ALTER ROLE monitor_etl           LOGIN INHERIT   NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;

-- Hierarki: ADMIN ⊃ ANALYST ⊃ USER ⊃ PUBLIC, ADMIN ⊃ DATA_ENGINEER ⊃ USER.
GRANT monitor_public  TO monitor_user;
GRANT monitor_user    TO monitor_analyst;
GRANT monitor_user    TO monitor_data_engineer;
GRANT monitor_analyst, monitor_data_engineer TO monitor_admin;

-- monitor_app hanya boleh SET ROLE ke kelima role aplikasi.
GRANT monitor_public, monitor_user, monitor_analyst,
      monitor_data_engineer, monitor_admin TO monitor_app;

REVOKE ALL ON ALL TABLES    IN SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
-- USAGE skema diberikan eksplisit, tidak mengandalkan default PUBLIC (skema
-- yang dibuat ulang dengan CREATE SCHEMA tidak membawanya).
GRANT USAGE ON SCHEMA public TO monitor_public, monitor_etl;
-- Tabel katalog PostGIS: dibaca ST_Transform/ST_SRID oleh role mana pun.
GRANT SELECT ON spatial_ref_sys TO PUBLIC;

-- =============================================================================
-- §8.3 MATRIKS GRANT
-- =============================================================================
-- Hak diberikan pada role paling rendah yang membutuhkannya; role di atasnya
-- mewarisi lewat hierarki. Kolom komentar = sel matriks DATABASE.md §8.3.

-- PUBLIC ----------------------------------------------------------------------
GRANT SELECT ON v_public_live_latest TO monitor_public;
GRANT SELECT (area_id, name, location_label, status, enabled, last_checked_at, deleted_at)
    ON live_areas TO monitor_public;                                   -- kolom publik
GRANT INSERT ON user_activity_logs TO monitor_public;                  -- I (login gagal, dsb.)

-- USER (dan semua role login di atasnya) --------------------------------------
GRANT SELECT ON v_live_scenes_recent, v_hujan_harian_kecamatan,
                v_statistik_hari_ini, v_alert_aktif, v_users_safe TO monitor_user;
-- Master referensi.
GRANT SELECT ON satellite_sources, spectral_bands, administrative_regions,
                regions_of_interest, processing_stages, fusion_strategies,
                report_types, alert_rules, quality_thresholds, disaster_types,
                app_settings TO monitor_user;
GRANT SELECT ON alert_events, region_observations TO monitor_user;
GRANT SELECT ON live_areas, live_scenes, live_events, live_scene_metrics TO monitor_user;
GRANT SELECT, INSERT, UPDATE ON api_tokens TO monitor_user;           -- milik sendiri (RLS)

-- ANALYST ---------------------------------------------------------------------
GRANT UPDATE (acknowledged_by, acknowledged_at, ack_note) ON alert_events TO monitor_analyst;
GRANT SELECT, INSERT, UPDATE ON disaster_events TO monitor_analyst;
GRANT SELECT ON v_kejadian_dan_hujan, v_evaluasi_alert TO monitor_analyst;
GRANT SELECT ON generated_reports TO monitor_analyst;                  -- + RLS

-- DATA_ENGINEER ---------------------------------------------------------------
GRANT SELECT, INSERT, UPDATE ON datasets, dataset_source_config, dataset_jobs,
                                scene_job_state TO monitor_data_engineer;
GRANT SELECT ON satellite_scenes, nasa_scenes TO monitor_data_engineer;
GRANT SELECT ON data_products, data_lineage, quality_metrics, quality_alerts,
                fusion_products, processing_jobs, processing_logs,
                cleanup_operations TO monitor_data_engineer;
GRANT SELECT ON v_ringkasan_kualitas, v_kelengkapan_data TO monitor_data_engineer;
GRANT SELECT ON generated_reports TO monitor_data_engineer;            -- + RLS

-- ADMIN (mewarisi ANALYST + DATA_ENGINEER) ------------------------------------
GRANT SELECT, INSERT, UPDATE, DELETE ON alert_events TO monitor_admin;
GRANT DELETE ON datasets, dataset_source_config, dataset_jobs, scene_job_state TO monitor_admin;
GRANT UPDATE ON satellite_scenes, nasa_scenes TO monitor_admin;         -- soft delete
GRANT SELECT, INSERT, UPDATE ON generated_reports TO monitor_admin;
GRANT SELECT, INSERT, UPDATE ON users, roles TO monitor_admin;          -- tanpa D
GRANT SELECT, INSERT, UPDATE ON alert_rules, quality_thresholds, disaster_types,
                                app_settings, administrative_regions,
                                regions_of_interest TO monitor_admin;
GRANT SELECT, INSERT, UPDATE ON live_areas, live_scenes, live_events,
                                live_scene_metrics TO monitor_admin;
GRANT SELECT ON user_activity_logs, audit_log, v_log_login, v_log_unduhan TO monitor_admin;

-- ETL (scheduler/pipeline) ----------------------------------------------------
GRANT SELECT ON satellite_sources, spectral_bands, administrative_regions,
                regions_of_interest, processing_stages, fusion_strategies,
                report_types, alert_rules, quality_thresholds, disaster_types,
                app_settings, v_live_scenes_recent, v_hujan_harian_kecamatan,
                v_statistik_hari_ini, v_alert_aktif TO monitor_etl;
GRANT SELECT, INSERT ON alert_events TO monitor_etl;
GRANT SELECT, INSERT, UPDATE ON region_observations TO monitor_etl;
GRANT SELECT, INSERT, UPDATE ON datasets, dataset_source_config, dataset_jobs,
                                scene_job_state TO monitor_etl;
GRANT SELECT, INSERT, UPDATE ON satellite_scenes, nasa_scenes TO monitor_etl;
GRANT SELECT, INSERT, UPDATE ON data_products, data_lineage, quality_metrics,
                                quality_alerts, fusion_products, processing_jobs,
                                processing_logs, cleanup_operations TO monitor_etl;
-- S1: penghapusan fisik dataset (diputuskan API untuk pembuat/ADMIN)
-- dikerjakan pipeline. Tabel anak lain ikut lewat ON DELETE CASCADE.
GRANT DELETE ON datasets, data_products, processing_jobs TO monitor_etl;
GRANT SELECT, INSERT, UPDATE ON generated_reports TO monitor_etl;
GRANT SELECT, INSERT, UPDATE ON live_areas, live_scenes, live_events,
                                live_scene_metrics TO monitor_etl;
GRANT INSERT ON user_activity_logs TO monitor_etl;

-- Sequence: nextval untuk tabel yang boleh di-INSERT. USAGE saja tidak
-- memberi hak menulis tabel mana pun.
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO monitor_public, monitor_etl;

-- =============================================================================
-- §8.4 ROW-LEVEL SECURITY
-- =============================================================================
-- Ekspresi policy dievaluasi dengan hak role pemanggil, sedangkan roles hanya
-- boleh dibaca ADMIN (§8.3). Nama role DB audiens karena itu diambil lewat
-- fungsi SECURITY DEFINER kecil, bukan subkueri langsung seperti di
-- DATABASE.md §8.4 (IMPLEMENTATION_NOTES Tahap 2, T1).
CREATE FUNCTION report_audience_db_role(p_report_type_id smallint) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
    SELECT r.db_role FROM report_types t JOIN roles r ON r.role_id = t.audience_role_id
    WHERE t.report_type_id = p_report_type_id;
$$;
COMMENT ON FUNCTION report_audience_db_role(smallint) IS 'RLS generated_reports: nama role PostgreSQL audiens sebuah jenis laporan (report_types.audience_role_id -> roles.db_role).';
ALTER FUNCTION report_audience_db_role(smallint) OWNER TO monitor_admin;
REVOKE ALL ON FUNCTION report_audience_db_role(smallint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION report_audience_db_role(smallint) TO monitor_public, monitor_etl;

ALTER TABLE generated_reports ENABLE ROW LEVEL SECURITY;
-- Pembaca: hanya audiens laporan (ADMIN anggota kedua audiens).
CREATE POLICY rp_audience ON generated_reports FOR SELECT
  USING (pg_has_role(current_user, report_audience_db_role(report_type_id), 'MEMBER'));
-- Penulis: scheduler dan ADMIN (regenerasi). Tanpa policy ini RLS menolak
-- INSERT/UPDATE untuk semua role selain pemilik.
CREATE POLICY rp_writers ON generated_reports FOR ALL TO monitor_admin, monitor_etl
  USING (true) WITH CHECK (true);

ALTER TABLE api_tokens ENABLE ROW LEVEL SECURITY;
CREATE POLICY tok_owner ON api_tokens
  USING (user_id = NULLIF(current_setting('app.user_id', true), '')::int
         OR pg_has_role(current_user, 'monitor_admin', 'MEMBER'));

-- =============================================================================
-- §8.2 FUNGSI AUTENTIKASI (SECURITY DEFINER, milik monitor_admin)
-- =============================================================================
-- Login dan pemeriksaan sesi berjalan sebelum role pengguna diketahui, yaitu
-- sebagai monitor_public yang tidak punya hak atas users/api_tokens. Fungsi
-- di bawah adalah satu-satunya jalan itu, masing-masing mengembalikan
-- sekecil mungkin (S2).

-- Dipakai login: hash + status kunci.
CREATE FUNCTION auth_get_user(p_username text)
RETURNS TABLE (user_id int, username varchar, password_hash varchar, full_name varchar,
               role_code varchar, db_role varchar, is_active boolean,
               failed_login_count smallint, locked_until timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
    SELECT u.user_id, u.username, u.password_hash, u.full_name,
           r.role_code, r.db_role, u.is_active, u.failed_login_count, u.locked_until
    FROM users u JOIN roles r ON r.role_id = u.role_id
    WHERE u.username = lower(p_username);
$$;
COMMENT ON FUNCTION auth_get_user(text) IS 'Login: mengambil hash bcrypt dan status akun. SECURITY DEFINER milik monitor_admin; satu-satunya jalan role non-admin membaca password_hash (DATABASE.md §8.2).';

-- Dipakai login: catat hasil verifikasi. 5 kali gagal beruntun -> kunci 15 menit.
CREATE FUNCTION auth_record_login(p_user_id int, p_success boolean)
RETURNS TABLE (failed_login_count smallint, locked_until timestamptz)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
    IF p_success THEN
        UPDATE users u SET failed_login_count = 0,
                           locked_until = NULL,
                           last_login_at = now()
        WHERE u.user_id = p_user_id;
    ELSE
        UPDATE users u
        SET failed_login_count = CASE WHEN u.failed_login_count + 1 >= 5 THEN 0
                                      ELSE u.failed_login_count + 1 END,
            locked_until       = CASE WHEN u.failed_login_count + 1 >= 5
                                      THEN now() + INTERVAL '15 minutes'
                                      ELSE u.locked_until END
        WHERE u.user_id = p_user_id;
    END IF;
    RETURN QUERY SELECT u.failed_login_count, u.locked_until FROM users u WHERE u.user_id = p_user_id;
END $$;
COMMENT ON FUNCTION auth_record_login(int, boolean) IS 'Login: sukses -> reset penghitung + last_login_at; gagal -> penghitung +1, kelima kalinya locked_until = now()+15 menit (DATABASE.md §8.6).';

-- Dipakai setiap request: role dan status terkini pemilik sesi/token.
CREATE FUNCTION auth_session_user(p_user_id int)
RETURNS TABLE (user_id int, username varchar, full_name varchar, organization varchar,
               role_code varchar, db_role varchar, is_active boolean)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
    SELECT u.user_id, u.username, u.full_name, u.organization,
           r.role_code, r.db_role, u.is_active
    FROM users u JOIN roles r ON r.role_id = u.role_id
    WHERE u.user_id = p_user_id;
$$;
COMMENT ON FUNCTION auth_session_user(int) IS 'Setiap request: membaca ulang role dan is_active pengguna (tanpa hash) sehingga perubahan role/nonaktif berlaku di request berikutnya (INTERFACE.md §6).';

-- Dipakai autentikasi Bearer: cari token dari prefix (RLS api_tokens menolak
-- pencarian sebelum pemilik diketahui).
CREATE FUNCTION auth_get_token(p_prefix text)
RETURNS TABLE (token_id int, user_id int, token_hash char(64), scopes varchar,
               expires_at timestamptz, revoked_at timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
    SELECT t.token_id, t.user_id, t.token_hash, t.scopes, t.expires_at, t.revoked_at
    FROM api_tokens t
    WHERE t.token_prefix = p_prefix;
$$;
COMMENT ON FUNCTION auth_get_token(text) IS 'Autentikasi Bearer: mengambil hash token dari prefix untuk dibandingkan constant-time di aplikasi (INTERFACE.md §6).';

-- Dipakai "ubah kata sandi": USER tidak punya UPDATE pada users (§8.3), jadi
-- pengguna mengganti hash miliknya sendiri lewat fungsi ini. Baris yang
-- diubah ditentukan app.user_id sesi, bukan argumen (Tahap 2, T2).
CREATE FUNCTION auth_change_own_password(p_new_hash text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE uid int := NULLIF(current_setting('app.user_id', true), '')::int;
BEGIN
    IF uid IS NULL THEN
        RAISE EXCEPTION 'app.user_id is not set' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF p_new_hash !~ '^\$2[aby]\$\d\d\$.{53}$' THEN
        RAISE EXCEPTION 'password hash must be bcrypt' USING ERRCODE = 'check_violation';
    END IF;
    UPDATE users SET password_hash = p_new_hash WHERE user_id = uid AND is_active;
    RETURN FOUND;
END $$;
COMMENT ON FUNCTION auth_change_own_password(text) IS 'Ubah kata sandi sendiri: mengganti password_hash baris users milik app.user_id sesi (hash bcrypt dihitung aplikasi).';

ALTER FUNCTION auth_get_user(text)              OWNER TO monitor_admin;
ALTER FUNCTION auth_record_login(int, boolean)  OWNER TO monitor_admin;
ALTER FUNCTION auth_session_user(int)           OWNER TO monitor_admin;
ALTER FUNCTION auth_get_token(text)             OWNER TO monitor_admin;
ALTER FUNCTION auth_change_own_password(text)   OWNER TO monitor_admin;
REVOKE ALL ON FUNCTION auth_get_user(text), auth_record_login(int, boolean),
                       auth_session_user(int), auth_get_token(text),
                       auth_change_own_password(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION auth_get_user(text), auth_record_login(int, boolean),
                          auth_session_user(int), auth_get_token(text) TO monitor_public;
GRANT EXECUTE ON FUNCTION auth_change_own_password(text) TO monitor_user;

-- =============================================================================
-- §8.5 AUDIT TRIGGER
-- =============================================================================
-- TG_ARGV[0] = kolom PK. TG_ARGV[1..] = kolom "pembukuan" yang perubahannya
-- saja tidak dicatat (mis. last_used_at token yang berubah setiap request,
-- penghitung progres dataset). updated_at selalu termasuk.
--
-- Fungsi SECURITY DEFINER (milik pemilik skema) agar bisa mengisi audit_log
-- yang tidak boleh ditulis role mana pun. Karena di dalamnya current_user =
-- pemilik fungsi, db_user diambil dari GUC "role" (hasil SET ROLE), atau
-- session_user bila tidak ada SET ROLE (psql langsung).
CREATE FUNCTION audit_row() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
    o_full  jsonb;
    n_full  jsonb;
    changed text[];
    ignored text[] := ARRAY['updated_at'];
    pk      text;
    actor   text;
BEGIN
    IF TG_OP <> 'INSERT' THEN o_full := to_jsonb(OLD); END IF;
    IF TG_OP <> 'DELETE' THEN n_full := to_jsonb(NEW); END IF;

    IF TG_OP = 'UPDATE' THEN
        -- Dihitung dari baris utuh, sebelum sensor: perubahan password_hash
        -- tetap terlihat di changed_columns walau nilainya tidak disimpan.
        -- updated_at (diisi trigger) tidak ikut dicantumkan.
        changed := ARRAY(SELECT k FROM jsonb_each(n_full) e(k, v)
                         WHERE v IS DISTINCT FROM o_full -> k AND k <> 'updated_at');
        IF TG_NARGS > 1 THEN
            ignored := ignored || TG_ARGV[1:TG_NARGS - 1];
        END IF;
        IF changed <@ ignored THEN
            RETURN NULL;
        END IF;
    END IF;

    pk := COALESCE(n_full, o_full) ->> TG_ARGV[0];
    actor := NULLIF(current_setting('role'), 'none');

    INSERT INTO audit_log (table_name, row_pk, operation, old_data, new_data,
                           changed_columns, app_user_id, db_user)
    VALUES (TG_TABLE_NAME, pk, left(TG_OP, 1),
            o_full - 'password_hash' - 'token_hash' - 'geom',
            n_full - 'password_hash' - 'token_hash' - 'geom',
            changed,
            NULLIF(current_setting('app.user_id', true), '')::int,
            COALESCE(actor, session_user));
    RETURN NULL;
END $$;
COMMENT ON FUNCTION audit_row() IS 'Trigger AFTER I/U/D: menulis audit_log (JSONB lama/baru, password_hash/token_hash/geom disensor, kolom berubah, app.user_id, role DB). TG_ARGV[0] = kolom PK; TG_ARGV[1..] = kolom pembukuan yang diabaikan bila hanya itu yang berubah (DATABASE.md §8.5).';
REVOKE ALL ON FUNCTION audit_row() FROM PUBLIC;

CREATE TRIGGER trg_audit_users AFTER INSERT OR UPDATE OR DELETE ON users
    FOR EACH ROW EXECUTE FUNCTION audit_row('user_id', 'last_login_at', 'failed_login_count');
CREATE TRIGGER trg_audit_api_tokens AFTER INSERT OR UPDATE OR DELETE ON api_tokens
    FOR EACH ROW EXECUTE FUNCTION audit_row('token_id', 'last_used_at');
CREATE TRIGGER trg_audit_alert_rules AFTER INSERT OR UPDATE OR DELETE ON alert_rules
    FOR EACH ROW EXECUTE FUNCTION audit_row('rule_id');
CREATE TRIGGER trg_audit_alert_events AFTER INSERT OR UPDATE OR DELETE ON alert_events
    FOR EACH ROW EXECUTE FUNCTION audit_row('alert_id');
CREATE TRIGGER trg_audit_disaster_events AFTER INSERT OR UPDATE OR DELETE ON disaster_events
    FOR EACH ROW EXECUTE FUNCTION audit_row('event_id');
CREATE TRIGGER trg_audit_quality_thresholds AFTER INSERT OR UPDATE OR DELETE ON quality_thresholds
    FOR EACH ROW EXECUTE FUNCTION audit_row('threshold_id');
CREATE TRIGGER trg_audit_disaster_types AFTER INSERT OR UPDATE OR DELETE ON disaster_types
    FOR EACH ROW EXECUTE FUNCTION audit_row('disaster_type_id');
CREATE TRIGGER trg_audit_administrative_regions AFTER UPDATE OF in_aoi ON administrative_regions
    FOR EACH ROW WHEN (OLD.in_aoi IS DISTINCT FROM NEW.in_aoi)
    EXECUTE FUNCTION audit_row('region_id');
CREATE TRIGGER trg_audit_app_settings AFTER INSERT OR UPDATE OR DELETE ON app_settings
    FOR EACH ROW EXECUTE FUNCTION audit_row('setting_key');
CREATE TRIGGER trg_audit_live_areas AFTER INSERT OR UPDATE OR DELETE ON live_areas
    FOR EACH ROW EXECUTE FUNCTION audit_row('area_id', 'status', 'status_message',
        'last_checked_at', 'forecast', 'forecast_updated_at');
CREATE TRIGGER trg_audit_satellite_scenes AFTER UPDATE OF is_valid ON satellite_scenes
    FOR EACH ROW WHEN (OLD.is_valid IS DISTINCT FROM NEW.is_valid)
    EXECUTE FUNCTION audit_row('scene_id');
CREATE TRIGGER trg_audit_nasa_scenes AFTER UPDATE OF is_valid ON nasa_scenes
    FOR EACH ROW WHEN (OLD.is_valid IS DISTINCT FROM NEW.is_valid)
    EXECUTE FUNCTION audit_row('nasa_scene_id');
CREATE TRIGGER trg_audit_datasets AFTER INSERT OR UPDATE OR DELETE ON datasets
    FOR EACH ROW EXECUTE FUNCTION audit_row('dataset_id', 'total_scenes',
        'completed_scenes', 'failed_scenes', 'total_size_bytes');

-- =============================================================================
-- END monitor_security.sql
-- =============================================================================
