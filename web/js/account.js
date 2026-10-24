// js/account.js — Akun Saya: profil (/auth/me), email & peringatan (M64), ubah sandi,
// token API milik sendiri.
'use strict';
Pages['account'] = {
  async init(root, ctx) {
    const me = ctx.me;
    UI.$('#profile', root).innerHTML = [
      ['NAMA', me.full_name], ['PENGGUNA', me.username], ['ORGANISASI', me.organization], ['PERAN', UI.ROLE_LABEL[me.role_code] || me.role_code],
    ].map(([k, v]) => '<dt>' + k + '</dt><dd>' + UI.esc(v || UI.NA) + '</dd>').join('');

    const setErr = (id, msg) => {
      const i = UI.$('#' + id, root);
      i.setAttribute('aria-invalid', msg ? 'true' : 'false');
      UI.$('#' + id + 'Err', root).textContent = msg || '';
    };

    // ---- email & peringatan (M64)
    await initNotify(root, setErr);

    // ---- ubah sandi
    UI.$('#pwForm', root).addEventListener('submit', async ev => {
      ev.preventDefault();
      const o = UI.$('#oldPw', root).value, n = UI.$('#newPw', root).value, n2 = UI.$('#newPw2', root).value;
      setErr('oldPw', o ? '' : 'Wajib diisi.');
      setErr('newPw', n.length >= 10 ? (n === o ? 'Harus berbeda dari kata sandi lama.' : '') : 'Minimal 10 karakter.');
      setErr('newPw2', n2 === n ? '' : 'Tidak sama dengan kata sandi baru.');
      if (UI.$$('[aria-invalid=true]', UI.$('#pwForm', root)).length) return;
      await UI.busy(UI.$('#pwBtn', root), async () => {
        try {
          await API.post('/api/auth/change-password', { old_password: o, new_password: n });
          UI.$('#pwForm', root).reset();
          UI.info('Ubah kata sandi', 'Kata sandi berhasil diubah.');
        } catch (e) { UI.showError('Ubah kata sandi', e); }
      });
    });

    // ---- token
    const list = UI.$('#tokenList', root);
    async function loadTokens() {
      list.innerHTML = UI.loadingHTML();
      let r;
      try { r = await API.get('/api/auth/tokens?limit=100'); }
      catch (e) { list.innerHTML = UI.emptyHTML('GAGAL MEMUAT'); UI.showError('Token API', e); return; }
      UI.$('#tkCount', root).textContent = UI.int(r.total) + ' TOKEN';
      list.innerHTML = UI.tableHTML([
        { label: 'Nama', key: 'name' }, { label: 'Prefix', get: t => t.prefix + '…' },
        { label: 'Cakupan', key: 'scope' },
        { label: 'Kedaluwarsa', get: t => UI.date(t.expires_at) },
        { label: 'Terakhir dipakai', get: t => t.last_used_at ? UI.dateTime(t.last_used_at) : 'belum pernah' },
        { label: 'Status', html: true, get: t => t.active ? 'AKTIF' : '<span class="v-dim">' + (t.revoked_at ? 'DICABUT' : 'KEDALUWARSA') + '</span>' },
        { label: 'Aksi', html: true, get: t => t.active ? '<button type="button" class="small" data-revoke="' + t.token_id + '">Cabut</button>' : '' },
      ], r.items, { empty: 'BELUM ADA TOKEN', caption: 'Token API milik saya' });
      UI.$$('[data-revoke]', list).forEach(b => b.addEventListener('click', async () => {
        const t = r.items.find(x => String(x.token_id) === b.dataset.revoke);
        if (!await UI.confirm('Cabut token', 'Cabut token "' + t.name + '" (' + t.prefix + '…)? Skrip yang memakainya akan langsung ditolak.', 'Cabut')) return;
        await UI.busy(b, async () => {
          try { await API.del('/api/auth/tokens/' + t.token_id); loadTokens(); } catch (e) { UI.showError('Cabut token', e); }
        });
      }));
    }

    UI.$('#tokenForm', root).addEventListener('submit', async ev => {
      ev.preventDefault();
      const name = UI.$('#tkName', root).value.trim(), days = Number(UI.$('#tkDays', root).value);
      const daysOk = Number.isInteger(days) && days >= 1 && days <= 180;
      setErr('tkName', name ? '' : 'Wajib diisi.');
      setErr('tkDays', daysOk ? '' : 'Isi bilangan bulat 1–180.');
      if (!name || !daysOk) return;
      await UI.busy(UI.$('#tkBtn', root), async () => {
        let r;
        try { r = await API.post('/api/auth/tokens', { name, scope: UI.$('#tkScope', root).value, expires_in_days: days }); }
        catch (e) { UI.showError('Buat token', e); return; }
        UI.$('#tokenForm', root).reset();
        await UI.dialog({ title: 'Token API dibuat', kind: 'warn', wide: true,
          message: 'Salin token ini sekarang. Token utuh hanya ditampilkan SEKALI dan tidak dapat dilihat lagi.',
          body: '<div class="field"><label for="newTokenVal">Token (' + UI.esc(r.scope) + ', berlaku sampai ' + UI.esc(UI.date(r.expires_at)) + ')</label>' +
            '<input type="text" id="newTokenVal" readonly value="' + UI.esc(r.token) + '" style="font-family:var(--font-data)"></div>' +
            '<div class="btn-row" style="margin-bottom:8px"><button type="button" id="copyTok">Salin</button><span id="copyMsg" role="status"></span></div>',
          buttons: [{ label: 'Sudah saya simpan', value: true, default: true }],
          onOpen: win => {
            const inp = UI.$('#newTokenVal', win); inp.select();
            UI.$('#copyTok', win).addEventListener('click', async () => {
              try { await navigator.clipboard.writeText(r.token); } catch (e) { inp.select(); document.execCommand('copy'); }
              UI.$('#copyMsg', win).textContent = 'Tersalin ke clipboard.';
            });
          } });
        loadTokens();
      });
    });
    loadTokens();
  },
};

