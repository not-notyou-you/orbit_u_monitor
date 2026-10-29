# =====================================================================================================
# BAB V
# =====================================================================================================
def bab5():
    simpulan = [
        "Rancangan basis data relasional spasial berhasil mengintegrasikan data Sentinel-1, MODIS, dan GPM IMERG ke dalam "
        "satu unit analisis kecamatan (RM1). Ketiga sumber dicatat sebagai metadata scene dan granule, lalu nilai rasternya "
        "diringkas dengan agregasi zonal ke dalam satu deret waktu region_observations dengan kunci (kecamatan, variabel, "
        "tanggal), sehingga sebelas variabel dari tiga satelit dapat dibandingkan pada unit yang sama tanpa mengubah skema "
        "saat variabel bertambah. Basis data diimplementasikan pada PostgreSQL dengan PostGIS, yang terpilih melalui DBMS "
        "Selection dengan skor terbobot 4,90 dibandingkan 2,90 untuk MySQL 8.0, dan per 24 Oktober 2026 memuat 43 tabel, "
        "22 VIEW, serta 72.850 nilai per kecamatan untuk rentang 1 Januari 2024 hingga 22 Oktober 2026.",
        "Ketertelusuran asal-usul dan kualitas data dijamin oleh rancangan basis data (RM2). Setiap berkas keluaran dicatat "
        "di data_products beserta *checksum* SHA-256, setiap transformasi dicatat di data_lineage, parameter setiap tahap "
        "disimpan di processing_jobs, dan mutu data diukur di quality_metrics terhadap quality_thresholds. Nilai di "
        "region_observations dapat ditelusuri melalui source_product_id hingga berkas mentah dan scene asalnya, dan "
        "integritasnya ditegakkan oleh 226 *constraint* yang lulus pengujian integritas.",
        "Informasi hidrometeorologi per kecamatan disajikan melalui 22 VIEW, REST API, dan aplikasi web yang dapat "
        "dimanfaatkan GMLS untuk pemantauan kondisi wilayah dan pencatatan kejadian bencana (RM3). Fitur utamanya meliputi "
        "Pantau Lokasi, peringatan hujan berbasis ambang BMKG 50, 100, dan 150 mm yang dikirim melalui surel kepada "
        "pengguna yang berlangganan, arsip kejadian beserta sumber dan status verifikasinya, serta laporan berkala. "
        "Tinjauan kebutuhan oleh GMLS menilai keenam kebutuhan K1–K6 sesuai dan menyetujui rancangan, dengan masukan "
        "berupa pemberitahuan melalui WhatsApp dan pencatatan jumlah rumah terdampak per desa.",
        "Kontrol akses berbasis peran dan jejak audit ditegakkan pada tingkat basis data (RM4). Lima peran aplikasi "
        "dipetakan ke lima role PostgreSQL yang diaktifkan dengan SET LOCAL ROLE pada setiap transaksi, dengan GRANT "
        "tingkat tabel dan kolom, VIEW dengan batas waktu per peran, dan *row-level security*, sedangkan setiap perubahan "
        "pada tabel penting dicatat trigger audit ke audit_log. Pengujian keamanan pada 165 kasus API dan 390 sel matriks "
        "GRANT menunjukkan bahwa akses yang tidak berhak ditolak oleh basis data walaupun pemeriksaan di API dimatikan.",
        "Keenam evaluasi minimum jalur *Design and Implementation* terpenuhi: tinjauan kebutuhan disetujui GMLS, pengujian "
        "otomatis menghasilkan 1.183 kasus lulus, 0 gagal, dan 2 dilewati dari 1.185 kasus, kelima kueri inti selesai di "
        "bawah 2 milidetik, dan pemulihan dari cadangan maupun dari proses yang dihentikan paksa menghasilkan data yang "
        "identik tanpa duplikasi.",
    ]
    saran = [
        "Bagi GMLS, kejadian bencana dari sumber pemerintah sebaiknya dicatat dan diverifikasi secara rutin agar evaluasi "
        "ketepatan peringatan melalui v_evaluasi_alert dapat disimpulkan dari data yang memadai.",
        "Ambang hujan pemicu longsor perlu ditetapkan dari literatur atau instansi pemerintah agar aturan peringatan "
        "longsor yang telah tersedia di basis data dapat diaktifkan.",
        "Pemberitahuan dapat dikembangkan ke kanal yang lebih sering dibuka relawan, seperti WhatsApp atau notifikasi "
        "ponsel, sesuai masukan tinjauan kebutuhan.",
        "Bila GMLS membutuhkan analisis dampak yang lebih rinci, jumlah rumah terdampak per desa dapat dicatat sebagai "
        "atribut terstruktur, dan batas desa dapat ditambahkan sebagai data wilayah apabila tersedia dari sumber resmi.",
        "Sumber data dengan pembaruan lebih cepat, seperti satelit geostasioner Himawari yang diusulkan GMLS, dan laporan "
        "warga dari Are You In Sys dapat dikaji sebagai sumber data tambahan.",
        "Bagi penelitian selanjutnya, perbandingan DBMS sebaiknya diulang dengan data produksi dan media penyimpanan yang "
        "setara untuk kedua DBMS, sehingga selisih kinerja penulisan dapat diatribusikan sepenuhnya kepada DBMS.",
    ]
    return {
        "_Toc207196521": para("Berdasarkan hasil perancangan, implementasi, dan evaluasi, simpulan penelitian ini adalah "
                              "sebagai berikut.") + items(simpulan),
        "_Toc207196522": para("Saran untuk pengembangan sistem dan penelitian selanjutnya adalah sebagai berikut.")
                         + items(saran),
    }


