"""Menyusun BAB I-III + DAFTAR PUSTAKA ke template skripsi.

Pemakaian:
    python build_skripsi.py <template_bersih.docx> <keluaran.docx> <folder_gambar_bab3> <folder_gambar_bab4>

Selalu mulai dari template bersih, jadi aman dijalankan ulang.

Sumber isi:
- rujukan: DOCS/skripsi/referensi/abstrak_referensi.csv (setiap klaim bersitasi dicocokkan dengan abstraknya)
- fakta GMLS: DOCS/skripsi/lampiran/notulensiGMLS.txt, "Notulen Diskusi dengan GMLS.txt",
  Lembar_Tinjauan_Kebutuhan_GMLS.docx, user_review_webapp/
- fakta sistem: README.md, DATABASE.md, PIPELINE.md, INTERFACE.md, PERBANDINGAN_DBMS.md, database
Markup teks: *miring*, **tebal**, [@kunci] atau [@a,@b] sitasi, <<...>> sorotan kuning (perlu tindakan penulis).
"""
import os
import re
import sys
import zipfile
from xml.sax.saxutils import escape

SRC, OUT, IMG = sys.argv[1], sys.argv[2], sys.argv[3]

# =====================================================================================================
# Daftar pustaka (IEEE). Hanya rujukan yang punya DOI dan abstrak.
# =====================================================================================================
REF = {
    "khan": "S. M. Khan *et al.*, “A systematic review of disaster management systems: Approaches, challenges, and future directions,” *Land*, vol. 12, no. 8, Art. no. 1514, 2023, doi: 10.3390/land12081514.",
    "deng": "T. Deng, “The application of database systems in information management,” *Applied and Computational Engineering*, vol. 40, no. 1, pp. 33–42, 2024, doi: 10.54254/2755-2721/40/20230625.",
    "wang": "J. Wang *et al.*, “Digital platform empowering China–Pakistan Economic Corridor disaster management: Enhancing data integration, resilience, and policy innovation,” *International Journal of Disaster Risk Science*, vol. 16, no. 3, pp. 376–391, 2025, doi: 10.1007/s13753-025-00644-3.",
    "shafiya": "A. Shafiya, A. A. Kuntoro, F. I. W. Rohmat, and W. Wijayasari, “Development of Java Island-scale flood model using CaMa-Flood,” *IOP Conference Series: Earth and Environmental Science*, vol. 1472, no. 1, Art. no. 012031, 2025, doi: 10.1088/1755-1315/1472/1/012031.",
    "hidayah": "E. Hidayah *et al.*, “Performance of GPM-IMERG satellite precipitation for rainfall-runoff modeling in Indonesia,” *Water Practice and Technology*, vol. 19, no. 10, pp. 3909–3928, 2024, doi: 10.2166/wpt.2024.240.",
    "kovacs": "D. D. Kovács, J. Musial, J. Bojanowski, D. Clarijs, J. de la Mar, and A. Zlinszky, “Copernicus Data Space Ecosystem establishes public cloud processing for Earth observation data,” *Scientific Data*, vol. 13, no. 1, Art. no. 537, 2026, doi: 10.1038/s41597-026-06765-8.",
    "tarpanelli": "A. Tarpanelli, A. C. Mondini, and S. Camici, “Effectiveness of Sentinel-1 and Sentinel-2 for flood detection assessment in Europe,” *Natural Hazards and Earth System Sciences*, vol. 22, no. 8, pp. 2473–2489, 2022, doi: 10.5194/nhess-22-2473-2022.",
    "roman": "M. O. Román *et al.*, “Continuity between NASA MODIS Collection 6.1 and VIIRS Collection 2 land products,” *Remote Sensing of Environment*, vol. 302, Art. no. 113963, 2024, doi: 10.1016/j.rse.2023.113963.",
    "zhu": "S. Zhu *et al.*, “Evaluation of IMERG climate trends over land in the TRMM and GPM eras,” *Environmental Research Letters*, vol. 20, no. 1, Art. no. 014064, 2025, doi: 10.1088/1748-9326/ad984e.",
    "ansori": "M. B. Ansori and I. D. B. JBS, “A comprehensive evaluation of GPM IMERG satellite rainfall data across multiple temporal and spatial scales for sustainable flood risk management in East Java, Indonesia,” *Sustainability*, vol. 18, no. 9, Art. no. 4550, 2026, doi: 10.3390/su18094550.",
    "liu": "S. Liu, Y. Wu, G. Xu, S. Cheng, Y. Zhong, and Y. Zhang, “Characterizing the 2022 extreme drought event over the Poyang Lake Basin using multiple satellite remote sensing observations and in situ data,” *Remote Sensing*, vol. 15, no. 21, Art. no. 5125, 2023, doi: 10.3390/rs15215125.",
    "castro": "I. Castro-Melgar, T. Falaras, E. Basiou, and I. Parcharidis, “Assessment of the October 2024 cut-off low event floods impact in Valencia (Spain) with satellite and geospatial data,” *Remote Sensing*, vol. 17, no. 13, Art. no. 2145, 2025, doi: 10.3390/rs17132145.",
    "weiss": "T. Weiß and T. Fincke, “SenSARP: A pipeline to pre-process Sentinel-1 SLC data by using ESA SNAP Sentinel-1 Toolbox,” *Journal of Open Source Software*, vol. 7, no. 69, Art. no. 3337, 2022, doi: 10.21105/joss.03337.",
    "upadhyay": "P. Upadhyay *et al.*, “A flexible multi-temporal and multi-modal framework for Sentinel-1 and Sentinel-2 analysis ready data,” *Remote Sensing*, vol. 14, no. 5, Art. no. 1120, 2022, doi: 10.3390/rs14051120.",
    "dev": "M. Dev, V. V. S. Krishna, D. Kumar, and M. K. Jha, “Integrated geospatial database design for land use pattern analysis and its impact on local governance: A case study of Manesar Urban Complex, Gurugram, India,” *Journal of Applied and Natural Science*, vol. 15, no. 4, pp. 1541–1556, 2023, doi: 10.31018/jans.v15i4.5084.",
    "vattumilli": "P. K. Vattumilli, “Metadata-driven ETL pipelines: A framework for scalable data integration architecture,” *International Journal of Scientific Research in Computer Science, Engineering and Information Technology*, vol. 10, no. 6, pp. 1799–1807, 2024, doi: 10.32628/CSEIT241061224.",
    "gopaluni": "J. Gopaluni, “Metadata driven optimization of distributed ETL pipelines in cloud native data warehouses,” *International Journal of Computational and Experimental Science and Engineering*, vol. 11, no. 4, 2025, doi: 10.22399/ijcesen.4742.",
    "ananth": "V. Ananthakrishnan, “Governance frameworks for large-scale ETL ecosystems in complex data environments,” *Journal of Computer Science and Technology Studies*, vol. 8, no. 5, pp. 82–87, 2026, doi: 10.32996/jcsts.2026.8.5.5.",
    "male": "V. R. Male, “Decoding role-based access control (RBAC),” *International Journal of Scientific Research in Computer Science, Engineering and Information Technology*, vol. 11, no. 1, pp. 2082–2090, 2025, doi: 10.32628/CSEIT251112211.",
    "purwitasari": "A. Purwitasari, R. Permatasari, and A. B. Putra, “Implementasi role-based access control (RBAC) untuk keamanan sistem informasi penjualan perhiasan pada PostgreSQL di pgAdmin4 dan DBeaver,” *Jurnal SCRIPT*, vol. 13, no. 2, pp. 134–143, 2025, doi: 10.34151/script.v13i2.5464.",
    "tilung": "G. E. Tilung, N. Prastomo, and A. F. Reza, “Analysis and visualization of earthquake patterns (2021–2025) in the South Lebak region based on the dataset from Gugus Mitigasi Lebak Selatan,” in *Proc. 2025 8th International Conference on New Media Studies (CONMEDIA)*, 2025, pp. 163–170, doi: 10.1109/CONMEDIA67140.2025.11290328.",
    "wong": "R. F. Wong, S. A. Sanjaya, C. Darren, H. Yahya, and M. F. Riyadi, “Perancangan dasbor pra-bencana tsunami di Gugus Mitigasi Lebak Selatan: Visualisasi dan mitigasi di Panggarangan,” *G-Tech: Jurnal Teknologi Terapan*, vol. 8, no. 4, pp. 2241–2252, 2024, doi: 10.70609/gtech.v8i4.4763.",
    "pradipta": "R. A. Pradipta, P. B. Wintoro, and D. Budiyanto, “Perancangan pemodelan basis data sistem informasi secara konseptual dan logikal,” *Jurnal Informatika dan Teknik Elektro Terapan*, vol. 10, no. 2, 2022, doi: 10.23960/jitet.v10i2.2541.",
    "rahmawati": "T. Rahmawati, E. Y. Sari, A. T. Shakti, and A. N. Yomura, “Analisis perancangan database managemen sistem untuk sistem penunjang proses bisnis wedang uwuh instan,” *TEKNIMEDIA: Teknologi Informasi dan Multimedia*, vol. 4, no. 1, pp. 61–69, 2023, doi: 10.46764/teknimedia.v4i1.104.",
    "siregar": "M. F. Siregar, R. A. Adithia, R. Azizzah, and I. Ernawati, “Sistem informasi pemesanan makanan online,” *Jurnal Riset Sistem Informasi*, vol. 2, no. 4, pp. 13–19, 2025, doi: 10.69714/4t9nht72.",
    "kaptsov": "L. Kaptosv, “Applying PostGIS for storage and processing of geospatial data in logistics system,” *The American Journal of Engineering and Technology*, vol. 7, no. 8, pp. 318–327, 2025, doi: 10.37547/tajet/volume07issue08-28.",
    "kaptsov_api": "L. Kaptosv, “RESTful API design for geospatial logistics platforms using TypeScript and Laravel,” *Journal of Information, Technology and Policy*, pp. 1–13, 2025, doi: 10.62836/jitp.2025.515.",
    "papasani": "P. K. Papasani and R. T. Papasani, “PostGIS-powered proximity queries: Implementation and Google Maps visualization,” *PeerJ Computer Science*, vol. 11, Art. no. e3220, 2025, doi: 10.7717/peerj-cs.3220.",
    "tran": "K. H. Tran, M. Menenti, and L. Jia, “Surface water mapping and flood monitoring in the Mekong Delta using Sentinel-1 SAR time series and Otsu threshold,” *Remote Sensing*, vol. 14, no. 22, Art. no. 5721, 2022, doi: 10.3390/rs14225721.",
    "halder": "B. Halder *et al.*, “Large-scale flood hazard monitoring and impact assessment on landscape: Representative case study in India,” *Sustainability*, vol. 15, no. 14, Art. no. 11413, 2023, doi: 10.3390/su151411413.",
    "alonso": "F. Alonso-Sarria, C. Valdivieso-Ros, and G. Molina-Pérez, “Detecting flooded areas using Sentinel-1 SAR imagery,” *Remote Sensing*, vol. 17, no. 8, Art. no. 1368, 2025, doi: 10.3390/rs17081368.",
    "misra": "A. Misra, K. White, S. F. Nsutezo, W. Straka, and J. Lavista, “Mapping global floods with 10 years of satellite radar data,” *Nature Communications*, vol. 16, no. 1, Art. no. 5762, 2025, doi: 10.1038/s41467-025-60973-1.",
    "klein": "I. Klein, S. Uereyen, P. Sogno, A. Twele, A. Hirner, and C. Kuenzer, “Global WaterPack – The development of global surface water over the past 20 years at daily temporal resolution,” *Scientific Data*, vol. 11, no. 1, Art. no. 472, 2024, doi: 10.1038/s41597-024-03328-7.",
    "tang": "W. Tang *et al.*, “TRIMS LST: A daily 1 km all-weather land surface temperature dataset for China's landmass and surrounding areas (2000–2022),” *Earth System Science Data*, vol. 16, no. 1, pp. 387–419, 2024, doi: 10.5194/essd-16-387-2024.",
    "seyf": "K. Seyfullazadə, “Verilənlər bazası sistemləri [Database systems],” *Scientific Work*, no. 3 (Special Issue), pp. 119–121, 2025, doi: 10.36719/2663-4619/117/119-121.",
    "sholah": "M. N. A. Sholah, I. Sutrisno, A. Z. Arfianto, D. P. Riananda, M. K. Hasin, and B. Rahmat, “Implementasi checksum untuk keandalan data dalam pesan AIS untuk pengembangan sistem prediksi daerah penangkapan ikan,” *Jurnal 7 Samudra*, vol. 9, no. 2, pp. 61–68, 2024, doi: 10.54992/7samudra.v9i2.186.",
    "ramli": "A. Ramli and M. Y. Darus, “AI-ready ICT security for education: A holistic framework to strengthen data integrity at Malaysia's data centre,” *International Journal on e-Learning and Higher Education*, vol. 21, no. 1, pp. 121–139, 2026, doi: 10.24191/ijelhe.v21n1.2117.",
    "chanda": "D. Chanda, “Automated ETL pipelines for modern data warehousing: Architectures, challenges, and emerging solutions,” *The Eastasouth Journal of Information System and Computer Science*, vol. 1, no. 3, pp. 209–212, 2024, doi: 10.58812/esiscs.v1i03.523.",
    "gujjala": "P. K. R. Gujjala, “Optimizing ETL pipelines with Delta Lake and medallion architecture: A scalable approach for large-scale data,” *International Journal for Multidisciplinary Research*, vol. 6, no. 6, Art. no. 55445, 2024, doi: 10.36948/ijfmr.2024.v06i06.55445.",
    "maryani": "N. Maryani, M. Muchlish, R. Mulyadi, and N. Solehah, “Blockchain-based audit trails: Improving transparency and fraud detection in digital accounting systems,” *International Journal of Advanced Computer Science and Applications*, vol. 17, no. 1, 2026, doi: 10.14569/IJACSA.2026.0170162.",
    "alshamaa": "Z. M. Alshamaa and N. N. Saleem, “Black box software testing techniques: A literature review,” *Passer Journal of Basic and Applied Sciences*, vol. 7, no. 2, 2025, doi: 10.24271/psr.2025.508216.1963.",
    "maspupah": "A. Maspupah, “Literature review: Advantages and disadvantages of black box and white box testing methods,” *Jurnal Techno Nusa Mandiri*, vol. 21, no. 2, pp. 151–162, 2024, doi: 10.33480/techno.v21i2.5776.",
    "maric": "V. Marić, “Difference and application of white-box, black-box, and grey-box testing,” *International Journal of Innovative Solutions in Engineering*, vol. 2, no. 1, p. 39, 2026, doi: 10.47960/3029-3200.2026.2.1.39.",
    "salih": "Y. Salih and R. Saefullah, “Black box testing on website-based guestbook registration applications,” *International Journal of Mathematics, Statistics, and Computing*, vol. 2, no. 2, pp. 44–49, 2024, doi: 10.46336/ijmsc.v2i2.96.",
    "balsam": "S. Balsam and D. Mishra, “Web application testing—Challenges and opportunities,” *Journal of Systems and Software*, vol. 219, Art. no. 112186, 2025, doi: 10.1016/j.jss.2024.112186.",
    "skav": 'P. Skavantzos and S. Link, “Third and Boyce–Codd normal form for property graphs,” *The VLDB Journal*, vol. 34, no. 2, Art. no. 23, 2025, doi: 10.1007/s00778-025-00902-2.',
    "zhang": 'Z. Zhang and S. Link, “Synthesizing third normal form schemata that minimize integrity maintenance and update overheads: Parameterizing 3NF by the numbers of minimal keys and functional dependencies,” *Proceedings of the ACM on Management of Data*, vol. 3, no. 3, pp. 1–25, 2025, doi: 10.1145/3725362.',
    "huang": 'H. Huang, B. Shen, L. Zhong, and Y. Zhou, “Protecting data integrity of web applications with database constraints inferred from application code,” in *Proc. 28th ACM International Conference on Architectural Support for Programming Languages and Operating Systems (ASPLOS), Vol. 2*, 2023, pp. 632–645, doi: 10.1145/3575693.3575699.',
    "kanwal": 'S. Kanwal, N. R. Chaudhry, R. Choudhary, Y. A. Shaik, P. Yadav, and A. Rashid, “Foreign key constraints to maintain referential integrity in distributed database in microservices architecture,” *International Journal of Advanced Computer Science and Applications*, vol. 16, no. 6, 2025, doi: 10.14569/IJACSA.2025.0160696.',
    "efendi": 'Y. Efendi, S. Sodikin, and R. Haryanto, “Perancangan dan implementasi system incremental backup database PostgreSQL menggunakan aplikasi Barman di PT. ROF,” *Jurnal Minfo Polgan*, vol. 12, no. 1, pp. 958–965, 2023, doi: 10.33395/jmp.v12i1.12539.',
    "ahmad": 'M. S. Ahmad and B. N. Panda, “ClusteredLog: Optimizing log structures for efficient data recovery and integrity management in database systems,” *Electronics*, vol. 13, no. 23, Art. no. 4723, 2024, doi: 10.3390/electronics13234723.',
    "syaddam": 'Syaddam, M. Yusril, A. J. J. Kawuta, S. D. Banni, and Y. S. Ratu, “Desain model relational database perpustakaan SMP Negeri 13 Tarakan menggunakan metode Database Life Cycle,” *Jurnal Terapan Teknologi Informasi*, vol. 9, no. 1, pp. 1–10, 2025, doi: 10.21460/jutei.2025.91.398.',
    "trihap": 'D. Trihapningsari and M. A. Putri, “Perancangan basis data sistem reservasi wisma Universitas Terbuka dengan metode Database Life Cycle,” *Jurnal Teknologi Sistem Informasi dan Aplikasi*, vol. 7, no. 4, pp. 1638–1646, 2024, doi: 10.32493/jtsi.v7i4.45421.',
    "esiefa": 'B. M. Esiefarienrhe and T. J. Moemi, “UML design of business intelligence system for small-scale enterprises,” *Journal of Information Systems and Informatics*, vol. 6, no. 1, pp. 495–513, 2024, doi: 10.51519/journalisi.v6i1.672.',
    "alyami": 'A. Alyami, S. F. Pileggi, O. Sohaib, and I. Hawryszkiewycz, “Seamless transformation from use case to sequence diagrams,” *PeerJ Computer Science*, vol. 9, Art. no. e1444, 2023, doi: 10.7717/peerj-cs.1444.',
    "bmkg_sumsel": 'Stasiun Klimatologi Kelas I Sumatera Selatan, Badan Meteorologi, Klimatologi, dan Geofisika, “Buletin Iklim Edisi Desember 2024: Analisis hujan November 2024 dan prediksi hujan Januari, Februari, dan Maret 2025 di Sumatera Selatan,” Palembang, Indonesia, Des. 2024. [Online]. Available: https://staklim-sumsel.bmkg.go.id/wp-content/uploads/2023/09/BULETIN-BMKG-EDISI-DESEMBER-2024.pdf',
    "bmkg_kalsel": 'Stasiun Klimatologi Kalimantan Selatan, Badan Meteorologi, Klimatologi, dan Geofisika, “Peringatan dini cuaca dan iklim Provinsi Kalimantan Selatan periode Dasarian III Maret 2026,” Surat No. e.T/ME.01.02/073/KBB3/III/2026, 21 Mar. 2026. [Online]. Available: https://staklim-kalsel.bmkg.go.id/wp-content/uploads/2026/03/Kalsel-Dasarian-III-Maret-2026-TTE-1_signed.pdf',
    "perban": 'Badan Meteorologi, Klimatologi, dan Geofisika, *Peraturan Badan Meteorologi, Klimatologi, dan Geofisika Nomor 9 Tahun 2022 tentang Penyediaan dan Penyebarluasan Peringatan Dini Cuaca Ekstrem*, Berita Negara Republik Indonesia Tahun 2022 Nomor 891, 2022.',
    "nascimento": "R. B. Nascimento, E. P. Teixeira, O. P. de Lima, M. R. Maduro, and V. C. da Silva, “Process mapping: A case study in the contract sector of the Public Defender's office in the state of Amazonas,” *ITEGAM-Journal of Engineering and Technology for Industrial Applications*, vol. 9, no. 44, 2023, doi: 10.5935/jetia.v9i44.1012.",
    "codab": "OCHA Field Information Services Section (FISS), “Indonesia – Subnational administrative boundaries (COD-AB),” Humanitarian Data Exchange, sumber data: Badan Pusat Statistik, lisensi CC BY-IGO, 2025. [Online]. Available: https://data.humdata.org/dataset/cod-ab-idn",
}

