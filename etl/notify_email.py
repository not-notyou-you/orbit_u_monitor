# etl/notify_email.py
"""Isi email peringatan dan konfirmasi (M64), Bahasa Indonesia.

Satu email dibaca dua jenis pembaca: Relawan (awam) dan analis/data
engineer. Karena itu tiap kecamatan disusun berlapis:

1. Ringkasnya   -- status + bahasa sehari-hari: apa yang terjadi, artinya,
                   dan saran umum; selalu ditutup "bukan peringatan dini resmi".
2. Bukti        -- citra scene terbaru yang dipotong ke kecamatan (ditempel
                   inline, CID) dan tabel nilai · ambang · sebelumnya ·
                   rentang biasa · tanggal data.
3. Detail teknis -- kalimat aturan lengkap, produk sumber dan run, bagian
                   kecamatan yang teramati, sumber ambang, metode rentang
                   biasa, keterbatasan.

HTML memakai tabel + CSS inline (klien email tidak membaca <style> dengan
andal) dan selalu disertai versi teks polos.
"""
from __future__ import annotations

from datetime import date
from html import escape

from etl.live_interpret import fmt

BULAN = ("Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des")
LEVEL_COLOR = {2: "#b00020", 1: "#9a5b00", 0: "#1b6b3a", -1: "#555555"}

# Bahasa sehari-hari per butir: (judul, artinya, saran).
PLAIN: dict[str, tuple[str, str, str]] = {
    "gpm_rain_24h": ("Hujan sangat deras dalam sehari",
                     "Curah hujan satu hari (07.00–07.00 WIB) melewati batas hujan lebat.",
                     "Waspadai genangan di daerah rendah, saluran air, dan tepi sungai."),
    "gpm_rain_72h": ("Hujan deras selama tiga hari",
                     "Hujan menumpuk selama tiga hari sehingga tanah makin jenuh air.",
                     "Waspadai genangan dan tanah longsor di lereng."),
    "gpm_rain_7d": ("Hujan menumpuk selama seminggu",
                    "Jumlah hujan tujuh hari terakhir tinggi; tanah cenderung jenuh air.",
                    "Perhatikan retakan tanah di lereng dan sungai yang naik."),
    "s1_vh": ("Permukaan yang tampak tergenang bertambah",
              "Radar satelit melihat lebih banyak permukaan yang memantulkan seperti air dibanding lintasan sebelumnya.",
              "Bisa sawah/lahan yang tergenang atau banjir; pastikan kondisi di lapangan."),
    "s1_vv": ("Permukaan tanah tampak lebih basah",
              "Pantulan radar turun dibanding lintasan sebelumnya; permukaan tampak lebih basah atau tergenang.",
              "Pantau genangan dan cocokkan dengan kondisi di lapangan."),
    "modis_flood": ("Satelit optik melihat genangan",
                    "Sebagian area kecamatan yang terlihat dari satelit diklasifikasikan sebagai banjir.",
                    "Periksa daerah rendah dan bantaran sungai."),
    "modis_ndwi": ("Permukaan tampak lebih basah dari biasanya",
                   "Indeks air dari citra optik berada di atas batas biasa kecamatan ini.",
                   "Bisa genangan atau lahan basah; pastikan kondisi di lapangan."),
    "modis_ndvi": ("Kehijauan tanaman menurun tajam",
                   "Vegetasi tampak jauh kurang hijau dibanding pengamatan sebelumnya.",
                   "Bisa karena kekeringan, banjir, panen, atau awan; periksa kebun dan sawah."),
    "alert": ("Alert hujan BMKG",
              "Hujan satu hari melewati ambang kategori BMKG (lebat ≥ 50, sangat lebat ≥ 100, ekstrem ≥ 150 mm).",
              "Ikuti informasi BMKG dan BPBD setempat."),
}

# Produk sumber per band, untuk lapisan teknis.
SOURCE: dict[str, str] = {
    "VV": "Sentinel-1 GRD IW (ESA Copernicus), backscatter VV rerata kecamatan per lintasan",
    "VH": "Sentinel-1 GRD IW (ESA Copernicus), backscatter VH rerata kecamatan per lintasan",
    "WATER_PCT": "Sentinel-1 GRD IW, persen piksel kecamatan dengan VH di bawah ambang air",
    "FLOOD": "MODIS MCDWD (NASA LANCE), persen area teramati berkelas banjir",
    "NDVI": "MODIS MOD09 (NASA), komposit 8 hari, rerata kecamatan",
    "NDWI": "MODIS MOD09 (NASA), komposit 8 hari, rerata kecamatan",
    "RAIN_24H": "GPM IMERG (NASA/JAXA), akumulasi 24 jam rerata kecamatan",
    "RAIN_72H": "GPM IMERG (NASA/JAXA), akumulasi 72 jam rerata kecamatan",
    "RAIN_7D": "GPM IMERG (NASA/JAXA), akumulasi 7 hari rerata kecamatan",
}
RUN = {"F": "Final", "L": "Late (sementara)", "E": "Early (sementara)"}
# Indeks memakai 3 desimal di tabel bukti: dengan 2 desimal nilai yang sedikit
# di atas batas rentang biasa tampak sama dengan batasnya.
DIGITS = {"NDVI": 3, "NDWI": 3}

