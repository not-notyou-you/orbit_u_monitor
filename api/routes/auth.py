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
    LoginRequest,
    MeResponse,
    OkResponse,
    TokenCreateRequest,
    TokenCreateResponse,
    TokenItem,
    TokenListResponse,
)
from api.security import (
    SESSION_COOKIE,
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
# tetap memeriksa sendiri (INTERFACE.md §3.2).
PERMISSIONS: dict[str, str] = {
    "live.latest": "PUBLIC",
    "live.recent": "USER",
    "hydromet.today": "USER",
    "alerts.view": "USER",
    "account.manage": "USER",
    "alerts.acknowledge": "ANALYST",
    "analytics.view": "ANALYST",
    "disasters.manage": "ANALYST",
    "reports.hydromet": "ANALYST",
    "datasets.manage": "DATA_ENGINEER",
    "reports.datahealth": "DATA_ENGINEER",
    "admin.system": "ADMIN",
    "admin.accounts": "ADMIN",
}


def _me(principal: Principal) -> MeResponse:
    return MeResponse(
        user_id=principal.user_id, username=principal.username, full_name=principal.full_name,
        organization=principal.organization, role_code=principal.role_code, auth=principal.auth,
        permissions=[k for k, role in PERMISSIONS.items() if principal.has_role(role)],
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