ORDER = []  # kunci menurut urutan kemunculan pertama


def cite(m):
    nums = []
    for key in re.findall(r"@([\w]+)", m.group(1)):
        if key not in REF:
            raise KeyError(key)
        if key not in ORDER:
            ORDER.append(key)
        nums.append(ORDER.index(key) + 1)
    return ", ".join(f"[{n}]" for n in nums)


# =====================================================================================================
# Pembangun XML
# =====================================================================================================
FONT = '<w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:cs="Times New Roman"/>'


def runs(text, size=24, bold=False):
    text = re.sub(r"\[(@[^\]]+)\]", cite, text)
    out = []
    for tok in re.split(r"(\*\*.+?\*\*|\*.+?\*|<<.+?>>)", text):
        if not tok:
            continue
        rpr, t = "", tok
        if tok.startswith("**"):
            rpr, t = "<w:b/><w:bCs/>", tok[2:-2]
        elif tok.startswith("*"):
            rpr, t = "<w:i/><w:iCs/>", tok[1:-1]
        elif tok.startswith("<<"):
            rpr, t = '<w:highlight w:val="yellow"/>', "[" + tok[2:-2] + "]"
        if bold:
            rpr = "<w:b/><w:bCs/>" + rpr
        out.append(f'<w:r><w:rPr>{FONT}{rpr}<w:sz w:val="{size}"/><w:szCs w:val="{size}"/></w:rPr>'
                   f'<w:t xml:space="preserve">{escape(t)}</w:t></w:r>')
    return "".join(out)


def para(text):
    return ('<w:p><w:pPr><w:spacing w:after="0" w:line="360" w:lineRule="auto"/>'
            '<w:ind w:firstLine="567"/><w:jc w:val="both"/></w:pPr>' + runs(text) + "</w:p>")


NUM_NEXT = [201]
NUM_IDS = []


def new_list():
    NUM_NEXT[0] += 1
    NUM_IDS.append(NUM_NEXT[0])
    return NUM_NEXT[0]


def items(texts):
    nid = new_list()
    return "".join(
        '<w:p><w:pPr><w:pStyle w:val="ListParagraph"/>'
        f'<w:numPr><w:ilvl w:val="0"/><w:numId w:val="{nid}"/></w:numPr>'
        '<w:spacing w:after="0" w:line="360" w:lineRule="auto"/><w:ind w:left="567" w:hanging="425"/>'
        '<w:contextualSpacing w:val="0"/><w:jc w:val="both"/></w:pPr>' + runs(t) + "</w:p>" for t in texts)


HEAD = {
    2: ('<w:pPr><w:pStyle w:val="Heading2"/><w:keepNext/><w:numPr><w:ilvl w:val="0"/><w:numId w:val="{nid}"/></w:numPr>'
        '<w:spacing w:before="120" w:line="360" w:lineRule="auto"/><w:jc w:val="both"/><w:rPr><w:b/></w:rPr></w:pPr>'),
    3: ('<w:pPr><w:pStyle w:val="Heading3"/><w:keepNext/><w:numPr><w:ilvl w:val="1"/><w:numId w:val="{nid}"/></w:numPr>'
        '<w:spacing w:before="120" w:line="360" w:lineRule="auto"/><w:ind w:left="709" w:hanging="709"/>'
        '<w:jc w:val="both"/><w:rPr><w:b/></w:rPr></w:pPr>'),
}
HEAD[4] = ('<w:pPr><w:pStyle w:val="Heading4"/><w:keepNext/><w:numPr><w:ilvl w:val="2"/><w:numId w:val="{nid}"/></w:numPr>'
           '<w:spacing w:before="120" w:line="360" w:lineRule="auto"/><w:ind w:left="851" w:hanging="851"/>'
           '<w:jc w:val="both"/><w:rPr><w:b/><w:i w:val="0"/></w:rPr></w:pPr>')
CHAPTER_NUMID = {2: 10, 3: 12, 4: 13}  # numbering bawaan template: "2.%1"/"2.%1.%2" dan "3.%1"/"3.%1.%2"


def head(level, text, chapter):
    return "<w:p>" + HEAD[level].format(nid=CHAPTER_NUMID[chapter]) + runs(text, bold=True) + "</w:p>"


def caption(kind, chapter, n, title):
    rp = f'<w:rPr>{FONT}<w:sz w:val="22"/><w:szCs w:val="22"/></w:rPr>'
    reset = r" \r 1" if n == 1 else ""
    fld = (f'<w:r>{rp}<w:fldChar w:fldCharType="begin"/></w:r>'
           f'<w:r>{rp}<w:instrText xml:space="preserve"> SEQ {kind} \\* ARABIC{reset} </w:instrText></w:r>'
           f'<w:r>{rp}<w:fldChar w:fldCharType="separate"/></w:r><w:r>{rp}<w:t>{n}</w:t></w:r>'
           f'<w:r>{rp}<w:fldChar w:fldCharType="end"/></w:r>')
    keep = '<w:keepNext/>' if kind == "Tabel" else ""
    return (f'<w:p><w:pPr><w:pStyle w:val="Caption"/>{keep}<w:spacing w:before="120" w:after="120"/>'
            f'<w:jc w:val="center"/></w:pPr>'
            f'<w:r>{rp}<w:t xml:space="preserve">{kind} {chapter}.</w:t></w:r>{fld}'
            f'<w:r>{rp}<w:t xml:space="preserve"> {escape(title)}</w:t></w:r></w:p>')


def table(widths, header, rows, size=20):
    total = sum(widths)
    grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in widths)

    def cell(text, w, hdr):
        shade = '<w:shd w:val="clear" w:color="auto" w:fill="D9E2F3"/>' if hdr else ""
        paras = "".join(
            f'<w:p><w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/>'
            f'<w:jc w:val="{"center" if hdr else "left"}"/></w:pPr>{runs(t, size=size, bold=hdr)}</w:p>'
            for t in text.split("\n"))
        return f'<w:tc><w:tcPr><w:tcW w:w="{w}" w:type="dxa"/>{shade}</w:tcPr>{paras}</w:tc>'

    def row(cells, hdr=False):
        trpr = '<w:trPr><w:tblHeader/><w:cantSplit/></w:trPr>' if hdr else '<w:trPr><w:cantSplit/></w:trPr>'
        return "<w:tr>" + trpr + "".join(cell(c, w, hdr) for c, w in zip(cells, widths)) + "</w:tr>"

    return (f'<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/><w:tblW w:w="{total}" w:type="dxa"/>'
            '<w:jc w:val="center"/><w:tblLayout w:type="fixed"/>'
            '<w:tblCellMar><w:left w:w="85" w:type="dxa"/><w:right w:w="85" w:type="dxa"/></w:tblCellMar>'
            '<w:tblLook w:val="04A0" w:firstRow="1" w:lastRow="0" w:firstColumn="1" w:lastColumn="0" w:noHBand="0" w:noVBand="1"/>'
            f'</w:tblPr><w:tblGrid>{grid}</w:tblGrid>' + row(header, True) + "".join(row(r) for r in rows)
            + '</w:tbl><w:p><w:pPr><w:spacing w:after="0"/></w:pPr></w:p>')


IMAGES = []  # (rid, nama berkas)
VIS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "naskah", "visualisasi")


def sumber(text):
    return ('<w:p><w:pPr><w:spacing w:before="0" w:after="200"/><w:jc w:val="center"/></w:pPr>'
            + runs("Sumber: " + text, size=20) + "</w:p>")


def gambar_rujukan(file, bab, n, judul, src, width=14.0):
    return figure(os.path.join(VIS, file), width) + caption("Gambar", bab, n, judul) + sumber(src)


def figure(path, width_cm):
    from PIL import Image
    w, h = Image.open(path).size
    cx = int(min(width_cm, 14.0) * 360000)
    cy = int(cx * h / w)
    idx = len(IMAGES) + 1
    rid = f"rIdSk{idx}"
    name = f"skripsi_{idx}_{os.path.basename(path)}"
    IMAGES.append((rid, name, path))
    return ('<w:p><w:pPr><w:keepNext/><w:spacing w:before="120" w:after="0"/><w:jc w:val="center"/></w:pPr><w:r><w:drawing>'
            f'<wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{cx}" cy="{cy}"/>'
            f'<wp:docPr id="{9000 + idx}" name="Gambar Skripsi {idx}"/>'
            '<wp:cNvGraphicFramePr><a:graphicFrameLocks xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" noChangeAspect="1"/></wp:cNvGraphicFramePr>'
            '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
            '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            '<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            f'<pic:nvPicPr><pic:cNvPr id="{9000 + idx}" name="{name}"/><pic:cNvPicPr/></pic:nvPicPr>'
            f'<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
            f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic></a:graphicData></a:graphic>'
            '</wp:inline></w:drawing></w:r></w:p>')


