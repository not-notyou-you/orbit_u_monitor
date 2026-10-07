// js/register.js — /daftar (INTERFACE.md §2 halaman -0, M56). POST /api/auth/register
// membuat akun Relawan (USER; peran dikunci di fungsi DB auth_register_user)
// dan langsung menyetel cookie sesi, lalu diantar ke Beranda.
'use strict';
Pages['register'] = {
  init(root) {
    UI.$$('[data-icon]', root).forEach(el => { el.innerHTML = UI.icon(el.dataset.icon); });
    const $ = s => UI.$(s, root);
    const email = $('#rEmail'), user = $('#rUser'), pw = $('#rPw'), pw2 = $('#rPw2');
    const status = t => { $('#regStatus').textContent = 'Status: ' + t; };
    const setErr = (input, msg) => {
      input.setAttribute('aria-invalid', msg ? 'true' : 'false');
      $('#' + input.id + 'Err').textContent = msg || '';
    };
    const rules = {
      rEmail: v => !v ? 'Wajib diisi.' : /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v) ? '' : 'Format email tidak valid.',
      rUser: v => !v ? 'Wajib diisi.' : /^[a-z0-9_.]{3,50}$/.test(v) ? '' : '3–50 karakter: huruf kecil, angka, titik, atau garis bawah.',
      rPw: v => !v ? 'Wajib diisi.' : v.length < 10 ? 'Minimal 10 karakter.' : new TextEncoder().encode(v).length > 72 ? 'Maksimal 72 byte.' : '',
      rPw2: v => !v ? 'Wajib diisi.' : v !== pw.value ? 'Tidak sama dengan kata sandi.' : '',
    };
    const check = i => { const m = rules[i.id](i.id === 'rUser' ? i.value.trim().toLowerCase() : i.id === 'rEmail' ? i.value.trim() : i.value); setErr(i, m); return !m; };
    [email, user, pw, pw2].forEach(i => {
      i.addEventListener('blur', () => check(i));
      i.addEventListener('input', () => { if (i.getAttribute('aria-invalid') === 'true') check(i); });
    });
    user.addEventListener('change', () => { user.value = user.value.trim().toLowerCase(); });
    $('#rShow').addEventListener('change', e => { pw.type = pw2.type = e.target.checked ? 'text' : 'password'; });
    $('#regForm').addEventListener('submit', async ev => {
      ev.preventDefault();
      const bad = [email, user, pw, pw2].filter(i => !check(i));
      if (bad.length) { bad[0].focus(); return; }
      await UI.busy($('#regBtn'), async () => {
        status('Mendaftarkan…');
        try {
          await API.post('/api/auth/register', { email: email.value.trim(), username: user.value.trim().toLowerCase(),
            password: pw.value, password_confirm: pw2.value }, { noRedirect: true });
          status('Berhasil');
          await UI.info('Akun dibuat', 'Selamat datang, ' + user.value.trim().toLowerCase() + '. Anda sudah masuk sebagai Relawan.');
          location.replace('/app#beranda');
        } catch (e) {
          status('Gagal (' + (e.status || 'jaringan') + ')');
          if (e.code === 'USERNAME_TAKEN') setErr(user, UI.ERROR_TEXT.USERNAME_TAKEN);
          if (e.code === 'EMAIL_TAKEN') setErr(email, UI.ERROR_TEXT.EMAIL_TAKEN);
          await UI.showError('Gagal mendaftar', e);
        }
      });
    });
    email.focus();
  },
};
