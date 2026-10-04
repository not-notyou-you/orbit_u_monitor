// js/login.js — /masuk. POST /api/auth/login menyetel cookie HttpOnly; sukses → ?next atau /app.
'use strict';
Pages['login'] = {
  init(root) {
    UI.$$('[data-icon]', root).forEach(el => { el.innerHTML = UI.icon(el.dataset.icon); });
    const params = new URLSearchParams(location.search);
    const notice = UI.$('#loginNotice', root);
    const reason = { sesi: ['warn32', UI.ERROR_TEXT.SESSION_EXPIRED], masuk: ['info32', 'Halaman itu memerlukan login.'],
      keluar: ['info32', 'Anda sudah keluar. Sampai jumpa.'] }[params.get('alasan')];
    if (reason) { notice.innerHTML = UI.icon(reason[0]) + '<div class="b-body">' + UI.esc(reason[1]) + '</div>'; notice.classList.remove('hidden'); }

    const form = UI.$('#loginForm', root), u = UI.$('#username', root), p = UI.$('#password', root);
    const status = t => { UI.$('#loginStatus', root).textContent = 'Status: ' + t; };
    const setErr = (input, msg) => {
      input.setAttribute('aria-invalid', msg ? 'true' : 'false');
      UI.$('#' + input.id + 'Err', root).textContent = msg || '';
    };
    // Validasi langsung saat mengetik (setelah field pernah disentuh).
    [u, p].forEach(i => {
      i.addEventListener('blur', () => setErr(i, i.value.trim() ? '' : 'Wajib diisi.'));
      i.addEventListener('input', () => { if (i.getAttribute('aria-invalid') === 'true' && i.value.trim()) setErr(i, ''); });
    });
    UI.$('#showPw', root).addEventListener('change', e => { p.type = e.target.checked ? 'text' : 'password'; });
    const next = () => {
      const n = params.get('next') || '/app';
      return n.startsWith('/') && !n.startsWith('//') && !n.startsWith('/masuk') ? n : '/app';
    };
    form.addEventListener('submit', async ev => {
      ev.preventDefault();
      const miss = [u, p].filter(i => !i.value.trim());
      [u, p].forEach(i => setErr(i, miss.includes(i) ? 'Wajib diisi.' : ''));
      if (miss.length) { miss[0].focus(); return; }
      await UI.busy(UI.$('#loginBtn', root), async () => {
        status('Memeriksa…');
        try {
          await API.post('/api/auth/login', { username: u.value.trim(), password: p.value }, { noRedirect: true });
          status('Berhasil'); location.replace(next());
        } catch (e) {
          status('Gagal (' + (e.status || 'jaringan') + ')');
          p.value = ''; await UI.showError('Gagal masuk', e); p.focus();
        }
      });
    });
    u.focus();
  },
};
