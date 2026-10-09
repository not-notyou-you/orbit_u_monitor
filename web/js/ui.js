// web/js/ui.js — primitif Orbital 95 (DESIGN.md §4) + format id-ID + terjemahan
// kode error (INTERFACE.md §5). Dipakai semua halaman; tanpa dependensi.
'use strict';

const UI = (() => {
  // ------------------------------------------------------------------ ikon (SVG inline, piksel)
  const S = (w, body) => '<svg viewBox="0 0 ' + w + ' ' + w + '" shape-rendering="crispEdges" aria-hidden="true" focusable="false">' + body + '</svg>';
  const ICONS = {
    satellite: S(16, '<rect x="6" y="6" width="4" height="4" fill="#c0c0c0" stroke="#000"/><rect x="1" y="5" width="4" height="6" fill="#000080"/><rect x="11" y="5" width="4" height="6" fill="#000080"/><rect x="5" y="7" width="1" height="2" fill="#000"/><rect x="10" y="7" width="1" height="2" fill="#000"/><rect x="7" y="2" width="2" height="4" fill="#000"/><rect x="7" y="1" width="2" height="1" fill="#ffd800"/>'),
    dish: S(16, '<path d="M2 3 Q2 12 11 12 Z" fill="#fff" stroke="#000"/><rect x="6" y="11" width="2" height="3" fill="#000"/><rect x="3" y="14" width="8" height="1" fill="#000"/><rect x="7" y="6" width="5" height="1" fill="#000"/><rect x="12" y="5" width="2" height="2" fill="#ffd800"/>'),
    globe: S(16, '<rect x="3" y="2" width="10" height="12" fill="#1084d0"/><rect x="2" y="4" width="12" height="8" fill="#1084d0"/><rect x="5" y="4" width="3" height="3" fill="#00a000"/><rect x="9" y="8" width="3" height="3" fill="#00a000"/><rect x="2" y="7" width="12" height="1" fill="#000080"/><rect x="7" y="2" width="1" height="12" fill="#000080"/>'),
    drop: S(16, '<path d="M8 1 L12 8 L12 11 L10 14 L6 14 L4 11 L4 8 Z" fill="#4de1ff" stroke="#000"/><rect x="6" y="9" width="1" height="3" fill="#fff"/>'),
    folder: S(16, '<rect x="1" y="4" width="14" height="10" fill="#ffd800" stroke="#000"/><rect x="1" y="2" width="6" height="2" fill="#ffd800" stroke="#000"/>'),
    disk: S(16, '<rect x="2" y="2" width="12" height="12" fill="#000080"/><rect x="4" y="2" width="8" height="5" fill="#c0c0c0"/><rect x="9" y="3" width="2" height="3" fill="#000080"/><rect x="4" y="9" width="8" height="5" fill="#fff"/>'),
    monitor: S(16, '<rect x="1" y="2" width="14" height="10" fill="#c0c0c0" stroke="#000"/><rect x="3" y="4" width="10" height="6" fill="#03110a"/><rect x="4" y="7" width="3" height="1" fill="#33ff99"/><rect x="5" y="12" width="6" height="2" fill="#808080"/>'),
    chart: S(16, '<rect x="1" y="1" width="14" height="14" fill="#03110a" stroke="#000"/><rect x="3" y="9" width="2" height="4" fill="#33ff99"/><rect x="7" y="6" width="2" height="7" fill="#33ff99"/><rect x="11" y="3" width="2" height="10" fill="#ffb000"/>'),
    doc: S(16, '<rect x="3" y="1" width="10" height="14" fill="#fff" stroke="#000"/><rect x="5" y="4" width="6" height="1" fill="#000"/><rect x="5" y="7" width="6" height="1" fill="#000"/><rect x="5" y="10" width="4" height="1" fill="#000"/>'),
    key: S(16, '<rect x="2" y="5" width="5" height="5" fill="#ffd800" stroke="#000"/><rect x="7" y="7" width="7" height="2" fill="#ffd800" stroke="#000"/><rect x="11" y="9" width="2" height="2" fill="#000"/>'),
    gear: S(16, '<rect x="4" y="4" width="8" height="8" fill="#808080" stroke="#000"/><rect x="7" y="1" width="2" height="14" fill="#808080"/><rect x="1" y="7" width="14" height="2" fill="#808080"/><rect x="6" y="6" width="4" height="4" fill="#c0c0c0"/>'),
    alarm: S(16, '<path d="M8 1 L15 14 L1 14 Z" fill="#ffd800" stroke="#000"/><rect x="7" y="5" width="2" height="5" fill="#000"/><rect x="7" y="11" width="2" height="2" fill="#000"/>'),
    user: S(16, '<rect x="5" y="1" width="6" height="6" fill="#ffd8a8" stroke="#000"/><rect x="2" y="9" width="12" height="6" fill="#000080" stroke="#000"/>'),
    door: S(16, '<rect x="3" y="1" width="9" height="14" fill="#808080" stroke="#000"/><rect x="9" y="8" width="2" height="2" fill="#ffd800"/><rect x="12" y="7" width="3" height="2" fill="#000"/>'),
    help: S(16, '<rect x="1" y="1" width="14" height="14" fill="#fff" stroke="#000"/><path d="M5 5 h1 v-1 h4 v1 h1 v2 h-1 v1 h-2 v2 h-2 v-3 h2 v-1 h1 v-1 h-2 v1 h-2 z" fill="#000080"/><rect x="7" y="11" width="2" height="2" fill="#000080"/>'),
    info32: S(32, '<rect x="6" y="2" width="20" height="28" fill="#fff" stroke="#000"/><rect x="2" y="6" width="28" height="20" fill="#fff"/><rect x="2" y="6" width="1" height="20" fill="#000"/><rect x="29" y="6" width="1" height="20" fill="#000"/><rect x="14" y="7" width="4" height="4" fill="#000080"/><rect x="14" y="13" width="4" height="12" fill="#000080"/>'),
    warn32: S(32, '<path d="M16 2 L30 28 L2 28 Z" fill="#ffd800" stroke="#000" stroke-width="2"/><rect x="14" y="10" width="4" height="10" fill="#000"/><rect x="14" y="22" width="4" height="3" fill="#000"/>'),
    error32: S(32, '<rect x="6" y="2" width="20" height="28" fill="#ff0000" stroke="#000"/><rect x="2" y="6" width="28" height="20" fill="#ff0000"/><rect x="2" y="6" width="1" height="20" fill="#000"/><rect x="29" y="6" width="1" height="20" fill="#000"/><path d="M10 10 L22 22 M22 10 L10 22" stroke="#fff" stroke-width="4"/>'),
    question32: S(32, '<rect x="6" y="2" width="20" height="28" fill="#fff" stroke="#000"/><rect x="2" y="6" width="28" height="20" fill="#fff"/><rect x="2" y="6" width="1" height="20" fill="#000"/><rect x="29" y="6" width="1" height="20" fill="#000"/><path d="M11 10 h2 v-2 h6 v2 h2 v4 h-2 v2 h-2 v3 h-3 v-5 h2 v-2 h2 v-2 h-4 v2 h-3 z" fill="#000080"/><rect x="14" y="21" width="3" height="3" fill="#000080"/>'),
    sat32: S(32, '<rect x="12" y="12" width="8" height="8" fill="#c0c0c0" stroke="#000"/><rect x="1" y="10" width="10" height="12" fill="#000080" stroke="#4de1ff"/><rect x="21" y="10" width="10" height="12" fill="#000080" stroke="#4de1ff"/><rect x="15" y="4" width="2" height="8" fill="#fff"/><rect x="14" y="2" width="4" height="2" fill="#ffd800"/>'),
    min: '<svg viewBox="0 0 8 7" shape-rendering="crispEdges" aria-hidden="true"><rect x="1" y="5" width="6" height="2" fill="#000"/></svg>',
    max: '<svg viewBox="0 0 8 7" shape-rendering="crispEdges" aria-hidden="true"><rect x="0" y="0" width="8" height="7" fill="none" stroke="#000" stroke-width="2"/></svg>',
    close: '<svg viewBox="0 0 8 7" shape-rendering="crispEdges" aria-hidden="true"><path d="M0 0h2v1h1v1h2v-1h1v-1h2v1h-1v1h-1v1h-1v1h1v1h1v1h1v1h-2v-1h-1v-1h-2v1h-1v1h-2v-1h1v-1h1v-1h1v-1h-1v-1h-1v-1h-1z" fill="#000"/></svg>',
  };
  const icon = name => ICONS[name] || '';

  // ------------------------------------------------------------------ format id-ID
  const NA = '—';
  const nf = {};
  function num(v, digits) {
    if (v === null || v === undefined || v === '' || Number.isNaN(Number(v))) return NA;
    const d = digits === undefined ? 1 : digits;
    const k = d;
    nf[k] = nf[k] || new Intl.NumberFormat('id-ID', { minimumFractionDigits: 0, maximumFractionDigits: d });
    return nf[k].format(Number(v));
  }
  function int(v) { return num(v, 0); }
  function pct(v, d) { return v === null || v === undefined ? NA : num(v, d === undefined ? 1 : d) + '%'; }
  function bytes(n) {
    if (n === null || n === undefined) return NA;
    const u = ['B', 'KB', 'MB', 'GB', 'TB']; let i = 0; let x = Number(n);
    while (x >= 1024 && i < u.length - 1) { x /= 1024; i++; }
    return num(x, i ? 1 : 0) + ' ' + u[i];
  }
  // Tanggal tanpa jam (YYYY-MM-DD) dibaca sebagai tanggal kalender, bukan UTC tengah malam.
  function parseDate(s) {
    if (!s) return null;
    if (s instanceof Date) return s;
    if (/^\d{4}-\d{2}-\d{2}$/.test(s)) { const [y, m, d] = s.split('-').map(Number); return new Date(y, m - 1, d); }
    const t = new Date(s); return Number.isNaN(t.getTime()) ? null : t;
  }
  function date(s, style) {
    const d = parseDate(s); if (!d) return NA;
    const opt = style === 'short' ? { day: 'numeric', month: 'short' }
      : style === 'long' ? { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }
      : { day: 'numeric', month: 'short', year: 'numeric' };
    return d.toLocaleDateString('id-ID', opt);
  }
  function dateTime(s) {
    const d = parseDate(s); if (!d) return NA;
    return d.toLocaleString('id-ID', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  }
  function isoDate(d) {
    const x = d instanceof Date ? d : new Date(d);
    return x.getFullYear() + '-' + String(x.getMonth() + 1).padStart(2, '0') + '-' + String(x.getDate()).padStart(2, '0');
  }
  function addDays(iso, n) { const d = parseDate(iso) || new Date(); d.setDate(d.getDate() + n); return isoDate(d); }

  function esc(s) {
    return String(s === null || s === undefined ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

  // ------------------------------------------------------------------ kode error → pesan Indonesia (INTERFACE §5, M21)
  const ERROR_TEXT = {
    NOT_AUTHENTICATED: 'Anda belum masuk. Silakan masuk terlebih dahulu.',
    SESSION_EXPIRED: 'Sesi Anda telah berakhir. Silakan masuk kembali.',
    ACCOUNT_INACTIVE: 'Akun ini dinonaktifkan. Hubungi administrator.',
    INVALID_CREDENTIALS: 'Nama pengguna atau kata sandi salah.',
    ACCOUNT_LOCKED: 'Akun dikunci sementara karena terlalu banyak percobaan gagal. Coba lagi 15 menit lagi atau hubungi administrator.',
    ROLE_FORBIDDEN: 'Peran Anda tidak memiliki akses ke fitur ini.',
    DB_PERMISSION_DENIED: 'Basis data menolak permintaan ini untuk peran Anda.',
    CSRF_HEADER_REQUIRED: 'Permintaan ditolak karena header keamanan tidak ada. Muat ulang halaman.',
    TOKEN_INVALID: 'Token API tidak valid.',
    TOKEN_REVOKED: 'Token API sudah dicabut.',
    TOKEN_EXPIRED: 'Token API sudah kedaluwarsa.',
    TOKEN_WRITE_FORBIDDEN: 'Token API hanya boleh membaca data; aksi ini harus dilakukan lewat sesi web.',
    TOKEN_SCOPE_FORBIDDEN: 'Cakupan token tidak mengizinkan unduhan.',
    RATE_LIMITED: 'Terlalu banyak permintaan. Tunggu sekitar satu menit lalu coba lagi.',
    NOT_DATASET_OWNER: 'Hanya pembuat dataset atau administrator yang boleh menghapusnya.',
    SCENE_OUT_OF_RANGE: 'Scene ini di luar rentang waktu peran Anda (pengunjung 30 hari, Relawan 1 tahun). Analis, Data Engineer, dan Administrator melihat semuanya.',
    PASSWORD_POLICY: 'Kata sandi belum memenuhi kebijakan: minimal 10 karakter dan maksimal 72 byte.',
    INVALID_OLD_PASSWORD: 'Kata sandi lama salah.',
    USERNAME_TAKEN: 'Nama pengguna sudah dipakai.',
    EMAIL_TAKEN: 'Email ini sudah terdaftar. Masuk dengan akun tersebut, atau gunakan email lain.',
    PASSWORD_MISMATCH: 'Konfirmasi kata sandi tidak sama dengan kata sandi.',
    CANNOT_MODIFY_SELF: 'Anda tidak dapat menonaktifkan atau menurunkan peran akun sendiri.',
    TOKEN_ALREADY_REVOKED: 'Token ini sudah dicabut sebelumnya.',
    INVALID_DATE_RANGE: 'Rentang tanggal tidak valid (tanggal akhir sebelum tanggal awal, atau melebihi batas).',
    ALERT_ALREADY_ACKED: 'Alert ini sudah ditandai dibaca oleh pengguna lain.',
    DATE_OUT_OF_RANGE: 'Data lebih tua dari 1 tahun hanya dapat dilihat Analis, Data Engineer, dan Administrator.',
    SCENE_NOT_PUBLIC: 'Hanya scene terbaru yang terbuka untuk umum. Masuk untuk melihat scene lain.',
    THRESHOLD_REQUIRED: 'Aturan aktif wajib memiliki nilai ambang.',
    RULE_CODE_TAKEN: 'Kode aturan sudah dipakai.',
    TYPE_CODE_TAKEN: 'Kode jenis bencana sudah dipakai.',
    UNKNOWN_REFERENCE: 'Data rujukan (jenis bencana, band, atau wilayah) tidak dikenal.',
    INVALID_DISASTER: 'Data kejadian tidak valid. Periksa jenis, kecamatan, tanggal, dan panjang deskripsi (10–4000 karakter).',
    NOT_KECAMATAN: 'Wilayah harus berupa kecamatan.',
    AOI_EMPTY: 'Minimal satu kecamatan harus tetap berada di AOI.',
    INVALID_ROI: 'Pilihan wilayah untuk ROI tidak valid.',
    HYDROMET_NOT_READY: 'Data hidromet untuk periode ini belum siap.',
    REPORT_AUDIENCE: 'Laporan ini bukan untuk peran Anda.',
    INVALID_PERIOD: 'Periode tidak valid: laporan mingguan dimulai hari Senin, bulanan tanggal 1.',
    FILE_MISSING: 'Berkas tidak ditemukan di arsip.',
    INVALID_SOURCE: 'Sumber satelit tidak dikenal.',
    INVALID_PAGES: 'Pilih minimal satu halaman laporan: Ringkasan, Sentinel-1, MODIS, atau GPM.',
    INVALID_BAND: 'Band ini tidak dihitung per kecamatan (Sentinel-1 hanya tingkat AOI).',
    BACKFILL_RUNNING: 'Backfill GPM/MODIS lain masih berjalan. Tunggu sampai selesai, lalu coba lagi.',
    OUTSIDE_RASTER_WINDOW: 'Rentang ini seluruhnya lebih tua dari 1 tahun, di luar jendela citra Sentinel-1 yang disimpan. Untuk riwayat lebih lama, buat dataset lewat Data › Unduh.',
    REASON_REQUIRED: 'Alasan wajib diisi saat menonaktifkan scene.',
    NOT_REPROCESSABLE: 'Scene ini milik dataset Katalog dan tidak dapat diproses ulang dari sini.',
    INVALID_THRESHOLD: 'Nilai ambang tidak valid.',
    INVALID_SETTING: 'Nilai pengaturan di luar rentang yang diizinkan.',
    ENTITY_FORBIDDEN: 'Peran Anda tidak boleh mengekspor atau mengimpor jenis data ini.',
    IMPORT_NOT_SUPPORTED: 'Jenis data ini hanya dapat diekspor, tidak dapat diimpor.',
    INVALID_IMPORT_FILE: 'Berkas bukan Excel yang valid atau tidak memakai templat yang benar.',
    IMPORT_ROWS_INVALID: 'Ada baris yang tidak valid. Tidak ada data yang disimpan.',
    EMPTY_UPLOAD: 'Berkas kosong.',
    UPLOAD_TOO_LARGE: 'Berkas terlalu besar (maksimal 10 MB).',
    BAD_REQUEST: 'Permintaan tidak valid.',
    NOT_FOUND: 'Data tidak ditemukan.',
    CONFLICT: 'Terjadi konflik dengan data yang sudah ada.',
    VALIDATION_ERROR: 'Isian tidak valid.',
    INTERNAL_ERROR: 'Terjadi kesalahan di server. Coba lagi nanti.',
    SERVICE_UNAVAILABLE: 'Layanan atau basis data sedang tidak tersedia.',
    NETWORK: 'Tidak dapat terhubung ke server. Periksa koneksi Anda.',
  };
  const STATUS_FALLBACK = { 400: 'BAD_REQUEST', 401: 'NOT_AUTHENTICATED', 403: 'ROLE_FORBIDDEN', 404: 'NOT_FOUND',
    409: 'CONFLICT', 422: 'VALIDATION_ERROR', 423: 'ACCOUNT_LOCKED', 429: 'RATE_LIMITED', 500: 'INTERNAL_ERROR', 503: 'SERVICE_UNAVAILABLE' };
  function errorText(err) {
    if (!err) return ERROR_TEXT.INTERNAL_ERROR;
    const code = err.code || STATUS_FALLBACK[err.status];
    const base = ERROR_TEXT[code];
    if (base) {
      // Validasi Pydantic / 400 generik: detail Inggris ditampilkan sebagai keterangan teknis.
      if ((code === 'VALIDATION_ERROR' || code === 'BAD_REQUEST' || code === 'CONFLICT') && err.detail) {
        return base + '\nKeterangan: ' + err.detail;
      }
      return base;
    }
    return err.detail || err.message || ERROR_TEXT.INTERNAL_ERROR;
  }

  // ------------------------------------------------------------------ window & dialog
  function windowHTML(opts) {
    const id = opts.id ? ' id="' + esc(opts.id) + '"' : '';
    const titleId = (opts.id || 'w' + Math.random().toString(36).slice(2, 8)) + '-title';
    return '<section class="window ' + (opts.cls || '') + '"' + id + ' aria-labelledby="' + titleId + '">' +
      '<div class="titlebar"><span class="ttl-icon">' + icon(opts.icon || 'monitor') + '</span>' +
      '<span class="ttl-text"><' + (opts.h || 'h2') + ' id="' + titleId + '">' + esc(opts.title) + '</' + (opts.h || 'h2') + '></span>' +
      (opts.controls === false ? '' :
        '<button type="button" class="ttl-btn" tabindex="-1" aria-hidden="true">' + ICONS.min + '</button>' +
        '<button type="button" class="ttl-btn" tabindex="-1" aria-hidden="true">' + ICONS.max + '</button>' +
        '<button type="button" class="ttl-btn" tabindex="-1" aria-hidden="true">' + ICONS.close + '</button>') +
      '</div>' + (opts.menu || '') +
      '<div class="window-body">' + (opts.body || '') + '</div>' +
      (opts.status ? '<div class="statusbar">' + opts.status + '</div>' : '') +
      '</section>';
  }

  let dialogDepth = 0;
  // Dialog modal (DESIGN §4): ikon 32px + teks + tombol di kanan bawah. Escape
  // menutup (nilai = cancel); fokus dikembalikan ke elemen pemicu.
  function dialog(opts) {
    return new Promise(resolve => {
      const prev = document.activeElement;
      const back = document.createElement('div');
      back.className = 'dialog-backdrop';
      back.style.zIndex = String(1000 + (++dialogDepth) * 10);
      const tid = 'dlg' + Date.now() + dialogDepth;
      const buttons = opts.buttons || [{ label: 'OK', value: true, default: true }];
      back.innerHTML =
        '<div class="window dialog ' + (opts.wide ? (opts.wide === 'x' ? 'xwide' : 'wide') : '') + '" role="' + (opts.kind === 'error' || opts.kind === 'warn' ? 'alertdialog' : 'dialog') + '" aria-modal="true" aria-labelledby="' + tid + '">' +
        '<div class="titlebar"><span class="ttl-text" id="' + tid + '">' + esc(opts.title || 'Orbit-U') + '</span>' +
        '<button type="button" class="ttl-btn" data-x aria-label="Tutup">' + ICONS.close + '</button></div>' +
        '<div class="window-body">' +
        (opts.message !== undefined ? '<div class="dialog-msg">' + icon({ error: 'error32', warn: 'warn32', question: 'question32' }[opts.kind] || 'info32') +
          '<div class="txt">' + (opts.html ? opts.message : esc(opts.message)) + '</div></div>' : '') +
        (opts.body || '') +
        '<div class="btn-row end">' + buttons.map((b, i) =>
          '<button type="' + (b.submit ? 'submit' : 'button') + '" data-i="' + i + '" class="' + (b.default ? 'default' : '') + '">' + esc(b.label) + '</button>').join('') +
        '</div></div></div>';
      document.body.appendChild(back);
      const win = back.firstElementChild;
      const close = val => {
        if (opts.validate && val && val !== 'cancel') {
          const ok = opts.validate(win, val);
          if (ok === false) return;
        }
        back.remove(); dialogDepth--;
        document.removeEventListener('keydown', onKey, true);
        if (prev && prev.focus) prev.focus();
        resolve(opts.collect && val && val !== 'cancel' ? opts.collect(win, val) : val);
      };
      const cancelValue = (buttons.find(b => b.cancel) || {}).value;
      const onKey = e => {
        if (e.key === 'Escape') { e.preventDefault(); close(cancelValue === undefined ? 'cancel' : cancelValue); }
        else if (e.key === 'Tab') {
          const f = $$('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])', win).filter(x => !x.disabled && x.offsetParent !== null);
          if (!f.length) return;
          const first = f[0], last = f[f.length - 1];
          if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
          else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
        }
      };
      document.addEventListener('keydown', onKey, true);
      win.querySelector('[data-x]').addEventListener('click', () => close(cancelValue === undefined ? 'cancel' : cancelValue));
      $$('.btn-row.end > button', win).forEach(btn => btn.addEventListener('click', () => close(buttons[+btn.dataset.i].value)));
      win.addEventListener('keydown', e => {
        if (e.key === 'Enter' && e.target.tagName === 'INPUT' && e.target.type !== 'checkbox') {
          const d = buttons.findIndex(b => b.default); if (d >= 0) { e.preventDefault(); close(buttons[d].value); }
        }
      });
      if (opts.onOpen) opts.onOpen(win, close);
      const focusEl = win.querySelector('[autofocus]') || win.querySelector('input, select, textarea') || win.querySelector('button.default') || win.querySelector('.btn-row button');
      if (focusEl) focusEl.focus();
    });
  }
  const info = (title, message) => dialog({ title, message, kind: 'info' });
  const warn = (title, message) => dialog({ title, message, kind: 'warn' });
  function showError(title, err) {
    const msg = typeof err === 'string' ? err : errorText(err);
    let extra = '';
    if (err && Array.isArray(err.errors) && err.errors.length) {
      extra = '<div class="screen"><div class="screen-inner"><span class="scr-ch">KESALAHAN PER BARIS</span><div class="scr-log">' +
        err.errors.slice(0, 200).map(e => '<div>' + esc(typeof e === 'string' ? e.replace(/^line (\d+):/, 'BARIS $1:') : (e.message || JSON.stringify(e))) + '</div>').join('') +
        '</div></div></div>';
    }
    return dialog({ title: title || 'Kesalahan', message: msg, kind: 'error', body: extra, wide: !!extra });
  }
  const confirm = (title, message, okLabel) => dialog({ title, message, kind: 'question',
    buttons: [{ label: okLabel || 'Ya', value: true, default: true }, { label: 'Batal', value: false, cancel: true }] });

  // Tombol sibuk: disable + aria-busy selama promise berjalan.
  async function busy(btn, fn) {
    if (!btn) return fn();
    if (btn.disabled) return undefined;
    btn.disabled = true; btn.setAttribute('aria-busy', 'true');
    try { return await fn(); } finally { btn.disabled = false; btn.removeAttribute('aria-busy'); }
  }

  // ------------------------------------------------------------------ screen / readout
  function screenHTML(opts) {
    return '<div class="screen ' + (opts.cls || '') + '"' + (opts.id ? ' id="' + opts.id + '"' : '') + '>' +
      '<div class="screen-inner ' + (opts.flush ? 'flush' : '') + '"' + (opts.label ? ' role="region" aria-label="' + esc(opts.aria || opts.channel) + '"' : '') + '>' +
      (opts.channel ? '<span class="scr-ch">' + esc(opts.channel) + '</span>' : '') +
      (opts.rec ? '<span class="scr-rec ' + (opts.recCls || '') + '">' + esc(opts.rec) + '</span>' : '') +
      '<div class="scr-body">' + (opts.body || '') + '</div></div></div>';
  }
  function readoutHTML(label, value, sub, cls) {
    return '<div class="readout screen"><div class="screen-inner" role="group" aria-label="' + esc(label) + '">' +
      '<span class="r-lbl">' + esc(label) + '</span><span class="r-val num ' + (cls || '') + '">' + value + '</span>' +
      (sub ? '<span class="r-sub">' + sub + '</span>' : '') + '</div></div>';
  }
  const emptyHTML = text => '<div class="scr-empty">' + esc(text || 'BELUM ADA DATA') + '</div>';
  const loadingHTML = () => '<div class="scr-empty" role="status">MEMUAT DATA…</div>';

  // Tabel data dalam screen. cols: [{key|get, label, cls, html}]
  function tableHTML(cols, rows, opts) {
    opts = opts || {};
    if (!rows || !rows.length) return emptyHTML(opts.empty);
    return '<div class="table-wrap"><table class="scr-table">' + (opts.caption ? '<caption class="sr-only">' + esc(opts.caption) + '</caption>' : '') +
      '<thead><tr>' + cols.map(c => '<th scope="col" class="' + (c.cls || '') + '">' + esc(c.label) + '</th>').join('') + '</tr></thead><tbody>' +
      rows.map((r, i) => '<tr' + (opts.rowAttr ? ' ' + opts.rowAttr(r, i) : '') + '>' + cols.map(c => {
        const v = c.get ? c.get(r, i) : r[c.key];
        return '<td class="' + (c.cls || '') + '">' + (c.html ? (v === null || v === undefined ? NA : v) : esc(v === null || v === undefined || v === '' ? NA : v)) + '</td>';
      }).join('') + '</tr>').join('') + '</tbody></table></div>';
  }

  // Navigasi halaman untuk kontrak {items,total,limit,offset}
  function pagerHTML(total, limit, offset) {
    if (!total || total <= limit) return '';
    const page = Math.floor(offset / limit) + 1, pages = Math.ceil(total / limit);
    return '<div class="btn-row" style="margin-top:8px"><button type="button" class="small" data-page="' + (page - 1) + '"' + (page <= 1 ? ' disabled' : '') + '>‹ Sebelumnya</button>' +
      '<span>Halaman ' + page + ' dari ' + pages + ' (' + int(total) + ' baris)</span>' +
      '<button type="button" class="small" data-page="' + (page + 1) + '"' + (page >= pages ? ' disabled' : '') + '>Berikutnya ›</button></div>';
  }

  // Tab ala property sheet, aksesibel (panah kiri/kanan).
  function bindTabs(root, onChange) {
    const tabs = $$('[role=tab]', root);
    const select = t => {
      tabs.forEach(x => { const on = x === t; x.setAttribute('aria-selected', on); x.tabIndex = on ? 0 : -1; });
      if (onChange) onChange(t.dataset.tab, t);
    };
    tabs.forEach((t, i) => {
      t.addEventListener('click', () => select(t));
      t.addEventListener('keydown', e => {
        const d = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
        if (d) { e.preventDefault(); const n = tabs[(i + d + tabs.length) % tabs.length]; n.focus(); select(n); }
      });
    });
    return select;
  }

  // ---------------------------------------------- preferensi "Garis wilayah"
  // Server merender dua varian tiap preview map (polos dan bergaris wilayah,
  // lihat etl/admin_overlay.py). Pilihan pengguna disimpan di localStorage
  // dan hanya menukar src <img> -- halaman tidak digambar ulang, jadi posisi
  // gulir, tab, dan lightbox yang terbuka tidak hilang saat dicentang.
  const ADM_KEY = 'orbit-u.garis_wilayah';
  let admOn = null;

  function boundaries() {
    if (admOn === null) { try { admOn = localStorage.getItem(ADM_KEY) === '1'; } catch (e) { admOn = false; } }
    return admOn;
  }
  function setBoundaries(on) {
    admOn = !!on;
    try { localStorage.setItem(ADM_KEY, admOn ? '1' : '0'); } catch (e) { /* mode privat: pilihan tidak diingat */ }
    applyBoundaries();
    document.dispatchEvent(new CustomEvent('orbit-u:garis-wilayah', { detail: admOn }));
  }
  // Tiap <img> preview ditulis dengan data-url (polos) + data-url-adm
  // (bergaris) oleh imgAttrs(); ini yang menukar keduanya.
  function applyBoundaries(root) {
    $$('img[data-url]', root).forEach(img => {
      const want = (boundaries() && img.dataset.urlAdm) || img.dataset.url;
      if (img.getAttribute('src') !== want) img.setAttribute('src', want);
    });
  }
  // p = item preview dari API: {url, url_boundaries?}. url_boundaries tidak
  // ada untuk scene yang varian bergarisnya belum pernah dirender -- tile itu
  // tetap tampil polos walau checkbox aktif.
  function imgSrc(p) { return (boundaries() && p.url_boundaries) || p.url; }
  function imgAttrs(p) {
    return 'src="' + esc(imgSrc(p)) + '" data-url="' + esc(p.url) + '"' +
      (p.url_boundaries ? ' data-url-adm="' + esc(p.url_boundaries) + '"' : '');
  }

  // Lightbox preview citra: jendela dialog dengan gambar di dalam screen.
  //
  // opts.action = {label} menambah satu tombol aksi di samping Tutup. Promise
  // dialog ini lalu RESOLVE DENGAN ITEM yang sedang dilihat (bukan `true`),
  // supaya pemanggil tahu lapisan mana yang dimaksud -- indeks yang sedang
  // tampil hidup di closure ini, bukan di pemanggil, karena tombol
  // Sebelumnya/Berikutnya bisa menggesernya setelah dialog dibuka.
  function lightbox(items, index, opts) {
    opts = opts || {};
    let i = index || 0;
    const render = win => {
      const it = items[i];
      $('.lb-body', win).innerHTML = screenHTML({ channel: it.channel || it.title, rec: it.rec || '', flush: false,
        body: '<img ' + imgAttrs(it) + ' alt="' + esc(it.title) + '" style="display:block;margin:0 auto;max-height:60vh">' +
          (it.legend || '') + (it.note ? '<p class="scr-text" style="margin-top:8px">' + it.note + '</p>' : '') });
      $('.lb-pos', win).textContent = (i + 1) + ' / ' + items.length + ' — ' + it.title;
    };
    const actionBtn = opts.action ? [{ label: opts.action.label, value: 'action' }] : [];
    return dialog({ title: 'Pratinjau citra', wide: 'x',
      body: '<div class="lb-body"></div><div class="btn-row" style="margin:8px 0"><button type="button" class="small lb-prev">‹ Sebelumnya</button><span class="lb-pos"></span><button type="button" class="small lb-next">Berikutnya ›</button></div>',
      buttons: actionBtn.concat([{ label: 'Tutup', value: true, default: true, cancel: true }]),
      collect: (win, val) => val === 'action' ? items[i] : val,
      onOpen: win => {
        render(win);
        const go = d => { i = (i + d + items.length) % items.length; render(win); };
        $('.lb-prev', win).addEventListener('click', () => go(-1));
        $('.lb-next', win).addEventListener('click', () => go(1));
        win.addEventListener('keydown', e => { if (e.key === 'ArrowLeft') go(-1); if (e.key === 'ArrowRight') go(1); });
      } });
  }

  // ------------------------------------------------------------------ grafik SVG di screen
  // series: [{label, cls, color?, forecast?:[{x,mean,lo,hi}], points:[{x:'YYYY-MM-DD', y}]}];
  // opts: {bar, thresholds:{name:v}, forecast:{points:[{x,mean,lo,hi}]}, unit, selected}
  // `color` (opsional) mewarnai garis satu seri — dipakai Forecast, tempat setiap
  // band/kecamatan punya warna tetap. `forecast` per seri digambar dengan warna seri itu.
  function chartSVG(series, opts) {
    opts = opts || {};
    const W = opts.width || 560, H = opts.height || 190, L = 44, R = 12, T = 14, B = 24;
    const t = d => (parseDate(d) || new Date()).getTime();
    const all = series.flatMap(s => s.points.filter(p => p.y !== null && p.y !== undefined));
    const fc = ((opts.forecast && opts.forecast.points) || []).concat(series.flatMap(s => s.forecast || []));
    if (!all.length) return emptyHTML('NO DATA');
    const xs = all.map(p => t(p.x)).concat(fc.map(p => t(p.x)));
    let x0 = Math.min(...xs), x1 = Math.max(...xs);
    if (x1 === x0) { x0 -= 3 * 864e5; x1 += 3 * 864e5; }
    const thr = opts.thresholds || {};
    const ys = all.map(p => p.y).concat(fc.flatMap(p => [p.lo, p.hi, p.mean]).filter(v => v !== null && v !== undefined)).concat(Object.values(thr));
    let y0 = Math.min(...ys), y1 = Math.max(...ys);
    if (opts.bar || opts.zero) y0 = Math.min(0, y0);
    const pad = (y1 - y0) * 0.08 || 1;
    // Nilai tak-negatif (hujan) tidak diberi ruang di bawah nol.
    if (!opts.bar && !(opts.zero && y0 >= 0)) y0 -= pad;
    y1 += pad;
    const X = v => L + (v - x0) / (x1 - x0) * (W - L - R);
    const Y = v => T + (1 - (v - y0) / (y1 - y0)) * (H - T - B);
    let g = '';
    for (let k = 0; k <= 3; k++) {
      const v = y0 + (y1 - y0) * k / 3;
      g += '<line class="grid" x1="' + L + '" x2="' + (W - R) + '" y1="' + Y(v) + '" y2="' + Y(v) + '"/>' +
        '<text class="axis" x="' + (L - 4) + '" y="' + (Y(v) + 3) + '" text-anchor="end">' + num(v, Math.abs(y1 - y0) < 0.5 ? 2 : Math.abs(y1 - y0) < 5 ? 1 : 0) + '</text>';
    }
    const dates = Array.from(new Set(all.map(p => p.x).concat(fc.map(p => p.x)))).sort();
    const step = Math.max(1, Math.ceil(dates.length / 6));
    // Label terakhir selalu tampil; label kelipatan step yang terlalu dekat dengannya dilewati supaya tidak bertumpuk.
    dates.forEach((d, k) => { if (k === dates.length - 1 || (k % step === 0 && dates.length - 1 - k >= step * 0.6))
      g += '<text class="axis" x="' + X(t(d)) + '" y="' + (H - 6) + '" text-anchor="middle">' + date(d, 'short') + '</text>'; });
    if (opts.selected) g += '<line class="sel" x1="' + X(t(opts.selected)) + '" x2="' + X(t(opts.selected)) + '" y1="' + T + '" y2="' + (H - B) + '"/>';
    Object.entries(thr).forEach(([name, v]) => {
      g += '<line class="thr" x1="' + L + '" x2="' + (W - R) + '" y1="' + Y(v) + '" y2="' + Y(v) + '"/>' +
        '<text class="thr-lbl" x="' + (L + 4) + '" y="' + (Y(v) - 3) + '">AMBANG ' + esc(name.toUpperCase()) + ' ' + num(v, 0) + '</text>';
    });
    const unit = opts.unit ? ' ' + opts.unit : '';
    const hits = [];
    // Penanda kejadian: garis vertikal amber + nomor (keterangan di tabel/tooltip).
    (opts.markers || []).forEach((m, k) => {
      const mx = X(t(m.x));
      if (mx < L || mx > W - R) return;
      g += '<line class="mk" x1="' + mx + '" x2="' + mx + '" y1="' + T + '" y2="' + (H - B) + '"/>' +
        '<text class="mk-lbl" x="' + (mx + 2) + '" y="' + (T + 9 + (k % 3) * 10) + '">' + esc(m.label || String(k + 1)) + '</text>';
      hits.push({ x: mx, y: T + 6, tip: m.tip || m.label });
    });
    series.forEach((s, si) => {
      const pts = s.points.filter(p => p.y !== null && p.y !== undefined);
      if (opts.bar) {
        const bw = Math.max(3, Math.min(18, (W - L - R) / (dates.length * 1.6)));
        pts.forEach(p => { const y = Y(p.y), yb = Y(Math.max(0, y0));
          g += '<rect class="bar" x="' + (X(t(p.x)) - bw / 2) + '" y="' + y + '" width="' + bw + '" height="' + Math.max(1, yb - y) + '"/>'; });
      } else {
        // Garis putus di nilai kosong (tidak menyambung celah data).
        let seg = [];
        const stroke = s.color ? ' style="stroke:' + esc(s.color) + '"' : '';
        const fill = s.color ? ' style="fill:' + esc(s.color) + '"' : '';
        // Satu titik saja tetap digambar sebagai titik (polyline butuh dua).
        const flush = () => { if (seg.length > 1) g += '<polyline class="line ' + (s.cls || '') + '"' + stroke + ' points="' + seg.join(' ') + '"/>'; seg = []; };
        s.points.forEach(p => { if (p.y === null || p.y === undefined) flush(); else seg.push(X(t(p.x)) + ',' + Y(p.y)); });
        flush();
        // Satu titik per tanggal yang berdata; diperkecil bila rapat.
        const ds = pts.length > 120 ? 2 : pts.length > 60 ? 3 : 4;
        pts.forEach(p => { g += '<rect class="dot"' + fill + ' x="' + (X(t(p.x)) - ds / 2) + '" y="' + (Y(p.y) - ds / 2) + '" width="' + ds + '" height="' + ds + '"/>'; });
      }
      pts.forEach(p => hits.push({ x: X(t(p.x)), y: Y(p.y), tip: (series.length > 1 ? s.label + ' · ' : '') + date(p.x) + ': ' + num(p.y, 1) + unit }));
    });
    const drawFc = (s, pts, color) => {
      const lastS = s.points.filter(p => p.y !== null && p.y !== undefined);
      const last = lastS[lastS.length - 1];
      const start = last ? [[X(t(last.x)), Y(last.y)]] : [];
      const band = start.concat(pts.map(p => [X(t(p.x)), Y(p.hi)])).concat(pts.slice().reverse().map(p => [X(t(p.x)), Y(p.lo)]));
      g += '<polygon class="band"' + (color ? ' style="fill:' + esc(color) + ';fill-opacity:.14"' : '') + ' points="' + band.map(q => q.join(',')).join(' ') + '"/>';
      g += '<polyline class="fc"' + (color ? ' style="stroke:' + esc(color) + '"' : '') + ' points="' + start.concat(pts.map(p => [X(t(p.x)), Y(p.mean)])).map(q => q.join(',')).join(' ') + '"/>';
      pts.forEach(p => hits.push({ x: X(t(p.x)), y: Y(p.mean), tip: (series.length > 1 ? s.label + ' · ' : '') + 'Prakiraan ' + date(p.x) + ': ' + num(p.mean, 1) + unit + ' (rentang ' + num(p.lo, 1) + '–' + num(p.hi, 1) + ')' }));
    };
    if (opts.forecast && opts.forecast.points && opts.forecast.points.length) drawFc(series[0], opts.forecast.points, null);
    series.forEach(s => { if (s.forecast && s.forecast.length) drawFc(s, s.forecast, s.color); });
    if (fc.length) g += '<text class="fc-lbl" x="' + (W - R) + '" y="' + (T - 3) + '" text-anchor="end">PRAKIRAAN STATISTIK, BUKAN PERINGATAN</text>';
    hits.forEach(h => { g += '<rect class="hit" x="' + (h.x - 8) + '" y="' + (h.y - 8) + '" width="16" height="16" data-tip="' + esc(h.tip) + '"><title>' + esc(h.tip) + '</title></rect>'; });
    return '<div class="chart" style="position:relative"><svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="' + esc(opts.label || 'Grafik') + '">' + g + '</svg></div>';
  }

  // ------------------------------------------------------------------ kategori BMKG (INTERFACE §2.3)
  // Warna sinyal dibatasi 3 (DESIGN §8): tingkat terang phos → amber → alert,
  // ditambah pola arsir untuk "Sangat lebat"/"Ekstrem", dan nama kategori selalu tertulis.
  const BMKG = {
    RINGAN: { label: 'Ringan', short: 'R', range: '< 20 mm', color: '#1a9960', opacity: .35, mark: '·' },
    SEDANG: { label: 'Sedang', short: 'S', range: '20–<50 mm', color: '#33ff99', opacity: .55, mark: '▪' },
    LEBAT: { label: 'Lebat', short: 'L', range: '50–<100 mm', color: '#ffb000', opacity: .6, mark: '▲' },
    SANGAT_LEBAT: { label: 'Sangat lebat', short: 'SL', range: '100–<150 mm', color: '#ff3b3b', opacity: .6, mark: '▲▲', hatch: 'hatch-a' },
    EKSTREM: { label: 'Ekstrem', short: 'E', range: '≥ 150 mm', color: '#ff3b3b', opacity: .9, mark: '▲▲▲', hatch: 'hatch-b' },
  };
  function bmkgCategory(mm) {
    if (mm === null || mm === undefined) return null;
    return mm < 20 ? 'RINGAN' : mm < 50 ? 'SEDANG' : mm < 100 ? 'LEBAT' : mm < 150 ? 'SANGAT_LEBAT' : 'EKSTREM';
  }
  function bmkgClass(code) { return { LEBAT: 'v-amber', SANGAT_LEBAT: 'v-alert', EKSTREM: 'v-alert' }[code] || ''; }

  const SEVERITY = { INFO: { label: 'Info', cls: '' }, WARNING: { label: 'Peringatan', cls: 'v-amber' }, CRITICAL: { label: 'Kritis', cls: 'v-alert' } };
  const ROLE_LABEL = { PUBLIC: 'Publik', USER: 'Relawan (USER)', ANALYST: 'Analis (ANALYST)', DATA_ENGINEER: 'Data Engineer', ADMIN: 'Administrator' };
  const LEVEL = [{ label: 'Normal', cls: '' }, { label: 'Waspada', cls: 'v-amber' }, { label: 'Tinggi', cls: 'v-alert' }];

  // Label dataset & satelit. Dulu ada salinannya di catalog.js saja; begitu
  // "Proses berjalan" dan Penyimpanan ikut memakainya, satu salinan di sini
  // mencegah dua daftar status yang perlahan berbeda isi.
  const DATASET_STATUS = {
    QUEUED: 'Antre', PREPARING: 'Menyiapkan', DOWNLOADING: 'Mengunduh', PROCESSING: 'Memproses', PAUSED: 'Dijeda',
    CLEANUP: 'Membersihkan', COMPLETED: 'Selesai', PARTIAL: 'Sebagian', FAILED: 'Gagal', CANCELLED: 'Dibatalkan',
    DELETING: 'Menghapus', DRAFT: 'Draf',
  };
  // Status yang masih bergerak: selama salah satunya ada, halaman perlu menjadwal
  // pembaruan berkala.
  const DATASET_ACTIVE = new Set(['QUEUED', 'PREPARING', 'DOWNLOADING', 'PROCESSING', 'PAUSED', 'CLEANUP', 'DELETING']);
  const SOURCE_LABEL = { sentinel1: 'Sentinel-1', modis: 'MODIS', gpm: 'GPM', fusion: 'Fusion',
    SENTINEL1: 'Sentinel-1', MODIS: 'MODIS', GPM: 'GPM', FUSION: 'Fusion' };
  const datasetStatus = code => DATASET_STATUS[code] || code || NA;

  // Bar proporsi berlabel: nama di kiri, palang di tengah, angka di kanan.
  // Dipakai Katalog (per sumber, per tier), Penyimpanan mesin, dan Proses
  // berjalan. `total` 0 menghasilkan palang kosong, bukan NaN.
  function barHTML(label, size, total, right) {
    const share = total > 0 ? size / total * 100 : 0;
    return '<div class="bar-row"><span>' + esc(label) + '</span>' +
      '<span class="trk" role="img" aria-label="' + esc(label + ' ' + num(share, 0) + '%') + '">' +
      '<i style="width:' + Math.max(share, size ? 1 : 0).toFixed(1) + '%"></i></span>' +
      '<span class="num" style="text-align:right">' + esc(right) + '</span></div>';
  }

  // Palang progres pipeline/penghapusan. `percent` di luar 0–100 dijepit supaya
  // nilai aneh dari server tidak merusak tata letak.
  function progressHTML(percent, label) {
    const v = Math.max(0, Math.min(100, Number(percent) || 0));
    return '<div class="progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="' +
      v.toFixed(0) + '" aria-label="' + esc(label || 'Progres') + '"><i style="width:' + Math.max(1, v).toFixed(1) + '%"></i></div>';
  }

  // Antrean forecast GET /api/diagram/forecast (M61), dipakai halaman Forecast:
  // `parallel` request sekaligus, hasil di `cache` per kunci deret (sakelar
  // mati-nyala tidak menghitung ulang). run() baru membatalkan antrean lama.
  // Progres + sisa waktu (rata-rata lama deret yang selesai × sisa deret)
  // digambar ke elemen dari progEl().
  function forecastQueue(progEl, parallel) {
    const q = { cache: {}, gen: 0 };
    const render = p => {
      const el = progEl();
      if (!el) return;
      if (!p || p.done >= p.total) { el.hidden = true; el.innerHTML = ''; return; }
      const elapsed = (performance.now() - p.t0) / 1000;
      const left = p.done ? Math.max(1, Math.round(elapsed / p.done * (p.total - p.done))) : null;
      el.hidden = false;
      el.innerHTML = progressHTML(p.done / p.total * 100, 'Progres forecast') +
        '<p class="scr-text v-dim fc-prog-text">MENGHITUNG FORECAST 15 HARI · ' + p.done + ' DARI ' + p.total + ' DERET · ' +
        (left === null ? 'MEMPERKIRAKAN WAKTU…' : '± ' + left + ' DETIK LAGI') + '</p>';
    };
    q.run = async (jobs, onDone) => {
      const gen = ++q.gen;
      const todo = jobs.filter(j => !(j.key in q.cache));
      const prog = { done: 0, total: todo.length, t0: performance.now() };
      render(prog);
      let next = 0;
      const worker = async () => {
        while (next < todo.length) {
          const j = todo[next++];
          let r;
          try { r = await API.get('/api/diagram/forecast' + API.qs(j.q)); }
          catch (e) { r = { error: true, points: [], notes: [(e && (e.message || e.code)) || 'gagal'] }; }
          if (q.gen !== gen) return;
          q.cache[j.key] = r;
          prog.done++;
          render(prog);
          onDone(j);
        }
      };
      await Promise.all(Array.from({ length: parallel || 3 }, worker));
    };
    q.stop = () => { q.gen++; render(null); };
    q.reset = () => { q.stop(); q.cache = {}; };
    return q;
  }
  const forecastDesc = f => !f ? 'menghitung…' : f.error ? 'gagal: ' + f.notes.join(' ') : !f.points.length ? (f.notes[0] || 'data kurang') :
    f.model_label + ' · keyakinan ' + f.confidence + (f.backtest ? ' (skill ' + num(f.backtest.skill, 2) + ')' : '');
  const forecastToggleHTML = (attr, on) => '<label class="check fc-toggle"><input type="checkbox" ' + attr + (on ? ' checked' : '') +
    '> Tampilkan forecast 15 hari</label>';

  // Banner pekerjaan dataset utama (M58) dari GET /api/data/activity: backfill
  // Sentinel-1 (siklus Live) dan Job Hidromet. Dipakai Data › Ringkasan dan
  // Sistem › Pengaturan supaya backfill yang berjalan di proses mana pun terlihat.
  // Kosong bila tidak ada yang berjalan.
  function mainActivityHTML(a) {
    if (!a || !a.running) return '';
    const rows = [];
    (a.live || []).filter(l => l.running).forEach(l => {
      const p = l.progress || {}, c = p.current;
      rows.push('<b>Backfill Sentinel-1 (' + esc(l.name) + ')</b>: ' +
        (p.frames_total ? int(p.frames_done) + '/' + int(p.frames_total) + ' frame (' + num(p.percent, 1) + '%), ' +
          int(p.dates_done) + '/' + int(p.dates_total) + ' tanggal lintasan' : esc(l.status_message || '')) +
        (c ? '. Sedang: ' + esc((c.date ? date(c.date) + ', ' : '') + (c.stage || '') + (c.percent != null && c.stage === 'DOWNLOAD' ? ' ' + num(c.percent, 0) + '%' : '')) : '') +
        (p.eta ? '. <b>Perkiraan selesai ' + esc(dateTime(p.eta)) + ' WIB</b>' : '') + '.' +
        (p.frames_total ? progressHTML(p.percent, 'Progres backfill Sentinel-1') : ''));
    });
    const h = a.hydromet || {};
    if (h.locked) rows.push('<b>Job Hidromet (GPM + MODIS)</b>: sedang mengerjakan ' + esc(h.current_date ? date(h.current_date) : 'tanggal berikutnya') +
      ', ' + int(h.done_last_hour) + ' tanggal selesai dalam 1 jam terakhir.');
    return '<div class="banner raised" role="status">' + icon('info32') + '<div class="b-body">' +
      '<b class="v-cyan">● BACKFILL DATASET UTAMA SEDANG BERJALAN</b><br>' + rows.join('<br>') +
      '<br><a href="#data/proses">Rincian di Data › Proses berjalan →</a></div></div>';
  }

  // Unduh berkas (Blob) dengan nama dari Content-Disposition.
  function saveBlob(blob, name) {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = name || 'unduhan';
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 4000);
  }

  return { icon, ICONS, NA, num, int, pct, bytes, date, dateTime, isoDate, addDays, parseDate, esc, $, $$,
    ERROR_TEXT, errorText, windowHTML, dialog, info, warn, showError, confirm, busy, screenHTML, readoutHTML,
    boundaries, setBoundaries, applyBoundaries, imgSrc, imgAttrs,
    emptyHTML, loadingHTML, tableHTML, pagerHTML, bindTabs, lightbox, chartSVG, BMKG, bmkgCategory, bmkgClass,
    SEVERITY, ROLE_LABEL, LEVEL, saveBlob,
    DATASET_STATUS, DATASET_ACTIVE, SOURCE_LABEL, datasetStatus, barHTML, progressHTML, mainActivityHTML,
    forecastQueue, forecastDesc, forecastToggleHTML };
})();
window.UI = UI;
