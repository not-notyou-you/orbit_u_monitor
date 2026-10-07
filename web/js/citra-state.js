// js/citra-state.js — status bersama tab Citra Satelit (M56): area terpilih
// dan teks batas waktu per peran. Dimuat app.html supaya tab per satelit dan
// laporan bisa dibuka langsung tanpa lewat Ringkasan.
'use strict';
// Area dan teks batas waktu dipakai bersama oleh tab Citra (ringkasan, per
// satelit, laporan) supaya area yang dipilih ikut saat berpindah tab.
window.CitraState = window.CitraState || (() => {
  let areaId = null;
  try { areaId = Number(sessionStorage.getItem('citra.area')) || null; } catch (e) { areaId = null; }
  return {
    area: () => areaId,
    setArea(id) { areaId = id; try { sessionStorage.setItem('citra.area', String(id)); } catch (e) { /* abaikan */ } },
    windowText(w) {
      if (!w) return '';
      if (w.days === null || w.days === undefined) return 'Peran Anda melihat seluruh arsip citra yang tersedia.';
      return w.role_code === 'PUBLIC'
        ? 'Pengunjung melihat citra 30 hari terakhir (scene terbaru selalu tampil). Masuk atau daftar akun Relawan untuk melihat setahun ke belakang.'
        : 'Relawan melihat citra 1 tahun terakhir. Analis, Data Engineer, dan Administrator melihat seluruh arsip.';
    },
  };
})();
