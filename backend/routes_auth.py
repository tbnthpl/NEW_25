import logging
import os
import time
from collections import defaultdict, deque
from datetime import datetime
from threading import Lock

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from backend.auth import (
    AUTH_COOKIE_NAME,
    AUTH_TOKEN_TTL_MINUTES,
    AuthUser,
    authenticate,
    get_current_user,
    issue_token,
    revoke_token,
)
from backend.audit import log_audit
from backend.db import SessionLocal
from backend.models import UserAccount

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])

_ENVIRONMENT = os.environ.get("ENVIRONMENT", "").strip().lower()
_IS_PROD_TIER = _ENVIRONMENT in {"uat", "pre", "preprod", "prod", "production", "prd"}
_COOKIE_SECURE_DEFAULT = "true" if _IS_PROD_TIER else "false"
_COOKIE_SECURE_RAW = os.environ.get("AUTH_COOKIE_SECURE", _COOKIE_SECURE_DEFAULT).lower() in (
    "true",
    "1",
    "yes",
)
COOKIE_SECURE = True if _IS_PROD_TIER else _COOKIE_SECURE_RAW
if _IS_PROD_TIER and not _COOKIE_SECURE_RAW:
    logger.warning(
        "AUTH_COOKIE_SECURE=false ignored: ENVIRONMENT=%r forces Secure cookies.",
        _ENVIRONMENT,
    )
COOKIE_SAMESITE = os.environ.get("AUTH_COOKIE_SAMESITE", "lax").strip().lower() or "lax"

_LOGIN_WINDOW_SEC = int(os.environ.get("LOGIN_RATE_WINDOW_SEC", "60"))
_LOGIN_MAX_PER_IP = int(os.environ.get("LOGIN_MAX_PER_IP_PER_MIN", "20"))
_LOGIN_MAX_PER_USER = int(os.environ.get("LOGIN_MAX_PER_USER_PER_MIN", "8"))
_LOGIN_LOCKOUT_FAILS = int(os.environ.get("LOGIN_LOCKOUT_FAILS", "10"))
_LOGIN_LOCKOUT_SEC = int(os.environ.get("LOGIN_LOCKOUT_SEC", "300"))

_login_attempts_ip: dict[str, deque[float]] = defaultdict(deque)
_login_attempts_user: dict[str, deque[float]] = defaultdict(deque)
_login_failures: dict[str, deque[float]] = defaultdict(deque)
_login_locks: dict[str, float] = {}
_login_lock = Lock()

_LOGIN_FAIL_AUDIT_MAX_PER_MIN = int(os.environ.get("LOGIN_FAIL_AUDIT_MAX_PER_MIN", "3"))
_login_fail_audit: dict[tuple[str, str], deque[float]] = defaultdict(deque)

def _should_audit_login_failure(ip: str, employee_id: str) -> bool:
    now = time.time()
    horizon = now - 60.0
    key = (ip, (employee_id or "").strip().lower())
    with _login_lock:
        window = _login_fail_audit[key]
        _trim(window, horizon)
        if len(window) >= _LOGIN_FAIL_AUDIT_MAX_PER_MIN:
            return False
        window.append(now)
        return True

_LOGIN_FAIL_FLOOR_MS = int(os.environ.get("LOGIN_FAIL_FLOOR_MS", "750"))

_TRUSTED_PROXIES_RAW = os.environ.get("TRUSTED_PROXIES", "").strip()
_TRUSTED_PROXIES: frozenset[str] = frozenset(
    p.strip() for p in _TRUSTED_PROXIES_RAW.split(",") if p.strip()
)

def _client_ip(request: Request) -> str:
    direct = request.client.host if request.client else "unknown"
    fwd = request.headers.get("x-forwarded-for")
    if not fwd:
        return direct
    if _TRUSTED_PROXIES and direct not in _TRUSTED_PROXIES:
        return direct
    return fwd.split(",")[0].strip()

def _trim(window: deque[float], horizon: float) -> None:
    while window and window[0] < horizon:
        window.popleft()

