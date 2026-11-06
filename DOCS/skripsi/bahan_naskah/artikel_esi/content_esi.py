# Isi artikel Earth Science Informatics (Springer), jenis Software article.
# Ditulis ulang dari skripsi (bab4.py, build_skripsi.py) dan DOCS/PIPELINE.md dengan fokus geoinformatika:
# harmonisasi data observasi bumi, model data, provenance, ketahanan pipeline, reproduktibilitas.
# Konteks pengguna/GMLS diringkas. Angka hanya dari skripsi/dokumen; bobot zonal mengikuti kode
# (etl/hydromet_aggregate.py: luas irisan x cos(lintang)).
# Markup: *miring*, **tebal**, [@kunci] sitasi penulis-tahun, [@!kunci] naratif, {F:x}, {T:x}, ~sub~, ^sup^.

TITLE = ("Orbit-U: The Monitor – a provenance-aware PostGIS database and processing pipeline that harmonises "
         "Sentinel-1, MODIS and GPM IMERG into sub-district time series")
ARTICLE_TYPE = "Software article"

AUTHORS = [("Muhammad Faiq Hakim Ulinnuha", 1, True), ("[Supervisor name]", 1, False)]
AFFIL = ["Department of Information Systems, Faculty of Engineering and Informatics, Universitas Multimedia "
         "Nusantara, Tangerang, Banten, Indonesia"]
CORRESP = "Muhammad Faiq Hakim Ulinnuha, e-mail: [to be completed]"
ORCID = ["Muhammad Faiq Hakim Ulinnuha: [16-digit ORCID, to be completed]",
         "[Supervisor name]: [16-digit ORCID, to be completed]"]
ACK = ("The authors thank the chairman and volunteers of Gugus Mitigasi Lebak Selatan for the interview and the "
       "requirements review, and all participants of the user trial.")

ABSTRACT = (
    "Open Earth observation archives are easy to download but hard to keep: synthetic aperture radar scenes, optical "
    "composites and gridded precipitation differ in format, resolution and revisit time, and once they are processed "
    "the link between a reported number and its source file is usually lost. This article presents Orbit-U: The "
    "Monitor, an open-source PostgreSQL/PostGIS database with a Python processing pipeline that harmonises Sentinel-1, "
    "MODIS and GPM IMERG into one daily time series per administrative sub-district. Rasters pass through seven "
    "ordered artefact tiers and are reduced to sub-district values by zonal aggregation weighted by cell–polygon "
    "overlap, together with the valid fraction of each polygon. Eleven variables are stored as rows of a single "
    "observation relation, so that new variables require no schema change. Every file is registered with a SHA-256 "
    "checksum and every transformation as an edge of a lineage graph, so that any value can be traced to its raw "
    "scene. Idempotent upserts with an explicit precedence of GPM runs, advisory locks and catch-up logic make the "
    "pipeline restartable, and role-based access control is enforced inside the database. Deployed for ten "
    "sub-districts of South Lebak, Indonesia, the database holds 72 850 observations from January 2024 to October "
    "2026; it passed 1183 of 1185 automated tests and recovered exactly after backup restoration and process kills.")
KEYWORDS = ("Earth observation data harmonisation · Data provenance · Spatial database · PostGIS · Zonal statistics · "
            "Sentinel-1")

