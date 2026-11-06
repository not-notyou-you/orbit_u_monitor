# Terjemahan bahasa Indonesia dari content.py (draf artikel GaEE). Struktur, kunci sitasi, gambar, dan tabel sama.
# Dibangun dengan: ARTIKEL_CONTENT=content_id python build_article.py ...
import content as _E

LABEL_FIG, LABEL_TAB, LABEL_SRC, LABEL_ABS, LABEL_KW = "Gambar", "Tabel", "Sumber", "Abstrak:", "Kata kunci: "
LABEL_REF = "Daftar Pustaka"

TITLE = ("Basis Data Spasial yang Dapat Ditelusuri untuk Integrasi Sentinel-1, MODIS, dan GPM IMERG di Tingkat "
         "Kecamatan bagi Mitigasi Bencana Hidrometeorologi Berbasis Komunitas di Lebak Selatan, Indonesia")

AUTHORS = [("Muhammad Faiq Hakim Ulinnuha", "Universitas Multimedia Nusantara, Fakultas Teknik dan Informatika, "
            "Program Studi Sistem Informasi, Tangerang, Indonesia, ORCID: [belum diisi], e-mail: [belum diisi]"),
           ("[Nama pembimbing]", "Universitas Multimedia Nusantara, Fakultas Teknik dan Informatika, "
            "Program Studi Sistem Informasi, Tangerang, Indonesia, ORCID: [belum diisi], e-mail: [belum diisi]")]

ABSTRACT = (
    "Organisasi kebencanaan berbasis komunitas dapat mengakses data satelit terbuka, tetapi jarang memiliki basis data "
    "yang mengubah produk-produk yang beragam itu menjadi informasi yang tersimpan, dapat dibandingkan, dan dapat "
    "ditelusuri. Mengikuti Database System Development Life Cycle, penelitian ini merancang dan mengimplementasikan basis "
    "data tersebut untuk Gugus Mitigasi Lebak Selatan, kelompok mitigasi komunitas di Banten, Indonesia. Observasi "
    "Sentinel-1, MODIS, dan GPM IMERG diringkas dengan agregasi zonal berbobot luas menjadi satu deret waktu per "
    "kecamatan, setiap nilai dihubungkan ke berkas sumbernya melalui checksum SHA-256 dan graf lineage, serta kontrol "
    "akses berbasis peran dan audit ditegakkan di dalam basis data. PostgreSQL dengan PostGIS dipilih dibanding MySQL 8.0 "
    "dengan skor berbobot 4,90 berbanding 3,05. Skema berisi 43 tabel dan 22 view lulus 1183 dari 1185 uji otomatis "
    "(2 dilewati), menjawab seluruh kueri inti di bawah 2 ms, dan dipulihkan secara identik dari backup. GMLS menyetujui "
    "rancangan dengan revisi, dan 13 pengguna menyelesaikan 62 dari 67 percobaan tugas.")
KEYWORDS = "basis data spasial, PostGIS, penginderaan jauh satelit, lineage data, mitigasi bencana"

