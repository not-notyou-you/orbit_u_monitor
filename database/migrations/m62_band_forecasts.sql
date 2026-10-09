-- =============================================================================
-- database/migrations/m62_band_forecasts.sql — Orbit-U: The Monitor
-- =============================================================================
-- Migrasi DB yang SUDAH berjalan: tabel forecast tersimpan (README M62,
-- DATABASE.md, PIPELINE.md §14). Database baru tidak memerlukannya:
-- monitor_schema.sql dan monitor_security.sql sudah memuatnya.
--
-- Idempoten (boleh dijalankan ulang). Tidak mengubah tabel lain.
-- Jalankan sebagai pemilik skema:
--     python database/apply_schema.py --migrate m62_band_forecasts.sql
-- lalu isi forecast pertama kali:
--     python -m etl.forecast_store
-- =============================================================================

BEGIN;

-- band_forecasts, band_forecast_points, band_forecast_scores (M62) ------------
-- Forecast 15 hari halaman Forecast, dihitung saat data baru masuk
-- (etl/forecast_store.py, PIPELINE.md §14). Satu baris band_forecasts = satu
-- deret (band × AOI atau band × kecamatan) pada satu cap data; titik dan skor
-- backtest per model di tabel anaknya (1NF, sama alasannya dengan M31).
CREATE TABLE IF NOT EXISTS band_forecasts (
    forecast_id      BIGSERIAL     PRIMARY KEY,
    band_id          SMALLINT      NOT NULL REFERENCES spectral_bands (band_id),
    region_id        INT           REFERENCES administrative_regions (region_id),
    data_stamp       TIMESTAMPTZ   NOT NULL,
    end_date         DATE          NOT NULL,
    history_from     DATE,
    last_obs_date    DATE,
    n_obs            INT           NOT NULL CHECK (n_obs >= 0),
    horizon          SMALLINT      NOT NULL CHECK (horizon BETWEEN 1 AND 30),
    model            VARCHAR(10)   CHECK (model IN ('naive', 'ses', 'holt', 'clim', 'clim_ar1')),
    confidence       VARCHAR(6)    CHECK (confidence IN ('rendah', 'sedang', 'tinggi')),
    backtest_origins SMALLINT,
    mae              NUMERIC(14,6),
    mae_naive        NUMERIC(14,6),
    skill            NUMERIC(8,4),
    notes            TEXT,
    duration_ms      INT           NOT NULL DEFAULT 0,
    computed_at      TIMESTAMPTZ   NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_band_forecasts_stamp ON band_forecasts (band_id, COALESCE(region_id, 0), data_stamp);
CREATE INDEX IF NOT EXISTS idx_band_forecasts_latest ON band_forecasts (band_id, region_id, computed_at DESC);
COMMENT ON TABLE  band_forecasts IS 'Forecast 15 hari per deret (band × AOI/kecamatan), dihitung saat data baru masuk dari seluruh riwayat region_observations (M62). Riwayat 365 hari disimpan supaya model yang dipakai pada tanggal tertentu bisa dilacak.';
COMMENT ON COLUMN band_forecasts.forecast_id      IS 'PK surrogate.';
COMMENT ON COLUMN band_forecasts.band_id          IS 'FK -> spectral_bands: band yang diramal.';
COMMENT ON COLUMN band_forecasts.region_id        IS 'FK -> administrative_regions (kecamatan). NULL = rerata AOI.';
COMMENT ON COLUMN band_forecasts.data_stamp       IS 'Cap data band saat dihitung: max(region_observations.computed_at) band itu dan max(live_scenes.updated_at). Forecast basi bila cap sekarang berbeda.';
COMMENT ON COLUMN band_forecasts.end_date         IS 'Data dipakai s.d. tanggal ini (hari UTC saat dihitung).';
COMMENT ON COLUMN band_forecasts.history_from     IS 'Tanggal observasi pertama yang dipakai.';
COMMENT ON COLUMN band_forecasts.last_obs_date    IS 'Tanggal observasi terakhir; titik forecast mulai sehari sesudahnya.';
COMMENT ON COLUMN band_forecasts.n_obs            IS 'Jumlah hari berdata yang dipakai.';
COMMENT ON COLUMN band_forecasts.horizon          IS 'Jumlah hari yang diramal (15).';
COMMENT ON COLUMN band_forecasts.model            IS 'Model terpilih backtest: naive | ses | holt | clim | clim_ar1. NULL bila data < 10 titik.';
COMMENT ON COLUMN band_forecasts.confidence       IS 'Keyakinan dari skill backtest: rendah | sedang | tinggi.';
COMMENT ON COLUMN band_forecasts.backtest_origins IS 'Jumlah titik asal backtest yang dinilai (maks. 12). NULL bila riwayat terlalu pendek.';
COMMENT ON COLUMN band_forecasts.mae              IS 'MAE backtest model terpilih (satuan band).';
COMMENT ON COLUMN band_forecasts.mae_naive        IS 'MAE backtest model naive (pembanding).';
COMMENT ON COLUMN band_forecasts.skill            IS 'Skill = 1 - mae / mae_naive.';
COMMENT ON COLUMN band_forecasts.notes            IS 'Catatan untuk pengguna (celah data, tidak mengalahkan naive), satu per baris.';
COMMENT ON COLUMN band_forecasts.duration_ms      IS 'Lama perhitungan deret ini (ms).';
COMMENT ON COLUMN band_forecasts.computed_at      IS 'Waktu dihitung.';

CREATE TABLE IF NOT EXISTS band_forecast_points (
    forecast_id BIGINT        NOT NULL REFERENCES band_forecasts (forecast_id) ON DELETE CASCADE,
    step        SMALLINT      NOT NULL CHECK (step BETWEEN 1 AND 30),
    target_date DATE          NOT NULL,
    mean        NUMERIC(12,4) NOT NULL,
    lo          NUMERIC(12,4) NOT NULL,
    hi          NUMERIC(12,4) NOT NULL,
    PRIMARY KEY (forecast_id, step),
    CHECK (lo <= mean AND mean <= hi)
);
COMMENT ON TABLE  band_forecast_points IS 'Titik forecast harian satu band_forecasts (M62).';
COMMENT ON COLUMN band_forecast_points.forecast_id IS 'FK -> band_forecasts.';
COMMENT ON COLUMN band_forecast_points.step        IS 'Langkah ke-k (1 = sehari sesudah last_obs_date).';
COMMENT ON COLUMN band_forecast_points.target_date IS 'Tanggal yang diramal.';
COMMENT ON COLUMN band_forecast_points.mean        IS 'Nilai forecast (satuan band).';
COMMENT ON COLUMN band_forecast_points.lo          IS 'Batas bawah pita 80%.';
COMMENT ON COLUMN band_forecast_points.hi          IS 'Batas atas pita 80%.';

CREATE TABLE IF NOT EXISTS band_forecast_scores (
    forecast_id BIGINT        NOT NULL REFERENCES band_forecasts (forecast_id) ON DELETE CASCADE,
    model       VARCHAR(10)   NOT NULL CHECK (model IN ('naive', 'ses', 'holt', 'clim', 'clim_ar1')),
    mae         NUMERIC(14,6) NOT NULL,
    PRIMARY KEY (forecast_id, model)
);
COMMENT ON TABLE  band_forecast_scores IS 'MAE backtest setiap model kandidat untuk satu band_forecasts (M62): bukti kenapa model terpilih menang.';
COMMENT ON COLUMN band_forecast_scores.forecast_id IS 'FK -> band_forecasts.';
COMMENT ON COLUMN band_forecast_scores.model       IS 'Model kandidat.';
COMMENT ON COLUMN band_forecast_scores.mae         IS 'MAE backtest model itu (satuan band).';

-- Forecast tersimpan (M62): dibaca halaman Forecast (ANALYST+), ditulis ETL.
GRANT SELECT ON band_forecasts, band_forecast_points, band_forecast_scores TO monitor_analyst;
GRANT SELECT, INSERT, DELETE ON band_forecasts, band_forecast_points, band_forecast_scores TO monitor_etl;
GRANT USAGE ON SEQUENCE band_forecasts_forecast_id_seq TO monitor_etl;

COMMIT;
