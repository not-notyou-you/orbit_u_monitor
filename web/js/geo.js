// web/js/geo.js — lokasi perangkat untuk "Lokasi saya" di Beranda (M63).
//
// Koordinat TIDAK pernah dikirim ke server: titik dicocokkan di browser dengan
// poligon kecamatan AOI dari GET /api/regions (sudah publik, sudah di-cache
// Maps.regions()), dan yang dipakai halaman hanya region_id hasilnya.
//
// Kompatibilitas (diuraikan di INTERFACE.md §2 halaman 1):
// * Geolocation API hanya ada di konteks aman: HTTPS, atau localhost saat
//   pengembangan. Lewat http://IP-LAN browser menolaknya tanpa bertanya.
// * Permissions API untuk 'geolocation' tidak ada di Safari < 16 dan
//   sebagian WebView; tanpa itu keadaannya dianggap 'prompt' (belum tahu),
//   jadi halaman menampilkan tombol, bukan meminta izin sendiri.
// * Izin TIDAK pernah diminta saat halaman dibuka. Hanya bila sudah
//   'granted' lokasi dibaca otomatis; selain itu lewat tombol. Prompt
//   otomatis cenderung ditolak refleks, dan di iOS penolakan per situs
//   hanya bisa dibatalkan dari Pengaturan.
// * enableHighAccuracy: false. Tingkat kecamatan cukup ±1 km; lokasi
//   kasar (Wi-Fi/seluler) jauh lebih cepat dan hemat baterai daripada GPS.
// * Desktop (Windows/macOS) tanpa GPS memperkirakan lokasi dari Wi-Fi/IP;
//   akurasinya bisa beberapa km, jadi halaman menyebutnya "perkiraan".
'use strict';

