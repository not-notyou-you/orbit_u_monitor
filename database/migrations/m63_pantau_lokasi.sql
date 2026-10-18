-- =============================================================================
-- database/migrations/m63_pantau_lokasi.sql — Orbit-U: The Monitor
-- =============================================================================
-- Migrasi DB yang SUDAH berjalan: VIEW Pantau Lokasi di Beranda (README M63,
-- INTERFACE.md §2 halaman 1). Database baru tidak memerlukannya:
-- monitor_schema.sql dan monitor_security.sql sudah memuatnya.
--
-- Idempoten (boleh dijalankan ulang). Tidak mengubah tabel atau baris data.
-- Jalankan sebagai pemilik skema:
--     python database/apply_schema.py --migrate m63_pantau_lokasi.sql
--
-- Isi VIEW disalin dari monitor_schema.sql supaya sama persis dengan skema baru.
-- =============================================================================

BEGIN;

-- Pantau Lokasi (M63, INTERFACE.md §2 halaman 1): angka per kecamatan untuk
-- Beranda. Batas waktu sama dengan v_citra_obs_aoi (PUBLIC 30 hari, USER 365
-- hari, ANALYST/DATA_ENGINEER semua). DUA observasi terakhir per kecamatan ×
-- band selalu terlihat: kalimat kondisi membandingkan nilai terbaru dengan
-- sebelumnya (mis. lintasan Sentinel-1 ±12 hari), dan pipeline yang sempat
-- berhenti tidak boleh membuat pembandingnya hilang.
CREATE OR REPLACE VIEW v_public_lokasi_obs AS
WITH ranked AS (
    SELECT o.region_id, o.band_id, o.obs_date, o.value, o.valid_fraction, o.run_type,
           row_number() OVER (PARTITION BY o.region_id, o.band_id ORDER BY o.obs_date DESC) AS rn
    FROM region_observations o
)
SELECT o.region_id,
       r.pcode,
       r.region_name,
       o.obs_date,
       src.source_code,
       b.band_code,
       b.unit,
       o.value,
       o.valid_fraction,
       o.run_type
FROM ranked                 o
JOIN administrative_regions r   ON r.region_id = o.region_id AND r.in_aoi
JOIN spectral_bands         b   ON b.band_id = o.band_id
JOIN satellite_sources      src ON src.source_id = b.source_id
WHERE pg_has_role(current_user, 'monitor_analyst', 'MEMBER')
   OR pg_has_role(current_user, 'monitor_data_engineer', 'MEMBER')
   OR o.obs_date >= CURRENT_DATE - CASE WHEN pg_has_role(current_user, 'monitor_user', 'MEMBER') THEN 365 ELSE 30 END
   OR o.rn <= 2;
COMMENT ON VIEW v_public_lokasi_obs IS 'Angka harian/per lintasan per kecamatan AOI untuk Pantau Lokasi di Beranda, batas waktu per role pemanggil seperti v_citra_obs_aoi; dua observasi terakhir per kecamatan × band selalu terlihat (M63). PUBLIC+.';

-- Rentang biasa per kecamatan × band: persentil 2–98 setahun sampai observasi
-- terakhir band itu. Hanya dua angka per band, jadi aman dibuka walau
-- riwayatnya sendiri tidak (pola band_ranges() di api/routes/diagram.py).
CREATE OR REPLACE VIEW v_public_lokasi_range AS
WITH last AS (
    SELECT band_id, max(obs_date) AS obs_date FROM region_observations GROUP BY band_id
)
SELECT o.region_id,
       b.band_code,
       percentile_cont(0.02) WITHIN GROUP (ORDER BY o.value) AS p02,
       percentile_cont(0.98) WITHIN GROUP (ORDER BY o.value) AS p98,
       count(*)                                              AS n_obs
FROM region_observations    o
JOIN administrative_regions r ON r.region_id = o.region_id AND r.in_aoi
JOIN spectral_bands         b ON b.band_id = o.band_id
JOIN last                   l ON l.band_id = o.band_id
WHERE o.value IS NOT NULL
  AND o.obs_date > l.obs_date - 365
GROUP BY o.region_id, b.band_code;
COMMENT ON VIEW v_public_lokasi_range IS 'Rentang biasa (persentil 2–98, 365 hari s.d. observasi terakhir band) per kecamatan AOI × band untuk grafik dan kalimat Pantau Lokasi (M63). PUBLIC+.';

-- Alert hujan 7 hari terakhir per kecamatan, tanpa kolom penanganan
-- (acknowledged_by/at): yang publik hanya "kecamatan ini pernah melewati
-- ambang BMKG", angka yang sama yang sudah tampak di grafik hujannya.
CREATE OR REPLACE VIEW v_public_lokasi_alert AS
SELECT a.region_id,
       a.observation_date,
       a.severity,
       b.band_code,
       a.observed_value,
       a.threshold_value
FROM alert_events           a
JOIN administrative_regions r  ON r.region_id = a.region_id AND r.in_aoi
JOIN alert_rules            ru ON ru.rule_id = a.rule_id
JOIN spectral_bands         b  ON b.band_id = ru.band_id
WHERE a.observation_date >= CURRENT_DATE - 7;
COMMENT ON VIEW v_public_lokasi_alert IS 'Alert hujan 7 hari terakhir per kecamatan AOI untuk Pantau Lokasi, tanpa kolom penanganan alert (M63). PUBLIC+.';

GRANT SELECT ON v_public_lokasi_obs, v_public_lokasi_range, v_public_lokasi_alert TO monitor_public;

COMMIT;
