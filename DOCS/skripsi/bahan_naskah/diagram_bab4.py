"""Diagram BAB IV yang ditata manual: ERD konseptual Crow's Foot per area subjek dan state machine status job dataset.

Setiap kotak diberi posisi tetap dan setiap garis diberi port (titik di sisi kotak, koordinat absolut) sehingga
semua garis hanya horizontal/vertikal dengan sudut membulat. SVG dibangun dan diukur di Chromium (Playwright),
lalu disimpan sebagai PNG. Warna dan huruf (Lexend) mengikuti gambar BAB IV lainnya.

Isi diagram mengikuti kode: atribut dan kunci alami dari database/monitor_schema.sql (nama bisnis), status job dari
CHECK chk_dataset_job_status, pembatalan dari etl/dataset_manager.py, batas tunggu dari hydromet.waiting_max_days = 3.

Pemakaian: python diagram_bab4.py <folder keluaran>
Keluaran: erd_a.png, erd_b.png, erd_c.png, state_job.png, erd_cf.png
"""
import json, pathlib, sys
from playwright.sync_api import sync_playwright

C0, C1, C2 = 30, 480, 930


def ent(x, y, *attrs):
    """attrs: 'nama:domain' atau 'PK nama:domain' / 'UK nama:domain'."""
    rows = []
    for a in attrs:
        key, rest = (a.split(" ", 1) if a[:3] in ("PK ", "UK ") else ("", a))
        name, dom = rest.split(":")
        rows.append([key, name, dom])
    return {"x": x, "y": y, "rows": rows}


def E(a, sa, pa, ma, b, sb, pb, mb, label="", via=None, lp=None):
    return {"a": a, "sa": sa, "pa": pa, "ma": ma, "b": b, "sb": sb, "pb": pb, "mb": mb,
            "label": label, "via": via, "lp": lp}


# ---------------------------------------------------------------- Area Pemantauan
ERD_A = {"w": 250, "nodes": {
    "VARIABEL": ent(C0, 40, "PK kode_band:teks", "nama:teks", "satuan:teks", "batas_min:desimal", "batas_maks:desimal"),
    "OBSERVASI": ent(C1, 40, "tanggal:tanggal", "nilai:desimal", "fraksi_valid:desimal", "run_GPM:teks"),
    "ATURAN_PERINGATAN": ent(C0, 310, "PK kode_aturan:teks", "pembanding:teks", "ambang:desimal", "severity:teks", "aktif:logika"),
    "PERINGATAN": ent(C1, 310, "tanggal:tanggal", "nilai_teramati:desimal", "ambang_saat_itu:desimal", "waktu_ack:waktu"),
    "WILAYAH": ent(C2, 310, "PK pcode:teks", "nama:teks", "level:teks", "geometri:geometri", "in_aoi:logika"),
    "JENIS_BENCANA": ent(C0, 590, "PK kode_jenis:teks", "nama:teks"),
    "KEJADIAN": ent(C1, 590, "tanggal:tanggal", "desa:teks", "keterangan:teks", "sumber_info:teks", "terverifikasi:logika"),
    "PENGGUNA": ent(C2, 590, "PK username:teks", "nama:teks", "email:teks"),
}, "edges": [
    E("VARIABEL", "R", 110, "one", "OBSERVASI", "L", 110, "zero_many", "nilai dari"),
    E("VARIABEL", "B", C0 + 125, "one", "ATURAN_PERINGATAN", "T", C0 + 125, "zero_many", "diuji pada"),
    E("JENIS_BENCANA", "T", C0 + 125, "one", "ATURAN_PERINGATAN", "B", C0 + 125, "zero_many", "dipicu oleh"),
    E("OBSERVASI", "B", C1 + 125, "one", "PERINGATAN", "T", C1 + 125, "zero_many", "memicu"),
    E("ATURAN_PERINGATAN", "R", 390, "one", "PERINGATAN", "L", 390, "zero_many", "menghasilkan"),
    E("WILAYAH", "L", 360, "one", "PERINGATAN", "R", 360, "zero_many", "terjadi di"),
    E("WILAYAH", "T", C2 + 125, "one", "OBSERVASI", "R", 110, "zero_many", "diamati di"),
    E("WILAYAH", "R", 350, "zero_one", "WILAYAH", "R", 440, "zero_many", "induk dari",
      via=[[C2 + 300, 350], [C2 + 300, 440]], lp=[C2 + 312, 395, "start"]),
    E("WILAYAH", "B", C2 + 60, "one", "KEJADIAN", "T", C1 + 180, "zero_many", "lokasi", via=[[C2 + 60, 525], [C1 + 180, 525]]),
    E("PENGGUNA", "T", C2 + 180, "zero_one", "PERINGATAN", "B", C1 + 60, "zero_many", "menindaklanjuti",
      via=[[C2 + 180, 556], [C1 + 60, 556]], lp=[(C1 + C2) / 2 + 160, 556]),
    E("JENIS_BENCANA", "R", 640, "one", "KEJADIAN", "L", 640, "zero_many", "jenis"),
    E("PENGGUNA", "L", 630, "one", "KEJADIAN", "R", 630, "zero_many", "mencatat"),
    E("PENGGUNA", "L", 685, "zero_one", "KEJADIAN", "R", 685, "zero_many", "memverifikasi"),
]}

