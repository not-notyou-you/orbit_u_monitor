# api/routes/auth.py
"""Autentikasi, sesi, dan token API pribadi (INTERFACE.md §4.1, §6; M20, M33)."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.activity import log_activity, request_meta
from api.deps import Principal, get_session, require_role
from api.errors import ApiError, error_response
from api.schemas import (
    ChangePasswordRequest,
    EmailUpdateRequest,
    LoginRequest,
    MeResponse,
    NotifyPrefsRequest,
    NotifyPrefsResponse,
    OkResponse,
    RegisterRequest,
    SessionInfoResponse,
    TokenCreateRequest,
    TokenCreateResponse,
    TokenItem,
    TokenListResponse,
)
from api.security import (
    SESSION_COOKIE,
    RateLimiter,
    SESSION_HOURS,
    burn_password_check,
    cookie_secure,
    create_session_jwt,
    generate_api_token,
    hash_password,
    password_policy_error,
    verify_password,
)

router = APIRouter()

# Kunci fitur untuk UI (menu per role). Bukan penegak akses: API dan DB
# tetap memeriksa sendiri (INTERFACE.md §3.2). Susunan halaman v2 (M56):
# Beranda, Citra, Kejadian (lihat), dan Tentang terbuka untuk pengunjung.
PERMISSIONS: dict[str, str] = {
    "home.view": "PUBLIC",
    "citra.view": "PUBLIC",
    "disasters.view": "PUBLIC",
    "about.view": "PUBLIC",
    "live.latest": "PUBLIC",
    "aoi3d.view": "USER",
    "live.recent": "USER",
    "hydromet.today": "USER",
    "alerts.view": "USER",
    "account.manage": "USER",
    "alerts.acknowledge": "ANALYST",
    "analytics.view": "ANALYST",
    "diagram.view": "ANALYST",
    "disasters.manage": "ANALYST",
    "reports.hydromet": "ANALYST",
    "logs.disasters": "ANALYST",
    "datasets.manage": "DATA_ENGINEER",
    "eda.view": "DATA_ENGINEER",
    "reports.datahealth": "DATA_ENGINEER",
    "logs.data": "DATA_ENGINEER",
    "admin.system": "ADMIN",
    "admin.accounts": "ADMIN",
    "logs.all": "ADMIN",
}

# Registrasi mandiri: 5 akun per alamat IP per jam (in-process, seperti
# token_rate_limiter). Cukup untuk menahan skrip pendaftaran massal tanpa
# CAPTCHA; organisasi pengguna < 100 akun.
register_rate_limiter = RateLimiter(limit=5, window_s=3600)
# Pengecekan email mengirim email konfirmasi ke alamat yang diketik; batasnya
# mencegah fitur ini dipakai mengirimi alamat orang lain berulang-ulang (M64).
email_rate_limiter = RateLimiter(limit=5, window_s=3600)

# Kode galat etl.mailer -> (HTTP, pesan).
_MAIL_HTTP = {
    "EMAIL_INVALID": (422, "Email address is not valid or its domain does not exist"),
    "EMAIL_UNREACHABLE": (422, "Email address cannot receive mail; it was not saved"),
    "MAIL_NOT_CONFIGURED": (503, "Email sending is not configured on this server"),
    "MAIL_SEND_FAILED": (503, "The confirmation email could not be sent; try again later"),
}


def _mail_error(exc) -> ApiError:
    status, detail = _MAIL_HTTP.get(exc.code, (503, "Email error"))
    return ApiError(status, detail, exc.code)


def verify_email(sess: Session, email: str | None, display_name: str) -> str | None:
    """Email ternormalisasi yang lolos pengecekan (format, belum dipakai akun
    lain, MX domain, email konfirmasi terkirim), atau None bila dikosongkan.
    Urutan ini sengaja: konfirmasi baru dikirim setelah semua yang bisa ditolak
    tanpa mengirim apa pun sudah lolos (M64)."""
    from etl.mailer import EMAIL_RE, MailError, normalize, verify_and_confirm
    e = normalize(email)
    if e is None:
        return None
    if not EMAIL_RE.match(e):
        raise ApiError(422, "Email address is not valid", "EMAIL_INVALID")
    if not sess.scalar(text("SELECT auth_email_available(:e)"), {"e": e}):
        raise ApiError(409, "Email is already registered", "EMAIL_TAKEN")
    try:
        return verify_and_confirm(e, display_name)
    except MailError as exc:
        raise _mail_error(exc)


def _permissions(principal: Principal) -> list[str]:
    return [k for k, role in PERMISSIONS.items() if principal.has_role(role)]


def _me(principal: Principal) -> MeResponse:
    return MeResponse(
        user_id=principal.user_id, username=principal.username, full_name=principal.full_name,
        organization=principal.organization, role_code=principal.role_code, auth=principal.auth,
        permissions=_permissions(principal),
    )


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE, token, max_age=SESSION_HOURS * 3600, path="/",
        httponly=True, secure=cookie_secure(), samesite="strict",
    )


@router.post("/login", summary="Sign in with username and password",
             dependencies=[Depends(require_role("PUBLIC"))],
             responses={401: {"description": "Wrong credentials"}, 423: {"description": "Account locked"}})
def login(req: LoginRequest, request: Request, sess: Session = Depends(get_session)):
    """Sets the `orbit_u_session` cookie (JWT HS256, 8 hours). Five consecutive
    failures lock the account for 15 minutes. Failures return a response
    instead of raising so the failure counter and log row are committed."""
    meta = request_meta(request)
    username = req.username.strip().lower()

    def failed(reason: str, user_id: int | None, status: int, detail: str, code: str) -> JSONResponse:
        log_activity(sess, "LOGIN_FAILED", user_id=user_id, username_attempted=username,
                     detail={"reason": reason}, **meta)
        return error_response(status, detail, code)

    row = sess.execute(text("SELECT * FROM auth_get_user(:u)"), {"u": username}).mappings().first()
    if row is None:
        burn_password_check(req.password)
        return failed("unknown_user", None, 401, "Invalid username or password", "INVALID_CREDENTIALS")

    now = datetime.now(timezone.utc)
    if row["locked_until"] is not None and row["locked_until"] > now:
        burn_password_check(req.password)
        return failed("locked", row["user_id"], 423,
                      "Account is temporarily locked after repeated failed sign-ins; try again later",
                      "ACCOUNT_LOCKED")

    if not verify_password(req.password, row["password_hash"]):
        state = sess.execute(text("SELECT * FROM auth_record_login(:u, false)"),
                             {"u": row["user_id"]}).mappings().one()
        if state["locked_until"] is not None and state["locked_until"] > now:
            return failed("bad_password_locked", row["user_id"], 423,
                          "Too many failed sign-ins; account locked for 15 minutes", "ACCOUNT_LOCKED")
        return failed("bad_password", row["user_id"], 401, "Invalid username or password",
                      "INVALID_CREDENTIALS")

    if not row["is_active"]:
        return failed("inactive", row["user_id"], 401, "Account is inactive", "ACCOUNT_INACTIVE")

    sess.execute(text("SELECT * FROM auth_record_login(:u, true)"), {"u": row["user_id"]})
    log_activity(sess, "LOGIN_SUCCESS", user_id=row["user_id"], **meta)
    token, _exp = create_session_jwt(row["user_id"], row["role_code"])
    principal = Principal(role_code=row["role_code"], user_id=row["user_id"], username=row["username"],
                          full_name=row["full_name"], auth="session")
    # organization tidak dikembalikan auth_get_user; /me memuatnya lengkap.
    response = JSONResponse(_me(principal).model_dump())
    _set_session_cookie(response, token)
    return response


@router.post("/register", status_code=201, summary="Create a USER account (self-registration)",
             dependencies=[Depends(require_role("PUBLIC"))],
             responses={409: {"description": "Username or email already registered"},
                        429: {"description": "Too many registrations from this address"}})
def register(req: RegisterRequest, request: Request, sess: Session = Depends(get_session)):
    """Visitors become `USER`; other roles are created by an ADMIN. The role
    is fixed inside the database function `auth_register_user`, so this
    endpoint cannot create anything else. On success the new account is
    signed in (sets `orbit_u_session`)."""
    meta = request_meta(request)
    if req.password != req.password_confirm:
        raise ApiError(400, "Password confirmation does not match", "PASSWORD_MISMATCH")
    problem = password_policy_error(req.password)
    if problem:
        raise ApiError(400, problem, "PASSWORD_POLICY")
    if not register_rate_limiter.allow(meta.get("ip") or "unknown"):
        raise ApiError(429, "Too many registrations from this address; try again later", "RATE_LIMITED",
                       headers={"Retry-After": "3600"})
    username = req.username.strip().lower()
    # Username diperiksa SEBELUM email dicek, karena pengecekan email
    # mengirim email konfirmasi -- jangan kirim untuk akun yang lalu ditolak.
    if sess.execute(text("SELECT 1 FROM auth_get_user(:u)"), {"u": username}).first():
        raise ApiError(409, f"Username {username} already exists", "USERNAME_TAKEN")
    email = verify_email(sess, req.email, username)
    try:
        with sess.begin_nested():
            user_id = sess.scalar(text("SELECT auth_register_user(:u, :e, :h)"),
                                  {"u": username, "e": email, "h": hash_password(req.password)})
    except IntegrityError as exc:
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", "") or ""
        if "email" in constraint:
            raise ApiError(409, "Email is already registered", "EMAIL_TAKEN")
        raise ApiError(409, f"Username {username} already exists", "USERNAME_TAKEN")
    log_activity(sess, "REGISTER", user_id=user_id, target_type="users", target_id=user_id,
                 detail={"email": email is not None}, **meta)
    token, _exp = create_session_jwt(user_id, "USER")
    principal = Principal(role_code="USER", user_id=user_id, username=username, full_name=username,
                          auth="session")
    response = JSONResponse(_me(principal).model_dump(), status_code=201)
    _set_session_cookie(response, token)
    return response


@router.get("/session", response_model=SessionInfoResponse,
            summary="Role and feature keys of the caller, also for visitors who are not signed in")
def session_info(principal: Principal = Depends(require_role("PUBLIC"))) -> SessionInfoResponse:
    """Unlike `/me` this never returns 401: a visitor gets role `PUBLIC` and
    the public feature keys, which the web UI uses to build its menu."""
    return SessionInfoResponse(authenticated=principal.is_authenticated, role_code=principal.role_code,
                               permissions=_permissions(principal),
                               user=_me(principal) if principal.is_authenticated else None)


@router.post("/logout", response_model=OkResponse, summary="Sign out (clears the session cookie)")
def logout(request: Request, response: Response, sess: Session = Depends(get_session),
           principal: Principal = Depends(require_role("USER"))) -> OkResponse:
    log_activity(sess, "LOGOUT", user_id=principal.user_id, **request_meta(request))
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, secure=cookie_secure(),
                           samesite="strict")
    return OkResponse(message="Signed out")


@router.get("/me", response_model=MeResponse, summary="Current user and permissions")
def me(principal: Principal = Depends(require_role("USER"))) -> MeResponse:
    return _me(principal)


@router.post("/change-password", response_model=OkResponse, summary="Change own password")
def change_password(req: ChangePasswordRequest, sess: Session = Depends(get_session),
                    principal: Principal = Depends(require_role("USER"))) -> OkResponse:
    row = sess.execute(text("SELECT password_hash FROM auth_get_user(:u)"),
                       {"u": principal.username}).mappings().first()
    if row is None or not verify_password(req.old_password, row["password_hash"]):
        raise ApiError(400, "Current password is incorrect", "INVALID_OLD_PASSWORD")
    problem = password_policy_error(req.new_password)
    if problem:
        raise ApiError(400, problem, "PASSWORD_POLICY")
    if req.new_password == req.old_password:
        raise ApiError(400, "New password must differ from the current password", "PASSWORD_POLICY")
    sess.execute(text("SELECT auth_change_own_password(:h)"), {"h": hash_password(req.new_password)})
    return OkResponse(message="Password changed")


# --- email dan peringatan (M64) -----------------------------------------------

def _notify_prefs(sess: Session) -> NotifyPrefsResponse:
    from etl.mailer import MailConfig
    row = sess.execute(text("SELECT * FROM auth_get_own_notify()")).mappings().first() or {}
    return NotifyPrefsResponse(email=row.get("email"), email_verified_at=row.get("email_verified_at"),
                               all_regions=bool(row.get("all_regions")), region_ids=list(row.get("region_ids") or []),
                               mail_configured=MailConfig.from_env().configured)


@router.get("/notify", response_model=NotifyPrefsResponse, summary="Own email and alert subscriptions")
def get_notify(sess: Session = Depends(get_session),
               principal: Principal = Depends(require_role("USER"))) -> NotifyPrefsResponse:
    return _notify_prefs(sess)


@router.put("/email", response_model=NotifyPrefsResponse, summary="Set or remove own email (checked first)",
            responses={422: {"description": "Email invalid or cannot receive mail; not saved"},
                       409: {"description": "Email used by another account"},
                       503: {"description": "Email sending not configured or failed"}})
def put_email(req: EmailUpdateRequest, request: Request, sess: Session = Depends(get_session),
              principal: Principal = Depends(require_role("USER"))) -> NotifyPrefsResponse:
    """The address is saved only after it passes the check: valid format, not
    used by another account, the domain has a mail server, and a confirmation
    email was sent successfully. `null` removes the email (no more alerts)."""
    meta = request_meta(request)
    if req.email is None or not req.email.strip():
        sess.execute(text("SELECT auth_set_own_email(NULL)"))
        log_activity(sess, "EMAIL_REMOVED", user_id=principal.user_id, target_type="users",
                     target_id=principal.user_id, **meta)
        return _notify_prefs(sess)
    if not email_rate_limiter.allow(principal.user_id):
        raise ApiError(429, "Too many email changes; try again in an hour", "RATE_LIMITED",
                       headers={"Retry-After": "3600"})
    try:
        email = verify_email(sess, req.email, principal.full_name or principal.username)
    except ApiError as exc:
        # Dikembalikan, bukan dilempar, supaya baris log penolakan ikut
        # ter-commit (pola yang sama dengan login gagal).
        log_activity(sess, "EMAIL_REJECTED", user_id=principal.user_id, target_type="users",
                     target_id=principal.user_id, detail={"code": exc.code}, **meta)
        return error_response(exc.status_code, exc.detail, exc.code, headers=exc.headers)
    try:
        with sess.begin_nested():
            sess.execute(text("SELECT auth_set_own_email(:e)"), {"e": email})
    except IntegrityError:
        raise ApiError(409, "Email is already registered", "EMAIL_TAKEN")
    log_activity(sess, "EMAIL_SET", user_id=principal.user_id, target_type="users",
                 target_id=principal.user_id, **meta)
    return _notify_prefs(sess)


@router.put("/notify", response_model=NotifyPrefsResponse, summary="Choose kecamatan for email alerts")
def put_notify(req: NotifyPrefsRequest, sess: Session = Depends(get_session),
               principal: Principal = Depends(require_role("USER"))) -> NotifyPrefsResponse:
    """`all_regions` covers every monitored kecamatan, including ones added
    later. Region ids that are not monitored kecamatan are ignored."""
    sess.execute(text("SELECT auth_set_own_notify(:a, CAST(:r AS int[]))"),
                 {"a": req.all_regions, "r": sorted(set(req.region_ids))})
    return _notify_prefs(sess)


# --- token API ----------------------------------------------------------------

_TOKEN_COLUMNS = """
    t.token_id, t.user_id, t.token_name AS name, t.token_prefix AS prefix, t.scopes AS scope,
    t.expires_at, t.last_used_at, t.revoked_at, t.created_at,
    (t.revoked_at IS NULL AND t.expires_at > now()) AS active
