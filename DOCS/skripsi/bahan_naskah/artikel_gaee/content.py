# Isi artikel GaEE. Markup: *miring*, [@kunci] sitasi, {F:x} gambar, {T:x} tabel, {E:x} persamaan, ~sub~, ^sup^.
TITLE = ("A Traceable Spatial Database Integrating Sentinel-1, MODIS and GPM IMERG at Sub-district Level "
         "for Community-based Hydrometeorological Disaster Mitigation in South Lebak, Indonesia")

AUTHORS = [("Muhammad Faiq Hakim Ulinnuha", "Universitas Multimedia Nusantara, Faculty of Engineering and Informatics, "
            "Department of Information Systems, Tangerang, Indonesia, ORCID: [to be completed], "
            "e-mail: [to be completed]"),
           ("[Supervisor name]", "Universitas Multimedia Nusantara, Faculty of Engineering and Informatics, "
            "Department of Information Systems, Tangerang, Indonesia, ORCID: [to be completed], "
            "e-mail: [to be completed]")]

ABSTRACT = (
    "Community disaster organisations can access open satellite data but rarely have a database that turns these "
    "heterogeneous products into stored, comparable and traceable information. Following the Database System "
    "Development Life Cycle, this study designs and implements such a database for Gugus Mitigasi Lebak Selatan, a "
    "community mitigation group in Banten, Indonesia. Sentinel-1, MODIS and GPM IMERG observations are reduced by "
    "area-weighted zonal aggregation to one time series per sub-district, every value is linked to its source file "
    "through SHA-256 checksums and a lineage graph, and role-based access control and auditing are enforced inside the "
    "database. PostgreSQL with PostGIS was selected over MySQL 8.0 with a weighted score of 4.90 against 2.90. The "
    "schema of 43 tables and 22 views passed 1183 of 1185 automated tests (2 skipped), answered all core queries below "
    "2 ms and was restored exactly from backup. GMLS approved the design with revisions, and 13 users completed 62 of "
    "67 task attempts.")
KEYWORDS = "spatial database, PostGIS, satellite remote sensing, data lineage, disaster mitigation"

