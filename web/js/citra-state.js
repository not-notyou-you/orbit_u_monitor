'use strict';
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