BODY = [
("H1", "Introduction"),
("P", "Open access to Earth observation (EO) data has changed what small organisations can monitor. The Copernicus "
      "Data Space Ecosystem distributes Sentinel data through application programming interfaces and cloud processing "
      "[@kovacs]; MODIS offers more than two decades of daily observations with continuity into VIIRS [@roman]; and "
      "GPM IMERG provides global precipitation estimates whose long-term behaviour over land is well documented "
      "[@zhu]. For hydrometeorological hazards the three missions are complementary: Sentinel-1 synthetic aperture "
      "radar (SAR) detects open water regardless of cloud cover [@tarpanelli, @tran, @misra], MODIS describes surface water "
      "and vegetation on cloud-free days [@klein], and IMERG describes the rainfall that drives both, which matters "
      "where rain gauges are sparse [@hidayah, @ansori]."),
("P", "Using the three missions together is, however, an informatics problem before it is an analytical one. The "
      "products arrive as GeoTIFF, HDF4-EOS, HDF5 or NetCDF, at about 10 m to 0.1°, every day or every 6–12 days, and "
      "with run types or quality flags that may later be superseded. Existing open tools concentrate on producing "
      "analysis-ready images, for example Sentinel-1 preprocessing pipelines or analysis-ready data cubes "
      "[@weiss, @upadhyay], and multi-sensor studies typically analyse a single event [@liu, @castro]. What is "
      "rarely addressed is the persistent layer behind such work: a database in which the outputs are stored in a "
      "comparable form, revised when better inputs appear, and traceable to the files and parameters that produced "
      "them. In data engineering, lineage is increasingly treated as metadata that the pipeline itself must record "
      "[@gopaluni], and PostGIS has been shown to outperform general relational approaches for spatial storage and "
      "queries [@kaptosv, @papasani], but these strands have not been combined for multi-mission EO time series."),
("P", "This article describes Orbit-U: The Monitor, an open-source system built for Gugus Mitigasi Lebak Selatan "
      "(GMLS), a community disaster mitigation group in Banten, Indonesia, whose earlier information work concerned "
      "earthquakes and tsunamis [@tilung, @wong] and which had no hydrometeorological data of its own. The "
      "contributions are (1) a harmonisation procedure that reduces three missions to one sub-district time series "
      "with an explicit valid-coverage measure; (2) a long-format data model in which variables are data rather than "
      "columns; (3) provenance recorded by the pipeline as checksummed products and lineage edges; (4) a restartable "
      "pipeline whose writes are idempotent and whose revisions follow a stated precedence; and (5) role-based access "
      "control enforced in the database rather than only in the application. The design followed the Database System "
      "Development Life Cycle and is evaluated by automated tests, a DBMS benchmark, recovery experiments and a user "
      "trial."),

("H1", "Design and implementation"),
("H2", "Requirements"),
("P", "Requirements were derived from observation of GMLS, an interview with its chairman, examination of its "
      "documents and data, and a literature study, and were confirmed by a requirements review questionnaire answered "
      "by the chairman and two volunteers. Expressed in informatics terms, the system had to (R1) integrate the three "
      "missions into one unit of analysis; (R2) record every output file with its checksum and the transformation "
      "that produced it; (R3) measure data quality and flag values below a threshold; (R4) generate rainfall warnings "
      "from stored values and record who acknowledged them; (R5) archive disaster events with source and verification "
      "status; and (R6) restrict data by role and audit changes. Demographic and evacuation data remain in an "
      "existing village application and are outside the database."),
("H2", "Study area and input data"),
("P", "The unit of analysis is the sub-district (*kecamatan*). Ten sub-districts in the south of Lebak Regency were "
      "selected with GMLS ({F:area}); their boundaries come from the Indonesian COD-AB dataset [@codab] and cover "
      "1575.8 km^2^, from about 94.9 km^2^ (Cilograng) to 400.8 km^2^ (Cibeber). The input products are listed in "
      "{T:data}. Because the sources cannot be compared pixel by pixel, the polygon rather than the grid cell is the "
      "common denominator of all stored values."),
("FIG", "area"),
("TAB", "data"),
("H2", "Processing pipeline and artefact tiers"),
("P", "Each mission is processed through ordered artefact tiers ({F:pipeline}). RAW holds the vendor file. ALIGNED "
      "holds the product reprojected to EPSG:4326 and cropped to the area of interest; for Sentinel-1 this already "
      "includes radiometric calibration to σ⁰, because uncalibrated digital numbers have no physical meaning. "
      "DESPECKLED applies a 7×7 Lee filter to SAR; INDICES holds MODIS NDVI and NDWI (McFeeters, green/NIR) after "
      "removal of cloud, shadow and cirrus pixels; and ACCUMULATED holds IMERG totals over 24 h, 72 h, 7 days and 30 "
      "days. Every band then becomes a Cloud-Optimised GeoTIFF (COG), and an optional FUSED tier stores multi-sensor "
      "HDF5. MODIS flood fraction is taken from the daily MCDWD product (two-day composite, 250 m) and vegetation "
      "and water indices from MOD09A1 (eight-day, 500 m) with MOD09GA as daily fallback. For IMERG, the Final, Late "
      "and Early runs are tried in that order and the run used is stored with each value."),
("FIG", "pipeline"),
("P", "Raster files are kept in the file system; the database stores their metadata, location and checksum. Rasters "
      "of the operational dataset are retained for 365 days, whereas sub-district values are kept indefinitely. A "
      "product whose file has been removed is marked invalid instead of deleted, so that its lineage remains "
      "readable. Separating heavy, regenerable files from light, permanent values keeps the database small while "
      "preserving the record of how every value was derived."),
("H2", "Zonal harmonisation"),
("P", "Sub-district values are computed in Python from the COGs. All cells touched by a polygon are selected, and "
      "each receives a weight equal to the planar area of its intersection with the polygon multiplied by the cosine "
      "of its latitude, which approximates the true area on the sphere. The value of band *b* for sub-district *r* on "
      "date *t* is the weighted mean of valid cells:"),
("EQ", "zonal"),
("P", "where *a*~r,c~ is the intersection area of cell *c* with polygon *r*, φ~c~ the latitude of the cell centre, "
      "*x*~c~ the cell value and *V*~r~ the set of valid cells. Overlap weighting matters for coarse grids: a 0.1° "
      "IMERG cell covers a sub-district with only one to six cells, so a cell that barely touches the polygon must "
      "not count fully. The valid fraction, the share of total weight carried by valid cells, is stored with each "
      "value; below 0.1 the value is stored as NULL rather than computed from a small cloud-free remnant, since optical pixels are frequently invalid under cloud cover [@tang]. Flood "
      "fraction is computed analogously as the weighted share of MCDWD water classes."),
("P", "Values are written with an upsert on the key (region, band, date) that replaces an existing value only if "
      "the new GPM run is not worse (Final over Late over Early) or the old value is NULL; a NULL never overwrites a "
      "value. Because IMERG Final appears about 3.5 months after observation, a weekly job recomputes dates in the "
      "last 153 days that still carry Late or Early values, and the upsert replaces them when Final is available. "
      "Revision thus needs no invalidation flags, and warnings already generated keep a copy of the value and "
      "threshold that triggered them."),
("H2", "Data model"),
("P", "The central relation region_observations ({F:erd}) has the alternate key (region_id, band_id, obs_date) and "
      "stores eleven variables as rows: VV and VH backscatter, water percentage and water change from Sentinel-1; "
      "flood fraction, NDVI and NDWI from MODIS; and 24-hour, 72-hour, 7-day and 30-day rainfall from IMERG. Each row "
      "also carries the valid fraction, the GPM run type and the identifier of the source product. Variables are "
      "described in spectral_bands, which defines physical limits that a trigger enforces, so that a processing error "
      "such as negative rainfall is rejected at insertion. Adding a variable is therefore an insertion into "
      "spectral_bands, not a schema migration."),
("FIG", "erd"),
("P", "The model was obtained by normalising an observation record that repeated sub-district, regency, band, unit "
      "and satellite in every row; moving these attributes to their own relations, with the regency as a recursive "
      "reference among administrative regions, yields third normal form, and selected relations were checked against "
      "Boyce–Codd and fourth normal form [@skavantzos, @zhang]. Integrity rules are declared in the database rather "
      "than inferred from application code [@huang, @kanwal]: the implemented schema has 43 tables, 22 views, 80 "
      "foreign keys, 67 check constraints and 29 triggers. Indexes follow access patterns: GiST on boundaries, scene "
      "footprints and event locations; descending B-trees for the latest values of a series; a partial index on "
      "unacknowledged warnings; and two B-trees on lineage edges for traversal in both directions."),
("H2", "Provenance"),
("P", "Provenance is held by three relations ({F:lineage}). data_products registers every file of every tier with "
      "its SHA-256 checksum; data_lineage stores each transformation (for example calibration, speckle filtering or "
      "COG conversion) as an edge from a parent to a child product with input and output checksums; and "
      "processing_jobs stores, for each stage, a JSON record of the software version, GPM run, accumulation window "
      "and thresholds used. A stored value is followed through source_product_id and a recursive query to the raw "
      "scene. Because edges carry checksums, a file altered after processing can be detected, and a doubtful value "
      "can be recomputed from its parent product without downloading the archive again. Quality metrics computed per "
      "scene are compared with configurable thresholds and raise quality alerts."),
("FIG", "lineage"),
("H2", "Scheduling, locking and recovery"),
("P", "One scheduler runs the daily hydrometeorological job, the weekly Final refresh, a six-hourly Sentinel-1 cycle "
      "and periodic reports. Each job type takes a PostgreSQL advisory lock on a dedicated connection; a second "
      "worker that cannot obtain it records the run as SKIPPED_LOCKED, and the lock is released automatically if the "
      "process dies. The daily job processes GPM first, because warnings depend only on rainfall, and treats MODIS as "
      "non-fatal. {T:fail} summarises how the pipeline reacts to the failures observed in operation; in every case "
      "recovery consists of running the same command again, because all writes are idempotent."),
("TAB", "fail"),
("H2", "Access control and interfaces"),
("P", "Five application roles (visitor, volunteer, analyst, data engineer and administrator) map to PostgreSQL "
      "roles. The ETL connects as a dedicated role; the FastAPI REST API connects as a NOINHERIT role without "
      "privileges and switches with SET LOCAL ROLE to the role of the requesting user in every transaction. Views "
      "restrict the time window per role (visitors 30 days of imagery, volunteers 365 days), row-level security "
      "limits generated reports to their audience and API tokens to their owner, and one audit trigger function stores old and new rows as JSON. The approach "
      "extends GRANT-based role control in PostgreSQL [@purwitasari] with per-transaction role switching and "
      "row-level security. A web client presents the latest condition per sub-district, imagery, warnings based on "
      "the 50, 100 and 150 mm thresholds of the Indonesian meteorological agency, and disaster events."),
("H2", "DBMS selection procedure"),
("P", "PostgreSQL 18.6 with PostGIS 3.6.2 and MySQL 8.0.40 were compared on an equivalent schema with identical deterministic synthetic data (a grid of 28 synthetic sub-district polygons, ten forming the area of interest; 76 720 observations; synthetic warnings and events, so that warning evaluation can be measured) and default configurations. All tests ran on one machine (Intel Core i7-7700, 32 GB RAM, Windows 10) with the data directories of both systems on the same 7200 rpm HDD, a 128 MB buffer and a flush on every commit. Five core "
      "queries were run 30 times after five warm-up runs in three separate runs, and medians are reported. Security features, scalability (a monthly summary over the whole table, Q6, up to 2.3 million rows), concurrency and write throughput were also tested. PostgreSQL used the C-based psycopg2; MySQL used PyMySQL for the core queries, and the extended tests were repeated with the C-based mysqlclient so that driver overhead does not penalise MySQL. Seven criteria, weighted by the authors from the problem formulation, were scored from 1 to 5: performance by the ratio of the summed median times of the tests behind each criterion (5 faster or within 10%, 4 below 2×, 3 for 2–5×, 2 above 5× or when a query had to be rewritten), features by availability (5 native, 2 workaround, 1 unavailable), and cost and familiarity qualitatively. The total is"),
("EQ", "score"),
("P", "where *w*~i~ is the weight and *s*~i~ the score of criterion *i*. An AI assistant was used in preparing this "
      "manuscript as described in the Declarations; it was not used to produce data or results."),

("H1", "Results"),
("H2", "Deployment and stored data"),
("P", "The system is deployed with the architecture shown in {F:arch}. Loading started from an empty database: "
      "schema, security objects and reference data were applied in order, the COD-AB boundaries were loaded, and "
      "GPM, MODIS and Sentinel-1 data were backfilled through the same code path as the daily jobs. As of 24 October "
      "2026 the database held 72 850 sub-district observations from 1 January 2024 to 22 October 2026, 15 850 data "
      "products, 8142 lineage edges, 7958 processing jobs and 210 warnings derived from the observations. Such "
      "multi-year records are a precondition for interpreting the behaviour of an area [@halder]."),
("FIG", "arch"),
("H2", "DBMS comparison"),
("P", "PostgreSQL was faster in four of five core queries ({T:bench}, {F:bench}), most clearly for polygon "
      "intersection with area computation (Q3, 16×) and for the evaluation of warnings against events (Q4, 14×). The "
      "equivalent Q3 failed in MySQL with error 3516 because the geographic intersection produced a "
      "GeometryCollection and had to be rewritten. MySQL was faster in the recursive lineage query Q5, although both "
      "completed below 1 ms. Result rows were identical, and Q3 areas agreed within 0.1% per sub-district. Over 2.3 million rows the summary query Q6 took 579 ms in PostgreSQL and 1666 ms in MySQL (2.9× with mysqlclient), and inserts were 4.4–6.2 times "
      "faster in PostgreSQL, with both data directories on the same physical disk."),
("TAB", "bench"),
("FIG", "bench"),
("P", "The decision rested on functional rather than temporal differences ({T:score}): MySQL 8.0 switches roles only "
      "per session, lacks row-level security and requires one audit trigger per table. PostgreSQL scored 4.90 and "
      "MySQL 3.05. A first run with PostgreSQL on an SSD and MySQL on an HDD had overstated the storage-sensitive differences (with PyMySQL, Q6 8.5× and inserts 8.2×; MySQL total 2.90). Repeating every test on one disk reduced these to 2.8× and 4.4–6.2× and raised MySQL's analytics score from 2 to 3, while the spatial query (16×), warning evaluation (14×) and security features showed that the decisive differences do not stem from storage."),
("TAB", "score"),
("H2", "Verification and recovery"),
("P", "{T:eval} summarises the evaluation. The final automated run executed 1185 test cases: 1183 passed, none "
      "failed, and 2 were skipped because they need the full boundary shapefile. All core queries completed below "
      "2 ms, and the system reached 8204 queries per second with eight clients. A copy of the production database (44 tables, i.e. the 43 schema tables plus the PostGIS table spatial_ref_sys; 146 541 rows) was dumped and restored, after which the MD5 hashes of all rows, sequences, "
      "constraints and 163 indexes were identical [@ahmad]. A backfill of ten dates killed with SIGKILL resumed only "
      "the two remaining dates, without duplicates or wrong values, in three of three repetitions, and a job started "
      "while its lock was held was skipped as designed."),
("TAB", "eval"),
("P", "GMLS approved the design, two of three respondents with revisions; the main request, notification through "
      "mobile messaging instead of e-mail, was not implemented because of per-message costs, although the "
      "subscription tables do not depend on the channel. In a user trial, 13 lay respondents made 67 attempts at six "
      "tasks, of which 62 (92.5%) succeeded, with a mean ease rating of 4.36 out of 5."),

("H1", "Discussion"),
("P", "Three design decisions carry most of the system. First, storing values rather than rasters in the database, "
      "with rasters as regenerable files, kept the database small enough to restore in seconds while preserving an "
      "indefinite time series; the cost is that raster-level questions must return to the files or the providers. "
      "Second, the long format with physical limits per band turned the addition of a variable into data entry and "
      "allowed one key, one upsert rule and one warning engine to serve all eleven variables. Third, recording "
      "provenance inside the pipeline, as recommended for metadata-driven ETL [@gopaluni], made traceability a by-product "
      "of normal operation rather than a reconstruction effort, and the stated precedence of GPM runs made revision "
      "of near-real-time values a routine, auditable step."),
("P", "Compared with preprocessing tools and data cubes [@weiss, @upadhyay], the system adds persistence, revision "
      "and provenance at the level of administrative units, which is the level at which local organisations act. "
      "Compared with work on integrated geospatial databases [@dev] and role control in PostgreSQL [@purwitasari], it "
      "enforces access in the database, so that unauthorised queries were rejected in tests even with the API checks "
      "disabled."),
("H2", "Limitations"),
("P", "Area weights use the planar intersection area scaled by the cosine of latitude, an approximation of geodesic "
      "area that is adequate at 6–7° S but not exact. The water change map uses a fixed VH threshold of −20 dB rather "
      "than an adaptive method such as Otsu [@tran], so smooth surfaces may appear as water and flooded vegetation as "
      "land. IMERG underestimates extreme daily rainfall [@ansori], and warnings inherit this. A view that classifies "
      "hits, misses and false alarms exists, but no verified official hydrometeorological events were available for "
      "the study area, so warning skill could not yet be quantified. Point-in-time recovery was not tested because WAL "
      "archiving was not enabled, and the benchmark used synthetic data, default configurations and an HDD on one desktop machine; tuned configurations could change the ratios but not the missing features of MySQL 8.0."),

("H1", "Conclusions"),
("P", "Orbit-U: The Monitor shows that a relational spatial database can serve as the persistent, traceable layer "
      "behind multi-mission EO monitoring. Sentinel-1, MODIS and GPM IMERG are harmonised into one sub-district time "
      "series by overlap-weighted zonal aggregation with an explicit valid fraction; variables are rows, so the schema "
      "is stable; every value is linked by checksums and lineage edges to its raw scene; revisions follow a stated "
      "precedence through idempotent upserts; and access control and auditing are enforced in PostgreSQL/PostGIS, "
      "which was selected over MySQL 8.0 with a weighted score of 4.90 against 3.05. The design passed automated, "
      "security and recovery tests and has been operating with real data since 2024. Future work includes adaptive "
      "water thresholds, exact geodesic weights, evaluation of warning skill as verified events accumulate, mobile "
      "notification, and continuous WAL archiving."),
]