# ---------------------------------------------------------------- Area Akuisisi dan Lineage
ERD_B = {"w": 260, "nodes": {
    "AREA_PANTAUAN": ent(C1, 40, "PK kode_area:teks", "nama:teks", "bbox:geometri"),
    "SUMBER_SATELIT": ent(C2, 40, "PK kode_sumber:teks", "nama:teks", "penyedia:teks"),
    "SCENE_S1": ent(C0, 250, "PK id_produk_ESA:teks", "waktu_akuisisi:waktu", "orbit:teks", "valid:logika"),
    "GRANULE_NASA": ent(C1, 250, "PK sumber:teks", "PK tile:teks", "PK produk:teks", "PK tanggal:tanggal",
                        "run_type:teks", "valid:logika"),
    "JOB_PROSES": ent(C1, 540, "status:teks", "parameter:json", "percobaan:bilangan", "durasi:desimal"),
    "TAHAP_PROSES": ent(C2, 540, "PK kode_tahap:teks", "urutan:bilangan"),
    "METRIK_MUTU": ent(C0, 790, "band:teks", "skor_mutu:desimal", "status_QA:teks"),
    "PRODUK_DATA": ent(C1, 790, "PK path_berkas:teks", "tier:teks", "checksum_SHA256:teks", "ukuran:bilangan"),
    "DATASET": ent(C2, 790, "PK nama:teks", "jenis:teks", "rentang_tanggal:teks", "status:teks"),
}, "edges": [
    E("AREA_PANTAUAN", "L", 100, "one", "SCENE_S1", "T", C0 + 130, "zero_many", "mencakup"),
    E("AREA_PANTAUAN", "B", C1 + 130, "one", "GRANULE_NASA", "T", C1 + 130, "zero_many", "mencakup"),
    E("SUMBER_SATELIT", "B", C2 + 130, "one", "GRANULE_NASA", "R", 300, "zero_many", "menerbitkan"),
    E("GRANULE_NASA", "B", C1 + 130, "zero_one", "JOB_PROSES", "T", C1 + 130, "zero_many", "diproses"),
    E("SCENE_S1", "B", C0 + 200, "zero_one", "JOB_PROSES", "L", 600, "zero_many", "diproses"),
    E("TAHAP_PROSES", "L", 590, "one", "JOB_PROSES", "R", 590, "zero_many", "tahap"),
    E("JOB_PROSES", "B", C1 + 130, "one", "PRODUK_DATA", "T", C1 + 130, "zero_many", "menulis"),
    E("DATASET", "L", 860, "zero_one", "PRODUK_DATA", "R", 860, "zero_many", "memiliki"),
    E("PRODUK_DATA", "L", 850, "one", "METRIK_MUTU", "R", 850, "zero_many", "diukur"),
    E("SCENE_S1", "B", C0 + 70, "one", "METRIK_MUTU", "T", C0 + 70, "zero_many", "dinilai"),
    E("PRODUK_DATA", "B", C1 + 70, "zero_many", "PRODUK_DATA", "B", C1 + 190, "zero_many", "lineage induk-anak",
      via=[[C1 + 70, 975], [C1 + 190, 975]], lp=[C1 + 130, 975]),
]}

