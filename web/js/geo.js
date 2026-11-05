'use strict';

const Geo = (() => {
  const ROUGH_M = 2000;

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

  function locate() {
    return new Promise((resolve, reject) => {
      if (!window.isSecureContext || !('geolocation' in navigator)) { reject({ code: 0 }); return; }
      navigator.geolocation.getCurrentPosition(
        p => resolve({ lon: p.coords.longitude, lat: p.coords.latitude, accuracy: p.coords.accuracy }),
        e => reject({ code: e && e.code, message: e && e.message }),
        { enableHighAccuracy: false, timeout: 12000, maximumAge: 300000 });
    });
  }

  function inRing(x, y, ring) {
    let inside = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const xi = ring[i][0], yi = ring[i][1], xj = ring[j][0], yj = ring[j][1];
      if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) inside = !inside;
    }
    return inside;
  }
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
  function regionAt(lon, lat, geojson) {
    return ((geojson && geojson.features) || []).find(f => inGeometry(lon, lat, f.geometry)) || null;
  }

  const REASON = {
    insecure: 'Lokasi perangkat hanya bisa dibaca lewat koneksi aman (HTTPS). Pilih kecamatan dari daftar.',
    unsupported: 'Peramban ini tidak mendukung lokasi perangkat. Pilih kecamatan dari daftar.',
    denied: 'Izin lokasi untuk situs ini ditolak. Pilih kecamatan dari daftar, atau aktifkan izinnya (petunjuk di bawah).',
    1: 'Izin lokasi ditolak. Pilih kecamatan dari daftar, atau aktifkan izinnya (petunjuk di bawah).',
    2: 'Lokasi perangkat tidak tersedia — layanan lokasi mungkin mati. Aktifkan, lalu coba lagi.',
    3: 'Lokasi perangkat tidak didapat dalam 12 detik. Coba lagi di tempat terbuka, atau pilih kecamatan dari daftar.',
    0: 'Lokasi perangkat tidak dapat dibaca. Pilih kecamatan dari daftar.',
  };

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