# =====================================================================================================
# Halaman awal (data mahasiswa dari draft bab 1-3.pdf)
# =====================================================================================================
NAMA = "Muhammad Faiq Hakim Ulinnuha"
NIM = "00000110782"
JUDUL = ("Perancangan Sistem Basis Data Monitoring Hidrometeorologi untuk Dukungan Mitigasi Bencana Lebak Selatan "
         "Berbasis Satelit Sentinel-1, MODIS, dan GPM")
TITLE = ("Design of a Hydrometeorological Monitoring Database System to Support Disaster Mitigation in South Lebak "
         "Based on Sentinel-1, MODIS, and GPM Satellites")
ABSTRAK = (
    "Gugus Mitigasi Lebak Selatan (GMLS) belum memiliki data hidrometeorologi per wilayah yang tersimpan dan dapat "
    "ditelusuri, padahal data satelit Sentinel-1, MODIS, dan GPM IMERG tersedia terbuka meskipun berbeda format, "
    "resolusi, dan frekuensi. Penelitian ini merancang dan mengimplementasikan sistem basis data pemantauan "
    "hidrometeorologi bagi GMLS dengan metode Database System Development Life Cycle (DBSDLC) dan Unified Modeling "
    "Language (UML). Data dikumpulkan melalui wawancara, pemeriksaan dokumen, studi pustaka, dan kuesioner tinjauan "
    "kebutuhan. Hasilnya adalah basis data PostgreSQL dengan PostGIS, yang dipilih melalui perbandingan dengan MySQL 8.0 "
    "dengan skor terbobot 4,90 dibandingkan 2,90, berisi 43 tabel dan 22 VIEW. Basis data ini mengintegrasikan ketiga "
    "satelit ke dalam deret waktu per kecamatan, mencatat asal-usul data dengan checksum SHA-256 beserta mutunya, serta "
    "menegakkan kontrol akses lima peran dan jejak audit di tingkat basis data. Keenam evaluasi minimum, yaitu tinjauan "
    "kebutuhan, integritas, fungsional, keamanan, kueri, serta pencadangan dan pemulihan, terpenuhi dengan 1.183 dari "
    "1.185 kasus uji otomatis lulus dan 2 dilewati. Rancangan ini menyediakan sumber data hidrometeorologi terpusat yang "
    "dapat ditelusuri bagi GMLS.")
KATA_KUNCI = "Kata kunci: basis data spasial, DBSDLC, hidrometeorologi, kontrol akses berbasis peran, mitigasi bencana"
ABSTRACT = (
    "Gugus Mitigasi Lebak Selatan (GMLS) does not yet have stored and traceable hydrometeorological data per area, even "
    "though Sentinel-1, MODIS, and GPM IMERG satellite data are openly available in different formats, resolutions, and "
    "frequencies. This research designs and implements a hydrometeorological monitoring database system for GMLS using "
    "the Database System Development Life Cycle (DBSDLC) and the Unified Modeling Language (UML). Data were collected "
    "through an interview, document examination, literature study, and a requirements review questionnaire. The result "
    "is a PostgreSQL database with PostGIS, selected through a comparison with MySQL 8.0 with a weighted score of 4.90 "
    "against 2.90, containing 43 tables and 22 views. The database integrates the three satellites into a time series "
    "per sub-district, records data lineage with SHA-256 checksums together with data quality, and enforces access "
    "control for five roles and an audit trail at the database level. All six minimum evaluations, namely requirements "
    "review, integrity, functional, security, query, and backup and recovery, were met, with 1,183 of 1,185 automated "
    "test cases passing and 2 skipped. The design provides GMLS with a centralized and traceable source of "
    "hydrometeorological data.")
KEYWORDS = ("Keywords: DBSDLC, disaster mitigation, hydrometeorology, role-based access control, spatial database")