# =====================================================================================================
# BAB I
# =====================================================================================================
def bab1():
    out = {}
    latar = [
        "Pengelolaan bencana semakin bergantung pada data. Tinjauan sistematis Khan dkk. [@khan] terhadap sistem "
        "manajemen bencana, khususnya banjir, menunjukkan bahwa infrastruktur penyimpanan dan pengolahan data, "
        "jaringan sensor, penginderaan jauh, serta sistem informasi geografis (SIG) mendukung pengambilan "
        "keputusan. Sistem basis data sendiri berperan menjamin ketepatan waktu, akurasi, dan keandalan data dalam "
        "pengelolaan informasi, serta memegang peran penting dalam manajemen krisis dan tanggap darurat di sektor "
        "pemerintahan dan layanan publik [@deng]. Sebaliknya, sistem pengelolaan data yang tidak memadai menjadi "
        "salah satu penghambat pemanfaatan teknologi digital untuk manajemen bencana [@wang].",

        "Hambatan tersebut juga terlihat di Indonesia. Pulau Jawa, yang dihuni sekitar 152 juta jiwa, mengalami "
        "peningkatan frekuensi banjir rata-rata 13,18% per tahun sejak 2012, sementara keterbatasan penyimpanan dan "
        "pengelolaan data menyebabkan sebagian wilayah tidak memiliki data yang memadai untuk pemodelan banjir "
        "[@shafiya]. Pada daerah aliran sungai yang tidak memiliki atau jarang memiliki pos hujan, data presipitasi "
        "satelit seperti GPM IMERG menjadi solusi yang layak, dan di Indonesia akurasinya terbukti melampaui produk "
        "satelit lain seperti TRMM [@hidayah]. Hasil pemodelan banjir skala Pulau Jawa pada Gambar 1.1 "
        "memperlihatkan bahwa kedalaman genangan dan debit sungai berubah sepanjang tahun dan memuncak pada bulan "
        "basah, sehingga kondisi hidrometeorologi perlu dipantau dan disimpan secara berkala, bukan hanya saat "
        "kejadian [@shafiya].",
        "@FIG1",

        "Akses terhadap data satelit juga semakin terbuka. Copernicus Data Space Ecosystem (CDSE), platform data "
        "resmi Program Copernicus, menyediakan akses citra satelit melalui *Application Programming Interface* (API) "
        "dan pemrosesan berbasis awan [@kovacs]. Meskipun demikian, setiap sensor memiliki keterbatasan. Radar "
        "Sentinel-1 berpotensi mengamati rata-rata 58% kejadian banjir di Eropa, jauh di atas satelit optik "
        "Sentinel-2 yang hanya 28% karena tutupan awan, tetapi pemetaan genangan dari kedua satelit tersebut sering "
        "kali tetap parsial atau terlewat karena banjir berlangsung beberapa jam hingga beberapa hari [@tarpanelli]. "
        "MODIS pada satelit Terra dan Aqua telah menyediakan data selama lebih dari dua puluh tahun [@roman]. GPM "
        "IMERG menyediakan data hujan harian yang konsisten dengan pos hujan pada resolusi 0,1° [@zhu], tetapi "
        "kurang presisi pada skala harian untuk mitigasi banjir bandang dan cenderung meremehkan hujan ekstrem "
        "[@ansori]. Karena setiap sumber memiliki keterbatasan, pemantauan yang hanya mengandalkan satu sumber data "
        "berisiko kehilangan informasi.",

        "Pemanfaatan beberapa sumber satelit sekaligus telah terbukti memberikan gambaran yang lebih lengkap. "
        "Liu dkk. [@liu] menggabungkan beberapa data satelit, antara lain GPM, SAR, dan MODIS, dengan data muka air "
        "lapangan untuk mengidentifikasi kekeringan ekstrem tahun 2022 di Daerah Aliran Sungai Poyang. "
        "Castro-Melgar dkk. [@castro] memadukan citra radar Sentinel-1 dengan citra optik Sentinel-2 dan Landsat 8 "
        "serta data kependudukan, sehingga dapat mengidentifikasi genangan seluas sekitar 199 km² yang berdampak "
        "langsung pada lebih dari 90.000 penduduk Valencia.",

        "Penggabungan data dari banyak sumber tidak sederhana. Data Sentinel-1 Level-1 masih mengandung distorsi "
        "radiometrik dan geometrik sehingga harus dikoreksi sebelum dapat dianalisis [@weiss], dan pembentukan "
        "*analysis-ready data* dari produk tingkat rendah masih memerlukan upaya dan infrastruktur yang besar "
        "[@upadhyay]. Pada tingkat pengambilan keputusan, ketiadaan basis data geospasial yang terintegrasi "
        "menghambat pengambilan keputusan antarpemangku kepentingan, sedangkan basis data geospasial terintegrasi "
        "direkomendasikan karena dapat mengurangi duplikasi dan mempercepat pengambilan keputusan pemerintah [@dev].",

        "Integrasi data juga perlu disertai tata kelola. *Pipeline Extract, Transform, Load* (ETL) berbasis "
        "metadata mengurangi beban pengembangan dan mendukung pengelolaan kualitas data yang konsisten "
        "[@vattumilli]. Pendekatan ini menempatkan aturan transformasi, *lineage*, dan kebijakan tata kelola sebagai "
        "metadata terstruktur sehingga asal-usul data dapat dilacak [@gopaluni], sedangkan pengelolaan metadata "
        "yang terpusat dan pemantauan proses ETL diperlukan untuk menjaga keandalan dan akuntabilitas data "
        "[@ananth]. Ketika data digunakan oleh pihak dengan tugas yang berbeda, *Role-Based Access Control* (RBAC) "
        "memberikan hak akses berdasarkan peran dengan prinsip hak minimum (*least privilege*) [@male]. Pada tingkat "
        "basis data, penerapan RBAC melalui perintah GRANT dan REVOKE di PostgreSQL terbukti membatasi setiap peran "
        "hanya pada data yang menjadi haknya [@purwitasari].",

        "Kebutuhan tersebut relevan bagi Gugus Mitigasi Lebak Selatan (GMLS), komunitas mitigasi bencana di "
        "Kabupaten Lebak, Banten. Penelitian terdahulu di GMLS telah menganalisis dan memvisualisasikan dataset "
        "gempa bumi resmi GMLS periode April 2021 hingga April 2025 [@tilung], serta merancang dasbor pra-bencana "
        "tsunami untuk Panggarangan [@wong]. Kedua penelitian tersebut berfokus pada bahaya geologi. Wawancara "
        "dengan Ketua GMLS pada 16 Oktober 2026 menunjukkan bahwa perhatian GMLS mencakup semua jenis bencana, "
        "termasuk banjir bagi warga di dekat sungai serta banjir bandang dan tanah longsor akibat hujan lebat. "
        "Informasi cuaca saat ini diterima dari BMKG melalui aplikasi Are You In Sys dan, menurut narasumber, baru "
        "menunjukkan area yang berpotensi hujan dan banjir, belum spesifik ke lokasi warga. GMLS juga tidak mencatat "
        "kejadian bencana sendiri dan merujuk pada data pemerintah, yang menurut penilaian narasumber belum rapi. "
        "Dengan kondisi tersebut, GMLS belum memiliki data hidrometeorologi per wilayah yang tersimpan dan dapat "
        "ditelusuri asal-usulnya.",

        "Dari penelitian yang ditinjau, pemanfaatan data multi-sensor [@liu,@castro] berfokus pada analisis satu "
        "kejadian tertentu, perancangan basis data geospasial terintegrasi [@dev] diterapkan pada analisis tata "
        "guna lahan, penerapan RBAC di PostgreSQL [@purwitasari] dilakukan pada sistem informasi penjualan, dan "
        "penelitian di GMLS [@tilung,@wong] berfokus pada gempa bumi dan tsunami. Belum ditemukan penelitian yang "
        "merancang basis data untuk mengelola data hidrometeorologi dari beberapa satelit secara berkelanjutan per "
        "wilayah administrasi, lengkap dengan pencatatan asal-usul data dan kontrol akses berbasis peran, bagi "
        "komunitas mitigasi bencana di Lebak Selatan.",

        "Berdasarkan kondisi tersebut, penelitian ini merancang dan mengimplementasikan sistem basis data "
        "pemantauan hidrometeorologi bagi GMLS yang mengintegrasikan data Sentinel-1, MODIS, dan GPM IMERG. "
        "Perancangan menggunakan metode *Database System Development Life Cycle* (DBSDLC), yang mencakup fase "
        "perancangan basis data untuk menghasilkan struktur basis data yang sesuai dengan kebutuhan pengguna "
        "[@pradipta]. Sistem hasil penelitian ini diberi nama Orbit-U: The Monitor, dan rincian rancangannya "
        "dibahas pada BAB IV.",
    ]
    out["_Toc207196473"] = "".join(
        gambar_rujukan("V1_shafiya2025_debit_sungai_jawa.png", 1, 1, "Peta Kedalaman Genangan dan Debit Sungai di Pulau Jawa Tahun 2014", "Shafiya dkk. [@shafiya]")
        if t == "@FIG1" else para(t) for t in latar)
    out["_Toc207196474"] = para("Berdasarkan latar belakang tersebut, rumusan masalah penelitian ini adalah sebagai berikut.") + items([
        "Bagaimana merancang basis data relasional spasial yang mengintegrasikan data hidrometeorologi dari "
        "Sentinel-1, MODIS, dan GPM IMERG, yang berbeda format, resolusi, dan frekuensi, ke dalam satu unit analisis "
        "wilayah?",
        "Bagaimana rancangan basis data dapat menjamin ketertelusuran asal-usul (*lineage*) dan kualitas data pada "
        "setiap tahap pengolahan?",
        "Bagaimana rancangan basis data dapat menyajikan informasi hidrometeorologi per kecamatan yang dapat "
        "dimanfaatkan GMLS untuk pemantauan kondisi wilayah dan pencatatan kejadian bencana?",
        "Bagaimana menerapkan kontrol akses berbasis peran dan jejak audit yang ditegakkan pada tingkat basis data?",
    ])
    out["_Toc207196475"] = para("Agar penelitian tetap berfokus pada perancangan dan implementasi basis data, batasan "
                                "masalah ditetapkan sebagai berikut.") + items([
        "Wilayah kajian adalah sepuluh kecamatan cakupan kerja GMLS di Kabupaten Lebak, Provinsi Banten, yaitu "
        "Banjarsari, Bayah, Cibeber, Cigemblong, Cihara, Cijaku, Cilograng, Malingping, Panggarangan, dan "
        "Wanasalam, dengan batas administrasi bersumber dari data COD-AB tingkat kecamatan [@codab]. Desa hanya dicatat "
        "sebagai keterangan pada catatan kejadian bencana.",
        "Data satelit hanya diambil dari layanan resmi penyedia, yaitu Sentinel-1 dari Copernicus Data Space "
        "Ecosystem, MODIS Terra dan Aqua dari NASA LANCE dan LAADS DAAC, serta GPM IMERG dari NASA GES DISC.",
        "Nilai per kecamatan disimpan tanpa batas waktu; pada saat penelitian, data yang tersimpan mencakup 1 Januari "
        "2024 hingga 22 Oktober 2026. Berkas citra (raster) disimpan selama satu tahun bergulir di luar basis data, dan "
        "basis data hanya menyimpan metadata, lokasi berkas, dan *checksum* berkas citra tersebut.",
        "Bencana yang dicakup adalah bencana hidrometeorologi, yaitu banjir, banjir bandang, tanah longsor, dan "
        "kekeringan. Peringatan otomatis dibangkitkan dari aturan ambang curah hujan yang disimpan di basis data, "
        "sedangkan kekeringan hanya ditampilkan sebagai indikator. Gempa bumi, tsunami, gelombang tinggi, dan banjir "
        "rob tidak termasuk dalam cakupan.",
        "Sistem berfungsi sebagai sarana pemantauan harian dan arsip, bukan sistem deteksi banjir waktu nyata. "
        "Peringatan yang dihasilkan bersifat informasi bagi GMLS, bukan peringatan dini resmi atau penetapan status "
        "bencana. Prakiraan 15 hari yang tersedia di aplikasi merupakan proyeksi statistik deret waktu dan tidak "
        "menjadi fokus penelitian.",
        "Kejadian bencana dicatat oleh Analis beserta sumber informasinya, terutama data pemerintah (BPBD Lebak dan "
        "BNPB), dan status verifikasinya; hanya kejadian terverifikasi yang dipakai untuk menilai peringatan. Data "
        "kependudukan, titik evakuasi, dan kawasan rawan bencana tetap dikelola aplikasi SIGAP DESA dan tidak "
        "diintegrasikan.",
        "Aplikasi web dan REST API dibangun sebagai prototipe untuk mengakses basis data. Pemberitahuan hanya dikirim "
        "melalui surel; aplikasi seluler serta notifikasi melalui SMS atau WhatsApp tidak termasuk karena layanan "
        "pengiriman pesan ke ponsel memerlukan biaya berlangganan atau biaya per pesan yang berada di luar anggaran "
        "penelitian.",
        "Evaluasi dibatasi pada enam kriteria evaluasi minimum jalur *Design and Implementation*, yaitu tinjauan "
        "kebutuhan oleh pengguna (*requirement/user review*), integritas, fungsional, keamanan, kueri, serta "
        "pencadangan dan pemulihan (*backup/recovery*). Uji coba aplikasi oleh pengguna dilakukan sebagai "
        "pelengkap evaluasi fungsional.",
    ])
    out["_Toc207196477"] = para("Sesuai rumusan masalah, tujuan penelitian ini adalah sebagai berikut.") + items([
        "Menghasilkan rancangan basis data relasional spasial yang mengintegrasikan data Sentinel-1, MODIS, dan GPM "
        "IMERG ke dalam satu unit analisis wilayah kecamatan.",
        "Menghasilkan rancangan basis data yang mencatat asal-usul dan kualitas setiap produk data pada setiap tahap "
        "pengolahan.",
        "Menyajikan informasi hidrometeorologi per kecamatan dari basis data dalam bentuk yang dapat digunakan GMLS "
        "untuk pemantauan kondisi wilayah dan pencatatan kejadian bencana.",
        "Menerapkan kontrol akses berbasis peran dan jejak audit yang ditegakkan pada tingkat basis data.",
    ])
    out["_Toc207196478"] = (
        para("Manfaat penelitian ini terbagi menjadi manfaat akademis dan manfaat praktis.")
        + para("Secara akademis, penelitian ini memberikan contoh penerapan DBSDLC pada data geospasial dari beberapa "
               "satelit, termasuk penerapan pencatatan asal-usul data dan kontrol akses berbasis peran pada tingkat "
               "basis data untuk data kebencanaan.")
        + para("Secara praktis, penelitian ini memberikan manfaat sebagai berikut.") + items([
            "Bagi GMLS, tersedia satu sumber data hidrometeorologi per kecamatan yang terpusat dan dapat ditelusuri "
            "asal-usulnya, melengkapi visualisasi gempa bumi dan dasbor tsunami yang telah ada.",
            "Bagi relawan dan pengurus GMLS, kondisi hujan per kecamatan dan peringatan dapat diperoleh melalui web dan "
            "surel tanpa perlu mengolah data satelit sendiri.",
            "Bagi wilayah lain, cakupan wilayah disimpan sebagai data, bukan ditanamkan di dalam kode program, sehingga "
            "rancangan basis data dapat diadaptasi untuk wilayah yang berbeda.",
        ]))
    out["_Toc207196479"] = para("Laporan skripsi ini disusun dengan sistematika sebagai berikut.") + items([
        "BAB I PENDAHULUAN menguraikan latar belakang, rumusan masalah, batasan masalah, tujuan dan manfaat "
        "penelitian, serta sistematika penulisan.",
        "BAB II LANDASAN TEORI menyajikan penelitian terdahulu, teori yang mendasari perancangan dan implementasi "
        "basis data, kerangka DBSDLC dan UML, serta perangkat lunak yang digunakan.",
        "BAB III METODOLOGI PENELITIAN menguraikan gambaran umum objek penelitian, alur penelitian berdasarkan DBSDLC, "
        "teknik pengumpulan data, dan teknik analisis data.",
        "BAB IV ANALISIS DAN HASIL PENELITIAN menguraikan hasil setiap tahap DBSDLC, mulai dari analisis sistem "
        "berjalan dan kebutuhan pengguna, pemodelan sistem, perancangan basis data konseptual dan logikal, pemilihan "
        "DBMS, perancangan fisik, perancangan antarmuka, implementasi, pemuatan data, dan *prototyping*, hingga hasil "
        "evaluasi dan pembahasannya terhadap rumusan masalah.",
        "BAB V SIMPULAN DAN SARAN merangkum jawaban atas rumusan masalah dan memberikan saran bagi pengembangan sistem "
        "serta penelitian selanjutnya.",
    ])
    return out