# ---------------------------------------------------------------- Area Akses dan Jejak
ERD_C = {"w": 260, "nodes": {
    "LOG_AUDIT": ent(C0, 40, "tabel:teks", "operasi:teks", "data_lama:json", "data_baru:json", "waktu:waktu"),
    "TOKEN_API": ent(C1, 40, "PK prefix:teks", "hash:teks", "scope:teks", "kedaluwarsa:waktu"),
    "LOG_AKTIVITAS": ent(C2, 40, "aksi:teks", "IP:teks", "waktu:waktu"),
    "PERAN": ent(C0, 300, "PK kode_peran:teks", "UK role_DB:teks", "label:teks"),
    "PENGGUNA": ent(C1, 300, "PK username:teks", "nama:teks", "email:teks", "organisasi:teks", "aktif:logika"),
    "KECAMATAN": ent(C2, 300, "PK pcode:teks", "nama:teks"),
    "JENIS_LAPORAN": ent(C0, 560, "PK kode_laporan:teks", "periode:teks"),
    "PERINGATAN_TERKIRIM": ent(C2, 560, "butir:teks", "tingkat:teks", "tanggal_data:tanggal"),
    "LAPORAN": ent(C0, 750, "periode_mulai:tanggal", "status:teks", "checksum:teks"),
}, "edges": [
    E("PERAN", "R", 360, "one", "PENGGUNA", "L", 360, "zero_many", "dimiliki"),
    E("PENGGUNA", "T", C1 + 130, "one", "TOKEN_API", "B", C1 + 130, "zero_many", "memiliki"),
    E("PENGGUNA", "T", C1 + 220, "zero_one", "LOG_AKTIVITAS", "B", C2 + 60, "zero_many", "melakukan", via=[[C1 + 220, 240], [C2 + 60, 240]]),
    E("PENGGUNA", "R", 340, "zero_many", "KECAMATAN", "L", 340, "zero_many", "berlangganan"),
    E("PENGGUNA", "R", 405, "zero_one", "PENGGUNA", "R", 450, "zero_many", "membuat akun",
      via=[[C1 + 300, 405], [C1 + 300, 450]], lp=[C1 + 312, 427, "start"]),
    E("PENGGUNA", "B", C1 + 130, "one", "PERINGATAN_TERKIRIM", "L", 620, "zero_many", "menerima"),
    E("KECAMATAN", "B", C2 + 130, "one", "PERINGATAN_TERKIRIM", "T", C2 + 130, "zero_many", "tentang"),
    E("PERAN", "B", C0 + 130, "one", "JENIS_LAPORAN", "T", C0 + 130, "zero_many", "audiens"),
    E("JENIS_LAPORAN", "B", C0 + 130, "one", "LAPORAN", "T", C0 + 130, "zero_many", "jenis"),
]}

