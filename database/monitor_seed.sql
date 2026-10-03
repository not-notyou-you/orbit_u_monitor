-- =============================================================================
-- database/monitor_seed.sql — Orbit-U: The Monitor
-- =============================================================================
-- Data master (12 tabel) + app_settings. Dijalankan sekali setelah
-- monitor_schema.sql dan monitor_security.sql (DATABASE.md §3, PIPELINE.md §10).
--
-- Sengaja TIDAK dimuat di sini (IMPLEMENTATION_NOTES K9):
--   users                   admin pertama dibuat scripts/create_admin.py
--                           (hash sandi tidak disimpan di berkas SQL)
--   administrative_regions  dimuat scripts/load_regions.py dari shapefile COD-AB
--   regions_of_interest     AOI GMLS diturunkan setelah kecamatan in_aoi ditandai
-- =============================================================================

BEGIN;

-- M1 roles --------------------------------------------------------------------
INSERT INTO roles (role_code, role_name, db_role, requires_login, description) VALUES
    ('PUBLIC',        'Pengunjung',    'monitor_public',        false, 'Scene Live terbaru tanpa login.'),
    ('USER',          'Relawan',       'monitor_user',          true,  'Scene Live 30 hari + prakiraan, statistik hujan hari ini, alert aktif (lihat).'),
    ('ANALYST',       'Analis',        'monitor_analyst',       true,  'USER + Analitik, acknowledge alert, CRUD kejadian, Laporan Hidromet.'),
    ('DATA_ENGINEER', 'Data Engineer', 'monitor_data_engineer', true,  'USER + Katalog Dataset, unduh produk/fusion, lineage, Laporan Kesehatan Data.'),
    ('ADMIN',         'Administrator', 'monitor_admin',         true,  'Semua akses + kelola scene, Live Area, pengguna, aturan, wilayah, log, audit.');

-- M3 satellite_sources --------------------------------------------------------
INSERT INTO satellite_sources (source_code, source_name, provider, sensor_type, spatial_resolution_m, nominal_revisit_days, products) VALUES
    ('SENTINEL1', 'Sentinel-1 SAR',     'ESA / CDSE',           'SAR',           10,    12, 'GRD IW (VV + VH)'),
    ('MODIS',     'MODIS Terra & Aqua', 'NASA LANCE / LAADS',   'OPTICAL',       250,   1,  'MCDWD_L3_F2_NRT, MOD09A1, MOD09GA'),
    ('GPM',       'GPM IMERG',          'NASA GES DISC',        'PRECIPITATION', 11000, 1,  'GPM_3IMERGDF, GPM_3IMERGDL, GPM_3IMERGDE'),
    ('FUSION',    'Fusion multi-sensor', 'Orbit-U (turunan)',   'DERIVED',       NULL,  NULL, 'HDF5 feature stack S1 + MODIS + GPM');

-- M4 spectral_bands -----------------------------------------------------------
INSERT INTO spectral_bands (source_id, band_code, band_name, unit, valid_min, valid_max, aggregation)
SELECT s.source_id, b.band_code, b.band_name, b.unit, b.valid_min, b.valid_max, b.aggregation
FROM (VALUES
    -- Rentang = batas FISIK, bukan batas "wajar": tujuannya menolak nilai
    -- rusak (satuan salah, NoData bocor), bukan kejadian ekstrem yang sah
    -- (IMPLEMENTATION_NOTES K16).
    -- S1 GRD sigma0: lantai derau IW ~ -30..-35 dB; > +30 dB hanya pantulan
    -- sudut (bangunan) -- di luar itu hampir pasti salah satuan.
    ('SENTINEL1', 'VV',           'Backscatter VV',               'dB',    -60,  30,   'MEAN'),
    ('SENTINEL1', 'VH',           'Backscatter VH',               'dB',    -60,  30,   'MEAN'),
    ('SENTINEL1', 'WATER_PCT',    'Persen air (VH < ambang)',     '%',     0,    100,  'FRACTION'),
    ('SENTINEL1', 'WATER_CHANGE', 'Perubahan luas air',           'km2',   0,    NULL, 'MEAN'),
    ('MODIS',     'FLOOD',        'Genangan MODIS (MCDWD)',       '%',     0,    100,  'FRACTION'),
    ('MODIS',     'NDVI',         'Indeks vegetasi (NDVI)',       'index', -1,   1,    'MEAN'),
    ('MODIS',     'NDWI',         'Indeks air (NDWI)',            'index', -1,   1,    'MEAN'),
    -- Hujan: dibulatkan ke atas dari rekor dunia WMO (24 jam 1825 mm, Foc-Foc
    -- 1966; 72 jam ~3930 mm, Cratere Commerson 2007; 8 hari ~5400 mm; bulan
    -- ~9300 mm, Cherrapunji 1861). Rerata GPM ~10 km per kecamatan tidak
    -- akan pernah mendekatinya, jadi ambang ini tidak menolak hujan sah.
    ('GPM',       'RAIN_24H',     'Hujan 24 jam',                 'mm',    0,    2000,  'MEAN'),
    ('GPM',       'RAIN_72H',     'Hujan 72 jam',                 'mm',    0,    4000,  'MEAN'),
    ('GPM',       'RAIN_7D',      'Hujan 7 hari',                 'mm',    0,    6000,  'MEAN'),
    ('GPM',       'RAIN_30D',     'Hujan 30 hari',                'mm',    0,    10000, 'MEAN')
) AS b(source_code, band_code, band_name, unit, valid_min, valid_max, aggregation)
JOIN satellite_sources s ON s.source_code = b.source_code;

