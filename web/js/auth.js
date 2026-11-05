'use strict';

const Auth = (() => {
  let me = null;
  let perms = [];
  let roleCode = 'PUBLIC';

  function loginUrl(reason) {
    const next = location.pathname + location.hash;
    return '/masuk?' + new URLSearchParams(Object.assign({ next }, reason ? { alasan: reason } : {})).toString();
  }

  API.setUnauthorizedHandler(err => {
    if (document.body.dataset.requiresAuth === 'true') {
      location.href = loginUrl(err.code === 'SESSION_EXPIRED' ? 'sesi' : 'masuk');
    }
  });

  async function load() {
    const s = await API.get('/api/auth/session', { noRedirect: true });
    me = s.user || null;
    perms = s.permissions || [];
    roleCode = s.role_code || 'PUBLIC';
    return me;
  }

  async function require() {
    const m = await load().catch(() => null);
    if (!m) { location.replace(loginUrl()); return new Promise(() => {}); }
    return m;
  }

  const can = perm => perms.includes(perm);
  const canAny = list => !list || !list.length || list.some(can);
  const role = () => roleCode;

  async function logout() {
    try { await API.post('/api/auth/logout', null, { noRedirect: true }); } catch (e) { /* tetap keluar */ }
    me = null;
    location.href = '/masuk?alasan=keluar';
  }

  return { load, require, can, canAny, role, logout, user: () => me, loginUrl };
})();
window.Auth = Auth;