# =====================================================================================================
# BAB II
# =====================================================================================================
def bab2():
    h2 = lambda t: head(2, t, 2)
    h3 = lambda t: head(3, t, 2)
    x = []
    x.append(h2("Penelitian Terdahulu"))
    x.append(para(
        "Penelitian terdahulu yang ditinjau dikelompokkan ke dalam empat kelompok, yaitu perancangan basis data "
        "dengan DBSDLC, basis data spasial dan keamanan basis data, pemanfaatan data satelit untuk pemantauan "
        "bencana, serta penelitian yang melibatkan GMLS. Ringkasannya disajikan pada Tabel 2.1."))
    x.append(caption("Tabel", 2, 1, "Ringkasan Penelitian Terdahulu"))
    x.append(table([400, 1500, 2150, 2150, 1700], ["No", "Peneliti", "Objek dan Metode", "Hasil", "Keterkaitan"], [
        ["1", "Pradipta dkk. (2022) [@pradipta]", "Basis data sistem informasi berbasis web; fase *database design* DBSDLC",
         "Model basis data konseptual dan logikal yang siap diterapkan pada fase implementasi",
         "Penelitian ini melanjutkan hingga perancangan fisik dan implementasi"],
        ["2", "Rahmawati dkk. (2023) [@rahmawati]", "Sistem penunjang bisnis wedang uwuh instan; desain konseptual, logis, dan fisik DBSDLC",
         "Model perancangan sistem pemasaran dan pemesanan daring", "Tiga fase perancangan DBSDLC pada domain bisnis"],
        ["3", "Siregar dkk. (2025) [@siregar]", "Sistem pemesanan makanan daring; DBSDLC: perencanaan, studi literatur, perancangan",
         "ERD konseptual dengan kunci primer dan kandidat, lalu model logikal yang divalidasi; mencatat bahwa penelitian sebelumnya lebih berfokus pada antarmuka daripada basis data",
         "Menegaskan perancangan basis data sebagai fokus"],
        ["4", "Dev dkk. (2023) [@dev]", "Basis data geospasial terintegrasi Manesar, India; wawancara pemangku kepentingan dan citra Landsat 1987–2022",
         "Basis data terintegrasi direkomendasikan untuk mengurangi duplikasi dan mempercepat keputusan pemerintah",
         "Basis data geospasial untuk pemerintah lokal, domain tata guna lahan"],
        ["5", "Kaptosv (2025) [@kaptsov]", "Routing logistik; PostgreSQL 15, PostGIS 3.3, dan pgRouting dibandingkan dengan MySQL",
         "Pada 10.000 titik, rata-rata waktu kueri 6,5 detik (PostGIS) dan 58,9 detik (MySQL)",
         "Pembanding PostGIS dan MySQL untuk tahap DBMS Selection"],
        ["6", "Papasani dan Papasani (2025) [@papasani]", "Kueri kedekatan dengan ST_DWithin dan indeks spasial; 108 lokasi toko di Texas",
         "Indeks spasial mempercepat kueri 19–24 kali dan skalabel hingga 1.000.000 lokasi", "Peran indeks spasial pada kinerja kueri"],
        ["7", "Wang dkk. (2025) [@wang]", "Platform Digital CPEC (Python, PostgreSQL, MapServer) untuk berbagi data bencana",
         "Standar manajemen bencana, kerangka integrasi data, serta 18 indikator metadata dan 38 *identifier* untuk kualitas data",
         "Platform data bencana di atas PostgreSQL dengan metadata"],
        ["8", "Purwitasari dkk. (2025) [@purwitasari]", "RBAC pada sistem penjualan perhiasan di PostgreSQL; empat *role*, GRANT dan REVOKE",
         "Validasi *privilege* berhasil 100%; akses tidak sah ditolak DBMS", "Kontrol akses di tingkat basis data"],
        ["9", "Castro-Melgar dkk. (2025) [@castro]", "Banjir Valencia 2024; Sentinel-1, Sentinel-2, Landsat 8, dan data sosial ekonomi",
         "Genangan sekitar 199 km² berdampak pada lebih dari 90.000 penduduk", "Integrasi multi-sensor untuk satu kejadian"],
        ["10", "Tran dkk. (2022) [@tran]", "Delta Mekong; deret waktu Sentinel-1 VH, ambang Otsu, deteksi perubahan",
         "Peta air permukaan di area sungai dengan R² = 0,97; peta banjir mendekati waktu nyata",
         "Pemetaan air dari polarisasi VH dan perbandingan dengan pengamatan sebelumnya"],
        ["11", "Tilung dkk. (2025) [@tilung]", "Dataset gempa GMLS April 2021–April 2025; analisis dan visualisasi",
         "Gempa dangkal bermagnitudo kecil mendominasi; visualisasi terintegrasi ke platform GMLS", "Mitra yang sama, fokus bahaya geologi"],
        ["12", "Wong dkk. (2024) [@wong]", "Dasbor pra-bencana tsunami Panggarangan; metodologi *prototype*, Tableau, SUS",
         "Rancangan dasbor untuk meningkatkan sinergi antarpemangku kepentingan", "Mitra yang sama, fokus tsunami"],
    ]))
    x.append(para(
        "Tabel 2.1 menunjukkan tiga hal. Pertama, penerapan DBSDLC [@pradipta,@rahmawati,@siregar] dilakukan pada "
        "domain bisnis dengan data transaksional, bukan data geospasial dari satelit. Kedua, keunggulan PostGIS "
        "dan indeks spasial [@kaptsov,@papasani] serta RBAC di PostgreSQL [@purwitasari] dibuktikan pada domain "
        "logistik, layanan lokasi, dan penjualan, sedangkan basis data geospasial terintegrasi [@dev] diterapkan pada "
        "tata guna lahan. Ketiga, penelitian multi-sensor [@castro,@tran] berfokus pada pemetaan kejadian, dan "
        "penelitian bersama GMLS [@tilung,@wong] berfokus pada bahaya geologi. Penelitian ini menggabungkan ketiga "
        "kelompok tersebut dengan menerapkan DBSDLC pada data hidrometeorologi multi-satelit, termasuk basis data "
        "spasial, pencatatan asal-usul data, dan kontrol akses berbasis peran."))

    x.append(h2("Teori yang Berkaitan"))
    x.append(h3("Pemantauan Bencana Hidrometeorologi Berbasis Satelit"))
    x.append(para(
        "Perubahan iklim dan aktivitas manusia merupakan faktor utama yang berkontribusi terhadap berbagai bahaya "
        "alam seperti banjir, tanah longsor, dan kekeringan [@halder]. Penginderaan jauh merupakan alat yang bernilai "
        "bagi manajemen bencana karena menyediakan data geografis dalam berbagai situasi, sedangkan SIG dan "
        "manajemen data spasial dipakai untuk memvisualisasikan dan menganalisis data spasial saat banjir [@khan]. "
        "Sebagai contoh, Halder dkk. memanfaatkan data Sentinel-1 GRD sebelum dan sesudah banjir serta citra Landsat "
        "8–9 untuk memetakan genangan banjir Assam tahun 2022 [@halder]."))
    x.append(para(
        "Curah hujan berkaitan erat dengan luas genangan. Alonso-Sarria dkk. menemukan hubungan yang jelas antara "
        "luas area tergenang dan metrik curah hujan, dengan koefisien korelasi 0,451 pada model regresi *random "
        "forest* yang memakai metrik curah hujan dan musim [@alonso]. Oleh karena itu, pemantauan hidrometeorologi "
        "memerlukan data hujan di samping data genangan."))

    x.append(h3("Sentinel-1"))
    x.append(para(
        "Misi Sentinel-1 terdiri atas dua satelit pengorbit kutub yang merekam data *Synthetic Aperture Radar* (SAR) "
        "pada pita C dengan frekuensi 5,405 GHz dan waktu kunjung ulang 6 hari [@weiss]. Kemampuan SAR menembus awan "
        "memungkinkan pemetaan genangan yang konsisten di bawah tutupan awan, baik siang maupun malam [@misra]. Namun, "
        "geometri pencitraan radar yang menyamping menimbulkan distorsi radiometrik, seperti *speckle*, dan distorsi "
        "geometrik, seperti *foreshortening*, *layover*, dan bayangan, sehingga data Level-1 harus dikoreksi sebelum "
        "dianalisis [@weiss]. Tahapan koreksi tersebut, yaitu kalibrasi radiometrik, penapisan *speckle*, koreksi "
        "medan, dan pemotongan wilayah, ditunjukkan pada Gambar 2.1 [@upadhyay]."))
    x.append(gambar_rujukan("V4_upadhyay2022_pipeline_sentinel1.png", 2, 1, "Tahapan Pra-Pemrosesan Sentinel-1",
                            "Upadhyay dkk. [@upadhyay]"))
    x.append(para(
        "Setiap tahap pada gambar tersebut menghasilkan citra antara yang berbeda dari masukannya, sehingga hasil "
        "akhirnya hanya dapat dipercaya bila urutan tahap dan parameternya tercatat. Hal ini menjadi alasan penelitian "
        "ini mencatat setiap tahap pengolahan sebagai *lineage*. Kemampuan SAR menembus awan juga memungkinkan pemetaan "
        "banjir secara global. Gambar 2.2 memperlihatkan sebaran "
        "banjir yang terdeteksi dari data Sentinel-1 selama sepuluh tahun, termasuk di wilayah Indonesia yang sering "
        "tertutup awan, serta wilayah yang deteksinya kurang andal, misalnya kawasan perkotaan dan lereng curam [@misra]."))
    x.append(gambar_rujukan("V2_misra2025_peta_banjir_global_sentinel1.png", 2, 2,
                            "Peta Banjir Global dari Sepuluh Tahun Data Sentinel-1", "Misra dkk. [@misra]"))
    x.append(para(
        "Wilayah yang ditandai kurang andal pada peta tersebut menunjukkan bahwa deteksi radar tetap memerlukan "
        "informasi mutu, misalnya porsi piksel valid, agar nilai genangan di wilayah perbukitan seperti Lebak Selatan "
        "tidak dibaca tanpa konteks. Untuk pemetaan air permukaan, Tran dkk. memilih polarisasi silang VH setelah membandingkan beberapa "
        "polarisasi Sentinel-1, menerapkan ambang Otsu dinamis untuk memisahkan piksel air dan bukan air, lalu "
        "menentukan piksel banjir dengan membandingkan kondisi setiap piksel pada waktu *t* terhadap kondisinya pada "
        "waktu *t*−1 [@tran]."))

    x.append(h3("MODIS"))
    x.append(para(
        "*Moderate Resolution Imaging Spectroradiometer* (MODIS) terpasang pada satelit Terra dengan lintasan pagi dan "
        "Aqua dengan lintasan siang, dan telah menyediakan data lebih dari dua puluh tahun; produk lahannya kini "
        "dilanjutkan oleh VIIRS [@roman]. Arsip MODIS telah dipakai untuk menyusun dataset air permukaan global harian "
        "beresolusi 250 m untuk periode 2003–2022 dari lebih dari 6,3 juta produk MODIS [@klein]. Pengamatan "
        "inframerah termal dari satelit, termasuk produk suhu permukaan MODIS yang paling umum digunakan, mengandung "
        "banyak piksel tidak valid yang terutama disebabkan kontaminasi awan [@tang], sehingga data MODIS perlu "
        "disertai informasi validitas piksel."))

    x.append(h3("GPM IMERG"))
    x.append(para(
        "*Integrated Multi-satellitE Retrievals for GPM* (IMERG) adalah rangkaian produk presipitasi global dari misi "
        "*Global Precipitation Measurement* (GPM) yang terdiri atas produk mendekati waktu nyata dan produk tingkat "
        "riset dengan resolusi spasio-temporal tinggi [@zhu]. Data harian IMERG Final menunjukkan konsistensi spasial "
        "yang tinggi dengan pos hujan pada resolusi 0,1°, dan kinerjanya pada era GPM lebih baik daripada era TRMM, "
        "dengan proporsi sampel tidak andal sekitar 10,2% dibandingkan 21,2% [@zhu]."))
    x.append(para(
        "Di Indonesia, IMERG terbukti lebih akurat daripada TRMM untuk pemodelan hujan-limpasan, meskipun masih "
        "memiliki keterbatasan dalam mendeteksi hujan berintensitas rendah [@hidayah]. Evaluasi di Jawa Timur "
        "menunjukkan bahwa IMERG unggul pada skala bulanan dan andal untuk pemantauan regional, tetapi kurang presisi "
        "pada skala harian di daerah aliran sungai kecil dan cenderung meremehkan kejadian hujan ekstrem [@ansori]. "
        "Gambar 2.3 memperlihatkan bahwa estimasi GPM mendekati pos hujan pada periode ulang pendek, tetapi jauh di "
        "bawahnya pada periode ulang panjang [@ansori]. Karena itu, peringatan hujan yang dihitung dari GPM IMERG "
        "pada penelitian ini diposisikan sebagai indikasi, bukan pengganti pengamatan lapangan."))
    x.append(gambar_rujukan("V3_ansori2026_gpm_meremehkan_hujan_ekstrem.png", 2, 3,
                            "Perbandingan Hujan Maksimum Tahunan dan Periode Ulang antara Pos Hujan dan GPM IMERG",
                            "Ansori dan JBS [@ansori]", 12.0))
    x.append(para("Selisih pada periode ulang panjang berarti hujan yang jarang terjadi tetapi paling berbahaya justru "
                  "paling mungkin terlewat bila hanya mengandalkan GPM, sehingga GPM perlu dilengkapi pengamatan genangan "
                  "dari Sentinel-1 dan MODIS. Karakteristik ketiga sumber data dirangkum pada Tabel 2.2."))
    x.append(caption("Tabel", 2, 2, "Karakteristik Tiga Sumber Data Satelit"))
    x.append(table([1700, 2300, 2100, 1800], ["Aspek", "Sentinel-1", "MODIS", "GPM IMERG"], [
        ["Jenis pengamatan", "Radar SAR pita C [@weiss]", "Sensor pada satelit Terra dan Aqua [@roman]", "Presipitasi global multi-satelit [@zhu]"],
        ["Resolusi", "Kunjung ulang 6 hari dengan dua satelit [@weiss]", "Air permukaan harian 250 m [@klein]", "0,1°; produk harian [@zhu]"],
        ["Keunggulan", "Menembus awan, siang dan malam [@misra]", "Arsip lebih dari dua puluh tahun [@roman]", "Konsisten dengan pos hujan [@zhu]"],
        ["Keterbatasan", "Distorsi radiometrik dan geometrik [@weiss]", "Piksel tidak valid akibat awan [@tang]", "Meremehkan hujan ekstrem harian [@ansori]"],
    ]))

    x.append(para('Tabel 2.2 memperlihatkan bahwa keunggulan satu sumber menutupi keterbatasan sumber lain. Sentinel-1 tetap dapat mengamati permukaan air ketika MODIS terhalang awan, sedangkan GPM IMERG menyediakan data hujan harian di antara dua lintasan Sentinel-1. Perbedaan jenis pengamatan dan resolusi ini juga berarti ketiga sumber tidak dapat dibandingkan langsung pada tingkat piksel, sehingga diperlukan satu unit analisis bersama sebagaimana dirumuskan pada RM1.'))
    x.append(h3("Sistem Basis Data dan DBMS"))
    x.append(para(
        "Sistem basis data dipakai untuk mengumpulkan, menyimpan, mengelola, dan menganalisis data, dan dikelola oleh "
        "sistem manajemen basis data (*Database Management System*, DBMS); kajian tentang sistem basis data mencakup "
        "jenis, struktur, model, peran bahasa SQL, serta perbandingannya dengan sistem NoSQL [@seyf]. Basis data "
        "relasional dan non-relasional merupakan dua kelompok utama, dan dalam pengelolaan informasi sistem basis data "
        "menjamin ketepatan waktu, akurasi, serta keandalan data [@deng]."))

    x.append(h3("Basis Data Spasial dan PostGIS"))
    x.append(para(
        "DBMS relasional tradisional memiliki keterbatasan kinerja dan skalabilitas saat menangani data spasial dalam "
        "jumlah besar, sedangkan teknologi terbuka seperti PostGIS semakin banyak digunakan untuk menyimpan dan "
        "mengolah data geospasial [@kaptsov]. PostGIS adalah ekstensi PostgreSQL yang menyediakan fungsi spasial, "
        "misalnya ST_DWithin dan ST_Buffer, serta kemampuan indeks spasial [@papasani]. PostgreSQL juga telah dipakai "
        "sebagai dasar platform berbagi data bencana, bersama Python dan MapServer [@wang]."))

    x.append(h3("Perancangan Basis Data, ERD, dan Normalisasi"))
    x.append(para(
        "Perancangan basis data dengan metode DBSDLC terdiri atas tiga proses, yaitu desain konseptual, desain logis, "
        "dan desain fisik [@rahmawati]. Pada desain konseptual, *Entity-Relationship Diagram* (ERD) disusun lalu "
        "kunci primer dan kunci kandidat ditentukan; model logikal kemudian dikembangkan melalui validasi dan "
        "optimasi struktur [@siregar]. Tujuan fase perancangan basis data adalah memperoleh struktur basis data yang "
        "sesuai dengan kebutuhan pengguna dan andal untuk diterapkan [@pradipta]."))
    x.append(para(
        "Normalisasi meminimalkan sumber inkonsistensi data dan biaya pemeliharaan pembaruan yang ditimbulkan oleh "
        "redundansi data; berbagai kelas ketergantungan yang menyebabkan redundansi melahirkan bentuk normal seperti "
        "3NF, BCNF, 4NF, dan 5NF [@skav]. Perancangan skema relasional menghasilkan dekomposisi ke 3NF yang *lossless* "
        "dan mempertahankan ketergantungan, serta BCNF bila memungkinkan, sehingga integritas data dapat dijaga pada "
        "setiap relasi tanpa harus melakukan *join* [@zhang]. Dalam penelitian ini, normalisasi dilakukan bertahap: 1NF "
        "menghilangkan grup berulang, 2NF menghilangkan ketergantungan parsial, dan 3NF menghilangkan ketergantungan "
        "transitif, sebagaimana diuraikan pada subbab 4.2.2.2."))

    x.append(h3("Integritas Data dan Checksum"))
    x.append(para(
        "Integritas data menyangkut keakuratan dan keutuhan data selama disimpan dan dipindahkan. Sebagian besar DBMS "
        "relasional memungkinkan pengembang menetapkan berbagai jenis *integrity constraint* untuk melindungi integritas "
        "data dari kesalahan kode aplikasi maupun kesalahan operator [@huang]. Salah satunya adalah integritas referensial, "
        "yaitu terjaganya hubungan antartabel, yang ditegakkan melalui *foreign key constraint* sehingga data tetap "
        "konsisten dan akurat [@kanwal]. Penelitian ini memakai *primary key*, *foreign key*, UNIQUE, dan CHECK sebagai "
        "*constraint* utama."))
    x.append(para(
        "Untuk berkas data, *checksum* dipakai sebagai pemeriksa keutuhan. Sholah dkk. menunjukkan bahwa *checksum* "
        "berbasis XOR efektif mendeteksi kesalahan transmisi pesan AIS sehingga data yang diterima dapat diverifikasi "
        "keakuratannya [@sholah]. Ramli dan Darus memasukkan tingkat ketidakcocokan *checksum* ke dalam kamus "
        "indikator integritas data yang dapat diaudit [@ramli]. Pada platform data bencana, standar dan kerangka "
        "integrasi data ditetapkan untuk menjamin integritas dan keamanan data [@wang]."))

    x.append(h3("Indeks dan Kinerja Kueri"))
    x.append(para(
        "Kinerja kueri pada basis data spasial umumnya diukur dari rata-rata waktu eksekusi, nilai puncak, penggunaan "
        "memori, dan skalabilitas terhadap jumlah data [@kaptsov]. Indeks berperan besar terhadap kinerja tersebut: "
        "pada kueri kedekatan dengan PostGIS, indeks spasial mempercepat kueri 19 hingga 24 kali dan tetap skalabel "
        "hingga 1.000.000 lokasi [@papasani]."))

    x.append(h3("ETL, Data Lineage, dan Tata Kelola Data"))
    x.append(para(
        "*Pipeline* ETL mengintegrasikan data dalam jumlah besar dari berbagai sumber ke penyimpanan terpusat [@ananth]. Tantangan umum pada *pipeline* "
        "ETL meliputi pengelolaan evolusi skema, penjaminan kualitas data, dan integrasi lintas platform [@chanda]. "
        "Pendekatan berbasis metadata mengurangi beban pengembangan, meningkatkan kemudahan pemeliharaan, dan "
        "mendukung pengelolaan kualitas data yang konsisten [@vattumilli]. Dengan menempatkan aturan transformasi, "
        "*lineage*, dan kebijakan tata kelola sebagai metadata terstruktur, asal-usul data dapat dilacak sebagai bagian "
        "dari tata kelola [@gopaluni]. Pengelolaan metadata terpusat, pemantauan, dan manajemen *pipeline* berbasis "
        "kebijakan diperlukan untuk menjaga keandalan dan akuntabilitas operasi ETL [@ananth]."))
    x.append(para(
        "Data juga dapat dikurasi secara berlapis. Arsitektur *medallion* membagi kurasi data ke lapisan *Bronze*, "
        "*Silver*, dan *Gold*, sedangkan jaminan transaksi ACID memberikan fondasi data yang tangguh [@gujjala]."))

    x.append(h3("Keamanan Basis Data: RBAC dan Jejak Audit"))
    x.append(para(
        "*Role-Based Access Control* (RBAC) memberikan hak akses berdasarkan peran dalam organisasi, bukan per "
        "pengguna. Penerapannya mencakup definisi peran, penetapan izin, dan pengaitan pengguna dengan peran; "
        "keunggulannya antara lain pengelolaan izin yang sederhana dan keamanan yang lebih baik melalui prinsip hak "
        "minimum. Tantangannya meliputi ledakan jumlah peran (*role explosion*) dan akses yang terlalu longgar, yang "
        "dapat diatasi dengan perencanaan yang cermat dan audit berkala [@male]. Di PostgreSQL, RBAC diterapkan dengan "
        "perintah GRANT dan REVOKE; pengujian koneksi menunjukkan bahwa setiap peran hanya dapat mengakses dan "
        "mengubah data sesuai hak yang diberikan, dan akses tidak sah ditolak dengan pesan galat seperti "
        "*permission denied* [@purwitasari]."))
    x.append(para(
        "Jejak audit mencatat transaksi agar dapat diperiksa kembali. Pada sistem akuntansi digital, jejak audit "
        "berbasis *blockchain* memberikan akses berkelanjutan terhadap data transaksi yang terverifikasi, mempercepat "
        "deteksi anomali, dan mengurangi peluang manipulasi data [@maryani]."))

    x.append(h3("Pencadangan dan Pemulihan"))
    x.append(para(
        "Pencadangan (*backup*) adalah proses membuat data cadangan dengan menyalin atau mengarsipkan data sehingga data "
        "tersebut dapat digunakan kembali apabila hilang, rusak, atau terhapus; pada PostgreSQL, pencadangan dapat "
        "dilakukan secara bertahap dengan aplikasi khusus [@efendi]. Pemulihan (*recovery*) adalah proses mengembalikan "
        "data setelah terjadi kerusakan data atau kegagalan sistem, dan pengelolaan log yang efisien berperan penting "
        "untuk menjaga integritas data serta mempercepat pemulihan tersebut [@ahmad]. Dalam penelitian ini, pemulihan "
        "juga mencakup kemampuan melanjutkan proses ETL yang terhenti tanpa menghasilkan data ganda (subbab 3.4.3)."))

    x.append(h3("REST API"))
    x.append(para(
        "*Representational State Transfer Application Programming Interface* (REST API) menjadi salah satu solusi "
        "arsitektur utama karena memungkinkan interoperabilitas, rancangan aplikasi yang modular, dan integrasi lintas "
        "platform. Pada platform logistik geospasial, REST API dipadukan dengan arsitektur relasional dan basis data "
        "spasial [@kaptsov_api]."))

    x.append(h3("Pengujian Perangkat Lunak"))
    x.append(para(
        "Pengujian aplikasi web penting untuk menjamin dan menjaga kualitas sistem [@balsam]. Berdasarkan pengetahuan "
        "tentang struktur internal program, pengujian dibedakan menjadi *white-box*, *black-box*, dan *grey-box*: "
        "*white-box* memverifikasi logika internal dan penanganan data, *black-box* mengevaluasi fitur yang dihadapi "
        "pengguna, dan *grey-box* menggabungkan keduanya untuk menilai keamanan dan integrasi dengan *backend* "
        "[@maric]. Keunggulan dan kelemahan *black-box* dan *white-box* dapat dibandingkan dari fokus uji, dasar uji, "
        "sudut pandang penguji, desain kasus uji, cara identifikasi kesalahan, pengetahuan kode program, dan "
        "efektivitas uji [@maspupah]."))
    x.append(para(
        "Pengujian *black-box* menguji sistem tanpa pengetahuan tentang struktur internal program, sehingga penguji "
        "tidak perlu mengetahui bahasa pemrograman dan implementasinya. Penguji menganalisis kebutuhan sistem untuk "
        "memilih teknik yang sesuai, karena tidak ada satu teknik yang cocok untuk semua situasi [@alshamaa]. "
        "Pengujian ini menekankan fungsionalitas dan keandalan aplikasi dari sudut pandang pengguna, termasuk input "
        "data dan fungsi utama [@salih]."))

    x.append(h2("Framework yang Digunakan"))
    x.append(h3("Database System Development Life Cycle (DBSDLC)"))
    x.append(para(
        "Pengembangan sistem informasi tidak lepas dari pengembangan basis data, dan basis data yang baik dikembangkan "
        "dengan metode DBSDLC yang mencakup fase perancangan basis data [@pradipta]. DBSDLC juga mencakup tahap "
        "perencanaan dan studi literatur sebelum perancangan [@siregar]. Metode Database Life Cycle juga telah dipakai "
        "untuk merancang basis data relasional melalui tahapan analisis kebutuhan serta desain konseptual, logikal, dan "
        "fisik [@syaddam,@trihap]. Contoh penerapannya ditunjukkan pada Gambar 2.4, yang menempatkan tahap Database "
        "Planning hingga DBMS Selection setelah identifikasi masalah, studi pustaka, dan pengumpulan data [@syaddam]."))
    x.append(gambar_rujukan("V7_syaddam2025_tahapan_dblc.png", 2, 4, "Contoh Penerapan Tahapan Database Life Cycle",
                            "Syaddam dkk. [@syaddam]", 10.0))
    x.append(para(
        "Gambar 2.4 hanya memuat tahap perancangan basis data. Penelitian ini memakai tahapan DBSDLC yang lengkap, "
        "yaitu sebagai berikut."))
    x.append(items([
        "**Database Planning**, menyusun *mission statement* yang mendefinisikan tujuan utama sistem basis data dan "
        "*mission objective* yang mendefinisikan tugas yang harus didukung.",
        "**System Definition**, menetapkan ruang lingkup dan batas sistem dari sudut pandang pengguna (*user views*).",
        "**Requirement Collection and Analysis**, mengumpulkan dan menganalisis informasi tentang bagian organisasi yang "
        "didukung sistem melalui teknik pencarian fakta: pemeriksaan dokumen, wawancara, pengamatan, penelitian, dan "
        "kuesioner.",
        "**Database Design**, terdiri atas desain konseptual (entitas, relasi, atribut, domain, kunci, pemeriksaan "
        "redundansi, validasi terhadap transaksi, dan tinjauan bersama pengguna), desain logikal (entitas kuat dan "
        "lemah, *multiplicity*, normalisasi, batasan integritas, dan tinjauan bersama pengguna), serta desain fisik "
        "(penerjemahan ke DBMS target, organisasi berkas dan indeks, pandangan pengguna, mekanisme keamanan, redundansi "
        "terkendali, serta pemantauan dan penyelarasan).",
        "**DBMS Selection**, menetapkan kerangka acuan, memilih daftar pendek dua atau tiga produk, mengevaluasi produk, "
        "dan merekomendasikan pilihan beserta laporannya.",
        "**Pemodelan Sistem**, memodelkan fungsi sistem dengan *use case diagram*, *activity diagram*, dan *class "
        "diagram* (opsional bila ERD telah tersedia).",
        "**Desain Antarmuka**, merancang tampilan yang digunakan pengguna untuk memproses basis data.",
        "**Prototyping**, membangun model kerja agar pengguna dapat menilai fitur dan mengusulkan perbaikan.",
        "**Implementation**, merealisasikan basis data dan aplikasi secara fisik.",
        "**Data Conversion and Loading**, memindahkan data ke basis data baru.",
        "**Testing**, menjalankan sistem untuk menemukan kesalahan sebelum digunakan.",
    ]))
    x.append(h3("Unified Modeling Language (UML)"))
    x.append(para(
        "Diagram *Unified Modeling Language* (UML) menyediakan bahasa pemodelan visual yang memudahkan perancangan, "
        "analisis, dan implementasi sistem yang kompleks [@esiefa]. UML telah diadopsi secara luas dalam perancangan "
        "sistem; setiap diagram berfokus pada bagian tertentu dari sistem, sehingga konsistensi antardiagram, misalnya "
        "dari *use case* ke *sequence diagram*, perlu dijaga [@alyami]. Penelitian ini memakai *use case diagram*, "
        "*activity diagram*, dan *sequence diagram*, sedangkan *class diagram* tidak disajikan terpisah karena struktur "
        "data telah digambarkan dengan ERD."))

    x.append(h2("Tools/Software yang Digunakan"))
    x.append(para("Perangkat lunak yang digunakan dalam penelitian ini dirangkum pada Tabel 2.3."))
    x.append(caption("Tabel", 2, 3, "Perangkat Lunak yang Digunakan"))
    x.append(table([2600, 1700, 3600], ["Perangkat Lunak", "Versi", "Kegunaan"], [
        ["PostgreSQL dan PostGIS", "18.6 dan 3.6.2", "DBMS dan ekstensi spasial basis data utama"],
        ["MySQL Community", "8.0.40", "DBMS pembanding pada tahap DBMS Selection"],
        ["Python", "3.10", "Bahasa pemrograman ETL, API, dan pengujian"],
        ["FastAPI dan Uvicorn", "0.115.5 dan 0.32.1", "Kerangka REST API dan peladennya"],
        ["SQLAlchemy, GeoAlchemy2, psycopg2", "2.0.36, 0.15.2, 2.9.10", "Akses basis data dari Python"],
        ["rasterio, shapely, pyproj, h5py", "1.4.3, 2.0.6, 3.7.0, 3.12.1", "Pengolahan raster, geometri, proyeksi, dan berkas HDF5"],
        ["APScheduler", "3.10 atau lebih baru", "Penjadwalan tugas ETL"],
        ["ReportLab", "5.0.1", "Pembuatan laporan PDF"],
        ["HTML, CSS, JavaScript, Leaflet, MapLibre GL", "Leaflet 1.9.4, MapLibre 4.7.1", "Antarmuka web dan peta"],
        ["pytest", "8.3.4", "Pengujian otomatis"],
    ]))
    x.append(para("Seluruh perangkat lunak pada Tabel 2.3 bersifat sumber terbuka dan tidak berbayar, sejalan dengan "
                  "kriteria biaya dan ekosistem pada pemilihan DBMS, karena GMLS merupakan organisasi relawan. PostgreSQL "
                  "dengan PostGIS menjadi DBMS utama berdasarkan hasil pemilihan DBMS pada subbab 4.2.2.3, sedangkan MySQL "
                  "hanya dipasang sebagai pembanding dalam pengujian dan tidak dipakai oleh sistem yang berjalan."))
    return "".join(x)


