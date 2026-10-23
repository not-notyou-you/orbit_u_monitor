# tests/test_notify.py
"""Peringatan email kondisi tidak normal (M64, INTERFACE.md §2, §4.1, §4.9).

* Email opsional; disimpan hanya bila lolos pengecekan (format, belum dipakai,
  domain bisa menerima email, email konfirmasi terkirim). Gagal = tidak disimpan.
* Kecamatan langganan: tidak ada, beberapa, atau semua.
* Notifikasi: data BARU yang tidak normal dikirim; data yang sama tidak dikirim
  dua kali; data lebih tua dari notify.max_age_days tidak dikirim; satu email
  per pengguna berisi semua kecamatannya.

tests/conftest.py memaksa MAIL_BACKEND=file (tidak ada email sungguhan) dan
MAIL_CHECK_DNS=false; cek MX diuji tersendiri dengan resolver tiruan.
"""

from __future__ import annotations

import email
import email.policy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

from etl import hydromet_aggregate as ha
from etl import mailer
from tests.conftest import create_test_user


def _today():
    return datetime.now(timezone.utc).date()


def _outbox() -> list[Path]:
    d = mailer.outbox_dir()
    return sorted(d.glob("*.eml")) if d.is_dir() else []


def _read(path: Path):
    return email.message_from_bytes(path.read_bytes(), policy=email.policy.default)


@pytest.fixture()
def person(db_client, test_password_hash):
    """Akun USER baru tanpa email dan tanpa langganan; dibersihkan sesudahnya."""
    name = f"ntf_{int(datetime.now().timestamp() * 1000) % 10_000_000}"
    uid = create_test_user(db_client, name, "USER", test_password_hash)
    yield uid
    with db_client.session() as s:
        s.execute(text("DELETE FROM notify_sent WHERE user_id = :u"), {"u": uid})
        s.execute(text("DELETE FROM user_notify_regions WHERE user_id = :u"), {"u": uid})
        s.execute(text("UPDATE users SET email = NULL, email_verified_at = NULL, notify_all_regions = false, "
                       "is_active = false WHERE user_id = :u"), {"u": uid})


@pytest.fixture(autouse=True)
def _fresh_limiter():
    from api.routes.auth import email_rate_limiter
    email_rate_limiter.reset()
    yield


class TestEmailCheck:
    def test_saved_only_after_confirmation_sent(self, make_client, person):
        c = make_client(user_id=person)
        before = len(_outbox())
        r = c.put("/api/auth/email", json={"email": f"  Warga{person}@Example.org "})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["email"] == f"warga{person}@example.org" and body["email_verified_at"]
        new = _outbox()[before:]
        assert len(new) == 1
        msg = _read(new[0])
        assert msg["To"] == f"warga{person}@example.org" and "tersimpan" in msg["Subject"]

    def test_unreachable_is_not_saved(self, make_client, person, monkeypatch):
        def boom(e):
            raise mailer.MailError("EMAIL_UNREACHABLE", "no mail server")
        monkeypatch.setattr(mailer, "check_deliverable", boom)
        c = make_client(user_id=person)
        r = c.put("/api/auth/email", json={"email": f"x{person}@tidak-ada.example"})
        assert (r.status_code, r.json()["code"]) == (422, "EMAIL_UNREACHABLE")
        assert c.get("/api/auth/notify").json()["email"] is None

    def test_invalid_format_and_not_configured(self, make_client, person, monkeypatch):
        c = make_client(user_id=person)
        r = c.put("/api/auth/email", json={"email": "bukan-email"})
        assert (r.status_code, r.json()["code"]) == (422, "EMAIL_INVALID")
        monkeypatch.setenv("MAIL_BACKEND", "smtp")
        monkeypatch.setenv("MAIL_USERNAME", "")
        r = c.put("/api/auth/email", json={"email": f"y{person}@example.org"})
        assert (r.status_code, r.json()["code"]) == (503, "MAIL_NOT_CONFIGURED")
        assert c.get("/api/auth/notify").json()["email"] is None

    def test_taken_by_someone_else_and_remove(self, make_client, person, db_client, test_password_hash):
        other = create_test_user(db_client, f"ntf_other_{person}", "USER", test_password_hash)
        assert make_client(user_id=other).put("/api/auth/email", json={"email": f"sama{person}@example.org"}).status_code == 200
        before = len(_outbox())
        r = make_client(user_id=person).put("/api/auth/email", json={"email": f"SAMA{person}@example.org"})
        assert (r.status_code, r.json()["code"]) == (409, "EMAIL_TAKEN")
        assert len(_outbox()) == before                    # konfirmasi tidak dikirim untuk email yang ditolak
        r = make_client(user_id=other).put("/api/auth/email", json={"email": None})
        assert r.status_code == 200 and r.json()["email"] is None and r.json()["email_verified_at"] is None

    def test_mx_lookup(self, monkeypatch):
        """Cek domain dengan resolver tiruan: NXDOMAIN = tidak valid, null MX = tidak bisa menerima."""
        import dns.resolver
        monkeypatch.setenv("MAIL_CHECK_DNS", "true")

        class Ans:
            def __init__(self, hosts):
                self.hosts = hosts

            def __iter__(self):
                return iter(type("R", (), {"exchange": h})() for h in self.hosts)

        def fake(domain, rtype, lifetime=None):
            if domain == "ada.example":
                return Ans(["mx.ada.example."])
            if domain == "nullmx.example" and rtype == "MX":
                return Ans(["."])
            raise dns.resolver.NXDOMAIN()
        monkeypatch.setattr(dns.resolver, "resolve", fake)
        mailer.check_deliverable("a@ada.example")
        with pytest.raises(mailer.MailError) as e:
            mailer.check_deliverable("a@tidakada.example")
        assert e.value.code == "EMAIL_INVALID"
        with pytest.raises(mailer.MailError) as e:
            mailer.check_deliverable("a@nullmx.example")
        assert e.value.code == "EMAIL_UNREACHABLE"