# Tile citra yang paling menjelaskan tiap butir.
IMAGE_KEYS: dict[str, tuple[str, ...]] = {
    "s1_vv": ("s1_vv",), "s1_vh": ("s1_vh", "s1_water_change"), "modis_flood": ("modis_flood",),
    "modis_ndvi": ("modis_ndvi",), "modis_ndwi": ("modis_ndwi",), "gpm_rain_24h": ("gpm_rain_24h",),
    "gpm_rain_72h": ("gpm_rain_72h",), "gpm_rain_7d": ("gpm_rain_7d",), "alert": ("gpm_rain_24h",),
}

LIMITS = (
    "Ini bukan peringatan dini resmi. Untuk keputusan evakuasi, ikuti BMKG dan BPBD.",
    "Sentinel-1 melintas ±6–12 hari sekali; banjir yang naik dan surut dalam beberapa jam bisa terlewat.",
    "Angka hujan adalah perkiraan satelit (petak ±10 km), belum dikalibrasi penakar hujan lapangan; run Late/Early bisa berubah.",
    "MODIS tidak menembus awan; data kosong bukan berarti aman.",
)


def tgl(d) -> str:
    if d is None:
        return "—"
    if isinstance(d, str):
        d = date.fromisoformat(d[:10])
    return f"{d.day} {BULAN[d.month - 1]} {d.year}"


def _val(band: str, v, unit: str | None) -> str:
    if v is None:
        return "—"
    u = "" if not unit or unit in ("index", "indeks") else f" {unit}"
    return fmt(v, DIGITS.get(band, 1)) + u


# ---------------------------------------------------------------- konfirmasi

def confirmation_message(name: str, email: str, cfg) -> tuple[str, str, str]:
    akun = cfg.link("/app#sistem/akun")
    subject = "Orbit-U · Email Anda tersimpan untuk peringatan kondisi"
    lines = [
        f"Halo {name},",
        "",
        f"Alamat {email} sekarang tersimpan di akun Orbit-U: The Monitor Anda.",
        "Peringatan email dikirim hanya untuk kecamatan yang Anda pilih di Akun saya.",
        "Tanpa kecamatan yang dipilih, Anda tidak menerima peringatan.",
    ]
    if akun:
        lines += ["", f"Pilih kecamatan: {akun}"]
    lines += ["", "Bila Anda tidak merasa menyimpan email ini, abaikan pesan ini atau hubungi Admin GMLS.",
              "", "Orbit-U: The Monitor — Gugus Mitigasi Lebak Selatan (GMLS)"]
    text = "\n".join(lines)
    html = _page(
        f"<p style='margin:0 0 12px'>Halo {escape(name)},</p>"
        f"<p style='margin:0 0 12px'>Alamat <b>{escape(email)}</b> sekarang tersimpan di akun "
        "Orbit-U: The Monitor Anda.</p>"
        "<p style='margin:0 0 12px'>Peringatan email dikirim hanya untuk kecamatan yang Anda pilih di "
        "<b>Akun saya</b>. Tanpa kecamatan yang dipilih, Anda tidak menerima peringatan.</p>"
        + (f"<p style='margin:0 0 12px'><a href='{escape(akun)}' style='color:#0b4f9c'>Pilih kecamatan</a></p>" if akun else "")
        + "<p style='margin:0;color:#555;font-size:12px'>Bila Anda tidak merasa menyimpan email ini, abaikan "
        "pesan ini atau hubungi Admin GMLS.</p>")
    return subject, text, html


# ---------------------------------------------------------------- peringatan