# =====================================================================================================
# BAB III
# =====================================================================================================
def bab3():
    h2 = lambda t: head(2, t, 3)
    h3 = lambda t: head(3, t, 3)
    x = []
    x.append(h2("Gambaran Umum Objek Penelitian"))
    x.append(para(
        "Objek penelitian ini adalah Gugus Mitigasi Lebak Selatan (GMLS) beserta kebutuhannya terhadap pengelolaan data "
        "hidrometeorologi. Informasi pada subbab ini bersumber dari wawancara dengan Ketua GMLS pada 16 Oktober 2026 "
        "beserta notulennya, profil resmi GMLS, dan data batas wilayah yang digunakan sistem."))
    x.append(h3("Profil GMLS"))
    x.append(para(
        "GMLS adalah komunitas masyarakat lokal yang bergerak di bidang mitigasi bencana dan berdomisili di Desa "
        "Panggarangan, Kecamatan Panggarangan, Kabupaten Lebak. GMLS resmi berdiri pada 13 Oktober 2020, sedangkan "
        "ketua dan pendirinya, Anis Faisal Reza (Abah Lala), telah memulai kegiatan mitigasi di Lebak Selatan sejak "
        "2015. Inisiasi GMLS dipromosikan oleh U-Inspire Indonesia. Pada 5 November 2020, bertepatan dengan Hari "
        "Kesadaran Tsunami Sedunia, Desa Panggarangan dicanangkan sebagai salah satu dari tujuh desa di Indonesia yang "
        "diusulkan memperoleh pengakuan *Tsunami Ready* dari IOC-UNESCO."))
    x.append(para(
        "Menurut profil resminya, Lebak Selatan merupakan wilayah multi-bahaya, yaitu banjir, pergerakan tanah, longsor, "
        "gempa, dan tsunami, dengan perhatian utama pada potensi gempa-tsunami di selatan Jawa. Dalam wawancara, Ketua "
        "GMLS menegaskan bahwa semua jenis bencana menjadi perhatian GMLS, termasuk banjir bagi masyarakat yang tinggal "
        "di dekat sungai, banjir bandang ke hilir dan tanah longsor akibat hujan lebat, serta kenaikan air laut yang "
        "berpotensi menimbulkan banjir rob. Beliau juga menyampaikan bahwa mitigasi bencana tidak sesederhana mengajar "
        "dan mengedukasi masyarakat, karena masalahnya mencakup infrastruktur, ekonomi, edukasi, dan teknologi."))
    x.append(para(
        "GMLS bekerja sama secara resmi dengan Universitas Multimedia Nusantara melalui LPPM dengan nota kesepahaman "
        "(MoU). Kolaborasi ini dipimpin Fakultas Teknik dan Informatika dan didukung Fakultas Ilmu Komunikasi, dengan "
        "prinsip yang dipegang GMLS bahwa masyarakat tidak boleh dipandang hanya sebagai objek penelitian. Dengan "
        "kemitraan resmi tersebut dan masa kegiatan sejak berdiri pada 2020, GMLS memenuhi prasyarat objek penelitian, "
        "yaitu diakui secara kelembagaan dan telah beroperasi lebih dari dua tahun. Kegiatan dan informasi resmi GMLS "
        "dipublikasikan melalui situs gmls.org, yang halaman utamanya ditunjukkan pada Gambar 3.1 [@tilung]."))
    x.append(gambar_rujukan("V5_tilung2025_situs_gmls.png", 3, 1, "Halaman Utama Situs Resmi GMLS",
                            "Tilung dkk. [@tilung]", 10.0))
    x.append(para(
        "Situs tersebut berfungsi sebagai kanal informasi kegiatan dan ajakan kolaborasi, bukan sebagai sistem data. "
        "Profil, wilayah kerja, dan kegiatan pada situs ini menjadi salah satu sumber observasi (subbab 3.3.1), "
        "sedangkan data pemantauan wilayah belum tersedia di dalamnya."))

    x.append(h3("Aplikasi dalam Kerja Sama GMLS dan UMN"))
    x.append(para(
        "Di bawah payung kerja sama *Humanity Project* GMLS x UMN, empat aplikasi dijadwalkan diluncurkan pada Desember "
        "2026. Keempat aplikasi tersebut dirangkum pada Tabel 3.1 karena menentukan batas sistem yang dibangun dalam "
        "penelitian ini."))
    x.append(caption("Tabel", 3, 1, "Aplikasi dalam Kerja Sama GMLS dan UMN"))
    x.append(table([1900, 1500, 4500], ["Aplikasi", "Bentuk", "Fungsi"], [
        ["SIGAP DESA", "Web SIG", "Pendataan penduduk di daerah rawan bencana yang disajikan sebagai infografis"],
        ["GMLS Logify", "Aplikasi seluler", "Manajemen tempat pengungsian dan logistik di daerah bencana"],
        ["Are You In Sys", "Aplikasi seluler (sudah ada)", "Menyalurkan informasi lembaga pemerintah ke masyarakat desa: peta lokasi pengguna dan wilayah rawan, informasi cuaca dari API BMKG termasuk radar, peta BNPB, notifikasi gempa dan peringatan dini tsunami, serta pelaporan kejadian oleh masyarakat"],
        ["GMLS Info Hub", "Situs web", "Rujukan informasi resmi dan valid tentang GMLS"],
    ]))
    x.append(para(
        "Menurut Ketua GMLS, fungsi sistem yang diusulkan beririsan dengan Are You In Sys, yang sudah menampilkan "
        "informasi cuaca dan menerima pelaporan bencana. Oleh karena itu, sistem dalam penelitian ini tidak menerima "
        "laporan warga, yang tetap disalurkan melalui Are You In Sys, dan tidak menyimpan data penduduk, yang tetap "
        "dikelola SIGAP DESA."))
    x.append(para(
        "Kerja sama GMLS dan UMN sebelumnya juga telah menghasilkan dasbor pra-bencana tsunami untuk Panggarangan yang "
        "memvisualisasikan data kependudukan, rambu, dan kejadian gempa-tsunami, sebagaimana ditunjukkan pada Gambar 3.2 "
        "[@wong]. Dasbor ini berfokus pada bahaya geologi dan belum memuat data hidrometeorologi, yang menjadi cakupan "
        "penelitian ini."))
    x.append(gambar_rujukan("V6_wong2024_dasbor_prabencana_gmls.png", 3, 2, "Dasbor Pra-Bencana Tsunami GMLS",
                            "Wong dkk. [@wong]"))
    x.append(para(
        "Dasbor tersebut menyajikan kondisi kependudukan dan kawasan rawan yang relatif tetap, bukan deret waktu "
        "pengamatan yang berubah setiap hari. Karena itu, sistem dalam penelitian ini melengkapinya dengan basis data "
        "yang diperbarui setiap hari, bukan menggantikan dasbor yang sudah ada."))

    x.append(h3("Sistem yang Sedang Berjalan"))
    x.append(para(
        "Informasi cuaca dan bencana yang diterima GMLS berasal dari lembaga pemerintah, terutama BMKG, dan disalurkan "
        "melalui aplikasi Are You In Sys. Informasi radar BMKG hanya menunjukkan area yang berpotensi hujan dan banjir, "
        "belum spesifik ke lokasi warga. Menurut narasumber, informasi yang paling dibutuhkan masyarakat adalah "
        "informasi yang spesifik ke lokasinya, misalnya adanya awan hujan lebat di atas tempat tinggal yang dapat "
        "memicu banjir bandang ke hilir atau tanah longsor, dan informasi tersebut sebaiknya dikirim sebagai "
        "notifikasi."))
    x.append(para(
        "GMLS belum memiliki penanggung jawab untuk mengumumkan informasi potensi bencana. Pengumuman bencana merupakan "
        "ranah pemerintah, sehingga GMLS hanya memberikan peringatan, bukan pernyataan atau penetapan status bencana, "
        "meskipun masyarakat tetap berhak memperoleh informasi sendiri. Karena itu, sistem yang dibangun diposisikan "
        "sebagai pemberi peringatan dan rekomendasi, bukan pengarah langsung, dan kalimat peringatannya perlu disusun "
        "dengan hati-hati."))
    x.append(para(
        "GMLS tidak melakukan pendataan kejadian bencana sendiri. Data kejadian dan dampak bencana lima tahun terakhir, "
        "termasuk korban dan warga terdampak, berada di lembaga resmi pemerintah, tetapi menurut narasumber data bencana "
        "BNPB tidak rapi dan tidak konsisten. Kekosongan inilah yang menjadi dasar dibuatnya fitur pelaporan masyarakat "
        "di Are You In Sys. Narasumber juga menilai situs informasi bencana yang ada, terutama untuk gunung api, sulit "
        "dipahami orang awam, sehingga masyarakat membutuhkan tampilan yang lebih sederhana."))
    x.append(para(
        "Terhadap sistem yang diusulkan, GMLS memberikan beberapa masukan: prediksi cuaca atau bencana ke depan, fitur "
        "laporan untuk pelaporan dan estimasi dampak, eksplorasi satelit geostasioner Himawari yang datanya diperbarui "
        "sekitar setiap 10 menit, serta informasi bahwa citra Sentinel juga digunakan BMKG untuk membuat peta lokasi "
        "dan dampak bencana. Analisis kondisi ini dengan metode 5W1H disajikan pada BAB IV."))

    x.append(h3("Wilayah Kajian"))
    x.append(para(
        "Wilayah kajian terdiri atas sepuluh kecamatan di Kabupaten Lebak, yaitu Banjarsari, Bayah, Cibeber, Cigemblong, "
        "Cihara, Cijaku, Cilograng, Malingping, Panggarangan, dan Wanasalam, sebagaimana ditunjukkan pada Gambar 3.3. "
        "Batas wilayah bersumber dari data COD-AB Indonesia tingkat kecamatan, dengan luas total sekitar 1.575,8 km² "
        "yang dihitung dari poligon tersebut. Cakupan sepuluh kecamatan ini dikonfirmasi oleh GMLS melalui kuesioner "
        "tinjauan kebutuhan (subbab 4.3.4)."))
    x.append(figure(os.path.join(IMG, "peta_wilayah.png"), 14.0))
    x.append(caption("Gambar", 3, 3, "Peta Wilayah Kajian"))

    x.append(para('Luas kecamatan dalam wilayah kajian bervariasi, dari Cilograng sekitar 94,9 km² hingga Cibeber sekitar 400,8 km². Perbedaan ini berpengaruh pada data hujan GPM IMERG yang beresolusi 0,1°: satu kecamatan hanya tercakup oleh satu hingga enam sel grid, sehingga nilai per kecamatan dihitung dengan bobot luas irisan sel dan poligon, bukan dengan mengambil satu sel terdekat. Cara perhitungan ini diuraikan pada subbab 4.3.1.'))
    x.append(h2("Metode Penelitian"))
    x.append(para(
        "Penelitian ini mengikuti jalur *Design and Implementation* pada peminatan Database, yang berfokus pada "
        "kebutuhan, perancangan konseptual, logikal, dan fisik, integritas, keamanan, serta implementasi basis data. "
        "Alur penelitian dan metode pengembangannya diuraikan pada subbab berikut."))
    x.append(h3("Alur Penelitian"))
    x.append(para("Alur penelitian ditunjukkan pada Gambar 3.4."))
    x.append(figure(os.path.join(IMG, "alur_penelitian.png"), 14.0))
    x.append(caption("Gambar", 3, 4, "Alur Penelitian"))
    x.append(para(
        "Penelitian diawali dengan analisis sistem yang sedang berjalan melalui observasi, wawancara dengan GMLS, dan pemeriksaan "
        "dokumen. Hasilnya diidentifikasi dengan metode 5W1H untuk merumuskan masalah dari sisi apa, siapa, kapan, di "
        "mana, mengapa, dan bagaimana. Studi pustaka kemudian dilakukan untuk menempatkan masalah tersebut terhadap "
        "penelitian terdahulu dan menentukan celah penelitian (*research gap*), sehingga diperoleh empat rumusan masalah "
        "(RM1–RM4) pada BAB I."))
    x.append(para(
        "Setiap rumusan masalah dijawab melalui sebelas tahap DBSDLC. Dua umpan balik ditunjukkan pada Gambar 3.4: "
        "temuan pada tahap *Prototyping* dikembalikan ke tahap desain antarmuka, dan hasil *Testing* yang belum memenuhi "
        "kriteria dikembalikan ke tahap *Implementation* untuk diperbaiki. Setelah seluruh evaluasi terpenuhi, hasil "
        "setiap tahap dibahas terhadap RM1–RM4 untuk menarik simpulan dan saran."))

    x.append(h3("Metode Pengembangan Sistem"))
    x.append(para(
        "Metode pengembangan sistem yang digunakan adalah DBSDLC (subbab 2.3.1), dilengkapi UML untuk pemodelan "
        "fungsional. Kegiatan dan keluaran setiap tahap dalam penelitian ini dirangkum pada Tabel 3.2, sedangkan "
        "hasilnya disajikan pada BAB IV."))
    x.append(caption("Tabel", 3, 2, "Kegiatan dan Keluaran Tahap DBSDLC"))
    x.append(table([2300, 3500, 2100], ["Tahap", "Kegiatan", "Keluaran"], [
        ["Database Planning", "Menurunkan tujuan basis data dari rumusan masalah", "*Mission statement* dan *mission objectives*"],
        ["System Definition", "Menetapkan batas sistem terhadap aplikasi GMLS lain dan penyedia data, serta pandangan lima peran pengguna", "Batas sistem dan *user views*"],
        ["Requirement Collection and Analysis", "Mengolah hasil observasi, wawancara, pemeriksaan dokumen, studi pustaka, dan kuesioner tinjauan kebutuhan", "Daftar kebutuhan dan keterlacakannya"],
        ["Database Design", "Menyusun ERD, kunci dan domain, normalisasi hingga 3NF, batasan integritas, DDL, indeks, VIEW, serta mekanisme keamanan", "ERD konseptual, logikal, dan fisik; kamus data; DDL"],
        ["DBMS Selection", "Membandingkan PostgreSQL dengan PostGIS dan MySQL 8.0 pada skema dan data yang setara", "Laporan dan rekomendasi DBMS"],
        ["Pemodelan Sistem", "Memodelkan fungsi sistem untuk setiap peran", "*Use case*, *activity*, dan *sequence diagram*"],
        ["Desain Antarmuka", "Merancang halaman dan matriks akses per peran", "Rancangan antarmuka"],
        ["Prototyping", "Membangun aplikasi web yang dapat dicoba pengguna dan memperbaruinya berdasarkan masukan GMLS", "Prototipe dan video demonstrasi"],
        ["Implementation", "Membangun basis data, ETL, REST API, dan aplikasi web", "Sistem yang berjalan"],
        ["Data Conversion and Loading", "Memuat batas wilayah COD-AB dan data satelit sejak 1 Januari 2024; tidak ada konversi karena GMLS belum memiliki basis data hidrometeorologi", "Basis data berisi data awal"],
        ["Testing", "Menjalankan enam evaluasi minimum (subbab 3.4.3)", "Hasil evaluasi"],
    ]))

    x.append(para('Keluaran setiap tahap menjadi masukan bagi tahap berikutnya. User views dari tahap System Definition, misalnya, menjadi dasar VIEW dan matriks GRANT pada desain fisik, sedangkan kebutuhan dari tahap Requirement Collection and Analysis menjadi butir yang ditinjau GMLS melalui kuesioner. Dengan demikian, hasil akhir pada BAB IV dapat ditelusuri kembali ke tahap yang menghasilkannya.'))
    x.append(h2("Teknik Pengumpulan Data"))
    x.append(para(
        "Pengumpulan data dilakukan dengan teknik pencarian fakta (*fact-finding techniques*) pada tahap *Requirement "
        "Collection and Analysis*, ditambah pengambilan data sekunder dari penyedia data satelit. Sesuai metode "
        "pengumpulan data program studi, teknik utamanya adalah observasi, pemeriksaan dokumen, dan studi pustaka, yang "
        "dilengkapi wawancara dan kuesioner."))
    x.append(h3("Observasi"))
    x.append(para(
        "Observasi dilakukan untuk memahami cara GMLS bekerja dan data yang sudah dimilikinya, sehingga kebutuhan sistem "
        "disusun dari kegiatan GMLS yang berjalan, bukan dari asumsi peneliti. Karena wilayah kerja GMLS berada di "
        "Lebak Selatan, observasi dilakukan melalui empat sumber. Pertama, wawancara dengan Ketua GMLS yang menggambarkan "
        "alur kerja GMLS sehari-hari, mulai dari penerimaan informasi cuaca hingga penyampaiannya ke masyarakat. Kedua, "
        "data kegiatan resmi GMLS (data_humanity) yang diberikan GMLS kepada peneliti. Ketiga, situs resmi GMLS "
        "(gmls.org) yang memuat profil, wilayah kerja, dan kegiatan GMLS. Keempat, sumber data aplikasi SIGAP DESA yang "
        "dikembangkan dalam kerja sama *Humanity Project* GMLS x UMN. Hasil observasi digunakan untuk menyusun gambaran "
        "sistem berjalan (subbab 3.1.3), menentukan data yang sudah dikelola SIGAP DESA sehingga tidak perlu disimpan "
        "ulang, dan menetapkan batas sistem pada Tabel 3.1."))
    x.append(para(
        "Pemeriksaan data_humanity menghasilkan empat temuan. Pertama, data terlengkap GMLS adalah Formulir Asesmen "
        "Demografi berbasis AppSheet yang diisi relawan GMLS pada 14 Januari hingga 16 Juni 2021, berisi 356 rumah tangga "
        "di zona rawan tsunami Desa Panggarangan, Kecamatan Panggarangan, lengkap dengan koordinat rumah, data kepala "
        "keluarga, dan kelompok rentan. Survei ini mendukung *Piloting Tsunami Ready* 2021 bersama BMKG, BNPB, dan "
        "lembaga lain untuk pengakuan UNESCO. Kedua, data tersebut telah disusun ulang menjadi tabel desa, zona bencana, "
        "keluarga, warga, rambu, tempat evakuasi, dan 25 kegiatan kesiapsiagaan tahun 2023. Ketiga, data spasial yang "
        "dimiliki adalah batas administrasi COD-AB BPS 2020 serta peta Kawasan Rawan Bencana gerakan tanah dan tsunami "
        "Banten dari PVMBG. Keempat, data kejadian yang tersedia hanya katalog gempa bumi global sebanyak 1.633 kejadian. "
        "Basis data SIGAP DESA (MySQL, 11 tabel) mengelola hierarki wilayah hingga RT, rumah dengan status zona tsunami "
        "dan koordinat, keluarga, warga, serta titik evakuasi yang ditampilkan melalui Tableau."))
    x.append(para(
        "Dari observasi ini disimpulkan bahwa data GMLS berfokus pada kependudukan, kawasan rawan, dan gempa-tsunami, "
        "sedangkan data hidrometeorologi per kecamatan, seperti curah hujan, genangan, dan kelembapan tanah, beserta "
        "catatan kejadian banjir dan longsor belum dimiliki. Temuan ini menjadi dasar ruang lingkup Orbit-U: The Monitor: "
        "data kependudukan dan titik evakuasi tetap dikelola SIGAP DESA, sedangkan basis data yang dirancang mengisi "
        "kekosongan data hidrometeorologi dengan memakai batas kecamatan COD-AB yang sama."))
    x.append(h3("Wawancara"))
    x.append(para(
        "Wawancara dilakukan pada 16 Oktober 2026 secara daring melalui Zoom Meeting dengan narasumber Anis Faisal Reza "
        "(Abah Lala), ketua dan pendiri GMLS, dengan didampingi dosen yang pernah melaksanakan *Humanity Project* di "
        "Lebak Selatan. Wawancara berlangsung dalam satu sesi panjang berbentuk diskusi terbuka dan tidak direkam. Satu "
        "sesi dipandang memadai karena mencakup keempat topik wawancara secara lengkap, didampingi dosen yang memahami "
        "konteks GMLS, dan hasilnya dikonfirmasi kembali kepada GMLS melalui kuesioner tinjauan kebutuhan. Notulen disusun "
        "dari dua catatan, yaitu catatan pewawancara dan catatan rekan peneliti, lalu dikonfirmasi oleh pewawancara."))
    x.append(para(
        "Pertanyaan wawancara dikelompokkan ke dalam empat topik, yaitu profil dan kerja sama, sistem yang sedang "
        "berjalan, masalah yang dirasakan, dan masukan untuk sistem yang diusulkan. Hasilnya digunakan untuk menyusun "
        "gambaran sistem berjalan (subbab 3.1.3) serta kebutuhan sistem pada BAB IV."))
    x.append(h3("Pemeriksaan Dokumen"))
    x.append(para(
        "Dokumen yang diperiksa meliputi profil resmi GMLS, kriteria intensitas curah hujan harian BMKG sebagai dasar "
        "aturan peringatan, data batas administrasi COD-AB (BPS melalui OCHA/HDX), serta spesifikasi produk dari "
        "penyedia data satelit. Kriteria BMKG membagi hujan harian menjadi ringan (0,5 hingga kurang dari 20 mm), sedang "
        "(20 hingga kurang dari 50 mm), lebat (50 hingga kurang dari 100 mm), sangat lebat (100 hingga 150 mm), dan "
        "ekstrem (lebih dari 150 mm) [@bmkg_sumsel,@bmkg_kalsel]. Penyediaan dan penyebarluasan peringatan dini cuaca "
        "ekstrem, termasuk hujan lebat, diatur sebagai kewenangan BMKG [@perban], sehingga sistem ini memosisikan "
        "keluarannya sebagai informasi pendukung, bukan peringatan dini resmi. Contoh produk peringatan dini curah "
        "hujan tinggi BMKG ditunjukkan pada Gambar 3.5. Peringatan tersebut dibagi ke dalam kelas Waspada, Siaga, dan "
        "Awas, tetapi disajikan per kabupaten dan per dasarian, sehingga belum menggambarkan kondisi harian per "
        "kecamatan yang dibutuhkan GMLS [@bmkg_kalsel]. "
        "Selain itu, kode dan skema basis data Orbit-U: The DataLab, yaitu sistem pengolah data satelit yang menjadi "
        "dasar pengembangan sistem ini, diperiksa untuk menentukan komponen yang dipertahankan, diubah, atau dihapus."))
    x.append(gambar_rujukan("V8_bmkg2026_peta_pdcht_kalsel.png", 3, 5, "Contoh Peta Peringatan Dini Curah Hujan Tinggi BMKG",
                            "Stasiun Klimatologi Kalimantan Selatan, BMKG [@bmkg_kalsel]", 11.0))
    x.append(para(
        "Klasifikasi Waspada, Siaga, dan Awas pada peta tersebut sejalan dengan ambang hujan lebat, sangat lebat, dan "
        "ekstrem, sehingga ketiga tingkat inilah yang dipakai sebagai severity aturan peringatan. Perbedaannya, sistem "
        "ini menghitung ambang tersebut dari hujan harian GPM IMERG per kecamatan, sehingga keluarannya lebih rinci "
        "tetapi tetap berstatus informasi pendukung."))
    x.append(h3("Studi Pustaka"))
    x.append(para(
        "Studi pustaka dilakukan terhadap artikel jurnal dan prosiding tentang pemantauan bencana berbasis satelit, "
        "perancangan basis data, basis data spasial, ETL dan tata kelola data, keamanan basis data, serta pengujian "
        "perangkat lunak. Hasilnya disajikan pada BAB II."))
    x.append(h3("Kuesioner Tinjauan Kebutuhan"))
    x.append(para(
        "Kuesioner digunakan untuk tinjauan kebutuhan oleh pengguna (*requirement/user review*). Lembar Tinjauan "
        "Kebutuhan Sistem Orbit-U: The Monitor disusun pada 23 Oktober 2026 dalam bentuk halaman web yang diisi pengurus "
        "GMLS, dengan jawaban tersimpan di Google Sheet. Karena pengisi bukan orang teknis, model data konseptual disajikan sebagai "
        "daftar informasi yang dicatat dan model data logikal sebagai aturan pencatatan dalam bahasa sehari-hari. "
        "Isi kuesioner dirangkum pada Tabel 3.3."))
    x.append(caption("Tabel", 3, 3, "Bagian Kuesioner Tinjauan Kebutuhan"))
    x.append(table([600, 3500, 3800], ["Bagian", "Isi", "Pilihan Jawaban"], [
        ["1", "Enam fitur (K1–K6) yang diturunkan dari wawancara", "Sesuai, perlu diubah, atau tidak sesuai, disertai catatan"],
        ["2", "Informasi yang dicatat (model konseptual) dan aturan pencatatan (model logikal)", "Cukup atau kurang; sesuai atau perlu diubah, disertai catatan"],
        ["3", "Hal yang tidak dilakukan sistem (batasan)", "Dapat atau tidak dapat diterima, disertai catatan"],
        ["4", "Pemetaan peran Analis, Data Engineer, dan Administrator ke orang di GMLS, serta konfirmasi sepuluh kecamatan", "Nama atau jabatan; wilayah sesuai atau perlu diubah"],
        ["5", "Persetujuan atas rancangan sistem", "Disetujui, disetujui dengan perbaikan, atau tidak disetujui, disertai saran"],
    ]))
    x.append(para('Kuesioner tidak memakai istilah teknis seperti entitas atau constraint. Aturan "peringatan untuk satu kecamatan hanya dicatat sekali per hari", misalnya, mewakili batasan UNIQUE pada tabel peringatan. Bila responden memilih jawaban perlu diubah, kuesioner meminta responden menuliskan bagian yang perlu diperbaiki, sehingga setiap masukan dapat ditindaklanjuti secara spesifik.'))
    x.append(h3("Kuesioner Uji Coba Pengguna"))
    x.append(para(
        "Kuesioner kedua digunakan untuk uji coba aplikasi oleh pengguna, yaitu peserta *Humanity Project* di GMLS dan masyarakat awam. Formulir uji coba berbentuk halaman web "
        "yang memuat enam skenario beserta video contoh, langkah, dan tanda berhasilnya, dengan jawaban tersimpan di "
        "Google Sheet. Untuk setiap skenario, responden memilih hasil, menilai kemudahan, dan menuliskan kendala; di "
        "akhir formulir responden menilai kelayakan aplikasi dan memberi saran. Rinciannya dibahas pada subbab "
        "Rancangan Evaluasi (Tabel 3.7)."))
    x.append(h3("Data Sekunder"))
    x.append(para(
        "Data satelit diambil melalui layanan resmi penyedianya, sedangkan batas wilayah diambil dari COD-AB. Sumber "
        "data sekunder dirangkum pada Tabel 3.4."))
    x.append(caption("Tabel", 3, 4, "Sumber Data Sekunder"))
    x.append(table([1600, 2600, 1300, 1200, 1200], ["Data", "Produk", "Resolusi", "Temporal", "Penyedia"], [
        ["Sentinel-1 (S1A, S1C, S1D)", "GRD IW, polarisasi VV dan VH", "±10 m", "Per lintasan, 6–12 hari", "ESA melalui CDSE"],
        ["MODIS Terra dan Aqua", "MCDWD (banjir); MOD09A1 dan MOD09GA (NDVI, NDWI)", "250–500 m", "Harian; komposit 8 hari", "NASA LANCE dan LAADS DAAC"],
        ["GPM IMERG", "Daily Final, Late, dan Early", "±10 km", "Harian", "NASA GES DISC"],
        ["Batas administrasi", "COD-AB Indonesia tingkat kabupaten dan kecamatan [@codab]", "Poligon", "Statis", "BPS melalui OCHA/HDX"],
    ]))
    x.append(para(
        "Catatan kejadian bencana tidak diperoleh dari GMLS karena GMLS tidak mencatat kejadian sendiri. Kejadian dicatat "
        "Analis dari sumber yang tersedia, terutama data pemerintah (BPBD Lebak dan BNPB), beserta sumber informasi dan "
        "status verifikasinya."))

    x.append(h2("Teknik Analisis Data"))
    x.append(h3("Analisis Masalah"))
    x.append(para(
        "Masalah diidentifikasi dengan dua metode. Metode 5W1H (*What, Who, When, Where, "
        "Why, How*) digunakan untuk menganalisis kondisi sistem yang sedang berjalan dan kebutuhan sistem usulan, "
        "sedangkan ERD digunakan untuk mengidentifikasi entitas data yang perlu dikelola beserta hubungannya. Metode "
        "5W1H juga lazim dipakai sebagai alat analisis untuk mengidentifikasi hambatan dalam proses kerja dan menyusun "
        "usulan perbaikannya [@nascimento]."))
    x.append(h3("Analisis Pemilihan DBMS"))
    x.append(para(
        "Pemilihan DBMS mengikuti empat langkah DBMS Selection. Kerangka acuan disusun dari kebutuhan nyata sistem dan "
        "rumusan masalah. Daftar pendek berisi PostgreSQL dengan PostGIS dan MySQL 8.0; MongoDB hanya dinilai dari "
        "fiturnya karena tidak mendukung *foreign key* sehingga skemanya tidak dapat dibuat setara. Penelitian "
        "terdahulu yang membandingkan PostGIS dan MySQL [@kaptsov] menjadi salah satu dasar pemilihan daftar pendek."))
    x.append(para(
        "Evaluasi dilakukan pada skema yang setara dan data sintetis deterministik yang sama untuk kedua DBMS, meliputi "
        "lima kueri inti (Q1–Q5), uji fitur keamanan (F1–F3), skalabilitas, konkurensi, dan penulisan data. Setiap kueri "
        "inti dijalankan 30 kali setelah 5 kali pemanasan dalam tiga run terpisah, lalu dilaporkan median dan persentil "
        "ke-95 waktu eksekusinya. Hasil evaluasi dinilai dengan skor terbobot:"))
    x.append('<w:p><w:pPr><w:spacing w:after="0" w:line="360" w:lineRule="auto"/><w:jc w:val="center"/></w:pPr>' + runs("*S* = Σ (*w*ᵢ × *s*ᵢ)") + "</w:p>")
    x.append(para(
        "dengan *w*ᵢ bobot kriteria ke-*i* dan *s*ᵢ skor DBMS pada kriteria tersebut dengan skala 1–5. Kriteria dan "
        "bobotnya ditunjukkan pada Tabel 3.5. Karena PostgreSQL telah digunakan sejak awal pengembangan, evaluasi ini "
        "berfungsi menguji apakah pilihan tersebut tepat dibandingkan dengan alternatif terdekatnya."))
    x.append(caption("Tabel", 3, 5, "Kriteria dan Bobot Pemilihan DBMS"))
    x.append(table([3800, 3000, 1100], ["Kriteria", "Dasar Kebutuhan", "Bobot"], [
        ["Keamanan per peran dan audit", "RM4: pergantian peran per transaksi, pembatasan baris, audit melalui *trigger*", "25%"],
        ["Kueri spasial", "Irisan poligon kecamatan dan luas geodesik", "20%"],
        ["Analitik dan skala", "Agregasi deret waktu per kecamatan", "15%"],
        ["Penulisan data ETL", "*Insert* dan *upsert* harian", "10%"],
        ["Konkurensi baca", "Akses banyak pengguna", "10%"],
        ["Integritas relasional dan kueri rekursif", "RM1 dan RM2: *foreign key*, *constraint*, *lineage*", "10%"],
        ["Biaya, ekosistem, dan keakraban pengguna", "Sumber terbuka dan kemampuan GMLS", "10%"],
    ]))
    x.append(para('Bobot terbesar diberikan pada keamanan per peran dan audit serta kueri spasial, karena keduanya berkaitan langsung dengan RM4 dan dengan unit analisis wilayah pada RM1. Kriteria biaya, ekosistem, dan keakraban pengguna tetap dinilai karena SIGAP DESA milik GMLS memakai PHP dan MySQL, sehingga MySQL merupakan alternatif yang paling mungkin dipertimbangkan oleh GMLS.'))
    x.append(h3("Rancangan Evaluasi"))
    x.append(para(
        "Evaluasi mengikuti enam evaluasi minimum jalur *Design and Implementation*. Evaluasi fungsional menggunakan "
        "pendekatan *black-box* karena menilai fungsi dari sudut pandang pengguna [@salih]. Rancangan setiap evaluasi "
        "dirangkum pada Tabel 3.6."))
    x.append(caption("Tabel", 3, 6, "Rancangan Evaluasi"))
    x.append(table([1500, 2300, 2200, 1900], ["Evaluasi", "Yang Dinilai", "Cara dan Alat", "Kriteria Terpenuhi"], [
        ["*Requirement/user review*", "Kesesuaian kebutuhan, data yang dicatat, aturan pencatatan, batasan, dan peran", "Kuesioner tinjauan kebutuhan oleh GMLS",
         "Butir dinilai sesuai; butir yang perlu diubah ditindaklanjuti"],
        ["*Integrity*", "*Primary key*, *foreign key*, CHECK, UNIQUE, *trigger*, dan komentar setiap objek", "Uji otomatis pytest terhadap basis data uji",
         "Seluruh kasus uji lulus"],
        ["*Functional*", "Keluaran setiap fitur sesuai kebutuhan", "Skenario *black-box* per fitur melalui REST API (pytest)",
         "Hasil aktual sama dengan hasil yang diharapkan"],
        ["*Security*", "Hak akses per peran (GRANT, VIEW, *row-level security*), autentikasi, dan jejak audit", "Skrip matriks GRANT dan uji akses per peran",
         "Setiap akses tidak sah ditolak dan matriks sesuai rancangan"],
        ["*Query*", "Waktu eksekusi kueri inti, skalabilitas, dan konkurensi", "Benchmark PostgreSQL dan MySQL pada data yang sama",
         "Hasil kueri sama di kedua DBMS; waktu dilaporkan sebagai median dan persentil ke-95"],
        ["*Backup/recovery*", "Pemulihan dari cadangan dan pemulihan proses yang dihentikan paksa", "pg_dump dan pg_restore ke basis data kosong; proses *backfill* dihentikan dengan kill -9 lalu dijalankan ulang",
         "Isi hasil pemulihan identik; tidak ada pekerjaan ganda atau nilai yang salah"],
    ]))
    x.append(para("Lima evaluasi teknis dijalankan dengan skrip sehingga dapat diulang setiap kali kode atau skema "
                  "berubah, sedangkan tinjauan kebutuhan melibatkan pengguna dari GMLS. Bukti setiap evaluasi, berupa "
                  "keluaran pengujian, hasil benchmark, dan catatan pemulihan, disimpan bersama kode sumber agar hasil "
                  "pada BAB IV dapat diperiksa kembali."))
    x.append(para("Sebagai pelengkap evaluasi fungsional, aplikasi juga diuji coba oleh pengguna. Uji *black-box* "
                  "melalui REST API memastikan keluaran setiap fungsi benar, sedangkan uji coba pengguna menilai apakah "
                  "fungsi tersebut dapat diselesaikan oleh orang yang tidak mengenal sistem. Skenario uji coba "
                  "ditunjukkan pada Tabel 3.7."))
    x.append(caption("Tabel", 3, 7, "Skenario Uji Coba Pengguna"))
    x.append(table([600, 3300, 1500, 2500], ["Kode", "Skenario", "Akun", "Tanda Berhasil"], [
        ["S1", "Melihat keadaan di tempat pengguna berada", "Pengunjung", "Status kecamatan lokasi pengguna tampil di Beranda"],
        ["S2", "Mengatur pemberitahuan melalui surel", "Relawan", "Surel dan kecamatan langganan tersimpan"],
        ["S3", "Melihat citra satelit", "Pengunjung", "Citra tanggal yang dipilih tampil di peta"],
        ["S4", "Melihat riwayat kejadian bencana", "Pengunjung", "Daftar dan titik kejadian tampil di peta"],
        ["S5", "Mencatat kejadian bencana baru", "Analis", "Kejadian baru muncul di daftar kejadian"],
        ["S6", "Menindaklanjuti peringatan hujan", "Analis", "Peringatan berstatus sudah ditindaklanjuti"],
    ]))
    x.append(para("Untuk setiap skenario, responden memilih hasil berhasil, berhasil dengan kesulitan, tidak berhasil, "
                  "atau tidak dicoba, menilai kemudahan pada skala 1 (sangat sulit) hingga 5 (sangat mudah), dan "
                  "menuliskan kendala bila ada. S5 dan S6 bersifat pilihan karena merupakan tugas Analis. Di akhir "
                  "formulir, responden menilai apakah aplikasi layak dipakai, layak dengan perbaikan, atau tidak layak. "
                  "Setiap kendala yang ditemukan dikembalikan ke tahap implementasi."))
    return "".join(x)


