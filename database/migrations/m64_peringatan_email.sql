-- =============================================================================
-- database/migrations/m64_peringatan_email.sql — Orbit-U: The Monitor
-- =============================================================================
-- Migrasi DB yang SUDAH berjalan: peringatan email kondisi tidak normal per
-- kecamatan (README M64, INTERFACE.md). Database baru tidak memerlukannya:
-- monitor_schema.sql, monitor_security.sql, dan monitor_seed.sql sudah
-- memuatnya.
--
-- Idempoten (boleh dijalankan ulang). Tidak mengubah baris data yang ada:
-- email lama tetap tersimpan tetapi email_verified_at-nya NULL, jadi tidak
-- dikirimi peringatan sampai pemiliknya menyimpan ulang lewat Akun saya.
-- Jalankan sebagai pemilik skema:
--     python database/apply_schema.py --migrate m64_peringatan_email.sql
--
-- Isi disalin dari ketiga berkas skema supaya sama persis dengan database baru.
-- =============================================================================

BEGIN;

-- 1. users: status pengecekan email + langganan semua kecamatan ---------------
ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified_at  TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS notify_all_regions BOOLEAN NOT NULL DEFAULT false;
COMMENT ON COLUMN users.email              IS 'Alamat email (unik, tanpa membedakan huruf besar). Opsional (M64; wajib saat registrasi pada M56). Hanya disimpan bila lolos pengecekan: format, MX domain, dan email konfirmasi terkirim.';
COMMENT ON COLUMN users.email_verified_at  IS 'Waktu email lolos pengecekan dan email konfirmasi terkirim (M64). NULL = email lama yang belum dicek; tidak dikirimi peringatan.';
COMMENT ON COLUMN users.notify_all_regions IS 'true = berlangganan peringatan email untuk SEMUA kecamatan AOI, termasuk yang ditambahkan kemudian (M64).';

-- 2. tabel langganan dan anti-duplikat ---------------------------------------------
-- Peringatan email (M64) --------------------------------------------------------
-- Kecamatan yang dipilih pengguna untuk peringatan email. Kosong (dan
-- users.notify_all_regions false) = tidak menerima peringatan; itu sah.
CREATE TABLE IF NOT EXISTS user_notify_regions (
    user_id    INT          NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
    region_id  INT          NOT NULL REFERENCES administrative_regions (region_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, region_id)
);
CREATE INDEX IF NOT EXISTS idx_user_notify_regions_region ON user_notify_regions (region_id);
COMMENT ON TABLE  user_notify_regions IS 'Langganan peringatan email per kecamatan (M64): tempat tinggal, beberapa, atau tidak sama sekali. Diubah pemiliknya lewat auth_set_own_notify().';
COMMENT ON COLUMN user_notify_regions.user_id    IS 'FK -> users pelanggan.';
COMMENT ON COLUMN user_notify_regions.region_id  IS 'FK -> administrative_regions (kecamatan AOI).';
COMMENT ON COLUMN user_notify_regions.created_at IS 'Waktu kecamatan dipilih.';

-- Satu baris = satu butir "tidak normal" (kalimat kondisi atau alert hujan)
-- untuk satu kecamatan dan satu tanggal data yang SUDAH dikirim ke pengguna.
-- Kunci unik ini yang mencegah data yang sama dikirim dua kali; data baru
-- (tanggal lain) dengan kondisi yang sama tetap dikirim.
CREATE TABLE IF NOT EXISTS notify_sent (
    notify_id  BIGSERIAL    PRIMARY KEY,
    user_id    INT          NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
    region_id  INT          NOT NULL REFERENCES administrative_regions (region_id),
    item_key   VARCHAR(20)  NOT NULL,
    data_date  DATE         NOT NULL,
    level      SMALLINT     NOT NULL CHECK (level BETWEEN 1 AND 2),
    sent_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT uq_notify_sent UNIQUE (user_id, region_id, item_key, data_date)
);
CREATE INDEX IF NOT EXISTS idx_notify_sent_time ON notify_sent (sent_at DESC);
COMMENT ON TABLE  notify_sent IS 'Butir tidak normal yang sudah dikirim lewat email (M64). Kunci unik (pengguna, kecamatan, butir, tanggal data) mencegah pengiriman ulang data yang sama.';
COMMENT ON COLUMN notify_sent.notify_id IS 'PK surrogate.';
COMMENT ON COLUMN notify_sent.user_id   IS 'FK -> users penerima.';
COMMENT ON COLUMN notify_sent.region_id IS 'FK -> administrative_regions (kecamatan).';
COMMENT ON COLUMN notify_sent.item_key  IS 'Butir kalimat kondisi (mis. gpm_rain_7d, s1_vh, modis_flood) atau "alert" untuk alert hujan BMKG.';
COMMENT ON COLUMN notify_sent.data_date IS 'Tanggal data yang menunjukkan kondisi tidak normal (tanggal observasi satelit atau alert).';
COMMENT ON COLUMN notify_sent.level     IS 'Tingkat saat dikirim: 1 Waspada, 2 Tinggi.';
COMMENT ON COLUMN notify_sent.sent_at   IS 'Waktu email terkirim.';

