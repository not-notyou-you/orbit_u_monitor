# api/activity.py
"""Pencatatan user_activity_logs (DATABASE.md §4.2.5).

Dua jalur:
  * ``log_activity(sess, ...)`` di dalam transaksi request (login, logout,
    aksi admin): ikut commit/rollback bersama request.
  * ``ActivityLogMiddleware``: setelah respons SELESAI dikirim, mencatat
    unduhan (dengan ``bytes_sent`` yang benar-benar terkirim) dan setiap
    request bertoken API (``detail.auth = 'token'``). Transaksi request
    sudah ditutup saat itu (exit dependency berjalan sebelum body dikirim),
    jadi baris ditulis lewat transaksi pendek sendiri dengan SET LOCAL ROLE
    pemilik request.
"""

from __future__ import annotations

import ipaddress
import json
import logging

from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

logger = logging.getLogger(__name__)

_INSERT = text("""
    INSERT INTO user_activity_logs
        (user_id, username_attempted, action, target_type, target_id,
         bytes_sent, ip_address, user_agent, detail)
    VALUES (:user_id, :username_attempted, :action, :target_type, :target_id,
            :bytes_sent, CAST(:ip AS inet), :user_agent, CAST(:detail AS jsonb))
""")


def _valid_ip(ip: str | None) -> str | None:
    """Kolom ip_address bertipe INET; host non-IP (mis. "testclient") -> NULL."""
    if not ip:
        return None
    try:
        return str(ipaddress.ip_address(ip))
    except ValueError:
        return None


def log_activity(sess: Session, action: str, *, user_id: int | None = None,
                 username_attempted: str | None = None, target_type: str | None = None,
                 target_id: int | None = None, bytes_sent: int | None = None,
                 ip: str | None = None, user_agent: str | None = None,
                 detail: dict | None = None) -> None:
    sess.execute(_INSERT, {
        "user_id": user_id,
        "username_attempted": username_attempted[:50] if username_attempted else None,
        "action": action,
        "target_type": target_type,
        "target_id": target_id,
        "bytes_sent": bytes_sent,
        "ip": _valid_ip(ip),
        "user_agent": (user_agent or "")[:255] or None,
        "detail": json.dumps(detail, default=str) if detail else None,
    })


def request_meta(request) -> dict:
    return {"ip": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent")}


def _log_standalone(principal, action: str, **fields) -> None:
    from api.deps import _apply_db_role, get_app_client

    sess = get_app_client()._SessionFactory()
    try:
        _apply_db_role(sess, principal.role_code, principal.user_id)
        log_activity(sess, action, user_id=principal.user_id, **fields)
        sess.commit()
    except Exception:
        sess.rollback()
        logger.exception("failed to write user_activity_logs (%s)", action)
    finally:
        sess.close()


class ActivityLogMiddleware:
    """ASGI murni: menghitung byte body yang terkirim tanpa menyangga respons."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        sent = {"status": None, "bytes": 0, "complete": False}

        async def counting_send(message):
            if message["type"] == "http.response.start":
                sent["status"] = message["status"]
            elif message["type"] == "http.response.body":
                sent["bytes"] += len(message.get("body", b""))
                if not message.get("more_body", False):
                    sent["complete"] = True
            await send(message)

        try:
            await self.app(scope, receive, counting_send)
        finally:
            await self._record(scope, sent)

    async def _record(self, scope, sent) -> None:
        state = scope.get("state") or {}
        principal = state.get("principal")
        if principal is None:
            return
        headers = {k.decode("latin-1"): v.decode("latin-1") for k, v in scope.get("headers", [])}
        meta = {"ip": (scope.get("client") or (None,))[0], "user_agent": headers.get("user-agent")}
        auth = {"auth": principal.auth} if principal.auth else {}
        if principal.token_id is not None:
            auth["token_id"] = principal.token_id

        download = state.get("download")
        status = sent["status"]
        try:
            if download and status is not None and 200 <= status < 300:
                detail = {**download.get("detail", {}), **auth, "status": status,
                          "complete": sent["complete"]}
                await run_in_threadpool(
                    _log_standalone, principal, download["action"],
                    target_type=download["target_type"], target_id=download["target_id"],
                    bytes_sent=sent["bytes"], detail=detail, **meta)
            elif principal.auth == "token":
                # INTERFACE §4.2.8: setiap pemakaian token tercatat (S6).
                detail = {**auth, "method": scope.get("method"), "path": scope.get("path"),
                          "status": status}
                await run_in_threadpool(_log_standalone, principal, "API_REQUEST",
                                        detail=detail, **meta)
        except Exception:
            logger.exception("activity logging failed for %s", scope.get("path"))
