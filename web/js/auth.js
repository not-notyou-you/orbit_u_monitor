// web/js/auth.js — sesi dan izin UI (INTERFACE.md §3, §6).
// Izin menu diambil dari `permissions` GET /api/auth/me (sumber: backend).
// Menyembunyikan menu hanya kenyamanan; API dan DB tetap menegakkan akses.
'use strict';

const Auth = (() => {
  let me = null;

  function loginUrl(reason) {
    const next = location.pathname + location.hash;
    return '/masuk?' + new URLSearchParams(Object.assign({ next }, reason ? { alasan: reason } : {})).toString();
  }

  API.setUnauthorizedHandler(err => {
    // Hanya halaman yang butuh login yang dialihkan; Beranda/Masuk tidak.
    if (document.body.dataset.requiresAuth === 'true') {
      location.href = loginUrl(err.code === 'SESSION_EXPIRED' ? 'sesi' : 'masuk');
    }
  });

  async function load() {
    try { me = await API.get('/api/auth/me', { noRedirect: true }); }
    catch (e) { me = null; if (e.status !== 401) throw e; }
    return me;
  }

  async function require() {
    const m = await load();
    if (!m) { location.replace(loginUrl()); return new Promise(() => {}); }
    return m;
  }

  const can = perm => !!(me && me.permissions && me.permissions.includes(perm));
  const canAny = perms => !perms || !perms.length || perms.some(can);
  const role = () => (me ? me.role_code : 'PUBLIC');

  async function logout() {
    try { await API.post('/api/auth/logout', null, { noRedirect: true }); } catch (e) { /* tetap keluar */ }
    me = null;
    location.href = '/masuk?alasan=keluar';
  }

  return { load, require, can, canAny, role, logout, user: () => me, loginUrl };
})();
window.Auth = Auth;