-- 3. registrasi: email opsional --------------------------------------------------
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
    IF p_email IS NOT NULL AND EXISTS (SELECT 1 FROM users WHERE lower(email) = lower(p_email)) THEN
        RAISE EXCEPTION 'email taken' USING ERRCODE = 'unique_violation', CONSTRAINT = 'uq_users_email';
    END IF;
    -- Email opsional (M64). Bila ada, API sudah mengeceknya (format, MX,
    -- email konfirmasi terkirim) sebelum memanggil fungsi ini.
    INSERT INTO users (role_id, username, email, email_verified_at, password_hash, full_name)
    SELECT role_id, lower(p_username), lower(p_email),
           CASE WHEN p_email IS NULL THEN NULL ELSE now() END, p_hash, lower(p_username)
    FROM roles WHERE role_code = 'USER'
    RETURNING user_id INTO uid;
    RETURN uid;
END $$;
COMMENT ON FUNCTION auth_register_user(text, text, text) IS 'Registrasi mandiri: membuat akun role USER (dikunci di fungsi) dengan full_name = username; email opsional (M64). Satu-satunya jalan monitor_public menulis users (M56).';

-- 4. fungsi dan GRANT ---------------------------------------------------------
-- Fungsi yang sudah ada dihapus dulu: CREATE OR REPLACE tidak boleh mengubah
-- bentuk RETURNS TABLE.
DROP FUNCTION IF EXISTS auth_get_own_notify();
DROP FUNCTION IF EXISTS notify_recipients();
-- =============================================================================
-- PERINGATAN EMAIL (M64)
-- =============================================================================
-- Email dan kecamatan langganan milik sendiri. USER tidak punya UPDATE pada
-- users (§8.3); baris yang diubah ditentukan app.user_id sesi, bukan argumen.
-- Fungsi ini MEMPERCAYAI API sudah mengecek email (format, MX domain, email
-- konfirmasi terkirim) sebelum memanggilnya -- pengguna tidak pernah
-- menjalankan SQL sendiri.
CREATE OR REPLACE FUNCTION auth_get_own_notify()
RETURNS TABLE (email varchar, email_verified_at timestamptz, all_regions boolean, region_ids int[])
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE uid int := NULLIF(current_setting('app.user_id', true), '')::int;
BEGIN
    IF uid IS NULL THEN
        RAISE EXCEPTION 'app.user_id is not set' USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN QUERY
    SELECT u.email, u.email_verified_at, u.notify_all_regions,
           COALESCE((SELECT array_agg(n.region_id ORDER BY n.region_id)
                     FROM user_notify_regions n WHERE n.user_id = uid), '{}'::int[])
    FROM users u WHERE u.user_id = uid;
END $$;
COMMENT ON FUNCTION auth_get_own_notify() IS 'Akun saya (M64): email, waktu lolos pengecekan, dan kecamatan langganan peringatan milik app.user_id sesi.';

CREATE OR REPLACE FUNCTION auth_email_available(p_email text) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
    SELECT NOT EXISTS (
        SELECT 1 FROM users
        WHERE lower(email) = lower(p_email)
          AND user_id IS DISTINCT FROM NULLIF(current_setting('app.user_id', true), '')::int);
$$;
COMMENT ON FUNCTION auth_email_available(text) IS 'true bila email belum dipakai akun lain (akun sesi sendiri dikecualikan). Dipanggil API SEBELUM mengirim email konfirmasi, supaya konfirmasi tidak dikirim untuk email yang lalu ditolak (M64).';