"""


def list_tokens(sess: Session, where: str, params: dict, limit: int, offset: int,
                with_owner: bool = False) -> TokenListResponse:
    join = "LEFT JOIN v_users_safe u ON u.user_id = t.user_id" if with_owner else ""
    owner = ", u.username" if with_owner else ""
    total = sess.scalar(text(f"SELECT count(*) FROM api_tokens t WHERE {where}"), params)
    rows = sess.execute(text(f"""
        SELECT {_TOKEN_COLUMNS}{owner} FROM api_tokens t {join}
        WHERE {where} ORDER BY t.created_at DESC LIMIT :limit OFFSET :offset"""),
        {**params, "limit": limit, "offset": offset}).mappings().all()
    return TokenListResponse(items=[TokenItem(**r) for r in rows], total=total, limit=limit, offset=offset)


@router.get("/tokens", response_model=TokenListResponse, summary="Own API tokens (token values are never returned)")
def my_tokens(sess: Session = Depends(get_session), principal: Principal = Depends(require_role("USER")),
              limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)) -> TokenListResponse:
    return list_tokens(sess, "t.user_id = :uid", {"uid": principal.user_id}, limit, offset)


@router.post("/tokens", status_code=201, response_model=TokenCreateResponse,
             summary="Create a personal API token (web session only)")
def create_token(req: TokenCreateRequest, sess: Session = Depends(get_session),
                 principal: Principal = Depends(require_role("USER"))) -> TokenCreateResponse:
    """The full `token` value is returned only in this response."""
    for _attempt in range(3):
        token, prefix, digest = generate_api_token()
        try:
            with sess.begin_nested():
                row = sess.execute(text("""
                    INSERT INTO api_tokens (user_id, token_name, token_prefix, token_hash, scopes, expires_at)
                    VALUES (:uid, :name, :prefix, :hash, :scope, now() + make_interval(days => :days))
                    RETURNING token_id, expires_at"""),
                    {"uid": principal.user_id, "name": req.name.strip(), "prefix": prefix,
                     "hash": digest, "scope": req.scope, "days": req.expires_in_days}).mappings().one()
        except IntegrityError:
            continue  # prefix bentrok (peluang sangat kecil): coba token lain
        return TokenCreateResponse(token_id=row["token_id"], token=token, prefix=prefix,
                                   scope=req.scope, expires_at=row["expires_at"])
    raise ApiError(409, "Could not allocate a unique token prefix; try again", "TOKEN_PREFIX_CONFLICT")


@router.delete("/tokens/{token_id}", response_model=OkResponse,
               summary="Revoke an API token (owner, or ADMIN for any token)")
def revoke_token(token_id: int, sess: Session = Depends(get_session),
                 principal: Principal = Depends(require_role("USER"))) -> OkResponse:
    # RLS tok_owner: non-admin hanya melihat/mengubah tokennya sendiri, jadi
    # token orang lain tampak tidak ada (404, tidak membocorkan keberadaan).
    row = sess.execute(text("SELECT revoked_at FROM api_tokens WHERE token_id = :t"),
                       {"t": token_id}).mappings().first()
    if row is None:
        raise ApiError(404, f"Token {token_id} not found", "NOT_FOUND")
    if row["revoked_at"] is not None:
        raise ApiError(409, "Token already revoked", "TOKEN_ALREADY_REVOKED")
    sess.execute(text("UPDATE api_tokens SET revoked_at = now() WHERE token_id = :t"), {"t": token_id})
    return OkResponse(message="Token revoked")