AVAILABILITY = [
    ("Project name", "Orbit-U: The Monitor"),
    ("Project home page", "https://github.com/not-notyou-you/orbit_u_monitor"),
    ("Running instance", "https://orbit-u.hakimhakim.workers.dev/"),
    ("Operating system(s)", "Platform independent (developed on Windows 10, deployed on Linux)"),
    ("Programming language", "Python 3.10, SQL (PL/pgSQL), JavaScript"),
    ("Other requirements", "PostgreSQL 18 with PostGIS 3.6 and pgcrypto; Python packages listed in requirements.txt "
                           "(FastAPI, SQLAlchemy, GeoAlchemy2, rasterio, shapely, pyproj, h5py, pyhdf, APScheduler); "
                           "Copernicus Data Space Ecosystem and NASA Earthdata accounts for data download"),
    ("Hardware requirements", "[to be completed: minimum server specification used in deployment]"),
    ("License", "[to be completed: the repository does not yet contain a licence file; an open licence for "
                "non-commercial use is required for software articles]"),
]

ABBREV = [
    ("AOI", "Area of interest"), ("API", "Application programming interface"),
    ("COD-AB", "Common Operational Datasets – Administrative Boundaries"), ("COG", "Cloud-Optimised GeoTIFF"),
    ("DBMS", "Database management system"), ("EO", "Earth observation"), ("ETL", "Extract–transform–load"),
    ("GMLS", "Gugus Mitigasi Lebak Selatan"),
    ("GPM IMERG", "Global Precipitation Measurement Integrated Multi-satellitE Retrievals for GPM"),
    ("MODIS", "Moderate Resolution Imaging Spectroradiometer"), ("NDVI", "Normalized Difference Vegetation Index"),
    ("NDWI", "Normalized Difference Water Index"), ("SAR", "Synthetic aperture radar"), ("WAL", "Write-ahead log"),
]

