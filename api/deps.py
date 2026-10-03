# api/deps.py
"""Dependency bersama: koneksi DB per request, autentikasi, dan role.

Tiga lapis penegakan (INTERFACE.md §3.2):
  1. UI menyembunyikan menu.
  2. ``require_role(...)`` di setiap route -> 401 / 403.
  3. Setiap request berjalan dalam SATU transaksi yang diawali
     ``SET LOCAL ROLE monitor_<role>`` + ``set_config('app.user_id', ...)``
     (DATABASE.md §8.2), sehingga GRANT/RLS PostgreSQL tetap menolak kueri
     yang lolos lapis 2 karena bug.

Koneksi:
  * ``monitor_app`` (NOINHERIT) untuk request API: tanpa SET ROLE ia tidak
    punya hak apa pun. Nama role hanya diambil dari ``ROLE_TO_DB``.
  * ``monitor_etl`` untuk kerja latar (thread job dataset, siklus Live,
    penghapusan fisik, scheduler) lewat ``get_etl_db``.
Aplikasi tidak pernah terkoneksi sebagai superuser.

Modul ini terpisah dari ``api/main.py`` karena ``api.main`` meng-import setiap
route; satu callable bersama di sini juga membuat
``app.dependency_overrides`` berlaku untuk semua route.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable, Generator

from fastapi import Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.errors import ApiError
from api.security import (
    SESSION_COOKIE,
    api_token_matches,
    decode_session_jwt,
    token_rate_limiter,
)
from etl.database_client import DatabaseClient

logger = logging.getLogger(__name__)

# Whitelist: satu-satunya sumber nama role untuk SET LOCAL ROLE.
ROLE_TO_DB: dict[str, str] = {
    "PUBLIC": "monitor_public",
    "USER": "monitor_user",
    "ANALYST": "monitor_analyst",
    "DATA_ENGINEER": "monitor_data_engineer",
    "ADMIN": "monitor_admin",
}

# Hierarki: ADMIN ⊃ ANALYST ⊃ USER ⊃ PUBLIC, ADMIN ⊃ DATA_ENGINEER ⊃ USER.
ROLE_INCLUDES: dict[str, frozenset[str]] = {
    "PUBLIC": frozenset({"PUBLIC"}),
    "USER": frozenset({"USER", "PUBLIC"}),
    "ANALYST": frozenset({"ANALYST", "USER", "PUBLIC"}),
    "DATA_ENGINEER": frozenset({"DATA_ENGINEER", "USER", "PUBLIC"}),
    "ADMIN": frozenset(ROLE_TO_DB),
}

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
CSRF_HEADER = "X-Requested-With"
CSRF_VALUE = "orbit-u"

# Lapis 2 bisa dimatikan HANYA oleh tes robustness (INTERFACE.md §3.2): role
# DB tetap diset, sehingga penolakan harus datang dari PostgreSQL.
ROLE_CHECKS_ENABLED = True


# --- klien basis data ---------------------------------------------------------

_app_client: DatabaseClient | None = None
_etl_client: DatabaseClient | None = None


def set_clients(app_client: DatabaseClient | None, etl_client: DatabaseClient | None) -> None:
    """Dipasang oleh lifespan ``api.main`` (dan fixture tes)."""
    global _app_client, _etl_client
    _app_client, _etl_client = app_client, etl_client


def get_app_client() -> DatabaseClient:
    if _app_client is None:
        raise RuntimeError("Application DatabaseClient not initialized. App startup failed.")
    return _app_client


def get_etl_db() -> DatabaseClient:
    """Dependency: klien monitor_etl untuk kerja latar yang dipicu request."""
    if _etl_client is None:
        raise RuntimeError("ETL DatabaseClient not initialized. App startup failed.")
    return _etl_client


class RequestDatabaseClient(DatabaseClient):
    """DatabaseClient yang seluruh ``session()``-nya memakai sesi request.

    Manager warisan (DatasetManager, MetadataManager, ...) memanggil
    ``db.session()`` berkali-kali. Di sini setiap blok menjadi SAVEPOINT di
    dalam satu transaksi request, sehingga SET LOCAL ROLE berlaku untuk
    semuanya dan exception yang ditangkap manager tetap hanya membatalkan
    bloknya sendiri. Commit terjadi sekali di akhir request.
    """

    def __init__(self, base: DatabaseClient, sess: Session, after_commit: list[Callable[[], None]]) -> None:
        # Sengaja tidak memanggil super().__init__: engine dipakai bersama.
        self._database_url = base._database_url
        self._engine = base._engine
        self._SessionFactory = base._SessionFactory
        self._request_session = sess
        self._after_commit = after_commit

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        nested = self._request_session.begin_nested()
        try:
            yield self._request_session
        except BaseException:
            if nested.is_active:
                nested.rollback()
            raise
        else:
            if nested.is_active:
                nested.commit()

    def call_after_commit(self, fn: Callable[[], None]) -> None:
        """Jalankan ``fn`` setelah transaksi request di-commit (mis. memulai
        thread yang harus melihat baris yang baru dibuat request ini).
        Dibuang bila request gagal."""
        self._after_commit.append(fn)

    def dispose(self) -> None:  # engine milik klien dasar
        pass


# --- prinsipal ----------------------------------------------------------------

@dataclass(frozen=True)
class Principal:
    role_code: str = "PUBLIC"
    user_id: int | None = None
    username: str | None = None
    full_name: str | None = None
    organization: str | None = None
    auth: str | None = None            # "session" | "token" | None
    token_id: int | None = None
    token_scope: str | None = None

    @property
    def is_authenticated(self) -> bool:
        return self.user_id is not None

    def has_role(self, min_role: str) -> bool:
        return min_role in ROLE_INCLUDES.get(self.role_code, frozenset())


ANONYMOUS = Principal()


def _apply_db_role(sess: Session, role_code: str, user_id: int | None) -> None:
    db_role = ROLE_TO_DB[role_code]  # KeyError = bukan whitelist -> 500, bukan injeksi
    sess.execute(text("SET LOCAL ROLE " + db_role))
    sess.execute(text("SELECT set_config('app.user_id', :uid, true)"),
                 {"uid": "" if user_id is None else str(user_id)})


def request_session(request: Request) -> Generator[Session, None, None]:
    """Satu transaksi per request (monitor_app). Commit di akhir, rollback
    bila route melempar exception; callback after-commit dijalankan
    setelahnya."""
    sess = get_app_client()._SessionFactory()
    after_commit: list[Callable[[], None]] = []
    request.state.after_commit = after_commit
    committed = False
    try:
        _apply_db_role(sess, "PUBLIC", None)
        yield sess
        sess.commit()
        committed = True
    except BaseException:
        sess.rollback()
        raise
    finally:
        sess.close()
        if committed:
            for fn in after_commit:
                try:
                    fn()
                except Exception:
                    logger.exception("after-commit callback failed on %s", request.url.path)


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _load_user(sess: Session, user_id: int):
    return sess.execute(text("SELECT * FROM auth_session_user(:u)"), {"u": user_id}).mappings().first()


def _authenticate_bearer(request: Request, sess: Session, token: str) -> Principal:
    if not token.startswith("trn_") or len(token) < 12:
        raise ApiError(401, "Invalid API token", "TOKEN_INVALID")
    row = sess.execute(text("SELECT * FROM auth_get_token(:p)"), {"p": token[:8]}).mappings().first()
    if row is None or not api_token_matches(token, row["token_hash"]):
        raise ApiError(401, "Invalid API token", "TOKEN_INVALID")
    if row["revoked_at"] is not None:
        raise ApiError(401, "API token has been revoked", "TOKEN_REVOKED")
    expired = sess.scalar(text("SELECT :e <= now()"), {"e": row["expires_at"]})
    if expired:
        raise ApiError(401, "API token has expired", "TOKEN_EXPIRED")
    user = _load_user(sess, row["user_id"])
    if user is None or not user["is_active"]:
        raise ApiError(401, "API token owner is inactive", "ACCOUNT_INACTIVE")
    if not token_rate_limiter.allow(row["token_id"]):
        raise ApiError(429, "Rate limit exceeded (120 requests per minute per token)", "RATE_LIMITED",
                       headers={"Retry-After": "60"})
    return Principal(role_code=user["role_code"], user_id=user["user_id"], username=user["username"],
                     full_name=user["full_name"], organization=user["organization"],
                     auth="token", token_id=row["token_id"], token_scope=row["scopes"])


def _authenticate_cookie(request: Request, sess: Session, cookie: str) -> Principal:
    user_id = decode_session_jwt(cookie)
    if user_id is None:
        request.state.auth_error = ("Session expired or invalid; please sign in again", "SESSION_EXPIRED")
        return ANONYMOUS
    user = _load_user(sess, user_id)
    if user is None or not user["is_active"]:
        request.state.auth_error = ("Account is inactive", "ACCOUNT_INACTIVE")
        return ANONYMOUS
    return Principal(role_code=user["role_code"], user_id=user["user_id"], username=user["username"],
                     full_name=user["full_name"], organization=user["organization"], auth="session")


def current_principal(request: Request, sess: Session = Depends(request_session)) -> Principal:
    """Siapa pemanggilnya, lalu SET LOCAL ROLE ke role-nya.

    Role dan is_active dibaca ulang setiap request (INTERFACE.md §6), jadi
    perubahan role/nonaktif berlaku di request berikutnya.
    """
    cached = getattr(request.state, "principal", None)
    if cached is not None:
        return cached

    authz = request.headers.get("authorization", "")
    if authz[:7].lower() == "bearer ":
        principal = _authenticate_bearer(request, sess, authz[7:].strip())
        if request.method not in SAFE_METHODS:
            raise ApiError(403, "API tokens cannot perform write actions; use a web session",
                           "TOKEN_WRITE_FORBIDDEN")
    else:
        # Lapis CSRF tambahan di atas SameSite=Strict (INTERFACE.md §6).
        if request.method not in SAFE_METHODS and request.headers.get(CSRF_HEADER) != CSRF_VALUE:
            raise ApiError(403, f"Missing {CSRF_HEADER}: {CSRF_VALUE} header", "CSRF_HEADER_REQUIRED")
        cookie = request.cookies.get(SESSION_COOKIE)
        principal = _authenticate_cookie(request, sess, cookie) if cookie else ANONYMOUS

    _apply_db_role(sess, principal.role_code, principal.user_id)
    if principal.auth == "token":
        # Di bawah role pemilik: RLS api_tokens mengizinkan baris miliknya.
        sess.execute(text("UPDATE api_tokens SET last_used_at = now() WHERE token_id = :t"),
                     {"t": principal.token_id})
    request.state.principal = principal
    request.state.client_ip = _client_ip(request)
    return principal


def require_role(min_role: str, *, download: bool = False):
    """Dependency role minimum (hierarki ROLE_INCLUDES).

    ``download=True`` menandai endpoint unduhan: token API ber-scope READ
    ditolak (butuh READ_DOWNLOAD).
    """
    if min_role not in ROLE_TO_DB:
        raise ValueError(f"unknown role {min_role!r}")

    def _check(request: Request, principal: Principal = Depends(current_principal)) -> Principal:
        if min_role != "PUBLIC" and not principal.is_authenticated:
            detail, code = getattr(request.state, "auth_error", ("Authentication required", "NOT_AUTHENTICATED"))
            raise ApiError(401, detail, code)
        if ROLE_CHECKS_ENABLED and not principal.has_role(min_role):
            raise ApiError(403, f"This action requires role {min_role}", "ROLE_FORBIDDEN")
        if download and principal.auth == "token" and principal.token_scope != "READ_DOWNLOAD":
            raise ApiError(403, "API token scope READ does not allow downloads", "TOKEN_SCOPE_FORBIDDEN")
        return principal

    _check.min_role = min_role          # dibaca tes RBAC dan OpenAPI (x-min-role)
    _check.download = download
    _check.__name__ = f"require_role_{min_role.lower()}{'_download' if download else ''}"
    return _check


def get_db(request: Request, sess: Session = Depends(request_session),
           principal: Principal = Depends(current_principal)) -> DatabaseClient:
    """Dependency: DatabaseClient yang berjalan di transaksi request dengan
    role pemanggil sudah diset."""
    return RequestDatabaseClient(get_app_client(), sess, request.state.after_commit)


def get_session(sess: Session = Depends(request_session),
                principal: Principal = Depends(current_principal)) -> Session:
    """Dependency: sesi SQLAlchemy request (role pemanggil sudah diset)."""
    return sess


def mark_download(request: Request, action: str, target_type: str, target_id: int | None,
                  **detail) -> None:
    """Tandai respons ini sebagai unduhan; api.activity mencatatnya ke
    user_activity_logs dengan bytes_sent setelah body selesai dikirim."""
    request.state.download = {"action": action, "target_type": target_type,
                              "target_id": target_id, "detail": detail}