BODY = [
("H1", "Introduction"),
("P", "Disaster management increasingly depends on information systems that collect, integrate and disseminate data "
      "before, during and after hazardous events [@khan]. Recent platforms for large regions show that the value of such "
      "systems lies less in a single data source than in the integration of heterogeneous data into one consistent "
      "structure that different actors can use [@wang]. In Indonesia, where floods and landslides are triggered mainly by "
      "intense rainfall, hydrological studies at island scale and the evaluation of satellite precipitation have "
      "demonstrated that satellite products can fill gaps left by sparse rain gauge networks [@hidayah, @ansori]."),
("P", "Access to satellite data has also become considerably more open. The Copernicus Data Space Ecosystem provides "
      "Sentinel data through application programming interfaces and cloud processing [@kovacs]. Sentinel-1 synthetic "
      "aperture radar (SAR) observes the surface regardless of cloud cover and has been shown to be effective for flood "
      "detection [@tarpanelli]. MODIS offers a daily archive of more than two decades with continuity into VIIRS "
      "[@roman], and GPM IMERG supplies global precipitation estimates whose long-term behaviour has been evaluated over "
      "land [@zhu]. The three missions are complementary: radar sees water through clouds, optical sensors describe "
      "vegetation and water indices on cloud-free days, and IMERG describes the rainfall that drives both."),
("P", "Open availability does not, however, mean that the data are usable by a local organisation. The products differ "
      "in format (GeoTIFF, HDF5, NetCDF), spatial resolution (about 10 m to 0.1°) and temporal frequency (daily to "
      "6–12 days). Without a database that stores them in a structured and comparable form, every analysis has to be "
      "repeated from raw files, and nobody can later verify from which file and processing step a reported value came. "
      "Studies that combine several sensors typically focus on the analysis of a single event, such as a drought or a "
      "flood [@liu, @castro], while open pipelines for Sentinel-1 preprocessing or analysis-ready data concentrate on "
      "image processing rather than on persistent storage [@weiss, @upadhyay]."),
("P", "This article reports the design and implementation of a hydrometeorological monitoring database for Gugus "
      "Mitigasi Lebak Selatan (GMLS), a community mitigation group in South Lebak, Banten. The contribution is a "
      "database design, tested on real data and real users, that (1) integrates Sentinel-1, MODIS and GPM IMERG into one "
      "time series per sub-district, (2) makes every value traceable to its source file and processing step, (3) "
      "supports early warning and the recording of disaster events, and (4) enforces role-based access control and "
      "auditing at the database level rather than only in the application. The system, named Orbit-U: The Monitor, is "
      "publicly accessible, and its source code is available for reproduction."),

("H1", "Analysis (state) of the Problems"),
("P", "Integrated geospatial databases have been recommended to reduce duplication and to support local decision "
      "making, for example in land-use governance [@dev]. In the data engineering literature, lineage is treated as "
      "structured metadata that should be recorded by the pipeline itself rather than reconstructed afterwards "
      "[@gopaluni]. Role-based access control has been implemented in PostgreSQL through GRANT and REVOKE statements for "
      "business information systems [@purwitasari], and PostGIS has been shown to outperform general relational "
      "approaches for spatial storage and proximity queries [@kaptosv, @papasani]. These studies address integration, "
      "lineage, security and spatial performance separately; none of them combines the three satellite missions into "
      "one traceable time series with access control enforced in the database for a community organisation."),
("P", "Research involving GMLS has so far concerned earthquakes and tsunamis. Earthquake patterns in South Lebak for "
      "2021–2025 were analysed and visualised from the official GMLS dataset [@tilung], and a pre-disaster tsunami "
      "dashboard was designed for the village of Panggarangan [@wong]. Hydrometeorological hazards, which are frequent in "
      "the area, have not been addressed."),
("P", "The current situation at GMLS was analysed through observation, an interview with the chairman of GMLS "
      "accompanied by a lecturer involved in earlier community projects, and the examination of GMLS documents and data. "
      "The data held by GMLS consist of a demographic assessment of 356 households in the tsunami-prone zone of "
      "Panggarangan collected by volunteers in January–June 2021, tables of families, residents, evacuation sites and "
      "25 preparedness activities in 2023, official administrative boundaries and hazard zone maps, and a global "
      "earthquake catalogue. A village information application developed with university partners (MySQL, 11 tables) "
      "manages the hierarchy of administrative areas, houses with their tsunami-zone status, families and residents. "
      "Weather information reaches GMLS from the national meteorological agency through radar images that show areas "
      "with potential rain and flooding but are not specific to the locations of residents."),
("P", "Four problems were therefore formulated: (P1) how to integrate the three satellite sources, with their different "
      "formats, resolutions and frequencies, into one structured unit of analysis; (P2) how to make every stored value "
      "traceable to its source and processing together with its quality; (P3) how to present the stored data as "
      "information that supports monitoring and the recording of disaster events; and (P4) how to secure the data through "
      "role-based access control and an audit trail. Demographic and evacuation data remain in the existing village "
      "application and are outside the scope of the new database."),

("H1", "Material and Methods"),
("H2", "Study area and data"),
("P", "The study area comprises ten sub-districts (*kecamatan*) of Lebak Regency: Banjarsari, Bayah, Cibeber, Cigemblong, "
      "Cihara, Cijaku, Cilograng, Malingping, Panggarangan and Wanasalam ({F:area}). The boundaries were taken from the "
      "Indonesian subnational administrative boundaries dataset (COD-AB) [@codab]; the total area computed from the "
      "polygons is 1575.8 km^2^, ranging from about 94.9 km^2^ (Cilograng) to 400.8 km^2^ (Cibeber). The selection of the "
      "ten sub-districts was confirmed by GMLS."),
("FIG", "area"),
("P", "The satellite products used are summarised in {T:data}. Sentinel-1 SAR is sensitive to open water because smooth "
      "water surfaces return little backscatter [@tran, @alonso], and global flood mapping with a decade of radar data "
      "has confirmed its value at large scale [@misra]. MODIS daily observations provide surface water dynamics at "
      "250 m [@klein], but optical pixels are frequently invalid under cloud cover [@tang]. Because the sources cannot be "
      "compared pixel by pixel, the sub-district was chosen as the common unit of analysis."),
("TAB", "data"),
("H2", "Development method"),
("P", "The Database System Development Life Cycle (DBSDLC) was followed: database planning (mission statement and eight "
      "mission objectives), system definition (system boundary and user views for five roles), requirements collection "
      "and analysis, conceptual, logical and physical database design, DBMS selection, application design with Unified "
      "Modeling Language use case, activity and sequence diagrams [@alyami], prototyping, implementation, data loading "
      "and testing. Conceptual design identified entities, relationships, attributes, domains and keys, checked "
      "redundancy and validated the model against user transactions. Logical design identified strong and weak entities "
      "and multiplicities and normalised the relations to third normal form, with selected relations checked against "
      "Boyce–Codd and fourth normal form [@skavantzos, @zhang]. Integrity rules were placed in the database as "
      "constraints and triggers, following the observation that constraints inferred from application code alone leave "
      "data unprotected [@huang, @kanwal]."),
("P", "Requirements were collected through observation, the interview, document examination, a literature study and a "
      "requirements review questionnaire. The questionnaire, written in plain language for non-technical users, asked "
      "GMLS to assess six requirements (R1–R6), the recorded information, the system limits and the role assignment, and "
      "to approve or reject the design. A second questionnaire was used for a user trial with six task scenarios."),
("H2", "Zonal aggregation"),
("P", "Each raster is converted to a Cloud-Optimised GeoTIFF per band and reduced to one value per sub-district. Because "
      "an IMERG cell of 0.1° covers only one to six cells per sub-district, taking the nearest cell would bias small "
      "sub-districts. The value of variable *b* for sub-district *r* on date *t* is therefore computed as the mean of "
      "valid cells weighted by the area of intersection between each cell and the sub-district polygon:"),
("EQ", "zonal"),
("P", "where *A*~r,c~ is the planar area of the intersection of cell *c* with polygon *r* multiplied by the cosine of the cell latitude, an approximation of its area on the sphere, *x*~c~ is the cell value and "
      "*C*~r~ is the set of valid cells intersecting *r*. The fraction of the polygon covered by valid cells is stored "
      "with each value, so that a value computed from a small cloud-free part of a sub-district can be recognised."),
("H2", "DBMS selection and evaluation"),
("P", "DBMS selection followed four steps: establishing the terms of reference, short-listing, evaluating the products "
      "and recommending one. PostgreSQL 18.6 with PostGIS 3.6.2 and MySQL 8.0.40 Community were short-listed; MongoDB 7 "
      "was assessed only by features because it does not support foreign keys. Both relational candidates received an "
      "equivalent schema with the same types, keys, constraints and indexes, including spatial indexes, and the same "
      "deterministic synthetic data (28 sub-districts and 76 720 observations) with default configurations. Five core "
      "queries (Q1–Q5) were each executed 30 times after 5 warm-up runs in three separate runs, and medians are reported. "
      "Security features (F1–F3), scalability, concurrency and write throughput were tested in addition. The products "
      "were scored from 1 to 5 on seven weighted criteria, and the total score was calculated as:"),
("EQ", "score"),
("P", "where *w*~i~ is the weight and *s*~i~ the score of criterion *i*. The six minimum evaluations of the design were "
      "requirements review, integrity, functional, security, query and backup/recovery testing. Integrity and functional "
      "behaviour were tested with automated black-box scenarios through the REST API [@balsam], security with a GRANT "
      "matrix and API tests for every role, and recovery with dump-and-restore and process-kill scenarios. The authors' "
      "use of an AI assistant in preparing this manuscript is described in the closing statement."),

("H1", "Results and Discussion"),
("H2", "Architecture and implementation"),
("P", "The implemented architecture has four layers ({F:arch}). A Python extract–transform–load (ETL) layer, scheduled "
      "with an advisory lock so that only one instance runs a job, downloads products from the official providers, "
      "processes them through ordered tiers, writes rasters to the file system and values to the database under a "
      "dedicated ETL role. A FastAPI REST API connects under a separate application role and switches to the role of the "
      "requesting user for every transaction. A web client presents current conditions per sub-district, satellite "
      "images, warnings and disaster events. The implemented schema contains 43 tables, 22 views, 528 columns, 226 "
      "constraints, 162 indexes, 29 triggers and 3 row-level security policies. It holds 12 master tables and 17 "
      "transaction tables with at least 100 records each, including 72 850 sub-district observations, 15 850 data "
      "products, 8142 lineage edges and 7958 processing jobs."),
("FIG", "arch"),
("H2", "Integration and traceability (P1, P2)"),
("P", "The core of the design is the relation region_observations ({F:erd}), with the alternate key (region_id, band_id, "
      "obs_date). Eleven variables from three missions are stored as rows rather than columns: VV and VH backscatter, "
      "water percentage and water change from Sentinel-1; MODIS flood fraction, NDVI and NDWI; and 24-hour, 72-hour, "
      "7-day and 30-day rainfall from IMERG. Adding a variable therefore requires a new row in spectral_bands, not a "
      "change of schema. Each band defines physical limits, and a trigger rejects values outside them, for example "
      "negative rainfall caused by a processing error."),
("FIG", "erd"),
("P", "The relation was obtained by normalisation of an unnormalised observation record that repeated the name of the "
      "sub-district, its regency, the band, its unit and the satellite in every row. Moving the attributes of the area "
      "and of the band to their own relations removed the partial dependencies (2NF); making the regency a recursive "
      "reference to the area relation through parent_region_id and moving the satellite attributes to a source relation "
      "removed the transitive dependencies (3NF). Weak and dependent entities, such as warnings that cannot exist "
      "without their rule and sub-district, are identified by composite unique keys. In total the schema defines 43 "
      "primary keys, 80 foreign keys, 36 unique and 67 check constraints."),
("P", "Physical design followed the observed access patterns. GiST indexes serve spatial predicates on boundaries, "
      "scene footprints and event locations; descending B-tree indexes serve the most recent values of a time series; a "
      "partial index covers only unacknowledged warnings; expression indexes support case-insensitive searches; and two "
      "B-tree indexes on the lineage edges allow traversal in both directions. Raster files are kept in the file system "
      "in ordered tiers from raw data to Cloud-Optimised GeoTIFF, while the database stores only their metadata, "
      "location and checksum. User views are implemented as database views whose time window depends on the active "
      "database role: visitors see 30 days of satellite images, volunteers 365 days and the other roles the full "
      "archive. Controlled redundancy was introduced only where a value is read repeatedly and its consistency can be "
      "maintained by a trigger or a scheduled job."),
("P", "Because GMLS had no previous hydrometeorological database, no data conversion was required. Loading started from "
      "an empty database: the schema, security objects and reference data were applied in order, the COD-AB boundaries "
      "were loaded and the ten sub-districts of the study area flagged, and GPM, MODIS and Sentinel-1 data were "
      "backfilled. As of 24 October 2026, the database held 72 850 observations from 1 January 2024 to 22 October 2026 "
      "and 210 warnings generated from them. Large-scale flood hazard assessments have shown that such multi-year "
      "satellite records are needed before the behaviour of an area can be interpreted [@halder]."),
("P", "Traceability is provided by three relations. data_products records every file with its SHA-256 checksum, "
      "data_lineage records each transformation as an edge between a parent and a child product with input and output "
      "checksums, and processing_jobs stores the parameters of every stage. Any value can be followed through "
      "source_product_id and a recursive query to the raw file it came from, and quality metrics are compared with "
      "configurable thresholds. This corresponds to treating lineage as structured metadata recorded by the pipeline "
      "[@gopaluni], and it answers the question that GMLS raised in the interview: where a number shown to residents "
      "comes from."),
("H2", "DBMS selection"),
("P", "Median execution times of the core queries are given in {T:bench} and {F:bench}. PostgreSQL was faster in Q1–Q4, "
      "most clearly in the spatial intersection with geodesic area (Q3, 17 times) and the evaluation of warnings against "
      "events (Q4, 9 times). The equivalent Q3 even failed in MySQL with error 3516, because the geographic intersection "
      "produced a GeometryCollection, and had to be rewritten specifically for MySQL. MySQL was faster in the recursive "
      "lineage query Q5, although both completed below 1 ms. Row counts of every query were identical in both systems, "
      "and the intersection areas of Q3 agreed per sub-district within 0.1%. In the scalability test, a summary query "
      "over 2.3 million rows took 654 ms in PostgreSQL and 5577 ms in MySQL; PostgreSQL was 13–26% faster under concurrent "
      "reads and 8.2 times faster for inserts."),
("TAB", "bench"),
("FIG", "bench"),
("P", "The decisive differences were functional rather than temporal ({T:score}). PostgreSQL supports SET LOCAL ROLE, "
      "which narrows privileges for one transaction and reverts automatically, row-level security policies and a single "
      "audit trigger function that stores old and new rows as JSON. MySQL 8.0 switches roles only per session while the "
      "account privileges remain effective, has no row-level security and requires a trigger per table for auditing. "
      "MySQL scored higher only on cost, ecosystem and familiarity, because the existing village application uses MySQL. "
      "The data of PostgreSQL were stored on an SSD and those of MySQL on an HDD. To test whether this affected the "
      "recommendation, MySQL was given the maximum score on the two storage-sensitive criteria (ETL writes, and "
      "analytics and scale); its total rose to 3.55, still below 4.90, because the largest differences come from "
      "security and spatial queries, which do not depend on the storage medium. This agrees with earlier comparisons "
      "that favour PostGIS for spatial workloads [@kaptosv, @papasani]."),
("TAB", "score"),
("H2", "Information, access control and audit (P3, P4)"),
("P", "Information is presented through 22 views, the REST API and the web client: current conditions for the "
      "sub-district in which the user is located, rainfall warnings based on the 50, 100 and 150 mm thresholds of the "
      "national meteorological agency sent by e-mail to subscribed users, an archive of disaster events with their "
      "source and verification status, and periodic reports. A warning is recorded once per rule, sub-district and day "
      "(a unique constraint), and a check constraint ensures that the person and the time of acknowledgement are always "
      "recorded together. Five application roles (visitor, volunteer, analyst, data engineer and administrator) are "
      "mapped to five PostgreSQL roles. The API role is NOINHERIT and has no privileges until it switches role, and no "
      "application role is a superuser or may bypass row-level security. Views restrict the time window visible to each "
      "role, and the audit trigger writes every change of important tables to audit_log. In the security tests, queries "
      "under an unauthorised role were rejected by the database even when the checks in the API were disabled, which "
      "extends the GRANT-based approach of [@purwitasari] with per-transaction role switching and row-level security."),
("H2", "Evaluation"),
("P", "The results of the six minimum evaluations are summarised in {T:eval}. The automated test run comprised 1185 test "
      "cases, of which 1183 passed, none failed and 2 were skipped because they require the full boundary shapefile; an "
      "earlier run had revealed two failures, which were corrected before the final run. All five core queries finished "
      "below 2 ms, and the system reached 8523 queries per second with eight clients. Backup and recovery were tested on "
      "a copy of the production database with 44 tables and 146 541 rows: after restore, the MD5 hashes of all rows, "
      "sequences, constraints and 163 indexes were identical, which corresponds to the role of log and dump structures "
      "in reliable recovery [@ahmad]. A backfill killed during processing resumed only the remaining dates without "
      "duplicates."),
("TAB", "eval"),
("P", "In the requirements review, all three GMLS respondents (the chairman and two volunteers) assessed R1 and R3–R6 as "
      "appropriate. For R2, notification of abnormal conditions, one respondent agreed, one asked for a change and one "
      "disagreed, because residents use mobile phones more than e-mail. GMLS approved the design, two respondents with "
      "revisions. Notification by SMS or messaging applications was not implemented because these services charge per "
      "message or subscription, which exceeded the budget of the study; the subscription and delivery tables do not "
      "depend on the channel, so the database can support such a channel without change. In the user trial, 13 "
      "respondents (three participants of a university community project working with GMLS and ten students outside "
      "engineering representing lay users) made 67 attempts at six scenarios, of which 62 (92.5%) succeeded with a mean "
      "ease rating of 4.36 out of 5. The remaining attempts concerned saving the e-mail subscription, which requires "
      "signing in first, and finding the event list; the application log showed no errors, and other respondents "
      "completed the same scenarios. Nine respondents judged the application ready for use and four ready with "
      "improvements, mainly larger fonts, plainer language and an in-application guide."),
("H2", "Limitations"),
("P", "The accuracy of warnings can be evaluated through a dedicated view that classifies hits, misses and false "
      "alarms, but at the time of writing no verified official hydrometeorological events were available for the study "
      "area, so this evaluation remains empty. IMERG is known to underestimate extreme daily rainfall [@ansori], and the "
      "warnings inherit this limitation. Point-in-time recovery was not tested because WAL archiving was not enabled, "
      "and raster files are not backed up because they can be regenerated from the providers while the values per "
      "sub-district remain in the database. The benchmark used synthetic data and default configurations, and its "
      "storage asymmetry was addressed only through the sensitivity check described above."),

("H1", "Conclusion"),
("P", "A spatial relational database was designed and implemented with the DBSDLC for a community disaster mitigation "
      "group. Sentinel-1, MODIS and GPM IMERG observations were integrated into one time series per sub-district by "
      "area-weighted zonal aggregation, with eleven variables stored as rows so that new variables do not change the "
      "schema. Every value is traceable to its source file through checksums and a lineage graph, and role-based access "
      "control and auditing are enforced in the database itself. PostgreSQL with PostGIS was selected over MySQL 8.0 "
      "with a weighted score of 4.90 against 2.90, a result that remained unchanged when storage-related criteria were "
      "given their best case for MySQL. All six minimum evaluations were met, GMLS approved the design with revisions, "
      "and lay users completed 92.5% of task attempts."),
("P", "The design shows that a community organisation without its own hydrometeorological data can obtain a traceable "
      "data source from open satellite missions when the database, rather than the application, carries integration, "
      "lineage and security. Future work should add notification through mobile messaging when funding is available, "
      "evaluate warning accuracy as verified events accumulate, allow residents to report events that remain unverified "
      "until reviewed by an analyst, and enable continuous WAL archiving for point-in-time recovery."),
]