G = "../artikel_gaee/"
FIGS = {
    "area": (G + "fig1_study_area.png", "Study area: ten sub-districts of South Lebak, Banten, Indonesia",
             "Own elaboration based on COD-AB boundaries [@codab]",
             "Map of ten sub-districts in the southern part of Lebak Regency, Indonesia, outlined and labelled; total "
             "area 1575.8 km2."),
    "pipeline": ("fig_pipeline.png", "Processing tiers per mission and the path of values to the database",
                 "Own elaboration",
                 "Three columns for Sentinel-1, MODIS and GPM IMERG, each going from RAW through ALIGNED and a "
                 "mission-specific tier (DESPECKLED, INDICES, ACCUMULATED) to COG; COGs feed a fused HDF5 product and "
                 "zonal aggregation into region_observations, which feeds alert_events and band_forecasts."),
    "erd": (G + "fig3_erd_core.png", "Core relations for observations, lineage, warnings and events (crow's foot "
            "notation)", "Own elaboration",
            "Entity-relationship diagram: region_observations references administrative_regions, spectral_bands and "
            "data_products; data_lineage links pairs of data_products; alert rules and events reference bands, "
            "regions and disaster types."),
    "lineage": ("fig_lineage.png", "Provenance of a Sentinel-1 value from scene to sub-district observation",
                "Own elaboration",
                "A satellite scene produces a RAW product with SHA-256 checksum; lineage edges CALIBRATE, "
                "SPECKLE_FILTER and COG link it to ALIGNED, DESPECKLED and COG products; each product is created by a "
                "processing job; the COG is aggregated into region_observations through source_product_id."),
    "arch": (G + "fig2_architecture.png", "Deployment architecture", "Own elaboration",
             "Block diagram: official data providers feed a Python ETL layer with scheduler; ETL writes to "
             "PostgreSQL/PostGIS and the file system; a FastAPI REST API serves a web client for five roles."),
    "bench": (G + "fig4_benchmark.png", "Median execution time of core queries (logarithmic scale)", "Own elaboration",
              "Grouped bar chart comparing PostgreSQL and MySQL for Q1 to Q5; PostgreSQL lower for Q1–Q4, MySQL lower "
              "for Q5."),
}

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "artikel_gaee"))
import content as _G