# ---------------------------------------------------------------- State machine dataset_jobs
ST = lambda cx, cy: {"cx": cx, "cy": cy}
STATE = {"group": {"label": "BERJALAN", "x": 350, "y": 195, "w": 860, "h": 130}, "nodes": {
    "start": {"cx": 40, "cy": 260, "kind": "init"},
    "QUEUED": ST(160, 260), "PREPARING": ST(460, 260), "DOWNLOADING": ST(680, 260),
    "PROCESSING": ST(910, 260), "CLEANUP": ST(1120, 260), "COMPLETED": ST(1390, 260),
    "stop": {"cx": 1560, "cy": 260, "kind": "final"},
    "WAITING_UPSTREAM": ST(680, 90), "FAILED": ST(1120, 90),
    "PAUSED": ST(795, 430), "CANCELLED": ST(1390, 430),
    "grp": {"kind": "group"},
}, "edges": [
    E("start", "R", 260, "none", "QUEUED", "L", 260, "arrow", "job dibuat", lp=[85, 238]),
    E("QUEUED", "R", 260, "none", "PREPARING", "L", 260, "arrow", "worker mengambil", lp=[290, 238]),
    E("PREPARING", "R", 260, "none", "DOWNLOADING", "L", 260, "arrow"),
    E("DOWNLOADING", "R", 260, "none", "PROCESSING", "L", 260, "arrow"),
    E("PROCESSING", "R", 260, "none", "CLEANUP", "L", 260, "arrow"),
    E("CLEANUP", "R", 260, "none", "COMPLETED", "L", 260, "arrow", "semua unit\nselesai", lp=[1265, 232]),
    E("COMPLETED", "R", 260, "none", "stop", "L", 260, "arrow"),
    E("DOWNLOADING", "T", 680, "none", "WAITING_UPSTREAM", "B", 680, "arrow",
      "[HYDROMET_DAILY]\ngranule GPM belum terbit", lp=[680, 154]),
    E("WAITING_UPSTREAM", "L", 90, "none", "QUEUED", "T", 160, "arrow", "dicoba lagi (≤ 3 hari)", lp=[390, 90]),
    E("WAITING_UPSTREAM", "R", 90, "none", "FAILED", "L", 90, "arrow", "> 3 hari"),
    E("grp", "T", 1120, "none", "FAILED", "B", 1120, "arrow", "galat"),
    E("FAILED", "R", 90, "none", "stop", "T", 1560, "arrow"),
    E("grp", "B", 795, "none", "PAUSED", "T", 795, "arrow", "dijeda"),
    E("PAUSED", "L", 430, "none", "PREPARING", "B", 460, "arrow", "dilanjutkan (resume_count+1)", lp=[600, 430]),
    E("grp", "B", 1120, "none", "CANCELLED", "L", 418, "arrow", "dibatalkan\n(sebelum CLEANUP)", lp=[1225, 384]),
    E("PAUSED", "R", 442, "none", "CANCELLED", "L", 442, "arrow", "dibatalkan", lp=[1000, 442]),
    E("QUEUED", "B", 160, "none", "CANCELLED", "B", 1390, "arrow", "dibatalkan", via=[[160, 520], [1390, 520]]),
    E("CANCELLED", "R", 430, "none", "stop", "B", 1560, "arrow"),
]}