FIGS = {
    "area": ("fig1_study_area.png", "Study area: ten sub-districts of South Lebak, Banten, Indonesia",
             "Own elaboration based on COD-AB boundaries [@codab]",
             "Map of ten sub-districts in the southern part of Lebak Regency, Indonesia, outlined and labelled with their "
             "names, with longitude 105.85–106.55 degrees east and latitude 6.4–7.0 degrees south; total area 1575.8 km2."),
    "arch": ("fig2_architecture.png", "System architecture of Orbit-U: The Monitor", "Own elaboration",
             "Block diagram of four layers: three official satellite data providers feed a Python ETL layer with a "
             "scheduler, daily hydrometeorological job, Sentinel-1 cycle, reports and e-mail alerts; the ETL writes to a "
             "PostgreSQL/PostGIS database and a file system; a FastAPI REST API reads both and serves a web client; users "
             "in five roles receive e-mail through an SMTP server."),
    "erd": ("fig3_erd_core.png", "Core relations for observations, lineage, warnings and events (crow's foot notation)",
            "Own elaboration",
            "Entity-relationship diagram in crow's foot notation. region_observations references administrative_regions, "
            "spectral_bands and data_products; data_lineage links pairs of data_products; alert_rules reference "
            "spectral_bands and disaster_types; alert_events reference alert_rules, administrative_regions and optionally "
            "region_observations; disaster_events reference disaster_types and administrative_regions."),
    "bench": ("fig4_benchmark.png", "Median execution time of core queries (logarithmic scale)", "Own elaboration",
              "Grouped bar chart on a logarithmic scale comparing PostgreSQL and MySQL median times for queries Q1 to Q5. "
              "PostgreSQL is lower for Q1 to Q4, most strongly for Q3 (1.34 versus 22.57 ms) and Q4 (1.76 versus 16.64 ms); "
              "MySQL is lower for Q5 (0.43 versus 0.82 ms)."),
}