TABLES = {
    "data": _G.TABLES["data"],
    "fail": ("Failure handling of the pipeline", "Own elaboration", [3400, 6238],
             ["Situation", "Behaviour"],
             [["GPM granule not yet published in any run", "Date marked WAITING_UPSTREAM and retried at every schedule "
               "for up to 3 days, then FAILED"],
              ["Daily job missed (process down at run time)", "Missed dates up to 30 days are detected from the job "
               "table and processed at start-up and in the next daily run; older gaps are filled by backfill"],
              ["MODIS unavailable", "Non-fatal; the day completes with GPM values"],
              ["Stalled download", "Attempt cancelled when the mean rate stays below a threshold within a 90 s window; "
               "retry with HTTP Range resume"],
              ["Pipeline killed mid-run", "Completed dates are skipped, the current date is repeated; all writes are "
               "upserts or ON CONFLICT"],
              ["Same job started twice", "Advisory lock not obtained; run recorded as SKIPPED_LOCKED"],
              ["Sentinel-1 scene only grazes the area", "Marked INCOMPLETE and not retried"]]),
    "bench": _G.TABLES["bench"],
    "score": _G.TABLES["score"],
    "eval": _G.TABLES["eval"],
}

DECLARATIONS = [
    ("Funding", "No funding was received for conducting this study."),
    ("Competing interests", "The authors have no competing interests to declare that are relevant to the content of "
                            "this article."),
    ("Author contributions", "Conceptualization: Muhammad Faiq Hakim Ulinnuha, [Supervisor name]; Methodology, "
     "Software, Validation, Formal analysis and investigation, Data curation, Visualization: Muhammad Faiq Hakim "
     "Ulinnuha; Writing – original draft preparation: Muhammad Faiq Hakim Ulinnuha; Writing – review and editing: "
     "[Supervisor name]; Supervision: [Supervisor name]."),
    ("Ethics approval and consent to participate", "[To be confirmed by the authors: statement on informed consent of "
     "the GMLS respondents and the user-trial participants, and whether institutional ethics approval was required.]"),
    ("Data availability", _G.CLOSING[3][1]),
    ("Code availability", "The source code is available at https://github.com/not-notyou-you/orbit_u_monitor."),
    ("Use of generative AI", "During the preparation of this manuscript, the authors used Claude (Anthropic) to "
     "translate and condense text from the first author's undergraduate thesis into English, to draft diagrams from "
     "the authors' design and to format the references. The authors reviewed and edited all content and take full "
     "responsibility for the publication."),
]

SOFTWARE_FILES = ("The complete software (ETL pipeline, REST API, web client, DDL scripts, automated tests and data "
                  "dictionary) is provided in the public repository https://github.com/not-notyou-you/orbit_u_monitor; "
                  "an archived snapshot with a persistent identifier will be supplied on acceptance.")

MANUAL = {
    "codab": ("OCHA", "n.d.", "OCHA Field Information Services Section (n.d.) Indonesia – Subnational administrative "
              "boundaries (COD-AB). https://data.humdata.org/dataset/cod-ab-idn. Accessed 24 October 2026"),
}