// Email dan kecamatan langganan peringatan (M64). Email disimpan server hanya
// setelah lolos pengecekan (format, belum dipakai, domain punya server mail,
// email konfirmasi terkirim); penolakan dijelaskan di bawah kolomnya.
async function initNotify(root, setErr) {
  const addr = UI.$('#mailAddr', root), state = UI.$('#mailState', root), del = UI.$('#mailDel', root);
  const list = UI.$('#regList', root), all = UI.$('#regAll', root), regState = UI.$('#regState', root);
  let prefs, regions = [];
  try {
    [prefs, regions] = await Promise.all([API.get('/api/auth/notify'),
      Maps.regions().then(g => g.features.map(f => f.properties)).catch(() => [])]);
  } catch (e) {
    UI.$('#mailBox', root).innerHTML = '<legend>Email &amp; peringatan</legend>' + UI.emptyHTML('PENGATURAN EMAIL TIDAK DAPAT DIMUAT');
    UI.$('#regBox', root).hidden = true;
    return;
  }
  regions.sort((a, b) => a.name.localeCompare(b.name, 'id'));

  function showMail(p) {
    prefs = p;
    addr.value = p.email || '';
    del.hidden = !p.email;
    state.textContent = p.email
      ? (p.email_verified_at ? 'Tersimpan dan terkonfirmasi sejak ' + UI.dateTime(p.email_verified_at) + '.'
        : 'Email lama belum dicek ulang — simpan sekali lagi agar peringatan dikirim ke alamat ini.')
      : 'Belum ada email. Anda tidak menerima peringatan, dan itu tidak masalah.';
    const off = UI.$('#mailOff', root);
    off.hidden = p.mail_configured;
    off.textContent = 'Pengiriman email belum diatur di server ini; email belum bisa disimpan. Hubungi Administrator.';
    summary();
  }
  function summary() {
    const n = prefs.all_regions ? regions.length : prefs.region_ids.length;
    const ok = prefs.email && prefs.email_verified_at;
    regState.textContent = !n ? 'Belum ada kecamatan dipilih — tidak ada peringatan.'
      : (prefs.all_regions ? 'Semua kecamatan' : n + ' kecamatan') + ' dipilih' +
        (ok ? '; peringatan dikirim ke ' + prefs.email + '.' : '; isi email di atas agar peringatan terkirim.');
  }
  function renderRegions() {
    all.checked = prefs.all_regions;
    list.innerHTML = regions.map(r => '<label class="check"><input type="checkbox" value="' + r.region_id + '"' +
      (prefs.all_regions || prefs.region_ids.includes(r.region_id) ? ' checked' : '') + (prefs.all_regions ? ' disabled' : '') +
      '> ' + UI.esc(r.name) + '</label>').join('') || UI.emptyHTML('AOI BELUM DIATUR');
  }
  showMail(prefs);
  renderRegions();
  all.addEventListener('change', () => UI.$$('input', list).forEach(i => { i.disabled = all.checked; if (all.checked) i.checked = true; }));

  UI.$('#mailForm', root).addEventListener('submit', async ev => {
    ev.preventDefault();
    const v = addr.value.trim();
    if (!v) { setErr('mailAddr', 'Isi alamat email, atau pakai "Hapus email".'); return; }
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v)) { setErr('mailAddr', 'Format email tidak valid.'); return; }
    setErr('mailAddr', '');
    state.textContent = 'Memeriksa alamat dan mengirim email konfirmasi…';
    await UI.busy(UI.$('#mailBtn', root), async () => {
      try {
        showMail(await API.put('/api/auth/email', { email: v }));
        UI.info('Email tersimpan', 'Email konfirmasi sudah dikirim ke ' + v + '. Bila tidak ada di kotak masuk, periksa folder spam.');
      } catch (e) {
        setErr('mailAddr', (UI.ERROR_TEXT[e.code] || UI.errorText(e)) + ' Email tidak disimpan.');
        showMail(prefs);
      }
    });
  });
  del.addEventListener('click', async () => {
    if (!await UI.confirm('Hapus email', 'Hapus ' + prefs.email + '? Anda tidak akan menerima peringatan lagi.', 'Hapus')) return;
    await UI.busy(del, async () => {
      try { showMail(await API.put('/api/auth/email', { email: null })); setErr('mailAddr', ''); }
      catch (e) { UI.showError('Hapus email', e); }
    });
  });
  UI.$('#regBtn', root).addEventListener('click', async () => {
    const ids = UI.$$('input:checked', list).map(i => +i.value);
    await UI.busy(UI.$('#regBtn', root), async () => {
      try {
        prefs = await API.put('/api/auth/notify', { all_regions: all.checked, region_ids: all.checked ? [] : ids });
        renderRegions(); summary();
      } catch (e) { UI.showError('Simpan pilihan kecamatan', e); }
    });
  });
}