TABLES = {
    "data": ("Satellite data sources", "Own elaboration based on [@tarpanelli, @roman, @zhu]",
             [1900, 2600, 1300, 1700, 1788],
             ["Mission", "Products", "Resolution", "Frequency", "Provider"],
             [["Sentinel-1 (S1A, S1C, S1D)", "GRD IW, VV and VH polarisation", "≈10 m", "6–12 days per orbit", "ESA, CDSE"],
              ["MODIS Terra and Aqua", "MCDWD flood; MOD09A1, MOD09GA (NDVI, NDWI)", "250–500 m", "Daily; 8-day composite",
               "NASA LANCE, LAADS DAAC"],
              ["GPM IMERG", "Daily Final, Late and Early runs", "0.1°", "Daily", "NASA GES DISC"]]),
    "bench": ("Median execution time of core queries [ms]", "Own elaboration",
              [700, 4388, 1500, 1400, 1300],
              ["Query", "Content", "PostgreSQL", "MySQL", "MySQL/PG"],
              [["Q1", "Rainfall pivot per sub-district, one date", "0.45", "1.14", "2.5×"],
               ["Q2", "30-day trend, one sub-district and band", "0.29", "0.67", "2.3×"],
               ["Q3", "Polygon intersection with geodesic area", "1.34", "22.57", "17×"],
               ["Q4", "Warning evaluation: hits, misses, false alarms", "1.76", "16.64", "9×"],
               ["Q5", "Six-level lineage (WITH RECURSIVE)", "0.82", "0.43", "0.5×"]]),
    "score": ("Weighted scores of the DBMS selection", "Own elaboration",
              [3600, 1000, 1400, 1100, 2188],
              ["Criterion", "Weight", "PostgreSQL", "MySQL", "Basis"],
              [["Role-based security and audit", "25%", "5", "2", "F1–F3"],
               ["Spatial queries", "20%", "5", "2", "Q3 17×, error 3516"],
               ["Analytics and scale", "15%", "5", "2", "Q4 9×, 2.3 M rows 8.5×"],
               ["ETL writes", "10%", "5", "3", "Insert 8×, upsert 2×"],
               ["Concurrent reads", "10%", "5", "4", "13–26%"],
               ["Relational and recursive integrity", "10%", "5", "5", "Both support FK"],
               ["Cost, ecosystem, familiarity", "10%", "4", "5", "MySQL used locally"],
               ["Total", "100%", "4.90", "2.90", ""]]),
    "eval": ("Results of the six minimum evaluations", "Own elaboration",
             [2300, 4188, 2800],
             ["Evaluation", "Evidence", "Result"],
             [["Requirements review", "Questionnaire, three GMLS respondents", "Approved (two with revisions)"],
              ["Integrity", "Schema, constraint, comment and audit tests", "Passed"],
              ["Functional", "Black-box scenarios through the REST API", "Passed"],
              ["Security", "165 API cases, GRANT matrix of 390 cells", "Passed"],
              ["Query", "Benchmark Q1–Q6, concurrency, writes, F1–F3", "All core queries < 2 ms"],
              ["Backup/recovery", "Dump and restore, process kill and resume", "Passed; identical MD5"]]),
}

