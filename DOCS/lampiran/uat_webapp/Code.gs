/**
 * Uji penerimaan pengguna (UAT) Orbit-U: The Monitor.
 *
 * Pasang di script.google.com (proyek terpisah dari tinjauan kebutuhan):
 *   1. Proyek baru → tempel file ini sebagai Code.gs.
 *   2. + → HTML, beri nama "Index" → tempel Index.html.
 *   3. Jalankan fungsi siapkan() sekali dan izinkan aksesnya.
 *   4. Terapkan → Deployment baru → Aplikasi web.
 *      Jalankan sebagai: Saya · Yang memiliki akses: Siapa saja.
 *
 * Setiap jawaban disimpan sebagai satu baris di Sheet dan dikirim ke email
 * pemilik skrip.
 */

const SHEET_NAME = 'Jawaban UAT';
const JUMLAH_SKENARIO = 6;

// [kunci, label kolom]. Urutan = urutan kolom di Sheet.
const FIELDS = (function () {
  const f = [['nama', 'Nama'], ['asal', 'Asal'], ['perangkat', 'Perangkat']];
  for (let i = 1; i <= JUMLAH_SKENARIO; i++) {
    f.push(['s' + i + '_hasil', 'S' + i + ' Hasil']);
    f.push(['s' + i + '_mudah', 'S' + i + ' Kemudahan (1-5)']);
    f.push(['s' + i + '_kendala', 'S' + i + ' Kendala']);
  }
  f.push(['layak', 'Layak dipakai']);
  f.push(['saran', 'Saran']);
  return f;
})();

const REQUIRED = ['nama', 'asal', 'perangkat', 'layak']
  .concat(Array.from({ length: JUMLAH_SKENARIO }, function (_, i) { return 's' + (i + 1) + '_hasil'; }));

function doGet() {
  return HtmlService.createHtmlOutputFromFile('Index')
    .setTitle('Uji Coba – Orbit-U: The Monitor')
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
      subject: 'UAT Orbit-U dari ' + values[0] + ' (' + values[1] + ')',
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
    ss = SpreadsheetApp.create('Jawaban UAT – Orbit-U');
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