# =====================================================================================================
# BAB IV (isi di bab4.py)
# =====================================================================================================
def bab4(fig_dir):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import bab4 as B
    blocks = B.blocks()
    num, cnt = {}, {"fig": 0, "tab": 0}
    for blk in blocks:
        if blk[0] in ("fig", "tab"):
            assert blk[1] not in num, blk[1]
            cnt[blk[0]] += 1
            num[blk[1]] = cnt[blk[0]]

    def refs(t):
        def r(m):
            kind, key = m.group(1), m.group(2)
            assert key in num, key
            return f"{'Gambar' if kind == 'G' else 'Tabel'} 4.{num[key]}"
        return re.sub(r"\{([GT]):([a-z_0-9]+)\}", r, t)

    out = []
    for blk in blocks:
        k = blk[0]
        if k == "p":
            out.append(para(refs(blk[1])))
        elif k == "list":
            out.append(items([refs(t) for t in blk[1]]))
        elif k == "h":
            out.append(head(blk[1], blk[2], 4))
        elif k == "eq":
            out.append('<w:p><w:pPr><w:spacing w:after="0" w:line="360" w:lineRule="auto"/><w:jc w:val="center"/></w:pPr>'
                       + runs(blk[1]) + "</w:p>")
        elif k == "fig":
            _, key, file, title, width = blk
            out.append(figure(os.path.join(fig_dir, file), width))
            out.append(caption("Gambar", 4, num[key], title))
        elif k == "tab":
            _, key, title, widths, header, rows = blk
            assert abs(sum(widths) - 7900) <= 100, (key, sum(widths))
            out.append(caption("Tabel", 4, num[key], title))
            out.append(table(widths, header, [[refs(c) for c in r] for r in rows]))
    print(f"BAB IV: {cnt['fig']} gambar, {cnt['tab']} tabel")
    return "".join(out)


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
        "Pada tinjauan kebutuhan, ketiga responden GMLS menilai K1 dan K3–K6 sesuai dan menyetujui rancangan, dua di "
        "antaranya dengan perbaikan. Masukan utamanya adalah agar pemberitahuan pada K2 dikirim ke ponsel, yang belum "
        "dapat diwujudkan karena layanan pesan ponsel berbayar. Pada uji coba oleh 13 pengguna, 62 dari 67 "
        "percobaan berhasil dengan rata-rata kemudahan 4,36 dari 5, dan seluruh responden menilai aplikasi layak "
        "dipakai, empat di antaranya dengan perbaikan.",
        "Kontrol akses berbasis peran dan jejak audit ditegakkan pada tingkat basis data (RM4). Lima peran aplikasi "
        "dipetakan ke lima role PostgreSQL yang diaktifkan dengan SET LOCAL ROLE pada setiap transaksi, dengan GRANT "
        "tingkat tabel dan kolom, VIEW dengan batas waktu per peran, dan *row-level security*, sedangkan setiap perubahan "
        "pada tabel penting dicatat trigger audit ke audit_log. Pengujian keamanan pada 165 kasus API dan 390 sel matriks "
        "GRANT menunjukkan bahwa akses yang tidak berhak ditolak oleh basis data walaupun pemeriksaan di API dimatikan.",
        "Keenam evaluasi minimum jalur *Design and Implementation* terpenuhi: tinjauan kebutuhan disetujui GMLS dengan perbaikan, pengujian "
        "otomatis menghasilkan 1.183 kasus lulus, 0 gagal, dan 2 dilewati dari 1.185 kasus, kelima kueri inti selesai di "
        "bawah 2 milidetik, dan pemulihan dari cadangan maupun dari proses yang dihentikan paksa menghasilkan data yang "
        "identik tanpa duplikasi.",
    ]
    saran = [
        "Bagi GMLS, kejadian bencana dari sumber pemerintah sebaiknya dicatat dan diverifikasi secara rutin agar evaluasi "
        "ketepatan peringatan melalui v_evaluasi_alert dapat disimpulkan dari data yang memadai.",
        "Ambang hujan pemicu longsor perlu ditetapkan dari literatur atau instansi pemerintah agar aturan peringatan "
        "longsor yang telah tersedia di basis data dapat diaktifkan.",
        "Pemberitahuan sebaiknya dikembangkan ke ponsel, misalnya melalui WhatsApp, SMS, atau notifikasi aplikasi, "
        "sesuai masukan Ketua GMLS bahwa masyarakat lebih terbiasa memakai ponsel daripada surel. Pengembangan ini "
        "membutuhkan anggaran untuk layanan pengiriman pesan, sehingga dapat diwujudkan bila GMLS atau mitranya "
        "menyediakan biaya tersebut; rancangan basis data yang ada dapat dipakai tanpa perubahan karena langganan "
        "kecamatan dan catatan pengiriman tidak bergantung pada kanal.",
        "Pencatatan kejadian oleh masyarakat di setiap kecamatan, sebagaimana diusulkan Relawan GMLS, dapat dikaji "
        "dengan tetap menandai catatan tersebut belum terverifikasi sampai diperiksa Analis.",
        "Antarmuka perlu disempurnakan sesuai masukan uji coba pengguna, yaitu huruf isi yang lebih besar dan tebal, "
        "subjudul yang dibedakan dari teks isi, bahasa yang lebih awam, serta petunjuk atau tutorial di dalam aplikasi.",
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
    "Language (UML). Data dikumpulkan melalui observasi, wawancara, pemeriksaan dokumen, studi pustaka, kuesioner tinjauan "
    "kebutuhan, dan uji coba pengguna. Hasilnya adalah basis data PostgreSQL dengan PostGIS, yang dipilih melalui perbandingan dengan MySQL 8.0 "
    "dengan skor terbobot 4,90 dibandingkan 2,90, berisi 43 tabel dan 22 VIEW. Basis data ini mengintegrasikan ketiga "
    "satelit ke dalam deret waktu per kecamatan, mencatat asal-usul data dengan checksum SHA-256 beserta mutunya, serta "
    "menegakkan kontrol akses lima peran dan jejak audit di tingkat basis data. Keenam evaluasi minimum, yaitu tinjauan "
    "kebutuhan, integritas, fungsional, keamanan, kueri, serta pencadangan dan pemulihan, terpenuhi dengan 1.183 dari "
    "1.185 kasus uji otomatis lulus dan 2 dilewati. GMLS menyetujui rancangan dengan perbaikan, dan pada uji coba "
    "oleh 13 pengguna, 62 dari 67 percobaan berhasil. Rancangan ini menyediakan sumber data hidrometeorologi terpusat yang "
    "dapat ditelusuri bagi GMLS.")