const Geo = (() => {
  // Di atas ini titiknya terlalu kasar untuk yakin soal kecamatan.
  const ROUGH_M = 2000;

  // 'insecure' | 'unsupported' | 'granted' | 'prompt' | 'denied'
  async function state() {
    if (!window.isSecureContext) return 'insecure';
    if (!('geolocation' in navigator)) return 'unsupported';
    try {
      if (navigator.permissions && navigator.permissions.query) {
        const p = await navigator.permissions.query({ name: 'geolocation' });
        return p.state;
      }
    } catch (e) { /* Safari < 16, WebView: nama izin tidak dikenal */ }
    return 'prompt';
  }

  // Dipanggil bila izin berubah dari luar halaman (pengguna mencabutnya di
  // pengaturan situs). Mengembalikan fungsi untuk berhenti mendengar.
  function watchPermission(onChange) {
    let status = null, alive = true;
    const handler = () => { if (alive && status) onChange(status.state); };
    try {
      if (navigator.permissions && navigator.permissions.query) {
        navigator.permissions.query({ name: 'geolocation' }).then(s => {
          if (!alive) return;
          status = s;
          if (s.addEventListener) s.addEventListener('change', handler); else s.onchange = handler;
        }).catch(() => {});
      }
    } catch (e) { /* tidak didukung: tidak ada yang didengar */ }
    return () => {
      alive = false;
      if (status) { if (status.removeEventListener) status.removeEventListener('change', handler); else status.onchange = null; }
    };
  }

  // {lon, lat, accuracy} atau lempar {code, message} dengan code:
  // 1 ditolak, 2 lokasi perangkat tidak tersedia, 3 waktu habis.
  function locate() {
    return new Promise((resolve, reject) => {
      if (!window.isSecureContext || !('geolocation' in navigator)) { reject({ code: 0 }); return; }
      navigator.geolocation.getCurrentPosition(
        p => resolve({ lon: p.coords.longitude, lat: p.coords.latitude, accuracy: p.coords.accuracy }),
        e => reject({ code: e && e.code, message: e && e.message }),
        { enableHighAccuracy: false, timeout: 12000, maximumAge: 300000 });
    });
  }

  // Ray-casting genap-ganjil satu cincin [[lon, lat], ...].
  function inRing(x, y, ring) {
    let inside = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const xi = ring[i][0], yi = ring[i][1], xj = ring[j][0], yj = ring[j][1];
      if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) inside = !inside;
    }
    return inside;
  }
  // Polygon: di dalam cincin luar dan tidak di dalam lubang mana pun.
  function inPolygon(x, y, rings) {
    if (!rings.length || !inRing(x, y, rings[0])) return false;
    for (let k = 1; k < rings.length; k++) if (inRing(x, y, rings[k])) return false;
    return true;
  }
  function inGeometry(x, y, g) {
    if (!g) return false;
    if (g.type === 'Polygon') return inPolygon(x, y, g.coordinates);
    if (g.type === 'MultiPolygon') return g.coordinates.some(p => inPolygon(x, y, p));
    return false;
  }
  // Fitur kecamatan yang memuat titik, atau null (di luar wilayah terdaftar).
  function regionAt(lon, lat, geojson) {
    return ((geojson && geojson.features) || []).find(f => inGeometry(lon, lat, f.geometry)) || null;
  }

  // Penjelasan untuk orang, sesuai keadaan/kode galat.
  const REASON = {
    insecure: 'Lokasi perangkat hanya bisa dibaca lewat koneksi aman (HTTPS). Pilih kecamatan dari daftar.',
    unsupported: 'Peramban ini tidak mendukung lokasi perangkat. Pilih kecamatan dari daftar.',
    denied: 'Izin lokasi untuk situs ini ditolak. Pilih kecamatan dari daftar, atau aktifkan izinnya (petunjuk di bawah).',
    1: 'Izin lokasi ditolak. Pilih kecamatan dari daftar, atau aktifkan izinnya (petunjuk di bawah).',
    2: 'Lokasi perangkat tidak tersedia — layanan lokasi mungkin mati. Aktifkan, lalu coba lagi.',
    3: 'Lokasi perangkat tidak didapat dalam 12 detik. Coba lagi di tempat terbuka, atau pilih kecamatan dari daftar.',
    0: 'Lokasi perangkat tidak dapat dibaca. Pilih kecamatan dari daftar.',
  };

  // Deteksi kasar platform, hanya untuk memilih teks petunjuk izin.
  function platform() {
    const ua = navigator.userAgent || '';
    if (/FBAN|FBAV|Instagram|Line\/|WhatsApp|; wv\)/i.test(ua)) return 'inapp';
    if (/iPhone|iPad|iPod/i.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1)) return 'ios';
    if (/Android/i.test(ua)) return 'android';
    if (/Windows/i.test(ua)) return 'windows';
    if (/Macintosh|Mac OS X/i.test(ua)) return 'mac';
    return 'other';
  }
  const HELP = {
    ios: 'iPhone/iPad: Pengaturan › Privasi & Keamanan › Layanan Lokasi harus Aktif; lalu di bagian Safari (atau peramban yang dipakai) pilih "Saat Digunakan". Di Safari, ketuk "aA" di bilah alamat › Pengaturan Situs Web › Lokasi › Izinkan, lalu muat ulang halaman.',
    android: 'Android: ketuk ikon di kiri alamat situs › Izin › Lokasi › Izinkan. Pastikan Lokasi perangkat juga aktif (tarik panel notifikasi › Lokasi), lalu muat ulang halaman.',
    windows: 'Windows: Pengaturan › Privasi & keamanan › Lokasi — aktifkan "Layanan lokasi" dan "Izinkan aplikasi desktop mengakses lokasi". Lalu klik ikon gembok di bilah alamat › Lokasi › Izinkan. Tanpa GPS, lokasi diperkirakan dari Wi-Fi dan bisa meleset beberapa km.',
    mac: 'macOS: Pengaturan Sistem › Privasi & Keamanan › Layanan Lokasi — aktifkan untuk peramban yang dipakai. Lalu klik ikon gembok/info di bilah alamat › Lokasi › Izinkan.',
    inapp: 'Anda membuka halaman ini dari dalam aplikasi (mis. WhatsApp/Instagram/Facebook) yang biasanya tidak meneruskan lokasi. Buka di peramban (menu ⋮ › "Buka di browser"), lalu coba lagi.',
    other: 'Klik ikon gembok/info di bilah alamat › Lokasi › Izinkan, pastikan layanan lokasi perangkat aktif, lalu muat ulang halaman.',
  };

  return { ROUGH_M, state, watchPermission, locate, regionAt, REASON, platform, HELP };
})();
window.Geo = Geo;