def front_matter(doc):
    stop = doc.find("DAFTAR ISI</w:t>")
    paras = [(m.start(), m.end()) for m in re.finditer(r"<w:p\b[^>]*?(?:/>|>.*?</w:p>)", doc[:stop], re.S)]

    def rebuild(px, texts):
        if px.endswith("/>"):
            return px
        open_tag = re.match(r"<w:p\b[^>]*>", px).group(0)
        ppr = re.search(r"<w:pPr>.*?</w:pPr>", px, re.S)
        ppr = ppr.group(0) if ppr else ""
        rpr = re.search(r"<w:r\b[^>]*>\s*(<w:rPr>.*?</w:rPr>)", px, re.S)
        rpr = rpr.group(1) if rpr else ""
        rpr = re.sub(r"<w:(color|highlight|i|iCs)\b[^>]*/>", "", rpr)
        starts = "".join(re.findall(r"<w:bookmarkStart\b[^>]*/>", px))
        ends = "".join(re.findall(r"<w:bookmarkEnd\b[^>]*/>", px))
        out = []
        for k, t in enumerate(texts):
            run = f'<w:r>{rpr}<w:t xml:space="preserve">{escape(t)}</w:t></w:r>' if t else ""
            out.append(open_tag + ppr + (starts if k == 0 else "") + run + (ends if k == len(texts) - 1 else "") + "</w:p>")
        return "".join(out)

    upper = JUDUL.upper()
    M = {
        0: [upper], 4: ["SKRIPSI"], 6: [NAMA], 7: [NIM], 14: ["2026"],
        20: [upper], 23: ["SKRIPSI"], 28: [NAMA], 29: [NIM], 36: ["2026"],
        41: [f"Nama : {NAMA}"], 42: [f"Nomor Induk Mahasiswa : {NIM}"], 43: ["Program Studi : Sistem Informasi"],
        46: [upper], 47: [""], 48: [""], 57: [f"({NAMA})"],
        63: [f"Nama Lengkap : {NAMA}"], 64: [f"NIM : {NIM}"], 65: ["Program Studi : Sistem Informasi"],
        66: [f"Judul Skripsi : {JUDUL}"], 82: [f"({NAMA})"], 88: [f"({NAMA})"],
        90: ["Skripsi dengan judul"], 91: [JUDUL], 92: [""], 93: [""],
        96: [f"Nama : {NAMA}"], 97: [f"NIM : {NIM}"], 98: ["Program Studi : Sistem Informasi"],
        99: ["Fakultas : Teknik dan Informatika"], 102: ["Sidang Ujian Skripsi Universitas Multimedia Nusantara"],
        148: ["Skripsi dengan judul"], 149: [JUDUL], 150: [""],
        152: [f"Nama : {NAMA}"], 153: [f"NIM : {NIM}"], 154: ["Program Studi : Sistem Informasi"],
        155: ["Fakultas : Teknik dan Informatika"],
        218: [f"Nama : {NAMA}"], 219: [f"NIM : {NIM}"], 220: ["Program Studi : Sistem Informasi"],
        221: ["Jenjang : S1"], 222: [f"Judul Karya Ilmiah : {JUDUL}"], 223: [""], 224: [""], 235: [f"({NAMA})"],
        241: ["Puji syukur penulis panjatkan kepada Tuhan Yang Maha Esa atas rahmat dan karunia-Nya sehingga skripsi "
              f"berjudul “{JUDUL}” dapat diselesaikan. Skripsi ini disusun sebagai salah satu syarat untuk memperoleh "
              "gelar Sarjana Komputer pada Program Studi Sistem Informasi, Fakultas Teknik dan Informatika, Universitas "
              "Multimedia Nusantara."],
        243: ["Dalam penyusunan skripsi ini, penulis mengucapkan terima kasih kepada:"],
        250: ["Bapak Anis Faisal Reza (Abah Lala), selaku Ketua Gugus Mitigasi Lebak Selatan, beserta pengurus GMLS yang "
              "telah bersedia menjadi narasumber dan meninjau kebutuhan sistem."],
        251: ["Semoga karya ilmiah ini bermanfaat bagi GMLS dalam memantau kondisi hidrometeorologi wilayahnya dan dapat "
              "menjadi rujukan bagi penelitian selanjutnya di bidang perancangan basis data."],
        256: [f"({NAMA})"],
        258: [JUDUL], 259: [f"({NAMA})"], 262: [ABSTRAK], 266: [KATA_KUNCI], 267: [""],
        270: [TITLE], 271: [f"({NAMA})"], 275: [ABSTRACT], 278: [KEYWORDS], 279: [""],
    }
    texts = {i: "".join(re.findall(r"<w:t[^>]*>([^<]*)", doc[a:b])) for i, (a, b) in enumerate(paras)}
    # jangkar pemeriksa: pastikan indeks menunjuk paragraf yang benar
    for i, frag in {0: "JUDUL TUGAS AKHIR", 41: "Nama", 46: "JUDUL LAPORAN", 63: "Nama Lengkap", 96: "Nama",
                    152: "Nama", 218: "Nama", 241: "Kata Pengantar dapat", 250: "Dst", 262: "Isi Abstrak",
                    275: "Content", 278: "Keywords"}.items():
        assert frag in texts[i], (i, texts[i][:60])
    for i in sorted(M, reverse=True):
        a, b = paras[i]
        doc = doc[:a] + rebuild(doc[a:b], M[i]) + doc[b:]
    return doc
