/**
 * Tinjauan Kebutuhan (requirement/user review) Orbit-U: The Monitor oleh GMLS.
 *
 * Pasang di script.google.com:
 *   1. Proyek baru → tempel file ini sebagai Code.gs.
 *   2. File → + → HTML, beri nama "Index" → tempel Index.html.
 *   3. Jalankan fungsi siapkan() sekali dan izinkan aksesnya.
 *      Log akan menampilkan URL Google Sheet tempat jawaban disimpan.
 *   4. Deploy → New deployment → Web app.
 *      Execute as: Me · Who has access: Anyone → Deploy → salin URL /exec.
 *
 * Setiap jawaban disimpan sebagai satu baris di Sheet dan dikirim ke email
 * pemilik skrip (akun Google yang men-deploy).
 */

const SHEET_NAME = 'Jawaban';

// [kunci, label kolom/email]. Urutan = urutan kolom di Sheet.
const FIELDS = [
  ['nama', 'Nama'],
  ['jabatan', 'Jabatan di GMLS'],
  ['k1', 'K1 Kondisi di lokasi sendiri'],
  ['k2', 'K2 Peringatan hujan lebat + email'],
  ['k3', 'K3 Bahasa peringatan dan tampilan awam'],
  ['k4', 'K4 Pemantauan genangan dan perkiraan 15 hari'],
  ['k5', 'K5 Arsip kejadian dari sumber resmi'],
  ['k6', 'K6 Akses sesuai peran'],
  ['catatan_kebutuhan', 'Catatan kebutuhan'],
  ['data', 'Data yang dicatat'],
  ['catatan_data', 'Catatan data'],
  ['aturan', 'Aturan pencatatan'],
  ['catatan_aturan', 'Catatan aturan'],
  ['batasan', 'Batasan sistem'],
  ['catatan_batasan', 'Catatan batasan'],
  ['peran_analis', 'Peran Analis'],
  ['peran_data_engineer', 'Peran Data Engineer'],
  ['peran_admin', 'Peran Administrator'],
  ['wilayah', '10 kecamatan sesuai'],
  ['catatan_wilayah', 'Catatan wilayah'],
  ['persetujuan', 'Persetujuan akhir'],
  ['saran', 'Saran'],
];

const REQUIRED = ['nama', 'jabatan', 'k1', 'k2', 'k3', 'k4', 'k5', 'k6', 'data', 'aturan', 'batasan', 'wilayah', 'persetujuan'];

function doGet() {
  return HtmlService.createHtmlOutputFromFile('Index')
    .setTitle('Tinjauan Kebutuhan – Orbit-U: The Monitor')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

/** Jalankan sekali dari editor untuk memberi izin dan membuat Sheet. */
function siapkan() {
  const sh = getSheet_();
  Logger.log('Jawaban disimpan di: ' + sh.getParent().getUrl());
  Logger.log('Email dikirim ke: ' + Session.getEffectiveUser().getEmail());
}

/** Dipanggil halaman lewat google.script.run. */
function submit(data) {
  data = data || {};
  const missing = REQUIRED.filter(function (k) { return !String(data[k] || '').trim(); });
  if (missing.length) throw new Error('Masih ada pertanyaan wajib yang kosong.');

  const lock = LockService.getScriptLock();
  lock.waitLock(15000);
  try {
    const sh = getSheet_();
    const values = FIELDS.map(function (f) { return clean_(data[f[0]]); });
    sh.appendRow([new Date()].concat(values.map(noFormula_)));

    const body = FIELDS.map(function (f, i) { return f[1] + ': ' + (values[i] || '-'); }).join('\n');
    MailApp.sendEmail({
      to: Session.getEffectiveUser().getEmail(),
      subject: 'Tinjauan kebutuhan Orbit-U dari ' + values[0] + ' (' + values[1] + ')',
      body: body + '\n\nSemua jawaban: ' + sh.getParent().getUrl(),
    });
    return { ok: true };
  } finally {
    lock.releaseLock();
  }
}

function getSheet_() {
  const props = PropertiesService.getScriptProperties();
  let ss = null;
  const id = props.getProperty('SHEET_ID');
  if (id) {
    try { ss = SpreadsheetApp.openById(id); } catch (e) { ss = null; }
  }
  if (!ss) {
    ss = SpreadsheetApp.create('Jawaban Tinjauan Kebutuhan GMLS – Orbit-U');
    props.setProperty('SHEET_ID', ss.getId());
  }
  let sh = ss.getSheetByName(SHEET_NAME);
  if (!sh) {
    sh = ss.getSheets()[0];
    sh.setName(SHEET_NAME);
  }
  // Baris judul selalu disamakan dengan FIELDS (bila daftar pertanyaan berubah).
  const header = ['Waktu'].concat(FIELDS.map(function (f) { return f[1]; }));
  sh.getRange(1, 1, 1, header.length).setValues([header]);
  sh.setFrozenRows(1);
  return sh;
}

function clean_(v) {
  return String(v == null ? '' : v).trim().slice(0, 2000);
}

// Cegah isian yang diawali =, +, -, @ dibaca Sheet sebagai rumus.
function noFormula_(v) {
  return /^[=+\-@]/.test(v) ? "'" + v : v;
}
