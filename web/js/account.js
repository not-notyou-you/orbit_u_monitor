// js/account.js — Akun Saya: profil (/auth/me), ubah sandi, token API milik sendiri.
'use strict';
Pages['account'] = {
  async init(root, ctx) {
    const me = ctx.me;
    UI.$('#profile', root).innerHTML = [
      ['NAMA', me.full_name], ['PENGGUNA', me.username], ['ORGANISASI', me.organization], ['PERAN', UI.ROLE_LABEL[me.role_code] || me.role_code],
    ].map(([k, v]) => '<dt>' + k + '</dt><dd>' + UI.esc(v || UI.NA) + '</dd>').join('');

    const origin = location.origin;
    UI.$('#curlEx', root).textContent =
      'curl -H "Authorization: Bearer $ORBIT_U_TOKEN" \\\n  "' + origin + '/api/hydromet/observations?band=RAIN_24H&limit=50"';
    UI.$('#pyEx', root).textContent =
      'import os, requests\nH = {"Authorization": "Bearer " + os.environ["ORBIT_U_TOKEN"]}\n' +
      'r = requests.get("' + origin + '/api/hydromet/today", headers=H, timeout=30)\nr.raise_for_status()\n' +
      'for k in r.json()["regions"]:\n    print(k["name"], k["rain_24h_mm"])';

    const setErr = (id, msg) => {
      const i = UI.$('#' + id, root);
      i.setAttribute('aria-invalid', msg ? 'true' : 'false');
      UI.$('#' + id + 'Err', root).textContent = msg || '';
    };

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
