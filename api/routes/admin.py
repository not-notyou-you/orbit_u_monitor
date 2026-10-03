# api/routes/admin.py
"""Administrasi akun dan log (INTERFACE.md §4.9, bagian akun & log).

Seluruh router dijaga require_role("ADMIN") di api/main.py dan berjalan
sebagai monitor_admin; perubahan users tercatat audit trigger dengan
app.user_id admin.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.deps import Principal, current_principal, get_session
from api.errors import ApiError
from api.routes.auth import list_tokens
from api.schemas import (
    AdminResetPasswordRequest,
    AdminUserCreateRequest,
    AdminUserItem,
    AdminUserListResponse,
    AdminUserUpdateRequest,
    LogListResponse,
    OkResponse,
    TokenListResponse,
)
from api.security import hash_password, password_policy_error

router = APIRouter()

_USER_SELECT = """
    SELECT u.user_id, u.username, u.full_name, u.organization, r.role_code, u.is_active,
           (u.locked_until IS NOT NULL AND u.locked_until > now()) AS is_locked,
           u.locked_until, u.last_login_at, u.created_by, u.created_at, u.updated_at
    FROM users u JOIN roles r ON r.role_id = u.role_id
"""


def _page(page: int | None, limit: int, offset: int) -> int:
    return (page - 1) * limit if page else offset


def _check_dates(date_from: date | None, date_to: date | None) -> None:
    if date_from and date_to and date_from > date_to:
        raise ApiError(400, "date_from must not be after date_to", "INVALID_DATE_RANGE")


def _get_user(sess: Session, user_id: int) -> AdminUserItem:
    row = sess.execute(text(_USER_SELECT + " WHERE u.user_id = :u"), {"u": user_id}).mappings().first()
    if row is None:
        raise ApiError(404, f"User {user_id} not found", "NOT_FOUND")
    return AdminUserItem(**row)


def _check_password(password: str) -> None:
    problem = password_policy_error(password)
    if problem:
        raise ApiError(400, problem, "PASSWORD_POLICY")


# --- pengguna -----------------------------------------------------------------

@router.get("/users", response_model=AdminUserListResponse, summary="List user accounts")
def list_users(sess: Session = Depends(get_session),
               q: str | None = Query(None, max_length=50, description="Username/name contains"),
               role_code: str | None = Query(None, pattern=r"^(USER|ANALYST|DATA_ENGINEER|ADMIN)$"),
               is_active: bool | None = None,
               limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)) -> AdminUserListResponse:
    where, params = ["true"], {}
    if q:
        where.append("(u.username ILIKE :q OR u.full_name ILIKE :q)")
        params["q"] = f"%{q}%"
    if role_code:
        where.append("r.role_code = :role")
        params["role"] = role_code
    if is_active is not None:
        where.append("u.is_active = :active")
        params["active"] = is_active
    cond = " AND ".join(where)
    total = sess.scalar(text(f"SELECT count(*) FROM users u JOIN roles r ON r.role_id = u.role_id WHERE {cond}"), params)
    rows = sess.execute(text(f"{_USER_SELECT} WHERE {cond} ORDER BY u.username LIMIT :limit OFFSET :offset"),
                        {**params, "limit": limit, "offset": offset}).mappings().all()
    return AdminUserListResponse(items=[AdminUserItem(**r) for r in rows], total=total, limit=limit, offset=offset)


@router.post("/users", status_code=201, response_model=AdminUserItem, summary="Create a user account")
def create_user(req: AdminUserCreateRequest, sess: Session = Depends(get_session),
                principal: Principal = Depends(current_principal)) -> AdminUserItem:
    _check_password(req.password)
    if sess.scalar(text("SELECT 1 FROM users WHERE username = :u"), {"u": req.username}):
        raise ApiError(409, f"Username {req.username} already exists", "USERNAME_TAKEN")
    user_id = sess.scalar(text("""
        INSERT INTO users (role_id, username, password_hash, full_name, organization, created_by)
        SELECT role_id, :username, :hash, :full_name, :org, :by FROM roles WHERE role_code = :role
        RETURNING user_id"""),
        {"username": req.username, "hash": hash_password(req.password), "full_name": req.full_name.strip(),
         "org": (req.organization or "").strip() or None, "by": principal.user_id, "role": req.role_code})
    return _get_user(sess, user_id)


@router.patch("/users/{user_id}", response_model=AdminUserItem, summary="Change role, name, organization or active status")
def update_user(user_id: int, req: AdminUserUpdateRequest, sess: Session = Depends(get_session),
                principal: Principal = Depends(current_principal)) -> AdminUserItem:
    current = _get_user(sess, user_id)
    if user_id == principal.user_id and (
        (req.is_active is False) or (req.role_code is not None and req.role_code != "ADMIN")
    ):
        # Mencegah admin terakhir mengunci dirinya sendiri keluar.
        raise ApiError(409, "Administrators cannot deactivate or demote their own account", "CANNOT_MODIFY_SELF")
    sets, params = [], {"u": user_id}
    if req.full_name is not None:
        sets.append("full_name = :full_name")
        params["full_name"] = req.full_name.strip()
    if "organization" in req.model_fields_set:
        sets.append("organization = :org")
        params["org"] = (req.organization or "").strip() or None
    if req.role_code is not None and req.role_code != current.role_code:
        sets.append("role_id = (SELECT role_id FROM roles WHERE role_code = :role)")
        params["role"] = req.role_code
    if req.is_active is not None:
        sets.append("is_active = :active")
        params["active"] = req.is_active
    if sets:
        sess.execute(text(f"UPDATE users SET {', '.join(sets)} WHERE user_id = :u"), params)
    return _get_user(sess, user_id)


@router.post("/users/{user_id}/reset-password", response_model=OkResponse, summary="Set a new password for a user")
def reset_password(user_id: int, req: AdminResetPasswordRequest,
                   sess: Session = Depends(get_session)) -> OkResponse:
    _get_user(sess, user_id)
    _check_password(req.new_password)
    sess.execute(text("""UPDATE users SET password_hash = :h, failed_login_count = 0, locked_until = NULL
                         WHERE user_id = :u"""), {"h": hash_password(req.new_password), "u": user_id})
    return OkResponse(message="Password reset")


@router.post("/users/{user_id}/unlock", response_model=OkResponse, summary="Unlock a temporarily locked account")
def unlock_user(user_id: int, sess: Session = Depends(get_session)) -> OkResponse:
    _get_user(sess, user_id)
    sess.execute(text("UPDATE users SET failed_login_count = 0, locked_until = NULL WHERE user_id = :u"),
                 {"u": user_id})
    return OkResponse(message="Account unlocked")


# --- token --------------------------------------------------------------------

@router.get("/tokens", response_model=TokenListResponse,
            summary="All API tokens (owner, prefix, scope, expiry, last use); revoke with DELETE /api/auth/tokens/{id}")
def all_tokens(sess: Session = Depends(get_session), user_id: int | None = None,
               active: bool | None = None, limit: int = Query(50, ge=1, le=500),
               offset: int = Query(0, ge=0)) -> TokenListResponse:
    where, params = ["true"], {}
    if user_id is not None:
        where.append("t.user_id = :uid")
        params["uid"] = user_id
    if active is not None:
        where.append(("" if active else "NOT ") + "(t.revoked_at IS NULL AND t.expires_at > now())")
    return list_tokens(sess, " AND ".join(where), params, limit, offset, with_owner=True)


# --- log ----------------------------------------------------------------------

def _log_query(sess: Session, view: str, where: list[str], params: dict, order: str,
               limit: int, offset: int) -> LogListResponse:
    cond = " AND ".join(where) or "true"
    total = sess.scalar(text(f"SELECT count(*) FROM {view} WHERE {cond}"), params)
    rows = sess.execute(text(f"SELECT * FROM {view} WHERE {cond} ORDER BY {order} LIMIT :limit OFFSET :offset"),
                        {**params, "limit": limit, "offset": offset}).mappings().all()
    items = [{k: (str(v) if k == "ip_address" and v is not None else v) for k, v in r.items()} for r in rows]
    return LogListResponse(items=items, total=total, limit=limit, offset=offset)


def _activity_filters(user_id, date_from, date_to, time_col="logged_at"):
    _check_dates(date_from, date_to)
    where, params = [], {}
    if user_id is not None:
        where.append("user_id = :uid")
        params["uid"] = user_id
    if date_from:
        where.append(f"{time_col} >= :df")
        params["df"] = date_from
    if date_to:
        where.append(f"{time_col} < CAST(:dt AS date) + 1")
        params["dt"] = date_to
    return where, params


@router.get("/logs/login", response_model=LogListResponse, summary="Sign-in log (v_log_login)")
def login_log(sess: Session = Depends(get_session), user_id: int | None = None,
              date_from: date | None = None, date_to: date | None = None,
              action: str | None = Query(None, pattern=r"^(LOGIN_SUCCESS|LOGIN_FAILED|LOGOUT)$"),
              page: int | None = Query(None, ge=1), limit: int = Query(50, ge=1, le=500),
              offset: int = Query(0, ge=0)) -> LogListResponse:
    where, params = _activity_filters(user_id, date_from, date_to)
    if action:
        where.append("action = :action")
        params["action"] = action
    return _log_query(sess, "v_log_login", where, params, "logged_at DESC, log_id DESC",
                      limit, _page(page, limit, offset))


@router.get("/logs/download", response_model=LogListResponse, summary="Download log (v_log_unduhan)")
def download_log(sess: Session = Depends(get_session), user_id: int | None = None,
                 date_from: date | None = None, date_to: date | None = None,
                 action: str | None = Query(None, pattern=r"^(DOWNLOAD_[A-Z_]+|EXPORT_CSV)$"),
                 page: int | None = Query(None, ge=1), limit: int = Query(50, ge=1, le=500),
                 offset: int = Query(0, ge=0)) -> LogListResponse:
    where, params = _activity_filters(user_id, date_from, date_to)
    if action:
        where.append("action = :action")
        params["action"] = action
    return _log_query(sess, "v_log_unduhan", where, params, "logged_at DESC, log_id DESC",
                      limit, _page(page, limit, offset))


@router.get("/audit", response_model=LogListResponse, summary="Audit trail (audit_log)")
def audit_trail(sess: Session = Depends(get_session), table: str | None = Query(None, max_length=63),
                operation: str | None = Query(None, pattern=r"^[IUD]$"), user_id: int | None = None,
                date_from: date | None = None, date_to: date | None = None,
                page: int | None = Query(None, ge=1), limit: int = Query(50, ge=1, le=500),
                offset: int = Query(0, ge=0)) -> LogListResponse:
    _check_dates(date_from, date_to)
    where, params = [], {}
    if table:
        where.append("table_name = :table")
        params["table"] = table
    if operation:
        where.append("operation = :op")
        params["op"] = operation
    if user_id is not None:
        where.append("app_user_id = :uid")
        params["uid"] = user_id
    if date_from:
        where.append("changed_at >= :df")
        params["df"] = date_from
    if date_to:
        where.append("changed_at < CAST(:dt AS date) + 1")
        params["dt"] = date_to
    return _log_query(sess, "audit_log", where, params, "changed_at DESC, audit_id DESC",
                      limit, _page(page, limit, offset))
