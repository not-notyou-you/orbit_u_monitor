# etl/mailer.py
"""Kirim email (peringatan dan konfirmasi, M64) dan cek alamat email.

Pustaka standar saja (smtplib + email.message); satu-satunya tambahan adalah
dnspython untuk membaca rekaman MX domain.

Konfigurasi dari .env (nama mengikuti konvensi fastapi-mail):
    MAIL_SERVER, MAIL_PORT, MAIL_USERNAME, MAIL_PASSWORD, MAIL_FROM,
    MAIL_STARTTLS (True/False), MAIL_SSL_TLS (True/False)
    MAIL_BACKEND   smtp (bawaan) | file -- `file` menulis .eml ke
                   LOGS_DIR/mail tanpa mengirim (pengembangan dan uji)
    MAIL_MAX_PER_RUN  batas email peringatan per putaran job (bawaan 200)
    MAIL_CHECK_DNS    false = lewati cek MX domain (pengembangan offline dan
                   tests/conftest.py; alamat uji @example.org memakai null MX)
    APP_BASE_URL   alamat aplikasi untuk tautan di email, mis.
                   https://orbit-u.example.org (kosong = tanpa tautan)

MAIL_PASSWORD tidak pernah ditulis ke log atau pesan galat.

Pengecekan email (check_deliverable) sengaja sederhana: format, lalu domain
punya server mail (MX; tanpa MX boleh rekaman A, RFC 5321 §5.1). Kotak surat
yang tidak ada di domain yang valid TIDAK bisa diketahui di sini -- server
pengirim seperti Gmail menerima dulu, lalu pantulannya masuk ke inbox
pengirim belakangan.
"""
from __future__ import annotations

import logging
import os
import re
import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr, format_datetime, make_msgid
from pathlib import Path

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SENDER_NAME = "Orbit-U: The Monitor"


class MailError(Exception):
    """code: EMAIL_INVALID | EMAIL_UNREACHABLE | MAIL_NOT_CONFIGURED | MAIL_SEND_FAILED."""

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _bool(v: str | None, default: bool) -> bool:
    if v is None or v == "":
        return default
    return v.strip().lower() in ("1", "true", "yes", "ya", "on")


@dataclass(frozen=True)
class MailConfig:
    server: str
    port: int
    username: str
    password: str
    sender: str
    starttls: bool
    ssl_tls: bool
    backend: str
    base_url: str
    max_per_run: int

    @classmethod
    def from_env(cls) -> "MailConfig":
        g = os.getenv
        return cls(
            server=(g("MAIL_SERVER") or "").strip(),
            port=int(g("MAIL_PORT") or 587),
            username=(g("MAIL_USERNAME") or "").strip(),
            password=g("MAIL_PASSWORD") or "",
            sender=(g("MAIL_FROM") or g("MAIL_USERNAME") or "").strip(),
            starttls=_bool(g("MAIL_STARTTLS"), True),
            ssl_tls=_bool(g("MAIL_SSL_TLS"), False),
            backend=(g("MAIL_BACKEND") or "smtp").strip().lower(),
            base_url=(g("APP_BASE_URL") or "").strip().rstrip("/"),
            max_per_run=int(g("MAIL_MAX_PER_RUN") or 200),
        )

    @property
    def configured(self) -> bool:
        if self.backend == "file":
            return True
        return bool(self.server and self.username and self.password and self.sender)

    def link(self, path: str) -> str | None:
        """Tautan absolut ke aplikasi, atau None bila APP_BASE_URL kosong."""
        return f"{self.base_url}{path}" if self.base_url else None


def outbox_dir() -> Path:
    return Path(os.getenv("LOGS_DIR", "logs")) / "mail"


# ------------------------------------------------------------------- pesan