-- M7 processing_stages --------------------------------------------------------
INSERT INTO processing_stages (stage_name, stage_code, stage_order, description, source_code, timeout_minutes, retry_count, retry_delay_sec, is_mandatory) VALUES
    ('DOWNLOAD',           'DL',  1, 'Unduh scene/granule dari API resmi (CDSE, LANCE/LAADS, GES DISC)',       NULL,        120, 3, 60, true),
    ('CROP',               'CR',  2, 'Kalibrasi + reproject + potong S1 ke bbox ROI (tier ALIGNED)',           'SENTINEL1', 30,  2, 30, true),
    ('LEE_FILTER',         'LF',  3, 'Reduksi speckle SAR dengan filter Lee 7x7 (tier DESPECKLED)',            'SENTINEL1', 45,  2, 30, true),
    ('COG_EXPORT',         'CE',  4, 'Normalisasi dan ekspor Cloud-Optimized GeoTIFF (warisan)',               NULL,        30,  2, 30, true),
    ('ORCHESTRATE',        'OR',  5, 'Orkestrasi pipeline, checkpoint, dan retry',                             NULL,        10,  1, 10, true),
    ('QUALITY_ANALYTICS',  'QA',  6, 'Metrik kualitas radiometrik S1 (quality_metrics)',                       'SENTINEL1', 30,  2, 30, true),
    ('FUSION',             'FS',  7, 'Stack HDF5 multi-sensor S1 + MODIS + GPM (tier FUSED)',                  'FUSION',    60,  2, 30, true),
    ('GOLD_EXPORT',        'GE',  8, 'Ekspor COG per sumber (tier COG)',                                       NULL,        45,  2, 30, true),
    ('PREVIEW',            'PV',  9, 'Render PNG preview dari COG, sebelum FUSION',                            NULL,        15,  1, 15, false),
    ('HYDROMET_AGGREGATE', 'HA', 10, 'Zonal statistics COG GPM/MODIS per kecamatan -> region_observations',    NULL,        30,  2, 30, true),
    ('ALERT_CHECK',        'AC', 11, 'Evaluasi alert_rules terhadap region_observations -> alert_events',     NULL,        10,  2, 30, true),
    ('WATER_CHANGE',       'WC', 12, 'Peta & metrik perubahan air S1 antar scene Live (M19)',                  'SENTINEL1', 20,  1, 15, false),
    ('REPORT_BUILD',       'RB', 13, 'Pembuatan laporan PDF mingguan/bulanan',                                 NULL,        30,  1, 60, true);

-- M8 quality_thresholds -------------------------------------------------------
INSERT INTO quality_thresholds (band_id, metric_name, warn_below, fail_below, reference)
SELECT b.band_id, t.metric_name, t.warn_below, t.fail_below, t.reference
FROM (VALUES
    ('VV',       'quality_score',  NULL::numeric, 60::numeric, 'Konstanta DataLab module6 (skor < 60 = FAIL)'),
    ('VH',       'quality_score',  NULL,          60,          'Konstanta DataLab module6 (skor < 60 = FAIL)'),
    ('FLOOD',    'valid_fraction', 0.5,           0.1,         'DATABASE.md §3.8'),
    ('NDVI',     'valid_fraction', 0.5,           0.1,         'DATABASE.md §3.8'),
    ('NDWI',     'valid_fraction', 0.5,           0.1,         'DATABASE.md §3.8'),
    ('RAIN_24H', 'valid_fraction', 0.5,           0.1,         'DATABASE.md §3.8'),
    ('RAIN_72H', 'valid_fraction', 0.5,           0.1,         'DATABASE.md §3.8'),
    ('RAIN_7D',  'valid_fraction', 0.5,           0.1,         'DATABASE.md §3.8'),
    ('RAIN_30D', 'valid_fraction', 0.5,           0.1,         'DATABASE.md §3.8')
) AS t(band_code, metric_name, warn_below, fail_below, reference)
JOIN spectral_bands b ON b.band_code = t.band_code;

-- M9 disaster_types -----------------------------------------------------------
INSERT INTO disaster_types (type_code, type_name, indicator_bands) VALUES
    ('BANJIR',         'Banjir',         'RAIN_24H, VH, FLOOD'),
    ('BANJIR_BANDANG', 'Banjir bandang', 'RAIN_24H'),
    ('LONGSOR',        'Tanah longsor',  'RAIN_72H'),
    ('KEKERINGAN',     'Kekeringan',     'RAIN_30D, NDVI');

