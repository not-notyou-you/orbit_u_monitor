"""Isi BAB IV. Dipanggil dari build_skripsi.py.

Blok berupa tuple; nomor Gambar/Tabel dihitung otomatis dan dirujuk di teks dengan {G:kunci} / {T:kunci}.
Sumber angka: DOCS/skripsi/bahan_naskah/assets/data.js (snapshot database kampus 24 Okt 2026 18.40),
DOCS/hasil_uji/, benchmark/results/, dan kode (api/, etl/, database/).
"""

P = lambda t: ("p", t)
L = lambda *t: ("list", list(t))
H2 = lambda t: ("h", 2, t)
H3 = lambda t: ("h", 3, t)
H4 = lambda t: ("h", 4, t)
FIG = lambda key, file, title, width=15.0: ("fig", key, file, title, width)
TAB = lambda key, title, widths, header, rows: ("tab", key, title, widths, header, rows)
EQ = lambda t: ("eq", t)


def blocks():
    b = []
    b += [P("Bab ini menyajikan hasil setiap tahap DBSDLC sesuai alur pada Gambar 3.4 dan kegiatan pada Tabel 3.2. "
            "Penyajiannya mengikuti subbab template program studi, sehingga beberapa tahap ditempatkan sedikit berbeda dari "
            "urutan DBSDLC: pemodelan sistem disajikan pada 4.2.1 sebelum perancangan basis data, dan pemilihan DBMS disajikan "
            "sebelum desain fisik karena desain fisik menerjemahkan model logikal ke DBMS target. Pemetaannya ditunjukkan pada "
            "{T:peta}.")]
    b += [TAB("peta", "Pemetaan Tahap DBSDLC ke Subbab", [3300, 1500, 3100], ["Tahap DBSDLC", "Subbab", "Hasil Utama"], [
        ["Analisis sistem berjalan dan identifikasi masalah", "4.1.1", "Activity diagram As-Is dan To-Be, 5W1H"],
        ["1. Database Planning", "4.1.2.1", "*Mission statement* dan *mission objectives*"],
        ["2. System Definition", "4.1.2.2", "Batas sistem dan *user views*"],
        ["3. Requirement Collection and Analysis", "4.1.2.3", "Kebutuhan K1–K6"],
        ["6. Pemodelan Sistem", "4.2.1", "*Use case*, *activity*, dan *sequence diagram*"],
        ["4. Database Design: konseptual dan logikal", "4.2.2.1, 4.2.2.2", "ERD, kunci, domain, normalisasi, *constraint*"],
        ["5. DBMS Selection", "4.2.2.3", "Rekomendasi PostgreSQL dengan PostGIS"],
        ["4. Database Design: fisik", "4.2.2.4", "DDL, indeks, VIEW, keamanan, kamus data"],
        ["7. Desain Antarmuka", "4.2.3", "Akses halaman dan wireframe"],
        ["9. Implementation", "4.3.1", "Arsitektur, pipeline, lineage, jadwal"],
        ["10. Data Conversion and Loading", "4.3.2", "Pemuatan awal basis data"],
        ["8. Prototyping", "4.3.3", "Aplikasi web dan iterasinya"],
        ["11. Testing", "4.3.4", "Enam evaluasi minimum"],
    ])]
    # ============================================================== 4.1
    b += [P('Dengan pemetaan tersebut, setiap tahap DBSDLC pada Tabel 3.2 memiliki hasil yang dapat ditunjuk pada subbab tertentu. Tahap Database Design dipisah ke dalam dua bagian karena di antara desain logikal dan desain fisik terdapat tahap pemilihan DBMS yang menentukan dialek SQL, tipe data, dan fitur keamanan yang tersedia.')]
    b += [H2("Analisa Masalah")]
    b += [H3("Analisa Proses Bisnis")]
    b += [P("Analisis proses bisnis disusun dari wawancara dengan Ketua GMLS pada 16 Oktober 2026 dan profil resmi GMLS "
            "(subbab 3.1). Alur sistem yang sedang berjalan digambarkan dengan *activity diagram* ber-*swimlane* pada "
            "{G:asis}.")]
    b += [FIG("asis", "asis.png", "Activity Diagram Sistem Berjalan (As-Is)", 13.0)]
    b += [P("Informasi cuaca diterbitkan BMKG dan disalurkan melalui Are You In Sys. GMLS membaca informasi yang masih "
            "berupa area potensi hujan, lalu meneruskan peringatan tanpa menetapkan status bencana. Bila terjadi kejadian, "
            "masyarakat melapor melalui Are You In Sys, sedangkan GMLS tidak mencatat kejadian sendiri dan merujuk pada data "
            "dampak pemerintah. Kondisi ini diidentifikasi dengan metode 5W1H pada {T:5w1h}.")]
    b += [TAB("5w1h", "Identifikasi Masalah dengan 5W1H", [1000, 3500, 3400], ["Unsur", "Kondisi Sistem Berjalan", "Kebutuhan Sistem Usulan"], [
        ["What", "Informasi cuaca dari BMKG (termasuk radar) diterima melalui Are You In Sys. Tidak ada data hujan per kecamatan yang tersimpan. GMLS tidak mencatat kejadian sendiri dan data dampak bergantung pada data pemerintah yang menurut narasumber tidak rapi",
         "Basis data pemantauan hidrometeorologi per kecamatan dan arsip kejadian bencana dari sumber resmi"],
        ["Who", "BMKG dan BNPB sebagai sumber; GMLS meneruskan peringatan; masyarakat melapor melalui Are You In Sys; belum ada penanggung jawab informasi potensi bencana di GMLS",
         "Pengunjung, Relawan, Analis, Data Engineer, dan Administrator"],
        ["When", "Saat BMKG menerbitkan informasi; tidak ada rekap berkala per kecamatan",
         "Job Hidromet harian pukul 02.00 WIB, siklus Sentinel-1 pukul 01.00, 07.00, 13.00, dan 19.00 WIB, laporan mingguan dan bulanan"],
        ["Where", "Lebak Selatan; radar BMKG hanya menunjukkan area berpotensi hujan dan banjir, belum spesifik ke lokasi warga",
         "Sepuluh kecamatan wilayah kajian; kecamatan lokasi pengguna"],
        ["Why", "Hujan lebat memicu banjir bandang dan longsor. Tanpa informasi spesifik lokasi dan arsip kejadian, peringatan tidak dapat dinilai; situs rujukan sulit dipahami orang awam",
         "Data terpusat, dapat ditelusuri asal-usulnya, dan dapat dibandingkan dengan kejadian; tampilan sederhana"],
        ["How", "GMLS mengikuti informasi pemerintah dan hanya memberikan peringatan",
         "ETL otomatis dari layanan resmi ke PostgreSQL/PostGIS, agregasi per kecamatan, peringatan berbasis ambang hujan, dan akses per peran"],
    ])]
    b += [P("Akar masalah dari tabel tersebut dikelompokkan ke dalam tiga aspek, yaitu data, proses, serta pengguna dan "
            "akses, sebagaimana ditunjukkan pada {G:masalah}.")]
    b += [FIG("masalah", "masalah.png", "Diagram Sebab-Akibat Masalah Pemantauan Hidrometeorologi GMLS", 14.0)]
    b += [P("Diagram tersebut menunjukkan bahwa masalah tidak hanya bersumber dari ketiadaan data, tetapi juga dari "
            "proses yang bergantung pada pembacaan manual dan dari belum adanya pembagian akses. Karena itu, solusi "
            "tidak cukup berupa penyimpanan data, melainkan juga otomatisasi dan kontrol akses. Setiap kelompok masalah "
            "dipetakan ke rumusan masalah dan objek basis data yang menjawabnya pada {T:rm}.")]
    b += [TAB("rm", "Pemetaan Masalah, Rumusan Masalah, dan Solusi", [2600, 700, 2400, 2200], ["Masalah", "RM", "Solusi di Sistem", "Objek Basis Data"], [
        ["Data tiga satelit tidak terintegrasi", "RM1", "Pengambilan otomatis Sentinel-1, MODIS, GPM; nilai harian per kecamatan", "satellite_scenes, nasa_scenes, region_observations"],
        ["Asal-usul dan mutu data tidak dapat ditelusuri", "RM2", "Lineage dengan *checksum* SHA-256 dan metrik mutu per scene", "data_products, data_lineage, quality_metrics"],
        ["Informasi belum spesifik lokasi dan sulit dipahami; kejadian tidak diarsipkan", "RM3", "Pantau Lokasi, peringatan hujan melalui web dan surel, arsip kejadian, laporan PDF, REST API", "VIEW per peran, alert_events, user_notify_regions, disaster_events, generated_reports"],
        ["Belum ada wadah data bersama dengan kontrol akses dan jejak audit", "RM4", "Lima peran aplikasi dipetakan ke lima role PostgreSQL; GRANT, RLS, trigger audit", "roles, users, audit_log, user_activity_logs"],
    ])]
    b += [P("Alur sistem usulan (To-Be) pada {G:tobe} memindahkan pekerjaan pengambilan dan pengolahan data ke *scheduler*, "
            "sehingga relawan dan analis cukup membaca hasilnya dan menindaklanjuti peringatan.")]
    b += [FIG("tobe", "tobe.png", "Activity Diagram Sistem Usulan (To-Be)", 12.0)]

    b += [P('Perbedaan utama sistem usulan terhadap sistem berjalan ada pada tiga hal. Pertama, peringatan dibangkitkan dari angka per kecamatan dan aturan ambang yang tersimpan, bukan dari pembacaan informasi area secara manual. Kedua, setiap tindak lanjut peringatan dan setiap kejadian tercatat di basis data. Ketiga, karena keduanya tercatat, peringatan dapat dibandingkan dengan kejadian melalui v_evaluasi_alert, sesuatu yang tidak dapat dilakukan pada sistem berjalan.')]
    b += [H3("User Requirements")]
    b += [H4("Database Planning")]
    b += [P("*Mission statement* basis data Orbit-U: The Monitor adalah sebagai berikut: basis data menyimpan data pengamatan "
            "tiga satelit (Sentinel-1, MODIS, GPM) dalam bentuk yang terstruktur per kecamatan, lengkap dengan asal-usul dan "
            "mutunya, serta mencatat peringatan hujan dan kejadian bencana, supaya GMLS dapat memantau kondisi hidrometeorologi "
            "wilayahnya, menilai ketepatan peringatan, dan membagikan data dengan hak akses yang jelas. *Mission objectives* "
            "yang diturunkan dari RM1–RM4 ditunjukkan pada {T:mo}.")]
    b += [TAB("mo", "Mission Objectives", [600, 4100, 900, 2300], ["Kode", "Mission Objective", "RM", "Tabel Utama"], [
        ["MO1", "Mencatat setiap scene dan granule yang ditemukan atau diunduh dari tiga penyedia resmi", "RM1", "satellite_scenes, nasa_scenes"],
        ["MO2", "Menyimpan nilai harian per kecamatan per variabel sebagai satu deret waktu", "RM1", "region_observations"],
        ["MO3", "Mencatat setiap berkas keluaran beserta *checksum* dan transformasi asalnya", "RM2", "data_products, data_lineage, processing_jobs"],
        ["MO4", "Mengukur mutu data dan menandai data di bawah ambang", "RM2", "quality_metrics, quality_thresholds, quality_alerts"],
        ["MO5", "Membangkitkan peringatan ketika hujan melewati ambang BMKG serta mencatat siapa yang menindaklanjuti", "RM1, RM3", "alert_rules, alert_events"],
        ["MO6", "Mengarsipkan kejadian bencana dan membandingkannya dengan peringatan", "RM3", "disaster_events, v_evaluasi_alert"],
        ["MO7", "Menyajikan data kepada lima peran sesuai batas aksesnya", "RM3, RM4", "22 VIEW dan matriks GRANT"],
        ["MO8", "Mencatat siapa mengubah apa dan siapa mengunduh apa", "RM4", "audit_log, user_activity_logs"],
    ])]
    b += [P('Setiap rumusan masalah didukung oleh sekurang-kurangnya satu *mission objective*, dan setiap *mission objective* menunjuk tabel utama yang mewujudkannya. Hal ini memungkinkan pemeriksaan per tabel pada tahap desain fisik. MO7 dan MO8 juga menunjukkan bahwa keamanan dan jejak audit sudah direncanakan sejak tahap perencanaan, bukan ditambahkan pada tahap implementasi.')]
    b += [H4("System Definition")]
    b += [P("Batas sistem ditunjukkan pada {G:batas}. Di dalam batas sistem terdapat ETL dan *scheduler*, basis data, REST API, "
            "dan aplikasi web. Penyedia data satelit hanya dibaca. Berkas raster (COG, HDF5, PNG, PDF) disimpan di *filesystem*, "
            "sedangkan basis data hanya menyimpan lokasi dan *checksum*-nya. SIGAP DESA beserta data warganya tidak terhubung "
            "dengan sistem ini.")]
    b += [FIG("batas", "batas.png", "Batas Sistem Orbit-U: The Monitor", 13.0)]
    b += [P("Pandangan pengguna (*user views*) untuk lima peran dirangkum pada {T:uv}. Peran yang lebih tinggi mewarisi hak "
            "peran di bawahnya.")]
    b += [TAB("uv", "User Views per Peran", [1400, 1600, 2700, 2200], ["Peran", "Cara Mendapat Akun", "Data yang Dilihat", "Data yang Ditulis"], [
        ["Pengunjung (PUBLIC)", "Tanpa akun", "Angka per kecamatan dan citra 30 hari, kejadian 365 hari, master rujukan", "Registrasi akun Relawan"],
        ["Relawan (USER)", "Registrasi mandiri", "Ditambah citra 365 hari, hujan per kecamatan, peringatan aktif, seluruh riwayat kejadian, 3D AOI", "Sandi, token API, surel, dan kecamatan langganan milik sendiri"],
        ["Analis (ANALYST)", "Dibuat Administrator", "Ditambah semua citra, prakiraan, evaluasi peringatan, laporan keadaan wilayah", "Kejadian bencana, tindak lanjut peringatan"],
        ["Data Engineer (DATA_ENGINEER)", "Dibuat Administrator", "Ditambah dataset, lineage, mutu, EDA, laporan kesehatan data", "Dataset, *backfill*, status validitas scene"],
        ["Administrator (ADMIN)", "Dibuat Administrator", "Semua data", "Akun, aturan peringatan, ambang mutu, wilayah, pengaturan"],
    ])]
    b += [P('Analis dan Data Engineer sama-sama mewarisi hak Relawan, tetapi tidak saling mewarisi. Akibatnya, Analis tidak dapat mengelola dataset dan Data Engineer tidak dapat mencatat kejadian; hanya Administrator yang memiliki keduanya. Pemisahan ini mengikuti prinsip hak minimum, karena setiap peran hanya diberi hak sesuai tugasnya.')]
    b += [H4("Requirement Collection and Analysis")]
    b += [P("Kebutuhan dikumpulkan dengan teknik pada subbab 3.3. Hasil setiap teknik dan pengaruhnya terhadap rancangan "
            "ditunjukkan pada {T:ff}.")]
    b += [TAB("ff", "Teknik Pencarian Fakta dan Hasilnya", [1700, 2900, 3300], ["Teknik", "Sumber", "Hasil yang Masuk ke Rancangan"], [
        ["Observasi", "Data kegiatan GMLS (data_humanity), situs gmls.org, sumber data SIGAP DESA", "Gambaran sistem berjalan; data kependudukan dan kawasan rawan tetap di SIGAP DESA sehingga tidak disimpan ulang; batas sistem"],
        ["Wawancara", "Ketua GMLS, 16 Oktober 2026, daring, didampingi dosen", "Informasi spesifik lokasi dan notifikasi (Pantau Lokasi, langganan surel); peringatan bukan penetapan; kejadian dari sumber resmi dengan status verifikasi; batasan gempa, tsunami, rob, Himawari"],
        ["Pemeriksaan dokumen", "Profil GMLS; kriteria intensitas hujan BMKG [@bmkg_sumsel]; batas COD-AB; spesifikasi produk ESA dan NASA; kode dan skema Orbit-U: The DataLab", "alert_rules (50, 100, 150 mm); administrative_regions; batas fisik nilai per band; tabel warisan scene, dataset, job, lineage, mutu, fusion, dan Live"],
        ["Studi pustaka", "Penelitian terdahulu pada BAB II", "Pilihan basis data spasial, pencatatan lineage, RBAC di tingkat basis data, dan kandidat DBMS"],
        ["Kuesioner", "Tinjauan kebutuhan oleh GMLS (lima bagian)", "Konfirmasi kebutuhan K1–K6, informasi dan aturan pencatatan, batasan, peran, dan wilayah (subbab 4.3.4)"],
    ])]
    b += [P("Hasil analisis berupa enam kebutuhan (K1–K6) yang masing-masing ditelusuri ke bagian notulen wawancara dan "
            "objek basis data yang memenuhinya ({T:kebutuhan}). Keenam kebutuhan inilah yang kemudian ditinjau GMLS melalui "
            "kuesioner. Selain itu, masukan GMLS tentang fitur laporan (notulen D.3) dipenuhi dengan laporan mingguan dan "
            "bulanan yang disimpan di generated_reports.")]
    b += [TAB("kebutuhan", "Kebutuhan Pengguna dan Keterlacakannya", [500, 2600, 1100, 3700], ["Kode", "Kebutuhan", "Dasar (Notulen)", "Fitur dan Objek Basis Data"], [
        ["K1", "Keadaan di lokasi sendiri", "D.6", "Beranda Lokasi saya; administrative_regions, region_observations"],
        ["K2", "Pemberitahuan hujan lebat melalui surel", "B, D.6", "alert_rules (50, 100, 150 mm), alert_events, user_notify_regions, notify_sent"],
        ["K3", "Bahasa saran, bukan penetapan, dan mudah dipahami orang awam", "B, C, D.7", "Kalimat kondisi berstatus Waspada dan Tinggi; surel berlapis: ringkasan, bukti, detail teknis"],
        ["K4", "Pemantauan genangan dari satelit dan perkiraan 15 hari", "D.2, D.5", "satellite_scenes, live_scene_metrics, band_forecasts"],
        ["K5", "Catatan kejadian dari sumber resmi", "B, C", "disaster_events.info_source dan is_verified; v_evaluasi_alert"],
        ["K6", "Akses sesuai tugas", "Profil GMLS", "roles, users; GRANT, VIEW, dan RLS"],
    ])]

    # ============================================================== 4.2
    b += [P('K1 dan K2 lahir langsung dari masukan wawancara (notulen D.6) dan dipenuhi melalui perubahan prototipe setelah wawancara (subbab 4.3.3). K2 menambah dua tabel pada rancangan, yaitu user_notify_regions untuk kecamatan langganan dan notify_sent untuk mencegah surel yang sama terkirim dua kali.')]
    b += [H2("Perancangan Sistem")]
    b += [H3("Pemodelan Sistem")]
    b += [H4("Use Case Diagram")]
    b += [P("Sistem memiliki lima aktor manusia dan satu aktor sistem, yaitu *scheduler* yang terhubung sebagai role "
            "monitor_etl. Generalisasi aktor pada {G:aktor} menunjukkan bahwa Relawan mewarisi use case Pengunjung, Analis "
            "dan Data Engineer mewarisi use case Relawan, dan Administrator mewarisi keduanya.")]
    b += [FIG("aktor", "aktor.png", "Generalisasi Aktor", 11.0)]
    b += [P("Use case diambil dari *route* API dan kunci izin di api/routes/auth.py. Daftar lengkapnya ditunjukkan pada "
            "{T:uc}, sedangkan diagram per aktor untuk Analis dan Data Engineer ditunjukkan pada {G:uc_a} dan {G:uc_d}.")]
    b += [TAB("uc", "Daftar Use Case", [800, 4800, 2300], ["Kode", "Use Case", "Aktor"], [
        ["UC-01", "Memantau kondisi kecamatan (Beranda)", "Pengunjung dan peran di atasnya"],
        ["UC-02", "Melihat citra satelit (batas waktu per peran)", "Pengunjung dan peran di atasnya"],
        ["UC-03", "Mengunduh laporan PDF citra", "Pengunjung dan peran di atasnya"],
        ["UC-04", "Melihat kejadian bencana", "Pengunjung dan peran di atasnya"],
        ["UC-05", "Registrasi akun Relawan", "Pengunjung"],
        ["UC-06", "*Login* dan *logout*", "Semua peran"],
        ["UC-07", "Melihat 3D AOI", "Relawan dan peran di atasnya"],
        ["UC-08", "Melihat hujan per kecamatan dan peringatan aktif", "Relawan dan peran di atasnya"],
        ["UC-09", "Mengelola sandi dan token API sendiri", "Relawan dan peran di atasnya"],
        ["UC-10", "Melihat prakiraan dan analisa daerah", "Analis"],
        ["UC-11", "Menindaklanjuti (*acknowledge*) peringatan hujan", "Analis"],
        ["UC-12", "Mengelola kejadian bencana", "Analis"],
        ["UC-13", "Melihat evaluasi peringatan", "Analis"],
        ["UC-14", "Mengunduh laporan keadaan wilayah atau kesehatan data", "Analis, Data Engineer"],
        ["UC-15", "Mengelola scene per satelit", "Data Engineer"],
        ["UC-16", "Menjalankan *backfill*", "Data Engineer"],
        ["UC-17", "Membuat dan mengunduh dataset historis", "Data Engineer"],
        ["UC-18", "Melakukan EDA", "Data Engineer"],
        ["UC-19", "Mengelola akun pengguna", "Administrator"],
        ["UC-20", "Mengatur aturan, ambang, wilayah, pengaturan, dan Live Area", "Administrator"],
        ["UC-21", "Melihat log dan audit", "Analis, Data Engineer, Administrator"],
        ["UC-22", "Menjalankan Job Hidromet harian", "Scheduler"],
        ["UC-23", "Menjalankan siklus Live Sentinel-1", "Scheduler"],
        ["UC-24", "Membuat laporan periodik", "Scheduler"],
        ["UC-25", "Lokasi saya (kecamatan dari lokasi perangkat)", "Relawan dan peran di atasnya"],
        ["UC-26", "Mengatur surel dan kecamatan peringatan", "Relawan dan peran di atasnya"],
        ["UC-27", "Mengirim peringatan surel kondisi tidak normal", "Scheduler"],
        ["UC-28", "Memantau dan menguji surel peringatan", "Administrator"],
    ])]
    b += [P('Empat dari 28 use case dijalankan aktor Scheduler tanpa interaksi pengguna, yaitu UC-22, UC-23, UC-24, dan UC-27. Use case ini yang mengisi sebagian besar tabel transaksi, sedangkan use case aktor manusia lebih banyak membaca data melalui VIEW dan hanya menulis pada tabel tertentu sesuai perannya.')]
    b += [FIG("uc_a", "uc_a.png", "Use Case Diagram Aktor Analis", 14.0)]
    b += [P('Use case Analis berpusat pada peringatan dan kejadian, yaitu melihat prakiraan (UC-10), menindaklanjuti peringatan (UC-11), mengelola kejadian (UC-12), dan melihat evaluasi peringatan (UC-13). Ketiga use case terakhir saling berkaitan, karena evaluasi hanya bermakna bila peringatan ditindaklanjuti dan kejadian dicatat beserta status verifikasinya.')]
    b += [FIG("uc_d", "uc_d.png", "Use Case Diagram Aktor Data Engineer", 14.0)]
    b += [P("Use case Data Engineer berpusat pada kesehatan data, yaitu mutu, kelengkapan, dan pengolahan ulang, bukan "
            "pada tindak lanjut peringatan. Karena Analis dan Data Engineer tidak saling mewarisi hak, urusan pengolahan "
            "data terpisah dari keputusan analisis. Skenario use case yang "
            "paling berkaitan dengan basis data dijabarkan pada {T:ucd}.")]
    b += [TAB("ucd", "Deskripsi Use Case Menindaklanjuti Peringatan dan Mengelola Kejadian", [1800, 6100], ["Bagian", "Isi"], [
        ["UC-11 Skenario utama", "1. Analis membuka daftar peringatan aktif.\n2. Analis memilih peringatan dan mengisi catatan.\n3. Sistem mengunci baris (SELECT … FOR UPDATE) dan memeriksa statusnya.\n4. Sistem mengisi acknowledged_by, acknowledged_at, dan ack_note melalui GRANT tingkat kolom.\n5. Trigger audit_row mencatat perubahan ke audit_log."],
        ["UC-11 Alternatif", "3a. Peringatan sudah ditindaklanjuti: sistem menolak dengan ALERT_ALREADY_ACKED."],
        ["UC-11 Pascakondisi", "Peringatan hilang dari v_alert_aktif dan tercatat siapa yang menindaklanjutinya."],
        ["UC-12 Skenario utama", "1. Analis membuka halaman Kejadian.\n2. Analis memilih tambah, ubah, atau hapus.\n3. Analis mengisi jenis, kecamatan, tanggal, keterangan (10–4000 karakter), dan sumber informasi.\n4. Sistem memvalidasi data dan menyimpannya ke disaster_events.\n5. Trigger audit_row mencatat perubahan."],
        ["UC-12 Alternatif", "4a. Data tidak valid: sistem menampilkan dialog galat.\n2a. Hapus: sistem mengisi deleted_at (*soft delete*), baris tidak dihapus secara fisik."],
        ["UC-12 Pascakondisi", "Kejadian tersimpan; bila terverifikasi, kejadian ikut dihitung v_evaluasi_alert."],
    ])]
    b += [P('Kedua use case tersebut menulis data yang dipakai v_evaluasi_alert: UC-11 mengisi kolom tindak lanjut pada alert_events, sedangkan UC-12 mengisi disaster_events. Karena keduanya diawasi trigger audit, setiap perubahan dapat ditelusuri ke pengguna yang melakukannya.')]
    b += [H4("Activity Diagram")]
    b += [P("Proses yang paling menentukan isi basis data adalah Job Hidromet harian, yang mengunduh data GPM dan MODIS, "
            "menghitung nilai per kecamatan, lalu membangkitkan peringatan. Alurnya ditunjukkan pada {G:act_hj}.")]
    b += [FIG("act_hj", "act_hj.png", "Activity Diagram Job Hidromet Harian sampai Peringatan Hujan", 14.0)]
    b += [P("Proses yang paling banyak ditulis pengguna adalah pengelolaan kejadian bencana oleh Analis, sebagaimana "
            "ditunjukkan pada {G:act_kj}.")]
    b += [FIG("act_kj", "act_kj.png", "Activity Diagram Mengelola Kejadian Bencana", 14.0)]
    b += [P('Validasi pada alur ini dilakukan di dua tempat. Aplikasi menampilkan dialog galat bila data tidak valid, dan basis data tetap menolak data yang melanggar NOT NULL atau CHECK, misalnya uraian yang kurang dari 10 atau lebih dari 4000 karakter. Penghapusan berupa *soft delete*, sehingga riwayat kejadian tetap tersimpan dan tetap tercatat di audit_log.')]
    b += [H4("Sequence Diagram")]
    b += [P("{G:seq} menunjukkan urutan pesan ketika Relawan membuka citra satelit. Setiap *request* API dijalankan dalam satu "
            "transaksi yang diawali SET LOCAL ROLE sesuai peran pengguna, sehingga batas waktu 365 hari ditegakkan oleh VIEW "
            "v_citra_scenes di basis data, bukan hanya oleh aplikasi.")]
    b += [FIG("seq", "seq_citra.png", "Sequence Diagram Membuka Citra Satelit dengan SET LOCAL ROLE", 14.0)]
    b += [P("*Class diagram* tidak disajikan secara terpisah karena struktur data telah digambarkan dengan ERD pada subbab "
            "4.2.2.")]

    # ---------------------------------------------------------- 4.2.2
    b += [H3("Perancangan Database")]
    b += [H4("Desain Konseptual")]
    b += [P("Entitas diidentifikasi dari kebutuhan pada subbab 4.1.2 dan dikelompokkan ke dalam area subjek pada {T:entitas}. "
            "Model konseptual tidak memuat tipe data maupun kunci *surrogate*; entitas diberi nama bisnis dan kunci yang "
            "digambar adalah kunci alami.")]
    b += [TAB("entitas", "Identifikasi Entitas per Area Subjek", [1300, 3300, 3300], ["Area Subjek", "Entitas Konseptual", "Tabel Fisik"], [
        ["Rujukan", "Sumber Satelit, Variabel (Band), Wilayah Administrasi, Area Pantauan, Jenis Bencana, Aturan Peringatan, Ambang Mutu, Tahap Proses, Strategi Fusion, Jenis Laporan",
         "satellite_sources, spectral_bands, administrative_regions, regions_of_interest, disaster_types, alert_rules, quality_thresholds, processing_stages, fusion_strategies, report_types"],
        ["Akses", "Peran, Pengguna, Token API, Langganan Peringatan", "roles, users, api_tokens, user_notify_regions"],
        ["Akuisisi", "Scene Sentinel-1, Granule NASA", "satellite_scenes, nasa_scenes"],
        ["Pemrosesan", "Dataset, Job, Produk Data, Lineage, Metrik Mutu", "datasets, processing_jobs, data_products, data_lineage, quality_metrics"],
        ["Pemantauan", "Observasi Wilayah, Peringatan, Kejadian Bencana, Prakiraan", "region_observations, alert_events, disaster_events, band_forecasts"],
        ["Jejak", "Laporan, Log Aktivitas, Log Audit, Peringatan Terkirim", "generated_reports, user_activity_logs, audit_log, notify_sent"],
    ])]
    b += [P("Hubungan antarentitas digambarkan dengan notasi *Crow's Foot* dan dipecah per area subjek agar terbaca. "
            "{G:erda} menunjukkan area Pemantauan, yang menjawab RM1 dan RM3: observasi per wilayah dan variabel, aturan "
            "dan peringatan, serta kejadian bencana. {G:erdb} menunjukkan area Akuisisi dan Pemrosesan, yang menjawab RM2: "
            "scene dan granule menghasilkan produk data yang saling terhubung melalui lineage dan menjadi sumber observasi. "
            "{G:erdc} menunjukkan area Akses, yang menjawab RM4.")]
    b += [FIG("erda", "erd_a.png", "ERD Konseptual Area Pemantauan", 13.0)]
    b += [P('Relasi OBSERVASI dengan PERINGATAN berkardinalitas satu ke nol atau banyak, karena satu nilai hujan dapat memicu beberapa aturan sekaligus, misalnya INFO dan WARNING pada hari yang sama. Relasi PENGGUNA dengan PERINGATAN bersifat opsional karena peringatan baru memiliki penindak lanjut setelah ditindaklanjuti Analis. WILAYAH memiliki relasi rekursif karena kecamatan berada di bawah kabupaten.')]
    b += [FIG("erdb", "erd_b.png", "ERD Konseptual Area Akuisisi, Pemrosesan, dan Prakiraan", 13.0)]
    b += [P('Setiap PRODUK_DATA berasal dari tepat satu sumber: scene Sentinel-1, granule NASA, atau tanpa keduanya untuk produk gabungan (fusion). Aturan ini ditegakkan oleh CHECK chk_dprods_single_origin pada desain fisik. LINEAGE menghubungkan produk induk dan produk anak sehingga membentuk graf, dan FORECAST disimpan per variabel dengan wilayah yang opsional karena wilayah kosong berarti rerata seluruh wilayah kajian.')]
    b += [FIG("erdc", "erd_c.png", "ERD Konseptual Area Akses", 10.0)]
    b += [P("Setiap entitas memiliki *candidate key* alami. Pada perancangan fisik, kunci primer umumnya berupa kunci *surrogate*, "
            "sedangkan kunci alami dipertahankan sebagai *alternate key* (UNIQUE NOT NULL) agar baris tetap dapat dikenali "
            "tanpa ID internal. Penetapan kunci entitas utama ditunjukkan pada {T:kunci}.")]
    b += [TAB("kunci", "Candidate Key, Primary Key, dan Alternate Key", [2200, 2000, 3700], ["Tabel", "Primary Key", "Alternate Key"], [
        ["roles", "role_id", "role_code, db_role"],
        ["users", "user_id", "username, lower(email) (unik parsial)"],
        ["satellite_sources", "source_id", "source_code"],
        ["spectral_bands", "band_id", "band_code"],
        ["administrative_regions", "region_id", "pcode (P-code COD-AB)"],
        ["satellite_scenes", "scene_id", "product_identifier, scene_uuid"],
        ["nasa_scenes", "nasa_scene_id", "(source, tile_id, product_short_name, acquisition_date)"],
        ["region_observations", "obs_id", "(region_id, band_id, obs_date)"],
        ["alert_events", "alert_id", "(rule_id, region_id, observation_date)"],
        ["data_lineage", "lineage_id", "(parent_product_id, child_product_id)"],
        ["notify_sent", "notify_id", "(user_id, region_id, item_key, data_date)"],
        ["user_notify_regions", "(user_id, region_id)", "—"],
    ])]
    b += [P("Domain atribut ditegakkan dengan tipe data, NOT NULL, CHECK, dan ENUM. Sebagai contoh, {T:domain} menunjukkan "
            "domain atribut entitas Observasi, yang menjadi pusat RM1. Batas fisik nilai per band disimpan di "
            "spectral_bands.valid_min dan valid_max dan ditegakkan oleh trigger trg_obs_range.")]
    b += [TAB("domain", "Domain Atribut region_observations", [1800, 1500, 900, 3700], ["Atribut", "Tipe", "Wajib", "Domain dan Keterangan"], [
        ["obs_id", "bigint", "ya", "Kunci *surrogate*"],
        ["region_id", "integer", "ya", "FK ke administrative_regions; bagian *alternate key*"],
        ["band_id", "smallint", "ya", "FK ke spectral_bands; bagian *alternate key*"],
        ["obs_date", "date", "ya", "Tanggal data (hari UTC); bagian *alternate key*"],
        ["value", "numeric(10,4)", "tidak", "Nilai agregat; NULL bila fraksi valid di bawah ambang; rentang fisik dicek trigger"],
        ["valid_fraction", "numeric(5,4)", "ya", "Bagian poligon yang memiliki piksel valid, 0 sampai 1"],
        ["run_type", "varchar(5)", "tidak", "Run GPM: F (Final), L (Late), E (Early)"],
        ["source_product_id", "bigint", "tidak", "FK ke data_products (asal nilai)"],
        ["job_id", "bigint", "tidak", "FK ke dataset_jobs"],
        ["computed_at", "timestamptz", "ya", "Waktu perhitungan"],
    ])]
    b += [P("*Enhanced modeling* dipertimbangkan pada dua tempat. Pengguna per peran tidak dipecah menjadi subtipe karena "
            "peran hanya membedakan hak akses tanpa atribut khusus, sehingga cukup FK users.role_id. Scene Sentinel-1 dan "
            "granule NASA disimpan di dua tabel karena atributnya berbeda, sedangkan supertipe \"sumber produk\" diwujudkan "
            "pada data_products dengan CHECK chk_dprods_single_origin.")]
    b += [P("Model konseptual divalidasi terhadap transaksi pengguna dengan menelusuri jalur relasi setiap transaksi "
            "({T:transaksi}). Semua transaksi dapat dijalankan melalui relasi yang ada, sehingga model tidak memerlukan "
            "entitas tambahan. Model konseptual juga ditinjau bersama GMLS dalam bahasa awam sebagai daftar informasi yang "
            "dicatat pada bagian 2 kuesioner tinjauan kebutuhan (subbab 4.3.4).")]
    b += [TAB("transaksi", "Validasi Model Konseptual terhadap Transaksi Pengguna", [500, 2900, 1300, 3200], ["No", "Transaksi", "Peran", "Jalur Entitas"], [
        ["T1", "Melihat hujan dan kondisi kecamatan 30 hari terakhir", "Pengunjung+", "administrative_regions → region_observations ← spectral_bands → satellite_sources"],
        ["T2", "Membangkitkan peringatan saat hujan melewati ambang", "Scheduler", "region_observations → alert_events ← alert_rules ← disaster_types"],
        ["T3", "Menerima surel peringatan untuk kecamatan pilihan", "Relawan+", "users → user_notify_regions → administrative_regions; notify_sent"],
        ["T4", "Menindaklanjuti peringatan", "Analis, Administrator", "users → alert_events.acknowledged_by"],
        ["T5", "Mencatat dan memverifikasi kejadian", "Analis, Administrator", "users → disaster_events ← disaster_types, administrative_regions"],
        ["T6", "Menilai peringatan terhadap kejadian", "Analis+", "alert_events ⋈ disaster_events melalui v_evaluasi_alert"],
        ["T7", "Menelusuri asal-usul dan mutu produk", "Data Engineer+", "data_products → data_lineage → processing_jobs → processing_stages; quality_metrics"],
        ["T8", "Mengelola akun dan melihat jejak perubahan", "Administrator", "roles → users; audit_log, user_activity_logs"],
    ])]

    b += [P('T6 adalah satu-satunya transaksi yang menggabungkan dua area subjek, yaitu peringatan dan kejadian. Penggabungannya dilakukan oleh VIEW berdasarkan kecamatan, jenis bencana, dan jendela waktu 0–3 hari, bukan oleh *foreign key*, karena peringatan dan kejadian dicatat secara terpisah dan tidak selalu berpasangan.')]
    b += [H4("Desain Logikal")]
    b += [P("Model logikal relasional disusun dari model konseptual dan masih bebas dari DBMS. Hasilnya terdiri atas 43 "
            "relasi yang dikelompokkan ke dalam enam modul. Relasi inti modul M6 Observasi, Peringatan, dan Kejadian, yang "
            "menjawab RM1 dan RM3, ditunjukkan pada {G:erdl} dengan domain umum (integer, string, decimal, date); ERD logikal "
            "lengkap per modul tersedia pada repositori kode sumber penelitian.")]
    b += [FIG("erdl", "erd_logikal_core.png", "ERD Logikal Relasi Inti Modul M6", 14.0)]
    b += [P("Empat puluh dari 43 relasi memiliki kunci primer *surrogate* sendiri. Tiga relasi lainnya berkunci primer "
            "komposit: band_forecast_points dan band_forecast_scores merupakan entitas lemah karena kunci primernya memuat "
            "kunci induk (forecast_id), sedangkan user_notify_regions merupakan relasi asosiatif antara users dan "
            "administrative_regions. Beberapa entitas lain kuat tetapi eksistensinya bergantung pada induk, yang ditegakkan dengan ON DELETE CASCADE "
            "({T:dependen}).")]
    b += [TAB("dependen", "Entitas Lemah dan Entitas Dependen", [2600, 2500, 2800], ["Entitas", "Induk", "Multiplicity"], [
        ["band_forecast_points (lemah)", "band_forecasts", "1 : 0..15"],
        ["band_forecast_scores (lemah)", "band_forecasts", "1 : 0..5"],
        ["dataset_source_config", "datasets", "1 : 1..3"],
        ["dataset_jobs", "datasets", "1 : 0..*"],
        ["scene_job_state", "dataset_jobs", "1 : 0..*"],
        ["data_lineage", "data_products (induk dan anak)", "1 : 0..* pada tiap sisi"],
        ["quality_metrics", "satellite_scenes, data_products", "1 : 0..* per band"],
        ["live_scene_metrics", "live_scenes", "1 : 0..* per band dan metrik"],
    ])]
    b += [P("Normalisasi dilakukan hingga bentuk normal ketiga (3NF) dan diperiksa terhadap BCNF dan 4NF. Contoh berikut "
            "memakai data nyata observasi harian tanggal 7 Oktober 2026. Dalam bentuk tidak normal (UNF), satu baris per "
            "kecamatan per tanggal memuat grup berulang berupa beberapa variabel dalam satu sel ({T:unf}).")]
    b += [TAB("unf", "Data Observasi dalam Bentuk Tidak Normal (UNF)", [1100, 1100, 1200, 900, 3600], ["tanggal", "pcode", "kecamatan", "kabupaten", "variabel (kode, nama, satuan, sumber, nilai, run)"], [
        ["2026-10-07", "ID3602030", "Bayah", "Lebak", "RAIN_24H, Hujan 24 jam, mm, GPM, 0,7465, E\nRAIN_72H, Hujan 72 jam, mm, GPM, 4,4018, E\nNDVI, Indeks vegetasi, index, MODIS, 0,6985, –"],
        ["2026-10-07", "ID3602010", "Malingping", "Lebak", "RAIN_24H, Hujan 24 jam, mm, GPM, 0,6221, E\nRAIN_72H, Hujan 72 jam, mm, GPM, 1,1254, E\nNDVI, Indeks vegetasi, index, MODIS, 0,7409, –"],
    ])]
    b += [P("Pada 1NF, grup berulang dipecah menjadi baris sehingga setiap sel bernilai tunggal dengan kunci (tanggal, pcode, "
            "kode_band). Variabel disimpan sebagai baris, bukan kolom, sehingga variabel baru tidak mengubah skema. "
            "Ketergantungan fungsional relasi 1NF ditunjukkan pada {G:fd}: nilai dan run bergantung penuh pada kunci, "
            "kecamatan dan kabupaten hanya bergantung pada pcode, dan nama band, satuan, serta sumber hanya bergantung pada "
            "kode_band.")]
    b += [FIG("fd", "fd.png", "Ketergantungan Fungsional Relasi Observasi 1NF", 13.0)]
    b += [P("Pada 2NF, ketergantungan parsial dihapus dengan memindahkan atribut wilayah ke relasi Wilayah dan atribut band "
            "ke relasi Band. Pada 3NF, ketergantungan transitif dihapus: kabupaten menjadi rujukan rekursif ke Wilayah "
            "(parent_region_id), dan atribut sumber satelit dipindah ke relasi Sumber. Hasil dekomposisinya ditunjukkan pada "
            "{G:nf3}.")]
    b += [FIG("nf3", "nf3.png", "Hasil Dekomposisi Observasi hingga 3NF", 9.0)]
    b += [P("Contoh kedua adalah peringatan hujan. Atribut aturan (pembanding, ambang, *severity*, jenis) bergantung hanya pada "
            "kode aturan sehingga dipindah ke alert_rules, nama jenis bencana dipindah ke disaster_types, dan nama "
            "kecamatan dipindah ke administrative_regions. Kolom observed_value, threshold_value, dan severity tetap disimpan "
            "di alert_events sebagai salinan historis yang disengaja, karena ambang aturan dapat diubah Administrator dan "
            "nilai observasi dapat ditimpa run GPM Final, sedangkan peringatan harus tetap menunjukkan angka yang memicunya. "
            "Pemeriksaan tabel inti terhadap BCNF dan 4NF dirangkum pada {T:bcnf}.")]
    b += [TAB("bcnf", "Pemeriksaan Tabel Inti terhadap 3NF, BCNF, dan 4NF", [2100, 2400, 600, 700, 600, 1500], ["Tabel", "Determinan", "3NF", "BCNF", "4NF", "Catatan"], [
        ["region_observations", "obs_id; (region_id, band_id, obs_date)", "✓", "✓", "✓", "Satu fakta per baris"],
        ["spectral_bands", "band_id; band_code", "✓", "✓", "✓", "—"],
        ["administrative_regions", "region_id; pcode", "✓", "✓", "✓", "area_km2 kolom GENERATED"],
        ["alert_rules", "rule_id; rule_code", "✓", "✓", "✓", "—"],
        ["alert_events", "alert_id; (rule_id, region_id, observation_date)", "✓*", "✓*", "✓", "*Salinan historis disengaja"],
        ["disaster_events", "event_id", "✓", "✓", "✓", "Desa disimpan sebagai teks"],
        ["band_forecast_points, band_forecast_scores", "(forecast_id, step); (forecast_id, model)", "✓", "✓", "✓", "Dipisah agar bebas *multivalued dependency*"],
        ["data_lineage", "lineage_id; (parent_product_id, child_product_id)", "✓", "✓", "✓", "Satu baris per sisi graf"],
    ])]
    b += [P("Satu-satunya pengecualian pada tabel tersebut adalah salinan nilai historis di alert_events, yang sengaja "
            "dipertahankan agar peringatan lama tetap menunjukkan nilai dan ambang saat dibangkitkan walaupun aturannya "
            "kemudian diubah. Batasan integritas ditetapkan pada tingkat logikal dan diterjemahkan ke DBMS pada tahap fisik ({T:cons}). Skema "
            "akhir memuat 43 PRIMARY KEY, 80 FOREIGN KEY, 36 UNIQUE, dan 67 CHECK. Model logikal ditinjau kembali bersama "
            "GMLS dengan menerjemahkan batasan utamanya ke dalam aturan pencatatan berbahasa sehari-hari pada bagian 2 "
            "kuesioner, yaitu peringatan dicatat sekali per kecamatan per hari (UNIQUE pada alert_events), kejadian wajib "
            "berisi jenis, tanggal, kecamatan, uraian, dan sumber (NOT NULL dan CHECK pada disaster_events), kejadian baru "
            "dihitung setelah terverifikasi (filter is_verified pada v_evaluasi_alert), angka disimpan tanpa batas waktu "
            "sedangkan gambar satu tahun, dan akun tidak dihapus melainkan dinonaktifkan (users.is_active tanpa GRANT "
            "DELETE).")]
    b += [TAB("cons", "Jenis Batasan Integritas", [2000, 2400, 3500], ["Jenis", "Penegakan", "Contoh"], [
        ["Entity integrity", "PRIMARY KEY", "PK di semua tabel"],
        ["Referential integrity", "FOREIGN KEY dengan aksi eksplisit", "RESTRICT untuk master, CASCADE untuk entitas dependen, SET NULL untuk rujukan opsional"],
        ["Domain", "CHECK, ENUM, regex", "valid_fraction 0–1, quality_score 0–100, regex username dan email"],
        ["Antarkolom", "CHECK multikolom", "chk_dataset_date_range, chk_alert_ack_pair, chk_scene_invalidation, chk_rule_active_needs_threshold"],
        ["Antartabel", "Trigger", "trg_users_role_not_public, trg_obs_range"],
        ["Keunikan bersyarat", "Indeks unik parsial", "uq_roi_monitor_aoi, uq_report_ready, uq_users_email"],
    ])]

    b += [P('Aturan bisnis ditegakkan di basis data, bukan hanya di aplikasi. Sebagai contoh, chk_alert_ack_pair memastikan kolom acknowledged_by dan acknowledged_at selalu terisi atau kosong bersamaan, sehingga tidak ada peringatan yang tercatat telah ditindaklanjuti tanpa diketahui siapa pelakunya. Trigger trg_obs_range menolak nilai observasi di luar batas fisik variabelnya, misalnya curah hujan negatif akibat kesalahan pengolahan.')]
    b += [H4("DBMS Selection")]
    b += [P("Pemilihan DBMS mengikuti empat langkah dan kriteria pada subbab 3.4.2. Kandidat dalam daftar pendek adalah "
            "PostgreSQL 18.6 dengan PostGIS 3.6.2 dan MySQL 8.0.40 Community. Keduanya diuji pada skema yang setara (tipe, "
            "PK, FK, UNIQUE, CHECK, dan indeks yang sama, termasuk indeks spasial) dengan data sintetis deterministik yang "
            "sama, yaitu 28 kecamatan dan 76.720 observasi, menggunakan konfigurasi bawaan. MongoDB 7 hanya dinilai dari "
            "fiturnya karena tidak mendukung *foreign key*. Hasil kueri inti ditunjukkan pada {T:q} dan {G:qchart}.")]
    b += [TAB("q", "Median Waktu Kueri Inti (milidetik)", [600, 3700, 1200, 1200, 1200], ["Kueri", "Isi", "PostgreSQL", "MySQL", "MySQL ÷ PG"], [
        ["Q1", "Pivot hujan per kecamatan, satu tanggal", "0,45", "1,14", "2,5×"],
        ["Q2", "Tren 30 hari satu kecamatan satu band", "0,29", "0,67", "2,3×"],
        ["Q3", "Irisan poligon dan luas geodesik", "1,34", "22,57", "17×"],
        ["Q4", "Evaluasi peringatan: *hit*, *miss*, *false alarm*", "1,76", "16,64", "9×"],
        ["Q5", "Lineage 6 tingkat (WITH RECURSIVE)", "0,82", "0,43", "0,5×"],
    ])]
    b += [P('Median diambil dari run terakhir di antara tiga run terpisah, dan urutan hasilnya stabil: rentang tiga run Q3 adalah 1,09–1,34 milidetik di PostgreSQL dan 20,2–24,0 milidetik di MySQL. Pada Q1 dan Q2, sebagian selisih berasal dari *driver* pymysql; pada uji konkurensi dengan *driver* C untuk kedua DBMS, selisihnya hanya sekitar 1,25 kali.')]
    b += [FIG("qchart", "chart_q.png", "Perbandingan Median Waktu Kueri Inti", 14.0)]
    b += [P("PostgreSQL lebih cepat pada Q1–Q4, terutama kueri spasial (Q3) dan evaluasi peringatan (Q4). Kueri Q3 yang ditulis "
            "setara bahkan gagal di MySQL dengan galat 3516 karena irisan geografis menghasilkan GeometryCollection, sehingga "
            "kueri harus ditulis ulang khusus untuk MySQL. MySQL lebih cepat pada kueri rekursif Q5, meskipun keduanya di bawah "
            "1 milidetik. Pada uji skalabilitas, kueri rekap seluruh tabel (Q6) dengan 2,3 juta baris memerlukan 654 milidetik "
            "di PostgreSQL dan 5.577 milidetik di MySQL. Pada uji konkurensi dengan *driver* C, PostgreSQL unggul 13–26%, dan "
            "pada uji tulis PostgreSQL 8,2 kali lebih cepat untuk *insert* dan 1,9 kali untuk *upsert*.")]
    b += [P("Hasil uji fitur keamanan, yang paling menentukan bagi RM4, ditunjukkan pada {T:fitur}.")]
    b += [TAB("fitur", "Hasil Uji Fitur Keamanan dan Audit", [2300, 2900, 2700], ["Fitur", "PostgreSQL", "MySQL 8.0"], [
        ["F1 SET ROLE per transaksi", "Didukung; SET LOCAL ROLE mempersempit hak dan kembali otomatis setelah transaksi", "Sebagian; berlaku per sesi, hak akun tetap berlaku sehingga DELETE tetap diizinkan"],
        ["F2 Row-level security", "Didukung (CREATE POLICY)", "Tidak didukung; harus diemulasi dengan VIEW"],
        ["F3 Trigger audit OLD/NEW sebagai JSON", "Didukung dengan satu fungsi untuk semua tabel", "Sebagian; setiap kolom harus disebut per tabel"],
    ])]
    b += [P("Perbedaan F1 paling menentukan bagi rancangan ini, karena tanpa pergantian peran per transaksi seluruh "
            "pengguna aplikasi akan memakai hak akun koneksi yang sama dan pembatasan per peran hanya dapat dilakukan di "
            "aplikasi. Skor terbobot dihitung dengan persamaan pada subbab 3.4.2 dan ditunjukkan pada {T:skor}.")]
    b += [TAB("skor", "Skor Terbobot Pemilihan DBMS", [3300, 900, 1200, 1100, 1400], ["Kriteria", "Bobot", "PostgreSQL", "MySQL", "Dasar"], [
        ["Keamanan per peran dan audit", "25%", "5", "2", "F1–F3"],
        ["Kueri spasial", "20%", "5", "2", "Q3 17×, galat 3516"],
        ["Analitik dan skala", "15%", "5", "2", "Q4 9×, Q6 8,5×"],
        ["Penulisan data ETL", "10%", "5", "3", "*Insert* 8×, *upsert* 2×"],
        ["Konkurensi baca", "10%", "5", "4", "Selisih 13–26%"],
        ["Integritas relasional dan rekursif", "10%", "5", "5", "Keduanya mendukung FK"],
        ["Biaya, ekosistem, keakraban", "10%", "4", "5", "MySQL dipakai SIGAP DESA"],
        ["**Total**", "100%", "**4,90**", "**2,90**", ""],
    ])]
    b += [P("Berdasarkan skor tersebut, DBMS yang direkomendasikan adalah PostgreSQL dengan PostGIS. Penentunya bukan selisih "
            "milidetik pada kueri sederhana, melainkan kontrol akses per peran di dalam basis data, kueri spasial, dan kueri "
            "analitik saat data membesar. Keunggulan MySQL bersifat operasional, yaitu lebih akrab bagi GMLS karena SIGAP DESA "
            "memakai PHP/MySQL. Pengujian memiliki keterbatasan: data PostgreSQL berada di SSD sedangkan data MySQL di HDD, "
            "sehingga selisih pada uji tulis dan Q6 skala ×30 belum dapat diatribusikan sepenuhnya ke DBMS; keunggulan pada "
            "F1–F3, Q3, dan Q4 tidak terpengaruh karena datanya sudah berada di memori. Untuk menguji apakah keterbatasan ini "
            "mengubah rekomendasi, MySQL diberi skor 5 pada kriteria yang dapat terpengaruh media penyimpanan, yaitu "
            "penulisan data ETL serta analitik dan skala. Skor MySQL naik menjadi 3,55, masih di bawah 4,90 untuk "
            "PostgreSQL, karena selisih terbesar berasal dari keamanan per peran dan kueri spasial yang tidak bergantung "
            "pada media penyimpanan. Rekomendasi PostgreSQL dengan PostGIS tidak berubah.")]

    b += [H4("Desain Fisik")]
    b += [P("Model logikal diterjemahkan ke PostgreSQL 18 dengan ekstensi postgis dan pgcrypto melalui tiga berkas berurutan: "
            "monitor_schema.sql, monitor_security.sql, dan monitor_seed.sql. Tipe data dipilih seperti pada {T:tipe}.")]
    b += [TAB("tipe", "Pemilihan Tipe Data", [3000, 4900], ["Kebutuhan", "Tipe"], [
        ["Geometri", "GEOMETRY(MultiPolygon, 4326) untuk batas wilayah; Polygon untuk *bounding box*; Point untuk lokasi kejadian"],
        ["Waktu", "TIMESTAMPTZ untuk cap waktu; DATE untuk tanggal data (hari UTC)"],
        ["Nilai ukur", "NUMERIC(p,s) agar presisinya pasti"],
        ["Nilai tertutup lintas tabel", "ENUM, misalnya job_status_enum, product_tier_enum, alert_severity_enum"],
        ["Struktur bebas per baris", "JSONB untuk parameter tahap, pengaturan, dan isi audit"],
    ])]
    b += [P("Pemilihan NUMERIC dan TIMESTAMPTZ mencegah selisih pembulatan dan kerancuan zona waktu, karena data satelit "
            "dicatat dalam UTC sedangkan pengguna membaca dalam WIB. Hasil implementasi skema pada basis data yang berjalan per 24 Oktober 2026 adalah 43 tabel, 22 VIEW, 528 "
            "kolom, 226 *constraint*, 162 indeks, 29 *trigger*, dan 3 *policy* RLS. Prasyarat program studi mensyaratkan "
            "sekurang-kurangnya 10 tabel master dan tabel transaksi dengan sekurang-kurangnya 100 *record*. {T:record} "
            "menunjukkan bahwa terdapat 12 tabel master dan 17 tabel transaksi dengan 100 *record* atau lebih.")]
    b += [TAB("record", "Jumlah Record Tabel Master dan Tabel Transaksi", [2700, 1200, 2800, 1200], ["Tabel Master", "Record", "Tabel Transaksi (≥ 100)", "Record"], [
        ["administrative_regions", "29", "region_observations", "72.850"],
        ["processing_stages", "13", "band_forecast_points", "18.870"],
        ["spectral_bands", "11", "data_products", "15.850"],
        ["regions_of_interest", "11", "data_lineage", "8.142"],
        ["quality_thresholds", "9", "processing_jobs", "7.958"],
        ["users", "7", "processing_logs", "6.361"],
        ["roles", "5", "band_forecast_scores", "5.762"],
        ["satellite_sources", "4", "nasa_scenes", "2.230"],
        ["disaster_types", "4", "live_scene_metrics", "1.793"],
        ["alert_rules", "4", "band_forecasts", "1.342"],
        ["report_types", "4", "dataset_jobs", "1.043"],
        ["fusion_strategies", "3", "audit_log", "531"],
        ["", "", "live_events", "436"],
        ["", "", "alert_events", "210"],
        ["", "", "quality_metrics", "208"],
        ["", "", "scene_job_state", "156"],
        ["", "", "user_activity_logs", "132"],
    ])]
    b += [P("Tabel master berjumlah kecil karena berisi rujukan yang jarang berubah, sedangkan tabel transaksi bertambah "
            "setiap hari dari pekerjaan otomatis; region_observations saja bertambah rata-rata sekitar 70 *record* per hari "
            "sejak 1 Januari 2024. ERD fisik relasi inti modul M6 dengan tipe data PostgreSQL ditunjukkan pada {G:erdf}. ERD fisik seluruh modul dan kamus data "
            "lengkap tersedia pada repositori kode sumber penelitian. Kamus data dibangkitkan oleh tools/data_dictionary.py dari COMMENT pada setiap tabel dan "
            "kolom, dan kewajiban COMMENT ini diuji oleh test_schema_comments, sehingga kamus data tidak dapat berbeda dari "
            "skema.")]
    b += [FIG("erdf", "erd_fisik_core.png", "ERD Fisik Relasi Inti Modul M6", 14.0)]
    b += [P("Dibandingkan ERD logikal, ERD fisik menetapkan tipe data PostgreSQL, termasuk geometri PostGIS dan cap waktu "
            "berzona, sehingga batasan domain yang semula konseptual kini ditegakkan langsung oleh DBMS. Organisasi berkas dan indeks dirancang berdasarkan pola akses ({T:indeks}). Berkas raster disimpan di "
            "*filesystem* dengan tier RAW, ALIGNED, DESPECKLED, INDICES, ACCUMULATED, COG, dan FUSED, sedangkan basis data "
            "hanya menyimpan metadata, lokasi, dan *checksum*-nya.")]
    b += [TAB("indeks", "Rancangan Indeks Berdasarkan Pola Akses", [2900, 1700, 3300], ["Pola Akses", "Jenis Indeks", "Contoh"], [
        ["Kueri spasial (scene di AOI, kecamatan berisi titik)", "GiST", "Pada geom, bbox, location"],
        ["Deret waktu terbaru", "B-tree (… DESC)", "idx_obs_date_band, idx_scenes_acq_dt"],
        ["Baris aktif saja", "Indeks parsial", "idx_alerts_active (acknowledged_at IS NULL)"],
        ["Pencarian tanpa membedakan huruf", "Indeks ekspresi", "lower(name), lower(email)"],
        ["Lineage dua arah", "B-tree", "idx_lineage_parent_id, idx_lineage_child_id"],
        ["Prakiraan terbaru per deret", "B-tree komposit", "idx_band_forecasts_latest"],
    ])]
    b += [P("Setiap indeks pada tabel tersebut dibuat untuk kueri yang benar-benar dijalankan aplikasi, sehingga indeks "
            "tidak menambah beban penulisan tanpa manfaat; rencana eksekusinya diperiksa dengan EXPLAIN. Pandangan pengguna diwujudkan dalam 22 VIEW. VIEW utama dan peran pembacanya ditunjukkan pada {T:view}. Batas "
            "waktu per peran ditegakkan di dalam VIEW berdasarkan role basis data yang aktif, bukan hanya di menu aplikasi.")]
    b += [TAB("view", "VIEW Utama per Peran", [2600, 3800, 1500], ["VIEW", "Isi", "Dibaca"], [
        ["v_citra_scenes", "Scene dengan batas waktu: Pengunjung 30 hari, Relawan 365 hari, lainnya semua", "Pengunjung+"],
        ["v_public_lokasi_obs", "Angka per kecamatan untuk Pantau Lokasi dengan batas waktu yang sama", "Pengunjung+"],
        ["v_public_kejadian", "Kejadian 365 hari tanpa kolom pencatat dan rujukan", "Pengunjung"],
        ["v_hujan_harian_kecamatan", "Hujan 24 jam, 72 jam, 7 hari, 30 hari dan kategori BMKG", "Relawan+"],
        ["v_alert_aktif", "Peringatan yang belum ditindaklanjuti", "Relawan+"],
        ["v_evaluasi_alert", "HIT, MISS, dan FALSE_ALARM peringatan terhadap kejadian terverifikasi", "Analis"],
        ["v_ringkasan_kualitas", "Mutu per sumber per minggu", "Data Engineer"],
        ["v_kelengkapan_data", "Tanggal berdata per sumber dan celahnya", "Data Engineer"],
        ["v_log_login, v_log_unduhan", "Log masuk, registrasi, dan unduhan", "Administrator"],
    ])]
    b += [P("Dengan VIEW tersebut, setiap peran hanya membaca kolom dan rentang waktu yang dibutuhkannya; misalnya "
            "Pengunjung tidak dapat melihat siapa yang mencatat kejadian. Mekanisme keamanan dirancang berlapis. Lima peran aplikasi dipetakan ke lima role PostgreSQL dengan hierarki "
            "pewarisan pada {G:role}. API terhubung sebagai monitor_app yang bersifat NOINHERIT, sehingga tanpa SET ROLE role "
            "ini tidak memiliki hak apa pun. *Scheduler* dan *pipeline* terhubung sebagai monitor_etl. Tidak ada role aplikasi "
            "yang berstatus SUPERUSER, CREATEDB, CREATEROLE, atau BYPASSRLS.")]
    b += [FIG("role", "role.png", "Hierarki Role Aplikasi dan Role PostgreSQL", 13.0)]
    b += [P("Setiap *request* melewati tiga lapis penegakan ({G:lapis}): menu antarmuka disusun dari kunci izin, *route* API "
            "memeriksa peran, dan basis data menegakkan GRANT, VIEW, RLS, serta mencatat audit. Karena lapis ketiga berada di "
            "basis data, kueri yang lolos dari pemeriksaan API akibat kesalahan program tetap ditolak.")]
    b += [FIG("lapis", "lapis.png", "Tiga Lapis Penegakan Hak Akses", 12.0)]
    b += [P("Lapis pertama dan kedua bertujuan memudahkan pengguna dan memberi pesan galat yang jelas, sedangkan lapis "
            "ketiga adalah satu-satunya lapis yang tidak dapat dilewati oleh skrip yang terhubung langsung ke API. Hak akses langsung setiap role terhadap tabel dirangkum pada {T:grant}. Hak peran di bawah juga berlaku untuk "
            "peran di atasnya.")]
    b += [TAB("grant", "Matriks GRANT Tabel per Role", [2600, 700, 700, 900, 900, 900, 1100], ["Objek", "PUBLIC", "USER", "ANALYST", "DATA_ENG", "ADMIN", "ETL"], [
        ["Master rujukan (wilayah, jenis bencana, sumber, band)", "S", "S", "", "", "SIU", "S"],
        ["Master lain (aturan, ambang, pengaturan, dan lainnya)", "", "S", "", "", "SIU", "S"],
        ["users, roles", "", "", "", "", "SIU", ""],
        ["region_observations", "", "S", "", "", "", "SIU"],
        ["alert_events", "", "S", "U (kolom ack)", "", "SIUD", "SI"],
        ["disaster_events", "", "S", "SIU", "", "", "S"],
        ["datasets dan job dataset", "", "", "", "SIU", "+D", "SIU"],
        ["satellite_scenes, nasa_scenes", "", "", "", "SU", "", "SIU"],
        ["Lineage dan mutu", "", "", "", "S", "", "SIU"],
        ["generated_reports", "", "", "S (RLS)", "S (RLS)", "SIU", "SIU"],
        ["api_tokens", "", "SIU (RLS)", "", "", "", ""],
        ["user_activity_logs", "I", "", "", "", "S", "I"],
        ["audit_log", "", "", "", "", "S", ""],
    ])]
    b += [P("Keterangan: S = SELECT, I = INSERT, U = UPDATE, D = DELETE. Tidak ada peran yang memiliki DELETE pada users, "
            "disaster_events, atau log; penghapusan pada tabel tersebut memakai *soft delete* atau tidak dilakukan. "
            "*Row-level security* diterapkan pada generated_reports, sehingga laporan hanya terbaca oleh peran audiensnya, "
            "dan pada api_tokens, sehingga token hanya terbaca oleh pemiliknya. Proses *login* yang berjalan sebelum peran "
            "diketahui memakai fungsi SECURITY DEFINER, misalnya auth_get_user dan auth_register_user, yang mengunci peran "
            "registrasi mandiri sebagai Relawan.")]
    b += [P("Jejak audit dicatat oleh fungsi audit_row() yang dipasang sebagai trigger pada tabel penting, antara lain users, "
            "api_tokens, alert_rules, alert_events, disaster_events, dan app_settings. Setiap INSERT, UPDATE, dan DELETE "
            "menghasilkan satu baris audit_log berisi data lama dan baru dalam JSONB, dengan hash sandi dan token disensor, "
            "serta pelaku yang dicatat sebagai pengguna aplikasi dan role basis data. Parameter kredensial ditunjukkan pada "
            "{T:kred}.")]
    b += [TAB("kred", "Parameter Kredensial dan Penguncian", [2600, 5300], ["Hal", "Nilai"], [
        ["Hash sandi", "bcrypt *cost* 12; panjang minimal 10 karakter"],
        ["Gagal *login*", "5 kali berturut-turut mengunci akun selama 15 menit"],
        ["Sesi", "JWT HS256 dalam *cookie*, berlaku 8 jam"],
        ["Token API", "Disimpan sebagai prefiks dan hash SHA-256; masa berlaku paling lama 180 hari; 120 *request* per menit"],
    ])]
    b += [P("Penguncian akun dan masa berlaku token membatasi dampak sandi atau token yang bocor, sedangkan penyimpanan "
            "token dalam bentuk hash membuat isi basis data yang tercuri tidak dapat langsung dipakai. Redundansi terkendali diperkenalkan hanya bila nilainya dibaca berulang dan konsistensinya dapat dijaga "
            "({T:redund}). Pemantauan dan penyelarasan dilakukan dengan database/db_manifest.sql, yang mencetak jumlah objek "
            "dan *record* per tabel, serta rencana eksekusi kueri yang disimpan di benchmark/results/explain_*.txt.")]
    b += [TAB("redund", "Redundansi Terkendali", [2900, 2400, 2600], ["Redundansi", "Alasan", "Penjaga Konsistensi"], [
        ["administrative_regions.area_km2", "Luas dipakai berulang", "Kolom GENERATED ALWAYS … STORED dari geom"],
        ["regions_of_interest.centroid", "Titik peta tanpa hitung ulang", "Trigger trg_roi_centroid"],
        ["alert_events.observed_value, threshold_value, severity", "Salinan historis", "Sengaja tidak ikut berubah"],
        ["datasets.total_scenes dan kawan-kawannya", "Progres tanpa COUNT tiap halaman dibuka", "Diperbarui job"],
        ["band_forecasts.mae, mae_naive, skill", "Ringkasan yang dibaca setiap *request*", "Ditulis bersama skor oleh forecast_store"],
    ])]

    b += [P('Setiap redundansi pada tabel tersebut memiliki penjaga konsistensi, baik berupa kolom GENERATED, trigger, maupun kode yang menulis keduanya sekaligus. VIEW tidak termasuk redundansi karena merupakan VIEW biasa yang tidak di-*materialize*, sehingga selalu membaca data terbaru dari tabel sumbernya.')]
    b += [H3("Perancangan Antarmuka")]
    b += [P("Antarmuka berupa satu aplikasi web yang terbuka untuk pengunjung. Menu disusun dari kunci izin pada "
            "GET /api/auth/session, sehingga halaman yang tidak diizinkan tidak ditampilkan. Aplikasi terdiri atas halaman Masuk, "
            "Registrasi, Beranda, Tentang, 3D AOI, Citra Satelit, Forecast, Kejadian, Data, Laporan, dan Sistem. Akses halaman "
            "per peran ditunjukkan pada {T:akses}.")]
    b += [TAB("akses", "Akses Halaman per Peran", [3300, 900, 900, 900, 1000, 900], ["Halaman", "PUBLIC", "USER", "ANALYST", "DATA_ENG", "ADMIN"], [
        ["Masuk, Registrasi", "●", "—", "—", "—", "—"],
        ["Beranda: Informasi lokasi dan panel pantau", "30 hari", "365 hari", "●", "●", "●"],
        ["Beranda: Lokasi saya", "—", "●", "●", "●", "●"],
        ["3D AOI", "—", "●", "●", "●", "●"],
        ["Citra Satelit", "30 hari", "365 hari", "●", "●", "●"],
        ["Forecast", "—", "—", "●", "—", "●"],
        ["Lihat kejadian", "365 hari", "●", "●", "●", "●"],
        ["Kelola kejadian", "—", "—", "●", "—", "●"],
        ["Data", "—", "—", "—", "●", "●"],
        ["Laporan Kesehatan Data", "—", "—", "—", "●", "●"],
        ["Laporan Keadaan AOI", "—", "—", "●", "—", "●"],
        ["Log", "—", "—", "Kejadian", "Data", "●"],
        ["Akun saya, surel, dan peringatan", "—", "sendiri", "sendiri", "sendiri", "semua"],
        ["Pengaturan aplikasi", "—", "—", "—", "—", "●"],
    ])]
    b += [P("Tampilan mengikuti satu *design system*: jendela dengan *title bar*, *menu bar*, satu baris instruksi di setiap "
            "halaman, data di dalam panel, lampu status yang selalu disertai teks, dialog modal untuk pesan, dan *taskbar* "
            "dengan menu per peran. Wireframe halaman Beranda ditunjukkan pada {G:wf}; tampilan aplikasi yang telah dibangun "
            "disajikan pada subbab 4.3.3.")]
    b += [FIG("wf", "wf.png", "Wireframe Halaman Beranda", 13.0)]

    # ============================================================== 4.3
    b += [P('Wireframe menetapkan urutan isi Beranda: daftar kecamatan, tiga ringkasan berupa status, waktu pembaruan terakhir, dan luas daerah, lalu peta kecamatan berwarna sesuai status, pilihan tema tampilan, dan Detail lokasi yang menampilkan citra serta angka satu satelit untuk kecamatan terpilih. Urutan ini dipertahankan pada aplikasi yang telah dibangun, sebagaimana terlihat pada {G:sc_beranda}.')]
    b += [H2("Testing dan Implementasi Sistem")]
    b += [H3("Implementasi")]
    b += [P("Arsitektur sistem terdiri atas penyedia data resmi, lapisan ETL berbahasa Python, penyimpanan (PostgreSQL dan "
            "*filesystem*), serta lapisan aplikasi berupa REST API FastAPI dan web ({G:arsitektur}). ETL menulis ke basis data "
            "sebagai monitor_etl, sedangkan API membaca dan menulis sebagai monitor_app dengan SET LOCAL ROLE per *request*. "
            "Aplikasi yang telah diimplementasikan dapat diakses di https://orbit-u.hakimhakim.workers.dev/, sedangkan kode "
            "sumber, skrip DDL dan kueri, konfigurasi, kamus data, serta README untuk reproduksi tersedia pada repositori "
            "https://github.com/not-notyou-you/orbit_u_monitor.")]
    b += [FIG("arsitektur", "arsitektur.png", "Arsitektur Sistem", 14.0)]
    b += [P("Setiap satelit diproses melalui tier berurutan dan menghasilkan COG per band. Nilai per kecamatan dihitung dari "
            "COG dengan agregasi zonal berbobot luas irisan sel dan poligon dikalikan kosinus lintang sel sebagai pendekatan luas di permukaan bumi, lalu disimpan ke region_observations dan dipakai "
            "untuk peringatan dan prakiraan ({G:pipeline}).")]
    b += [FIG("pipeline", "pipeline.png", "Pipeline per Satelit", 13.0)]
    b += [P("Setiap berkas keluaran dicatat di data_products dengan *checksum* SHA-256, dan setiap transformasi dicatat di "
            "data_lineage sebagai sisi graf dari produk induk ke produk anak ({G:lineage}). Dengan demikian, nilai di "
            "region_observations dapat ditelusuri melalui source_product_id hingga berkas mentah dan scene asalnya.")]
    b += [FIG("lineage", "lineage.png", "Alur Lineage Data", 6.5)]
    b += [P("Karena setiap sisi graf menyimpan *checksum* masukan dan keluaran, perubahan berkas setelah diproses dapat "
            "dideteksi, dan nilai yang meragukan dapat dihitung ulang dari produk induknya tanpa mengunduh ulang seluruh "
            "data. Pekerjaan otomatis dijalankan APScheduler dengan *advisory lock* PostgreSQL agar satu pekerjaan tidak berjalan "
            "ganda ({T:jadwal}).")]
    b += [TAB("jadwal", "Jadwal Scheduler", [3000, 2700, 2200], ["Pekerjaan", "Jadwal (WIB)", "Kunci"], [
        ["Hidromet harian", "02.00 setiap hari", "hydromet"],
        ["Pembaruan GPM Late ke Final", "Minggu 04.00", "hydromet"],
        ["Siklus Live Sentinel-1", "01.00, 07.00, 13.00, 19.00", "live"],
        ["Laporan mingguan", "Senin 03.00 dan 03.15", "report"],
        ["Laporan bulanan", "Tanggal 1, 03.30 dan 03.45", "report"],
        ["Prakiraan tersimpan", "00.30, 06.30, 12.30, 18.30", "forecast"],
    ])]
    b += [P('Pembaruan GPM Late ke Final dijadwalkan setiap Minggu karena IMERG Final terbit sekitar 3,5 bulan setelah hari pengamatan. Pada pembaruan ini, tanggal dalam 153 hari terakhir yang masih bernilai Late atau Early dihitung ulang, dan nilai Final menggantikannya melalui *upsert*. Bila kunci pekerjaan sedang dipegang proses lain, pekerjaan tidak dijalankan ganda dan dicatat dengan status SKIPPED_LOCKED.')]
    b += [H3("Data Conversion and Loading")]
    b += [P("GMLS belum memiliki basis data hidrometeorologi, sehingga tidak ada data lama yang dikonversi. Pemuatan dilakukan "
            "dari basis data kosong dengan urutan: penerapan skema, keamanan, dan *seed* (apply_schema.py); pemuatan batas "
            "kecamatan COD-AB ke administrative_regions beserta penandaan sepuluh kecamatan wilayah kajian (load_regions.py); "
            "pembuatan akun administrator pertama; *backfill* GPM dan MODIS ke region_observations dan alert_events; dan "
            "*backfill* Sentinel-1 per lintasan. Per 24 Oktober 2026, region_observations berisi 72.850 *record* untuk "
            "rentang 1 Januari 2024 hingga 22 Oktober 2026, dan alert_events berisi 210 peringatan yang dibangkitkan dari data "
            "tersebut.")]
    b += [H3("Prototyping")]
    b += [P("Prototipe berupa aplikasi web yang berjalan dan dapat dicoba pengguna. Prototipe diperbarui berdasarkan "
            "masukan GMLS dalam dua putaran. Pada wawancara 16 Oktober 2026, GMLS menanggapi sistem yang diusulkan dan "
            "menyampaikan bahwa informasi paling berguna bila spesifik ke lokasi pengguna dan dikirim sebagai notifikasi "
            "(notulen D.6), serta bahwa kalimat peringatan harus disusun hati-hati (D.7). Masukan ini diwujudkan dengan "
            "mengubah Beranda menjadi Pantau Lokasi pada 16 Oktober 2026 dan menambahkan peringatan surel per kecamatan "
            "pada 19 Oktober 2026, beserta tabel user_notify_regions dan notify_sent. Putaran kedua berupa kuesioner tinjauan "
            "kebutuhan oleh GMLS dan uji coba aplikasi oleh 13 pengguna, yang tindak lanjutnya dibahas pada subbab 4.3.4.")]
    b += [P("Tampilan utama prototipe diambil dari video demonstrasi aplikasi. {G:sc_beranda} menunjukkan Beranda Pantau Lokasi yang menampilkan status kecamatan "
            "lokasi pengguna, dan {G:sc_citra} menunjukkan perbandingan dua tanggal citra Sentinel-1.")]
    b += [FIG("sc_beranda", "sc_beranda.png", "Halaman Beranda Pantau Lokasi", 14.0)]
    b += [P('Tangkapan layar tersebut diambil dengan akun Relawan yang berada di Kecamatan Bayah. Status Waspada dipicu oleh peta genangan optik MODIS yang melewati ambang, waktu pembaruan menunjukkan perhitungan Job Hidromet terakhir, dan luas 145 km² berasal dari kolom area_km2 yang dihitung otomatis dari poligon kecamatan. Daftar di atas peta menunjukkan status kesepuluh kecamatan sekaligus.')]
    b += [FIG("sc_citra", "sc_citra.png", "Halaman Citra Satelit dengan Perbandingan Dua Tanggal", 14.0)]
    b += [P("Perbandingan dua tanggal membantu pengguna membedakan genangan baru dari badan air yang memang ada, karena "
            "keduanya tampak serupa pada satu citra radar. Batas tanggal yang dapat dipilih mengikuti VIEW v_citra_scenes, "
            "sehingga Pengunjung hanya melihat 30 hari terakhir. {G:sc_kejadian} dan {G:sc_form} menunjukkan halaman Kejadian dan formulir pencatatan kejadian, termasuk kolom "
            "sumber informasi dan status verifikasi yang dibutuhkan evaluasi peringatan. {G:sc_ack} menunjukkan tindak lanjut "
            "peringatan oleh Analis, dan {G:sc_email} menunjukkan pengaturan surel dan kecamatan langganan peringatan.")]
    b += [FIG("sc_kejadian", "sc_kejadian.png", "Halaman Kejadian", 14.0)]
    b += [P('Peta dan daftar kejadian saling terhubung: memilih baris pada daftar menyorot titik kejadiannya pada peta. Tangkapan layar tersebut diambil dari video demonstrasi dengan akun Relawan Demo dan memuat tujuh kejadian contoh yang seluruhnya belum terverifikasi, sehingga belum ikut dihitung dalam evaluasi peringatan. Jumlah ini berbeda dari basis data yang berjalan, yang per 24 Oktober 2026 berisi 18 catatan kejadian.')]
    b += [FIG("sc_form", "sc_form.png", "Formulir Catat Kejadian Baru", 14.0)]
    b += [P('Setiap isian formulir dipetakan ke kolom disaster_events: jenis bencana ke disaster_type_id, tanggal mulai dan selesai ke event_date dan event_end_date, uraian ke description, ringkasan dampak ke impact_summary, kecamatan dan desa ke region_id dan village_name, titik pada peta ke location, serta sumber, rujukan, dan status verifikasi ke info_source, source_reference, dan is_verified. Kolom bertanda bintang wajib diisi sesuai batasan NOT NULL pada tabel tersebut.')]
    b += [FIG("sc_ack", "sc_ack.png", "Tindak Lanjut Peringatan Hujan Aktif", 14.0)]
    b += [P('Catatan pada dialog tindak lanjut dibatasi 500 karakter sesuai kolom ack_note. Setelah ditandai, peringatan hilang dari daftar peringatan aktif karena v_alert_aktif hanya menampilkan peringatan yang belum ditindaklanjuti.')]
    b += [FIG("sc_email", "sc_email.png", "Pengaturan Surel dan Kecamatan Peringatan", 14.0)]

    b += [P('Pilihan "semua kecamatan" disimpan sebagai satu nilai pada kolom notify_all_regions di tabel users, sehingga kecamatan yang kelak ditambahkan ke wilayah kajian ikut terpantau. Pilihan kecamatan satu per satu disimpan di user_notify_regions. Surel hanya dikirim ke alamat yang telah lolos pengecekan dan dikonfirmasi.')]
    b += [H3("Testing")]
    b += [P("Pengujian mencakup enam evaluasi minimum sesuai rancangan pada subbab 3.4.3. Hubungan antara alat uji dan "
            "evaluasi yang dibuktikannya ditunjukkan pada {G:strategi}.")]
    b += [FIG("strategi", "strategi.png", "Strategi Pengujian", 8.0)]
    b += [P('Pengujian otomatis dijalankan pada basis data uji yang terpisah, sehingga tidak mengubah data produksi. Uji pencadangan dan pemulihan memakai salinan basis data produksi agar hasilnya mencerminkan data yang sebenarnya.')]
    b += [H4("Requirement/User Review")]
    b += [P("Kuesioner tinjauan kebutuhan dengan lima bagian (Tabel 3.3) diisi pada 27 Oktober 2026 oleh tiga orang "
            "dari GMLS, yaitu Ketua GMLS dan dua Relawan GMLS. Rekapitulasi jawabannya ditunjukkan pada {T:review}.")]
    b += [TAB("review", "Rekapitulasi Tinjauan Kebutuhan oleh GMLS", [3100, 1900, 2900], ["Butir", "Hasil", "Catatan"], [
        ["K1 Kondisi di lokasi sendiri", "3 sesuai", "—"],
        ["K2 Peringatan hujan lebat melalui surel", "1 sesuai, 1 perlu diubah, 1 tidak sesuai", "Pemberitahuan sebaiknya melalui kanal yang biasa dipakai masyarakat di ponsel karena tidak semua orang rutin membuka surel"],
        ["K3 Bahasa peringatan dan tampilan awam", "3 sesuai", "—"],
        ["K4 Pemantauan genangan dan perkiraan 15 hari", "3 sesuai", "—"],
        ["K5 Arsip kejadian dari sumber resmi", "3 sesuai", "—"],
        ["K6 Akses sesuai peran", "3 sesuai", "—"],
        ["Data yang dicatat (model konseptual)", "2 cukup, 1 kurang", "Tambahkan proyeksi potensi hujan"],
        ["Aturan pencatatan (model logikal)", "3 sesuai", "—"],
        ["Batasan sistem", "2 dapat diterima, 1 tidak dapat diterima", "Upayakan notifikasi di ponsel bagi akun yang mendaftar dan menginginkannya"],
        ["Sepuluh kecamatan wilayah kajian", "3 ya", "—"],
        ["Persetujuan akhir", "1 disetujui, 2 disetujui dengan perbaikan", "—"],
    ])]
    b += [P("Kebutuhan K1, K3, K4, K5, dan K6, aturan pencatatan, serta sepuluh kecamatan wilayah kajian dinyatakan sesuai "
            "oleh ketiga responden, dan rancangan disetujui oleh seluruh responden, dua di antaranya dengan perbaikan. "
            "Masukan terbesar menyangkut kanal pemberitahuan. Ketua GMLS menilai K2 tidak sesuai dan batasan sistem tidak "
            "dapat diterima karena masyarakat belum terbiasa memakai surel dalam keseharian, sedangkan ponsel menjadi sarana "
            "informasi yang andal; seorang Relawan menyampaikan masukan serupa pada K2. Pemberitahuan melalui SMS atau "
            "WhatsApp tidak dapat diwujudkan dalam penelitian ini karena layanan pengiriman pesan ke ponsel berbayar per pesan "
            "atau per bulan, sementara penelitian tidak memiliki anggaran operasional untuk layanan tersebut dan GMLS belum "
            "memiliki akun layanannya. Karena itu, kanal surel dipertahankan, pemberitahuan ponsel ditetapkan sebagai batasan "
            "penelitian (subbab 1.3), dan diajukan sebagai saran pengembangan. Rancangan basis data tidak menghalangi "
            "pengembangan ini, karena pilihan kecamatan per pengguna (user_notify_regions) dan catatan pengiriman "
            "(notify_sent) tidak bergantung pada kanal pengiriman.")]
    b += [P("Masukan lain ditindaklanjuti sebagai berikut. Proyeksi potensi hujan telah tersedia sebagai bagian dari "
            "prakiraan 15 hari pada band_forecasts, yang juga mencakup variabel curah hujan RAIN_24H hingga RAIN_30D, "
            "sehingga tidak memerlukan perubahan skema; prakiraan ini tetap bersifat proyeksi statistik sesuai batasan "
            "penelitian. Untuk pemetaan peran, peran Analis diserahkan kepada tim analis GMLS, dan seorang Relawan menyatakan "
            "bersedia mengisi peran Data Engineer dan Administrator. Responden yang sama mengusulkan agar masyarakat di "
            "setiap kecamatan dapat mencatat dan melaporkan kejadian; usulan ini dicatat sebagai saran karena pada rancangan "
            "saat ini kejadian dicatat oleh Analis agar sumber dan status verifikasinya terjaga.")]
    b += [H4("Integrity dan Functional")]
    b += [P("Pengujian otomatis dengan pytest dijalankan pada 24 Oktober 2026 terhadap basis data uji. Dari 1.185 kasus uji, "
            "1.183 lulus, 0 gagal, dan 2 dilewati karena membutuhkan berkas *shapefile* COD-AB, dengan waktu eksekusi 150 "
            "detik. Uji integritas meliputi test_database, test_schema_comments, dan test_audit. Uji fungsional dilakukan "
            "dengan skenario *black-box* melalui REST API; contoh skenarionya ditunjukkan pada {T:bb}. Sesuai alur pada Gambar "
            "3.4, hasil uji yang belum lulus dikembalikan ke tahap implementasi: run 8 Oktober 2026 dengan 1.140 kasus lulus "
            "menemukan dua kegagalan, yaitu kode galat OUTSIDE_RASTER_WINDOW yang belum memiliki terjemahan di antarmuka dan "
            "pemeriksa cakupan CSS tema yang salah memecah selektor, dan keduanya diperbaiki sebelum run akhir.")]
    b += [TAB("bb", "Contoh Skenario Uji Black-Box", [400, 2400, 1500, 2300, 1300], ["No", "Skenario", "Masukan", "Hasil yang Diharapkan", "Hasil"], [
        ["1", "*Login* dengan sandi benar", "Nama pengguna dan sandi valid", "200, *cookie* sesi, menu sesuai peran", "Lulus"],
        ["2", "*Login* dengan sandi salah 5 kali", "Sandi salah ×5", "Akun terkunci 15 menit (ACCOUNT_LOCKED)", "Lulus"],
        ["3", "Registrasi dengan nama pengguna terpakai", "Nama pengguna yang sudah ada", "409 USERNAME_TAKEN", "Lulus"],
        ["4", "Registrasi mencoba memilih peran", "*Payload* berisi peran ADMIN", "Akun tetap Relawan", "Lulus"],
        ["5", "Pengunjung membuka citra lebih dari 30 hari", "Tanggal > 30 hari", "Tanggal tidak terlihat (VIEW)", "Lulus"],
        ["6", "Relawan membuka halaman Data", "GET /api/data/summary", "403 ROLE_FORBIDDEN", "Lulus"],
        ["7", "Pemeriksaan peran API dimatikan", "DELETE sebagai monitor_user", "Ditolak basis data", "Lulus"],
        ["8", "Menindaklanjuti peringatan dua kali", "POST acknowledge ×2", "409 ALERT_ALREADY_ACKED", "Lulus"],
        ["9", "Hujan pada batas ambang BMKG", "RAIN_24H = 49,99; 100; dan 151 mm di tiga kecamatan", "49,99 mm tanpa peringatan; 100 mm INFO dan WARNING; 151 mm INFO, WARNING, dan CRITICAL; masing-masing sekali per aturan, kecamatan, dan hari", "Lulus"],
        ["10", "*Backfill* lebih dari 366 hari", "Rentang 1 Januari 2024–1 Juni 2025 (518 hari)", "422 VALIDATION_ERROR", "Lulus"],
        ["11", "Menonaktifkan scene tanpa alasan", "is_valid = false, alasan kosong", "400 REASON_REQUIRED", "Lulus"],
        ["12", "Token API dicabut", "Token yang dicabut", "401 TOKEN_REVOKED", "Lulus"],
        ["13", "Perubahan data tercatat audit", "UPDATE disaster_events", "Baris audit_log berisi data lama dan baru", "Lulus"],
        ["14", "Setiap tabel dan kolom memiliki COMMENT", "Katalog skema", "Tidak ada objek tanpa komentar", "Lulus"],
    ])]
    b += [P('Pengujian fungsional juga mencakup komponen ETL, seperti agregasi zonal, mesin peringatan, dan pengiriman surel. Pengiriman surel diuji dengan server SMTP tiruan sehingga pengujian tidak pernah mengirim surel sungguhan; pengiriman melalui layanan surel sungguhan belum diuji secara otomatis.')]
    b += [H4("Uji Coba Pengguna")]
    b += [P("Sebagai pelengkap uji *black-box* melalui REST API, aplikasi dicoba langsung oleh pengguna melalui formulir "
            "uji coba berbasis web (Tabel 3.7). Formulir diisi oleh 13 responden pada 27 Oktober hingga 5 November 2026, "
            "yang dipilih untuk mewakili dua kelompok pengguna. Kelompok pertama adalah 3 peserta *Humanity Project* yang "
            "terlibat langsung di GMLS dan mewakili pengguna dari GMLS. Kelompok kedua adalah 10 mahasiswa di luar Fakultas "
            "Teknik dan Informatika yang mewakili masyarakat awam, yaitu pengguna yang tidak memiliki latar belakang teknis. Sebanyak 7 responden memakai ponsel, 5 memakai komputer atau laptop, dan "
            "1 memakai keduanya. Responden memakai akun uji yang disediakan, sehingga uji coba tidak mengubah data "
            "kejadian yang sebenarnya. Hasil per skenario ditunjukkan pada {T:uat}.")]
    b += [TAB("uat", "Rekapitulasi Uji Coba Pengguna", [500, 2800, 900, 800, 900, 900, 1100],
              ["No", "Skenario", "Berhasil", "Dengan Kesulitan", "Belum Berhasil", "Tidak Dicoba", "Rata-rata Kemudahan"], [
        ["S1", "Melihat keadaan di tempat pengguna berada", "13", "0", "0", "0", "4,31"],
        ["S2", "Mengatur pemberitahuan melalui surel", "7", "1", "4", "1", "3,75"],
        ["S3", "Melihat citra satelit", "13", "0", "0", "0", "4,54"],
        ["S4", "Melihat riwayat kejadian bencana", "12", "0", "1", "0", "4,54"],
        ["S5", "Mencatat kejadian bencana baru (Analis)", "8", "0", "0", "5", "4,50"],
        ["S6", "Menindaklanjuti peringatan hujan (Analis)", "8", "0", "0", "5", "4,62"],
    ])]
    b += [P("Rata-rata kemudahan dihitung dari skala 1 (sangat sulit) hingga 5 (sangat mudah) dan hanya mencakup skenario "
            "yang dicoba. Dari 67 percobaan, 62 berhasil (92,5%), termasuk satu yang berhasil dengan kesulitan, dengan "
            "rata-rata kemudahan 4,36. Skenario S5 dan S6 tidak dicoba oleh lima responden karena keduanya merupakan tugas "
            "akun Analis dan bersifat pilihan pada formulir. Sebanyak 9 responden menilai aplikasi layak dipakai dan 4 "
            "menilai layak dengan perbaikan; tidak ada responden yang menilai tidak layak.")]
    b += [P("Kesulitan terbanyak ada pada S2: empat responden belum berhasil menyimpan alamat surel pemberitahuan, dan "
            "sebagian belum mengetahui bahwa pengaturan ini mengharuskan pengguna masuk (*login*) lebih dulu. Pada S4, satu "
            "responden kesulitan menemukan daftar kejadian. Kedua temuan ini ditelusuri ke catatan sistem dan tidak "
            "ditemukan galat: log aplikasi mencatat penyimpanan surel dan pembukaan daftar kejadian oleh responden lain "
            "berhasil, dan skenario yang sama diselesaikan oleh responden lain pada perangkat yang sama jenisnya. Dengan "
            "demikian, kesulitan tersebut berasal dari langkah pengguna yang belum dikenal, bukan dari fungsi sistem, dan sejalan dengan saran "
            "responden agar aplikasi menyediakan petunjuk. Saran responden yang lain berkaitan dengan "
            "keterbacaan, yaitu ukuran huruf isi yang terlalu kecil dan tipis terutama di ponsel, subjudul yang perlu "
            "dibedakan dari teks isi, penjelasan yang perlu memakai bahasa yang lebih awam, serta perlunya petunjuk atau "
            "tutorial untuk langkah yang tidak langsung jelas. Saran ini dicatat untuk pengembangan antarmuka berikutnya "
            "dan tidak memengaruhi rancangan basis data.")]
    b += [H4("Security")]
    b += [P("Keamanan diuji pada dua tingkat. Pada tingkat API, test_rbac_api menjalankan 165 kasus uji yang mencoba setiap "
            "*endpoint* dengan setiap peran, termasuk pengujian lapis basis data dengan pemeriksaan peran API dimatikan. Pada "
            "tingkat basis data, tests/security/grant_matrix.sql mencocokkan 390 sel objek × role dengan matriks rancangan, "
            "lalu menguji GRANT tingkat kolom, RLS, tabel *append-only*, fungsi autentikasi, dan batas waktu VIEW per peran, "
            "serta memastikan monitor_app tidak memiliki hak tanpa SET ROLE. Seluruh pengujian tersebut lulus.")]
    b += [H4("Query")]
    b += [P("Kinerja kueri diuji melalui benchmark pada subbab 4.2.2.3. Pada PostgreSQL, kelima kueri inti selesai di bawah "
            "2 milidetik (median 0,29–1,76 milidetik), kueri rekap Q6 pada 2,3 juta baris selesai dalam 654 milidetik, dan "
            "throughput mencapai 8.523 kueri per detik pada 8 klien. Hasil setiap kueri divalidasi dengan jumlah baris yang "
            "sama di kedua DBMS, dan luas irisan Q3 cocok per kecamatan dengan selisih maksimum 0,1%.")]
    b += [H4("Backup/Recovery")]
    b += [P("Pengujian pencadangan dan pemulihan dijalankan pada 23 Oktober 2026 dengan PostgreSQL 18.6 terhadap salinan "
            "basis data produksi berisi 44 tabel dan 146.541 baris ({T:br}).")]
    b += [TAB("br", "Hasil Uji Backup dan Recovery", [2500, 3100, 2300], ["Skenario", "Langkah", "Hasil"], [
        ["Backup dan restore", "pg_dump -Fc, basis data kosong, pg_restore, lalu bandingkan isi", "Lulus: jumlah objek dan baris identik; MD5 seluruh baris 44 tabel, *sequence*, *constraint*, dan 163 indeks sama; restore 4 detik"],
        ["Hak akses setelah restore", "grant_matrix.sql pada basis data hasil restore", "Lulus"],
        ["Proses mati saat *backfill*", "*Backfill* 10 tanggal dihentikan dengan kill -9, lalu dijalankan ulang", "Lulus 3 dari 3: hanya 2 tanggal sisa yang dikerjakan, tanpa duplikat dan tanpa nilai salah"],
        ["Pekerjaan saat kunci dipegang proses lain", "Pytest: kunci advisory dipegang lebih dulu, lalu scheduler menjalankan job dengan kunci yang sama dan backfill dipicu dari halaman Data", "Lulus: job tidak dijalankan dan dicatat SKIPPED_LOCKED; backfill ditolak 409 BACKFILL_RUNNING"],
        ["Backup terjadwal", "Tugas pg_dump harian dijalankan manual", "Berhasil: 5,0 MB dalam 1,3 detik dan dapat dibaca pg_restore"],
    ])]
    b += [P("Hasil uji kunci menunjukkan bahwa pemulihan tidak hanya bergantung pada cadangan, tetapi juga pada pekerjaan "
            "yang dapat diulang dengan aman: *backfill* yang terputus cukup dijalankan ulang tanpa membersihkan data secara "
            "manual. Rekapitulasi enam evaluasi minimum ditunjukkan pada {T:rekap}.")]
    b += [TAB("rekap", "Rekapitulasi Evaluasi Minimum", [2000, 3900, 2000], ["Evaluasi", "Bukti", "Hasil"], [
        ["*Requirement/user review*", "Kuesioner tinjauan kebutuhan, tiga responden GMLS", "Disetujui (dua dengan perbaikan); kanal ponsel menjadi saran"],
        ["*Integrity*", "test_database, test_schema_comments, test_audit", "Lulus"],
        ["*Functional*", "Skenario *black-box* melalui REST API (pytest)", "Lulus"],
        ["*Security*", "test_rbac_api (165 kasus), grant_matrix.sql (390 sel)", "Lulus"],
        ["*Query*", "Benchmark Q1–Q6, E1–E3, F1–F3", "Seluruh kueri inti < 2 ms di PostgreSQL"],
        ["*Backup/recovery*", "backup_restore.sh, kill_and_resume.sh", "Lulus"],
    ])]

    # ============================================================== 4.4
    b += [P('Beberapa hal berada di luar cakupan pengujian di atas. Uji antarmuka di peramban tidak termasuk dalam run akhir, *point-in-time recovery* tidak diuji karena pengarsipan WAL tidak diaktifkan, dan berkas raster tidak dicadangkan karena dapat dibangkitkan ulang dari sumber resmi sementara angka per kecamatan tetap tersimpan di basis data.')]
    b += [H2("Hasil dan Diskusi")]
    b += [P("**RM1.** Data Sentinel-1, MODIS, dan GPM IMERG yang berbeda format, resolusi, dan frekuensi diintegrasikan dengan "
            "menjadikan kecamatan sebagai unit analisis bersama. Ketiga sumber dicatat sebagai metadata di satellite_scenes "
            "dan nasa_scenes, lalu nilai rasternya diringkas dengan agregasi zonal ke satu deret waktu region_observations "
            "dengan kunci alternatif (region_id, band_id, obs_date). Sebelas variabel dari tiga satelit disimpan sebagai baris, "
            "sehingga variabel baru tidak mengubah skema. Kueri spasial dan deret waktu ditangani PostgreSQL dengan PostGIS, "
            "yang terpilih melalui DBMS Selection dengan skor 4,90 dibandingkan 2,90. Hasil ini sejalan dengan rekomendasi "
            "basis data geospasial terintegrasi untuk mengurangi duplikasi [@dev] dan dengan keunggulan PostGIS atas MySQL "
            "pada kueri spasial [@kaptsov].")]
    b += [P("**RM2.** Ketertelusuran dijamin oleh data_products yang mencatat setiap berkas beserta *checksum* SHA-256, "
            "data_lineage yang mencatat setiap transformasi sebagai sisi graf, dan processing_jobs yang menyimpan parameter "
            "setiap tahap. Nilai di region_observations dapat ditelusuri melalui source_product_id hingga berkas mentah. Mutu "
            "dicatat di quality_metrics dan dibandingkan dengan quality_thresholds. Pendekatan ini sesuai dengan penempatan "
            "*lineage* sebagai metadata terstruktur dalam tata kelola ETL [@gopaluni].")]
    b += [P("**RM3.** Informasi disajikan melalui 22 VIEW, REST API, dan aplikasi web: kondisi per kecamatan di Beranda, "
            "peringatan hujan berbasis ambang BMKG yang dikirim melalui surel kepada pengguna yang berlangganan, arsip kejadian "
            "dengan sumber dan status verifikasi, serta laporan berkala. Pada tinjauan kebutuhan, kebutuhan K1 dan K3–K6 dinilai "
            "sesuai oleh ketiga responden GMLS, sedangkan K2 mendapat masukan agar pemberitahuan dikirim ke ponsel, yang belum dapat diwujudkan karena keterbatasan biaya layanan pesan. Pada uji coba pengguna, 62 dari 67 percobaan oleh 13 responden berhasil dengan rata-rata kemudahan 4,36 dari 5. Evaluasi ketepatan peringatan telah tersedia melalui v_evaluasi_alert, tetapi hasilnya bergantung "
            "pada jumlah kejadian terverifikasi dari sumber resmi.")]
    b += [P("**RM4.** Kontrol akses ditegakkan di basis data melalui lima role PostgreSQL yang diaktifkan dengan SET LOCAL ROLE "
            "per transaksi, GRANT tingkat tabel dan kolom, VIEW dengan batas waktu per peran, dan RLS. Jejak audit dicatat "
            "trigger audit_row ke audit_log. Pengujian menunjukkan bahwa kueri dengan peran yang tidak berhak ditolak oleh basis "
            "data walaupun pemeriksaan di API dimatikan. Hasil ini sejalan dengan penerapan RBAC melalui GRANT dan REVOKE di "
            "PostgreSQL [@purwitasari], dengan tambahan pergantian peran per transaksi dan RLS yang tidak tersedia penuh di "
            "MySQL.")]
    b += [P("Dibandingkan penelitian terdahulu pada Tabel 2.1, penelitian ini menerapkan DBSDLC hingga perancangan fisik dan "
            "implementasi, bukan hanya perancangan konseptual dan logikal [@pradipta], dan menerapkannya pada data geospasial "
            "multi-satelit yang terus bertambah. Penelitian ini juga melengkapi penelitian terdahulu bersama GMLS yang berfokus "
            "pada gempa bumi [@tilung] dan tsunami [@wong] dengan data hidrometeorologi.")]
    b += [P("Penelitian ini memiliki beberapa keterbatasan. Pertama, aturan peringatan longsor belum aktif karena ambang hujan "
            "pemicu longsor belum ditetapkan dari literatur atau pemerintah. Kedua, evaluasi ketepatan peringatan belum dapat "
            "disimpulkan karena GMLS tidak mencatat kejadian sendiri dan catatan kejadian resmi yang tersedia masih terbatas. "
            "Ketiga, perbandingan DBMS memakai data sintetis dan penyimpanan yang tidak setara untuk uji tulis. Keempat, "
            "pemberitahuan baru tersedia melalui surel.")]
    return b