BODY = [
("H1", "Pendahuluan"),
("P", "Penanggulangan bencana semakin bergantung pada sistem informasi yang mengumpulkan, mengintegrasikan, dan "
      "menyebarkan data sebelum, selama, dan sesudah kejadian berbahaya [@khan]. Platform terbaru untuk wilayah luas "
      "menunjukkan bahwa nilai sistem semacam itu tidak terletak pada satu sumber data, tetapi pada integrasi data yang "
      "beragam ke dalam satu struktur konsisten yang dapat digunakan berbagai pihak [@wang]. Di Indonesia, tempat banjir dan "
      "longsor terutama dipicu hujan lebat, kajian hidrologi skala pulau dan evaluasi presipitasi satelit menunjukkan "
      "bahwa produk satelit dapat mengisi kekosongan jaringan penakar hujan yang jarang [@hidayah, @ansori]."),
("P", "Akses terhadap data satelit juga semakin terbuka. Copernicus Data Space Ecosystem menyediakan data Sentinel "
      "melalui antarmuka pemrograman aplikasi dan pemrosesan awan [@kovacs]. Synthetic aperture radar (SAR) Sentinel-1 "
      "mengamati permukaan tanpa terhalang awan dan terbukti efektif untuk deteksi banjir [@tarpanelli]. MODIS menyediakan "
      "arsip harian lebih dari dua dekade dengan kesinambungan ke VIIRS [@roman], dan GPM IMERG menyediakan estimasi "
      "presipitasi global yang perilaku jangka panjangnya telah dievaluasi di daratan [@zhu]. Ketiga misi saling "
      "melengkapi: radar melihat air menembus awan, sensor optik menggambarkan indeks vegetasi dan air pada hari cerah, "
      "dan IMERG menggambarkan hujan yang menjadi pemicu keduanya."),
("P", "Namun, ketersediaan terbuka tidak berarti data dapat langsung dipakai oleh organisasi lokal. Produk-produk itu "
      "berbeda format (GeoTIFF, HDF5, NetCDF), resolusi spasial (sekitar 10 m hingga 0,1°), dan frekuensi temporal "
      "(harian hingga 6–12 hari). Tanpa basis data yang menyimpannya dalam bentuk terstruktur dan dapat dibandingkan, "
      "setiap analisis harus diulang dari berkas mentah, dan tidak ada yang dapat memverifikasi dari berkas dan tahap "
      "pemrosesan mana suatu nilai yang dilaporkan berasal. Kajian yang menggabungkan beberapa sensor umumnya berfokus "
      "pada analisis satu kejadian, seperti kekeringan atau banjir [@liu, @castro], sedangkan pipeline terbuka untuk "
      "praproses Sentinel-1 atau data siap analisis berfokus pada pengolahan citra, bukan penyimpanan persisten "
      "[@weiss, @upadhyay]."),
("P", "Artikel ini melaporkan perancangan dan implementasi basis data pemantauan hidrometeorologi untuk Gugus Mitigasi "
      "Lebak Selatan (GMLS), kelompok mitigasi komunitas di Lebak Selatan, Banten. Kontribusinya adalah rancangan basis "
      "data, yang diuji dengan data nyata dan pengguna nyata, yang (1) mengintegrasikan Sentinel-1, MODIS, dan GPM IMERG "
      "menjadi satu deret waktu per kecamatan, (2) membuat setiap nilai dapat ditelusuri ke berkas sumber dan tahap "
      "pemrosesannya, (3) mendukung peringatan dini dan pencatatan kejadian bencana, serta (4) menegakkan kontrol akses "
      "berbasis peran dan audit di tingkat basis data, bukan hanya di aplikasi. Sistem yang diberi nama Orbit-U: The "
      "Monitor ini dapat diakses publik, dan kode sumbernya tersedia untuk reproduksi."),

("H1", "Analisis (Kondisi) Permasalahan"),
("P", "Basis data geospasial terintegrasi telah direkomendasikan untuk mengurangi duplikasi dan mendukung pengambilan "
      "keputusan lokal, misalnya dalam tata kelola penggunaan lahan [@dev]. Dalam literatur rekayasa data, lineage "
      "diperlakukan sebagai metadata terstruktur yang semestinya dicatat oleh pipeline itu sendiri, bukan direkonstruksi "
      "belakangan [@gopaluni]. Kontrol akses berbasis peran telah diimplementasikan di PostgreSQL melalui pernyataan GRANT "
      "dan REVOKE untuk sistem informasi bisnis [@purwitasari], dan PostGIS terbukti mengungguli pendekatan relasional "
      "umum untuk penyimpanan spasial dan kueri kedekatan [@kaptosv, @papasani]. Kajian-kajian tersebut membahas "
      "integrasi, lineage, keamanan, dan kinerja spasial secara terpisah; belum ada yang menggabungkan ketiga misi satelit "
      "menjadi satu deret waktu yang dapat ditelusuri dengan kontrol akses yang ditegakkan di basis data untuk organisasi "
      "komunitas."),
("P", "Penelitian yang melibatkan GMLS sejauh ini menyangkut gempa bumi dan tsunami. Pola gempa di Lebak Selatan untuk "
      "periode 2021–2025 telah dianalisis dan divisualisasikan dari dataset resmi GMLS [@tilung], dan dasbor tsunami "
      "prabencana telah dirancang untuk Desa Panggarangan [@wong]. Bahaya hidrometeorologi, yang sering terjadi di wilayah "
      "ini, belum ditangani."),
("P", "Kondisi berjalan di GMLS dianalisis melalui observasi, wawancara dengan Ketua GMLS yang didampingi dosen yang "
      "terlibat dalam proyek komunitas sebelumnya, serta pemeriksaan dokumen dan data GMLS. Data yang dimiliki GMLS terdiri "
      "atas asesmen demografis 356 rumah tangga di zona rawan tsunami Panggarangan yang dikumpulkan relawan pada "
      "Januari–Juni 2021, tabel keluarga, penduduk, tempat evakuasi, dan 25 kegiatan kesiapsiagaan pada 2023, batas "
      "administrasi resmi dan peta zona bahaya, serta katalog gempa global. Aplikasi informasi desa yang dikembangkan "
      "bersama mitra universitas (MySQL, 11 tabel) mengelola hierarki wilayah administrasi, rumah beserta status zona "
      "tsunaminya, keluarga, dan penduduk. Informasi cuaca sampai ke GMLS dari badan meteorologi nasional melalui citra "
      "radar yang menunjukkan area berpotensi hujan dan banjir, tetapi tidak spesifik terhadap lokasi warga."),
("P", "Karena itu, dirumuskan empat masalah: (P1) bagaimana mengintegrasikan ketiga sumber satelit, dengan format, "
      "resolusi, dan frekuensi yang berbeda, ke dalam satu unit analisis terstruktur; (P2) bagaimana membuat setiap nilai "
      "tersimpan dapat ditelusuri ke sumber dan pemrosesannya beserta mutunya; (P3) bagaimana menyajikan data tersimpan "
      "sebagai informasi yang mendukung pemantauan dan pencatatan kejadian bencana; dan (P4) bagaimana mengamankan data "
      "melalui kontrol akses berbasis peran dan jejak audit. Data demografis dan evakuasi tetap berada di aplikasi desa "
      "yang ada dan berada di luar cakupan basis data baru."),

("H1", "Bahan dan Metode"),
("H2", "Wilayah kajian dan data"),
("P", "Wilayah kajian terdiri atas sepuluh kecamatan di Kabupaten Lebak: Banjarsari, Bayah, Cibeber, Cigemblong, Cihara, "
      "Cijaku, Cilograng, Malingping, Panggarangan, dan Wanasalam ({F:area}). Batas wilayah diambil dari dataset batas "
      "administrasi subnasional Indonesia (COD-AB) [@codab]; luas total yang dihitung dari poligon adalah 1575,8 km^2^, "
      "berkisar dari sekitar 94,9 km^2^ (Cilograng) hingga 400,8 km^2^ (Cibeber). Pemilihan sepuluh kecamatan tersebut "
      "dikonfirmasi oleh GMLS."),
("FIG", "area"),
("P", "Produk satelit yang digunakan dirangkum pada {T:data}. SAR Sentinel-1 peka terhadap air terbuka karena permukaan "
      "air yang halus memantulkan sedikit hamburan balik [@tran, @alonso], dan pemetaan banjir global dengan data radar "
      "satu dekade telah menegaskan nilainya pada skala besar [@misra]. Observasi harian MODIS menyediakan dinamika air "
      "permukaan pada 250 m [@klein], tetapi piksel optik sering tidak valid karena tutupan awan [@tang]. Karena "
      "sumber-sumber ini tidak dapat dibandingkan piksel demi piksel, kecamatan dipilih sebagai unit analisis bersama."),
("TAB", "data"),
("P", "Ketiga misi saling melengkapi, bukan saling menggantikan. Sentinel-1 merupakan radar aktif yang dapat mengamati "
      "menembus awan, tetapi hanya melintas setiap 6–12 hari; MODIS mengamati setiap hari, tetapi kehilangan piksel "
      "saat berawan; IMERG mengukur hujan yang mendahului banjir, bukan genangannya. Resolusinya juga berbeda hingga tiga "
      "orde besaran, dari sekitar 10 m sampai 0,1° (kira-kira 11 km), sehingga nilai direduksi ke tingkat kecamatan "
      "sebelum dibandingkan. Jenis run IMERG berbeda latensinya: Early dan Late tersedia dalam hitungan jam, sedangkan "
      "Final terbit sekitar 3,5 bulan kemudian; nilai tersimpan hanya diganti oleh run yang tidak lebih buruk (Final di "
      "atas Late di atas Early), sehingga peringatan dapat memakai hujan hampir waktu nyata sementara arsip berangsur "
      "menjadi Final."),
("H2", "Metode pengembangan"),
("P", "Penelitian mengikuti Database System Development Life Cycle (DBSDLC): perencanaan basis data (pernyataan misi dan "
      "delapan tujuan misi), definisi sistem (batas sistem dan user view untuk lima peran), pengumpulan dan analisis "
      "kebutuhan, desain basis data konseptual, logikal, dan fisik, pemilihan DBMS, desain aplikasi dengan diagram use "
      "case, aktivitas, dan sekuens Unified Modeling Language [@alyami], prototyping, implementasi, pemuatan data, dan "
      "pengujian. Desain konseptual mengidentifikasi entitas, relasi, atribut, domain, dan kunci, memeriksa redundansi, "
      "dan memvalidasi model terhadap transaksi pengguna. Desain logikal mengidentifikasi entitas kuat dan lemah serta "
      "multiplisitas dan menormalisasi relasi hingga bentuk normal ketiga, dengan relasi tertentu diperiksa terhadap "
      "bentuk normal Boyce–Codd dan keempat [@skavantzos, @zhang]. Aturan integritas ditempatkan di basis data sebagai "
      "constraint dan trigger, mengikuti temuan bahwa constraint yang hanya disimpulkan dari kode aplikasi membiarkan "
      "data tidak terlindungi [@huang, @kanwal]."),
("P", "Kebutuhan dikumpulkan melalui observasi, wawancara, pemeriksaan dokumen, studi pustaka, dan kuesioner tinjauan "
      "kebutuhan. Kuesioner yang ditulis dalam bahasa sederhana bagi pengguna nonteknis meminta GMLS menilai enam "
      "kebutuhan (R1–R6), informasi yang dicatat, batasan sistem, dan pembagian peran, serta menyetujui atau menolak "
      "rancangan. Kuesioner kedua digunakan untuk uji coba pengguna dengan enam skenario tugas."),
("H2", "Agregasi zonal"),
("P", "Setiap raster dikonversi menjadi Cloud-Optimised GeoTIFF per band dan diringkas menjadi satu nilai per "
      "kecamatan. Karena satu sel IMERG berukuran 0,1° hanya mencakup satu hingga enam sel per kecamatan, mengambil sel "
      "terdekat akan membiaskan kecamatan kecil. Karena itu, nilai variabel *b* untuk kecamatan *r* pada tanggal *t* "
      "dihitung sebagai rerata sel valid yang dibobot dengan luas irisan antara setiap sel dan poligon kecamatan:"),
("EQ", "zonal"),
("P", "dengan *A*~r,c~ adalah luas planar irisan sel *c* dengan poligon *r* dikalikan kosinus lintang sel, sebagai "
      "pendekatan luasnya di permukaan bumi, *x*~c~ adalah nilai sel, dan *C*~r~ adalah himpunan sel valid yang beririsan "
      "dengan *r*. Bagian poligon yang tercakup sel valid disimpan bersama setiap nilai, sehingga nilai yang dihitung dari "
      "sebagian kecil kecamatan yang bebas awan dapat dikenali."),
("H2", "Pemilihan dan evaluasi DBMS"),
("P", "Pemilihan DBMS mengikuti empat langkah: menetapkan kerangka acuan, menyusun daftar pendek, mengevaluasi produk, "
      "dan merekomendasikan satu produk. PostgreSQL 18.6 dengan PostGIS 3.6.2 dan MySQL 8.0.40 Community masuk daftar "
      "pendek; MongoDB 7 hanya dinilai dari fitur karena tidak mendukung foreign key. Kedua kandidat relasional diberi "
      "skema setara dengan tipe, kunci, constraint, dan indeks yang sama, termasuk indeks spasial, serta data sintetis deterministik yang sama dengan konfigurasi bawaan: kisi 28 poligon kecamatan sintetis, sepuluh di antaranya membentuk wilayah kajian agar predikat spasial juga mengenai wilayah tetangga, 76 720 observasi, 1076 peringatan, dan 150 kejadian; kejadian sintetis ini memungkinkan Q4 diukur walaupun kejadian resmi terverifikasi belum ada. Semua uji dijalankan pada satu mesin (Intel Core i7-7700, 4 inti dan 8 thread, RAM 32 GB, Windows 10), dan data directory kedua sistem ditempatkan pada HDD 7200 rpm yang sama dengan buffer 128 MB dan penulisan ke disk pada setiap commit, sehingga hasil yang peka media penyimpanan dapat dibandingkan. Lima kueri inti (Q1–Q5) "
      "masing-masing dijalankan 30 kali setelah 5 kali pemanasan dalam tiga run terpisah, dan yang dilaporkan adalah "
      "mediannya. Fitur keamanan (F1–F3), skalabilitas (rekap bulanan per kecamatan atas seluruh tabel, Q6, pada 1, 10, dan 30 kali volume data, hingga 2,3 juta baris), konkurensi, dan throughput tulis juga diuji. Uji tulis diulang dalam dua sesi, dan karena PostgreSQL di HDD bervariasi antar-sesi, hasilnya dilaporkan sebagai rentang. PostgreSQL diakses melalui psycopg2, driver berbasis C; MySQL diukur dengan PyMySQL (Python murni) untuk kueri inti, dan uji skalabilitas, konkurensi, serta tulis diulang dengan mysqlclient yang berbasis C, agar overhead driver Python tidak merugikan MySQL. Produk dinilai 1 hingga 5 pada tujuh kriteria berbobot. Kriteria kinerja dinilai dari rasio sistem yang lebih lambat terhadap yang lebih cepat, dihitung dari jumlah median waktu uji di balik setiap kriteria sehingga uji dengan keterlambatan absolut terbesar paling menentukan: 5 untuk sistem yang lebih cepat atau selisih dalam 10%, 4 untuk kurang dari 2 kali, 3 untuk 2–5 kali, dan 2 untuk lebih dari 5 kali atau bila kueri harus ditulis ulang; kriteria fitur bernilai 5 bila fitur tersedia bawaan, 2 bila memerlukan penyiasatan, dan 1 bila tidak dapat disediakan. Biaya, ekosistem, dan keakraban dinilai secara kualitatif. Bobot ditetapkan penulis dari rumusan masalah (P1–P4), bukan ditanyakan kepada GMLS. Skor total dihitung sebagai:"),
("EQ", "score"),
("P", "dengan *w*~i~ adalah bobot dan *s*~i~ skor kriteria *i*. Enam evaluasi minimum rancangan adalah tinjauan "
      "kebutuhan, uji integritas, fungsional, keamanan, kueri, dan backup/recovery. Integritas dan perilaku fungsional "
      "diuji dengan skenario black-box otomatis melalui REST API [@balsam], keamanan dengan matriks GRANT dan uji API "
      "untuk setiap peran, dan pemulihan dengan skenario dump-and-restore serta penghentian proses. Penggunaan asisten AI "
      "oleh penulis dalam menyiapkan naskah ini dijelaskan pada pernyataan penutup."),

("H1", "Hasil dan Pembahasan"),
("H2", "Arsitektur dan implementasi"),
("P", "Arsitektur yang diimplementasikan memiliki empat lapisan ({F:arch}). Lapisan extract–transform–load (ETL) "
      "berbahasa Python, yang dijadwalkan dengan advisory lock agar hanya satu instans menjalankan suatu pekerjaan, "
      "mengunduh produk dari penyedia resmi, memprosesnya melalui tier berurutan, menulis raster ke filesystem dan nilai "
      "ke basis data dengan peran ETL khusus. REST API FastAPI terhubung dengan peran aplikasi tersendiri dan beralih ke "
      "peran pengguna yang meminta pada setiap transaksi. Klien web menyajikan kondisi terkini per kecamatan, citra "
      "satelit, peringatan, dan kejadian bencana. Skema yang diimplementasikan berisi 43 tabel, 22 view, 528 kolom, 226 "
      "constraint, 162 indeks, 29 trigger, dan 3 kebijakan row-level security. Skema ini memuat 12 tabel master dan 17 "
      "tabel transaksi dengan sedikitnya 100 record masing-masing, termasuk 72 850 observasi kecamatan, 15 850 produk "
      "data, 8142 sisi lineage, dan 7958 job pemrosesan."),
("FIG", "arch"),
("P", "Dua sifat arsitektur ini tidak terlihat dari lapisannya saja. Pertama, basis data hanya menyimpan nilai dan "
      "metadata, sedangkan berkas raster tetap di sistem berkas; karena itu basis data tetap cukup kecil untuk di-dump "
      "secara rutin, dan raster yang hilang dapat dibangkitkan ulang dari penyedia. Kedua, ETL dan API tidak pernah "
      "memakai role yang sama: API tidak dapat menulis observasi dan ETL tidak dapat membaca akun pengguna, sehingga "
      "kesalahan atau penyalahgunaan di satu lapisan tidak menjangkau data lapisan lain. Klien web tidak pernah "
      "terhubung langsung ke basis data."),
("H2", "Integrasi dan keterlacakan (P1, P2)"),
("P", "Inti rancangan adalah relasi region_observations ({F:erd}) dengan kunci alternatif (region_id, band_id, "
      "obs_date). Sebelas variabel dari tiga misi disimpan sebagai baris, bukan kolom: hamburan balik VV dan VH, persentase "
      "air, dan perubahan air dari Sentinel-1; fraksi banjir, NDVI, dan NDWI MODIS; serta hujan 24 jam, 72 jam, 7 hari, "
      "dan 30 hari dari IMERG. Karena itu, penambahan variabel hanya memerlukan baris baru di spectral_bands, bukan "
      "perubahan skema. Setiap band menetapkan batas fisik, dan trigger menolak nilai di luar batas itu, misalnya hujan "
      "negatif akibat kesalahan pemrosesan."),
("FIG", "erd"),
("P", "Relasi ini diperoleh melalui normalisasi record observasi tidak normal yang mengulang nama kecamatan, kabupaten, "
      "band, satuan, dan satelit di setiap baris. Memindahkan atribut wilayah dan band ke relasinya sendiri menghilangkan "
      "ketergantungan parsial (2NF); menjadikan kabupaten rujukan rekursif ke relasi wilayah melalui parent_region_id dan "
      "memindahkan atribut satelit ke relasi sumber menghilangkan ketergantungan transitif (3NF). Entitas lemah dan "
      "dependen, seperti peringatan yang tidak dapat ada tanpa aturan dan kecamatannya, diidentifikasi dengan kunci unik "
      "komposit. Secara keseluruhan skema mendefinisikan 43 primary key, 80 foreign key, 36 unique, dan 67 check "
      "constraint."),
("P", "Desain fisik mengikuti pola akses yang diamati. Indeks GiST melayani predikat spasial pada batas wilayah, jejak "
      "scene, dan lokasi kejadian; indeks B-tree menurun melayani nilai terbaru suatu deret waktu; indeks parsial hanya "
      "mencakup peringatan yang belum ditindaklanjuti; indeks ekspresi mendukung pencarian tanpa membedakan huruf; dan dua "
      "indeks B-tree pada sisi lineage memungkinkan penelusuran dua arah. Berkas raster disimpan di filesystem dalam tier "
      "berurutan dari data mentah hingga Cloud-Optimised GeoTIFF, sedangkan basis data hanya menyimpan metadata, lokasi, "
      "dan checksum-nya. User view diimplementasikan sebagai view basis data yang jendela waktunya bergantung pada peran "
      "basis data yang aktif: pengunjung melihat 30 hari citra satelit, relawan 365 hari, dan peran lain seluruh arsip. "
      "Redundansi terkendali hanya diterapkan pada nilai yang dibaca berulang dan konsistensinya dapat dijaga oleh trigger "
      "atau pekerjaan terjadwal."),
("P", "Karena GMLS belum memiliki basis data hidrometeorologi, tidak diperlukan konversi data. Pemuatan dimulai dari "
      "basis data kosong: skema, objek keamanan, dan data rujukan diterapkan berurutan, batas COD-AB dimuat dan sepuluh "
      "kecamatan wilayah kajian ditandai, lalu data GPM, MODIS, dan Sentinel-1 di-backfill. Per 24 Oktober 2026, basis "
      "data berisi 72 850 observasi dari 1 Januari 2024 hingga 22 Oktober 2026 dan 210 peringatan yang dibangkitkan "
      "darinya. Kajian bahaya banjir skala besar menunjukkan bahwa rekaman satelit multitahun seperti ini diperlukan "
      "sebelum perilaku suatu wilayah dapat ditafsirkan [@halder]."),
("P", "Keterlacakan disediakan oleh tiga relasi. data_products mencatat setiap berkas beserta checksum SHA-256-nya, "
      "data_lineage mencatat setiap transformasi sebagai sisi antara produk induk dan produk anak dengan checksum masukan "
      "dan keluaran, dan processing_jobs menyimpan parameter setiap tahap. Setiap nilai dapat ditelusuri melalui "
      "source_product_id dan kueri rekursif hingga berkas mentah asalnya, dan metrik mutu dibandingkan dengan ambang yang "
      "dapat dikonfigurasi. Hal ini sesuai dengan perlakuan lineage sebagai metadata terstruktur yang dicatat oleh "
      "pipeline [@gopaluni], dan menjawab pertanyaan yang diajukan GMLS dalam wawancara: dari mana angka yang ditunjukkan "
      "kepada warga berasal."),
("H2", "Pemilihan DBMS"),
("P", "Median waktu eksekusi kueri inti disajikan pada {T:bench} dan {F:bench}. PostgreSQL lebih cepat pada Q1–Q4, "
      "paling jelas pada irisan spasial dengan luas geodesik (Q3, 16 kali) dan evaluasi peringatan terhadap kejadian (Q4, "
      "14 kali). Q3 yang setara bahkan gagal di MySQL dengan galat 3516 karena irisan geografis menghasilkan "
      "GeometryCollection, sehingga harus ditulis ulang khusus untuk MySQL. MySQL lebih cepat pada kueri lineage rekursif "
      "Q5, meskipun keduanya selesai di bawah 1 ms. Jumlah baris setiap kueri identik di kedua sistem, dan luas irisan Q3 "
      "cocok per kecamatan dengan selisih di bawah 0,1%. Pada uji skalabilitas, kueri rekap Q6 atas 2,3 juta baris memerlukan 579 ms di PostgreSQL dan 1666 ms di MySQL (2,9 kali dengan mysqlclient), dengan p95 MySQL naik hingga 6,0 detik; PostgreSQL 11–35% lebih cepat pada pembacaan konkuren dan "
      "4,4–6,2 kali lebih cepat untuk insert. Data directory kedua sistem berada pada disk fisik yang sama, dan jumlah baris uji 2,3 juta baris identik."),
("TAB", "bench"),
("P", "Kolom rasio perlu dibaca bersama waktu absolutnya. Pada Q1, Q2 dan Q5 selisihnya di bawah 1 ms dan tidak "
      "terasa bagi pengguna, sehingga keunggulan MySQL pada Q5 tidak menentukan. Selisih yang berarti ada pada Q3 dan Q4, "
      "sekitar 17 ms dan 14 ms per eksekusi, karena kueri ini diulang untuk setiap kecamatan dan peringatan dalam job "
      "harian dan bertambah seiring arsip, seperti ditunjukkan uji 2,3 juta baris."),
("FIG", "bench"),
("P", "Perbedaan yang menentukan bersifat fungsional, bukan waktu ({T:score}). PostgreSQL mendukung SET LOCAL ROLE, "
      "yang mempersempit hak untuk satu transaksi dan kembali otomatis, kebijakan row-level security, dan satu fungsi "
      "trigger audit yang menyimpan baris lama dan baru sebagai JSON. MySQL 8.0 hanya berganti peran per sesi sementara "
      "hak akun tetap berlaku, tidak memiliki row-level security, dan memerlukan trigger per tabel untuk audit. MySQL "
      "unggul hanya pada biaya, ekosistem, dan keakraban, karena aplikasi desa yang ada menggunakan MySQL. Pengujian "
      "awal dengan PostgreSQL di SSD dan MySQL di HDD membesar-besarkan selisih yang peka media penyimpanan: dengan klien PyMySQL yang sama, kueri rekap Q6 menyusut dari 8,5 menjadi 2,8 kali dan insert dari 8,2 menjadi 4,4–6,2 kali setelah kedua sistem ditempatkan pada disk yang sama. Kueri spasial (17 menjadi 16 kali) dan fitur keamanan tidak berubah, dan evaluasi peringatan Q4 bahkan melebar dari 9 menjadi 14 kali, sehingga keunggulan PostgreSQL pada kueri-kueri ini bukan berasal dari media penyimpanan. Skor analitik MySQL karena itu naik dari 2 "
      "menjadi 3 dan totalnya dari 2,90 menjadi 3,05, tetap di bawah 4,90, karena selisih terbesar berasal dari keamanan "
      "dan kueri spasial yang tidak bergantung pada media penyimpanan. Hal ini sejalan dengan perbandingan terdahulu yang mengunggulkan PostGIS untuk "
      "beban kerja spasial [@kaptosv, @papasani]."),
("TAB", "score"),
("P", "Mengikuti rumusan masalah, keamanan berbasis role dan audit mendapat bobot terbesar karena basis data harus "
      "melindungi peringatan dan akun pengguna (P4), disusul kueri spasial yang menjadi dasar agregasi zonal. Dari "
      "selisih total 1,85 poin, keamanan berbasis role menyumbang 0,75 dan kueri spasial 0,60, atau hampir tiga perempat; "
      "integritas tidak menyumbang karena kedua sistem bernilai 5, dan biaya, ekosistem dan keakraban menjadi "
      "satu-satunya kriteria yang mengunggulkan MySQL, sebesar 0,10."),
("H2", "Informasi, kontrol akses, dan audit (P3, P4)"),
("P", "Informasi disajikan melalui 22 view, REST API, dan klien web: kondisi terkini untuk kecamatan tempat pengguna "
      "berada, peringatan hujan berdasarkan ambang 50, 100, dan 150 mm dari badan meteorologi nasional yang dikirim melalui "
      "e-mail kepada pengguna yang berlangganan, arsip kejadian bencana beserta sumber dan status verifikasinya, serta "
      "laporan berkala. Peringatan dicatat sekali per aturan, kecamatan, dan hari (unique constraint), dan check "
      "constraint memastikan orang dan waktu tindak lanjut selalu tercatat bersamaan. Lima peran aplikasi (pengunjung, "
      "relawan, analis, data engineer, dan administrator) dipetakan ke lima peran PostgreSQL. Peran API bersifat "
      "NOINHERIT dan tidak memiliki hak sampai berganti peran, dan tidak ada peran aplikasi yang merupakan superuser atau "
      "dapat melewati row-level security. View membatasi jendela waktu yang terlihat oleh setiap peran, dan trigger audit "
      "menulis setiap perubahan tabel penting ke audit_log. Dalam uji keamanan, kueri dengan peran yang tidak berwenang "
      "ditolak oleh basis data bahkan ketika pemeriksaan di API dinonaktifkan; hal ini memperluas pendekatan berbasis "
      "GRANT dari [@purwitasari] dengan pergantian peran per transaksi dan row-level security."),
("H2", "Evaluasi"),
("P", "Hasil enam evaluasi minimum dirangkum pada {T:eval}. Run uji otomatis terdiri atas 1185 kasus uji, dengan 1183 "
      "lulus, tidak ada yang gagal, dan 2 dilewati karena memerlukan shapefile batas wilayah lengkap; run sebelumnya "
      "menemukan dua kegagalan yang diperbaiki sebelum run akhir. Kelima kueri inti selesai di bawah 2 ms, dan sistem "
      "mencapai 8204 kueri per detik dengan delapan klien. Backup dan recovery diuji pada salinan basis data produksi dengan 44 tabel (43 tabel skema ditambah tabel PostGIS spatial_ref_sys) dan 146 541 baris: setelah restore, hash MD5 seluruh baris, sequence, constraint, dan 163 indeks (termasuk primary key spatial_ref_sys) identik, sesuai dengan peran struktur log dan dump dalam pemulihan yang andal [@ahmad]. Backfill yang dihentikan "
      "di tengah pemrosesan hanya melanjutkan tanggal yang tersisa tanpa duplikat."),
("TAB", "eval"),
("P", "Pada tinjauan kebutuhan, ketiga responden GMLS (ketua dan dua relawan) menilai R1 dan R3–R6 sesuai. Untuk R2, "
      "notifikasi kondisi tidak normal, satu responden setuju, satu meminta perubahan, dan satu tidak setuju karena warga "
      "lebih banyak menggunakan ponsel daripada e-mail. GMLS menyetujui rancangan, dua responden dengan revisi. Notifikasi "
      "melalui SMS atau aplikasi pesan tidak diimplementasikan karena layanan tersebut mengenakan biaya per pesan atau "
      "langganan yang melebihi anggaran penelitian; tabel langganan dan pengiriman tidak bergantung pada kanal, sehingga "
      "basis data dapat mendukung kanal tersebut tanpa perubahan. Pada uji coba pengguna, 13 responden (tiga peserta "
      "proyek komunitas universitas yang bekerja bersama GMLS dan sepuluh mahasiswa nonteknik yang mewakili pengguna "
      "awam) melakukan 67 percobaan pada enam skenario, dengan 62 (92,5%) berhasil dan rata-rata penilaian kemudahan 4,36 "
      "dari 5. Percobaan sisanya berkaitan dengan penyimpanan langganan e-mail, yang mengharuskan masuk akun terlebih "
      "dahulu, dan pencarian daftar kejadian; log aplikasi tidak menunjukkan galat, dan responden lain menyelesaikan "
      "skenario yang sama. Sembilan responden menilai aplikasi siap digunakan dan empat siap dengan perbaikan, terutama "
      "huruf yang lebih besar, bahasa yang lebih sederhana, dan panduan di dalam aplikasi."),
("H2", "Keterbatasan"),
("P", "Ketepatan peringatan dapat dievaluasi melalui view khusus yang mengelompokkan hit, miss, dan false alarm, tetapi "
      "pada saat penulisan belum tersedia kejadian hidrometeorologi resmi yang terverifikasi untuk wilayah kajian, sehingga "
      "evaluasi ini masih kosong. IMERG diketahui cenderung meremehkan hujan harian ekstrem [@ansori], dan peringatan "
      "mewarisi keterbatasan ini. Point-in-time recovery tidak diuji karena pengarsipan WAL tidak diaktifkan, dan berkas "
      "raster tidak dicadangkan karena dapat dibangkitkan ulang dari penyedia, sementara nilai per kecamatan tetap "
      "tersimpan di basis data. Benchmark menggunakan data sintetis, konfigurasi bawaan, dan HDD pada satu komputer desktop; waktu tulis absolut di SSD atau di server produksi akan lebih rendah, dan konfigurasi yang disetel dapat mengubah rasio, tetapi tidak mengubah fitur yang tidak dimiliki MySQL 8.0 (pergantian peran per transaksi dan row-level security)."),

("H1", "Kesimpulan"),
("P", "Basis data relasional spasial telah dirancang dan diimplementasikan dengan DBSDLC untuk kelompok mitigasi "
      "bencana berbasis komunitas. Observasi Sentinel-1, MODIS, dan GPM IMERG diintegrasikan menjadi satu deret waktu per "
      "kecamatan melalui agregasi zonal berbobot luas, dengan sebelas variabel disimpan sebagai baris sehingga variabel "
      "baru tidak mengubah skema. Setiap nilai dapat ditelusuri ke berkas sumbernya melalui checksum dan graf lineage, "
      "serta kontrol akses berbasis peran dan audit ditegakkan di dalam basis data itu sendiri. PostgreSQL dengan PostGIS "
      "dipilih dibanding MySQL 8.0 dengan skor berbobot 4,90 berbanding 3,05, diukur dengan kedua "
      "sistem pada disk yang sama. Keenam evaluasi minimum terpenuhi, GMLS menyetujui "
      "rancangan dengan revisi, dan pengguna awam menyelesaikan 92,5% percobaan tugas."),
("P", "Rancangan ini menunjukkan bahwa organisasi komunitas yang tidak memiliki data hidrometeorologi sendiri dapat "
      "memperoleh sumber data yang dapat ditelusuri dari misi satelit terbuka apabila integrasi, lineage, dan keamanan "
      "ditangani oleh basis data, bukan oleh aplikasi. Penelitian selanjutnya perlu menambahkan notifikasi melalui "
      "aplikasi pesan ponsel ketika pendanaan tersedia, mengevaluasi ketepatan peringatan seiring bertambahnya kejadian "
      "terverifikasi, memungkinkan warga melaporkan kejadian yang tetap berstatus belum terverifikasi sampai ditinjau "
      "analis, dan mengaktifkan pengarsipan WAL berkelanjutan untuk point-in-time recovery."),
]