def alert_message(name: str, regions: list[dict], cfg, units: dict[str, str], thresholds) -> tuple[str, str, str, list]:
    """regions: [{region, status, items(baru), all_abnormal, latest, prev, ranges,
    scene_date, images:[(cid, key, label, png)]}]. thresholds(band) ->
    [{label, value}] (etl.band_catalog.thresholds).

    Mengembalikan (subjek, teks, html, [(cid, png)])."""
    worst = max(r["status"]["level"] for r in regions)
    if len(regions) == 1:
        r = regions[0]
        first = PLAIN.get(r["items"][0]["key"], (r["items"][0]["what"],))[0].lower()
        subject = (f"Orbit-U · {r['status']['label']} di {r['region']['name']}: {first}"
                   f" (data {tgl(max(i['date'] for i in r['items']))})")
    else:
        names = ", ".join(r["region"]["name"] for r in regions)
        subject = f"Orbit-U · {len(regions)} kecamatan tidak normal: {names}"

    text = [f"Halo {name},", "",
            "Data satelit terbaru menunjukkan kondisi tidak normal di kecamatan yang Anda pantau.",
            "Ini bukan peringatan dini resmi — ikuti BMKG dan BPBD.", ""]
    body = (f"<p style='margin:0 0 8px'>Halo {escape(name)},</p>"
            "<p style='margin:0 0 4px'>Data satelit terbaru menunjukkan <b>kondisi tidak normal</b> di "
            "kecamatan yang Anda pantau.</p>"
            "<p style='margin:0 0 16px;color:#9a5b00'><b>Ini bukan peringatan dini resmi.</b> "
            "Untuk keputusan evakuasi, ikuti BMKG dan BPBD.</p>")
    images: list[tuple[str, bytes]] = []
    for r in regions:
        t, h, imgs = _region_block(r, cfg, units, thresholds)
        text += t
        body += h
        images += imgs

    akun = cfg.link("/app#sistem/akun")
    beranda = cfg.link("/app#beranda")
    names = ", ".join(r["region"]["name"] for r in regions)
    foot_t = [f"Anda menerima email ini karena memilih kecamatan {names} di Akun saya."]
    foot_h = f"Anda menerima email ini karena memilih kecamatan <b>{escape(names)}</b> di Akun saya."
    if akun:
        foot_t.append(f"Ubah kecamatan atau berhenti menerima peringatan: {akun}")
        foot_h += f" <a href='{escape(akun)}' style='color:#0b4f9c'>Ubah kecamatan atau berhenti</a>."
    if beranda:
        foot_t.append(f"Lihat kondisi terkini di Beranda: {beranda}")
        foot_h += f" <a href='{escape(beranda)}' style='color:#0b4f9c'>Buka Beranda</a>."
    text += ["—", *foot_t, "Orbit-U: The Monitor — Gugus Mitigasi Lebak Selatan (GMLS)"]
    body += (f"<p style='margin:16px 0 0;padding-top:8px;border-top:1px solid #ddd;color:#555;font-size:12px'>"
             f"{foot_h}</p>")
    return subject, "\n".join(text), _page(body, accent=LEVEL_COLOR.get(worst, "#555")), images