class TestSubscriptions:
    def test_none_some_all(self, make_client, person, synthetic_aoi):
        c = make_client(user_id=person)
        assert c.get("/api/auth/notify").json() == {"email": None, "email_verified_at": None, "all_regions": False,
                                                    "region_ids": [], "mail_configured": True}
        ids = [synthetic_aoi["TST001"], synthetic_aoi["TST002"], 99_999_999]
        body = c.put("/api/auth/notify", json={"all_regions": False, "region_ids": ids}).json()
        assert body["region_ids"] == sorted(ids[:2])          # bukan kecamatan AOI diabaikan
        body = c.put("/api/auth/notify", json={"all_regions": True, "region_ids": []}).json()
        assert body["all_regions"] is True and body["region_ids"] == []

    def test_register_without_email_and_with_bad_email(self, make_client, monkeypatch):
        from api.routes.auth import register_rate_limiter
        register_rate_limiter.reset()
        name = f"ntfreg_{int(datetime.now().timestamp() * 1000) % 10_000_000}"
        base = {"username": name, "password": "kata-sandi-uji-123", "password_confirm": "kata-sandi-uji-123"}
        def boom(e):
            raise mailer.MailError("EMAIL_UNREACHABLE", "no mail server")
        monkeypatch.setattr(mailer, "check_deliverable", boom)
        r = make_client(None).post("/api/auth/register", json={**base, "email": f"{name}@tidak.example"})
        assert (r.status_code, r.json()["code"]) == (422, "EMAIL_UNREACHABLE")
        r = make_client(None).post("/api/auth/register", json={**base, "email": None})
        assert r.status_code == 201, r.text