FIGS = {
    "area": ("fig1_study_area.png", "Wilayah kajian: sepuluh kecamatan di Lebak Selatan, Banten, Indonesia",
             "Diolah penulis berdasarkan batas COD-AB [@codab]", _E.FIGS["area"][3]),
    "arch": ("fig2_architecture.png", "Arsitektur sistem Orbit-U: The Monitor", "Diolah penulis", _E.FIGS["arch"][3]),
    "erd": ("fig3_erd_core.png", "Relasi inti untuk observasi, lineage, peringatan, dan kejadian (notasi crow's foot)",
            "Diolah penulis", _E.FIGS["erd"][3]),
    "bench": ("fig4_benchmark.png", "Median waktu eksekusi kueri inti (skala logaritmik)", "Diolah penulis",
              _E.FIGS["bench"][3]),
}

TABLES = {
    "data": ("Sumber data satelit", "Diolah penulis berdasarkan [@tarpanelli, @roman, @zhu]",
             [1900, 2600, 1300, 1700, 1788],
             ["Misi", "Produk", "Resolusi", "Frekuensi", "Penyedia"],
             [["Sentinel-1 (S1A, S1C, S1D)", "GRD IW, polarisasi VV dan VH", "≈10 m", "6–12 hari per lintasan", "ESA, CDSE"],
              ["MODIS Terra dan Aqua", "Banjir MCDWD; MOD09A1, MOD09GA (NDVI, NDWI)", "250–500 m", "Harian; komposit 8 hari",
               "NASA LANCE, LAADS DAAC"],
              ["GPM IMERG", "Run harian Final, Late, dan Early", "0,1°", "Harian", "NASA GES DISC"]]),
    "bench": ("Median waktu eksekusi kueri inti [ms]", "Diolah penulis",
              [700, 4388, 1500, 1400, 1300],
              ["Kueri", "Isi", "PostgreSQL", "MySQL", "MySQL/PG"],
              [["Q1", "Pivot hujan per kecamatan, satu tanggal", "0,45", "0,87", "1,9×"],
               ["Q2", "Tren 30 hari, satu kecamatan dan band", "0,31", "0,68", "2,2×"],
               ["Q3", "Irisan poligon dengan luas geodesik", "1,15", "18,63", "16×"],
               ["Q4", "Evaluasi peringatan: hit, miss, false alarm", "1,06", "15,13", "14×"],
               ["Q5", "Lineage enam tingkat (WITH RECURSIVE)", "0,65", "0,45", "0,7×"]]),
    "score": ("Skor berbobot pemilihan DBMS", "Diolah penulis",
              [3600, 1000, 1400, 1100, 2188],
              ["Kriteria", "Bobot", "PostgreSQL", "MySQL", "Dasar"],
              [["Keamanan berbasis peran dan audit", "25%", "5", "2", "F1–F3"],
               ["Kueri spasial", "20%", "5", "2", "Q3 16×, ditulis ulang (galat 3516)"],
               ["Analitik dan skala", "15%", "5", "3", "Q4 14×, Q6 2,9×; jumlah 2,9×"],
               ["Penulisan ETL", "10%", "5", "3", "Insert 4,4–6,2×, upsert 1,3–2,2×; jumlah 3,2–5,0×"],
               ["Pembacaan konkuren", "10%", "5", "4", "11–35%"],
               ["Integritas relasional dan rekursif", "10%", "5", "5", "Keduanya mendukung FK"],
               ["Biaya, ekosistem, keakraban", "10%", "4", "5", "MySQL dipakai setempat"],
               ["Total", "100%", "4,90", "3,05", ""]]),
    "eval": ("Hasil enam evaluasi minimum", "Diolah penulis",
             [2300, 4188, 2800],
             ["Evaluasi", "Bukti", "Hasil"],
             [["Tinjauan kebutuhan", "Kuesioner, tiga responden GMLS", "Disetujui (dua dengan revisi)"],
              ["Integritas", "Uji skema, constraint, komentar, dan audit", "Lulus"],
              ["Fungsional", "Skenario black-box melalui REST API", "Lulus"],
              ["Keamanan", "165 kasus API, matriks GRANT 390 sel", "Lulus"],
              ["Kueri", "Benchmark Q1–Q6, konkurensi, penulisan, F1–F3", "Semua kueri inti < 2 ms"],
              ["Backup/recovery", "Dump dan restore, penghentian proses dan lanjut", "Lulus; MD5 identik"]]),
}