# ---------------------------------------------------------------- ERD konseptual ringkas (keterhubungan antararea)
# Entitas dikelompokkan per area subjek; yang digambar hanya relasi antararea dan relasi FORECAST
# (relasi di dalam area sudah ada pada ERD konseptual per area).
_C = [40 + 240 * i for i in range(5)]
_BW, _BH = 190, 40
_box = lambda col, y, name: (name, {"x": _C[col], "y": y, "w": _BW, "h": _BH, "label": name})
_mid = lambda col: _C[col] + _BW // 2
ERD_CF = {"groups": [
    {"name": "akses", "x": 20, "y": 20, "w": 1190, "h": 250, "label": "AKSES DAN JEJAK", "align": "start"},
    {"name": "pantau", "x": 20, "y": 410, "w": 1190, "h": 250, "label": "PEMANTAUAN", "align": "start"},
    {"name": "akuisisi", "x": 20, "y": 800, "w": 1190, "h": 230, "label": "AKUISISI DAN LINEAGE", "align": "start"}],
    "nodes": dict([
        _box(0, 70, "PERAN"), _box(1, 70, "TOKEN_API"), _box(2, 70, "LOG_AKTIVITAS"), _box(3, 70, "JENIS_LAPORAN"),
        _box(4, 70, "LAPORAN"), _box(0, 170, "LOG_AUDIT"), _box(2, 170, "PENGGUNA"), _box(3, 170, "PERINGATAN_TERKIRIM"),
        _box(0, 460, "ATURAN_PERINGATAN"), _box(1, 460, "PERINGATAN"), _box(2, 460, "KEJADIAN"), _box(3, 460, "WILAYAH"),
        _box(0, 560, "JENIS_BENCANA"), _box(1, 560, "OBSERVASI"), _box(2, 560, "VARIABEL"), _box(4, 560, "FORECAST"),
        _box(0, 850, "AREA_PANTAUAN"), _box(1, 850, "PRODUK_DATA"), _box(2, 850, "SUMBER_SATELIT"),
        _box(3, 850, "TAHAP_PROSES"), _box(4, 850, "DATASET"), _box(0, 950, "SCENE_S1"), _box(1, 950, "GRANULE_NASA"),
        _box(2, 950, "JOB_PROSES"), _box(3, 950, "METRIK_MUTU")]),
    "edges": [
        E("PENGGUNA", "B", _C[2] + 25, "zero_one", "PERINGATAN", "T", _mid(1), "zero_many", "menindaklanjuti",
          via=[[_C[2] + 25, 330], [_mid(1), 330]], lp=[_mid(1) - 8, 380, "end"]),
        E("PENGGUNA", "B", _C[2] + 70, "one", "KEJADIAN", "T", _C[2] + 70, "zero_many", "mencatat",
          lp=[_C[2] + 62, 365, "end"]),
        E("PENGGUNA", "B", _C[2] + 120, "zero_one", "KEJADIAN", "T", _C[2] + 120, "zero_many", "memverifikasi",
          lp=[_C[2] + 128, 365, "start"]),
        E("PENGGUNA", "B", _C[2] + 165, "zero_many", "WILAYAH", "T", _C[3] + 40, "zero_many", "berlangganan",
          via=[[_C[2] + 165, 300], [_C[3] + 40, 300]]),
        E("PERINGATAN_TERKIRIM", "B", _C[3] + 140, "zero_many", "WILAYAH", "T", _C[3] + 140, "one", "tentang",
          lp=[_C[3] + 148, 365, "start"]),
        E("WILAYAH", "R", 480, "zero_one", "FORECAST", "T", _mid(4), "zero_many", "untuk"),
        E("VARIABEL", "R", 580, "one", "FORECAST", "L", 580, "zero_many", "diprakirakan"),
        E("PRODUK_DATA", "T", _mid(1), "zero_one", "OBSERVASI", "B", _mid(1), "zero_many", "sumber",
          lp=[_mid(1) + 8, 730, "start"]),
        E("SUMBER_SATELIT", "T", _mid(2), "one", "VARIABEL", "B", _mid(2), "one_many", "mengukur",
          lp=[_mid(2) + 8, 730, "start"]),
    ]}

JOBS = [("erd_a.png", "erd", ERD_A), ("erd_b.png", "erd", ERD_B), ("erd_c.png", "erd", ERD_C),
        ("state_job.png", "state", STATE),
        ("erd_cf.png", "arch", ERD_CF)]