KATA_KUNCI = "Kata kunci: basis data spasial, DBSDLC, hidrometeorologi, kontrol akses berbasis peran, mitigasi bencana"
ABSTRACT = (
    "Gugus Mitigasi Lebak Selatan (GMLS) does not yet have stored and traceable hydrometeorological data per area, even "
    "though Sentinel-1, MODIS, and GPM IMERG satellite data are openly available in different formats, resolutions, and "
    "frequencies. This research designs and implements a hydrometeorological monitoring database system for GMLS using "
    "the Database System Development Life Cycle (DBSDLC) and the Unified Modeling Language (UML). Data were collected "
    "through observation, an interview, document examination, literature study, a requirements review questionnaire, and a user trial. The result "
    "is a PostgreSQL database with PostGIS, selected through a comparison with MySQL 8.0 with a weighted score of 4.90 "
    "against 2.90, containing 43 tables and 22 views. The database integrates the three satellites into a time series "
    "per sub-district, records data lineage with SHA-256 checksums together with data quality, and enforces access "
    "control for five roles and an audit trail at the database level. All six minimum evaluations, namely requirements "
    "review, integrity, functional, security, query, and backup and recovery, were met, with 1,183 of 1,185 automated "
    "test cases passing and 2 skipped. GMLS approved the design with revisions, and in a trial by 13 users, 62 of 67 "
    "attempts succeeded. The design provides GMLS with a centralized and traceable source of "
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

# =====================================================================================================
# Rakit dokumen
# =====================================================================================================
zin = zipfile.ZipFile(SRC)
doc = zin.read("word/document.xml").decode("utf-8")
numbering = zin.read("word/numbering.xml").decode("utf-8")
rels = zin.read("word/_rels/document.xml.rels").decode("utf-8")


def span(bookmark):
    pos = doc.find(f'w:name="{bookmark}"')
    assert pos > 0, bookmark
    return doc.rfind("<w:p ", 0, pos), doc.find("</w:p>", pos) + len("</w:p>")


B1 = bab1()
B2 = bab2()
B3 = bab3()
B4 = bab4(sys.argv[4])
B5 = bab5()
refs = "".join(
    '<w:p><w:pPr><w:spacing w:after="120" w:line="240" w:lineRule="auto"/><w:ind w:left="567" w:hanging="567"/>'
    f'<w:jc w:val="both"/></w:pPr>{runs(f"[{i}] " + REF[k])}</w:p>' for i, k in enumerate(ORDER, 1))
unused = [k for k in REF if k not in ORDER]
assert not unused, f"rujukan tidak dikutip: {unused}"

PAGEBREAK = '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'
# urutan dari belakang dokumen ke depan supaya posisi tidak bergeser
_, e = span("_Toc207196523")
s = span("_Toc207196524")[0]
doc = doc[:e] + refs + PAGEBREAK + doc[s:]
for bm in ["_Toc207196522", "_Toc207196521"]:   # 5.2 Saran, 5.1 Simpulan
    _, e = span(bm)
    s_next = doc.find("<w:p", e)
    doc = doc[:e] + B5[bm] + doc[e:]
_, e = span("_Toc207196505")                 # BAB IV
s = span("_Toc207196520")[0]                 # BAB V
doc = doc[:e] + B4 + PAGEBREAK + doc[s:]
_, e = span("_Toc207196487")                 # BAB III
s = span("_Toc207196505")[0]                 # BAB IV
doc = doc[:e] + B3 + PAGEBREAK + doc[s:]
_, e = span("_Toc207196480")                 # BAB II
s = span("_Toc207196487")[0]
doc = doc[:e] + B2 + PAGEBREAK + doc[s:]
for bm in ["_Toc207196479", "_Toc207196478", "_Toc207196477", "_Toc207196475", "_Toc207196474"]:
    _, e = span(bm)
    doc = doc[:e] + B1[bm] + doc[e:]
_, e = span("_Toc207196473")
s = span("_Toc207196474")[0]
doc = doc[:e] + B1["_Toc207196473"] + doc[s:]

doc = front_matter(doc)

# numbering daftar bernomor
absnum = ('<w:abstractNum w:abstractNumId="201"><w:multiLevelType w:val="singleLevel"/>'
          '<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/>'
          '<w:lvlJc w:val="left"/><w:pPr><w:ind w:left="567" w:hanging="425"/></w:pPr>'
          f'<w:rPr>{FONT}</w:rPr></w:lvl></w:abstractNum>')
nums = "".join(f'<w:num w:numId="{n}"><w:abstractNumId w:val="201"/>'
               '<w:lvlOverride w:ilvl="0"><w:startOverride w:val="1"/></w:lvlOverride></w:num>' for n in NUM_IDS)
i = numbering.find("<w:num ")
numbering = numbering[:i] + absnum + numbering[i:]
numbering = numbering.replace("</w:numbering>", nums + "</w:numbering>")

rels = rels.replace("</Relationships>", "".join(
    f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
    f'Target="media/{name}"/>' for rid, name, _ in IMAGES) + "</Relationships>")

with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zout:
    for item in zin.infolist():
        data = zin.read(item.filename)
        if item.filename == "word/document.xml":
            data = doc.encode("utf-8")
        elif item.filename == "word/numbering.xml":
            data = numbering.encode("utf-8")
        elif item.filename == "word/_rels/document.xml.rels":
            data = rels.encode("utf-8")
        elif item.filename == "word/settings.xml":
            st = data.decode("utf-8")
            if "w:updateFields" not in st:
                anchor = next(t for t in ("<w:hdrShapeDefaults", "<w:footnotePr", "<w:endnotePr", "<w:compat", "<w:rsids")
                              if t in st)
                i = st.index(anchor)
                st = st[:i] + '<w:updateFields w:val="true"/>' + st[i:]
            data = st.encode("utf-8")
        zout.writestr(item, data)
    for _, name, path in IMAGES:
        zout.write(path, f"word/media/{name}")

print(f"rujukan dikutip: {len(ORDER)}; gambar: {len(IMAGES)}; daftar bernomor: {len(NUM_IDS)}")