CLOSING = [
    ("Pendanaan", "Penelitian ini tidak menerima hibah khusus dari lembaga pendanaan mana pun di sektor publik, komersial, "
                  "maupun nirlaba."),
    ("Kontribusi Penulis (CRediT)", "M. F. H. U.: konseptualisasi, metodologi, perangkat lunak, validasi, analisis "
     "formal, investigasi, kurasi data, penulisan – draf awal, visualisasi. [Inisial pembimbing]: konseptualisasi, "
     "validasi, supervisi, penulisan – tinjauan dan penyuntingan."),
    ("Pernyataan Konflik Kepentingan", "Para penulis menyatakan tidak memiliki kepentingan finansial atau hubungan "
     "pribadi yang diketahui dapat memengaruhi pekerjaan yang dilaporkan dalam artikel ini."),
    ("Ketersediaan Data", "Kode sumber, skrip DDL, kueri, konfigurasi, kamus data, dan petunjuk reproduksi tersedia di "
     "https://github.com/not-notyou-you/orbit_u_monitor, dan sistem yang diimplementasikan dapat diakses di "
     "https://orbit-u.hakimhakim.workers.dev/. Data satelit tersedia untuk publik dari Copernicus Data Space Ecosystem dan "
     "NASA Earthdata. Data demografis GMLS memuat informasi pribadi warga dan tidak dibagikan; akses dapat diajukan "
     "kepada GMLS."),
    ("Penggunaan AI Generatif dan Teknologi Berbantuan AI", "Dalam menyiapkan naskah ini, para penulis menggunakan "
     "Claude (Anthropic) untuk menerjemahkan dan meringkas teks dari skripsi penulis pertama ke dalam bahasa Inggris, "
     "menyusun gambar dari data penulis, dan memformat daftar pustaka. Para penulis telah meninjau dan menyunting seluruh "
     "isi dan bertanggung jawab penuh atas publikasi ini."),
    ("Ucapan Terima Kasih", "Para penulis berterima kasih kepada ketua dan relawan Gugus Mitigasi Lebak Selatan atas "
     "wawancara dan tinjauan kebutuhan, serta kepada seluruh peserta uji coba pengguna."),
]

MANUAL = {
    "codab": "OCHA Field Information Services Section: Indonesia – Subnational administrative boundaries (COD-AB), "
             "[daring:] https://data.humdata.org/dataset/cod-ab-idn [diakses: 24.10.2026].",
}