class TestNotifyRun:
    @pytest.fixture()
    def subscriber(self, make_client, person, synthetic_aoi):
        c = make_client(user_id=person)
        assert c.put("/api/auth/email", json={"email": f"pantau{person}@example.org"}).status_code == 200
        c.put("/api/auth/notify", json={"all_regions": False,
                                         "region_ids": [synthetic_aoi["TST001"], synthetic_aoi["TST002"]]})
        return person

    @staticmethod
    def _rain(db_client, d, values):
        with db_client.session() as s:
            for band, v in values.items():
                ha.upsert_observations(s, band, d, {rid: ha.ZonalResult(x, 1.0, 1) for rid, x in v.items()},
                                       run_type="L")

    def _run(self, etl_db_client, **kw):
        from etl import notify
        return notify.run(etl_db_client, source="test", cfg=mailer.MailConfig.from_env(), **kw)

    def _mine(self, person, before):
        return [p for p in _outbox()[before:] if _read(p)["To"] == f"pantau{person}@example.org"]

    def test_new_data_sent_once_then_again_for_newer_data(self, subscriber, etl_db_client, db_client, synthetic_aoi):
        t2, t1 = synthetic_aoi["TST002"], synthetic_aoi["TST001"]
        d0 = _today()
        # TST002: hujan sangat lebat; TST001: hujan 7 hari di atas ambang waspada.
        self._rain(db_client, d0, {"RAIN_24H": {t2: 120.0, t1: 5.0}, "RAIN_72H": {t2: 240.0, t1: 20.0},
                                   "RAIN_7D": {t2: 360.0, t1: 90.0}})
        before = len(_outbox())
        res = self._run(etl_db_client)
        assert res["status"] == "OK" and res["sent"] >= 1
        mine = self._mine(subscriber, before)
        assert len(mine) == 1                                    # satu email, dua kecamatan
        msg = _read(mine[0])
        assert "2 kecamatan tidak normal" in msg["Subject"]
        html = msg.get_body(("html",)).get_content()
        plain = msg.get_body(("plain",)).get_content()
        for part in ("Ringkasnya", "Bukti", "Detail teknis", "Kecamatan 1", "Kecamatan 2"):
            assert part in html, part
        assert "bukan peringatan dini resmi" in plain.lower() and "GPM IMERG" in plain
        with db_client.session() as s:
            keys = set(s.execute(text("SELECT region_id, item_key FROM notify_sent WHERE user_id = :u AND data_date = :d"),
                                 {"u": subscriber, "d": d0}).all())
        assert (t2, "gpm_rain_24h") in keys and (t1, "gpm_rain_7d") in keys

        # Data yang sama: tidak dikirim lagi.
        before = len(_outbox())
        self._run(etl_db_client)
        assert self._mine(subscriber, before) == []

        # Data BARU (besok) dengan kondisi yang sama: dikirim lagi.
        d1 = d0 + timedelta(days=1)
        self._rain(db_client, d1, {"RAIN_24H": {t2: 110.0}, "RAIN_72H": {t2: 250.0}, "RAIN_7D": {t2: 370.0}})
        before = len(_outbox())
        self._run(etl_db_client, today=d1)
        mine = self._mine(subscriber, before)
        assert len(mine) == 1 and "Kecamatan 2" in _read(mine[0])["Subject"]
        with db_client.session() as s:     # jangan tinggalkan data "hari ini/besok" untuk modul lain
            s.execute(text("DELETE FROM region_observations WHERE obs_date IN (:a, :b) AND region_id IN (:t1, :t2)"),
                      {"a": d0, "b": d1, "t1": t1, "t2": t2})
            s.execute(text("DELETE FROM alert_events WHERE observation_date IN (:a, :b)"), {"a": d0, "b": d1})

    def test_old_data_does_not_trigger(self, subscriber, etl_db_client, db_client, synthetic_aoi):
        """Dijalankan seolah 60 hari kemudian: semua data lebih tua dari
        notify.max_age_days (7), jadi tidak ada yang dikirim."""
        before = len(_outbox())
        self._run(etl_db_client, today=_today() + timedelta(days=60))
        assert self._mine(subscriber, before) == []

    def test_no_email_or_no_region_means_no_alert(self, make_client, person, etl_db_client, synthetic_aoi):
        c = make_client(user_id=person)
        c.put("/api/auth/notify", json={"all_regions": True, "region_ids": []})   # tanpa email
        with etl_db_client.session() as s:
            ids = [r[0] for r in s.execute(text("SELECT user_id FROM notify_recipients()")).all()]
        assert person not in ids
        c.put("/api/auth/email", json={"email": f"tanpa{person}@example.org"})
        c.put("/api/auth/notify", json={"all_regions": False, "region_ids": []})   # tanpa kecamatan
        with etl_db_client.session() as s:
            ids = [r[0] for r in s.execute(text("SELECT user_id FROM notify_recipients()")).all()]
        assert person not in ids

    def test_disabled_setting(self, etl_db_client, db_client):
        with db_client.session() as s:
            s.execute(text("UPDATE app_settings SET setting_value = 'false' WHERE setting_key = 'notify.enabled'"))
        try:
            assert self._run(etl_db_client)["status"] == "DISABLED"
        finally:
            with db_client.session() as s:
                s.execute(text("UPDATE app_settings SET setting_value = 'true' WHERE setting_key = 'notify.enabled'"))


