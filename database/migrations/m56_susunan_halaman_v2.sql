-- =============================================================================
-- database/migrations/m56_susunan_halaman_v2.sql — Orbit-U: The Monitor
-- =============================================================================
-- Migrasi DB yang SUDAH berjalan ke susunan halaman v2 (README M56,
-- INTERFACE.md). Database baru tidak memerlukannya: monitor_schema.sql dan
-- monitor_security.sql sudah memuat semuanya.
--
-- Idempoten (boleh dijalankan ulang). Tidak menghapus atau mengubah baris data.
-- Jalankan sebagai pemilik skema:
--     python database/apply_schema.py --migrate m56_susunan_halaman_v2.sql
-- atau psql -v ON_ERROR_STOP=1 -d themonitor -f database/migrations/m56_susunan_halaman_v2.sql
--
-- Dibangkitkan dari monitor_schema.sql / monitor_security.sql supaya isi VIEW
-- dan fungsi sama persis dengan skema baru.
-- =============================================================================

BEGIN;

-- 1. users.email (registrasi mandiri) --------------------------------------------
ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(254)
    CHECK (email IS NULL OR email ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$');
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email ON users (lower(email)) WHERE email IS NOT NULL;
COMMENT ON COLUMN users.email              IS 'Alamat email (unik, tanpa membedakan huruf besar). Wajib untuk akun hasil registrasi mandiri (M56); NULL untuk akun lama buatan ADMIN.';

-- 2. v_log_login ikut mencatat REGISTER ------------------------------------------
CREATE OR REPLACE VIEW v_log_login AS
SELECT l.log_id, l.logged_at, l.action, l.user_id, u.username,
       l.username_attempted, l.ip_address, l.user_agent, l.detail
FROM user_activity_logs l
LEFT JOIN users u ON u.user_id = l.user_id
WHERE l.action IN ('LOGIN_SUCCESS', 'LOGIN_FAILED', 'LOGOUT', 'REGISTER');
COMMENT ON VIEW v_log_login IS 'Log masuk, keluar, dan registrasi akun mandiri dari user_activity_logs. ADMIN.';

-- 3. VIEW baru -------------------------------------------------------------------
-- =============================================================================
-- VIEW SUSUNAN HALAMAN v2 (M56, INTERFACE.md §3)
-- =============================================================================
-- Batas waktu per role ditegakkan di VIEW, bukan hanya di API: VIEW berjalan
-- dengan hak pemiliknya, tetapi current_user di dalamnya tetap role pemanggil
-- (hasil SET LOCAL ROLE), sehingga pg_has_role(current_user, ...) membaca
-- peran pengguna yang sebenarnya.

-- Kejadian untuk PUBLIC: 365 hari terakhir, tanpa kolom internal
-- (source_reference, recorded_by, verified_by).
CREATE OR REPLACE VIEW v_public_kejadian AS
SELECT e.event_id,
       dt.type_code     AS disaster_type_code,
       dt.type_name     AS disaster_type_name,
       e.region_id,
       r.pcode,
       r.region_name,
       e.village_name,
       ST_Y(e.location) AS lat,
       ST_X(e.location) AS lon,
       e.event_date,
       e.event_end_date,
       e.description,
       e.impact_summary,
       e.info_source,
       e.is_verified
FROM disaster_events        e
JOIN disaster_types         dt ON dt.disaster_type_id = e.disaster_type_id
JOIN administrative_regions r  ON r.region_id = e.region_id
WHERE e.deleted_at IS NULL
  AND e.event_date >= CURRENT_DATE - 365;
COMMENT ON VIEW v_public_kejadian IS 'Kejadian bencana 365 hari terakhir untuk PUBLIC, tanpa source_reference/recorded_by/verified_by (M56). Role login membaca disaster_events langsung tanpa batas waktu.';

-- Scene citra per role: PUBLIC 30 hari, USER 365 hari, ANALYST/DATA_ENGINEER/
-- ADMIN tanpa batas. Scene terbaru tiap area selalu terlihat (sama dengan
-- halaman publik lama), supaya pipeline yang sempat berhenti tidak membuat
-- halaman kosong. Scene yang berkasnya sudah dihapus retensi tetap tampil
-- (angkanya ada di live_scene_metrics) dengan files_available = false.
CREATE OR REPLACE VIEW v_citra_scenes AS
SELECT s.live_scene_id,
       s.area_id,
       a.name                 AS area_name,
       s.scene_date,
       s.status,
       s.area_status,
       s.interpretations,
       s.previews,
       s.source_status,
       (s.deleted_at IS NULL) AS files_available
FROM live_scenes s
JOIN live_areas  a ON a.area_id = s.area_id
WHERE a.deleted_at IS NULL
  AND s.status IN ('READY', 'PARTIAL', 'DELETED')
  AND (pg_has_role(current_user, 'monitor_analyst', 'MEMBER')
       OR pg_has_role(current_user, 'monitor_data_engineer', 'MEMBER')
       OR s.scene_date >= CURRENT_DATE - CASE WHEN pg_has_role(current_user, 'monitor_user', 'MEMBER')
                                              THEN 365 ELSE 30 END
       OR s.live_scene_id IN (SELECT live_scene_id FROM v_public_live_latest));
COMMENT ON VIEW v_citra_scenes IS 'Scene citra (Sentinel-1 + MODIS/GPM pendamping) dengan batas waktu per role pemanggil: PUBLIC 30 hari, USER 365 hari, ANALYST/DATA_ENGINEER/ADMIN semua; scene terbaru tiap area selalu terlihat. files_available = PNG masih ada di disk (M56). PUBLIC+.';

-- Angka per band untuk scene yang lolos v_citra_scenes.
CREATE OR REPLACE VIEW v_citra_metrics AS
SELECT m.live_scene_id,
       v.area_id,
       v.scene_date,
       src.source_code,
       b.band_code,
       b.band_name,
       b.unit,
       m.metric_name,
       m.value,
       m.source_date
FROM live_scene_metrics m
JOIN v_citra_scenes     v   ON v.live_scene_id = m.live_scene_id
JOIN spectral_bands     b   ON b.band_id = m.band_id
JOIN satellite_sources  src ON src.source_id = b.source_id;
COMMENT ON VIEW v_citra_metrics IS 'Metrik numerik per band x metrik untuk scene yang terlihat role pemanggil lewat v_citra_scenes (M56). PUBLIC+.';

-- Angka harian GPM/MODIS hasil Job Hidromet (termasuk backfill), dirata-rata
-- ke seluruh kecamatan AOI, dengan batas waktu yang sama seperti
-- v_citra_scenes. Tanggal observasi terakhir tiap satelit selalu terlihat. Angka PER
-- kecamatan tetap milik USER+ (region_observations); pengunjung hanya agregat.
CREATE OR REPLACE VIEW v_citra_obs_aoi AS
WITH latest AS (
    SELECT b.source_id, max(o.obs_date) AS obs_date
    FROM region_observations o JOIN spectral_bands b ON b.band_id = o.band_id
    GROUP BY b.source_id
)
SELECT o.obs_date,
       src.source_code,
       b.band_code,
       b.band_name,
       b.unit,
       avg(o.value)            AS mean_value,
       max(o.value)            AS max_value,
       min(o.value)            AS min_value,
       count(o.value)          AS n_regions,
       avg(o.valid_fraction)   AS valid_fraction,
       max(o.run_type)         AS run_type
FROM region_observations    o
JOIN administrative_regions r   ON r.region_id = o.region_id AND r.in_aoi
JOIN spectral_bands         b   ON b.band_id = o.band_id
JOIN satellite_sources      src ON src.source_id = b.source_id
JOIN latest                 l   ON l.source_id = b.source_id
WHERE pg_has_role(current_user, 'monitor_analyst', 'MEMBER')
   OR pg_has_role(current_user, 'monitor_data_engineer', 'MEMBER')
   OR o.obs_date >= CURRENT_DATE - CASE WHEN pg_has_role(current_user, 'monitor_user', 'MEMBER') THEN 365 ELSE 30 END
   OR o.obs_date = l.obs_date
GROUP BY o.obs_date, src.source_code, b.band_code, b.band_name, b.unit;
COMMENT ON VIEW v_citra_obs_aoi IS 'Angka harian GPM/MODIS (Job Hidromet, termasuk backfill) dirata-rata ke kecamatan AOI, batas waktu per role pemanggil seperti v_citra_scenes; observasi terakhir selalu terlihat (M56). PUBLIC+.';

-- Log halaman Data (DATA_ENGINEER, ADMIN): aktivitas unduhan/backfill +
-- jejak audit tabel katalog dan scene.
CREATE OR REPLACE VIEW v_log_data AS
SELECT 'L-' || l.log_id         AS log_ref,
       l.logged_at,
       'AKTIVITAS'              AS kind,
       l.action,
       l.target_type,
       l.target_id::text        AS target_id,
       l.user_id,
       u.username,
       l.detail
FROM user_activity_logs l
LEFT JOIN users u ON u.user_id = l.user_id
WHERE l.action IN ('DOWNLOAD_DATASET', 'DOWNLOAD_FUSION', 'DOWNLOAD_PRODUCT', 'BACKFILL_START', 'SCENE_UPDATE')
   OR l.target_type IN ('datasets', 'data_products', 'satellite_scenes', 'nasa_scenes')
UNION ALL
SELECT 'A-' || a.audit_id,
       a.changed_at,
       'AUDIT',
       CASE a.operation WHEN 'I' THEN 'INSERT' WHEN 'U' THEN 'UPDATE' ELSE 'DELETE' END,
       a.table_name,
       a.row_pk,
       a.app_user_id,
       u.username,
       jsonb_build_object('changed_columns', to_jsonb(a.changed_columns), 'old', a.old_data, 'new', a.new_data)
FROM audit_log a
LEFT JOIN users u ON u.user_id = a.app_user_id
WHERE a.table_name IN ('datasets', 'dataset_source_config', 'dataset_jobs', 'scene_job_state',
                       'satellite_scenes', 'nasa_scenes');
COMMENT ON VIEW v_log_data IS 'Log yang menyangkut halaman Data: aktivitas unduhan/backfill/ubah scene dan jejak audit tabel katalog & scene (M56). DATA_ENGINEER, ADMIN.';

-- Log halaman Kejadian (ANALYST, ADMIN).
CREATE OR REPLACE VIEW v_log_kejadian AS
SELECT 'A-' || a.audit_id       AS log_ref,
       a.changed_at             AS logged_at,
       'AUDIT'                  AS kind,
       CASE a.operation WHEN 'I' THEN 'INSERT' WHEN 'U' THEN 'UPDATE' ELSE 'DELETE' END AS action,
       a.table_name             AS target_type,
       a.row_pk                 AS target_id,
       a.app_user_id            AS user_id,
       u.username,
       jsonb_build_object('changed_columns', to_jsonb(a.changed_columns), 'old', a.old_data, 'new', a.new_data) AS detail
FROM audit_log a
LEFT JOIN users u ON u.user_id = a.app_user_id
WHERE a.table_name IN ('disaster_events', 'disaster_types')
UNION ALL
SELECT 'L-' || l.log_id,
       l.logged_at,
       'AKTIVITAS',
       l.action,
       l.target_type,
       l.target_id::text,
       l.user_id,
       u.username,
       l.detail
FROM user_activity_logs l
LEFT JOIN users u ON u.user_id = l.user_id
WHERE l.target_type = 'disaster_events'
   OR (l.action = 'DOWNLOAD_XLSX' AND l.detail ->> 'entity' IN ('disasters', 'disaster_rain', 'disaster_types'));
COMMENT ON VIEW v_log_kejadian IS 'Log yang menyangkut halaman Kejadian: jejak audit disaster_events/disaster_types dan ekspor Excel kejadian (M56). ANALYST, ADMIN.';


-- 4. GRANT ----------------------------------------------------------------------
GRANT SELECT ON v_public_kejadian, v_citra_scenes, v_citra_metrics, v_citra_obs_aoi TO monitor_public;
GRANT SELECT ON administrative_regions, disaster_types, satellite_sources, spectral_bands TO monitor_public;
GRANT SELECT ON disaster_events TO monitor_user;
GRANT SELECT ON v_log_kejadian TO monitor_analyst;
GRANT SELECT ON v_log_data TO monitor_data_engineer;
GRANT UPDATE ON satellite_scenes, nasa_scenes TO monitor_data_engineer;
-- ADMIN kini mewarisinya lewat DATA_ENGINEER (sama dengan monitor_security.sql).
REVOKE UPDATE ON satellite_scenes, nasa_scenes FROM monitor_admin;

-- 5. Fungsi registrasi -----------------------------------------------------------
CREATE OR REPLACE FUNCTION auth_register_user(p_username text, p_email text, p_hash text) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE uid int;
BEGIN
    IF p_hash !~ '^\$2[aby]\$\d\d\$.{53}$' THEN
        RAISE EXCEPTION 'password hash must be bcrypt' USING ERRCODE = 'check_violation';
    END IF;
    IF EXISTS (SELECT 1 FROM users WHERE username = lower(p_username)) THEN
        RAISE EXCEPTION 'username taken' USING ERRCODE = 'unique_violation', CONSTRAINT = 'users_username_key';
    END IF;
    IF EXISTS (SELECT 1 FROM users WHERE lower(email) = lower(p_email)) THEN
        RAISE EXCEPTION 'email taken' USING ERRCODE = 'unique_violation', CONSTRAINT = 'uq_users_email';
    END IF;
    INSERT INTO users (role_id, username, email, password_hash, full_name)
    SELECT role_id, lower(p_username), lower(p_email), p_hash, lower(p_username)
    FROM roles WHERE role_code = 'USER'
    RETURNING user_id INTO uid;
    RETURN uid;
END $$;
COMMENT ON FUNCTION auth_register_user(text, text, text) IS 'Registrasi mandiri: membuat akun role USER (dikunci di fungsi) dengan full_name = username. Satu-satunya jalan monitor_public menulis users (M56).';
ALTER FUNCTION auth_register_user(text, text, text) OWNER TO monitor_admin;
REVOKE ALL ON FUNCTION auth_register_user(text, text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION auth_register_user(text, text, text) TO monitor_public;

COMMIT;