def _region_block(r: dict, cfg, units, thresholds) -> tuple[list[str], str, list]:
    reg, st = r["region"], r["status"]
    color = LEVEL_COLOR.get(st["level"], "#555")
    t = [f"== Kecamatan {reg['name']}: {st['label'].upper()} ==", "", "RINGKASNYA"]
    h = (f"<div style='border:1px solid #ccc;border-left:6px solid {color};padding:12px 14px;margin:0 0 16px'>"
         f"<h2 style='margin:0 0 4px;font-size:18px'>Kecamatan {escape(reg['name'])} "
         f"<span style='color:{color}'>· {escape(st['label'].upper())}</span></h2>"
         f"<p style='margin:0 0 10px;color:#555;font-size:12px'>{escape(st['text'])}</p>"
         "<h3 style='margin:8px 0 4px;font-size:14px'>Ringkasnya</h3><ul style='margin:0 0 8px;padding-left:18px'>")
    for it in r["items"]:
        title, meaning, advice = PLAIN.get(it["key"], (it["what"], it["because"], ""))
        t.append(f"- {title}. {meaning} {advice} (data {tgl(it['date'])})")
        h += (f"<li style='margin:0 0 6px'><b>{escape(title)}.</b> {escape(meaning)} "
              f"<i>{escape(advice)}</i> <span style='color:#555'>(data {escape(tgl(it['date']))})</span></li>")
    h += "</ul>"

    # Bukti: gambar + tabel
    imgs = []
    t += ["", "BUKTI"]
    h += "<h3 style='margin:12px 0 4px;font-size:14px'>Bukti</h3>"
    if r.get("images"):
        h += "<div>"
        for cid, key, label, png in r["images"]:
            imgs.append((cid, png))
            h += (f"<div style='display:inline-block;vertical-align:top;width:200px;margin:0 8px 8px 0'>"
                  f"<img src='cid:{cid}' alt='{escape(label)}' width='200' "
                  "style='display:block;width:200px;height:auto;background:#000;border:1px solid #999'>"
                  f"<div style='font-size:11px;color:#555'>{escape(label)}</div></div>")
            t.append(f"- Citra {label} (terlampir di versi HTML)")
        h += ("</div><p style='margin:0 0 8px;font-size:11px;color:#555'>Citra scene Live terbaru "
              f"{escape(tgl(r.get('scene_date')))}, dipotong ke batas Kecamatan {escape(reg['name'])} "
              "(di luar batas transparan). MODIS/GPM memakai data terdekat dengan tanggal scene.</p>")
    else:
        h += "<p style='margin:0 0 8px;font-size:12px;color:#555'>Belum ada citra yang menutupi kecamatan ini.</p>"
    head = ("Indikator", "Nilai", "Ambang", "Sebelumnya", "Rentang biasa", "Tanggal data")
    h += ("<table cellpadding='4' cellspacing='0' style='border-collapse:collapse;font-size:12px;width:100%'>"
          "<tr>" + "".join(f"<th align='left' style='border-bottom:2px solid #999'>{c}</th>" for c in head) + "</tr>")
    for it in r["items"]:
        b = it["band"]
        unit = units.get(b)
        if it["key"] == "alert":
            val, thr = _val(b, it.get("observed_value"), "mm"), _val(b, it.get("threshold_value"), "mm")
            prev, rng = "—", "—"
        else:
            val = _val(b, (r["latest"].get(b) or {}).get("value"), unit)
            thr = "; ".join(f"{x['label']} {_val(b, x['value'], unit)}" for x in thresholds(b)) or "perubahan antar pengamatan"
            prev = _val(b, (r["prev"].get(b) or {}).get("value"), unit)
            rg = r["ranges"].get(b) or {}
            rng = (f"{_val(b, rg.get('p02'), None)} s.d. {_val(b, rg.get('p98'), unit)}"
                   if rg.get("p02") is not None else "—")
        label = PLAIN.get(it["key"], (it["what"],))[0] if it["key"] == "alert" else it["what"]
        cells = (label, val, thr, prev, rng, tgl(it["date"]))
        t.append("- " + " | ".join(f"{k}: {v}" for k, v in zip(head, cells)))
        h += "<tr>" + "".join(f"<td style='border-bottom:1px solid #ddd;vertical-align:top'>{escape(str(c))}</td>"
                              for c in cells) + "</tr>"
    h += "</table>"

    # Detail teknis
    t += ["", "DETAIL TEKNIS"]
    h += ("<h3 style='margin:12px 0 4px;font-size:14px'>Detail teknis</h3>"
          "<ul style='margin:0;padding-left:18px;font-size:12px;color:#333'>")
    for it in r["items"]:
        b = it["band"]
        e = r["latest"].get(b) or {}
        bits = [f"{it['what']}: {it['because']}."]
        if b in SOURCE:
            bits.append(f"Sumber: {SOURCE[b]}" + (f", run {RUN.get(e.get('run_type'), e.get('run_type'))}"
                                                  if e.get("run_type") else "") + ".")
        if e.get("valid_fraction") is not None:
            bits.append(f"Bagian kecamatan yang teramati: {fmt(e['valid_fraction'] * 100, 0)}%.")
        line = " ".join(bits)
        t.append(f"- {line}")
        h += f"<li style='margin:0 0 4px'>{escape(line)}</li>"
    method = ("Ambang hujan = aturan alert BMKG yang aktif di Orbit-U (lebat ≥ 50, sangat lebat ≥ 100 mm/hari); "
              "ambang radar dan optik dari literatur penginderaan jauh banjir (mis. VH < −20 dB untuk air terbuka, "
              "NDWI > 0). Rentang biasa = persentil 2–98 nilai kecamatan ini selama 365 hari.")
    t.append(f"- Metode: {method}")
    h += f"<li style='margin:0 0 4px'>Metode: {escape(method)}</li>"
    for lim in LIMITS:
        t.append(f"- {lim}")
        h += f"<li style='margin:0 0 4px;color:#555'>{escape(lim)}</li>"
    h += "</ul></div>"
    t.append("")
    return t, h, imgs


def _page(body: str, accent: str = "#0b4f9c") -> str:
    return ("<!doctype html><html lang='id'><body style='margin:0;padding:0;background:#f2f2f2'>"
            "<table role='presentation' width='100%' cellpadding='0' cellspacing='0' style='background:#f2f2f2'>"
            "<tr><td align='center' style='padding:16px 8px'>"
            "<table role='presentation' width='640' cellpadding='0' cellspacing='0' "
            "style='max-width:640px;width:100%;background:#ffffff;font-family:Segoe UI,Arial,sans-serif;"
            "font-size:14px;line-height:1.5;color:#111'>"
            f"<tr><td style='background:{accent};color:#fff;padding:10px 16px;font-weight:bold'>"
            "Orbit-U: The Monitor · Pantauan Hidrometeorologi Lebak Selatan</td></tr>"
            f"<tr><td style='padding:16px'>{body}</td></tr>"
            "</table></td></tr></table></body></html>")