def _check_and_record_login(ip: str, employee_id: str) -> None:
    now = time.time()
    horizon = now - _LOGIN_WINDOW_SEC
    key = (employee_id or "").strip().lower()
    with _login_lock:
        locked_until = _login_locks.get(key)
        if locked_until and locked_until > now:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many failed attempts. Please try again later.",
            )
        ip_bucket = _login_attempts_ip[ip]
        user_bucket = _login_attempts_user[key]
        _trim(ip_bucket, horizon)
        _trim(user_bucket, horizon)
        if len(ip_bucket) >= _LOGIN_MAX_PER_IP or len(user_bucket) >= _LOGIN_MAX_PER_USER:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many login attempts. Please slow down.",
            )
        ip_bucket.append(now)
        user_bucket.append(now)

def _record_login_failure(employee_id: str) -> None:
    now = time.time()
    horizon = now - _LOGIN_WINDOW_SEC
    key = (employee_id or "").strip().lower()
    with _login_lock:
        fails = _login_failures[key]
        _trim(fails, horizon)
        fails.append(now)
        if len(fails) >= _LOGIN_LOCKOUT_FAILS:
            _login_locks[key] = now + _LOGIN_LOCKOUT_SEC
            fails.clear()

def _clear_login_failures(employee_id: str) -> None:
    key = (employee_id or "").strip().lower()
    with _login_lock:
        _login_failures.pop(key, None)
        _login_locks.pop(key, None)

class LoginRequest(BaseModel):
    employeeId: str
    password: str

@router.post("/login")
def login(payload: LoginRequest, request: Request, response: Response):
    started_at = time.monotonic()
    ip = _client_ip(request)
    _check_and_record_login(ip, payload.employeeId)

    db = SessionLocal()
    user = None
    try:
        try:
            user = authenticate(db, payload.employeeId, payload.password)
        except Exception:
            user = None
        if not user:
            if _should_audit_login_failure(ip, payload.employeeId):
                try:
                    log_audit(
                        db,
                        entity_type="AUTH",
                        entity_id=None,
                        action="LOGIN_FAILED",
                        old_data=None,
                        new_data=f"employee_id={payload.employeeId}",
                        changed_by=payload.employeeId,
                    )
                    db.commit()
                except Exception:
                    db.rollback()
            _record_login_failure(payload.employeeId)
            elapsed_ms = (time.monotonic() - started_at) * 1000.0
            remaining = (_LOGIN_FAIL_FLOOR_MS - elapsed_ms) / 1000.0
            if remaining > 0:
                time.sleep(remaining)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

        token = issue_token(user)
        db_user = (
            db.query(UserAccount)
            .filter(UserAccount.employee_id == payload.employeeId)
            .first()
        )
        if db_user:
            db_user.last_login_date = datetime.utcnow()
        log_audit(
            db,
            entity_type="AUTH",
            entity_id=None,
            action="LOGIN",
            old_data=None,
            new_data=f"employee_id={user.employee_id}",
            changed_by=user.employee_id,
        )
        db.commit()
        _clear_login_failures(payload.employeeId)
    except HTTPException:
        raise
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        raise
    finally:
        db.close()

    cookie_max_age = AUTH_TOKEN_TTL_MINUTES * 60
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        max_age=cookie_max_age,
        httponly=True,
        samesite=COOKIE_SAMESITE,
        secure=COOKIE_SECURE,
        path="/",
    )
    return {"token": token, "employeeId": user.employee_id, "name": user.name, "role": user.role}

@router.get("/me")
def me(user: AuthUser = Depends(get_current_user)):
    return {"employeeId": user.employee_id, "name": user.name, "role": user.role}

@router.post("/logout")
def logout(request: Request, response: Response, user: AuthUser = Depends(get_current_user)):
    db = SessionLocal()
    try:
        log_audit(
            db,
            entity_type="AUTH",
            entity_id=None,
            action="LOGOUT",
            old_data=None,
            new_data=f"employee_id={user.employee_id}",
            changed_by=user.employee_id,
        )
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()
    revoke_token(request)
    response.delete_cookie(
        key=AUTH_COOKIE_NAME,
        path="/",
        httponly=True,
        samesite=COOKIE_SAMESITE,
        secure=COOKIE_SECURE,
    )
    return {"status": "ok"}