CREATE OR REPLACE FUNCTION auth_set_own_email(p_email text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE uid int := NULLIF(current_setting('app.user_id', true), '')::int;
BEGIN
    IF uid IS NULL THEN
        RAISE EXCEPTION 'app.user_id is not set' USING ERRCODE = 'insufficient_privilege';
    END IF;
    UPDATE users
    SET email = lower(p_email),
        email_verified_at = CASE WHEN p_email IS NULL THEN NULL ELSE now() END
    WHERE user_id = uid AND is_active;
    RETURN FOUND;
END $$;
COMMENT ON FUNCTION auth_set_own_email(text) IS 'Simpan (atau hapus, NULL) email milik app.user_id sesi; email_verified_at = now(). Dipanggil API hanya setelah email lolos pengecekan (M64). Email ganda -> unique_violation uq_users_email.';

CREATE OR REPLACE FUNCTION auth_set_own_notify(p_all boolean, p_regions int[]) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE uid int := NULLIF(current_setting('app.user_id', true), '')::int;
        n int;
BEGIN
    IF uid IS NULL THEN
        RAISE EXCEPTION 'app.user_id is not set' USING ERRCODE = 'insufficient_privilege';
    END IF;
    UPDATE users SET notify_all_regions = COALESCE(p_all, false) WHERE user_id = uid AND is_active;
    IF NOT FOUND THEN
        RETURN 0;
    END IF;
    DELETE FROM user_notify_regions WHERE user_id = uid;
    INSERT INTO user_notify_regions (user_id, region_id)
    SELECT uid, r.region_id FROM administrative_regions r
    WHERE r.region_id = ANY (COALESCE(p_regions, '{}'::int[])) AND r.admin_level = 3 AND r.in_aoi;
    GET DIAGNOSTICS n = ROW_COUNT;
    RETURN n;
END $$;
COMMENT ON FUNCTION auth_set_own_notify(boolean, int[]) IS 'Ganti langganan peringatan milik app.user_id sesi: semua kecamatan (true) dan/atau daftar kecamatan AOI (yang bukan kecamatan AOI diabaikan). Mengembalikan jumlah kecamatan tersimpan (M64).';

-- Penerima peringatan untuk job notifikasi (monitor_etl, tanpa hak atas
-- users): hanya akun aktif dengan email yang lolos pengecekan dan minimal
-- satu kecamatan. Tanpa hash, tanpa token.
CREATE OR REPLACE FUNCTION notify_recipients()
RETURNS TABLE (user_id int, username varchar, full_name varchar, role_code varchar,
               email varchar, region_ids int[])
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
    SELECT q.* FROM (
        SELECT u.user_id, u.username, u.full_name, r.role_code, u.email,
               CASE WHEN u.notify_all_regions
                    THEN (SELECT array_agg(a.region_id ORDER BY a.region_id) FROM administrative_regions a
                          WHERE a.admin_level = 3 AND a.in_aoi)
                    ELSE (SELECT array_agg(n.region_id ORDER BY n.region_id) FROM user_notify_regions n
                          JOIN administrative_regions a ON a.region_id = n.region_id AND a.in_aoi
                          WHERE n.user_id = u.user_id) END AS region_ids
        FROM users u JOIN roles r ON r.role_id = u.role_id
        WHERE u.is_active AND u.email IS NOT NULL AND u.email_verified_at IS NOT NULL
    ) q
    WHERE q.region_ids IS NOT NULL AND cardinality(q.region_ids) > 0
    ORDER BY q.user_id;
$$;
COMMENT ON FUNCTION notify_recipients() IS 'Penerima peringatan email (M64): akun aktif ber-email terverifikasi dengan kecamatan langganannya (semua kecamatan AOI bila notify_all_regions). Satu-satunya jalan monitor_etl membaca email pengguna.';

ALTER FUNCTION auth_get_own_notify()                 OWNER TO monitor_admin;
ALTER FUNCTION auth_email_available(text)            OWNER TO monitor_admin;
ALTER FUNCTION auth_set_own_email(text)              OWNER TO monitor_admin;
ALTER FUNCTION auth_set_own_notify(boolean, int[])   OWNER TO monitor_admin;
ALTER FUNCTION notify_recipients()                   OWNER TO monitor_admin;
REVOKE ALL ON FUNCTION auth_get_own_notify(), auth_email_available(text), auth_set_own_email(text),
                       auth_set_own_notify(boolean, int[]), notify_recipients() FROM PUBLIC;
-- Registrasi (pengunjung) juga memeriksa email sebelum mengirim konfirmasi.
GRANT EXECUTE ON FUNCTION auth_email_available(text) TO monitor_public;
GRANT EXECUTE ON FUNCTION auth_get_own_notify(), auth_set_own_email(text),
                          auth_set_own_notify(boolean, int[]) TO monitor_user;
GRANT EXECUTE ON FUNCTION notify_recipients() TO monitor_etl;

-- Fungsi auth_set_own_notify (milik monitor_admin) mengganti baris langganan.
GRANT SELECT, INSERT, DELETE ON user_notify_regions TO monitor_admin;
GRANT SELECT ON notify_sent TO monitor_admin;
GRANT SELECT, INSERT ON notify_sent TO monitor_etl;
GRANT USAGE ON SEQUENCE notify_sent_notify_id_seq TO monitor_etl;
-- Job notifikasi membaca angka per kecamatan lewat VIEW yang sama dengan
-- Beranda (M63); monitor_etl bukan anggota monitor_user, jadi jendelanya
-- sama dengan pengunjung: 30 hari + dua observasi terakhir.
GRANT SELECT ON v_public_lokasi_obs, v_public_lokasi_range, v_public_lokasi_alert TO monitor_etl;

-- 5. pengaturan -------------------------------------------------------------------
INSERT INTO app_settings (setting_key, setting_value, description) VALUES
    ('notify.enabled',      'true', 'Kirim peringatan email kondisi tidak normal ke pengguna yang berlangganan kecamatan (M64).'),
    ('notify.max_age_days', '7',    'Hanya data yang tanggalnya paling lama sekian hari yang memicu email; data backfill yang lebih tua tidak dikirim (M64).')
ON CONFLICT (setting_key) DO NOTHING;

COMMIT;