def build_message(cfg: MailConfig, to: str, subject: str, text: str, html: str | None = None,
                  images: list[tuple[str, bytes]] | None = None) -> EmailMessage:
    """HTML + teks polos; `images` = [(cid, png)] ditempel inline dan dirujuk
    dari HTML sebagai src="cid:<cid>"."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((SENDER_NAME, cfg.sender or "orbit-u@localhost"))
    msg["To"] = to
    msg["Date"] = format_datetime(datetime.now(timezone.utc))
    domain = (cfg.sender.split("@", 1)[1] if "@" in cfg.sender else "localhost")
    msg["Message-ID"] = make_msgid(domain=domain)
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
        if images:
            part = msg.get_payload()[-1]
            for cid, data in images:
                part.add_related(data, maintype="image", subtype="png", cid=f"<{cid}>",
                                 filename=f"{cid}.png", disposition="inline")
    return msg


def send(cfg: MailConfig, msg: EmailMessage) -> str:
    """Kirim satu pesan. Mengembalikan keterangan (path .eml atau 'smtp').
    Melempar MailError; pesan galat tidak pernah memuat kata sandi."""
    if not cfg.configured:
        raise MailError("MAIL_NOT_CONFIGURED", "MAIL_SERVER/MAIL_USERNAME/MAIL_PASSWORD are not set")
    if cfg.backend == "file":
        out = outbox_dir()
        out.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", str(msg["To"]))
        path = out / f"{datetime.now():%Y%m%d_%H%M%S_%f}_{safe}.eml"
        path.write_bytes(msg.as_bytes())
        return str(path)
    try:
        if cfg.ssl_tls:
            smtp = smtplib.SMTP_SSL(cfg.server, cfg.port, timeout=20, context=ssl.create_default_context())
        else:
            smtp = smtplib.SMTP(cfg.server, cfg.port, timeout=20)
        with smtp:
            if cfg.starttls and not cfg.ssl_tls:
                smtp.starttls(context=ssl.create_default_context())
            smtp.login(cfg.username, cfg.password)
            refused = smtp.send_message(msg)
        if refused:
            raise MailError("EMAIL_UNREACHABLE", f"recipient refused: {', '.join(refused)}")
        return "smtp"
    except MailError:
        raise
    except smtplib.SMTPRecipientsRefused as exc:
        raise MailError("EMAIL_UNREACHABLE", f"recipient refused: {', '.join(exc.recipients)}")
    except smtplib.SMTPAuthenticationError:
        raise MailError("MAIL_SEND_FAILED", "SMTP login failed (check MAIL_USERNAME / app password)")
    except (smtplib.SMTPException, OSError) as exc:
        raise MailError("MAIL_SEND_FAILED", f"SMTP error: {exc.__class__.__name__}")


# ---------------------------------------------------------------- cek alamat

def normalize(email: str | None) -> str | None:
    e = (email or "").strip().lower()
    return e or None


def check_deliverable(email: str) -> None:
    """Format + domain yang bisa menerima email. Melempar MailError
    EMAIL_INVALID (format / domain tidak ada) atau EMAIL_UNREACHABLE."""
    if not EMAIL_RE.match(email or "") or len(email) > 254:
        raise MailError("EMAIL_INVALID", "not an email address")
    domain = email.rsplit("@", 1)[1].rstrip(".")
    if not _bool(os.getenv("MAIL_CHECK_DNS"), True):
        return
    try:
        import dns.exception
        import dns.resolver
    except ImportError:          # tanpa dnspython: hanya format yang dicek
        logger.warning("[MAIL] dnspython tidak terpasang; MX domain tidak dicek")
        return
    try:
        answers = dns.resolver.resolve(domain, "MX", lifetime=8)
        hosts = [str(r.exchange).rstrip(".") for r in answers]
        if hosts and all(h in ("", ".") for h in hosts):     # null MX (RFC 7505)
            raise MailError("EMAIL_UNREACHABLE", f"{domain} does not accept email")
        return
    except dns.resolver.NXDOMAIN:
        raise MailError("EMAIL_INVALID", f"domain {domain} does not exist")
    except dns.resolver.NoAnswer:
        pass
    except dns.exception.DNSException as exc:
        raise MailError("EMAIL_UNREACHABLE", f"DNS lookup for {domain} failed ({exc.__class__.__name__})")
    try:
        dns.resolver.resolve(domain, "A", lifetime=8)
    except dns.exception.DNSException:
        raise MailError("EMAIL_UNREACHABLE", f"{domain} has no mail server")


def verify_and_confirm(email: str, display_name: str, cfg: MailConfig | None = None) -> str:
    """Pengecekan lengkap sebelum email disimpan: alamat bisa menerima email
    DAN email konfirmasi berhasil dikirim. Mengembalikan alamat ternormalisasi."""
    from etl.notify_email import confirmation_message
    cfg = cfg or MailConfig.from_env()
    e = normalize(email)
    if e is None:
        raise MailError("EMAIL_INVALID", "empty")
    if not cfg.configured:
        raise MailError("MAIL_NOT_CONFIGURED", "email sending is not configured on this server")
    check_deliverable(e)
    subject, text, html = confirmation_message(display_name, e, cfg)
    send(cfg, build_message(cfg, e, subject, text, html))
    return e
