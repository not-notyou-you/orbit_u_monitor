window.SKRIPSI_DATA = {
 "generated": "2026-10-09 14:37",
 "tables": {
  "administrative_regions": {
   "desc": "Batas wilayah resmi COD-AB Indonesia (BPS via OCHA/HDX): Kabupaten Lebak (level 2) dan kecamatannya (level 3). AOI GMLS = kecamatan in_aoi (M8).",
   "cols": [
    {
     "n": "region_id",
     "t": "integer",
     "nn": true,
     "d": "nextval('administrative_regions_region_id_seq'::regclass)",
     "k": "PK",
     "ds": "PK surrogate."
    },
    {
     "n": "parent_region_id",
     "t": "integer",
     "nn": false,
     "d": "",
     "k": "FK→administrative_regions",
     "ds": "FK -> administrative_regions: kabupaten induk. NULL untuk level 2."
    },
    {
     "n": "pcode",
     "t": "character varying(20)",
     "nn": true,
     "d": "",
     "k": "UNIQUE",
     "ds": "Alternate key: P-code COD-AB, mis. ID3602xxx."
    },
    {
     "n": "region_name",
     "t": "character varying(100)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Nama wilayah (ADM2_EN/ADM3_EN), mis. Bayah."
    },
    {
     "n": "admin_level",
     "t": "smallint",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "2 = kabupaten, 3 = kecamatan."
    },
    {
     "n": "in_aoi",
     "t": "boolean",
     "nn": true,
     "d": "false",
     "k": "",
     "ds": "true = kecamatan termasuk cakupan GMLS (hanya level 3). Diubah ADMIN."
    },
    {
     "n": "geom",
     "t": "geometry(MultiPolygon,4326)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Poligon batas wilayah, MultiPolygon EPSG:4326 (ST_Multi(ST_MakeValid(...)))."
    },
    {
     "n": "area_km2",
     "t": "numeric(10,2)",
     "nn": false,
     "d": "GENERATED",
     "k": "",
     "ds": "Luas geodesik (km2), kolom GENERATED dari geom (redundansi terkendali, §9)."
    },
    {
     "n": "source_dataset",
     "t": "character varying(100)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Asal data batas, mis. \"COD-AB IDN 2020 (BPS/OCHA)\"."
    }
   ],
   "cons": [
    {
     "n": "administrative_regions_admin_level_check",
     "type": "CHECK",
     "def": "CHECK ((admin_level = ANY (ARRAY[2, 3])))"
    },
    {
     "n": "administrative_regions_check",
     "type": "CHECK",
     "def": "CHECK (((admin_level = 2) OR (parent_region_id IS NOT NULL)))"
    },
    {
     "n": "administrative_regions_check1",
     "type": "CHECK",
     "def": "CHECK (((NOT in_aoi) OR (admin_level = 3)))"
    },
    {
     "n": "administrative_regions_parent_region_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (parent_region_id) REFERENCES administrative_regions(region_id)"
    },
    {
     "n": "administrative_regions_pkey",
     "type": "PK",
     "def": "PRIMARY KEY (region_id)"
    },
    {
     "n": "administrative_regions_pcode_key",
     "type": "UNIQUE",
     "def": "UNIQUE (pcode)"
    }
   ]
  },
  "alert_events": {
   "desc": "Alert hujan per aturan per kecamatan per hari. observed_value/threshold_value/severity adalah salinan historis (§5.2).",
   "cols": [
    {
     "n": "alert_id",
     "t": "bigint",
     "nn": true,
     "d": "nextval('alert_events_alert_id_seq'::regclass)",
     "k": "PK",
     "ds": "PK surrogate."
    },
    {
     "n": "rule_id",
     "t": "integer",
     "nn": true,
     "d": "",
     "k": "FK→alert_rules, UNIQUE",
     "ds": "FK -> alert_rules yang terpicu."
    },
    {
     "n": "region_id",
     "t": "integer",
     "nn": true,
     "d": "",
     "k": "FK→administrative_regions, UNIQUE",
     "ds": "FK -> administrative_regions (kecamatan)."
    },
    {
     "n": "obs_id",
     "t": "bigint",
     "nn": true,
     "d": "",
     "k": "FK→region_observations",
     "ds": "FK -> region_observations: nilai pemicu."
    },
    {
     "n": "observation_date",
     "t": "date",
     "nn": true,
     "d": "",
     "k": "UNIQUE",
     "ds": "Tanggal pengamatan pemicu (hari UTC)."
    },
    {
     "n": "observed_value",
     "t": "numeric(10,4)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Salinan nilai saat terpicu (mm)."
    },
    {
     "n": "threshold_value",
     "t": "numeric(8,2)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Salinan ambang saat terpicu (mm)."
    },
    {
     "n": "severity",
     "t": "character varying(10)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Salinan severity aturan: INFO \\"
    },
    {
     "n": "triggered_at",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "now()",
     "k": "",
     "ds": "Waktu alert dibuat job."
    },
    {
     "n": "acknowledged_by",
     "t": "integer",
     "nn": false,
     "d": "",
     "k": "FK→users",
     "ds": "FK -> users: ANALYST/ADMIN yang menandai sudah dibaca."
    },
    {
     "n": "acknowledged_at",
     "t": "timestamp with time zone",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Waktu ditandai sudah dibaca. Berpasangan dengan acknowledged_by."
    },
    {
     "n": "ack_note",
     "t": "character varying(500)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Catatan opsional saat acknowledge."
    }
   ],
   "cons": [
    {
     "n": "alert_events_severity_check",
     "type": "CHECK",
     "def": "CHECK (((severity)::text = ANY (ARRAY[('INFO'::character varying)::text, ('WARNING'::character varying)::text, ('CRITICAL'::character varying)::text])))"
    },
    {
     "n": "chk_alert_ack_pair",
     "type": "CHECK",
     "def": "CHECK (((acknowledged_by IS NULL) = (acknowledged_at IS NULL)))"
    },
    {
     "n": "alert_events_acknowledged_by_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (acknowledged_by) REFERENCES users(user_id)"
    },
    {
     "n": "alert_events_obs_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (obs_id) REFERENCES region_observations(obs_id)"
    },
    {
     "n": "alert_events_region_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (region_id) REFERENCES administrative_regions(region_id)"
    },
    {
     "n": "alert_events_rule_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (rule_id) REFERENCES alert_rules(rule_id)"
    },
    {
     "n": "alert_events_pkey",
     "type": "PK",
     "def": "PRIMARY KEY (alert_id)"
    },
    {
     "n": "uq_alert_rule_region_date",
     "type": "UNIQUE",
     "def": "UNIQUE (rule_id, region_id, observation_date)"
    }
   ]
  },
  "alert_rules": {
   "desc": "Aturan alert hujan per jenis bencana (ambang BMKG; longsor nonaktif sampai ambang literatur diisi).",
   "cols": [
    {
     "n": "rule_id",
     "t": "integer",
     "nn": true,
     "d": "nextval('alert_rules_rule_id_seq'::regclass)",
     "k": "PK",
     "ds": "PK surrogate."
    },
    {
     "n": "rule_code",
     "t": "character varying(40)",
     "nn": true,
     "d": "",
     "k": "UNIQUE",
     "ds": "Alternate key, mis. FLOOD_RAIN24_HEAVY."
    },
    {
     "n": "disaster_type_id",
     "t": "smallint",
     "nn": true,
     "d": "",
     "k": "FK→disaster_types",
     "ds": "FK -> disaster_types."
    },
    {
     "n": "band_id",
     "t": "smallint",
     "nn": true,
     "d": "",
     "k": "FK→spectral_bands",
     "ds": "FK -> spectral_bands: band yang dibandingkan, mis. RAIN_24H."
    },
    {
     "n": "comparator",
     "t": "character varying(2)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Operator pembanding nilai terhadap ambang: >= \\"
    },
    {
     "n": "threshold_value",
     "t": "numeric(8,2)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Ambang dalam satuan band (mm untuk hujan). Wajib terisi bila is_active (K7)."
    },
    {
     "n": "severity",
     "t": "character varying(10)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "INFO \\"
    },
    {
     "n": "reference_source",
     "t": "character varying(150)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Rujukan ambang, mis. \"BMKG (hujan lebat)\"."
    },
    {
     "n": "is_active",
     "t": "boolean",
     "nn": true,
     "d": "true",
     "k": "",
     "ds": "false = aturan tidak dievaluasi job hidromet."
    },
    {
     "n": "updated_by",
     "t": "integer",
     "nn": false,
     "d": "",
     "k": "FK→users",
     "ds": "FK -> users: ADMIN yang terakhir mengubah."
    },
    {
     "n": "updated_at",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "now()",
     "k": "",
     "ds": "Waktu baris terakhir diubah (trigger)."
    }
   ],
   "cons": [
    {
     "n": "alert_rules_comparator_check",
     "type": "CHECK",
     "def": "CHECK (((comparator)::text = ANY (ARRAY[('>='::character varying)::text, ('>'::character varying)::text, ('<='::character varying)::text, ('<'::character varying)::text])))"
    },
    {
     "n": "alert_rules_severity_check",
     "type": "CHECK",
     "def": "CHECK (((severity)::text = ANY (ARRAY[('INFO'::character varying)::text, ('WARNING'::character varying)::text, ('CRITICAL'::character varying)::text])))"
    },
    {
     "n": "chk_rule_active_needs_threshold",
     "type": "CHECK",
     "def": "CHECK (((NOT is_active) OR (threshold_value IS NOT NULL)))"
    },
    {
     "n": "alert_rules_band_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (band_id) REFERENCES spectral_bands(band_id)"
    },
    {
     "n": "alert_rules_disaster_type_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (disaster_type_id) REFERENCES disaster_types(disaster_type_id)"
    },
    {
     "n": "alert_rules_updated_by_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (updated_by) REFERENCES users(user_id)"
    },
    {
     "n": "alert_rules_pkey",
     "type": "PK",
     "def": "PRIMARY KEY (rule_id)"
    },
    {
     "n": "alert_rules_rule_code_key",
     "type": "UNIQUE",
     "def": "UNIQUE (rule_code)"
    }
   ]
  },
  "api_tokens": {
   "desc": "Token API pribadi untuk skrip/sistem lain (M33). Hanya hash yang disimpan; token utuh ditampilkan sekali.",
   "cols": [
    {
     "n": "token_id",
     "t": "integer",
     "nn": true,
     "d": "nextval('api_tokens_token_id_seq'::regclass)",
     "k": "PK",
     "ds": "PK surrogate."
    },
    {
     "n": "user_id",
     "t": "integer",
     "nn": true,
     "d": "",
     "k": "FK→users",
     "ds": "FK -> users pemilik; role token = role pemilik saat dipakai."
    },
    {
     "n": "token_name",
     "t": "character varying(60)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Nama token, mis. \"skrip training\"."
    },
    {
     "n": "token_prefix",
     "t": "character(8)",
     "nn": true,
     "d": "",
     "k": "UNIQUE",
     "ds": "Awalan token untuk identifikasi, mis. trn_4f2a (unik)."
    },
    {
     "n": "token_hash",
     "t": "character(64)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "SHA-256 token (64 hex)."
    },
    {
     "n": "scopes",
     "t": "character varying(20)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "READ \\"
    },
    {
     "n": "expires_at",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Kedaluwarsa, maksimal 180 hari sejak dibuat."
    },
    {
     "n": "last_used_at",
     "t": "timestamp with time zone",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Waktu terakhir dipakai."
    },
    {
     "n": "revoked_at",
     "t": "timestamp with time zone",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Waktu dicabut; NULL = aktif."
    },
    {
     "n": "created_at",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "now()",
     "k": "",
     "ds": "Waktu token dibuat."
    }
   ],
   "cons": [
    {
     "n": "api_tokens_scopes_check",
     "type": "CHECK",
     "def": "CHECK (((scopes)::text = ANY (ARRAY[('READ'::character varying)::text, ('READ_DOWNLOAD'::character varying)::text])))"
    },
    {
     "n": "chk_token_max_lifetime",
     "type": "CHECK",
     "def": "CHECK ((expires_at <= (created_at + '180 days'::interval)))"
    },
    {
     "n": "api_tokens_user_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (user_id) REFERENCES users(user_id)"
    },
    {
     "n": "api_tokens_pkey",
     "type": "PK",
     "def": "PRIMARY KEY (token_id)"
    },
    {
     "n": "api_tokens_token_prefix_key",
     "type": "UNIQUE",
     "def": "UNIQUE (token_prefix)"
    }
   ]
  },
  "app_settings": {
   "desc": "Pengaturan key-value yang boleh diubah ADMIN tanpa restart (PIPELINE.md §11).",
   "cols": [
    {
     "n": "setting_key",
     "t": "character varying(50)",
     "nn": true,
     "d": "",
     "k": "PK",
     "ds": "PK: nama kunci bertitik, mis. live.max_areas."
    },
    {
     "n": "setting_value",
     "t": "jsonb",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Nilai JSON, mis. 5, -20, \"Asia/Jakarta\"."
    },
    {
     "n": "description",
     "t": "text",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Penjelasan arti dan satuan nilai."
    },
    {
     "n": "updated_by",
     "t": "integer",
     "nn": false,
     "d": "",
     "k": "FK→users",
     "ds": "FK -> users: ADMIN yang terakhir mengubah."
    },
    {
     "n": "updated_at",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "now()",
     "k": "",
     "ds": "Waktu baris terakhir diubah (trigger)."
    }
   ],
   "cons": [
    {
     "n": "app_settings_updated_by_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (updated_by) REFERENCES users(user_id)"
    },
    {
     "n": "app_settings_pkey",
     "type": "PK",
     "def": "PRIMARY KEY (setting_key)"
    }
   ]
  },
  "audit_log": {
   "desc": "Jejak perubahan data yang diisi trigger audit_row (append-only, M15). Trigger dipasang di monitor_security.sql.",
   "cols": [
    {
     "n": "audit_id",
     "t": "bigint",
     "nn": true,
     "d": "nextval('audit_log_audit_id_seq'::regclass)",
     "k": "PK",
     "ds": "PK surrogate."
    },
    {
     "n": "table_name",
     "t": "character varying(63)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Nama tabel yang berubah."
    },
    {
     "n": "row_pk",
     "t": "text",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Nilai PK baris yang berubah (teks)."
    },
    {
     "n": "operation",
     "t": "character(1)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "I (INSERT) \\"
    },
    {
     "n": "old_data",
     "t": "jsonb",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Baris sebelum perubahan (JSONB; password_hash/token_hash disensor)."
    },
    {
     "n": "new_data",
     "t": "jsonb",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Baris sesudah perubahan (JSONB; password_hash/token_hash disensor)."
    },
    {
     "n": "changed_columns",
     "t": "text[]",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Kolom yang berubah (untuk U)."
    },
    {
     "n": "app_user_id",
     "t": "integer",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "users.user_id dari current_setting('app.user_id'); NULL bila lewat psql."
    },
    {
     "n": "db_user",
     "t": "name",
     "nn": true,
     "d": "CURRENT_USER",
     "k": "",
     "ds": "Role PostgreSQL yang menjalankan perubahan."
    },
    {
     "n": "changed_at",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "now()",
     "k": "",
     "ds": "Waktu perubahan."
    }
   ],
   "cons": [
    {
     "n": "audit_log_operation_check",
     "type": "CHECK",
     "def": "CHECK ((operation = ANY (ARRAY['I'::bpchar, 'U'::bpchar, 'D'::bpchar])))"
    },
    {
     "n": "audit_log_pkey",
     "type": "PK",
     "def": "PRIMARY KEY (audit_id)"
    }
   ]
  },
  "band_forecast_points": {
   "desc": "Titik forecast harian satu band_forecasts (M62).",
   "cols": [
    {
     "n": "forecast_id",
     "t": "bigint",
     "nn": true,
     "d": "",
     "k": "FK→band_forecasts, PK",
     "ds": "FK -> band_forecasts."
    },
    {
     "n": "step",
     "t": "smallint",
     "nn": true,
     "d": "",
     "k": "PK",
     "ds": "Langkah ke-k (1 = sehari sesudah last_obs_date)."
    },
    {
     "n": "target_date",
     "t": "date",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Tanggal yang diramal."
    },
    {
     "n": "mean",
     "t": "numeric(12,4)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Nilai forecast (satuan band)."
    },
    {
     "n": "lo",
     "t": "numeric(12,4)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Batas bawah pita 80%."
    },
    {
     "n": "hi",
     "t": "numeric(12,4)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Batas atas pita 80%."
    }
   ],
   "cons": [
    {
     "n": "band_forecast_points_check",
     "type": "CHECK",
     "def": "CHECK (((lo <= mean) AND (mean <= hi)))"
    },
    {
     "n": "band_forecast_points_step_check",
     "type": "CHECK",
     "def": "CHECK (((step >= 1) AND (step <= 30)))"
    },
    {
     "n": "band_forecast_points_forecast_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (forecast_id) REFERENCES band_forecasts(forecast_id) ON DELETE CASCADE"
    },
    {
     "n": "band_forecast_points_pkey",
     "type": "PK",
     "def": "PRIMARY KEY (forecast_id, step)"
    }
   ]
  },
  "band_forecast_scores": {
   "desc": "MAE backtest setiap model kandidat untuk satu band_forecasts (M62): bukti kenapa model terpilih menang.",
   "cols": [
    {
     "n": "forecast_id",
     "t": "bigint",
     "nn": true,
     "d": "",
     "k": "FK→band_forecasts, PK",
     "ds": "FK -> band_forecasts."
    },
    {
     "n": "model",
     "t": "character varying(10)",
     "nn": true,
     "d": "",
     "k": "PK",
     "ds": "Model kandidat."
    },
    {
     "n": "mae",
     "t": "numeric(14,6)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "MAE backtest model itu (satuan band)."
    }
   ],
   "cons": [
    {
     "n": "band_forecast_scores_model_check",
     "type": "CHECK",
     "def": "CHECK (((model)::text = ANY ((ARRAY['naive'::character varying, 'ses'::character varying, 'holt'::character varying, 'clim'::character varying, 'clim_ar1'::character varying])::text[])))"
    },
    {
     "n": "band_forecast_scores_forecast_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (forecast_id) REFERENCES band_forecasts(forecast_id) ON DELETE CASCADE"
    },
    {
     "n": "band_forecast_scores_pkey",
     "type": "PK",
     "def": "PRIMARY KEY (forecast_id, model)"
    }
   ]
  },
  "band_forecasts": {
   "desc": "Forecast 15 hari per deret (band × AOI/kecamatan), dihitung saat data baru masuk dari seluruh riwayat region_observations (M62). Riwayat 365 hari disimpan supaya model yang dipakai pada tanggal tertentu bisa dilacak.",
   "cols": [
    {
     "n": "forecast_id",
     "t": "bigint",
     "nn": true,
     "d": "nextval('band_forecasts_forecast_id_seq'::regclass)",
     "k": "PK",
     "ds": "PK surrogate."
    },
    {
     "n": "band_id",
     "t": "smallint",
     "nn": true,
     "d": "",
     "k": "FK→spectral_bands",
     "ds": "FK -> spectral_bands: band yang diramal."
    },
    {
     "n": "region_id",
     "t": "integer",
     "nn": false,
     "d": "",
     "k": "FK→administrative_regions",
     "ds": "FK -> administrative_regions (kecamatan). NULL = rerata AOI."
    },
    {
     "n": "data_stamp",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Cap data band saat dihitung: max(region_observations.computed_at) band itu dan max(live_scenes.updated_at). Forecast basi bila cap sekarang berbeda."
    },
    {
     "n": "end_date",
     "t": "date",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Data dipakai s.d. tanggal ini (hari UTC saat dihitung)."
    },
    {
     "n": "history_from",
     "t": "date",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Tanggal observasi pertama yang dipakai."
    },
    {
     "n": "last_obs_date",
     "t": "date",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Tanggal observasi terakhir; titik forecast mulai sehari sesudahnya."
    },
    {
     "n": "n_obs",
     "t": "integer",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Jumlah hari berdata yang dipakai."
    },
    {
     "n": "horizon",
     "t": "smallint",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Jumlah hari yang diramal (15)."
    },
    {
     "n": "model",
     "t": "character varying(10)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Model terpilih backtest: naive \\"
    },
    {
     "n": "confidence",
     "t": "character varying(6)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Keyakinan dari skill backtest: rendah \\"
    },
    {
     "n": "backtest_origins",
     "t": "smallint",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Jumlah titik asal backtest yang dinilai (maks. 12). NULL bila riwayat terlalu pendek."
    },
    {
     "n": "mae",
     "t": "numeric(14,6)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "MAE backtest model terpilih (satuan band)."
    },
    {
     "n": "mae_naive",
     "t": "numeric(14,6)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "MAE backtest model naive (pembanding)."
    },
    {
     "n": "skill",
     "t": "numeric(8,4)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Skill = 1 - mae / mae_naive."
    },
    {
     "n": "notes",
     "t": "text",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Catatan untuk pengguna (celah data, tidak mengalahkan naive), satu per baris."
    },
    {
     "n": "duration_ms",
     "t": "integer",
     "nn": true,
     "d": "0",
     "k": "",
     "ds": "Lama perhitungan deret ini (ms)."
    },
    {
     "n": "computed_at",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "now()",
     "k": "",
     "ds": "Waktu dihitung."
    }
   ],
   "cons": [
    {
     "n": "band_forecasts_confidence_check",
     "type": "CHECK",
     "def": "CHECK (((confidence)::text = ANY ((ARRAY['rendah'::character varying, 'sedang'::character varying, 'tinggi'::character varying])::text[])))"
    },
    {
     "n": "band_forecasts_horizon_check",
     "type": "CHECK",
     "def": "CHECK (((horizon >= 1) AND (horizon <= 30)))"
    },
    {
     "n": "band_forecasts_model_check",
     "type": "CHECK",
     "def": "CHECK (((model)::text = ANY ((ARRAY['naive'::character varying, 'ses'::character varying, 'holt'::character varying, 'clim'::character varying, 'clim_ar1'::character varying])::text[])))"
    },
    {
     "n": "band_forecasts_n_obs_check",
     "type": "CHECK",
     "def": "CHECK ((n_obs >= 0))"
    },
    {
     "n": "band_forecasts_band_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (band_id) REFERENCES spectral_bands(band_id)"
    },
    {
     "n": "band_forecasts_region_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (region_id) REFERENCES administrative_regions(region_id)"
    },
    {
     "n": "band_forecasts_pkey",
     "type": "PK",
     "def": "PRIMARY KEY (forecast_id)"
    }
   ]
  },
  "cleanup_operations": {
   "desc": "Progres penghapusan berkas per dataset (cleanup tier akhir job atau hapus dataset). Sengaja tanpa FK ke datasets agar progres tetap terbaca setelah dataset dihapus.",
   "cols": [
    {
     "n": "id",
     "t": "bigint",
     "nn": true,
     "d": "nextval('cleanup_operations_id_seq'::regclass)",
     "k": "PK",
     "ds": "PK surrogate."
    },
    {
     "n": "dataset_id",
     "t": "integer",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Dataset yang dibersihkan (tanpa FK, lihat komentar tabel)."
    },
    {
     "n": "job_id",
     "t": "bigint",
     "nn": false,
     "d": "",
     "k": "FK→dataset_jobs",
     "ds": "FK -> dataset_jobs yang memicu cleanup."
    },
    {
     "n": "operation_type",
     "t": "character varying(20)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "TIER_CLEANUP \\"
    },
    {
     "n": "status",
     "t": "character varying(20)",
     "nn": true,
     "d": "'PENDING'::character varying",
     "k": "",
     "ds": "PENDING \\"
    },
    {
     "n": "total_files",
     "t": "integer",
     "nn": true,
     "d": "0",
     "k": "",
     "ds": "Jumlah berkas yang akan dihapus."
    },
    {
     "n": "deleted_count",
     "t": "integer",
     "nn": true,
     "d": "0",
     "k": "",
     "ds": "Jumlah berkas yang sudah dihapus."
    },
    {
     "n": "freed_bytes",
     "t": "bigint",
     "nn": true,
     "d": "0",
     "k": "",
     "ds": "Ruang disk yang dibebaskan (byte)."
    },
    {
     "n": "error_log",
     "t": "text",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Galat selama penghapusan."
    },
    {
     "n": "created_at",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "now()",
     "k": "",
     "ds": "Waktu baris dibuat."
    },
    {
     "n": "started_at",
     "t": "timestamp with time zone",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Waktu mulai."
    },
    {
     "n": "completed_at",
     "t": "timestamp with time zone",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Waktu selesai."
    }
   ],
   "cons": [
    {
     "n": "cleanup_operations_operation_type_check",
     "type": "CHECK",
     "def": "CHECK (((operation_type)::text = ANY (ARRAY[('TIER_CLEANUP'::character varying)::text, ('FULL_DELETE'::character varying)::text])))"
    },
    {
     "n": "cleanup_operations_status_check",
     "type": "CHECK",
     "def": "CHECK (((status)::text = ANY (ARRAY[('PENDING'::character varying)::text, ('IN_PROGRESS'::character varying)::text, ('COMPLETED'::character varying)::text, ('FAILED'::character varying)::text])))"
    },
    {
     "n": "cleanup_operations_job_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (job_id) REFERENCES dataset_jobs(job_id) ON DELETE SET NULL"
    },
    {
     "n": "cleanup_operations_pkey",
     "type": "PK",
     "def": "PRIMARY KEY (id)"
    }
   ]
  },
  "data_lineage": {
   "desc": "Graf asiklik (DAG) transformasi produk: induk -> anak dengan checksum input/output (RM2).",
   "cols": [
    {
     "n": "lineage_id",
     "t": "bigint",
     "nn": true,
     "d": "nextval('data_lineage_lineage_id_seq'::regclass)",
     "k": "PK",
     "ds": "PK surrogate."
    },
    {
     "n": "parent_product_id",
     "t": "bigint",
     "nn": true,
     "d": "",
     "k": "FK→data_products, UNIQUE",
     "ds": "FK -> data_products: produk input."
    },
    {
     "n": "child_product_id",
     "t": "bigint",
     "nn": true,
     "d": "",
     "k": "FK→data_products, UNIQUE",
     "ds": "FK -> data_products: produk output."
    },
    {
     "n": "transformation_type",
     "t": "character varying(50)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Jenis transformasi, mis. CROP, LEE_FILTER, GOLD_EXPORT, FUSION."
    },
    {
     "n": "stage_id",
     "t": "integer",
     "nn": true,
     "d": "",
     "k": "FK→processing_stages",
     "ds": "FK -> processing_stages."
    },
    {
     "n": "job_id",
     "t": "bigint",
     "nn": true,
     "d": "",
     "k": "FK→processing_jobs",
     "ds": "FK -> processing_jobs: eksekusi yang melakukan transformasi."
    },
    {
     "n": "transformation_params",
     "t": "jsonb",
     "nn": true,
     "d": "'{}'::jsonb",
     "k": "",
     "ds": "Parameter transformasi (JSONB): bbox crop, window Lee, kompresi COG."
    },
    {
     "n": "input_checksum",
     "t": "character varying(64)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "SHA-256 induk saat transformasi."
    },
    {
     "n": "output_checksum",
     "t": "character varying(64)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "SHA-256 anak setelah transformasi."
    },
    {
     "n": "created_at",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "now()",
     "k": "",
     "ds": "Waktu baris dibuat."
    }
   ],
   "cons": [
    {
     "n": "chk_lineage_no_self_ref",
     "type": "CHECK",
     "def": "CHECK ((parent_product_id <> child_product_id))"
    },
    {
     "n": "data_lineage_child_product_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (child_product_id) REFERENCES data_products(product_id) ON DELETE CASCADE"
    },
    {
     "n": "data_lineage_job_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (job_id) REFERENCES processing_jobs(job_id) ON DELETE RESTRICT"
    },
    {
     "n": "data_lineage_parent_product_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (parent_product_id) REFERENCES data_products(product_id) ON DELETE CASCADE"
    },
    {
     "n": "data_lineage_stage_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (stage_id) REFERENCES processing_stages(stage_id) ON DELETE RESTRICT"
    },
    {
     "n": "data_lineage_pkey",
     "type": "PK",
     "def": "PRIMARY KEY (lineage_id)"
    },
    {
     "n": "uq_lineage_parent_child",
     "type": "UNIQUE",
     "def": "UNIQUE (parent_product_id, child_product_id)"
    }
   ]
  },
  "data_products": {
   "desc": "Registri setiap berkas keluaran pipeline (COG, TIFF, HDF5) dengan checksum SHA-256.",
   "cols": [
    {
     "n": "product_id",
     "t": "bigint",
     "nn": true,
     "d": "nextval('data_products_product_id_seq'::regclass)",
     "k": "PK",
     "ds": "PK surrogate."
    },
    {
     "n": "product_uuid",
     "t": "uuid",
     "nn": true,
     "d": "gen_random_uuid()",
     "k": "UNIQUE",
     "ds": "UUID stabil untuk referensi eksternal."
    },
    {
     "n": "scene_id",
     "t": "integer",
     "nn": false,
     "d": "",
     "k": "FK→satellite_scenes",
     "ds": "FK -> satellite_scenes: scene S1 asal. Terisi hanya untuk source SENTINEL1 (chk_dprods_single_origin)."
    },
    {
     "n": "nasa_scene_id",
     "t": "bigint",
     "nn": false,
     "d": "",
     "k": "FK→nasa_scenes",
     "ds": "FK -> nasa_scenes: granule MODIS/GPM asal. Terisi hanya untuk source MODIS/GPM; FUSION keduanya NULL (M30)."
    },
    {
     "n": "job_id",
     "t": "bigint",
     "nn": true,
     "d": "",
     "k": "FK→processing_jobs",
     "ds": "FK -> processing_jobs: eksekusi tahap yang menulis berkas ini."
    },
    {
     "n": "dataset_id",
     "t": "integer",
     "nn": false,
     "d": "",
     "k": "FK→datasets",
     "ds": "FK -> datasets: dataset pemilik berkas."
    },
    {
     "n": "product_tier",
     "t": "product_tier_enum",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Posisi di lineage (D14): RAW \\"
    },
    {
     "n": "source",
     "t": "character varying(20)",
     "nn": true,
     "d": "'SENTINEL1'::character varying",
     "k": "FK→satellite_sources",
     "ds": "FK -> satellite_sources.source_code: SENTINEL1 \\"
    },
    {
     "n": "processing_level",
     "t": "character varying(20)",
     "nn": false,
     "d": "'PROCESSED'::character varying",
     "k": "",
     "ds": "Level konfigurasi yang menghasilkan berkas: RAW \\"
    },
    {
     "n": "product_type",
     "t": "character varying(50)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Jenis artefak, mis. S1_COG, MODIS_FLOOD, GPM_RAINFALL, FUSION_H5."
    },
    {
     "n": "band_name",
     "t": "character varying(20)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Band/lapisan, mis. VV, NDVI, RAIN_24H, FUSION_PROCESSED."
    },
    {
     "n": "file_name",
     "t": "character varying(255)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Nama berkas."
    },
    {
     "n": "file_path",
     "t": "text",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Path berkas di filesystem data/ (raster tidak disimpan di DB)."
    },
    {
     "n": "file_size_mb",
     "t": "numeric(12,3)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Ukuran berkas (MB)."
    },
    {
     "n": "file_format",
     "t": "character varying(20)",
     "nn": true,
     "d": "'TIFF'::character varying",
     "k": "",
     "ds": "Format: TIFF \\"
    },
    {
     "n": "data_hash_sha256",
     "t": "character varying(64)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "SHA-256 isi berkas (64 hex) untuk lineage dan verifikasi arsip (RM2)."
    },
    {
     "n": "crs",
     "t": "character varying(50)",
     "nn": true,
     "d": "'EPSG:4326'::character varying",
     "k": "",
     "ds": "Sistem koordinat, mis. EPSG:4326."
    },
    {
     "n": "pixel_size_m",
     "t": "numeric(8,3)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Ukuran piksel (meter)."
    },
    {
     "n": "nodata_value",
     "t": "numeric",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Nilai NoData raster."
    },
    {
     "n": "rows",
     "t": "integer",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Jumlah baris piksel."
    },
    {
     "n": "cols",
     "t": "integer",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Jumlah kolom piksel."
    },
    {
     "n": "band_count",
     "t": "smallint",
     "nn": true,
     "d": "1",
     "k": "",
     "ds": "Jumlah band dalam berkas."
    },
    {
     "n": "storage_location",
     "t": "storage_location_enum",
     "nn": true,
     "d": "'LOCAL'::storage_location_enum",
     "k": "",
     "ds": "Lokasi penyimpanan, selalu LOCAL di Monitor."
    },
    {
     "n": "is_valid",
     "t": "boolean",
     "nn": true,
     "d": "true",
     "k": "",
     "ds": "false = berkas dinyatakan tidak sah/dihapus."
    },
    {
     "n": "is_latest",
     "t": "boolean",
     "nn": true,
     "d": "true",
     "k": "",
     "ds": "true = versi terbaru untuk kunci dedup (COALESCE(scene_id,0), COALESCE(nasa_scene_id,0), band, tier, dataset); FUSION didedup per file_path (K3)."
    },
    {
     "n": "created_at",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "now()",
     "k": "",
     "ds": "Waktu baris dibuat."
    },
    {
     "n": "updated_at",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "now()",
     "k": "",
     "ds": "Waktu baris terakhir diubah (trigger)."
    }
   ],
   "cons": [
    {
     "n": "chk_dprods_processing_level",
     "type": "CHECK",
     "def": "CHECK (((processing_level IS NULL) OR ((processing_level)::text = ANY (ARRAY[('RAW'::character varying)::text, ('PROCESSED'::character varying)::text]))))"
    },
    {
     "n": "chk_dprods_single_origin",
     "type": "CHECK",
     "def": "CHECK (((((source)::text = 'SENTINEL1'::text) AND (scene_id IS NOT NULL) AND (nasa_scene_id IS NULL)) OR (((source)::text = ANY (ARRAY[('MODIS'::character varying)::text, ('GPM'::character varying)::text])) AND (scene_id IS NULL) AND (nasa_scene_id IS NOT NULL)) OR (((source)::text = 'FUSION'::text) AND (scene_id IS NULL) AND (nasa_scene_id IS NULL))))"
    },
    {
     "n": "data_products_dataset_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (dataset_id) REFERENCES datasets(dataset_id) ON DELETE CASCADE"
    },
    {
     "n": "data_products_job_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (job_id) REFERENCES processing_jobs(job_id) ON DELETE RESTRICT"
    },
    {
     "n": "data_products_nasa_scene_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (nasa_scene_id) REFERENCES nasa_scenes(nasa_scene_id) ON DELETE CASCADE"
    },
    {
     "n": "data_products_scene_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (scene_id) REFERENCES satellite_scenes(scene_id) ON DELETE CASCADE"
    },
    {
     "n": "data_products_source_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (source) REFERENCES satellite_sources(source_code) ON UPDATE CASCADE"
    },
    {
     "n": "data_products_pkey",
     "type": "PK",
     "def": "PRIMARY KEY (product_id)"
    },
    {
     "n": "data_products_product_uuid_key",
     "type": "UNIQUE",
     "def": "UNIQUE (product_uuid)"
    }
   ]
  },
  "dataset_jobs": {
   "desc": "Satu eksekusi pekerjaan atas sebuah dataset (buat, backfill, siklus Live, hidromet harian).",
   "cols": [
    {
     "n": "job_id",
     "t": "bigint",
     "nn": true,
     "d": "nextval('dataset_jobs_job_id_seq'::regclass)",
     "k": "PK",
     "ds": "PK surrogate."
    },
    {
     "n": "job_uuid",
     "t": "uuid",
     "nn": true,
     "d": "gen_random_uuid()",
     "k": "UNIQUE",
     "ds": "UUID stabil untuk referensi eksternal."
    },
    {
     "n": "dataset_id",
     "t": "integer",
     "nn": true,
     "d": "",
     "k": "FK→datasets",
     "ds": "FK -> datasets."
    },
    {
     "n": "job_type",
     "t": "character varying(20)",
     "nn": true,
     "d": "'CREATE'::character varying",
     "k": "",
     "ds": "CREATE \\"
    },
    {
     "n": "status",
     "t": "character varying(20)",
     "nn": true,
     "d": "'QUEUED'::character varying",
     "k": "",
     "ds": "QUEUED, PREPARING, DOWNLOADING, PROCESSING, PAUSED, CLEANUP, COMPLETED, FAILED, CANCELLED, WAITING_UPSTREAM (hidromet: granule GPM hari itu belum terbit, dicoba lagi maks. 3 hari)."
    },
    {
     "n": "paused_at",
     "t": "timestamp with time zone",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Waktu job dijeda."
    },
    {
     "n": "paused_by",
     "t": "character varying(20)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Penjeda: user \\"
    },
    {
     "n": "pause_reason",
     "t": "text",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Alasan jeda."
    },
    {
     "n": "resumed_at",
     "t": "timestamp with time zone",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Waktu terakhir dilanjutkan."
    },
    {
     "n": "resume_count",
     "t": "smallint",
     "nn": true,
     "d": "0",
     "k": "",
     "ds": "Berapa kali job dilanjutkan."
    },
    {
     "n": "date_range_start",
     "t": "date",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Awal rentang tanggal yang dikerjakan job ini."
    },
    {
     "n": "date_range_end",
     "t": "date",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Akhir rentang tanggal yang dikerjakan job ini."
    },
    {
     "n": "total_scenes",
     "t": "integer",
     "nn": true,
     "d": "0",
     "k": "",
     "ds": "Jumlah unit (scene S1) yang dikerjakan."
    },
    {
     "n": "downloaded_count",
     "t": "integer",
     "nn": true,
     "d": "0",
     "k": "",
     "ds": "Unit yang selesai diunduh."
    },
    {
     "n": "processed_count",
     "t": "integer",
     "nn": true,
     "d": "0",
     "k": "",
     "ds": "Unit yang selesai diproses."
    },
    {
     "n": "failed_count",
     "t": "integer",
     "nn": true,
     "d": "0",
     "k": "",
     "ds": "Unit yang gagal."
    },
    {
     "n": "cleaned_count",
     "t": "integer",
     "nn": true,
     "d": "0",
     "k": "",
     "ds": "Unit yang selesai dibersihkan (tahap CLEANUP)."
    },
    {
     "n": "created_at",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "now()",
     "k": "",
     "ds": "Waktu job dibuat."
    },
    {
     "n": "started_at",
     "t": "timestamp with time zone",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Waktu job mulai berjalan."
    },
    {
     "n": "completed_at",
     "t": "timestamp with time zone",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Waktu job selesai (berhasil atau gagal)."
    }
   ],
   "cons": [
    {
     "n": "chk_dataset_job_status",
     "type": "CHECK",
     "def": "CHECK (((status)::text = ANY (ARRAY[('QUEUED'::character varying)::text, ('PREPARING'::character varying)::text, ('DOWNLOADING'::character varying)::text, ('PROCESSING'::character varying)::text, ('PAUSED'::character varying)::text, ('CLEANUP'::character varying)::text, ('COMPLETED'::character varying)::text, ('FAILED'::character varying)::text, ('CANCELLED'::character varying)::text, ('WAITING_UPSTREAM'::character varying)::text])))"
    },
    {
     "n": "chk_dataset_job_type",
     "type": "CHECK",
     "def": "CHECK (((job_type)::text = ANY (ARRAY[('CREATE'::character varying)::text, ('BACKFILL'::character varying)::text, ('LIVE_INGEST'::character varying)::text, ('HYDROMET_DAILY'::character varying)::text])))"
    },
    {
     "n": "dataset_jobs_dataset_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (dataset_id) REFERENCES datasets(dataset_id) ON DELETE CASCADE"
    },
    {
     "n": "dataset_jobs_pkey",
     "type": "PK",
     "def": "PRIMARY KEY (job_id)"
    },
    {
     "n": "dataset_jobs_job_uuid_key",
     "type": "UNIQUE",
     "def": "UNIQUE (job_uuid)"
    }
   ]
  },
  "dataset_source_config": {
   "desc": "Konfigurasi pemrosesan per (dataset, sumber). ETL membaca tabel ini untuk memutuskan sumber dan level yang dijalankan.",
   "cols": [
    {
     "n": "config_id",
     "t": "integer",
     "nn": true,
     "d": "nextval('dataset_source_config_config_id_seq'::regclass)",
     "k": "PK",
     "ds": "PK surrogate."
    },
    {
     "n": "dataset_id",
     "t": "integer",
     "nn": true,
     "d": "",
     "k": "FK→datasets, UNIQUE",
     "ds": "FK -> datasets."
    },
    {
     "n": "source_name",
     "t": "character varying(20)",
     "nn": true,
     "d": "",
     "k": "FK→satellite_sources, UNIQUE",
     "ds": "FK -> satellite_sources.source_code: SENTINEL1 \\"
    },
    {
     "n": "processing_levels",
     "t": "text[]",
     "nn": true,
     "d": "ARRAY['PROCESSED'::text]",
     "k": "",
     "ds": "Level yang diminta: {RAW}, {PROCESSED}, atau {RAW,PROCESSED} (TEXT[] <= 2 elemen, M32)."
    },
    {
     "n": "created_at",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "now()",
     "k": "",
     "ds": "Waktu baris dibuat."
    },
    {
     "n": "updated_at",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "now()",
     "k": "",
     "ds": "Waktu baris terakhir diubah (trigger)."
    }
   ],
   "cons": [
    {
     "n": "chk_source_config_levels_not_empty",
     "type": "CHECK",
     "def": "CHECK (((array_length(processing_levels, 1) IS NOT NULL) AND (array_length(processing_levels, 1) > 0)))"
    },
    {
     "n": "chk_source_config_levels_valid",
     "type": "CHECK",
     "def": "CHECK ((processing_levels <@ ARRAY['RAW'::text, 'PROCESSED'::text]))"
    },
    {
     "n": "chk_source_config_source_name",
     "type": "CHECK",
     "def": "CHECK (((source_name)::text = ANY (ARRAY[('SENTINEL1'::character varying)::text, ('MODIS'::character varying)::text, ('GPM'::character varying)::text])))"
    },
    {
     "n": "dataset_source_config_dataset_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (dataset_id) REFERENCES datasets(dataset_id) ON DELETE CASCADE"
    },
    {
     "n": "dataset_source_config_source_name_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (source_name) REFERENCES satellite_sources(source_code) ON UPDATE CASCADE"
    },
    {
     "n": "dataset_source_config_pkey",
     "type": "PK",
     "def": "PRIMARY KEY (config_id)"
    },
    {
     "n": "uq_source_config_dataset_source",
     "type": "UNIQUE",
     "def": "UNIQUE (dataset_id, source_name)"
    }
   ]
  },
  "datasets": {
   "desc": "Dataset historis (Katalog, DATA_ENGINEER), dataset Live Area, dan dataset sistem HYDROMET_AOI.",
   "cols": [
    {
     "n": "dataset_id",
     "t": "integer",
     "nn": true,
     "d": "nextval('datasets_dataset_id_seq'::regclass)",
     "k": "PK",
     "ds": "PK surrogate."
    },
    {
     "n": "dataset_uuid",
     "t": "uuid",
     "nn": true,
     "d": "gen_random_uuid()",
     "k": "UNIQUE",
     "ds": "UUID stabil untuk referensi eksternal."
    },
    {
     "n": "name",
     "t": "character varying(255)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Nama dataset; juga bagian nama folder data/datasets/{id}_{slug}."
    },
    {
     "n": "description",
     "t": "text",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Keterangan bebas."
    },
    {
     "n": "location_label",
     "t": "character varying(255)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Label lokasi saat dibuat (salinan nama ROI)."
    },
    {
     "n": "region_id",
     "t": "integer",
     "nn": false,
     "d": "",
     "k": "FK→regions_of_interest",
     "ds": "FK -> regions_of_interest. Hanya ROI sistem (M27)."
    },
    {
     "n": "bbox",
     "t": "geometry(Polygon,4326)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Bbox AOI dataset (Polygon EPSG:4326)."
    },
    {
     "n": "bbox_wkt",
     "t": "text",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Bbox yang sama dalam WKT, dipakai pipeline tanpa PostGIS."
    },
    {
     "n": "date_start",
     "t": "date",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Awal rentang tanggal data (inklusif)."
    },
    {
     "n": "date_end",
     "t": "date",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Akhir rentang tanggal data (inklusif); maksimal 366 hari (app_settings.dataset.max_days)."
    },
    {
     "n": "required_tiers",
     "t": "text[]",
     "nn": true,
     "d": "ARRAY['COG'::text]",
     "k": "",
     "ds": "Tier D14 yang disimpan, diturunkan dari dataset_source_config (TEXT[] <= 7 elemen, M32). Contoh {RAW,ALIGNED,DESPECKLED,COG}."
    },
    {
     "n": "fusion_strategy",
     "t": "character varying(20)",
     "nn": false,
     "d": "'FULL_COVERAGE'::character varying",
     "k": "FK→fusion_strategies",
     "ds": "FK -> fusion_strategies.strategy_code. NULL = dataset satu sumber (tanpa fusi)."
    },
    {
     "n": "preview_options",
     "t": "text[]",
     "nn": true,
     "d": "ARRAY['GRAYSCALE'::text, 'COLORED'::text, 'COMPOSITE'::text]",
     "k": "",
     "ds": "Varian PNG tahap PREVIEW: GRAYSCALE \\"
    },
    {
     "n": "fusion_output_only",
     "t": "boolean",
     "nn": true,
     "d": "false",
     "k": "",
     "ds": "true = hapus artefak per-satelit setelah stack fusion tanggal itu ditulis."
    },
    {
     "n": "s1_match_tolerance_days",
     "t": "smallint",
     "nn": true,
     "d": "2",
     "k": "",
     "ds": "FULL_COVERAGE: jarak hari maksimum meminjam scene S1 (0-14)."
    },
    {
     "n": "quality_settings",
     "t": "jsonb",
     "nn": true,
     "d": "'{}'::jsonb",
     "k": "",
     "ds": "Pengaturan kualitas (JSONB, M32), mis. {\"min_cloud_cover\": 20, \"orbit_direction\": \"ASCENDING\"}. Ambang skor kualitas TIDAK di sini: quality_thresholds (K15)."
    },
    {
     "n": "fusion_grid",
     "t": "jsonb",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Grid fusion yang dipaku: {transform, width, height, crs, source_product_id, pinned_at}. NULL = belum pernah fusi."
    },
    {
     "n": "dataset_kind",
     "t": "character varying(10)",
     "nn": true,
     "d": "'STANDARD'::character varying",
     "k": "",
     "ds": "STANDARD (Katalog / sistem) \\"
    },
    {
     "n": "is_system",
     "t": "boolean",
     "nn": true,
     "d": "false",
     "k": "",
     "ds": "true = dataset sistem (HYDROMET_AOI) yang disembunyikan dari Katalog (PIPELINE.md §3.1)."
    },
    {
     "n": "status",
     "t": "character varying(20)",
     "nn": true,
     "d": "'DRAFT'::character varying",
     "k": "",
     "ds": "Status siklus: DRAFT, QUEUED, PREPARING, DOWNLOADING, PROCESSING, PAUSED, CLEANUP, COMPLETED, FAILED, CANCELLED, DELETING, DELETED."
    },
    {
     "n": "total_scenes",
     "t": "integer",
     "nn": true,
     "d": "0",
     "k": "",
     "ds": "Jumlah scene S1 yang ditemukan."
    },
    {
     "n": "completed_scenes",
     "t": "integer",
     "nn": true,
     "d": "0",
     "k": "",
     "ds": "Jumlah scene S1 yang selesai diproses."
    },
    {
     "n": "failed_scenes",
     "t": "integer",
     "nn": true,
     "d": "0",
     "k": "",
     "ds": "Jumlah scene S1 yang gagal."
    },
    {
     "n": "total_size_bytes",
     "t": "bigint",
     "nn": true,
     "d": "0",
     "k": "",
     "ds": "Total ukuran berkas dataset di disk (byte)."
    },
    {
     "n": "is_deletable",
     "t": "boolean",
     "nn": true,
     "d": "true",
     "k": "",
     "ds": "false = tidak boleh dihapus lewat Katalog (mis. dataset Live Area)."
    },
    {
     "n": "generate_preview",
     "t": "boolean",
     "nn": true,
     "d": "true",
     "k": "",
     "ds": "false = lewati tahap PREVIEW."
    },
    {
     "n": "created_by",
     "t": "integer",
     "nn": false,
     "d": "",
     "k": "FK→users",
     "ds": "FK -> users: pembuat dataset. NULL untuk dataset sistem."
    },
    {
     "n": "created_at",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "now()",
     "k": "",
     "ds": "Waktu baris dibuat."
    },
    {
     "n": "updated_at",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "now()",
     "k": "",
     "ds": "Waktu baris terakhir diubah (trigger)."
    },
    {
     "n": "deleted_at",
     "t": "timestamp with time zone",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Waktu dataset dihapus (berkasnya dihapus, barisnya disimpan)."
    }
   ],
   "cons": [
    {
     "n": "chk_dataset_date_range",
     "type": "CHECK",
     "def": "CHECK ((date_end >= date_start))"
    },
    {
     "n": "chk_dataset_kind",
     "type": "CHECK",
     "def": "CHECK (((dataset_kind)::text = ANY (ARRAY[('STANDARD'::character varying)::text, ('LIVE_AREA'::character varying)::text])))"
    },
    {
     "n": "chk_dataset_status",
     "type": "CHECK",
     "def": "CHECK (((status)::text = ANY (ARRAY[('DRAFT'::character varying)::text, ('QUEUED'::character varying)::text, ('PREPARING'::character varying)::text, ('DOWNLOADING'::character varying)::text, ('PROCESSING'::character varying)::text, ('PAUSED'::character varying)::text, ('CLEANUP'::character varying)::text, ('COMPLETED'::character varying)::text, ('FAILED'::character varying)::text, ('CANCELLED'::character varying)::text, ('DELETING'::character varying)::text, ('DELETED'::character varying)::text])))"
    },
    {
     "n": "chk_datasets_s1_tolerance",
     "type": "CHECK",
     "def": "CHECK (((s1_match_tolerance_days >= 0) AND (s1_match_tolerance_days <= 14)))"
    },
    {
     "n": "chk_preview_options",
     "type": "CHECK",
     "def": "CHECK ((preview_options <@ ARRAY['GRAYSCALE'::text, 'COLORED'::text, 'COMPOSITE'::text]))"
    },
    {
     "n": "chk_required_tiers",
     "type": "CHECK",
     "def": "CHECK (((required_tiers <@ ARRAY['RAW'::text, 'ALIGNED'::text, 'DESPECKLED'::text, 'INDICES'::text, 'ACCUMULATED'::text, 'COG'::text, 'FUSED'::text]) AND (array_length(required_tiers, 1) > 0)))"
    },
    {
     "n": "datasets_created_by_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (created_by) REFERENCES users(user_id) ON DELETE SET NULL"
    },
    {
     "n": "datasets_fusion_strategy_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (fusion_strategy) REFERENCES fusion_strategies(strategy_code) ON UPDATE CASCADE"
    },
    {
     "n": "datasets_region_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (region_id) REFERENCES regions_of_interest(region_id) ON DELETE SET NULL"
    },
    {
     "n": "datasets_pkey",
     "type": "PK",
     "def": "PRIMARY KEY (dataset_id)"
    },
    {
     "n": "datasets_dataset_uuid_key",
     "type": "UNIQUE",
     "def": "UNIQUE (dataset_uuid)"
    }
   ]
  },
  "disaster_events": {
   "desc": "Catatan kejadian bencana (GMLS, BPBD, input ANALYST). Tanpa data pribadi. Soft delete.",
   "cols": [
    {
     "n": "event_id",
     "t": "bigint",
     "nn": true,
     "d": "nextval('disaster_events_event_id_seq'::regclass)",
     "k": "PK",
     "ds": "PK surrogate."
    },
    {
     "n": "disaster_type_id",
     "t": "smallint",
     "nn": true,
     "d": "",
     "k": "FK→disaster_types",
     "ds": "FK -> disaster_types."
    },
    {
     "n": "region_id",
     "t": "integer",
     "nn": true,
     "d": "",
     "k": "FK→administrative_regions",
     "ds": "FK -> administrative_regions (kecamatan)."
    },
    {
     "n": "village_name",
     "t": "character varying(100)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Nama desa sebagai teks (COD-AB level 4 tidak tersedia)."
    },
    {
     "n": "location",
     "t": "geometry(Point,4326)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Titik kejadian opsional (Point EPSG:4326)."
    },
    {
     "n": "event_date",
     "t": "date",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Tanggal mulai kejadian."
    },
    {
     "n": "event_end_date",
     "t": "date",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Tanggal selesai (>= event_date), opsional."
    },
    {
     "n": "description",
     "t": "text",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Uraian kejadian, 10-4000 karakter."
    },
    {
     "n": "impact_summary",
     "t": "character varying(500)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Ringkasan dampak (rumah terdampak, akses jalan) tanpa data pribadi."
    },
    {
     "n": "info_source",
     "t": "character varying(30)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "GMLS \\"
    },
    {
     "n": "source_reference",
     "t": "text",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "URL atau nomor dokumen rujukan."
    },
    {
     "n": "is_verified",
     "t": "boolean",
     "nn": true,
     "d": "false",
     "k": "",
     "ds": "true = sudah diverifikasi (dipakai v_evaluasi_alert)."
    },
    {
     "n": "verified_by",
     "t": "integer",
     "nn": false,
     "d": "",
     "k": "FK→users",
     "ds": "FK -> users: pemverifikasi."
    },
    {
     "n": "recorded_by",
     "t": "integer",
     "nn": true,
     "d": "",
     "k": "FK→users",
     "ds": "FK -> users: pencatat."
    },
    {
     "n": "recorded_at",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "now()",
     "k": "",
     "ds": "Waktu dicatat."
    },
    {
     "n": "updated_at",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "now()",
     "k": "",
     "ds": "Waktu baris terakhir diubah (trigger)."
    },
    {
     "n": "deleted_at",
     "t": "timestamp with time zone",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Soft delete; NULL = aktif."
    }
   ],
   "cons": [
    {
     "n": "disaster_events_check",
     "type": "CHECK",
     "def": "CHECK (((event_end_date IS NULL) OR (event_end_date >= event_date)))"
    },
    {
     "n": "disaster_events_description_check",
     "type": "CHECK",
     "def": "CHECK (((length(description) >= 10) AND (length(description) <= 4000)))"
    },
    {
     "n": "disaster_events_info_source_check",
     "type": "CHECK",
     "def": "CHECK (((info_source)::text = ANY (ARRAY[('GMLS'::character varying)::text, ('BPBD_LEBAK'::character varying)::text, ('BNPB_DIBI'::character varying)::text, ('MEDIA'::character varying)::text, ('LAINNYA'::character varying)::text])))"
    },
    {
     "n": "disaster_events_disaster_type_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (disaster_type_id) REFERENCES disaster_types(disaster_type_id)"
    },
    {
     "n": "disaster_events_recorded_by_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (recorded_by) REFERENCES users(user_id)"
    },
    {
     "n": "disaster_events_region_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (region_id) REFERENCES administrative_regions(region_id)"
    },
    {
     "n": "disaster_events_verified_by_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (verified_by) REFERENCES users(user_id)"
    },
    {
     "n": "disaster_events_pkey",
     "type": "PK",
     "def": "PRIMARY KEY (event_id)"
    }
   ]
  },
  "disaster_types": {
   "desc": "Master jenis bencana. ADMIN dapat menambah jenis tanpa ubah kode (uji adaptability).",
   "cols": [
    {
     "n": "disaster_type_id",
     "t": "smallint",
     "nn": true,
     "d": "nextval('disaster_types_disaster_type_id_seq'::regclass)",
     "k": "PK",
     "ds": "PK surrogate."
    },
    {
     "n": "type_code",
     "t": "character varying(30)",
     "nn": true,
     "d": "",
     "k": "UNIQUE",
     "ds": "Alternate key: BANJIR \\"
    },
    {
     "n": "type_name",
     "t": "character varying(100)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Label UI."
    },
    {
     "n": "category",
     "t": "character varying(30)",
     "nn": true,
     "d": "'HIDROMETEOROLOGI'::character varying",
     "k": "",
     "ds": "Kelompok bencana, default HIDROMETEOROLOGI."
    },
    {
     "n": "indicator_bands",
     "t": "character varying(100)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Teks informatif band indikator, mis. \"RAIN_24H, VH\"."
    },
    {
     "n": "is_active",
     "t": "boolean",
     "nn": true,
     "d": "true",
     "k": "",
     "ds": "false = jenis tidak ditawarkan lagi di form."
    }
   ],
   "cons": [
    {
     "n": "disaster_types_pkey",
     "type": "PK",
     "def": "PRIMARY KEY (disaster_type_id)"
    },
    {
     "n": "disaster_types_type_code_key",
     "type": "UNIQUE",
     "def": "UNIQUE (type_code)"
    }
   ]
  },
  "fusion_products": {
   "desc": "Registri stack HDF5 multi-sensor (S1 + MODIS + GPM) per dataset per tanggal per level.",
   "cols": [
    {
     "n": "fusion_id",
     "t": "bigint",
     "nn": true,
     "d": "nextval('fusion_products_fusion_id_seq'::regclass)",
     "k": "PK",
     "ds": "PK surrogate."
    },
    {
     "n": "dataset_id",
     "t": "integer",
     "nn": false,
     "d": "",
     "k": "FK→datasets, UNIQUE",
     "ds": "FK -> datasets pemilik stack (bagian kunci unik)."
    },
    {
     "n": "feature_date",
     "t": "date",
     "nn": true,
     "d": "",
     "k": "UNIQUE",
     "ds": "Tanggal fitur stack (hari UTC)."
    },
    {
     "n": "region_id",
     "t": "integer",
     "nn": true,
     "d": "",
     "k": "FK→regions_of_interest",
     "ds": "FK -> regions_of_interest."
    },
    {
     "n": "s1_scene_id",
     "t": "integer",
     "nn": false,
     "d": "",
     "k": "FK→satellite_scenes",
     "ds": "FK -> satellite_scenes: scene S1 yang dipakai; NULL bila hari itu tanpa S1."
    },
    {
     "n": "modis_scene_id",
     "t": "bigint",
     "nn": false,
     "d": "",
     "k": "FK→nasa_scenes",
     "ds": "FK -> nasa_scenes: granule MODIS penanda."
    },
    {
     "n": "gpm_scene_id",
     "t": "bigint",
     "nn": false,
     "d": "",
     "k": "FK→nasa_scenes",
     "ds": "FK -> nasa_scenes: granule GPM penanda."
    },
    {
     "n": "days_since_s1",
     "t": "integer",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Selisih hari terbesar antar sumber terhadap tanggal fitur."
    },
    {
     "n": "feature_stack_path",
     "t": "text",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Path berkas HDF5."
    },
    {
     "n": "fusion_strategy",
     "t": "character varying(20)",
     "nn": false,
     "d": "'FULL_COVERAGE'::character varying",
     "k": "FK→fusion_strategies",
     "ds": "FK -> fusion_strategies.strategy_code."
    },
    {
     "n": "processing_level",
     "t": "character varying(20)",
     "nn": true,
     "d": "'PROCESSED'::character varying",
     "k": "UNIQUE",
     "ds": "Level input stack: RAW (dari ALIGNED) \\"
    },
    {
     "n": "temporal_offset_modis",
     "t": "integer",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Selisih hari MODIS terhadap tanggal fitur. NULL = MODIS tidak ikut."
    },
    {
     "n": "temporal_offset_gpm",
     "t": "integer",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Selisih hari GPM terhadap tanggal fitur. NULL = GPM tidak ikut."
    },
    {
     "n": "s1_offset_days",
     "t": "smallint",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Jarak hari S1 yang dipakai: 0 = same-day, NULL = tanpa S1."
    },
    {
     "n": "created_at",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "now()",
     "k": "",
     "ds": "Waktu baris dibuat."
    }
   ],
   "cons": [
    {
     "n": "fusion_products_processing_level_check",
     "type": "CHECK",
     "def": "CHECK (((processing_level)::text = ANY (ARRAY[('RAW'::character varying)::text, ('PROCESSED'::character varying)::text])))"
    },
    {
     "n": "fusion_products_dataset_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (dataset_id) REFERENCES datasets(dataset_id) ON DELETE CASCADE"
    },
    {
     "n": "fusion_products_fusion_strategy_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (fusion_strategy) REFERENCES fusion_strategies(strategy_code) ON UPDATE CASCADE"
    },
    {
     "n": "fusion_products_gpm_scene_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (gpm_scene_id) REFERENCES nasa_scenes(nasa_scene_id) ON DELETE SET NULL"
    },
    {
     "n": "fusion_products_modis_scene_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (modis_scene_id) REFERENCES nasa_scenes(nasa_scene_id) ON DELETE SET NULL"
    },
    {
     "n": "fusion_products_region_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (region_id) REFERENCES regions_of_interest(region_id) ON DELETE RESTRICT"
    },
    {
     "n": "fusion_products_s1_scene_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (s1_scene_id) REFERENCES satellite_scenes(scene_id) ON DELETE SET NULL"
    },
    {
     "n": "fusion_products_pkey",
     "type": "PK",
     "def": "PRIMARY KEY (fusion_id)"
    },
    {
     "n": "uq_fusion_dataset_date_level",
     "type": "UNIQUE",
     "def": "UNIQUE (dataset_id, feature_date, processing_level)"
    }
   ]
  },
  "fusion_strategies": {
   "desc": "Master strategi fusion (M9). Dirujuk datasets.fusion_strategy dan fusion_products.fusion_strategy lewat strategy_code.",
   "cols": [
    {
     "n": "strategy_id",
     "t": "smallint",
     "nn": true,
     "d": "nextval('fusion_strategies_strategy_id_seq'::regclass)",
     "k": "PK",
     "ds": "PK surrogate."
    },
    {
     "n": "strategy_code",
     "t": "character varying(20)",
     "nn": true,
     "d": "",
     "k": "UNIQUE",
     "ds": "Alternate key: CO_OCCURRENCE \\"
    },
    {
     "n": "download_axis",
     "t": "text",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Sumbu unduh: tanggal MODIS/GPM mana yang diambil."
    },
    {
     "n": "assemble_axis",
     "t": "text",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Sumbu rakit: tanggal mana yang menjadi satu berkas HDF5."
    },
    {
     "n": "description",
     "t": "text",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Uraian strategi."
    }
   ],
   "cons": [
    {
     "n": "fusion_strategies_pkey",
     "type": "PK",
     "def": "PRIMARY KEY (strategy_id)"
    },
    {
     "n": "fusion_strategies_strategy_code_key",
     "type": "UNIQUE",
     "def": "UNIQUE (strategy_code)"
    }
   ]
  },
  "generated_reports": {
   "desc": "Laporan PDF mingguan/bulanan yang dibuat (M18). Akses dibatasi RLS per audiens (tahap keamanan).",
   "cols": [
    {
     "n": "report_id",
     "t": "bigint",
     "nn": true,
     "d": "nextval('generated_reports_report_id_seq'::regclass)",
     "k": "PK",
     "ds": "PK surrogate."
    },
    {
     "n": "report_type_id",
     "t": "smallint",
     "nn": true,
     "d": "",
     "k": "FK→report_types",
     "ds": "FK -> report_types."
    },
    {
     "n": "period_start",
     "t": "date",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Awal periode (Senin / tanggal 1, WIB)."
    },
    {
     "n": "period_end",
     "t": "date",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Akhir periode (Minggu / akhir bulan, WIB)."
    },
    {
     "n": "file_path",
     "t": "text",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Path PDF: data/reports/{report_code}/{YYYY}/...pdf."
    },
    {
     "n": "file_size_bytes",
     "t": "bigint",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Ukuran PDF (byte)."
    },
    {
     "n": "checksum_sha256",
     "t": "character(64)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "SHA-256 PDF (64 hex)."
    },
    {
     "n": "status",
     "t": "character varying(10)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "READY \\"
    },
    {
     "n": "error_message",
     "t": "text",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Pesan galat bila FAILED."
    },
    {
     "n": "generated_by",
     "t": "integer",
     "nn": false,
     "d": "",
     "k": "FK→users",
     "ds": "FK -> users: ADMIN yang meregenerasi. NULL = scheduler."
    },
    {
     "n": "generated_at",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "now()",
     "k": "",
     "ds": "Waktu laporan dibuat."
    }
   ],
   "cons": [
    {
     "n": "generated_reports_check",
     "type": "CHECK",
     "def": "CHECK ((period_end >= period_start))"
    },
    {
     "n": "generated_reports_file_size_bytes_check",
     "type": "CHECK",
     "def": "CHECK ((file_size_bytes >= 0))"
    },
    {
     "n": "generated_reports_status_check",
     "type": "CHECK",
     "def": "CHECK (((status)::text = ANY (ARRAY[('READY'::character varying)::text, ('FAILED'::character varying)::text, ('SUPERSEDED'::character varying)::text])))"
    },
    {
     "n": "generated_reports_generated_by_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (generated_by) REFERENCES users(user_id)"
    },
    {
     "n": "generated_reports_report_type_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (report_type_id) REFERENCES report_types(report_type_id)"
    },
    {
     "n": "generated_reports_pkey",
     "type": "PK",
     "def": "PRIMARY KEY (report_id)"
    }
   ]
  },
  "live_areas": {
   "desc": "Live Area: satu AOI yang dipantau otomatis per lintasan S1 (maksimal app_settings.live.max_areas).",
   "cols": [
    {
     "n": "area_id",
     "t": "integer",
     "nn": true,
     "d": "nextval('live_areas_area_id_seq'::regclass)",
     "k": "PK",
     "ds": "PK surrogate."
    },
    {
     "n": "dataset_id",
     "t": "integer",
     "nn": false,
     "d": "",
     "k": "FK→datasets",
     "ds": "FK -> datasets berjenis LIVE_AREA yang diproses pipeline."
    },
    {
     "n": "name",
     "t": "character varying(255)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Nama area, mis. \"Lebak Selatan\"."
    },
    {
     "n": "region_id",
     "t": "integer",
     "nn": false,
     "d": "",
     "k": "FK→regions_of_interest",
     "ds": "FK -> regions_of_interest."
    },
    {
     "n": "location_label",
     "t": "character varying(255)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Label lokasi (salinan nama ROI)."
    },
    {
     "n": "bbox_wkt",
     "t": "text",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Bbox area dalam WKT."
    },
    {
     "n": "retention",
     "t": "smallint",
     "nn": true,
     "d": "6",
     "k": "",
     "ds": "Jumlah scene terbaru yang ditampilkan kartu dan dipakai prakiraan (1-60, default 6). Berkas scene disimpan menurut umur: app_settings.storage.raster_retention_days (M58)."
    },
    {
     "n": "enabled",
     "t": "boolean",
     "nn": true,
     "d": "true",
     "k": "",
     "ds": "false = siklus terjadwal dilewati."
    },
    {
     "n": "status",
     "t": "character varying(20)",
     "nn": true,
     "d": "'BACKFILLING'::character varying",
     "k": "",
     "ds": "BACKFILLING \\"
    },
    {
     "n": "status_message",
     "t": "text",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Pesan status untuk kartu Live."
    },
    {
     "n": "last_checked_at",
     "t": "timestamp with time zone",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Waktu siklus terakhir memeriksa scene baru."
    },
    {
     "n": "forecast",
     "t": "jsonb",
     "nn": true,
     "d": "'{}'::jsonb",
     "k": "",
     "ds": "Prakiraan statistik terakhir (JSONB tampilan, M12)."
    },
    {
     "n": "forecast_updated_at",
     "t": "timestamp with time zone",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Waktu prakiraan dihitung."
    },
    {
     "n": "updated_by",
     "t": "integer",
     "nn": false,
     "d": "",
     "k": "FK→users",
     "ds": "FK -> users: ADMIN yang terakhir mengubah."
    },
    {
     "n": "created_at",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "now()",
     "k": "",
     "ds": "Waktu baris dibuat."
    },
    {
     "n": "updated_at",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "now()",
     "k": "",
     "ds": "Waktu baris terakhir diubah (trigger)."
    },
    {
     "n": "deleted_at",
     "t": "timestamp with time zone",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Waktu area dihapus (log tetap disimpan)."
    }
   ],
   "cons": [
    {
     "n": "chk_live_area_retention",
     "type": "CHECK",
     "def": "CHECK (((retention >= 1) AND (retention <= 60)))"
    },
    {
     "n": "chk_live_area_status",
     "type": "CHECK",
     "def": "CHECK (((status)::text = ANY (ARRAY[('BACKFILLING'::character varying)::text, ('ACTIVE'::character varying)::text, ('RUNNING'::character varying)::text, ('WAITING'::character varying)::text, ('ERROR'::character varying)::text, ('DELETED'::character varying)::text])))"
    },
    {
     "n": "live_areas_dataset_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (dataset_id) REFERENCES datasets(dataset_id) ON DELETE SET NULL"
    },
    {
     "n": "live_areas_region_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (region_id) REFERENCES regions_of_interest(region_id) ON DELETE SET NULL"
    },
    {
     "n": "live_areas_updated_by_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (updated_by) REFERENCES users(user_id)"
    },
    {
     "n": "live_areas_pkey",
     "type": "PK",
     "def": "PRIMARY KEY (area_id)"
    }
   ]
  },
  "live_events": {
   "desc": "Log langkah siklus Live per area (append-only, tanpa FK agar bertahan setelah area dihapus).",
   "cols": [
    {
     "n": "event_id",
     "t": "bigint",
     "nn": true,
     "d": "nextval('live_events_event_id_seq'::regclass)",
     "k": "PK",
     "ds": "PK surrogate."
    },
    {
     "n": "area_id",
     "t": "integer",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "live_areas.area_id (tanpa FK)."
    },
    {
     "n": "scene_date",
     "t": "date",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Tanggal scene terkait, bila ada."
    },
    {
     "n": "step",
     "t": "character varying(40)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Langkah siklus, mis. DISCOVER, INGEST, PREVIEW, RETENTION."
    },
    {
     "n": "status",
     "t": "character varying(20)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Status langkah, mis. OK, FAILED, SKIPPED."
    },
    {
     "n": "message",
     "t": "text",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Pesan langkah."
    },
    {
     "n": "details",
     "t": "jsonb",
     "nn": true,
     "d": "'{}'::jsonb",
     "k": "",
     "ds": "Detail terstruktur (JSONB)."
    },
    {
     "n": "created_at",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "now()",
     "k": "",
     "ds": "Waktu kejadian."
    }
   ],
   "cons": [
    {
     "n": "live_events_pkey",
     "type": "PK",
     "def": "PRIMARY KEY (event_id)"
    }
   ]
  },
  "live_scene_metrics": {
   "desc": "Metrik numerik scene Live, satu baris per band x metrik (1NF, M31). Tetap ada setelah berkas scene dihapus retensi.",
   "cols": [
    {
     "n": "metric_id",
     "t": "bigint",
     "nn": true,
     "d": "nextval('live_scene_metrics_metric_id_seq'::regclass)",
     "k": "PK",
     "ds": "PK surrogate."
    },
    {
     "n": "live_scene_id",
     "t": "bigint",
     "nn": true,
     "d": "",
     "k": "FK→live_scenes, UNIQUE",
     "ds": "FK -> live_scenes."
    },
    {
     "n": "band_id",
     "t": "smallint",
     "nn": true,
     "d": "",
     "k": "FK→spectral_bands, UNIQUE",
     "ds": "FK -> spectral_bands: VV, VH, FLOOD, NDVI, NDWI, RAIN_24H/72H/7D, WATER_CHANGE."
    },
    {
     "n": "metric_name",
     "t": "character varying(30)",
     "nn": true,
     "d": "",
     "k": "UNIQUE",
     "ds": "Nama metrik, mis. mean, pct_below_threshold, valid_pct, new_km2, receded_km2, persistent_km2, same_orbit."
    },
    {
     "n": "value",
     "t": "numeric(12,4)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Nilai dalam satuan metrik (dB, %, mm, km2, indeks). NULL = tidak ada piksel valid."
    },
    {
     "n": "source_date",
     "t": "date",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Tanggal data sumber (MODIS/GPM bisa tanggal terdekat D-1)."
    },
    {
     "n": "ref_live_scene_id",
     "t": "bigint",
     "nn": false,
     "d": "",
     "k": "FK→live_scenes",
     "ds": "FK -> live_scenes: scene pembanding untuk WATER_CHANGE."
    }
   ],
   "cons": [
    {
     "n": "live_scene_metrics_band_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (band_id) REFERENCES spectral_bands(band_id)"
    },
    {
     "n": "live_scene_metrics_live_scene_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (live_scene_id) REFERENCES live_scenes(live_scene_id) ON DELETE CASCADE"
    },
    {
     "n": "live_scene_metrics_ref_live_scene_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (ref_live_scene_id) REFERENCES live_scenes(live_scene_id) ON DELETE SET NULL"
    },
    {
     "n": "live_scene_metrics_pkey",
     "type": "PK",
     "def": "PRIMARY KEY (metric_id)"
    },
    {
     "n": "uq_live_scene_metric",
     "type": "UNIQUE",
     "def": "UNIQUE (live_scene_id, band_id, metric_name)"
    }
   ]
  },
  "live_scenes": {
   "desc": "Satu scene Live (tanggal lintasan S1) per area. Tidak pernah dihapus: retensi hanya menghapus berkas dan mengisi deleted_at. Sengaja tanpa FK agar hidup lebih lama dari area/dataset.",
   "cols": [
    {
     "n": "live_scene_id",
     "t": "bigint",
     "nn": true,
     "d": "nextval('live_scenes_live_scene_id_seq'::regclass)",
     "k": "PK",
     "ds": "PK surrogate."
    },
    {
     "n": "area_id",
     "t": "integer",
     "nn": true,
     "d": "",
     "k": "UNIQUE",
     "ds": "live_areas.area_id (tanpa FK, lihat komentar tabel)."
    },
    {
     "n": "dataset_id",
     "t": "integer",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "datasets.dataset_id (tanpa FK)."
    },
    {
     "n": "scene_date",
     "t": "date",
     "nn": true,
     "d": "",
     "k": "UNIQUE",
     "ds": "Tanggal akuisisi S1 (hari UTC)."
    },
    {
     "n": "s1_product_ids",
     "t": "text[]",
     "nn": true,
     "d": "ARRAY[]::text[]",
     "k": "",
     "ds": "Identifier produk S1 yang membentuk scene (TEXT[] <= 3 frame, M32)."
    },
    {
     "n": "status",
     "t": "character varying(20)",
     "nn": true,
     "d": "'PROCESSING'::character varying",
     "k": "",
     "ds": "PROCESSING \\"
    },
    {
     "n": "source_status",
     "t": "jsonb",
     "nn": true,
     "d": "'{}'::jsonb",
     "k": "",
     "ds": "Status per sumber untuk tampilan (JSONB, tidak dikueri), termasuk deskriptor teks metrik di [sumber].meta (run IMERG, periode komposit). Angka metrik ada di live_scene_metrics (M31)."
    },
    {
     "n": "interpretations",
     "t": "jsonb",
     "nn": true,
     "d": "'{}'::jsonb",
     "k": "",
     "ds": "Kalimat kondisi per variabel (JSONB tampilan)."
    },
    {
     "n": "area_status",
     "t": "jsonb",
     "nn": true,
     "d": "'{}'::jsonb",
     "k": "",
     "ds": "Status area ringkas {level, label, sentence} (JSONB tampilan)."
    },
    {
     "n": "previews",
     "t": "jsonb",
     "nn": true,
     "d": "'{}'::jsonb",
     "k": "",
     "ds": "Manifest preview PNG per kunci (JSONB tampilan)."
    },
    {
     "n": "created_at",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "now()",
     "k": "",
     "ds": "Waktu baris dibuat."
    },
    {
     "n": "updated_at",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "now()",
     "k": "",
     "ds": "Waktu baris terakhir diubah (trigger)."
    },
    {
     "n": "deleted_at",
     "t": "timestamp with time zone",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Waktu berkas scene dihapus retensi; baris tetap ada."
    },
    {
     "n": "delete_reason",
     "t": "text",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Alasan penghapusan berkas, mis. retention."
    },
    {
     "n": "deleted_files",
     "t": "jsonb",
     "nn": true,
     "d": "'[]'::jsonb",
     "k": "",
     "ds": "Daftar berkas yang dihapus (JSONB array)."
    },
    {
     "n": "freed_bytes",
     "t": "bigint",
     "nn": true,
     "d": "0",
     "k": "",
     "ds": "Ruang disk yang dibebaskan (byte)."
    }
   ],
   "cons": [
    {
     "n": "chk_live_scene_status",
     "type": "CHECK",
     "def": "CHECK (((status)::text = ANY ((ARRAY['PROCESSING'::character varying, 'READY'::character varying, 'PARTIAL'::character varying, 'FAILED'::character varying, 'DELETED'::character varying, 'INCOMPLETE'::character varying])::text[])))"
    },
    {
     "n": "live_scenes_pkey",
     "type": "PK",
     "def": "PRIMARY KEY (live_scene_id)"
    },
    {
     "n": "uq_live_scene_area_date",
     "type": "UNIQUE",
     "def": "UNIQUE (area_id, scene_date)"
    }
   ]
  },
  "nasa_scenes": {
   "desc": "Registri granule MODIS dan GPM (satu baris per sumber/produk/tile/tanggal).",
   "cols": [
    {
     "n": "nasa_scene_id",
     "t": "bigint",
     "nn": true,
     "d": "nextval('nasa_scenes_nasa_scene_id_seq'::regclass)",
     "k": "PK",
     "ds": "PK surrogate."
    },
    {
     "n": "source",
     "t": "character varying(20)",
     "nn": true,
     "d": "",
     "k": "FK→satellite_sources, UNIQUE",
     "ds": "FK -> satellite_sources.source_code: MODIS \\"
    },
    {
     "n": "tile_id",
     "t": "character varying(10)",
     "nn": true,
     "d": "",
     "k": "UNIQUE",
     "ds": "Tile MODIS (mis. MOSAIC dari h28v09) atau GLOBAL untuk GPM."
    },
    {
     "n": "product_short_name",
     "t": "character varying(50)",
     "nn": true,
     "d": "",
     "k": "UNIQUE",
     "ds": "Short name produk NASA, mis. MCDWD_L3_F2_NRT, MOD09A1, GPM_3IMERGDF."
    },
    {
     "n": "acquisition_date",
     "t": "date",
     "nn": true,
     "d": "",
     "k": "UNIQUE",
     "ds": "Tanggal data (hari UTC, M28). Untuk komposit MOD09A1: awal periode."
    },
    {
     "n": "region_id",
     "t": "integer",
     "nn": true,
     "d": "",
     "k": "FK→regions_of_interest",
     "ds": "FK -> regions_of_interest: ROI yang memicu unduhan."
    },
    {
     "n": "raw_file_path",
     "t": "text",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Path berkas hasil (atau granule) di disk."
    },
    {
     "n": "download_url",
     "t": "text",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "URL granule di penyedia."
    },
    {
     "n": "run_type",
     "t": "character varying(5)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "GPM IMERG run: F (Final) \\"
    },
    {
     "n": "is_available",
     "t": "boolean",
     "nn": true,
     "d": "true",
     "k": "",
     "ds": "false = granule tidak tersedia lagi."
    },
    {
     "n": "is_valid",
     "t": "boolean",
     "nn": true,
     "d": "true",
     "k": "",
     "ds": "false = dinonaktifkan ADMIN (soft delete, M24)."
    },
    {
     "n": "invalidated_by",
     "t": "integer",
     "nn": false,
     "d": "",
     "k": "FK→users",
     "ds": "FK -> users: ADMIN yang menonaktifkan."
    },
    {
     "n": "invalidated_at",
     "t": "timestamp with time zone",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Waktu dinonaktifkan."
    },
    {
     "n": "invalid_reason",
     "t": "text",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Alasan wajib saat dinonaktifkan."
    },
    {
     "n": "created_at",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "now()",
     "k": "",
     "ds": "Waktu baris dibuat."
    }
   ],
   "cons": [
    {
     "n": "chk_nasa_invalidation",
     "type": "CHECK",
     "def": "CHECK ((is_valid OR ((invalidated_at IS NOT NULL) AND (invalid_reason IS NOT NULL))))"
    },
    {
     "n": "nasa_scenes_run_type_check",
     "type": "CHECK",
     "def": "CHECK (((run_type)::text = ANY (ARRAY[('F'::character varying)::text, ('L'::character varying)::text, ('E'::character varying)::text])))"
    },
    {
     "n": "nasa_scenes_invalidated_by_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (invalidated_by) REFERENCES users(user_id)"
    },
    {
     "n": "nasa_scenes_region_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (region_id) REFERENCES regions_of_interest(region_id) ON DELETE RESTRICT"
    },
    {
     "n": "nasa_scenes_source_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (source) REFERENCES satellite_sources(source_code) ON UPDATE CASCADE"
    },
    {
     "n": "nasa_scenes_pkey",
     "type": "PK",
     "def": "PRIMARY KEY (nasa_scene_id)"
    },
    {
     "n": "uq_nasa_scene",
     "type": "UNIQUE",
     "def": "UNIQUE (source, tile_id, product_short_name, acquisition_date)"
    }
   ]
  },
  "processing_jobs": {
   "desc": "Eksekusi satu tahap pipeline (scene/granule x tahap x percobaan). Jangkar: scene S1, granule NASA, atau tidak keduanya untuk FUSION (M30).",
   "cols": [
    {
     "n": "job_id",
     "t": "bigint",
     "nn": true,
     "d": "nextval('processing_jobs_job_id_seq'::regclass)",
     "k": "PK",
     "ds": "PK surrogate."
    },
    {
     "n": "job_uuid",
     "t": "uuid",
     "nn": true,
     "d": "gen_random_uuid()",
     "k": "UNIQUE",
     "ds": "UUID stabil untuk referensi eksternal."
    },
    {
     "n": "scene_id",
     "t": "integer",
     "nn": false,
     "d": "",
     "k": "FK→satellite_scenes, UNIQUE",
     "ds": "FK -> satellite_scenes: scene S1 yang diproses. NULL untuk job MODIS/GPM/FUSION."
    },
    {
     "n": "nasa_scene_id",
     "t": "bigint",
     "nn": false,
     "d": "",
     "k": "FK→nasa_scenes",
     "ds": "FK -> nasa_scenes: granule MODIS/GPM yang diproses. NULL untuk job S1/FUSION (M30)."
    },
    {
     "n": "stage_id",
     "t": "integer",
     "nn": true,
     "d": "",
     "k": "FK→processing_stages, UNIQUE",
     "ds": "FK -> processing_stages."
    },
    {
     "n": "attempt_number",
     "t": "smallint",
     "nn": true,
     "d": "1",
     "k": "UNIQUE",
     "ds": "Percobaan ke berapa untuk (scene, tahap)."
    },
    {
     "n": "status",
     "t": "job_status_enum",
     "nn": true,
     "d": "'QUEUED'::job_status_enum",
     "k": "",
     "ds": "QUEUED \\"
    },
    {
     "n": "queued_at",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "now()",
     "k": "",
     "ds": "Waktu masuk antrean."
    },
    {
     "n": "started_at",
     "t": "timestamp with time zone",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Waktu mulai."
    },
    {
     "n": "completed_at",
     "t": "timestamp with time zone",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Waktu selesai."
    },
    {
     "n": "duration_seconds",
     "t": "numeric(10,3)",
     "nn": false,
     "d": "GENERATED",
     "k": "",
     "ds": "Durasi (detik), GENERATED dari completed_at - started_at."
    },
    {
     "n": "worker_hostname",
     "t": "character varying(100)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Host yang menjalankan tahap."
    },
    {
     "n": "cpu_usage_percent",
     "t": "numeric(7,2)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Pemakaian CPU total seluruh core (24 core = sampai 2400%)."
    },
    {
     "n": "memory_usage_mb",
     "t": "numeric(10,2)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Pemakaian memori puncak (MB)."
    },
    {
     "n": "input_size_mb",
     "t": "numeric(12,3)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Ukuran input (MB)."
    },
    {
     "n": "output_size_mb",
     "t": "numeric(12,3)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Ukuran output (MB)."
    },
    {
     "n": "error_code",
     "t": "character varying(50)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Kode galat (nama exception), mis. MemoryError."
    },
    {
     "n": "error_message",
     "t": "text",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Pesan galat."
    },
    {
     "n": "log_file_path",
     "t": "text",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Path berkas log tahap."
    },
    {
     "n": "parameters_json",
     "t": "jsonb",
     "nn": true,
     "d": "'{}'::jsonb",
     "k": "",
     "ds": "Parameter reproduksibilitas (JSONB, M32): versi software, window Lee, run GPM, ambang. Nama \"parameters\" di DATABASE.md §4.1 (K8)."
    },
    {
     "n": "created_at",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "now()",
     "k": "",
     "ds": "Waktu baris dibuat."
    },
    {
     "n": "updated_at",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "now()",
     "k": "",
     "ds": "Waktu baris terakhir diubah (trigger)."
    }
   ],
   "cons": [
    {
     "n": "chk_pjobs_single_anchor",
     "type": "CHECK",
     "def": "CHECK (((scene_id IS NULL) OR (nasa_scene_id IS NULL)))"
    },
    {
     "n": "processing_jobs_nasa_scene_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (nasa_scene_id) REFERENCES nasa_scenes(nasa_scene_id) ON DELETE CASCADE"
    },
    {
     "n": "processing_jobs_scene_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (scene_id) REFERENCES satellite_scenes(scene_id) ON DELETE CASCADE"
    },
    {
     "n": "processing_jobs_stage_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (stage_id) REFERENCES processing_stages(stage_id) ON DELETE RESTRICT"
    },
    {
     "n": "processing_jobs_pkey",
     "type": "PK",
     "def": "PRIMARY KEY (job_id)"
    },
    {
     "n": "processing_jobs_job_uuid_key",
     "type": "UNIQUE",
     "def": "UNIQUE (job_uuid)"
    },
    {
     "n": "uq_job_scene_stage_attempt",
     "type": "UNIQUE",
     "def": "UNIQUE (scene_id, stage_id, attempt_number)"
    }
   ]
  },
  "processing_logs": {
   "desc": "Log pipeline terstruktur append-only: satu baris per kejadian tahap (STARTED/RUNNING/COMPLETED/FAILED).",
   "cols": [
    {
     "n": "log_id",
     "t": "bigint",
     "nn": true,
     "d": "nextval('processing_logs_log_id_seq'::regclass)",
     "k": "PK",
     "ds": "PK surrogate."
    },
    {
     "n": "log_uuid",
     "t": "uuid",
     "nn": true,
     "d": "gen_random_uuid()",
     "k": "UNIQUE",
     "ds": "UUID stabil untuk referensi eksternal."
    },
    {
     "n": "dataset_id",
     "t": "integer",
     "nn": true,
     "d": "",
     "k": "FK→datasets",
     "ds": "FK -> datasets."
    },
    {
     "n": "scene_id",
     "t": "character varying(255)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Kunci unit kerja sebagai teks (product identifier S1 atau tanggal aux), bukan FK."
    },
    {
     "n": "module",
     "t": "character varying(50)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Modul ETL penulis log, mis. M5_ORCH."
    },
    {
     "n": "stage",
     "t": "character varying(50)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Nama tahap, mis. DOWNLOAD, FUSION."
    },
    {
     "n": "status",
     "t": "character varying(20)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "STARTED \\"
    },
    {
     "n": "message",
     "t": "text",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Pesan log (Bahasa Inggris, M21)."
    },
    {
     "n": "details",
     "t": "jsonb",
     "nn": true,
     "d": "'{}'::jsonb",
     "k": "",
     "ds": "Detail terstruktur (durasi, ukuran, memori, kualitas) dalam JSONB."
    },
    {
     "n": "created_at",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "now()",
     "k": "",
     "ds": "Waktu kejadian."
    }
   ],
   "cons": [
    {
     "n": "processing_logs_dataset_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (dataset_id) REFERENCES datasets(dataset_id) ON DELETE CASCADE"
    },
    {
     "n": "processing_logs_pkey",
     "type": "PK",
     "def": "PRIMARY KEY (log_id)"
    },
    {
     "n": "processing_logs_log_uuid_key",
     "type": "UNIQUE",
     "def": "UNIQUE (log_uuid)"
    }
   ]
  },
  "processing_stages": {
   "desc": "Master tahap pipeline (S1/MODIS/GPM/FUSION/PREVIEW + HYDROMET_AGGREGATE, ALERT_CHECK, WATER_CHANGE, REPORT_BUILD).",
   "cols": [
    {
     "n": "stage_id",
     "t": "integer",
     "nn": true,
     "d": "nextval('processing_stages_stage_id_seq'::regclass)",
     "k": "PK",
     "ds": "PK surrogate."
    },
    {
     "n": "stage_name",
     "t": "character varying(50)",
     "nn": true,
     "d": "",
     "k": "UNIQUE",
     "ds": "Nama tahap yang dipakai kode, mis. LEE_FILTER, GOLD_EXPORT, HYDROMET_AGGREGATE."
    },
    {
     "n": "stage_code",
     "t": "character varying(20)",
     "nn": true,
     "d": "",
     "k": "UNIQUE",
     "ds": "Kode pendek tahap, mis. LF, GE, HA."
    },
    {
     "n": "stage_order",
     "t": "smallint",
     "nn": true,
     "d": "",
     "k": "UNIQUE",
     "ds": "Urutan pendaftaran (unik). Urutan eksekusi nyata ditentukan kode orchestrator."
    },
    {
     "n": "description",
     "t": "text",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Uraian tahap."
    },
    {
     "n": "source_code",
     "t": "character varying(20)",
     "nn": false,
     "d": "",
     "k": "FK→satellite_sources",
     "ds": "FK -> satellite_sources.source_code bila tahap khusus satu sumber; NULL = lintas sumber."
    },
    {
     "n": "timeout_minutes",
     "t": "smallint",
     "nn": true,
     "d": "60",
     "k": "",
     "ds": "Batas waktu tahap (menit)."
    },
    {
     "n": "retry_count",
     "t": "smallint",
     "nn": true,
     "d": "3",
     "k": "",
     "ds": "Jumlah percobaan ulang yang diizinkan."
    },
    {
     "n": "retry_delay_sec",
     "t": "smallint",
     "nn": true,
     "d": "30",
     "k": "",
     "ds": "Jeda antar percobaan ulang (detik)."
    },
    {
     "n": "is_mandatory",
     "t": "boolean",
     "nn": true,
     "d": "true",
     "k": "",
     "ds": "false = tahap opsional (mis. PREVIEW)."
    },
    {
     "n": "is_active",
     "t": "boolean",
     "nn": true,
     "d": "true",
     "k": "",
     "ds": "false = tahap tidak dipakai lagi."
    },
    {
     "n": "created_at",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "now()",
     "k": "",
     "ds": "Waktu baris dibuat."
    },
    {
     "n": "updated_at",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "now()",
     "k": "",
     "ds": "Waktu baris terakhir diubah (trigger)."
    }
   ],
   "cons": [
    {
     "n": "processing_stages_source_code_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (source_code) REFERENCES satellite_sources(source_code) ON UPDATE CASCADE"
    },
    {
     "n": "processing_stages_pkey",
     "type": "PK",
     "def": "PRIMARY KEY (stage_id)"
    },
    {
     "n": "processing_stages_stage_code_key",
     "type": "UNIQUE",
     "def": "UNIQUE (stage_code)"
    },
    {
     "n": "processing_stages_stage_name_key",
     "type": "UNIQUE",
     "def": "UNIQUE (stage_name)"
    },
    {
     "n": "processing_stages_stage_order_key",
     "type": "UNIQUE",
     "def": "UNIQUE (stage_order)"
    }
   ]
  },
  "quality_alerts": {
   "desc": "Peringatan kualitas/operasional pipeline (mis. skor QA < 60). Tabel alert_events DataLab yang diganti nama; nama alert_events kini untuk alert hujan.",
   "cols": [
    {
     "n": "alert_id",
     "t": "bigint",
     "nn": true,
     "d": "nextval('quality_alerts_alert_id_seq'::regclass)",
     "k": "PK",
     "ds": "PK surrogate."
    },
    {
     "n": "alert_uuid",
     "t": "uuid",
     "nn": true,
     "d": "gen_random_uuid()",
     "k": "UNIQUE",
     "ds": "UUID stabil untuk referensi eksternal."
    },
    {
     "n": "event_type",
     "t": "alert_event_type_enum",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "DATA_ARRIVAL \\"
    },
    {
     "n": "severity",
     "t": "alert_severity_enum",
     "nn": true,
     "d": "'INFO'::alert_severity_enum",
     "k": "",
     "ds": "INFO \\"
    },
    {
     "n": "scene_id",
     "t": "integer",
     "nn": false,
     "d": "",
     "k": "FK→satellite_scenes",
     "ds": "FK -> satellite_scenes terkait."
    },
    {
     "n": "job_id",
     "t": "bigint",
     "nn": false,
     "d": "",
     "k": "FK→processing_jobs",
     "ds": "FK -> processing_jobs terkait."
    },
    {
     "n": "product_id",
     "t": "bigint",
     "nn": false,
     "d": "",
     "k": "FK→data_products",
     "ds": "FK -> data_products terkait."
    },
    {
     "n": "title",
     "t": "character varying(200)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Judul singkat."
    },
    {
     "n": "message",
     "t": "text",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Uraian peringatan."
    },
    {
     "n": "metadata_json",
     "t": "jsonb",
     "nn": false,
     "d": "'{}'::jsonb",
     "k": "",
     "ds": "Konteks terstruktur (JSONB): skor, band, ambang."
    },
    {
     "n": "is_resolved",
     "t": "boolean",
     "nn": true,
     "d": "false",
     "k": "",
     "ds": "true = sudah ditangani."
    },
    {
     "n": "resolved_at",
     "t": "timestamp with time zone",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Waktu ditangani."
    },
    {
     "n": "resolved_by",
     "t": "character varying(100)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Penangan (teks bebas, warisan)."
    },
    {
     "n": "resolution_note",
     "t": "text",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Catatan penanganan."
    },
    {
     "n": "triggered_at",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "now()",
     "k": "",
     "ds": "Waktu peringatan terpicu."
    },
    {
     "n": "created_at",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "now()",
     "k": "",
     "ds": "Waktu baris dibuat."
    }
   ],
   "cons": [
    {
     "n": "quality_alerts_job_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (job_id) REFERENCES processing_jobs(job_id) ON DELETE SET NULL"
    },
    {
     "n": "quality_alerts_product_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (product_id) REFERENCES data_products(product_id) ON DELETE SET NULL"
    },
    {
     "n": "quality_alerts_scene_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (scene_id) REFERENCES satellite_scenes(scene_id) ON DELETE SET NULL"
    },
    {
     "n": "quality_alerts_pkey",
     "type": "PK",
     "def": "PRIMARY KEY (alert_id)"
    },
    {
     "n": "quality_alerts_alert_uuid_key",
     "type": "UNIQUE",
     "def": "UNIQUE (alert_uuid)"
    }
   ]
  },
  "quality_metrics": {
   "desc": "Hasil kontrol kualitas radiometrik per scene S1 per band (tahap QUALITY_ANALYTICS).",
   "cols": [
    {
     "n": "metric_id",
     "t": "bigint",
     "nn": true,
     "d": "nextval('quality_metrics_metric_id_seq'::regclass)",
     "k": "PK",
     "ds": "PK surrogate."
    },
    {
     "n": "scene_id",
     "t": "integer",
     "nn": true,
     "d": "",
     "k": "FK→satellite_scenes, UNIQUE",
     "ds": "FK -> satellite_scenes."
    },
    {
     "n": "product_id",
     "t": "bigint",
     "nn": true,
     "d": "",
     "k": "FK→data_products, UNIQUE",
     "ds": "FK -> data_products: COG yang dinilai."
    },
    {
     "n": "band_name",
     "t": "character varying(10)",
     "nn": true,
     "d": "",
     "k": "UNIQUE",
     "ds": "VV \\"
    },
    {
     "n": "assessed_at",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "now()",
     "k": "",
     "ds": "Waktu penilaian."
    },
    {
     "n": "total_pixels",
     "t": "bigint",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Jumlah piksel raster."
    },
    {
     "n": "valid_pixels",
     "t": "bigint",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Jumlah piksel bernilai sah."
    },
    {
     "n": "nodata_pixels",
     "t": "bigint",
     "nn": true,
     "d": "0",
     "k": "",
     "ds": "Jumlah piksel NoData."
    },
    {
     "n": "nodata_percent",
     "t": "numeric(5,2)",
     "nn": false,
     "d": "GENERATED",
     "k": "",
     "ds": "Persen NoData (%), GENERATED."
    },
    {
     "n": "backscatter_mean_db",
     "t": "numeric(8,4)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Rata-rata backscatter (dB)."
    },
    {
     "n": "backscatter_std_db",
     "t": "numeric(8,4)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Simpangan baku backscatter (dB)."
    },
    {
     "n": "backscatter_min_db",
     "t": "numeric(8,4)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Backscatter minimum (dB)."
    },
    {
     "n": "backscatter_max_db",
     "t": "numeric(8,4)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Backscatter maksimum (dB)."
    },
    {
     "n": "cloud_threshold_percent",
     "t": "numeric(5,2)",
     "nn": true,
     "d": "20.0",
     "k": "",
     "ds": "Ambang awan (%) warisan; tidak relevan untuk SAR."
    },
    {
     "n": "radiometric_consistency",
     "t": "boolean",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "true bila rata-rata backscatter dalam rentang sah (-35..5 dB)."
    },
    {
     "n": "speckle_index",
     "t": "numeric(8,4)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Indeks speckle (koefisien variasi); makin kecil makin baik."
    },
    {
     "n": "quality_score",
     "t": "numeric(5,2)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Skor komposit 0-100 (bobot 50 NoData / 30 speckle / 20 radiometrik)."
    },
    {
     "n": "quality_flag",
     "t": "character varying(20)",
     "nn": true,
     "d": "'UNCHECKED'::character varying",
     "k": "",
     "ds": "PASS \\"
    },
    {
     "n": "notes",
     "t": "text",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Catatan bebas."
    },
    {
     "n": "created_at",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "now()",
     "k": "",
     "ds": "Waktu baris dibuat."
    }
   ],
   "cons": [
    {
     "n": "chk_quality_score_range",
     "type": "CHECK",
     "def": "CHECK (((quality_score >= (0)::numeric) AND (quality_score <= (100)::numeric)))"
    },
    {
     "n": "quality_metrics_quality_flag_check",
     "type": "CHECK",
     "def": "CHECK (((quality_flag)::text = ANY (ARRAY[('PASS'::character varying)::text, ('WARNING'::character varying)::text, ('FAIL'::character varying)::text, ('UNCHECKED'::character varying)::text])))"
    },
    {
     "n": "quality_metrics_product_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (product_id) REFERENCES data_products(product_id) ON DELETE CASCADE"
    },
    {
     "n": "quality_metrics_scene_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (scene_id) REFERENCES satellite_scenes(scene_id) ON DELETE CASCADE"
    },
    {
     "n": "quality_metrics_pkey",
     "type": "PK",
     "def": "PRIMARY KEY (metric_id)"
    },
    {
     "n": "uq_quality_scene_product_band",
     "type": "UNIQUE",
     "def": "UNIQUE (scene_id, product_id, band_name)"
    }
   ]
  },
  "quality_thresholds": {
   "desc": "Ambang kontrol kualitas per band (menggantikan processing_rules). Dibaca module6_analytics; bobot skor 50/30/20 tetap konstanta kode.",
   "cols": [
    {
     "n": "threshold_id",
     "t": "smallint",
     "nn": true,
     "d": "nextval('quality_thresholds_threshold_id_seq'::regclass)",
     "k": "PK",
     "ds": "PK surrogate."
    },
    {
     "n": "band_id",
     "t": "smallint",
     "nn": true,
     "d": "",
     "k": "FK→spectral_bands, UNIQUE",
     "ds": "FK -> spectral_bands."
    },
    {
     "n": "metric_name",
     "t": "character varying(40)",
     "nn": true,
     "d": "",
     "k": "UNIQUE",
     "ds": "Metrik yang diuji: quality_score \\"
    },
    {
     "n": "warn_below",
     "t": "numeric",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Nilai di bawah ini -> WARNING. NULL = tidak diuji."
    },
    {
     "n": "fail_below",
     "t": "numeric",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Nilai di bawah ini -> FAIL. Contoh: quality_score 60."
    },
    {
     "n": "warn_above",
     "t": "numeric",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Nilai di atas ini -> WARNING. NULL = tidak diuji."
    },
    {
     "n": "fail_above",
     "t": "numeric",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Nilai di atas ini -> FAIL. NULL = tidak diuji."
    },
    {
     "n": "reference",
     "t": "character varying(150)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Rujukan asal ambang."
    },
    {
     "n": "is_active",
     "t": "boolean",
     "nn": true,
     "d": "true",
     "k": "",
     "ds": "false = ambang tidak dipakai."
    }
   ],
   "cons": [
    {
     "n": "quality_thresholds_check",
     "type": "CHECK",
     "def": "CHECK (((fail_below IS NULL) OR (warn_below IS NULL) OR (fail_below <= warn_below)))"
    },
    {
     "n": "quality_thresholds_check1",
     "type": "CHECK",
     "def": "CHECK (((fail_above IS NULL) OR (warn_above IS NULL) OR (fail_above >= warn_above)))"
    },
    {
     "n": "quality_thresholds_metric_name_check",
     "type": "CHECK",
     "def": "CHECK (((metric_name)::text = ANY (ARRAY[('quality_score'::character varying)::text, ('nodata_percent'::character varying)::text, ('valid_fraction'::character varying)::text, ('speckle_index'::character varying)::text])))"
    },
    {
     "n": "quality_thresholds_band_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (band_id) REFERENCES spectral_bands(band_id)"
    },
    {
     "n": "quality_thresholds_pkey",
     "type": "PK",
     "def": "PRIMARY KEY (threshold_id)"
    },
    {
     "n": "quality_thresholds_band_id_metric_name_key",
     "type": "UNIQUE",
     "def": "UNIQUE (band_id, metric_name)"
    }
   ]
  },
  "region_observations": {
   "desc": "Deret waktu dataset utama: nilai per kecamatan per band dari GPM/MODIS (harian) dan Sentinel-1 (per lintasan: VV, VH, WATER_PCT) (M7, M58). Tidak pernah dihapus retensi raster. Dasar grafik, statistik, alert, laporan.",
   "cols": [
    {
     "n": "obs_id",
     "t": "bigint",
     "nn": true,
     "d": "nextval('region_observations_obs_id_seq'::regclass)",
     "k": "PK",
     "ds": "PK surrogate."
    },
    {
     "n": "region_id",
     "t": "integer",
     "nn": true,
     "d": "",
     "k": "FK→administrative_regions, UNIQUE",
     "ds": "FK -> administrative_regions (kecamatan level 3)."
    },
    {
     "n": "band_id",
     "t": "smallint",
     "nn": true,
     "d": "",
     "k": "FK→spectral_bands, UNIQUE",
     "ds": "FK -> spectral_bands, mis. RAIN_24H, NDVI, FLOOD, VH, WATER_PCT."
    },
    {
     "n": "obs_date",
     "t": "date",
     "nn": true,
     "d": "",
     "k": "UNIQUE",
     "ds": "Tanggal pengamatan = hari UTC (07.00-07.00 WIB, M28)."
    },
    {
     "n": "value",
     "t": "numeric(10,4)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Nilai agregat (satuan band: mm, indeks, %). NULL bila valid_fraction < 0,1."
    },
    {
     "n": "valid_fraction",
     "t": "numeric(5,4)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Bagian poligon yang punya piksel valid (0-1)."
    },
    {
     "n": "source_product_id",
     "t": "bigint",
     "nn": false,
     "d": "",
     "k": "FK→data_products",
     "ds": "FK -> data_products: COG asal nilai (lineage, RM2)."
    },
    {
     "n": "run_type",
     "t": "character varying(5)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Run IMERG untuk band GPM: F \\"
    },
    {
     "n": "job_id",
     "t": "bigint",
     "nn": false,
     "d": "",
     "k": "FK→dataset_jobs",
     "ds": "FK -> dataset_jobs yang menghitung nilai."
    },
    {
     "n": "computed_at",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "now()",
     "k": "",
     "ds": "Waktu nilai dihitung."
    }
   ],
   "cons": [
    {
     "n": "region_observations_run_type_check",
     "type": "CHECK",
     "def": "CHECK (((run_type)::text = ANY (ARRAY[('F'::character varying)::text, ('L'::character varying)::text, ('E'::character varying)::text])))"
    },
    {
     "n": "region_observations_valid_fraction_check",
     "type": "CHECK",
     "def": "CHECK (((valid_fraction >= (0)::numeric) AND (valid_fraction <= (1)::numeric)))"
    },
    {
     "n": "region_observations_band_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (band_id) REFERENCES spectral_bands(band_id)"
    },
    {
     "n": "region_observations_job_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (job_id) REFERENCES dataset_jobs(job_id) ON DELETE SET NULL"
    },
    {
     "n": "region_observations_region_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (region_id) REFERENCES administrative_regions(region_id)"
    },
    {
     "n": "region_observations_source_product_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (source_product_id) REFERENCES data_products(product_id) ON DELETE SET NULL"
    },
    {
     "n": "region_observations_pkey",
     "type": "PK",
     "def": "PRIMARY KEY (obs_id)"
    },
    {
     "n": "uq_region_obs",
     "type": "UNIQUE",
     "def": "UNIQUE (region_id, band_id, obs_date)"
    }
   ]
  },
  "regions_of_interest": {
   "desc": "AOI dataset (bbox) warisan DataLab. Baris baru hanya dari kecamatan atau gabungan kecamatan (M27); tepat satu baris adalah AOI GMLS (is_monitor_aoi).",
   "cols": [
    {
     "n": "region_id",
     "t": "integer",
     "nn": true,
     "d": "nextval('regions_of_interest_region_id_seq'::regclass)",
     "k": "PK",
     "ds": "PK surrogate. Dirujuk datasets, satellite_scenes, nasa_scenes, fusion_products, live_areas."
    },
    {
     "n": "region_code",
     "t": "character varying(20)",
     "nn": true,
     "d": "",
     "k": "UNIQUE",
     "ds": "Alternate key, mis. GMLS_AOI atau ID3602xxx."
    },
    {
     "n": "name",
     "t": "character varying(100)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Nama tampilan ROI."
    },
    {
     "n": "description",
     "t": "text",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Keterangan bebas."
    },
    {
     "n": "bbox",
     "t": "geometry(Polygon,4326)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Kotak pembatas WGS84 (Polygon EPSG:4326) yang dipakai pencarian scene dan crop."
    },
    {
     "n": "centroid",
     "t": "geometry(Point,4326)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Titik tengah bbox, diisi trg_roi_centroid."
    },
    {
     "n": "area_km2",
     "t": "numeric(12,4)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Luas bbox (km2)."
    },
    {
     "n": "admin_level",
     "t": "smallint",
     "nn": true,
     "d": "3",
     "k": "",
     "ds": "Tingkat administratif ROI (warisan): 2 kabupaten, 3 kecamatan."
    },
    {
     "n": "country_code",
     "t": "character(2)",
     "nn": true,
     "d": "'ID'::bpchar",
     "k": "",
     "ds": "Kode negara ISO 3166-1 alpha-2, selalu ID."
    },
    {
     "n": "is_active",
     "t": "boolean",
     "nn": true,
     "d": "true",
     "k": "",
     "ds": "false = ROI dinonaktifkan (warisan; penghapusan memakai deleted_at)."
    },
    {
     "n": "source",
     "t": "character varying(20)",
     "nn": true,
     "d": "'SYSTEM'::character varying",
     "k": "",
     "ds": "Asal baris: SEEDER (seed) \\"
    },
    {
     "n": "admin_region_id",
     "t": "integer",
     "nn": false,
     "d": "",
     "k": "FK→administrative_regions",
     "ds": "FK -> administrative_regions bila ROI = satu kecamatan; NULL untuk gabungan."
    },
    {
     "n": "is_monitor_aoi",
     "t": "boolean",
     "nn": true,
     "d": "false",
     "k": "",
     "ds": "true = ROI AOI GMLS (bbox = ST_Envelope(ST_Union) kecamatan in_aoi). Paling banyak satu baris."
    },
    {
     "n": "deleted_at",
     "t": "timestamp with time zone",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Soft delete. NULL = aktif. Baris tidak dihapus fisik karena dirujuk FK."
    },
    {
     "n": "created_at",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "now()",
     "k": "",
     "ds": "Waktu baris dibuat."
    },
    {
     "n": "updated_at",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "now()",
     "k": "",
     "ds": "Waktu baris terakhir diubah (trigger)."
    }
   ],
   "cons": [
    {
     "n": "regions_of_interest_source_check",
     "type": "CHECK",
     "def": "CHECK (((source)::text = ANY (ARRAY[('SEEDER'::character varying)::text, ('SYSTEM'::character varying)::text])))"
    },
    {
     "n": "regions_of_interest_admin_region_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (admin_region_id) REFERENCES administrative_regions(region_id)"
    },
    {
     "n": "regions_of_interest_pkey",
     "type": "PK",
     "def": "PRIMARY KEY (region_id)"
    },
    {
     "n": "regions_of_interest_region_code_key",
     "type": "UNIQUE",
     "def": "UNIQUE (region_code)"
    }
   ]
  },
  "report_types": {
   "desc": "Master jenis laporan periodik (M18): Hidromet untuk ANALYST, Kesehatan Data untuk DATA_ENGINEER.",
   "cols": [
    {
     "n": "report_type_id",
     "t": "smallint",
     "nn": true,
     "d": "nextval('report_types_report_type_id_seq'::regclass)",
     "k": "PK",
     "ds": "PK surrogate."
    },
    {
     "n": "report_code",
     "t": "character varying(30)",
     "nn": true,
     "d": "",
     "k": "UNIQUE",
     "ds": "Alternate key: HYDROMET_WEEKLY \\"
    },
    {
     "n": "report_name",
     "t": "character varying(100)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Label UI."
    },
    {
     "n": "period",
     "t": "character varying(10)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "WEEKLY \\"
    },
    {
     "n": "audience_role_id",
     "t": "smallint",
     "nn": true,
     "d": "",
     "k": "FK→roles",
     "ds": "FK -> roles: role audiens (dipakai RLS generated_reports)."
    },
    {
     "n": "template_version",
     "t": "character varying(10)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Versi template PDF, mis. 1.0."
    }
   ],
   "cons": [
    {
     "n": "report_types_period_check",
     "type": "CHECK",
     "def": "CHECK (((period)::text = ANY (ARRAY[('WEEKLY'::character varying)::text, ('MONTHLY'::character varying)::text])))"
    },
    {
     "n": "report_types_audience_role_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (audience_role_id) REFERENCES roles(role_id)"
    },
    {
     "n": "report_types_pkey",
     "type": "PK",
     "def": "PRIMARY KEY (report_type_id)"
    },
    {
     "n": "report_types_report_code_key",
     "type": "UNIQUE",
     "def": "UNIQUE (report_code)"
    }
   ]
  },
  "roles": {
   "desc": "Master role aplikasi (5 role, M13). Setiap role dipetakan ke satu role PostgreSQL yang dipakai lewat SET LOCAL ROLE.",
   "cols": [
    {
     "n": "role_id",
     "t": "smallint",
     "nn": true,
     "d": "nextval('roles_role_id_seq'::regclass)",
     "k": "PK",
     "ds": "PK surrogate."
    },
    {
     "n": "role_code",
     "t": "character varying(20)",
     "nn": true,
     "d": "",
     "k": "UNIQUE",
     "ds": "Alternate key. PUBLIC \\"
    },
    {
     "n": "role_name",
     "t": "character varying(50)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Label role untuk UI (Bahasa Indonesia), mis. \"Relawan\"."
    },
    {
     "n": "db_role",
     "t": "character varying(40)",
     "nn": true,
     "d": "",
     "k": "UNIQUE",
     "ds": "Nama role PostgreSQL padanannya, mis. monitor_analyst (DATABASE.md §8.1)."
    },
    {
     "n": "requires_login",
     "t": "boolean",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "false hanya untuk PUBLIC (pengunjung tanpa akun)."
    },
    {
     "n": "description",
     "t": "text",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Uraian singkat kebutuhan akses role ini."
    }
   ],
   "cons": [
    {
     "n": "roles_pkey",
     "type": "PK",
     "def": "PRIMARY KEY (role_id)"
    },
    {
     "n": "roles_db_role_key",
     "type": "UNIQUE",
     "def": "UNIQUE (db_role)"
    },
    {
     "n": "roles_role_code_key",
     "type": "UNIQUE",
     "def": "UNIQUE (role_code)"
    }
   ]
  },
  "satellite_scenes": {
   "desc": "Registri scene Sentinel-1 GRD yang ditemukan/diunduh. Soft delete ADMIN lewat is_valid (M24).",
   "cols": [
    {
     "n": "scene_id",
     "t": "integer",
     "nn": true,
     "d": "nextval('satellite_scenes_scene_id_seq'::regclass)",
     "k": "PK",
     "ds": "PK surrogate."
    },
    {
     "n": "scene_uuid",
     "t": "uuid",
     "nn": true,
     "d": "gen_random_uuid()",
     "k": "UNIQUE",
     "ds": "UUID stabil untuk referensi eksternal."
    },
    {
     "n": "product_identifier",
     "t": "character varying(200)",
     "nn": true,
     "d": "",
     "k": "UNIQUE",
     "ds": "Identifier produk ESA (unik global), mis. S1A_IW_GRDH_1SDV_..._B5C2."
    },
    {
     "n": "platform",
     "t": "character varying(20)",
     "nn": true,
     "d": "'SENTINEL-1'::character varying",
     "k": "",
     "ds": "Platform, default SENTINEL-1."
    },
    {
     "n": "instrument_mode",
     "t": "character varying(10)",
     "nn": true,
     "d": "'IW'::character varying",
     "k": "",
     "ds": "Mode akuisisi: IW (Interferometric Wide)."
    },
    {
     "n": "polarization_vv",
     "t": "boolean",
     "nn": true,
     "d": "true",
     "k": "",
     "ds": "true bila produk memuat polarisasi VV."
    },
    {
     "n": "polarization_vh",
     "t": "boolean",
     "nn": true,
     "d": "true",
     "k": "",
     "ds": "true bila produk memuat polarisasi VH."
    },
    {
     "n": "acquisition_datetime",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Waktu akuisisi (UTC). Sumbu waktu utama."
    },
    {
     "n": "orbit_number",
     "t": "integer",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Nomor orbit absolut."
    },
    {
     "n": "orbit_direction",
     "t": "orbit_direction_enum",
     "nn": true,
     "d": "'ASCENDING'::orbit_direction_enum",
     "k": "",
     "ds": "ASCENDING \\"
    },
    {
     "n": "relative_orbit",
     "t": "smallint",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Nomor orbit relatif (track); dipakai menandai perubahan air antar orbit berbeda."
    },
    {
     "n": "bbox",
     "t": "geometry(Polygon,4326)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Footprint scene (Polygon EPSG:4326). Keterbatasan warisan: belum akurat (D17)."
    },
    {
     "n": "cloud_cover_percent",
     "t": "numeric(5,2)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Persen awan (tidak relevan untuk SAR; warisan)."
    },
    {
     "n": "incidence_angle_near",
     "t": "numeric(6,3)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Sudut datang near-range (derajat)."
    },
    {
     "n": "incidence_angle_far",
     "t": "numeric(6,3)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Sudut datang far-range (derajat)."
    },
    {
     "n": "resolution_m",
     "t": "smallint",
     "nn": true,
     "d": "10",
     "k": "",
     "ds": "Resolusi piksel nominal (meter)."
    },
    {
     "n": "region_id",
     "t": "integer",
     "nn": true,
     "d": "",
     "k": "FK→regions_of_interest",
     "ds": "FK -> regions_of_interest: ROI pencarian scene."
    },
    {
     "n": "raw_file_path",
     "t": "text",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Path berkas unduhan asli (bisa sudah dihapus setelah diproses)."
    },
    {
     "n": "raw_file_size_mb",
     "t": "numeric(12,3)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Ukuran berkas unduhan (MB)."
    },
    {
     "n": "download_url",
     "t": "text",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "URL unduhan CDSE."
    },
    {
     "n": "checksum_md5",
     "t": "character varying(32)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Checksum MD5 dari penyedia."
    },
    {
     "n": "is_available",
     "t": "boolean",
     "nn": true,
     "d": "true",
     "k": "",
     "ds": "false = scene tidak tersedia lagi di penyedia/disk."
    },
    {
     "n": "is_valid",
     "t": "boolean",
     "nn": true,
     "d": "true",
     "k": "",
     "ds": "false = dinonaktifkan ADMIN (soft delete, M24)."
    },
    {
     "n": "invalidated_by",
     "t": "integer",
     "nn": false,
     "d": "",
     "k": "FK→users",
     "ds": "FK -> users: ADMIN yang menonaktifkan."
    },
    {
     "n": "invalidated_at",
     "t": "timestamp with time zone",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Waktu dinonaktifkan."
    },
    {
     "n": "invalid_reason",
     "t": "text",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Alasan wajib saat dinonaktifkan."
    },
    {
     "n": "created_at",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "now()",
     "k": "",
     "ds": "Waktu baris dibuat."
    },
    {
     "n": "updated_at",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "now()",
     "k": "",
     "ds": "Waktu baris terakhir diubah (trigger)."
    }
   ],
   "cons": [
    {
     "n": "chk_scene_invalidation",
     "type": "CHECK",
     "def": "CHECK ((is_valid OR ((invalidated_at IS NOT NULL) AND (invalid_reason IS NOT NULL))))"
    },
    {
     "n": "satellite_scenes_cloud_cover_percent_check",
     "type": "CHECK",
     "def": "CHECK (((cloud_cover_percent >= (0)::numeric) AND (cloud_cover_percent <= (100)::numeric)))"
    },
    {
     "n": "satellite_scenes_invalidated_by_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (invalidated_by) REFERENCES users(user_id)"
    },
    {
     "n": "satellite_scenes_region_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (region_id) REFERENCES regions_of_interest(region_id) ON DELETE RESTRICT"
    },
    {
     "n": "satellite_scenes_pkey",
     "type": "PK",
     "def": "PRIMARY KEY (scene_id)"
    },
    {
     "n": "satellite_scenes_product_identifier_key",
     "type": "UNIQUE",
     "def": "UNIQUE (product_identifier)"
    },
    {
     "n": "satellite_scenes_scene_uuid_key",
     "type": "UNIQUE",
     "def": "UNIQUE (scene_uuid)"
    }
   ]
  },
  "satellite_sources": {
   "desc": "Master sumber data. Kolom VARCHAR \"source\" warisan DataLab dihubungkan ke source_code lewat FK.",
   "cols": [
    {
     "n": "source_id",
     "t": "smallint",
     "nn": true,
     "d": "nextval('satellite_sources_source_id_seq'::regclass)",
     "k": "PK",
     "ds": "PK surrogate."
    },
    {
     "n": "source_code",
     "t": "character varying(20)",
     "nn": true,
     "d": "",
     "k": "UNIQUE",
     "ds": "Alternate key: SENTINEL1 \\"
    },
    {
     "n": "source_name",
     "t": "character varying(100)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Nama tampilan, mis. \"Sentinel-1 SAR\"."
    },
    {
     "n": "provider",
     "t": "character varying(50)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Penyedia data: ESA/CDSE, NASA LANCE/LAADS, NASA GES DISC."
    },
    {
     "n": "sensor_type",
     "t": "character varying(20)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "SAR \\"
    },
    {
     "n": "spatial_resolution_m",
     "t": "numeric(8,1)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Resolusi spasial nominal (meter): 10 / 250 / 11000."
    },
    {
     "n": "nominal_revisit_days",
     "t": "numeric(4,1)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Revisit nominal (hari). Angka nyata dihitung dari data (v_kelengkapan_data)."
    },
    {
     "n": "products",
     "t": "text",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Produk yang diambil, mis. \"GRD IW\" atau \"GPM_3IMERGDF, DL, DE\"."
    }
   ],
   "cons": [
    {
     "n": "satellite_sources_sensor_type_check",
     "type": "CHECK",
     "def": "CHECK (((sensor_type)::text = ANY (ARRAY[('SAR'::character varying)::text, ('OPTICAL'::character varying)::text, ('PRECIPITATION'::character varying)::text, ('DERIVED'::character varying)::text])))"
    },
    {
     "n": "satellite_sources_pkey",
     "type": "PK",
     "def": "PRIMARY KEY (source_id)"
    },
    {
     "n": "satellite_sources_source_code_key",
     "type": "UNIQUE",
     "def": "UNIQUE (source_code)"
    }
   ]
  },
  "scene_job_state": {
   "desc": "Status per scene S1 di dalam satu dataset_job; dasar resume setelah proses mati.",
   "cols": [
    {
     "n": "id",
     "t": "bigint",
     "nn": true,
     "d": "nextval('scene_job_state_id_seq'::regclass)",
     "k": "PK",
     "ds": "PK surrogate."
    },
    {
     "n": "job_id",
     "t": "bigint",
     "nn": true,
     "d": "",
     "k": "FK→dataset_jobs, UNIQUE",
     "ds": "FK -> dataset_jobs."
    },
    {
     "n": "product_identifier",
     "t": "character varying(200)",
     "nn": true,
     "d": "",
     "k": "UNIQUE",
     "ds": "Identifier produk ESA scene ini."
    },
    {
     "n": "scene_id",
     "t": "integer",
     "nn": false,
     "d": "",
     "k": "FK→satellite_scenes",
     "ds": "FK -> satellite_scenes; NULL sebelum scene terdaftar."
    },
    {
     "n": "current_stage",
     "t": "character varying(30)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Tahap terakhir yang dicapai, mis. LEE_FILTER, CLEANUP."
    },
    {
     "n": "stage_status",
     "t": "character varying(20)",
     "nn": true,
     "d": "'PENDING'::character varying",
     "k": "",
     "ds": "PENDING \\"
    },
    {
     "n": "produced_files",
     "t": "jsonb",
     "nn": true,
     "d": "'{}'::jsonb",
     "k": "",
     "ds": "Berkas yang dihasilkan per tier (JSONB {tier: [path]}), untuk cleanup."
    },
    {
     "n": "attempt_number",
     "t": "smallint",
     "nn": true,
     "d": "1",
     "k": "",
     "ds": "Percobaan ke berapa."
    },
    {
     "n": "max_retries",
     "t": "smallint",
     "nn": true,
     "d": "3",
     "k": "",
     "ds": "Batas percobaan ulang."
    },
    {
     "n": "last_error",
     "t": "text",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Pesan galat terakhir."
    },
    {
     "n": "created_at",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "now()",
     "k": "",
     "ds": "Waktu baris dibuat."
    },
    {
     "n": "started_at",
     "t": "timestamp with time zone",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Waktu mulai diproses."
    },
    {
     "n": "completed_at",
     "t": "timestamp with time zone",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Waktu selesai."
    }
   ],
   "cons": [
    {
     "n": "chk_scene_job_stage_status",
     "type": "CHECK",
     "def": "CHECK (((stage_status)::text = ANY (ARRAY[('PENDING'::character varying)::text, ('RUNNING'::character varying)::text, ('COMPLETED'::character varying)::text, ('FAILED'::character varying)::text, ('SKIPPED'::character varying)::text])))"
    },
    {
     "n": "scene_job_state_job_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (job_id) REFERENCES dataset_jobs(job_id) ON DELETE CASCADE"
    },
    {
     "n": "scene_job_state_scene_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (scene_id) REFERENCES satellite_scenes(scene_id) ON DELETE SET NULL"
    },
    {
     "n": "scene_job_state_pkey",
     "type": "PK",
     "def": "PRIMARY KEY (id)"
    },
    {
     "n": "uq_job_product",
     "type": "UNIQUE",
     "def": "UNIQUE (job_id, product_identifier)"
    }
   ]
  },
  "spectral_bands": {
   "desc": "Master band/variabel yang diamati per sumber; dipakai region_observations, alert_rules, quality_thresholds, live_scene_metrics.",
   "cols": [
    {
     "n": "band_id",
     "t": "smallint",
     "nn": true,
     "d": "nextval('spectral_bands_band_id_seq'::regclass)",
     "k": "PK",
     "ds": "PK surrogate."
    },
    {
     "n": "source_id",
     "t": "smallint",
     "nn": true,
     "d": "",
     "k": "FK→satellite_sources",
     "ds": "FK -> satellite_sources."
    },
    {
     "n": "band_code",
     "t": "character varying(20)",
     "nn": true,
     "d": "",
     "k": "UNIQUE",
     "ds": "Alternate key, mis. VV, NDVI, RAIN_24H, WATER_CHANGE."
    },
    {
     "n": "band_name",
     "t": "character varying(100)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Label UI (Bahasa Indonesia)."
    },
    {
     "n": "unit",
     "t": "character varying(20)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Satuan nilai: dB, index, %, mm, km2."
    },
    {
     "n": "valid_min",
     "t": "numeric",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Batas bawah nilai sah; region_observations di luar rentang ditolak trg_obs_range. NULL = tanpa batas."
    },
    {
     "n": "valid_max",
     "t": "numeric",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Batas atas nilai sah. NULL = tanpa batas."
    },
    {
     "n": "aggregation",
     "t": "character varying(20)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Cara agregasi zonal: MEAN (hujan, NDVI, NDWI, backscatter) atau FRACTION (persen piksel kelas air)."
    }
   ],
   "cons": [
    {
     "n": "spectral_bands_aggregation_check",
     "type": "CHECK",
     "def": "CHECK (((aggregation)::text = ANY (ARRAY[('MEAN'::character varying)::text, ('FRACTION'::character varying)::text])))"
    },
    {
     "n": "spectral_bands_check",
     "type": "CHECK",
     "def": "CHECK (((valid_min IS NULL) OR (valid_max IS NULL) OR (valid_min <= valid_max)))"
    },
    {
     "n": "spectral_bands_source_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (source_id) REFERENCES satellite_sources(source_id)"
    },
    {
     "n": "spectral_bands_pkey",
     "type": "PK",
     "def": "PRIMARY KEY (band_id)"
    },
    {
     "n": "spectral_bands_band_code_key",
     "type": "UNIQUE",
     "def": "UNIQUE (band_code)"
    }
   ]
  },
  "user_activity_logs": {
   "desc": "Log aplikasi append-only: login, logout, unduhan, ekspor, aksi penting (RM4).",
   "cols": [
    {
     "n": "log_id",
     "t": "bigint",
     "nn": true,
     "d": "nextval('user_activity_logs_log_id_seq'::regclass)",
     "k": "PK",
     "ds": "PK surrogate."
    },
    {
     "n": "user_id",
     "t": "integer",
     "nn": false,
     "d": "",
     "k": "FK→users",
     "ds": "FK -> users. NULL untuk login gagal dengan username tak dikenal atau PUBLIC."
    },
    {
     "n": "username_attempted",
     "t": "character varying(50)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Username yang dicoba pada login gagal."
    },
    {
     "n": "action",
     "t": "character varying(30)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "LOGIN_SUCCESS, LOGIN_FAILED, LOGOUT, DOWNLOAD_PRODUCT, DOWNLOAD_DATASET, DOWNLOAD_FUSION, DOWNLOAD_REPORT, EXPORT_CSV, CREATE_DATASET, TRIGGER_INGEST, ..."
    },
    {
     "n": "target_type",
     "t": "character varying(40)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Tabel objek aksi, mis. data_products, datasets, generated_reports."
    },
    {
     "n": "target_id",
     "t": "bigint",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "PK objek aksi."
    },
    {
     "n": "bytes_sent",
     "t": "bigint",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Jumlah byte terkirim (unduhan)."
    },
    {
     "n": "ip_address",
     "t": "inet",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Alamat IP klien."
    },
    {
     "n": "user_agent",
     "t": "character varying(255)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "User-Agent klien (dipotong 255)."
    },
    {
     "n": "detail",
     "t": "jsonb",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Detail tambahan (JSONB), mis. {\"auth\": \"token\"}."
    },
    {
     "n": "logged_at",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "now()",
     "k": "",
     "ds": "Waktu kejadian."
    }
   ],
   "cons": [
    {
     "n": "user_activity_logs_bytes_sent_check",
     "type": "CHECK",
     "def": "CHECK (((bytes_sent IS NULL) OR (bytes_sent >= 0)))"
    },
    {
     "n": "user_activity_logs_user_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (user_id) REFERENCES users(user_id)"
    },
    {
     "n": "user_activity_logs_pkey",
     "type": "PK",
     "def": "PRIMARY KEY (log_id)"
    }
   ]
  },
  "users": {
   "desc": "Akun pengguna yang login (USER s.d. ADMIN). Akun dinonaktifkan, tidak pernah dihapus.",
   "cols": [
    {
     "n": "user_id",
     "t": "integer",
     "nn": true,
     "d": "nextval('users_user_id_seq'::regclass)",
     "k": "PK",
     "ds": "PK surrogate."
    },
    {
     "n": "role_id",
     "t": "smallint",
     "nn": true,
     "d": "",
     "k": "FK→roles",
     "ds": "FK -> roles. Tidak boleh PUBLIC (ditegakkan trg_users_role_not_public)."
    },
    {
     "n": "username",
     "t": "character varying(50)",
     "nn": true,
     "d": "",
     "k": "UNIQUE",
     "ds": "Alternate key, huruf kecil/angka/_/. 3-50 karakter. Contoh: relawan.bayah"
    },
    {
     "n": "password_hash",
     "t": "character varying(255)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Hash bcrypt (cost 12). Tidak pernah dikirim ke klien; disensor di audit_log."
    },
    {
     "n": "full_name",
     "t": "character varying(100)",
     "nn": true,
     "d": "",
     "k": "",
     "ds": "Nama lengkap untuk tampilan."
    },
    {
     "n": "organization",
     "t": "character varying(100)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Asal organisasi, mis. GMLS, BPBD Lebak, kampus."
    },
    {
     "n": "is_active",
     "t": "boolean",
     "nn": true,
     "d": "true",
     "k": "",
     "ds": "false = akun dinonaktifkan ADMIN; login ditolak."
    },
    {
     "n": "failed_login_count",
     "t": "smallint",
     "nn": true,
     "d": "0",
     "k": "",
     "ds": "Jumlah gagal login beruntun; 5 kali -> locked_until diisi."
    },
    {
     "n": "locked_until",
     "t": "timestamp with time zone",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Akun terkunci sementara sampai waktu ini (15 menit setelah 5 kali gagal)."
    },
    {
     "n": "last_login_at",
     "t": "timestamp with time zone",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Waktu login sukses terakhir."
    },
    {
     "n": "created_by",
     "t": "integer",
     "nn": false,
     "d": "",
     "k": "FK→users",
     "ds": "FK -> users: ADMIN yang membuat akun ini. NULL untuk admin pertama (create_admin.py)."
    },
    {
     "n": "created_at",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "now()",
     "k": "",
     "ds": "Waktu akun dibuat."
    },
    {
     "n": "updated_at",
     "t": "timestamp with time zone",
     "nn": true,
     "d": "now()",
     "k": "",
     "ds": "Waktu baris terakhir diubah (trigger)."
    },
    {
     "n": "email",
     "t": "character varying(254)",
     "nn": false,
     "d": "",
     "k": "",
     "ds": "Alamat email (unik, tanpa membedakan huruf besar). Wajib untuk akun hasil registrasi mandiri (M56); NULL untuk akun lama buatan ADMIN."
    }
   ],
   "cons": [
    {
     "n": "users_email_check",
     "type": "CHECK",
     "def": "CHECK (((email IS NULL) OR ((email)::text ~ '^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$'::text)))"
    },
    {
     "n": "users_failed_login_count_check",
     "type": "CHECK",
     "def": "CHECK ((failed_login_count >= 0))"
    },
    {
     "n": "users_username_check",
     "type": "CHECK",
     "def": "CHECK (((username)::text ~ '^[a-z0-9_.]{3,50}$'::text))"
    },
    {
     "n": "users_created_by_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (created_by) REFERENCES users(user_id)"
    },
    {
     "n": "users_role_id_fkey",
     "type": "FK",
     "def": "FOREIGN KEY (role_id) REFERENCES roles(role_id)"
    },
    {
     "n": "users_pkey",
     "type": "PK",
     "def": "PRIMARY KEY (user_id)"
    },
    {
     "n": "users_username_key",
     "type": "UNIQUE",
     "def": "UNIQUE (username)"
    }
   ]
  }
 },
 "views": [
  {
   "name": "v_alert_aktif",
   "cols": [
    "alert_id",
    "observation_date",
    "region_id",
    "pcode",
    "region_name",
    "rule_id",
    "rule_code",
    "disaster_type_code",
    "band_code",
    "observed_value",
    "threshold_value",
    "severity",
    "triggered_at"
   ],
   "desc": "Alert hujan yang belum ditandai dibaca, lengkap dengan nama kecamatan dan aturan. USER+."
  },
  {
   "name": "v_citra_metrics",
   "cols": [
    "live_scene_id",
    "area_id",
    "scene_date",
    "source_code",
    "band_code",
    "band_name",
    "unit",
    "metric_name",
    "value",
    "source_date"
   ],
   "desc": "Metrik numerik per band x metrik untuk scene yang terlihat role pemanggil lewat v_citra_scenes (M56). PUBLIC+."
  },
  {
   "name": "v_citra_obs_aoi",
   "cols": [
    "obs_date",
    "source_code",
    "band_code",
    "band_name",
    "unit",
    "mean_value",
    "max_value",
    "min_value",
    "n_regions",
    "valid_fraction",
    "run_type"
   ],
   "desc": "Angka harian GPM/MODIS (Job Hidromet, termasuk backfill) dirata-rata ke kecamatan AOI, batas waktu per role pemanggil seperti v_citra_scenes; observasi terakhir selalu terlihat (M56). PUBLIC+."
  },
  {
   "name": "v_citra_scenes",
   "cols": [
    "live_scene_id",
    "area_id",
    "area_name",
    "scene_date",
    "status",
    "area_status",
    "interpretations",
    "previews",
    "source_status",
    "files_available"
   ],
   "desc": "Scene citra (Sentinel-1 + MODIS/GPM pendamping) dengan batas waktu per role pemanggil: PUBLIC 30 hari, USER 365 hari, ANALYST/DATA_ENGINEER/ADMIN semua; scene terbaru tiap area selalu terlihat. files_available = PNG masih ada di disk (M56). PUBLIC+."
  },
  {
   "name": "v_evaluasi_alert",
   "cols": [
    "outcome",
    "event_id",
    "alert_id",
    "region_id",
    "ref_date"
   ],
   "desc": "Evaluasi alert WARNING+ terhadap kejadian terverifikasi dengan jendela 0-3 hari: HIT, MISS, FALSE_ALARM. ANALYST, ADMIN."
  },
  {
   "name": "v_hujan_harian_kecamatan",
   "cols": [
    "obs_date",
    "region_id",
    "pcode",
    "region_name",
    "rain_24h_mm",
    "rain_72h_mm",
    "rain_7d_mm",
    "rain_30d_mm",
    "gpm_run",
    "bmkg_category"
   ],
   "desc": "Hujan 24h/72h/7d/30d (mm) per kecamatan per tanggal UTC + run GPM + kategori BMKG hujan 24 jam (RINGAN < 20, SEDANG < 50, LEBAT < 100, SANGAT_LEBAT < 150, EKSTREM). USER+."
  },
  {
   "name": "v_kejadian_dan_hujan",
   "cols": [
    "event_id",
    "event_date",
    "event_end_date",
    "disaster_type_code",
    "region_id",
    "region_name",
    "village_name",
    "is_verified",
    "info_source",
    "rain_24h_h0",
    "rain_72h_h0",
    "rain_7d_h0",
    "rain_24h_h1",
    "rain_72h_h1",
    "rain_7d_h1",
    "rain_24h_h2",
    "rain_72h_h2",
    "rain_7d_h2"
   ],
   "desc": "Kejadian bencana aktif dengan hujan 24h/72h/7d (mm) pada H-0, H-1, H-2 di kecamatannya. ANALYST, ADMIN."
  },
  {
   "name": "v_kelengkapan_data",
   "cols": [
    "source_code",
    "data_date",
    "prev_date",
    "gap_days",
    "is_gap"
   ],
   "desc": "Tanggal yang punya data per sumber (S1 dari satellite_scenes, MODIS/GPM dari nasa_scenes) dengan jarak ke tanggal sebelumnya; is_gap = jarak > 10 hari. DATA_ENGINEER, ADMIN."
  },
  {
   "name": "v_live_scenes_recent",
   "cols": [
    "live_scene_id",
    "area_id",
    "area_name",
    "scene_date",
    "status",
    "area_status",
    "interpretations",
    "previews",
    "source_status"
   ],
   "desc": "Scene Live dalam 30 hari terakhir yang berkasnya masih ada. USER+."
  },
  {
   "name": "v_log_data",
   "cols": [
    "log_ref",
    "logged_at",
    "kind",
    "action",
    "target_type",
    "target_id",
    "user_id",
    "username",
    "detail"
   ],
   "desc": "Log yang menyangkut halaman Data: aktivitas unduhan/backfill/ubah scene dan jejak audit tabel katalog & scene (M56). DATA_ENGINEER, ADMIN."
  },
  {
   "name": "v_log_kejadian",
   "cols": [
    "log_ref",
    "logged_at",
    "kind",
    "action",
    "target_type",
    "target_id",
    "user_id",
    "username",
    "detail"
   ],
   "desc": "Log yang menyangkut halaman Kejadian: jejak audit disaster_events/disaster_types dan ekspor Excel kejadian (M56). ANALYST, ADMIN."
  },
  {
   "name": "v_log_login",
   "cols": [
    "log_id",
    "logged_at",
    "action",
    "user_id",
    "username",
    "username_attempted",
    "ip_address",
    "user_agent",
    "detail"
   ],
   "desc": "Log masuk, keluar, dan registrasi akun mandiri dari user_activity_logs. ADMIN."
  },
  {
   "name": "v_log_unduhan",
   "cols": [
    "log_id",
    "logged_at",
    "action",
    "user_id",
    "username",
    "target_type",
    "target_id",
    "bytes_sent",
    "ip_address",
    "detail"
   ],
   "desc": "Log unduhan dan ekspor CSV dari user_activity_logs. ADMIN."
  },
  {
   "name": "v_public_kejadian",
   "cols": [
    "event_id",
    "disaster_type_code",
    "disaster_type_name",
    "region_id",
    "pcode",
    "region_name",
    "village_name",
    "lat",
    "lon",
    "event_date",
    "event_end_date",
    "description",
    "impact_summary",
    "info_source",
    "is_verified"
   ],
   "desc": "Kejadian bencana 365 hari terakhir untuk PUBLIC, tanpa source_reference/recorded_by/verified_by (M56). Role login membaca disaster_events langsung tanpa batas waktu."
  },
  {
   "name": "v_public_live_latest",
   "cols": [
    "area_id",
    "area_name",
    "live_scene_id",
    "scene_date",
    "status",
    "area_status",
    "interpretations",
    "previews",
    "source_status"
   ],
   "desc": "Scene Live terbaru per area aktif (READY/PARTIAL, berkas belum dihapus): status area, kalimat kondisi, manifest preview. PUBLIC+."
  },
  {
   "name": "v_ringkasan_kualitas",
   "cols": [
    "source_code",
    "week_start",
    "n_quality_metrics",
    "avg_quality_score",
    "n_fail",
    "n_warning",
    "n_quality_alerts",
    "n_observations",
    "avg_valid_fraction"
   ],
   "desc": "Per sumber per minggu (Senin): jumlah & rata-rata skor quality_metrics, FAIL/WARNING, quality_alerts, dan rata-rata valid_fraction region_observations. DATA_ENGINEER, ADMIN."
  },
  {
   "name": "v_statistik_hari_ini",
   "cols": [
    "obs_date",
    "region_id",
    "pcode",
    "region_name",
    "rain_24h_mm",
    "rain_72h_mm",
    "rain_7d_mm",
    "rain_30d_mm",
    "gpm_run",
    "bmkg_category",
    "ndvi",
    "ndvi_date",
    "ndwi",
    "ndwi_date",
    "modis_flood_pct",
    "modis_date"
   ],
   "desc": "Baris v_hujan_harian_kecamatan untuk tanggal terakhir yang lengkap (semua kecamatan in_aoi punya RAIN_24H) + NDVI/NDWI/FLOOD MODIS terakhir yang tersedia. USER+."
  },
  {
   "name": "v_unduhan_per_role",
   "cols": [
    "log_date_wib",
    "action",
    "role_code",
    "n_downloads",
    "bytes_sent"
   ],
   "desc": "Jumlah dan volume unduhan/ekspor per tanggal WIB, jenis aksi, dan role pengunduh; tanpa nama pengguna. DATA_ENGINEER, ADMIN, ETL (laporan)."
  },
  {
   "name": "v_users_safe",
   "cols": [
    "user_id",
    "role_id",
    "role_code",
    "username",
    "full_name",
    "organization",
    "is_active",
    "last_login_at",
    "created_by",
    "created_at",
    "updated_at"
   ],
   "desc": "users tanpa password_hash, failed_login_count, locked_until. ADMIN (UI) dan semua role untuk join nama."
  }
 ],
 "rels": [
  {
   "parent": "administrative_regions",
   "child": "administrative_regions",
   "fk": "parent_region_id",
   "mandatory": false
  },
  {
   "parent": "users",
   "child": "alert_events",
   "fk": "acknowledged_by",
   "mandatory": false
  },
  {
   "parent": "region_observations",
   "child": "alert_events",
   "fk": "obs_id",
   "mandatory": true
  },
  {
   "parent": "administrative_regions",
   "child": "alert_events",
   "fk": "region_id",
   "mandatory": true
  },
  {
   "parent": "alert_rules",
   "child": "alert_events",
   "fk": "rule_id",
   "mandatory": true
  },
  {
   "parent": "spectral_bands",
   "child": "alert_rules",
   "fk": "band_id",
   "mandatory": true
  },
  {
   "parent": "disaster_types",
   "child": "alert_rules",
   "fk": "disaster_type_id",
   "mandatory": true
  },
  {
   "parent": "users",
   "child": "alert_rules",
   "fk": "updated_by",
   "mandatory": false
  },
  {
   "parent": "users",
   "child": "api_tokens",
   "fk": "user_id",
   "mandatory": true
  },
  {
   "parent": "users",
   "child": "app_settings",
   "fk": "updated_by",
   "mandatory": false
  },
  {
   "parent": "band_forecasts",
   "child": "band_forecast_points",
   "fk": "forecast_id",
   "mandatory": true
  },
  {
   "parent": "band_forecasts",
   "child": "band_forecast_scores",
   "fk": "forecast_id",
   "mandatory": true
  },
  {
   "parent": "spectral_bands",
   "child": "band_forecasts",
   "fk": "band_id",
   "mandatory": true
  },
  {
   "parent": "administrative_regions",
   "child": "band_forecasts",
   "fk": "region_id",
   "mandatory": false
  },
  {
   "parent": "dataset_jobs",
   "child": "cleanup_operations",
   "fk": "job_id",
   "mandatory": false
  },
  {
   "parent": "data_products",
   "child": "data_lineage",
   "fk": "child_product_id",
   "mandatory": true
  },
  {
   "parent": "processing_jobs",
   "child": "data_lineage",
   "fk": "job_id",
   "mandatory": true
  },
  {
   "parent": "data_products",
   "child": "data_lineage",
   "fk": "parent_product_id",
   "mandatory": true
  },
  {
   "parent": "processing_stages",
   "child": "data_lineage",
   "fk": "stage_id",
   "mandatory": true
  },
  {
   "parent": "datasets",
   "child": "data_products",
   "fk": "dataset_id",
   "mandatory": false
  },
  {
   "parent": "processing_jobs",
   "child": "data_products",
   "fk": "job_id",
   "mandatory": true
  },
  {
   "parent": "nasa_scenes",
   "child": "data_products",
   "fk": "nasa_scene_id",
   "mandatory": false
  },
  {
   "parent": "satellite_scenes",
   "child": "data_products",
   "fk": "scene_id",
   "mandatory": false
  },
  {
   "parent": "satellite_sources",
   "child": "data_products",
   "fk": "source",
   "mandatory": true
  },
  {
   "parent": "datasets",
   "child": "dataset_jobs",
   "fk": "dataset_id",
   "mandatory": true
  },
  {
   "parent": "datasets",
   "child": "dataset_source_config",
   "fk": "dataset_id",
   "mandatory": true
  },
  {
   "parent": "satellite_sources",
   "child": "dataset_source_config",
   "fk": "source_name",
   "mandatory": true
  },
  {
   "parent": "users",
   "child": "datasets",
   "fk": "created_by",
   "mandatory": false
  },
  {
   "parent": "fusion_strategies",
   "child": "datasets",
   "fk": "fusion_strategy",
   "mandatory": false
  },
  {
   "parent": "regions_of_interest",
   "child": "datasets",
   "fk": "region_id",
   "mandatory": false
  },
  {
   "parent": "disaster_types",
   "child": "disaster_events",
   "fk": "disaster_type_id",
   "mandatory": true
  },
  {
   "parent": "users",
   "child": "disaster_events",
   "fk": "recorded_by",
   "mandatory": true
  },
  {
   "parent": "administrative_regions",
   "child": "disaster_events",
   "fk": "region_id",
   "mandatory": true
  },
  {
   "parent": "users",
   "child": "disaster_events",
   "fk": "verified_by",
   "mandatory": false
  },
  {
   "parent": "datasets",
   "child": "fusion_products",
   "fk": "dataset_id",
   "mandatory": false
  },
  {
   "parent": "fusion_strategies",
   "child": "fusion_products",
   "fk": "fusion_strategy",
   "mandatory": false
  },
  {
   "parent": "nasa_scenes",
   "child": "fusion_products",
   "fk": "gpm_scene_id",
   "mandatory": false
  },
  {
   "parent": "nasa_scenes",
   "child": "fusion_products",
   "fk": "modis_scene_id",
   "mandatory": false
  },
  {
   "parent": "regions_of_interest",
   "child": "fusion_products",
   "fk": "region_id",
   "mandatory": true
  },
  {
   "parent": "satellite_scenes",
   "child": "fusion_products",
   "fk": "s1_scene_id",
   "mandatory": false
  },
  {
   "parent": "users",
   "child": "generated_reports",
   "fk": "generated_by",
   "mandatory": false
  },
  {
   "parent": "report_types",
   "child": "generated_reports",
   "fk": "report_type_id",
   "mandatory": true
  },
  {
   "parent": "datasets",
   "child": "live_areas",
   "fk": "dataset_id",
   "mandatory": false
  },
  {
   "parent": "regions_of_interest",
   "child": "live_areas",
   "fk": "region_id",
   "mandatory": false
  },
  {
   "parent": "users",
   "child": "live_areas",
   "fk": "updated_by",
   "mandatory": false
  },
  {
   "parent": "spectral_bands",
   "child": "live_scene_metrics",
   "fk": "band_id",
   "mandatory": true
  },
  {
   "parent": "live_scenes",
   "child": "live_scene_metrics",
   "fk": "live_scene_id",
   "mandatory": true
  },
  {
   "parent": "live_scenes",
   "child": "live_scene_metrics",
   "fk": "ref_live_scene_id",
   "mandatory": false
  },
  {
   "parent": "users",
   "child": "nasa_scenes",
   "fk": "invalidated_by",
   "mandatory": false
  },
  {
   "parent": "regions_of_interest",
   "child": "nasa_scenes",
   "fk": "region_id",
   "mandatory": true
  },
  {
   "parent": "satellite_sources",
   "child": "nasa_scenes",
   "fk": "source",
   "mandatory": true
  },
  {
   "parent": "nasa_scenes",
   "child": "processing_jobs",
   "fk": "nasa_scene_id",
   "mandatory": false
  },
  {
   "parent": "satellite_scenes",
   "child": "processing_jobs",
   "fk": "scene_id",
   "mandatory": false
  },
  {
   "parent": "processing_stages",
   "child": "processing_jobs",
   "fk": "stage_id",
   "mandatory": true
  },
  {
   "parent": "datasets",
   "child": "processing_logs",
   "fk": "dataset_id",
   "mandatory": true
  },
  {
   "parent": "satellite_sources",
   "child": "processing_stages",
   "fk": "source_code",
   "mandatory": false
  },
  {
   "parent": "processing_jobs",
   "child": "quality_alerts",
   "fk": "job_id",
   "mandatory": false
  },
  {
   "parent": "data_products",
   "child": "quality_alerts",
   "fk": "product_id",
   "mandatory": false
  },
  {
   "parent": "satellite_scenes",
   "child": "quality_alerts",
   "fk": "scene_id",
   "mandatory": false
  },
  {
   "parent": "data_products",
   "child": "quality_metrics",
   "fk": "product_id",
   "mandatory": true
  },
  {
   "parent": "satellite_scenes",
   "child": "quality_metrics",
   "fk": "scene_id",
   "mandatory": true
  },
  {
   "parent": "spectral_bands",
   "child": "quality_thresholds",
   "fk": "band_id",
   "mandatory": true
  },
  {
   "parent": "spectral_bands",
   "child": "region_observations",
   "fk": "band_id",
   "mandatory": true
  },
  {
   "parent": "dataset_jobs",
   "child": "region_observations",
   "fk": "job_id",
   "mandatory": false
  },
  {
   "parent": "administrative_regions",
   "child": "region_observations",
   "fk": "region_id",
   "mandatory": true
  },
  {
   "parent": "data_products",
   "child": "region_observations",
   "fk": "source_product_id",
   "mandatory": false
  },
  {
   "parent": "administrative_regions",
   "child": "regions_of_interest",
   "fk": "admin_region_id",
   "mandatory": false
  },
  {
   "parent": "roles",
   "child": "report_types",
   "fk": "audience_role_id",
   "mandatory": true
  },
  {
   "parent": "users",
   "child": "satellite_scenes",
   "fk": "invalidated_by",
   "mandatory": false
  },
  {
   "parent": "regions_of_interest",
   "child": "satellite_scenes",
   "fk": "region_id",
   "mandatory": true
  },
  {
   "parent": "dataset_jobs",
   "child": "scene_job_state",
   "fk": "job_id",
   "mandatory": true
  },
  {
   "parent": "satellite_scenes",
   "child": "scene_job_state",
   "fk": "scene_id",
   "mandatory": false
  },
  {
   "parent": "satellite_sources",
   "child": "spectral_bands",
   "fk": "source_id",
   "mandatory": true
  },
  {
   "parent": "users",
   "child": "user_activity_logs",
   "fk": "user_id",
   "mandatory": false
  },
  {
   "parent": "users",
   "child": "users",
   "fk": "created_by",
   "mandatory": false
  },
  {
   "parent": "roles",
   "child": "users",
   "fk": "role_id",
   "mandatory": true
  }
 ],
 "bench": {
  "timing": [
   {
    "engine": "PostgreSQL",
    "query": "Q1",
    "description": "Statistik hari ini: pivot hujan per kecamatan satu tanggal",
    "status": "dijalankan",
    "rows": "10",
    "runs": "30",
    "median_ms": "0.452",
    "p95_ms": "0.537",
    "min_ms": "0.448",
    "max_ms": "0.553"
   },
   {
    "engine": "PostgreSQL",
    "query": "Q2",
    "description": "Tren 30 hari satu kecamatan satu band",
    "status": "dijalankan",
    "rows": "30",
    "runs": "30",
    "median_ms": "0.293",
    "p95_ms": "0.307",
    "min_ms": "0.252",
    "max_ms": "0.468"
   },
   {
    "engine": "PostgreSQL",
    "query": "Q3",
    "description": "Spasial: kecamatan beririsan poligon + luas irisan geodesik (km²)",
    "status": "dijalankan",
    "rows": "12",
    "runs": "30",
    "median_ms": "1.342",
    "p95_ms": "2.15",
    "min_ms": "1.045",
    "max_ms": "2.181"
   },
   {
    "engine": "PostgreSQL",
    "query": "Q4",
    "description": "Evaluasi alert: hit / miss / false alarm (WARNING+, 0–3 hari)",
    "status": "dijalankan",
    "rows": "3",
    "runs": "30",
    "median_ms": "1.764",
    "p95_ms": "2.722",
    "min_ms": "0.977",
    "max_ms": "3.033"
   },
   {
    "engine": "PostgreSQL",
    "query": "Q5",
    "description": "Lineage: leluhur satu produk sampai 6 tingkat (WITH RECURSIVE)",
    "status": "dijalankan",
    "rows": "6",
    "runs": "30",
    "median_ms": "0.823",
    "p95_ms": "1.569",
    "min_ms": "0.572",
    "max_ms": "1.671"
   },
   {
    "engine": "MySQL 8.0",
    "query": "Q1",
    "description": "Statistik hari ini: pivot hujan per kecamatan satu tanggal",
    "status": "dijalankan",
    "rows": "10",
    "runs": "30",
    "median_ms": "1.136",
    "p95_ms": "1.3",
    "min_ms": "0.953",
    "max_ms": "1.351"
   },
   {
    "engine": "MySQL 8.0",
    "query": "Q2",
    "description": "Tren 30 hari satu kecamatan satu band",
    "status": "dijalankan",
    "rows": "30",
    "runs": "30",
    "median_ms": "0.666",
    "p95_ms": "0.71",
    "min_ms": "0.642",
    "max_ms": "0.718"
   },
   {
    "engine": "MySQL 8.0",
    "query": "Q3",
    "description": "Spasial: kecamatan beririsan poligon + luas irisan geodesik (km²)",
    "status": "dijalankan",
    "rows": "12",
    "runs": "30",
    "median_ms": "22.567",
    "p95_ms": "23.029",
    "min_ms": "17.702",
    "max_ms": "23.114"
   },
   {
    "engine": "MySQL 8.0",
    "query": "Q4",
    "description": "Evaluasi alert: hit / miss / false alarm (WARNING+, 0–3 hari)",
    "status": "dijalankan",
    "rows": "3",
    "runs": "30",
    "median_ms": "16.641",
    "p95_ms": "17.215",
    "min_ms": "14.679",
    "max_ms": "17.32"
   },
   {
    "engine": "MySQL 8.0",
    "query": "Q5",
    "description": "Lineage: leluhur satu produk sampai 6 tingkat (WITH RECURSIVE)",
    "status": "dijalankan",
    "rows": "6",
    "runs": "30",
    "median_ms": "0.425",
    "p95_ms": "0.492",
    "min_ms": "0.416",
    "max_ms": "0.505"
   }
  ],
  "features": [
   {
    "engine": "PostgreSQL",
    "feature": "F1",
    "name": "SET ROLE per transaksi",
    "result": "DIDUKUNG",
    "evidence": "SET LOCAL ROLE: SELECT diizinkan, DELETE ditolak=True, role kembali 'postgres' setelah ROLLBACK"
   },
   {
    "engine": "PostgreSQL",
    "feature": "F2",
    "name": "Row-level security",
    "result": "DIDUKUNG",
    "evidence": "CREATE POLICY: role terbatas melihat 99 dari 150 baris (terverifikasi 99)"
   },
   {
    "engine": "PostgreSQL",
    "feature": "F3",
    "name": "Trigger audit OLD/NEW sebagai JSON",
    "result": "DIDUKUNG",
    "evidence": "to_jsonb(OLD)/to_jsonb(NEW) generik untuk semua tabel (satu fungsi, tanpa daftar kolom)"
   },
   {
    "engine": "MySQL 8.0",
    "feature": "F1",
    "name": "SET ROLE per transaksi",
    "result": "SEBAGIAN",
    "evidence": "SET ROLE per sesi; DELETE ditolak=False (hak akun tetap berlaku); setelah ROLLBACK CURRENT_ROLE() masih `bench_reader`@`%` — aplikasi harus mereset manual"
   },
   {
    "engine": "MySQL 8.0",
    "feature": "F2",
    "name": "Row-level security",
    "result": "TIDAK DIDUKUNG",
    "evidence": "MySQL 8.0 tidak punya CREATE POLICY; emulasi lewat VIEW SQL SECURITY DEFINER + GRANT pada VIEW"
   },
   {
    "engine": "MySQL 8.0",
    "feature": "F3",
    "name": "Trigger audit OLD/NEW sebagai JSON",
    "result": "SEBAGIAN",
    "evidence": "JSON_OBJECT harus menyebut setiap kolom per tabel; tidak ada padanan to_jsonb(OLD)"
   },
   {
    "engine": "MongoDB 7 (fitur saja)",
    "feature": "F1",
    "name": "SET ROLE per transaksi",
    "result": "TIDAK DIDUKUNG",
    "evidence": "Hak akses per pengguna koneksi; tidak ada pergantian role di dalam transaksi"
   },
   {
    "engine": "MongoDB 7 (fitur saja)",
    "feature": "F2",
    "name": "Row-level security",
    "result": "TIDAK DIDUKUNG",
    "evidence": "Tidak ada policy per dokumen bawaan (hanya redaksi lewat $redact/VIEW agregasi)"
   },
   {
    "engine": "MongoDB 7 (fitur saja)",
    "feature": "F3",
    "name": "Trigger audit OLD/NEW sebagai JSON",
    "result": "SEBAGIAN",
    "evidence": "Change streams (pre/post image) di luar transaksi; audit log bawaan hanya edisi Enterprise"
   },
   {
    "engine": "MongoDB 7 (fitur saja)",
    "feature": "FK",
    "name": "Foreign key / integritas lineage",
    "result": "TIDAK DIDUKUNG",
    "evidence": "Tanpa FK; lineage dijaga aplikasi; $graphLookup untuk rantai leluhur"
   }
  ],
  "scaling": [
   {
    "engine": "PostgreSQL",
    "scale": "1",
    "rows": "76720",
    "query": "Q1",
    "result_rows": "10",
    "median_ms": "0.516",
    "p95_ms": "0.536",
    "data_mb": "5.0",
    "index_mb": "6.3",
    "grow_seconds": "0.0"
   },
   {
    "engine": "PostgreSQL",
    "scale": "1",
    "rows": "76720",
    "query": "Q2",
    "result_rows": "30",
    "median_ms": "0.288",
    "p95_ms": "0.291",
    "data_mb": "5.0",
    "index_mb": "6.3",
    "grow_seconds": "0.0"
   },
   {
    "engine": "PostgreSQL",
    "scale": "1",
    "rows": "76720",
    "query": "Q6",
    "result_rows": "360",
    "median_ms": "10.298",
    "p95_ms": "15.223",
    "data_mb": "5.0",
    "index_mb": "6.3",
    "grow_seconds": "0.0"
   },
   {
    "engine": "PostgreSQL",
    "scale": "10",
    "rows": "767200",
    "query": "Q1",
    "result_rows": "10",
    "median_ms": "0.516",
    "p95_ms": "0.528",
    "data_mb": "47.6",
    "index_mb": "62.1",
    "grow_seconds": "14.2"
   },
   {
    "engine": "PostgreSQL",
    "scale": "10",
    "rows": "767200",
    "query": "Q2",
    "result_rows": "30",
    "median_ms": "0.303",
    "p95_ms": "0.374",
    "data_mb": "47.6",
    "index_mb": "62.1",
    "grow_seconds": "14.2"
   },
   {
    "engine": "PostgreSQL",
    "scale": "10",
    "rows": "767200",
    "query": "Q6",
    "result_rows": "3610",
    "median_ms": "201.092",
    "p95_ms": "213.454",
    "data_mb": "47.6",
    "index_mb": "62.1",
    "grow_seconds": "14.2"
   },
   {
    "engine": "PostgreSQL",
    "scale": "30",
    "rows": "2301600",
    "query": "Q1",
    "result_rows": "10",
    "median_ms": "0.526",
    "p95_ms": "0.627",
    "data_mb": "142.7",
    "index_mb": "186.5",
    "grow_seconds": "40.0"
   },
   {
    "engine": "PostgreSQL",
    "scale": "30",
    "rows": "2301600",
    "query": "Q2",
    "result_rows": "30",
    "median_ms": "0.295",
    "p95_ms": "0.359",
    "data_mb": "142.7",
    "index_mb": "186.5",
    "grow_seconds": "40.0"
   },
   {
    "engine": "PostgreSQL",
    "scale": "30",
    "rows": "2301600",
    "query": "Q6",
    "result_rows": "10810",
    "median_ms": "653.786",
    "p95_ms": "717.418",
    "data_mb": "142.7",
    "index_mb": "186.5",
    "grow_seconds": "40.0"
   },
   {
    "engine": "MySQL 8.0",
    "scale": "1",
    "rows": "76720",
    "query": "Q1",
    "result_rows": "10",
    "median_ms": "0.792",
    "p95_ms": "0.811",
    "data_mb": "4.5",
    "index_mb": "9.0",
    "grow_seconds": "0.0"
   },
   {
    "engine": "MySQL 8.0",
    "scale": "1",
    "rows": "76720",
    "query": "Q2",
    "result_rows": "30",
    "median_ms": "0.642",
    "p95_ms": "0.652",
    "data_mb": "4.5",
    "index_mb": "9.0",
    "grow_seconds": "0.0"
   },
   {
    "engine": "MySQL 8.0",
    "scale": "1",
    "rows": "76720",
    "query": "Q6",
    "result_rows": "360",
    "median_ms": "39.461",
    "p95_ms": "41.176",
    "data_mb": "4.5",
    "index_mb": "9.0",
    "grow_seconds": "0.0"
   },
   {
    "engine": "MySQL 8.0",
    "scale": "10",
    "rows": "767200",
    "query": "Q1",
    "result_rows": "10",
    "median_ms": "1.9",
    "p95_ms": "2.027",
    "data_mb": "38.6",
    "index_mb": "68.2",
    "grow_seconds": "64.7"
   },
   {
    "engine": "MySQL 8.0",
    "scale": "10",
    "rows": "767200",
    "query": "Q2",
    "result_rows": "30",
    "median_ms": "1.154",
    "p95_ms": "1.411",
    "data_mb": "38.6",
    "index_mb": "68.2",
    "grow_seconds": "64.7"
   },
   {
    "engine": "MySQL 8.0",
    "scale": "10",
    "rows": "767200",
    "query": "Q6",
    "result_rows": "3610",
    "median_ms": "396.798",
    "p95_ms": "414.126",
    "data_mb": "38.6",
    "index_mb": "68.2",
    "grow_seconds": "64.7"
   },
   {
    "engine": "MySQL 8.0",
    "scale": "30",
    "rows": "2301600",
    "query": "Q1",
    "result_rows": "10",
    "median_ms": "0.972",
    "p95_ms": "1.034",
    "data_mb": "113.7",
    "index_mb": "198.4",
    "grow_seconds": "292.8"
   },
   {
    "engine": "MySQL 8.0",
    "scale": "30",
    "rows": "2301600",
    "query": "Q2",
    "result_rows": "30",
    "median_ms": "0.75",
    "p95_ms": "0.76",
    "data_mb": "113.7",
    "index_mb": "198.4",
    "grow_seconds": "292.8"
   },
   {
    "engine": "MySQL 8.0",
    "scale": "30",
    "rows": "2301600",
    "query": "Q6",
    "result_rows": "10810",
    "median_ms": "5577.347",
    "p95_ms": "9824.657",
    "data_mb": "113.7",
    "index_mb": "198.4",
    "grow_seconds": "292.8"
   }
  ],
  "concurrency": [
   {
    "engine": "PostgreSQL",
    "clients": "1",
    "seconds": "10",
    "queries": "23973",
    "qps": "2397.3",
    "median_ms": "0.433",
    "p95_ms": "0.602",
    "errors": "0"
   },
   {
    "engine": "PostgreSQL",
    "clients": "4",
    "seconds": "10",
    "queries": "73960",
    "qps": "7396.0",
    "median_ms": "0.51",
    "p95_ms": "0.799",
    "errors": "0"
   },
   {
    "engine": "PostgreSQL",
    "clients": "8",
    "seconds": "10",
    "queries": "85226",
    "qps": "8522.6",
    "median_ms": "0.896",
    "p95_ms": "1.369",
    "errors": "0"
   },
   {
    "engine": "PostgreSQL",
    "clients": "16",
    "seconds": "10",
    "queries": "81264",
    "qps": "8126.4",
    "median_ms": "1.724",
    "p95_ms": "3.58",
    "errors": "0"
   },
   {
    "engine": "MySQL 8.0 (mysqlclient)",
    "clients": "1",
    "seconds": "10",
    "queries": "19067",
    "qps": "1906.7",
    "median_ms": "0.529",
    "p95_ms": "0.766",
    "errors": "0"
   },
   {
    "engine": "MySQL 8.0 (mysqlclient)",
    "clients": "4",
    "seconds": "10",
    "queries": "63393",
    "qps": "6339.3",
    "median_ms": "0.619",
    "p95_ms": "0.94",
    "errors": "0"
   },
   {
    "engine": "MySQL 8.0 (mysqlclient)",
    "clients": "8",
    "seconds": "10",
    "queries": "70262",
    "qps": "7026.2",
    "median_ms": "1.09",
    "p95_ms": "1.699",
    "errors": "0"
   },
   {
    "engine": "MySQL 8.0 (mysqlclient)",
    "clients": "16",
    "seconds": "10",
    "queries": "71612",
    "qps": "7161.2",
    "median_ms": "2.041",
    "p95_ms": "4.012",
    "errors": "0"
   }
  ],
  "write": [
   {
    "engine": "PostgreSQL",
    "test": "Insert batch 50.000 baris",
    "runs": "3",
    "median_s": "0.993",
    "rows_per_s": "50361",
    "final_rows": "60000"
   },
   {
    "engine": "PostgreSQL",
    "test": "Upsert 20.000 baris (50% konflik)",
    "runs": "3",
    "median_s": "0.487",
    "rows_per_s": "41084",
    "final_rows": "60000"
   },
   {
    "engine": "MySQL 8.0 (mysqlclient)",
    "test": "Insert batch 50.000 baris",
    "runs": "3",
    "median_s": "8.167",
    "rows_per_s": "6122",
    "final_rows": "60000"
   },
   {
    "engine": "MySQL 8.0 (mysqlclient)",
    "test": "Upsert 20.000 baris (50% konflik)",
    "runs": "3",
    "median_s": "0.944",
    "rows_per_s": "21178",
    "final_rows": "60000"
   }
  ]
 },
 "pytest": {
  "tests": 1142,
  "failures": 0,
  "errors": 0,
  "skipped": 2,
  "time": 137.576,
  "timestamp": "2026-10-08T13:54:17.159563+07:00",
  "files": [
   {
    "file": "test_rbac_api",
    "n": 153,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_per_satellite_config",
    "n": 78,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_source_config",
    "n": 56,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_api_endpoints",
    "n": 53,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_folder_manager",
    "n": 47,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_processing_plan",
    "n": 43,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_auth",
    "n": 38,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_web_ui",
    "n": 32,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_excel_io",
    "n": 27,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_quality_metrics",
    "n": 27,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_download_concurrency",
    "n": 26,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_database",
    "n": 25,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_module10_preview",
    "n": 24,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_geo_utils",
    "n": 23,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_monitor_api",
    "n": 23,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_water_change",
    "n": 22,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_live_monitor",
    "n": 21,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_etl_pipeline",
    "n": 19,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_report_generation",
    "n": 19,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_tier_names",
    "n": 19,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_download_resilience",
    "n": 18,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_hydromet_aggregate",
    "n": 18,
    "fail": 0,
    "skip": 2
   },
   {
    "file": "test_pipeline_logger",
    "n": 18,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_try8_regressions",
    "n": 18,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_data_api",
    "n": 17,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_pipeline_branching",
    "n": 17,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_dataset_sources_api",
    "n": 16,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_fusion_strategies",
    "n": 16,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_live_interpret_forecast",
    "n": 15,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_fusion_grid",
    "n": 14,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_job_run_state",
    "n": 14,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_alert_engine",
    "n": 13,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_fusion_grid_pinned",
    "n": 13,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_orchestrator_preview_stage",
    "n": 13,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_audit",
    "n": 12,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_reports",
    "n": 12,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_aoi_coverage_gate",
    "n": 10,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_scene_reconcile",
    "n": 10,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_citra_api",
    "n": 9,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_modis_quality_bands",
    "n": 9,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_s1_mosaic",
    "n": 9,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_diagram_api",
    "n": 7,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_live_preview_geo",
    "n": 7,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_admin_api",
    "n": 6,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_gpm_native_resolution",
    "n": 6,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_backfill_circuit_breaker",
    "n": 5,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_live_scene_metrics",
    "n": 5,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_multicore_regressions",
    "n": 5,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_preview_gallery",
    "n": 5,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_schema_comments",
    "n": 5,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_jan_mar_2025_hybrid_regressions",
    "n": 4,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_openapi_docs",
    "n": 4,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_s1_observations_retention",
    "n": 4,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_scenes_source",
    "n": 4,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_deletion_manager",
    "n": 3,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_fusion_product_identity",
    "n": 3,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_modis_dependency",
    "n": 2,
    "fail": 0,
    "skip": 0
   },
   {
    "file": "test_grant_matrix",
    "n": 1,
    "fail": 0,
    "skip": 0
   }
  ]
 },
 "db": {
  "counts": {
   "report_types": 4,
   "administrative_regions": 29,
   "api_tokens": 1,
   "app_settings": 11,
   "audit_log": 338,
   "disaster_events": 0,
   "band_forecasts": 110,
   "band_forecast_points": 1560,
   "band_forecast_scores": 454,
   "cleanup_operations": 0,
   "dataset_jobs": 1034,
   "live_areas": 1,
   "processing_logs": 5778,
   "generated_reports": 1,
   "spectral_bands": 11,
   "processing_stages": 13,
   "quality_alerts": 14,
   "region_observations": 72300,
   "fusion_strategies": 3,
   "alert_rules": 4,
   "data_lineage": 7991,
   "datasets": 2,
   "live_events": 321,
   "fusion_products": 0,
   "live_scene_metrics": 1727,
   "quality_metrics": 190,
   "regions_of_interest": 11,
   "roles": 5,
   "scene_job_state": 147,
   "users": 5,
   "user_activity_logs": 28,
   "satellite_sources": 4,
   "satellite_scenes": 85,
   "nasa_scenes": 2206,
   "alert_events": 210,
   "data_products": 15604,
   "processing_jobs": 7873,
   "live_scenes": 55,
   "dataset_source_config": 5,
   "quality_thresholds": 9,
   "disaster_types": 4
  },
  "aoi": [
   "Banjarsari",
   "Bayah",
   "Cibeber",
   "Cigemblong",
   "Cihara",
   "Cijaku",
   "Cilograng",
   "Malingping",
   "Panggarangan",
   "Wanasalam"
  ],
  "obs_range": [
   "2024-01-01",
   "2026-10-07"
  ],
  "at": "2026-10-09 14:37",
  "indexes": [
   {
    "t": "administrative_regions",
    "n": "administrative_regions_pcode_key",
    "def": "CREATE UNIQUE INDEX administrative_regions_pcode_key ON public.administrative_regions USING btree (pcode)"
   },
   {
    "t": "administrative_regions",
    "n": "administrative_regions_pkey",
    "def": "CREATE UNIQUE INDEX administrative_regions_pkey ON public.administrative_regions USING btree (region_id)"
   },
   {
    "t": "administrative_regions",
    "n": "idx_admreg_geom",
    "def": "CREATE INDEX idx_admreg_geom ON public.administrative_regions USING gist (geom)"
   },
   {
    "t": "administrative_regions",
    "n": "idx_admreg_in_aoi",
    "def": "CREATE INDEX idx_admreg_in_aoi ON public.administrative_regions USING btree (region_id) WHERE in_aoi"
   },
   {
    "t": "administrative_regions",
    "n": "idx_admreg_parent",
    "def": "CREATE INDEX idx_admreg_parent ON public.administrative_regions USING btree (parent_region_id)"
   },
   {
    "t": "alert_events",
    "n": "alert_events_pkey",
    "def": "CREATE UNIQUE INDEX alert_events_pkey ON public.alert_events USING btree (alert_id)"
   },
   {
    "t": "alert_events",
    "n": "idx_alerts_active",
    "def": "CREATE INDEX idx_alerts_active ON public.alert_events USING btree (observation_date DESC) WHERE (acknowledged_at IS NULL)"
   },
   {
    "t": "alert_events",
    "n": "idx_alerts_region_date",
    "def": "CREATE INDEX idx_alerts_region_date ON public.alert_events USING btree (region_id, observation_date)"
   },
   {
    "t": "alert_events",
    "n": "uq_alert_rule_region_date",
    "def": "CREATE UNIQUE INDEX uq_alert_rule_region_date ON public.alert_events USING btree (rule_id, region_id, observation_date)"
   },
   {
    "t": "alert_rules",
    "n": "alert_rules_pkey",
    "def": "CREATE UNIQUE INDEX alert_rules_pkey ON public.alert_rules USING btree (rule_id)"
   },
   {
    "t": "alert_rules",
    "n": "alert_rules_rule_code_key",
    "def": "CREATE UNIQUE INDEX alert_rules_rule_code_key ON public.alert_rules USING btree (rule_code)"
   },
   {
    "t": "alert_rules",
    "n": "idx_alert_rules_band",
    "def": "CREATE INDEX idx_alert_rules_band ON public.alert_rules USING btree (band_id) WHERE is_active"
   },
   {
    "t": "api_tokens",
    "n": "api_tokens_pkey",
    "def": "CREATE UNIQUE INDEX api_tokens_pkey ON public.api_tokens USING btree (token_id)"
   },
   {
    "t": "api_tokens",
    "n": "api_tokens_token_prefix_key",
    "def": "CREATE UNIQUE INDEX api_tokens_token_prefix_key ON public.api_tokens USING btree (token_prefix)"
   },
   {
    "t": "api_tokens",
    "n": "idx_api_tokens_user",
    "def": "CREATE INDEX idx_api_tokens_user ON public.api_tokens USING btree (user_id)"
   },
   {
    "t": "app_settings",
    "n": "app_settings_pkey",
    "def": "CREATE UNIQUE INDEX app_settings_pkey ON public.app_settings USING btree (setting_key)"
   },
   {
    "t": "audit_log",
    "n": "audit_log_pkey",
    "def": "CREATE UNIQUE INDEX audit_log_pkey ON public.audit_log USING btree (audit_id)"
   },
   {
    "t": "audit_log",
    "n": "idx_audit_table_time",
    "def": "CREATE INDEX idx_audit_table_time ON public.audit_log USING btree (table_name, changed_at DESC)"
   },
   {
    "t": "band_forecast_points",
    "n": "band_forecast_points_pkey",
    "def": "CREATE UNIQUE INDEX band_forecast_points_pkey ON public.band_forecast_points USING btree (forecast_id, step)"
   },
   {
    "t": "band_forecast_scores",
    "n": "band_forecast_scores_pkey",
    "def": "CREATE UNIQUE INDEX band_forecast_scores_pkey ON public.band_forecast_scores USING btree (forecast_id, model)"
   },
   {
    "t": "band_forecasts",
    "n": "band_forecasts_pkey",
    "def": "CREATE UNIQUE INDEX band_forecasts_pkey ON public.band_forecasts USING btree (forecast_id)"
   },
   {
    "t": "band_forecasts",
    "n": "idx_band_forecasts_latest",
    "def": "CREATE INDEX idx_band_forecasts_latest ON public.band_forecasts USING btree (band_id, region_id, computed_at DESC)"
   },
   {
    "t": "band_forecasts",
    "n": "uq_band_forecasts_stamp",
    "def": "CREATE UNIQUE INDEX uq_band_forecasts_stamp ON public.band_forecasts USING btree (band_id, COALESCE(region_id, 0), data_stamp)"
   },
   {
    "t": "cleanup_operations",
    "n": "cleanup_operations_pkey",
    "def": "CREATE UNIQUE INDEX cleanup_operations_pkey ON public.cleanup_operations USING btree (id)"
   },
   {
    "t": "cleanup_operations",
    "n": "idx_cleanup_ops_dataset",
    "def": "CREATE INDEX idx_cleanup_ops_dataset ON public.cleanup_operations USING btree (dataset_id, created_at DESC)"
   },
   {
    "t": "cleanup_operations",
    "n": "idx_cleanup_ops_status",
    "def": "CREATE INDEX idx_cleanup_ops_status ON public.cleanup_operations USING btree (status)"
   },
   {
    "t": "data_lineage",
    "n": "data_lineage_pkey",
    "def": "CREATE UNIQUE INDEX data_lineage_pkey ON public.data_lineage USING btree (lineage_id)"
   },
   {
    "t": "data_lineage",
    "n": "idx_lineage_child_id",
    "def": "CREATE INDEX idx_lineage_child_id ON public.data_lineage USING btree (child_product_id)"
   },
   {
    "t": "data_lineage",
    "n": "idx_lineage_job_id",
    "def": "CREATE INDEX idx_lineage_job_id ON public.data_lineage USING btree (job_id)"
   },
   {
    "t": "data_lineage",
    "n": "idx_lineage_parent_id",
    "def": "CREATE INDEX idx_lineage_parent_id ON public.data_lineage USING btree (parent_product_id)"
   },
   {
    "t": "data_lineage",
    "n": "idx_lineage_stage_id",
    "def": "CREATE INDEX idx_lineage_stage_id ON public.data_lineage USING btree (stage_id)"
   },
   {
    "t": "data_lineage",
    "n": "idx_lineage_transform",
    "def": "CREATE INDEX idx_lineage_transform ON public.data_lineage USING btree (transformation_type, created_at DESC)"
   },
   {
    "t": "data_lineage",
    "n": "uq_lineage_parent_child",
    "def": "CREATE UNIQUE INDEX uq_lineage_parent_child ON public.data_lineage USING btree (parent_product_id, child_product_id)"
   },
   {
    "t": "data_products",
    "n": "data_products_pkey",
    "def": "CREATE UNIQUE INDEX data_products_pkey ON public.data_products USING btree (product_id)"
   },
   {
    "t": "data_products",
    "n": "data_products_product_uuid_key",
    "def": "CREATE UNIQUE INDEX data_products_product_uuid_key ON public.data_products USING btree (product_uuid)"
   },
   {
    "t": "data_products",
    "n": "idx_dprods_created_at",
    "def": "CREATE INDEX idx_dprods_created_at ON public.data_products USING btree (created_at DESC)"
   },
   {
    "t": "data_products",
    "n": "idx_dprods_dataset_level",
    "def": "CREATE INDEX idx_dprods_dataset_level ON public.data_products USING btree (dataset_id, processing_level)"
   },
   {
    "t": "data_products",
    "n": "idx_dprods_dataset_tier",
    "def": "CREATE INDEX idx_dprods_dataset_tier ON public.data_products USING btree (dataset_id, product_tier)"
   },
   {
    "t": "data_products",
    "n": "idx_dprods_dataset_tier_source",
    "def": "CREATE INDEX idx_dprods_dataset_tier_source ON public.data_products USING btree (dataset_id, product_tier, source) WHERE is_latest"
   },
   {
    "t": "data_products",
    "n": "idx_dprods_hash",
    "def": "CREATE INDEX idx_dprods_hash ON public.data_products USING btree (data_hash_sha256)"
   },
   {
    "t": "data_products",
    "n": "idx_dprods_job_id",
    "def": "CREATE INDEX idx_dprods_job_id ON public.data_products USING btree (job_id)"
   },
   {
    "t": "data_products",
    "n": "idx_dprods_latest",
    "def": "CREATE INDEX idx_dprods_latest ON public.data_products USING btree (is_latest, product_tier) WHERE is_latest"
   },
   {
    "t": "data_products",
    "n": "idx_dprods_nasa_scene_id",
    "def": "CREATE INDEX idx_dprods_nasa_scene_id ON public.data_products USING btree (nasa_scene_id) WHERE (nasa_scene_id IS NOT NULL)"
   },
   {
    "t": "data_products",
    "n": "idx_dprods_scene_band_tier",
    "def": "CREATE INDEX idx_dprods_scene_band_tier ON public.data_products USING btree (scene_id, band_name, product_tier, created_at DESC) WHERE (is_latest AND is_valid)"
   },
   {
    "t": "data_products",
    "n": "idx_dprods_scene_id",
    "def": "CREATE INDEX idx_dprods_scene_id ON public.data_products USING btree (scene_id)"
   },
   {
    "t": "data_products",
    "n": "idx_dprods_tier_source",
    "def": "CREATE INDEX idx_dprods_tier_source ON public.data_products USING btree (product_tier, source)"
   },
   {
    "t": "dataset_jobs",
    "n": "dataset_jobs_job_uuid_key",
    "def": "CREATE UNIQUE INDEX dataset_jobs_job_uuid_key ON public.dataset_jobs USING btree (job_uuid)"
   },
   {
    "t": "dataset_jobs",
    "n": "dataset_jobs_pkey",
    "def": "CREATE UNIQUE INDEX dataset_jobs_pkey ON public.dataset_jobs USING btree (job_id)"
   },
   {
    "t": "dataset_jobs",
    "n": "idx_dataset_jobs_dataset",
    "def": "CREATE INDEX idx_dataset_jobs_dataset ON public.dataset_jobs USING btree (dataset_id, created_at DESC)"
   },
   {
    "t": "dataset_jobs",
    "n": "idx_dataset_jobs_status",
    "def": "CREATE INDEX idx_dataset_jobs_status ON public.dataset_jobs USING btree (status)"
   },
   {
    "t": "dataset_source_config",
    "n": "dataset_source_config_pkey",
    "def": "CREATE UNIQUE INDEX dataset_source_config_pkey ON public.dataset_source_config USING btree (config_id)"
   },
   {
    "t": "dataset_source_config",
    "n": "idx_source_config_dataset",
    "def": "CREATE INDEX idx_source_config_dataset ON public.dataset_source_config USING btree (dataset_id)"
   },
   {
    "t": "dataset_source_config",
    "n": "uq_source_config_dataset_source",
    "def": "CREATE UNIQUE INDEX uq_source_config_dataset_source ON public.dataset_source_config USING btree (dataset_id, source_name)"
   },
   {
    "t": "datasets",
    "n": "datasets_dataset_uuid_key",
    "def": "CREATE UNIQUE INDEX datasets_dataset_uuid_key ON public.datasets USING btree (dataset_uuid)"
   },
   {
    "t": "datasets",
    "n": "datasets_pkey",
    "def": "CREATE UNIQUE INDEX datasets_pkey ON public.datasets USING btree (dataset_id)"
   },
   {
    "t": "datasets",
    "n": "idx_datasets_bbox",
    "def": "CREATE INDEX idx_datasets_bbox ON public.datasets USING gist (bbox)"
   },
   {
    "t": "datasets",
    "n": "idx_datasets_created_at",
    "def": "CREATE INDEX idx_datasets_created_at ON public.datasets USING btree (created_at DESC)"
   },
   {
    "t": "datasets",
    "n": "idx_datasets_created_by",
    "def": "CREATE INDEX idx_datasets_created_by ON public.datasets USING btree (created_by)"
   },
   {
    "t": "datasets",
    "n": "idx_datasets_kind",
    "def": "CREATE INDEX idx_datasets_kind ON public.datasets USING btree (dataset_kind)"
   },
   {
    "t": "datasets",
    "n": "idx_datasets_status",
    "def": "CREATE INDEX idx_datasets_status ON public.datasets USING btree (status) WHERE ((status)::text <> 'DELETED'::text)"
   },
   {
    "t": "disaster_events",
    "n": "disaster_events_pkey",
    "def": "CREATE UNIQUE INDEX disaster_events_pkey ON public.disaster_events USING btree (event_id)"
   },
   {
    "t": "disaster_events",
    "n": "idx_disasters_date_region",
    "def": "CREATE INDEX idx_disasters_date_region ON public.disaster_events USING btree (event_date, region_id) WHERE (deleted_at IS NULL)"
   },
   {
    "t": "disaster_events",
    "n": "idx_disasters_location",
    "def": "CREATE INDEX idx_disasters_location ON public.disaster_events USING gist (location)"
   },
   {
    "t": "disaster_types",
    "n": "disaster_types_pkey",
    "def": "CREATE UNIQUE INDEX disaster_types_pkey ON public.disaster_types USING btree (disaster_type_id)"
   },
   {
    "t": "disaster_types",
    "n": "disaster_types_type_code_key",
    "def": "CREATE UNIQUE INDEX disaster_types_type_code_key ON public.disaster_types USING btree (type_code)"
   },
   {
    "t": "fusion_products",
    "n": "fusion_products_pkey",
    "def": "CREATE UNIQUE INDEX fusion_products_pkey ON public.fusion_products USING btree (fusion_id)"
   },
   {
    "t": "fusion_products",
    "n": "idx_fusion_dataset_date",
    "def": "CREATE INDEX idx_fusion_dataset_date ON public.fusion_products USING btree (dataset_id, feature_date)"
   },
   {
    "t": "fusion_products",
    "n": "idx_fusion_date",
    "def": "CREATE INDEX idx_fusion_date ON public.fusion_products USING btree (feature_date DESC)"
   },
   {
    "t": "fusion_products",
    "n": "idx_fusion_region_date_level",
    "def": "CREATE INDEX idx_fusion_region_date_level ON public.fusion_products USING btree (region_id, feature_date, processing_level)"
   },
   {
    "t": "fusion_products",
    "n": "uq_fusion_dataset_date_level",
    "def": "CREATE UNIQUE INDEX uq_fusion_dataset_date_level ON public.fusion_products USING btree (dataset_id, feature_date, processing_level)"
   },
   {
    "t": "fusion_strategies",
    "n": "fusion_strategies_pkey",
    "def": "CREATE UNIQUE INDEX fusion_strategies_pkey ON public.fusion_strategies USING btree (strategy_id)"
   },
   {
    "t": "fusion_strategies",
    "n": "fusion_strategies_strategy_code_key",
    "def": "CREATE UNIQUE INDEX fusion_strategies_strategy_code_key ON public.fusion_strategies USING btree (strategy_code)"
   },
   {
    "t": "generated_reports",
    "n": "generated_reports_pkey",
    "def": "CREATE UNIQUE INDEX generated_reports_pkey ON public.generated_reports USING btree (report_id)"
   },
   {
    "t": "generated_reports",
    "n": "idx_reports_type_period",
    "def": "CREATE INDEX idx_reports_type_period ON public.generated_reports USING btree (report_type_id, period_start DESC)"
   },
   {
    "t": "generated_reports",
    "n": "uq_report_ready",
    "def": "CREATE UNIQUE INDEX uq_report_ready ON public.generated_reports USING btree (report_type_id, period_start) WHERE ((status)::text = 'READY'::text)"
   },
   {
    "t": "live_areas",
    "n": "idx_live_areas_active",
    "def": "CREATE INDEX idx_live_areas_active ON public.live_areas USING btree (area_id) WHERE (deleted_at IS NULL)"
   },
   {
    "t": "live_areas",
    "n": "live_areas_pkey",
    "def": "CREATE UNIQUE INDEX live_areas_pkey ON public.live_areas USING btree (area_id)"
   },
   {
    "t": "live_events",
    "n": "idx_live_events_area_time",
    "def": "CREATE INDEX idx_live_events_area_time ON public.live_events USING btree (area_id, created_at DESC)"
   },
   {
    "t": "live_events",
    "n": "live_events_pkey",
    "def": "CREATE UNIQUE INDEX live_events_pkey ON public.live_events USING btree (event_id)"
   },
   {
    "t": "live_scene_metrics",
    "n": "idx_lsm_band_metric",
    "def": "CREATE INDEX idx_lsm_band_metric ON public.live_scene_metrics USING btree (band_id, metric_name)"
   },
   {
    "t": "live_scene_metrics",
    "n": "live_scene_metrics_pkey",
    "def": "CREATE UNIQUE INDEX live_scene_metrics_pkey ON public.live_scene_metrics USING btree (metric_id)"
   },
   {
    "t": "live_scene_metrics",
    "n": "uq_live_scene_metric",
    "def": "CREATE UNIQUE INDEX uq_live_scene_metric ON public.live_scene_metrics USING btree (live_scene_id, band_id, metric_name)"
   },
   {
    "t": "live_scenes",
    "n": "idx_live_scenes_area_date",
    "def": "CREATE INDEX idx_live_scenes_area_date ON public.live_scenes USING btree (area_id, scene_date DESC)"
   },
   {
    "t": "live_scenes",
    "n": "live_scenes_pkey",
    "def": "CREATE UNIQUE INDEX live_scenes_pkey ON public.live_scenes USING btree (live_scene_id)"
   },
   {
    "t": "live_scenes",
    "n": "uq_live_scene_area_date",
    "def": "CREATE UNIQUE INDEX uq_live_scene_area_date ON public.live_scenes USING btree (area_id, scene_date)"
   },
   {
    "t": "nasa_scenes",
    "n": "idx_nasa_scenes_date",
    "def": "CREATE INDEX idx_nasa_scenes_date ON public.nasa_scenes USING btree (acquisition_date DESC)"
   },
   {
    "t": "nasa_scenes",
    "n": "idx_nasa_scenes_source_date",
    "def": "CREATE INDEX idx_nasa_scenes_source_date ON public.nasa_scenes USING btree (source, acquisition_date DESC)"
   },
   {
    "t": "nasa_scenes",
    "n": "nasa_scenes_pkey",
    "def": "CREATE UNIQUE INDEX nasa_scenes_pkey ON public.nasa_scenes USING btree (nasa_scene_id)"
   },
   {
    "t": "nasa_scenes",
    "n": "uq_nasa_scene",
    "def": "CREATE UNIQUE INDEX uq_nasa_scene ON public.nasa_scenes USING btree (source, tile_id, product_short_name, acquisition_date)"
   },
   {
    "t": "processing_jobs",
    "n": "idx_pjobs_params_gin",
    "def": "CREATE INDEX idx_pjobs_params_gin ON public.processing_jobs USING gin (parameters_json)"
   },
   {
    "t": "processing_jobs",
    "n": "idx_pjobs_queued_at",
    "def": "CREATE INDEX idx_pjobs_queued_at ON public.processing_jobs USING btree (queued_at DESC)"
   },
   {
    "t": "processing_jobs",
    "n": "idx_pjobs_scene_id",
    "def": "CREATE INDEX idx_pjobs_scene_id ON public.processing_jobs USING btree (scene_id) WHERE (scene_id IS NOT NULL)"
   },
   {
    "t": "processing_jobs",
    "n": "idx_pjobs_stage_id",
    "def": "CREATE INDEX idx_pjobs_stage_id ON public.processing_jobs USING btree (stage_id)"
   },
   {
    "t": "processing_jobs",
    "n": "idx_pjobs_status",
    "def": "CREATE INDEX idx_pjobs_status ON public.processing_jobs USING btree (status, queued_at DESC)"
   },
   {
    "t": "processing_jobs",
    "n": "processing_jobs_job_uuid_key",
    "def": "CREATE UNIQUE INDEX processing_jobs_job_uuid_key ON public.processing_jobs USING btree (job_uuid)"
   },
   {
    "t": "processing_jobs",
    "n": "processing_jobs_pkey",
    "def": "CREATE UNIQUE INDEX processing_jobs_pkey ON public.processing_jobs USING btree (job_id)"
   },
   {
    "t": "processing_jobs",
    "n": "uq_job_nasa_stage_attempt",
    "def": "CREATE UNIQUE INDEX uq_job_nasa_stage_attempt ON public.processing_jobs USING btree (nasa_scene_id, stage_id, attempt_number) WHERE (nasa_scene_id IS NOT NULL)"
   },
   {
    "t": "processing_jobs",
    "n": "uq_job_scene_stage_attempt",
    "def": "CREATE UNIQUE INDEX uq_job_scene_stage_attempt ON public.processing_jobs USING btree (scene_id, stage_id, attempt_number)"
   },
   {
    "t": "processing_logs",
    "n": "idx_processing_logs_dataset_created",
    "def": "CREATE INDEX idx_processing_logs_dataset_created ON public.processing_logs USING btree (dataset_id, created_at DESC)"
   },
   {
    "t": "processing_logs",
    "n": "idx_processing_logs_dataset_scene",
    "def": "CREATE INDEX idx_processing_logs_dataset_scene ON public.processing_logs USING btree (dataset_id, scene_id, created_at DESC)"
   },
   {
    "t": "processing_logs",
    "n": "idx_processing_logs_stage_status",
    "def": "CREATE INDEX idx_processing_logs_stage_status ON public.processing_logs USING btree (stage, status)"
   },
   {
    "t": "processing_logs",
    "n": "processing_logs_log_uuid_key",
    "def": "CREATE UNIQUE INDEX processing_logs_log_uuid_key ON public.processing_logs USING btree (log_uuid)"
   },
   {
    "t": "processing_logs",
    "n": "processing_logs_pkey",
    "def": "CREATE UNIQUE INDEX processing_logs_pkey ON public.processing_logs USING btree (log_id)"
   },
   {
    "t": "processing_stages",
    "n": "processing_stages_pkey",
    "def": "CREATE UNIQUE INDEX processing_stages_pkey ON public.processing_stages USING btree (stage_id)"
   },
   {
    "t": "processing_stages",
    "n": "processing_stages_stage_code_key",
    "def": "CREATE UNIQUE INDEX processing_stages_stage_code_key ON public.processing_stages USING btree (stage_code)"
   },
   {
    "t": "processing_stages",
    "n": "processing_stages_stage_name_key",
    "def": "CREATE UNIQUE INDEX processing_stages_stage_name_key ON public.processing_stages USING btree (stage_name)"
   },
   {
    "t": "processing_stages",
    "n": "processing_stages_stage_order_key",
    "def": "CREATE UNIQUE INDEX processing_stages_stage_order_key ON public.processing_stages USING btree (stage_order)"
   },
   {
    "t": "quality_alerts",
    "n": "idx_qalerts_scene_id",
    "def": "CREATE INDEX idx_qalerts_scene_id ON public.quality_alerts USING btree (scene_id) WHERE (scene_id IS NOT NULL)"
   },
   {
    "t": "quality_alerts",
    "n": "idx_qalerts_triggered_at",
    "def": "CREATE INDEX idx_qalerts_triggered_at ON public.quality_alerts USING btree (triggered_at DESC)"
   },
   {
    "t": "quality_alerts",
    "n": "idx_qalerts_unresolved",
    "def": "CREATE INDEX idx_qalerts_unresolved ON public.quality_alerts USING btree (severity, triggered_at DESC) WHERE (NOT is_resolved)"
   },
   {
    "t": "quality_alerts",
    "n": "quality_alerts_alert_uuid_key",
    "def": "CREATE UNIQUE INDEX quality_alerts_alert_uuid_key ON public.quality_alerts USING btree (alert_uuid)"
   },
   {
    "t": "quality_alerts",
    "n": "quality_alerts_pkey",
    "def": "CREATE UNIQUE INDEX quality_alerts_pkey ON public.quality_alerts USING btree (alert_id)"
   },
   {
    "t": "quality_metrics",
    "n": "idx_qmetrics_assessed_at",
    "def": "CREATE INDEX idx_qmetrics_assessed_at ON public.quality_metrics USING btree (assessed_at DESC)"
   },
   {
    "t": "quality_metrics",
    "n": "idx_qmetrics_product_id",
    "def": "CREATE INDEX idx_qmetrics_product_id ON public.quality_metrics USING btree (product_id)"
   },
   {
    "t": "quality_metrics",
    "n": "idx_qmetrics_quality_flag",
    "def": "CREATE INDEX idx_qmetrics_quality_flag ON public.quality_metrics USING btree (quality_flag, assessed_at DESC)"
   },
   {
    "t": "quality_metrics",
    "n": "idx_qmetrics_scene_id",
    "def": "CREATE INDEX idx_qmetrics_scene_id ON public.quality_metrics USING btree (scene_id)"
   },
   {
    "t": "quality_metrics",
    "n": "quality_metrics_pkey",
    "def": "CREATE UNIQUE INDEX quality_metrics_pkey ON public.quality_metrics USING btree (metric_id)"
   },
   {
    "t": "quality_metrics",
    "n": "uq_quality_scene_product_band",
    "def": "CREATE UNIQUE INDEX uq_quality_scene_product_band ON public.quality_metrics USING btree (scene_id, product_id, band_name)"
   },
   {
    "t": "quality_thresholds",
    "n": "quality_thresholds_band_id_metric_name_key",
    "def": "CREATE UNIQUE INDEX quality_thresholds_band_id_metric_name_key ON public.quality_thresholds USING btree (band_id, metric_name)"
   },
   {
    "t": "quality_thresholds",
    "n": "quality_thresholds_pkey",
    "def": "CREATE UNIQUE INDEX quality_thresholds_pkey ON public.quality_thresholds USING btree (threshold_id)"
   },
   {
    "t": "region_observations",
    "n": "idx_obs_date_band",
    "def": "CREATE INDEX idx_obs_date_band ON public.region_observations USING btree (obs_date DESC, band_id)"
   },
   {
    "t": "region_observations",
    "n": "region_observations_pkey",
    "def": "CREATE UNIQUE INDEX region_observations_pkey ON public.region_observations USING btree (obs_id)"
   },
   {
    "t": "region_observations",
    "n": "uq_region_obs",
    "def": "CREATE UNIQUE INDEX uq_region_obs ON public.region_observations USING btree (region_id, band_id, obs_date)"
   },
   {
    "t": "regions_of_interest",
    "n": "idx_roi_bbox",
    "def": "CREATE INDEX idx_roi_bbox ON public.regions_of_interest USING gist (bbox)"
   },
   {
    "t": "regions_of_interest",
    "n": "idx_roi_name_lower",
    "def": "CREATE INDEX idx_roi_name_lower ON public.regions_of_interest USING btree (lower((name)::text))"
   },
   {
    "t": "regions_of_interest",
    "n": "idx_roi_not_deleted",
    "def": "CREATE INDEX idx_roi_not_deleted ON public.regions_of_interest USING btree (deleted_at) WHERE (deleted_at IS NULL)"
   },
   {
    "t": "regions_of_interest",
    "n": "regions_of_interest_pkey",
    "def": "CREATE UNIQUE INDEX regions_of_interest_pkey ON public.regions_of_interest USING btree (region_id)"
   },
   {
    "t": "regions_of_interest",
    "n": "regions_of_interest_region_code_key",
    "def": "CREATE UNIQUE INDEX regions_of_interest_region_code_key ON public.regions_of_interest USING btree (region_code)"
   },
   {
    "t": "regions_of_interest",
    "n": "uq_roi_monitor_aoi",
    "def": "CREATE UNIQUE INDEX uq_roi_monitor_aoi ON public.regions_of_interest USING btree (is_monitor_aoi) WHERE is_monitor_aoi"
   },
   {
    "t": "report_types",
    "n": "report_types_pkey",
    "def": "CREATE UNIQUE INDEX report_types_pkey ON public.report_types USING btree (report_type_id)"
   },
   {
    "t": "report_types",
    "n": "report_types_report_code_key",
    "def": "CREATE UNIQUE INDEX report_types_report_code_key ON public.report_types USING btree (report_code)"
   },
   {
    "t": "roles",
    "n": "roles_db_role_key",
    "def": "CREATE UNIQUE INDEX roles_db_role_key ON public.roles USING btree (db_role)"
   },
   {
    "t": "roles",
    "n": "roles_pkey",
    "def": "CREATE UNIQUE INDEX roles_pkey ON public.roles USING btree (role_id)"
   },
   {
    "t": "roles",
    "n": "roles_role_code_key",
    "def": "CREATE UNIQUE INDEX roles_role_code_key ON public.roles USING btree (role_code)"
   },
   {
    "t": "satellite_scenes",
    "n": "idx_scenes_acq_dt",
    "def": "CREATE INDEX idx_scenes_acq_dt ON public.satellite_scenes USING btree (acquisition_datetime DESC)"
   },
   {
    "t": "satellite_scenes",
    "n": "idx_scenes_bbox",
    "def": "CREATE INDEX idx_scenes_bbox ON public.satellite_scenes USING gist (bbox)"
   },
   {
    "t": "satellite_scenes",
    "n": "idx_scenes_region_date",
    "def": "CREATE INDEX idx_scenes_region_date ON public.satellite_scenes USING btree (region_id, acquisition_datetime DESC) WHERE is_available"
   },
   {
    "t": "satellite_scenes",
    "n": "satellite_scenes_pkey",
    "def": "CREATE UNIQUE INDEX satellite_scenes_pkey ON public.satellite_scenes USING btree (scene_id)"
   },
   {
    "t": "satellite_scenes",
    "n": "satellite_scenes_product_identifier_key",
    "def": "CREATE UNIQUE INDEX satellite_scenes_product_identifier_key ON public.satellite_scenes USING btree (product_identifier)"
   },
   {
    "t": "satellite_scenes",
    "n": "satellite_scenes_scene_uuid_key",
    "def": "CREATE UNIQUE INDEX satellite_scenes_scene_uuid_key ON public.satellite_scenes USING btree (scene_uuid)"
   },
   {
    "t": "satellite_sources",
    "n": "satellite_sources_pkey",
    "def": "CREATE UNIQUE INDEX satellite_sources_pkey ON public.satellite_sources USING btree (source_id)"
   },
   {
    "t": "satellite_sources",
    "n": "satellite_sources_source_code_key",
    "def": "CREATE UNIQUE INDEX satellite_sources_source_code_key ON public.satellite_sources USING btree (source_code)"
   },
   {
    "t": "scene_job_state",
    "n": "idx_scene_job_state_job",
    "def": "CREATE INDEX idx_scene_job_state_job ON public.scene_job_state USING btree (job_id)"
   },
   {
    "t": "scene_job_state",
    "n": "idx_scene_job_state_scene_id",
    "def": "CREATE INDEX idx_scene_job_state_scene_id ON public.scene_job_state USING btree (scene_id) WHERE (scene_id IS NOT NULL)"
   },
   {
    "t": "scene_job_state",
    "n": "idx_scene_job_state_stage_status",
    "def": "CREATE INDEX idx_scene_job_state_stage_status ON public.scene_job_state USING btree (stage_status)"
   },
   {
    "t": "scene_job_state",
    "n": "scene_job_state_pkey",
    "def": "CREATE UNIQUE INDEX scene_job_state_pkey ON public.scene_job_state USING btree (id)"
   },
   {
    "t": "scene_job_state",
    "n": "uq_job_product",
    "def": "CREATE UNIQUE INDEX uq_job_product ON public.scene_job_state USING btree (job_id, product_identifier)"
   },
   {
    "t": "spectral_bands",
    "n": "idx_bands_source",
    "def": "CREATE INDEX idx_bands_source ON public.spectral_bands USING btree (source_id)"
   },
   {
    "t": "spectral_bands",
    "n": "spectral_bands_band_code_key",
    "def": "CREATE UNIQUE INDEX spectral_bands_band_code_key ON public.spectral_bands USING btree (band_code)"
   },
   {
    "t": "spectral_bands",
    "n": "spectral_bands_pkey",
    "def": "CREATE UNIQUE INDEX spectral_bands_pkey ON public.spectral_bands USING btree (band_id)"
   },
   {
    "t": "user_activity_logs",
    "n": "idx_activity_action_time",
    "def": "CREATE INDEX idx_activity_action_time ON public.user_activity_logs USING btree (action, logged_at DESC)"
   },
   {
    "t": "user_activity_logs",
    "n": "idx_activity_user_time",
    "def": "CREATE INDEX idx_activity_user_time ON public.user_activity_logs USING btree (user_id, logged_at DESC)"
   },
   {
    "t": "user_activity_logs",
    "n": "user_activity_logs_pkey",
    "def": "CREATE UNIQUE INDEX user_activity_logs_pkey ON public.user_activity_logs USING btree (log_id)"
   },
   {
    "t": "users",
    "n": "idx_users_role",
    "def": "CREATE INDEX idx_users_role ON public.users USING btree (role_id)"
   },
   {
    "t": "users",
    "n": "uq_users_email",
    "def": "CREATE UNIQUE INDEX uq_users_email ON public.users USING btree (lower((email)::text)) WHERE (email IS NOT NULL)"
   },
   {
    "t": "users",
    "n": "users_pkey",
    "def": "CREATE UNIQUE INDEX users_pkey ON public.users USING btree (user_id)"
   },
   {
    "t": "users",
    "n": "users_username_key",
    "def": "CREATE UNIQUE INDEX users_username_key ON public.users USING btree (username)"
   }
  ],
  "grants": [
   {
    "role": "monitor_admin",
    "obj": "administrative_regions",
    "priv": "INSERT,SELECT,UPDATE"
   },
   {
    "role": "monitor_etl",
    "obj": "administrative_regions",
    "priv": "SELECT"
   },
   {
    "role": "monitor_public",
    "obj": "administrative_regions",
    "priv": "SELECT"
   },
   {
    "role": "monitor_user",
    "obj": "administrative_regions",
    "priv": "SELECT"
   },
   {
    "role": "monitor_admin",
    "obj": "alert_events",
    "priv": "DELETE,INSERT,SELECT,UPDATE"
   },
   {
    "role": "monitor_etl",
    "obj": "alert_events",
    "priv": "INSERT,SELECT"
   },
   {
    "role": "monitor_user",
    "obj": "alert_events",
    "priv": "SELECT"
   },
   {
    "role": "monitor_admin",
    "obj": "alert_rules",
    "priv": "INSERT,SELECT,UPDATE"
   },
   {
    "role": "monitor_etl",
    "obj": "alert_rules",
    "priv": "SELECT"
   },
   {
    "role": "monitor_user",
    "obj": "alert_rules",
    "priv": "SELECT"
   },
   {
    "role": "monitor_user",
    "obj": "api_tokens",
    "priv": "INSERT,SELECT,UPDATE"
   },
   {
    "role": "monitor_admin",
    "obj": "app_settings",
    "priv": "INSERT,SELECT,UPDATE"
   },
   {
    "role": "monitor_etl",
    "obj": "app_settings",
    "priv": "SELECT"
   },
   {
    "role": "monitor_user",
    "obj": "app_settings",
    "priv": "SELECT"
   },
   {
    "role": "monitor_admin",
    "obj": "audit_log",
    "priv": "SELECT"
   },
   {
    "role": "monitor_analyst",
    "obj": "band_forecast_points",
    "priv": "SELECT"
   },
   {
    "role": "monitor_etl",
    "obj": "band_forecast_points",
    "priv": "DELETE,INSERT,SELECT"
   },
   {
    "role": "monitor_analyst",
    "obj": "band_forecast_scores",
    "priv": "SELECT"
   },
   {
    "role": "monitor_etl",
    "obj": "band_forecast_scores",
    "priv": "DELETE,INSERT,SELECT"
   },
   {
    "role": "monitor_analyst",
    "obj": "band_forecasts",
    "priv": "SELECT"
   },
   {
    "role": "monitor_etl",
    "obj": "band_forecasts",
    "priv": "DELETE,INSERT,SELECT"
   },
   {
    "role": "monitor_data_engineer",
    "obj": "cleanup_operations",
    "priv": "SELECT"
   },
   {
    "role": "monitor_etl",
    "obj": "cleanup_operations",
    "priv": "INSERT,SELECT,UPDATE"
   },
   {
    "role": "monitor_data_engineer",
    "obj": "data_lineage",
    "priv": "SELECT"
   },
   {
    "role": "monitor_etl",
    "obj": "data_lineage",
    "priv": "INSERT,SELECT,UPDATE"
   },
   {
    "role": "monitor_data_engineer",
    "obj": "data_products",
    "priv": "SELECT"
   },
   {
    "role": "monitor_etl",
    "obj": "data_products",
    "priv": "DELETE,INSERT,SELECT,UPDATE"
   },
   {
    "role": "monitor_admin",
    "obj": "dataset_jobs",
    "priv": "DELETE"
   },
   {
    "role": "monitor_data_engineer",
    "obj": "dataset_jobs",
    "priv": "INSERT,SELECT,UPDATE"
   },
   {
    "role": "monitor_etl",
    "obj": "dataset_jobs",
    "priv": "INSERT,SELECT,UPDATE"
   },
   {
    "role": "monitor_admin",
    "obj": "dataset_source_config",
    "priv": "DELETE"
   },
   {
    "role": "monitor_data_engineer",
    "obj": "dataset_source_config",
    "priv": "INSERT,SELECT,UPDATE"
   },
   {
    "role": "monitor_etl",
    "obj": "dataset_source_config",
    "priv": "INSERT,SELECT,UPDATE"
   },
   {
    "role": "monitor_admin",
    "obj": "datasets",
    "priv": "DELETE"
   },
   {
    "role": "monitor_data_engineer",
    "obj": "datasets",
    "priv": "INSERT,SELECT,UPDATE"
   },
   {
    "role": "monitor_etl",
    "obj": "datasets",
    "priv": "DELETE,INSERT,SELECT,UPDATE"
   },
   {
    "role": "monitor_analyst",
    "obj": "disaster_events",
    "priv": "INSERT,SELECT,UPDATE"
   },
   {
    "role": "monitor_etl",
    "obj": "disaster_events",
    "priv": "SELECT"
   },
   {
    "role": "monitor_user",
    "obj": "disaster_events",
    "priv": "SELECT"
   },
   {
    "role": "monitor_admin",
    "obj": "disaster_types",
    "priv": "INSERT,SELECT,UPDATE"
   },
   {
    "role": "monitor_etl",
    "obj": "disaster_types",
    "priv": "SELECT"
   },
   {
    "role": "monitor_public",
    "obj": "disaster_types",
    "priv": "SELECT"
   },
   {
    "role": "monitor_user",
    "obj": "disaster_types",
    "priv": "SELECT"
   },
   {
    "role": "monitor_data_engineer",
    "obj": "fusion_products",
    "priv": "SELECT"
   },
   {
    "role": "monitor_etl",
    "obj": "fusion_products",
    "priv": "INSERT,SELECT,UPDATE"
   },
   {
    "role": "monitor_etl",
    "obj": "fusion_strategies",
    "priv": "SELECT"
   },
   {
    "role": "monitor_user",
    "obj": "fusion_strategies",
    "priv": "SELECT"
   },
   {
    "role": "monitor_admin",
    "obj": "generated_reports",
    "priv": "INSERT,SELECT,UPDATE"
   },
   {
    "role": "monitor_analyst",
    "obj": "generated_reports",
    "priv": "SELECT"
   },
   {
    "role": "monitor_data_engineer",
    "obj": "generated_reports",
    "priv": "SELECT"
   },
   {
    "role": "monitor_etl",
    "obj": "generated_reports",
    "priv": "INSERT,SELECT,UPDATE"
   },
   {
    "role": "monitor_admin",
    "obj": "live_areas",
    "priv": "INSERT,SELECT,UPDATE"
   },
   {
    "role": "monitor_etl",
    "obj": "live_areas",
    "priv": "INSERT,SELECT,UPDATE"
   },
   {
    "role": "monitor_user",
    "obj": "live_areas",
    "priv": "SELECT"
   },
   {
    "role": "monitor_admin",
    "obj": "live_events",
    "priv": "INSERT,SELECT,UPDATE"
   },
   {
    "role": "monitor_etl",
    "obj": "live_events",
    "priv": "INSERT,SELECT,UPDATE"
   },
   {
    "role": "monitor_user",
    "obj": "live_events",
    "priv": "SELECT"
   },
   {
    "role": "monitor_admin",
    "obj": "live_scene_metrics",
    "priv": "INSERT,SELECT,UPDATE"
   },
   {
    "role": "monitor_etl",
    "obj": "live_scene_metrics",
    "priv": "DELETE,INSERT,SELECT,UPDATE"
   },
   {
    "role": "monitor_user",
    "obj": "live_scene_metrics",
    "priv": "SELECT"
   },
   {
    "role": "monitor_admin",
    "obj": "live_scenes",
    "priv": "INSERT,SELECT,UPDATE"
   },
   {
    "role": "monitor_etl",
    "obj": "live_scenes",
    "priv": "INSERT,SELECT,UPDATE"
   },
   {
    "role": "monitor_user",
    "obj": "live_scenes",
    "priv": "SELECT"
   },
   {
    "role": "monitor_data_engineer",
    "obj": "nasa_scenes",
    "priv": "SELECT,UPDATE"
   },
   {
    "role": "monitor_etl",
    "obj": "nasa_scenes",
    "priv": "INSERT,SELECT,UPDATE"
   },
   {
    "role": "monitor_data_engineer",
    "obj": "processing_jobs",
    "priv": "SELECT"
   },
   {
    "role": "monitor_etl",
    "obj": "processing_jobs",
    "priv": "DELETE,INSERT,SELECT,UPDATE"
   },
   {
    "role": "monitor_data_engineer",
    "obj": "processing_logs",
    "priv": "SELECT"
   },
   {
    "role": "monitor_etl",
    "obj": "processing_logs",
    "priv": "INSERT,SELECT,UPDATE"
   },
   {
    "role": "monitor_etl",
    "obj": "processing_stages",
    "priv": "SELECT"
   },
   {
    "role": "monitor_user",
    "obj": "processing_stages",
    "priv": "SELECT"
   },
   {
    "role": "monitor_data_engineer",
    "obj": "quality_alerts",
    "priv": "SELECT"
   },
   {
    "role": "monitor_etl",
    "obj": "quality_alerts",
    "priv": "INSERT,SELECT,UPDATE"
   },
   {
    "role": "monitor_data_engineer",
    "obj": "quality_metrics",
    "priv": "SELECT"
   },
   {
    "role": "monitor_etl",
    "obj": "quality_metrics",
    "priv": "INSERT,SELECT,UPDATE"
   },
   {
    "role": "monitor_admin",
    "obj": "quality_thresholds",
    "priv": "INSERT,SELECT,UPDATE"
   },
   {
    "role": "monitor_etl",
    "obj": "quality_thresholds",
    "priv": "SELECT"
   },
   {
    "role": "monitor_user",
    "obj": "quality_thresholds",
    "priv": "SELECT"
   },
   {
    "role": "monitor_etl",
    "obj": "region_observations",
    "priv": "INSERT,SELECT,UPDATE"
   },
   {
    "role": "monitor_user",
    "obj": "region_observations",
    "priv": "SELECT"
   },
   {
    "role": "monitor_admin",
    "obj": "regions_of_interest",
    "priv": "INSERT,SELECT,UPDATE"
   },
   {
    "role": "monitor_etl",
    "obj": "regions_of_interest",
    "priv": "SELECT"
   },
   {
    "role": "monitor_user",
    "obj": "regions_of_interest",
    "priv": "SELECT"
   },
   {
    "role": "monitor_etl",
    "obj": "report_types",
    "priv": "SELECT"
   },
   {
    "role": "monitor_user",
    "obj": "report_types",
    "priv": "SELECT"
   },
   {
    "role": "monitor_admin",
    "obj": "roles",
    "priv": "INSERT,SELECT,UPDATE"
   },
   {
    "role": "monitor_data_engineer",
    "obj": "satellite_scenes",
    "priv": "SELECT,UPDATE"
   },
   {
    "role": "monitor_etl",
    "obj": "satellite_scenes",
    "priv": "INSERT,SELECT,UPDATE"
   },
   {
    "role": "monitor_etl",
    "obj": "satellite_sources",
    "priv": "SELECT"
   },
   {
    "role": "monitor_public",
    "obj": "satellite_sources",
    "priv": "SELECT"
   },
   {
    "role": "monitor_user",
    "obj": "satellite_sources",
    "priv": "SELECT"
   },
   {
    "role": "monitor_admin",
    "obj": "scene_job_state",
    "priv": "DELETE"
   },
   {
    "role": "monitor_data_engineer",
    "obj": "scene_job_state",
    "priv": "INSERT,SELECT,UPDATE"
   },
   {
    "role": "monitor_etl",
    "obj": "scene_job_state",
    "priv": "INSERT,SELECT,UPDATE"
   },
   {
    "role": "monitor_etl",
    "obj": "spectral_bands",
    "priv": "SELECT"
   },
   {
    "role": "monitor_public",
    "obj": "spectral_bands",
    "priv": "SELECT"
   },
   {
    "role": "monitor_user",
    "obj": "spectral_bands",
    "priv": "SELECT"
   },
   {
    "role": "monitor_admin",
    "obj": "user_activity_logs",
    "priv": "SELECT"
   },
   {
    "role": "monitor_etl",
    "obj": "user_activity_logs",
    "priv": "INSERT"
   },
   {
    "role": "monitor_public",
    "obj": "user_activity_logs",
    "priv": "INSERT"
   },
   {
    "role": "monitor_admin",
    "obj": "users",
    "priv": "INSERT,SELECT,UPDATE"
   },
   {
    "role": "monitor_etl",
    "obj": "v_alert_aktif",
    "priv": "SELECT"
   },
   {
    "role": "monitor_user",
    "obj": "v_alert_aktif",
    "priv": "SELECT"
   },
   {
    "role": "monitor_public",
    "obj": "v_citra_metrics",
    "priv": "SELECT"
   },
   {
    "role": "monitor_public",
    "obj": "v_citra_obs_aoi",
    "priv": "SELECT"
   },
   {
    "role": "monitor_public",
    "obj": "v_citra_scenes",
    "priv": "SELECT"
   },
   {
    "role": "monitor_analyst",
    "obj": "v_evaluasi_alert",
    "priv": "SELECT"
   },
   {
    "role": "monitor_etl",
    "obj": "v_evaluasi_alert",
    "priv": "SELECT"
   },
   {
    "role": "monitor_etl",
    "obj": "v_hujan_harian_kecamatan",
    "priv": "SELECT"
   },
   {
    "role": "monitor_user",
    "obj": "v_hujan_harian_kecamatan",
    "priv": "SELECT"
   },
   {
    "role": "monitor_analyst",
    "obj": "v_kejadian_dan_hujan",
    "priv": "SELECT"
   },
   {
    "role": "monitor_etl",
    "obj": "v_kejadian_dan_hujan",
    "priv": "SELECT"
   },
   {
    "role": "monitor_data_engineer",
    "obj": "v_kelengkapan_data",
    "priv": "SELECT"
   },
   {
    "role": "monitor_etl",
    "obj": "v_kelengkapan_data",
    "priv": "SELECT"
   },
   {
    "role": "monitor_etl",
    "obj": "v_live_scenes_recent",
    "priv": "SELECT"
   },
   {
    "role": "monitor_user",
    "obj": "v_live_scenes_recent",
    "priv": "SELECT"
   },
   {
    "role": "monitor_data_engineer",
    "obj": "v_log_data",
    "priv": "SELECT"
   },
   {
    "role": "monitor_analyst",
    "obj": "v_log_kejadian",
    "priv": "SELECT"
   },
   {
    "role": "monitor_admin",
    "obj": "v_log_login",
    "priv": "SELECT"
   },
   {
    "role": "monitor_admin",
    "obj": "v_log_unduhan",
    "priv": "SELECT"
   },
   {
    "role": "monitor_public",
    "obj": "v_public_kejadian",
    "priv": "SELECT"
   },
   {
    "role": "monitor_public",
    "obj": "v_public_live_latest",
    "priv": "SELECT"
   },
   {
    "role": "monitor_data_engineer",
    "obj": "v_ringkasan_kualitas",
    "priv": "SELECT"
   },
   {
    "role": "monitor_etl",
    "obj": "v_ringkasan_kualitas",
    "priv": "SELECT"
   },
   {
    "role": "monitor_etl",
    "obj": "v_statistik_hari_ini",
    "priv": "SELECT"
   },
   {
    "role": "monitor_user",
    "obj": "v_statistik_hari_ini",
    "priv": "SELECT"
   },
   {
    "role": "monitor_data_engineer",
    "obj": "v_unduhan_per_role",
    "priv": "SELECT"
   },
   {
    "role": "monitor_etl",
    "obj": "v_unduhan_per_role",
    "priv": "SELECT"
   },
   {
    "role": "monitor_user",
    "obj": "v_users_safe",
    "priv": "SELECT"
   }
  ],
  "colgrants": [
   {
    "role": "monitor_analyst",
    "obj": "alert_events",
    "col": "ack_note",
    "priv": "UPDATE"
   },
   {
    "role": "monitor_analyst",
    "obj": "alert_events",
    "col": "acknowledged_at",
    "priv": "UPDATE"
   },
   {
    "role": "monitor_analyst",
    "obj": "alert_events",
    "col": "acknowledged_by",
    "priv": "UPDATE"
   }
  ],
  "members": [
   {
    "role": "monitor_admin",
    "member": "monitor_app"
   },
   {
    "role": "monitor_data_engineer",
    "member": "monitor_app"
   },
   {
    "role": "monitor_analyst",
    "member": "monitor_app"
   },
   {
    "role": "monitor_user",
    "member": "monitor_app"
   },
   {
    "role": "monitor_public",
    "member": "monitor_app"
   },
   {
    "role": "monitor_public",
    "member": "monitor_user"
   },
   {
    "role": "monitor_user",
    "member": "monitor_analyst"
   },
   {
    "role": "monitor_user",
    "member": "monitor_data_engineer"
   },
   {
    "role": "monitor_data_engineer",
    "member": "monitor_admin"
   },
   {
    "role": "monitor_analyst",
    "member": "monitor_admin"
   }
  ],
  "policies": [
   {
    "t": "api_tokens",
    "n": "tok_owner",
    "cmd": "ALL",
    "roles": "public",
    "using": "((user_id = (NULLIF(current_setting('app.user_id'::text, true), ''::text))::integer) OR pg_has_role(CURRENT_USER, 'monitor_admin'::name, 'MEMBER'::text))",
    "check": ""
   },
   {
    "t": "generated_reports",
    "n": "rp_audience",
    "cmd": "SELECT",
    "roles": "public",
    "using": "pg_has_role(CURRENT_USER, (report_audience_db_role(report_type_id))::name, 'MEMBER'::text)",
    "check": ""
   },
   {
    "t": "generated_reports",
    "n": "rp_writers",
    "cmd": "ALL",
    "roles": "monitor_admin,monitor_etl",
    "using": "true",
    "check": "true"
   }
  ],
  "triggers": [
   {
    "t": "administrative_regions",
    "n": "trg_audit_administrative_regions",
    "ev": "UPDATE",
    "timing": "AFTER",
    "stmt": "EXECUTE FUNCTION audit_row('region_id')"
   },
   {
    "t": "alert_events",
    "n": "trg_audit_alert_events",
    "ev": "DELETE/INSERT/UPDATE",
    "timing": "AFTER",
    "stmt": "EXECUTE FUNCTION audit_row('alert_id')"
   },
   {
    "t": "alert_rules",
    "n": "trg_alert_rules_updated_at",
    "ev": "UPDATE",
    "timing": "BEFORE",
    "stmt": "EXECUTE FUNCTION fn_set_updated_at()"
   },
   {
    "t": "alert_rules",
    "n": "trg_audit_alert_rules",
    "ev": "DELETE/INSERT/UPDATE",
    "timing": "AFTER",
    "stmt": "EXECUTE FUNCTION audit_row('rule_id')"
   },
   {
    "t": "api_tokens",
    "n": "trg_audit_api_tokens",
    "ev": "DELETE/INSERT/UPDATE",
    "timing": "AFTER",
    "stmt": "EXECUTE FUNCTION audit_row('token_id', 'last_used_at')"
   },
   {
    "t": "app_settings",
    "n": "trg_app_settings_updated_at",
    "ev": "UPDATE",
    "timing": "BEFORE",
    "stmt": "EXECUTE FUNCTION fn_set_updated_at()"
   },
   {
    "t": "app_settings",
    "n": "trg_audit_app_settings",
    "ev": "DELETE/INSERT/UPDATE",
    "timing": "AFTER",
    "stmt": "EXECUTE FUNCTION audit_row('setting_key')"
   },
   {
    "t": "data_products",
    "n": "trg_data_products_updated_at",
    "ev": "UPDATE",
    "timing": "BEFORE",
    "stmt": "EXECUTE FUNCTION fn_set_updated_at()"
   },
   {
    "t": "dataset_source_config",
    "n": "trg_dataset_source_config_updated_at",
    "ev": "UPDATE",
    "timing": "BEFORE",
    "stmt": "EXECUTE FUNCTION fn_set_updated_at()"
   },
   {
    "t": "datasets",
    "n": "trg_audit_datasets",
    "ev": "DELETE/INSERT/UPDATE",
    "timing": "AFTER",
    "stmt": "EXECUTE FUNCTION audit_row('dataset_id', 'total_scenes', 'completed_scenes', 'failed_scenes', 'total_size_bytes')"
   },
   {
    "t": "datasets",
    "n": "trg_datasets_updated_at",
    "ev": "UPDATE",
    "timing": "BEFORE",
    "stmt": "EXECUTE FUNCTION fn_set_updated_at()"
   },
   {
    "t": "disaster_events",
    "n": "trg_audit_disaster_events",
    "ev": "DELETE/INSERT/UPDATE",
    "timing": "AFTER",
    "stmt": "EXECUTE FUNCTION audit_row('event_id')"
   },
   {
    "t": "disaster_events",
    "n": "trg_disaster_events_updated_at",
    "ev": "UPDATE",
    "timing": "BEFORE",
    "stmt": "EXECUTE FUNCTION fn_set_updated_at()"
   },
   {
    "t": "disaster_types",
    "n": "trg_audit_disaster_types",
    "ev": "DELETE/INSERT/UPDATE",
    "timing": "AFTER",
    "stmt": "EXECUTE FUNCTION audit_row('disaster_type_id')"
   },
   {
    "t": "live_areas",
    "n": "trg_audit_live_areas",
    "ev": "DELETE/INSERT/UPDATE",
    "timing": "AFTER",
    "stmt": "EXECUTE FUNCTION audit_row('area_id', 'status', 'status_message', 'last_checked_at', 'forecast', 'forecast_updated_at')"
   },
   {
    "t": "live_areas",
    "n": "trg_live_areas_updated_at",
    "ev": "UPDATE",
    "timing": "BEFORE",
    "stmt": "EXECUTE FUNCTION fn_set_updated_at()"
   },
   {
    "t": "live_scenes",
    "n": "trg_live_scenes_updated_at",
    "ev": "UPDATE",
    "timing": "BEFORE",
    "stmt": "EXECUTE FUNCTION fn_set_updated_at()"
   },
   {
    "t": "nasa_scenes",
    "n": "trg_audit_nasa_scenes",
    "ev": "UPDATE",
    "timing": "AFTER",
    "stmt": "EXECUTE FUNCTION audit_row('nasa_scene_id')"
   },
   {
    "t": "processing_jobs",
    "n": "trg_processing_jobs_updated_at",
    "ev": "UPDATE",
    "timing": "BEFORE",
    "stmt": "EXECUTE FUNCTION fn_set_updated_at()"
   },
   {
    "t": "processing_stages",
    "n": "trg_processing_stages_updated_at",
    "ev": "UPDATE",
    "timing": "BEFORE",
    "stmt": "EXECUTE FUNCTION fn_set_updated_at()"
   },
   {
    "t": "quality_thresholds",
    "n": "trg_audit_quality_thresholds",
    "ev": "DELETE/INSERT/UPDATE",
    "timing": "AFTER",
    "stmt": "EXECUTE FUNCTION audit_row('threshold_id')"
   },
   {
    "t": "region_observations",
    "n": "trg_obs_range",
    "ev": "INSERT/UPDATE",
    "timing": "BEFORE",
    "stmt": "EXECUTE FUNCTION fn_obs_range()"
   },
   {
    "t": "regions_of_interest",
    "n": "trg_regions_of_interest_updated_at",
    "ev": "UPDATE",
    "timing": "BEFORE",
    "stmt": "EXECUTE FUNCTION fn_set_updated_at()"
   },
   {
    "t": "regions_of_interest",
    "n": "trg_roi_centroid",
    "ev": "INSERT/UPDATE",
    "timing": "BEFORE",
    "stmt": "EXECUTE FUNCTION fn_compute_roi_centroid()"
   },
   {
    "t": "satellite_scenes",
    "n": "trg_audit_satellite_scenes",
    "ev": "UPDATE",
    "timing": "AFTER",
    "stmt": "EXECUTE FUNCTION audit_row('scene_id')"
   },
   {
    "t": "satellite_scenes",
    "n": "trg_satellite_scenes_updated_at",
    "ev": "UPDATE",
    "timing": "BEFORE",
    "stmt": "EXECUTE FUNCTION fn_set_updated_at()"
   },
   {
    "t": "users",
    "n": "trg_audit_users",
    "ev": "DELETE/INSERT/UPDATE",
    "timing": "AFTER",
    "stmt": "EXECUTE FUNCTION audit_row('user_id', 'last_login_at', 'failed_login_count')"
   },
   {
    "t": "users",
    "n": "trg_users_role_not_public",
    "ev": "INSERT/UPDATE",
    "timing": "BEFORE",
    "stmt": "EXECUTE FUNCTION fn_users_role_not_public()"
   },
   {
    "t": "users",
    "n": "trg_users_updated_at",
    "ev": "UPDATE",
    "timing": "BEFORE",
    "stmt": "EXECUTE FUNCTION fn_set_updated_at()"
   }
  ]
 }
};
