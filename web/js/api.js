// web/js/api.js — klien API (INTERFACE.md §4–6).
// Sesi = cookie HttpOnly `orbit_u_session` yang dikirim browser otomatis
// (satu origin, SameSite=Strict). JWT tidak pernah disentuh JavaScript.
// Setiap request non-GET wajib membawa X-Requested-With: orbit-u (§6, CSRF).
'use strict';

const API = (() => {
  class ApiError extends Error {
    constructor(status, body) {
      super((body && body.detail) || ('HTTP ' + status));
      this.status = status;
      this.code = body && body.code;
      this.detail = body && body.detail;
      this.errors = body && body.errors;
      this.body = body;
    }
  }

  let onUnauthorized = null; // diisi auth.js: alihkan ke /masuk

  async function request(path, opts) {
    opts = opts || {};
    const headers = Object.assign({ 'X-Requested-With': 'orbit-u' }, opts.headers || {});
    let body = opts.body;
    if (body !== undefined && body !== null && !(body instanceof Blob) && !(body instanceof ArrayBuffer) && typeof body !== 'string') {
      headers['Content-Type'] = 'application/json';
      body = JSON.stringify(body);
    }
    let res;
    try {
      res = await fetch(path, { method: opts.method || 'GET', headers, body, credentials: 'same-origin', cache: 'no-store' });
    } catch (e) {
      throw new ApiError(0, { code: 'NETWORK', detail: String(e) });
    }
    if (!res.ok) {
      let data = null;
      try { data = await res.json(); } catch (e) { data = { detail: res.statusText }; }
      const err = new ApiError(res.status, data);
      if (res.status === 401 && onUnauthorized && !opts.noRedirect) onUnauthorized(err);
      throw err;
    }
    if (opts.raw) return res;
    if (res.status === 204) return null;
    const ct = res.headers.get('content-type') || '';
    return ct.includes('application/json') ? res.json() : res.text();
  }

  const get = (path, opts) => request(path, opts);
  const post = (path, body, opts) => request(path, Object.assign({ method: 'POST', body }, opts || {}));
  const put = (path, body, opts) => request(path, Object.assign({ method: 'PUT', body }, opts || {}));
  const patch = (path, body, opts) => request(path, Object.assign({ method: 'PATCH', body }, opts || {}));
  const del = (path, opts) => request(path, Object.assign({ method: 'DELETE' }, opts || {}));

  function qs(params) {
    const p = new URLSearchParams();
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v === undefined || v === null || v === '') return;
      if (Array.isArray(v)) v.forEach(x => p.append(k, x)); else p.append(k, v);
    });
    const s = p.toString();
    return s ? '?' + s : '';
  }

  // Unduh berkas lewat fetch (agar error JSON bisa diterjemahkan) lalu simpan.
  async function download(path, fallbackName) {
    const res = await request(path, { raw: true });
    const cd = res.headers.get('content-disposition') || '';
    const m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd);
    const name = m ? decodeURIComponent(m[1]) : fallbackName;
    UI.saveBlob(await res.blob(), name);
  }

  return { ApiError, request, get, post, put, patch, del, qs, download,
    setUnauthorizedHandler: fn => { onUnauthorized = fn; } };
})();
window.API = API;