def test_inline_images_and_layers():
    """Gambar bukti ditempel inline (CID) dan dirujuk dari HTML."""
    from etl.notify_email import alert_message
    cfg = mailer.MailConfig.from_env()
    d = _today()
    block = {"region": {"region_id": 1, "name": "Uji"}, "status": {"label": "Waspada", "level": 1, "text": "Waspada — x"},
             "items": [{"key": "gpm_rain_7d", "what": "curah hujan 7 hari", "because": "rata-rata 90 mm", "level": 1,
                        "band": "RAIN_7D", "date": d}],
             "latest": {"RAIN_7D": {"value": 90.0, "obs_date": d, "valid_fraction": 1.0, "run_type": "L"}},
             "prev": {"RAIN_7D": {"value": 40.0}}, "ranges": {"RAIN_7D": {"p02": 0.0, "p98": 120.0}},
             "scene_date": d, "images": [("r1_gpm_rain_7d", "gpm_rain_7d", "GPM 7 hari", b"\x89PNG\r\n\x1a\nuji")]}
    subject, text_, html, images = alert_message("Warga", [block], cfg, {"RAIN_7D": "mm"},
                                                 lambda b: [{"label": "waspada", "value": 75.0}])
    assert "Waspada di Uji" in subject and "cid:r1_gpm_rain_7d" in html
    msg = mailer.build_message(cfg, "a@example.org", subject, text_, html, images)
    related = [p for p in msg.walk() if p.get_content_type() == "image/png"]
    # Bukti citra + logo di pita judul (cid:orbitu-logo, dilampirkan mailer.build_message).
    assert sorted(p["Content-ID"] for p in related) == ["<orbitu-logo>", "<r1_gpm_rain_7d>"]
    assert "cid:orbitu-logo" in html
    assert "90 mm" in text_ and "waspada 75 mm" in text_ and "0 s.d. 120 mm" in text_


class TestSmtpBackend:
    """Jalur SMTP sungguhan dengan smtplib tiruan: STARTTLS → login → kirim,
    dan pemetaan galat (sandi aplikasi salah, penerima ditolak)."""

    @staticmethod
    def _cfg():
        from dataclasses import replace
        return replace(mailer.MailConfig.from_env(), backend="smtp", server="smtp.contoh.id", port=587,
                       username="orbit-u@contoh.id", password="rahasia-16-huruf", sender="orbit-u@contoh.id",
                       starttls=True, ssl_tls=False)

    def _fake(self, monkeypatch, *, login_error=None, refused=None):
        import smtplib
        calls = []

        class FakeSMTP:
            def __init__(self, host, port, timeout=None):
                calls.append(("connect", host, port))

            def __enter__(self):
                return self

            def __exit__(self, *a):
                calls.append(("quit",))

            def starttls(self, context=None):
                calls.append(("starttls",))

            def login(self, user, pw):
                calls.append(("login", user))
                if login_error:
                    raise login_error

            def send_message(self, msg):
                calls.append(("send", msg["To"]))
                if refused:
                    raise smtplib.SMTPRecipientsRefused({msg["To"]: (550, b"no such user")})
                return {}
        monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
        return calls

    def test_starttls_login_send(self, monkeypatch):
        calls = self._fake(monkeypatch)
        cfg = self._cfg()
        assert mailer.send(cfg, mailer.build_message(cfg, "a@contoh.id", "s", "t")) == "smtp"
        assert [c[0] for c in calls] == ["connect", "starttls", "login", "send", "quit"]

    def test_wrong_app_password_and_refused_recipient(self, monkeypatch):
        import smtplib
        self._fake(monkeypatch, login_error=smtplib.SMTPAuthenticationError(535, b"bad"))
        cfg = self._cfg()
        with pytest.raises(mailer.MailError) as e:
            mailer.send(cfg, mailer.build_message(cfg, "a@contoh.id", "s", "t"))
        assert e.value.code == "MAIL_SEND_FAILED" and "rahasia" not in e.value.detail
        self._fake(monkeypatch, refused=True)
        with pytest.raises(mailer.MailError) as e:
            mailer.send(cfg, mailer.build_message(cfg, "a@contoh.id", "s", "t"))
        assert e.value.code == "EMAIL_UNREACHABLE"