CLOSING = [
    ("Funding", "This research received no specific grant from any funding agency in the public, commercial, or "
                "not-for-profit sectors."),
    ("CRediT Author Contribution", "M. F. H. U.: conceptualization, methodology, software, validation, formal analysis, "
     "investigation, data curation, writing – original draft preparation, visualization. [Supervisor initials]: "
     "conceptualization, validation, supervision, writing – review and editing."),
    ("Declaration of Competing Interests", "The authors declare that they have no known competing financial interests or "
     "personal relationships that could have appeared to influence the work reported in this paper."),
    ("Data Availability", "The source code, DDL scripts, queries, configuration, data dictionary and instructions for "
     "reproduction are available at https://github.com/not-notyou-you/orbit_u_monitor, and the implemented system is "
     "accessible at https://orbit-u.hakimhakim.workers.dev/. Satellite data are publicly available from the Copernicus "
     "Data Space Ecosystem and NASA Earthdata. Demographic data of GMLS contain personal information of residents and "
     "are not shared; access may be requested from GMLS."),
    ("Use of Generative AI and AI-Assisted Technologies", "During the preparation of this manuscript, the authors used "
     "Claude (Anthropic) to translate and condense text from the first author's undergraduate thesis into English, to "
     "draft figures from the authors' data and to format the references. The authors reviewed and edited all content "
     "and take full responsibility for the publication."),
    ("Acknowledgements", "The authors thank the chairman and volunteers of Gugus Mitigasi Lebak Selatan for the interview "
     "and the requirements review, and all participants of the user trial."),
]

# Referensi: kunci -> entri manual (non-DOI) atau dari refs.json
MANUAL = {
    "codab": "OCHA Field Information Services Section: Indonesia – Subnational administrative boundaries (COD-AB), "
             "[on-line:] https://data.humdata.org/dataset/cod-ab-idn [access: 24.10.2026].",
}