-- M10 alert_rules -------------------------------------------------------------
INSERT INTO alert_rules (rule_code, disaster_type_id, band_id, comparator, threshold_value, severity, reference_source, is_active)
SELECT r.rule_code, d.disaster_type_id, b.band_id, '>=', r.threshold_value, r.severity, r.reference_source, r.is_active
FROM (VALUES
    ('FLOOD_RAIN24_HEAVY',   'BANJIR',  'RAIN_24H', 50::numeric,  'INFO',     'BMKG (hujan lebat)',        true),
    ('FLOOD_RAIN24_VHEAVY',  'BANJIR',  'RAIN_24H', 100,          'WARNING',  'BMKG (hujan sangat lebat)', true),
    ('FLOOD_RAIN24_EXTREME', 'BANJIR',  'RAIN_24H', 150,          'CRITICAL', 'BMKG (hujan ekstrem)',      true),
    -- Ambang longsor diisi dari literatur sebelum diaktifkan (K7).
    ('LANDSLIDE_RAIN72',     'LONGSOR', 'RAIN_72H', NULL,         'WARNING',  '— (menunggu literatur)',    false)
) AS r(rule_code, type_code, band_code, threshold_value, severity, reference_source, is_active)
JOIN disaster_types d ON d.type_code = r.type_code
JOIN spectral_bands b ON b.band_code = r.band_code;

-- M11 fusion_strategies -------------------------------------------------------
INSERT INTO fusion_strategies (strategy_code, download_axis, assemble_axis, description) VALUES
    ('CO_OCCURRENCE', 'Tanggal S1 saja', 'Per tanggal S1', 'MODIS/GPM hanya diunduh untuk tanggal yang punya scene S1; satu HDF5 per tanggal S1.'),
    ('FULL_COVERAGE', 'Setiap hari',     'Per hari',       'Satu HDF5 per hari; S1 dipinjam dari hari terdekat dalam s1_match_tolerance_days.'),
    ('HYBRID',        'Setiap hari',     'Per tanggal S1', 'Unduh aux harian seperti FULL_COVERAGE, rakit per tanggal S1 seperti CO_OCCURRENCE.');

-- M12 report_types ------------------------------------------------------------
INSERT INTO report_types (report_code, report_name, period, audience_role_id, template_version)
SELECT t.report_code, t.report_name, t.period, r.role_id, '1.0'
FROM (VALUES
    ('HYDROMET_WEEKLY',    'Laporan Hidromet Mingguan',         'WEEKLY',  'ANALYST'),
    ('HYDROMET_MONTHLY',   'Laporan Hidromet Bulanan',          'MONTHLY', 'ANALYST'),
    ('DATAHEALTH_WEEKLY',  'Laporan Kesehatan Data Mingguan',   'WEEKLY',  'DATA_ENGINEER'),
    ('DATAHEALTH_MONTHLY', 'Laporan Kesehatan Data Bulanan',    'MONTHLY', 'DATA_ENGINEER')
) AS t(report_code, report_name, period, role_code)
JOIN roles r ON r.role_code = t.role_code;

-- app_settings ----------------------------------------------------------------
INSERT INTO app_settings (setting_key, setting_value, description) VALUES
    ('live.max_areas',        '5',              'Jumlah maksimum Live Area aktif.'),
    ('live.retention_max',    '60',             'Batas atas retensi scene per Live Area (M11).'),
    ('report.timezone',       '"Asia/Jakarta"', 'Zona waktu periode laporan (WIB).'),
    ('water.vh_threshold_db', '-20',            'Ambang air VH (dB) untuk peta perubahan air dan kalimat Live.'),
    ('dataset.max_days',      '366',            'Rentang tanggal maksimum satu dataset (hari).'),
    -- Tahap 3 (IMPLEMENTATION_NOTES "Tahap 3"): angka yang PIPELINE.md sebut
    -- sebagai default/batas operasional, dipindah dari konstanta kode.
    ('live.retention_default',          '6',               'Retensi scene default Live Area baru (1..live.retention_max).'),
    ('live.default_area_name',          '"Lebak Selatan"', 'Nama Live Area default yang dibuat dari ROI AOI GMLS (PIPELINE §4).'),
    ('hydromet.min_valid_fraction',     '0.1',             'Di bawah fraksi piksel valid ini nilai zonal kecamatan = NULL (PIPELINE §3.3).'),
    ('hydromet.waiting_max_days',       '3',               'Berapa hari tanggal hidromet boleh WAITING_UPSTREAM sebelum FAILED (PIPELINE §8).'),
    ('report.wait_hydromet_minutes',    '60',              'Lama job laporan menunggu advisory lock hidromet sebelum tetap jalan (PIPELINE §6.1).');

COMMIT;