JS = r"""
([kind, spec]) => {
const D = '#004e53', L = '#e5feff', MUTED = '#5f8f92', NS = 'http://www.w3.org/2000/svg', R = 12, STUB = 28;
const o = document.getElementById('o'); o.innerHTML = '';
const svg = document.createElementNS(NS, 'svg'); o.appendChild(svg);
const gBack = el('g', {}, svg), gEdge = el('g', {}, svg), gNode = el('g', {}, svg), gLab = el('g', {}, svg);
function el(t, a, p) { const e = document.createElementNS(NS, t); for (const k in a) e.setAttribute(k, a[k]); (p || svg).appendChild(e); return e; }
function txt(p, x, y, s, a) { const t = el('text', Object.assign({x, y, 'font-family': 'Lexend', fill: D, 'font-size': 14,
  'dominant-baseline': 'central'}, a || {}), p); t.textContent = s; return t; }
const box = {};
// ---------- nodes
if (kind === 'erd') {
  const W = spec.w, HH = 36, RH = 24;
  for (const [name, n] of Object.entries(spec.nodes)) {
    const h = HH + 6 + RH * n.rows.length + 6; box[name] = {x: n.x, y: n.y, w: W, h};
    const g = el('g', {}, gNode);
    el('rect', {x: n.x, y: n.y, width: W, height: h, rx: 10, fill: 'white', stroke: 'none'}, g);
    el('path', {d: `M${n.x},${n.y + HH} V${n.y + 10} Q${n.x},${n.y} ${n.x + 10},${n.y} H${n.x + W - 10} Q${n.x + W},${n.y} ${n.x + W},${n.y + 10} V${n.y + HH} Z`, fill: L}, g);
    el('line', {x1: n.x, y1: n.y + HH, x2: n.x + W, y2: n.y + HH, stroke: D, 'stroke-width': 1.5}, g);
    el('rect', {x: n.x, y: n.y, width: W, height: h, rx: 10, fill: 'none', stroke: D, 'stroke-width': 2}, g);
    txt(g, n.x + W / 2, n.y + HH / 2, name, {'text-anchor': 'middle', 'font-weight': 600, 'font-size': 15});
    n.rows.forEach((r, i) => {
      const y = n.y + HH + 6 + RH * i + RH / 2;
      if (r[0]) txt(g, n.x + 12, y, r[0], {'font-weight': 600, 'font-size': 13});
      txt(g, n.x + (spec.kw || 48), y, r[1], r[0] && r[0] !== 'FK' ? {'text-decoration': 'underline'} : (r[0] === 'FK' ? {'font-style': 'italic'} : {}));
      txt(g, n.x + W - 12, y, r[2], {'text-anchor': 'end', fill: MUTED, 'font-size': 12});
    });
  }
} else if (kind === 'arch') {
  for (const G of spec.groups) {
    el('rect', {x: G.x, y: G.y, width: G.w, height: G.h, rx: 14, fill: L, stroke: D, 'stroke-width': 2}, gBack);
    if (G.align === 'start') txt(gBack, G.x + 18, G.y + 22, G.label, {'font-weight': 600, 'font-size': 13, 'letter-spacing': 0.5});
    else txt(gBack, G.x + G.w / 2, G.y + 20, G.label, {'text-anchor': 'middle', 'font-weight': 600, 'font-size': 13, 'letter-spacing': 0.5});
    box[G.name] = {x: G.x, y: G.y, w: G.w, h: G.h};
  }
  for (const [name, n] of Object.entries(spec.nodes)) {
    const {x, y, w, h} = n; box[name] = {x, y, w, h}; const g = el('g', {}, gNode), ry = 9;
    if (n.shape === 'db') {
      el('path', {d: `M${x},${y + ry} A${w / 2},${ry} 0 0 1 ${x + w},${y + ry} V${y + h - ry} A${w / 2},${ry} 0 0 1 ${x},${y + h - ry} Z`, fill: 'white', stroke: D, 'stroke-width': 2}, g);
      el('path', {d: `M${x},${y + ry} A${w / 2},${ry} 0 0 0 ${x + w},${y + ry}`, fill: 'none', stroke: D, 'stroke-width': 2}, g);
    } else {
      el('rect', {x, y, width: w, height: h, rx: n.shape === 'pill' ? h / 2 : 10, fill: 'white', stroke: D, 'stroke-width': 2,
        'stroke-dasharray': n.shape === 'dashed' ? '7 5' : 'none'}, g);
    }
    const lines = n.label.split('\n'), lh = 17, cy = y + h / 2 + (n.shape === 'db' ? 5 : 0) - (lines.length - 1) * lh / 2;
    lines.forEach((s, i) => txt(g, x + w / 2, cy + i * lh, s, i === 0 ? {'text-anchor': 'middle', 'font-weight': 600, 'font-size': 14}
                                                        : {'text-anchor': 'middle', 'font-size': 12.5}));
  }
} else {
  const G = spec.group;
  el('rect', {x: G.x, y: G.y, width: G.w, height: G.h, rx: 14, fill: L, stroke: D, 'stroke-width': 2}, gBack);
  txt(gBack, G.x + 16, G.y + 16, G.label, {'font-weight': 600, 'font-size': 13});
  for (const [name, n] of Object.entries(spec.nodes)) {
    if (n.kind === 'group') { box[name] = {x: G.x, y: G.y, w: G.w, h: G.h}; continue; }
    if (n.kind === 'init') { el('circle', {cx: n.cx, cy: n.cy, r: 11, fill: D}, gNode); box[name] = {x: n.cx - 11, y: n.cy - 11, w: 22, h: 22}; continue; }
    if (n.kind === 'final') { el('circle', {cx: n.cx, cy: n.cy, r: 13, fill: 'white', stroke: D, 'stroke-width': 2}, gNode);
      el('circle', {cx: n.cx, cy: n.cy, r: 8, fill: D}, gNode); box[name] = {x: n.cx - 13, y: n.cy - 13, w: 26, h: 26}; continue; }
    const t = txt(gNode, n.cx, n.cy, name, {'text-anchor': 'middle', 'font-weight': 600});
    const w = t.getBBox().width + 36, h = 46; box[name] = {x: n.cx - w / 2, y: n.cy - h / 2, w, h};
    const r = el('rect', {x: n.cx - w / 2, y: n.cy - h / 2, width: w, height: h, rx: 12, fill: 'white', stroke: D, 'stroke-width': 2}, gNode);
    gNode.insertBefore(r, t);
  }
}
// ---------- edges
const N = {L: [-1, 0], R: [1, 0], T: [0, -1], B: [0, 1]};
function port(name, side, v) { const b = box[name];
  if (side === 'L') return [b.x, v]; if (side === 'R') return [b.x + b.w, v]; if (side === 'T') return [v, b.y]; return [v, b.y + b.h]; }
function marker(P, n, kind) {
  const t = [-n[1], n[0]], at = d => [P[0] + n[0] * d, P[1] + n[1] * d];
  const bar = d => { const c = at(d); el('line', {x1: c[0] + t[0] * 8, y1: c[1] + t[1] * 8, x2: c[0] - t[0] * 8, y2: c[1] - t[1] * 8, stroke: D, 'stroke-width': 2}, gEdge); };
  const circ = d => { const c = at(d); el('circle', {cx: c[0], cy: c[1], r: 5, fill: 'white', stroke: D, 'stroke-width': 2}, gEdge); };
  const crow = () => { const c = at(14); for (const s of [-1, 0, 1]) el('line', {x1: c[0], y1: c[1], x2: P[0] + t[0] * 9 * s, y2: P[1] + t[1] * 9 * s, stroke: D, 'stroke-width': 2}, gEdge); };
  const arrow = () => { const c = at(12); for (const s of [-1, 1]) el('line', {x1: P[0], y1: P[1], x2: c[0] + t[0] * 6 * s, y2: c[1] + t[1] * 6 * s, stroke: D, 'stroke-width': 2, 'stroke-linecap': 'round'}, gEdge); };
  if (kind === 'one') { bar(8); bar(14); } else if (kind === 'zero_one') { bar(8); circ(21); }
  else if (kind === 'zero_many') { crow(); circ(21); } else if (kind === 'one_many') { crow(); bar(19); } else if (kind === 'arrow') arrow();
}
for (const e of spec.edges) {
  const S = port(e.a, e.sa, e.pa), T = port(e.b, e.sb, e.pb), na = N[e.sa], nb = N[e.sb];
  const S1 = [S[0] + na[0] * STUB, S[1] + na[1] * STUB], T1 = [T[0] + nb[0] * STUB, T[1] + nb[1] * STUB];
  let pts = [S, S1];
  if (e.via) pts.push(...e.via);
  else if (na[0] !== 0 && nb[0] !== 0) { const m = (S1[0] + T1[0]) / 2; pts.push([m, S1[1]], [m, T1[1]]); }
  else if (na[1] !== 0 && nb[1] !== 0) { const m = (S1[1] + T1[1]) / 2; pts.push([S1[0], m], [T1[0], m]); }
  else if (na[0] !== 0) pts.push([T1[0], S1[1]]); else pts.push([S1[0], T1[1]]);
  pts.push(T1, T);
  let w = pts.filter((q, i) => i === 0 || Math.hypot(q[0] - pts[i - 1][0], q[1] - pts[i - 1][1]) > 0.5);
  const v = [w[0]];
  for (let i = 1; i < w.length - 1; i++) { const a = v[v.length - 1], b = w[i], c = w[i + 1];
    if (Math.abs((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])) > 0.5) v.push(b); }
  v.push(w[w.length - 1]);
  let d = `M${v[0][0]},${v[0][1]}`;
  for (let i = 1; i < v.length - 1; i++) { const a = v[i - 1], b = v[i], c = v[i + 1];
    const l1 = Math.hypot(b[0] - a[0], b[1] - a[1]), l2 = Math.hypot(c[0] - b[0], c[1] - b[1]), r = Math.min(R, l1 / 2, l2 / 2);
    const p1 = [b[0] - (b[0] - a[0]) / l1 * r, b[1] - (b[1] - a[1]) / l1 * r], p2 = [b[0] + (c[0] - b[0]) / l2 * r, b[1] + (c[1] - b[1]) / l2 * r];
    d += ` L${p1[0]},${p1[1]} Q${b[0]},${b[1]} ${p2[0]},${p2[1]}`; }
  d += ` L${v[v.length - 1][0]},${v[v.length - 1][1]}`;
  el('path', {d, fill: 'none', stroke: D, 'stroke-width': 2, 'stroke-linejoin': 'round'}, gEdge);
  marker(S, na, e.ma); marker(T, nb, e.mb);
  if (!e.label) continue;
  let x, y, anchor = 'middle';
  if (e.lp) { [x, y] = e.lp; if (e.lp[2]) anchor = e.lp[2]; }
  else { let best = -1; for (let i = 1; i < v.length; i++) { const l = Math.hypot(v[i][0] - v[i - 1][0], v[i][1] - v[i - 1][1]);
    if (l > best) { best = l; x = (v[i][0] + v[i - 1][0]) / 2; y = (v[i][1] + v[i - 1][1]) / 2; } } }
  const lines = e.label.split('\n'), t = el('text', {x, y, 'text-anchor': anchor, 'font-family': 'Lexend', 'font-size': 13, fill: D}, gLab);
  lines.forEach((s, i) => { const ts = el('tspan', {x, dy: i === 0 ? `${0.35 - (lines.length - 1) * 0.6}em` : '1.2em'}, t); ts.textContent = s; });
  const bb = t.getBBox(); const bg = el('rect', {x: bb.x - 5, y: bb.y - 2, width: bb.width + 10, height: bb.height + 4, rx: 4, fill: 'white'}, gLab);
  gLab.insertBefore(bg, t);
}
const bb = svg.getBBox(), P = 16;
svg.setAttribute('viewBox', `${bb.x - P} ${bb.y - P} ${bb.width + 2 * P} ${bb.height + 2 * P}`);
svg.setAttribute('width', bb.width + 2 * P); svg.setAttribute('height', bb.height + 2 * P);
// periksa teks yang melampaui kotak entitas
const over = [];
if (kind === 'erd') for (const [name, b] of Object.entries(box)) for (const t of gNode.querySelectorAll('text')) {
  const r = t.getBBox(); if (r.y >= b.y && r.y <= b.y + b.h && r.x >= b.x - 2 && r.x <= b.x + b.w && r.x + r.width > b.x + b.w - 4) over.push(name + ':' + t.textContent); }
return [Math.round(bb.width), Math.round(bb.height), over];
}"""


def render(jobs, outdir):
    """jobs: daftar (nama_png, jenis 'erd'|'state'|'arch', spesifikasi). Dipakai juga oleh artikel_gaee/figs.py."""
    outdir = pathlib.Path(outdir)
    with sync_playwright() as pw:
        b = pw.chromium.launch(); pg = b.new_page(device_scale_factor=3, viewport={"width": 1800, "height": 1200})
        pg.set_content('<html><head><link href="https://fonts.googleapis.com/css2?family=Lexend:wght@400;600&display=swap" '
                       'rel="stylesheet"></head><body style="margin:0;background:#fff"><div id="o" style="display:inline-block"></div></body></html>')
        pg.evaluate("Promise.all([document.fonts.load('14px Lexend'), document.fonts.load('600 14px Lexend')])")
        pg.wait_for_timeout(500)
        for png, kind, spec in jobs:
            w, h, over = pg.evaluate(JS, [kind, json.loads(json.dumps(spec))])
            pg.locator("#o svg").screenshot(path=str(outdir / png))
            print(png, w, h, ("TEKS MELAMPAUI: " + ", ".join(over)) if over else "", flush=True)
        b.close()


def main(outdir):
    render(JOBS, outdir)


if __name__ == "__main__":
    main(sys.argv[1])
