import logging
import os
import random
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from backend.db import SessionLocal
from backend.models import UserAccount, UserSession

logger = logging.getLogger(__name__)

@dataclass
class AuthUser:
    employee_id: str
    name: str
    role: str

@dataclass
class TokenSession:
    user: AuthUser
    expires_at: datetime

_TOKEN_STORE: dict[str, TokenSession] = {}
AUTH_TOKEN_TTL_MINUTES = int(os.environ.get("AUTH_TOKEN_TTL_MINUTES", "480"))
_TOKEN_TTL_MINUTES = AUTH_TOKEN_TTL_MINUTES
AUTH_COOKIE_NAME = os.environ.get("AUTH_COOKIE_NAME", "dsb_auth")
PERSIST_TOKENS = os.environ.get("AUTH_PERSIST_TOKENS", "true").lower() in ("true", "1", "yes")

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

def _extract_bearer_token(request: Request) -> str:
    header = request.headers.get("Authorization")
    if not header or not header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    return header.replace("Bearer ", "").strip()

def extract_token(request: Request) -> str:
    header = request.headers.get("Authorization")
    if header and header.startswith("Bearer "):
        return header.replace("Bearer ", "").strip()
    cookie_token = request.cookies.get(AUTH_COOKIE_NAME)
    if cookie_token:
        return cookie_token.strip()
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")

def authenticate(db: Session, employee_id: str, password: str) -> AuthUser | None:
    user = (
        db.query(UserAccount)
        .filter(UserAccount.employee_id == employee_id)
        .filter(UserAccount.status == "ACTIVE")
        .first()
    )
    if not user:
        return None

    try:
        from backend.ad_login import validate_ad_credentials

        ad_ok = validate_ad_credentials(employee_id, password)
    except Exception as e:
        logging.getLogger(__name__).warning("AD validation error: %s", e)
        ad_ok = False

    if not ad_ok:
        return None

    return AuthUser(employee_id=user.employee_id, name=user.full_name, role=user.role_code)

def _persist_session(token: str, user: AuthUser, expires_at: datetime) -> None:
    if not PERSIST_TOKENS:
        return
    db = SessionLocal()
    try:
        row = UserSession(
            token=token,
            employee_id=user.employee_id,
            role_code=user.role,
            full_name=user.name,
            expires_at=expires_at.replace(tzinfo=None),
            last_seen_at=datetime.utcnow(),
        )
        db.add(row)
        db.commit()
    except Exception as exc:
        logger.warning("Persisting auth token failed (continuing with in-memory cache): %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()

def _load_session_from_db(token: str) -> TokenSession | None:
    if not PERSIST_TOKENS:
        return None
    db = SessionLocal()
    try:
        row = db.query(UserSession).filter(UserSession.token == token).first()
        if not row:
            return None
        if row.expires_at and row.expires_at <= datetime.utcnow():
            try:
                db.delete(row)
                db.commit()
            except Exception:
                db.rollback()
            return None
        try:
            row.last_seen_at = datetime.utcnow()
            row.expires_at = datetime.utcnow() + timedelta(minutes=_TOKEN_TTL_MINUTES)
            db.commit()
        except Exception:
            db.rollback()
        expires_at_aware = row.expires_at.replace(tzinfo=timezone.utc) if row.expires_at else _utcnow()
        return TokenSession(
            user=AuthUser(employee_id=row.employee_id, name=row.full_name, role=row.role_code),
            expires_at=expires_at_aware,
        )
    except Exception as exc:
        logger.warning("Loading auth token from DB failed: %s", exc)
        return None
    finally:
        db.close()

def _delete_session_in_db(token: str) -> None:
    if not PERSIST_TOKENS:
        return
    db = SessionLocal()
    try:
        db.query(UserSession).filter(UserSession.token == token).delete()
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()

def issue_token(user: AuthUser) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = _utcnow() + timedelta(minutes=_TOKEN_TTL_MINUTES)
    _TOKEN_STORE[token] = TokenSession(user=user, expires_at=expires_at)
    _persist_session(token, user, expires_at)
    return token

_TOKEN_SWEEP_CHANCE = float(os.environ.get("AUTH_TOKEN_SWEEP_CHANCE", "0.005"))

def _maybe_sweep_token_store() -> None:
    if _TOKEN_SWEEP_CHANCE <= 0 or random.random() > _TOKEN_SWEEP_CHANCE:
        return
    now = _utcnow()
    expired = [t for t, s in _TOKEN_STORE.items() if s.expires_at <= now]
    for t in expired:
        _TOKEN_STORE.pop(t, None)

def get_current_user(request: Request) -> AuthUser:
    token = extract_token(request)
    _maybe_sweep_token_store()
    session = _TOKEN_STORE.get(token)
    if not session:
        session = _load_session_from_db(token)
        if session:
            _TOKEN_STORE[token] = session
    if not session or session.expires_at <= _utcnow():
        _TOKEN_STORE.pop(token, None)
        _delete_session_in_db(token)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = session.user
    db = SessionLocal()
    try:
        active = (
            db.query(UserAccount)
            .filter(UserAccount.employee_id == user.employee_id)
            .filter(UserAccount.status == "ACTIVE")
            .first()
        )
        if not active:
            _TOKEN_STORE.pop(token, None)
            _delete_session_in_db(token)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        session.expires_at = _utcnow() + timedelta(minutes=_TOKEN_TTL_MINUTES)
        return user
    finally:
        db.close()

def revoke_token(request: Request) -> None:
    try:
        token = extract_token(request)
    except HTTPException:
        return
    _TOKEN_STORE.pop(token, None)
    _delete_session_in_db(token)

def require_roles(*roles: str):
    def _dependency(user: AuthUser = Depends(get_current_user)) -> AuthUser:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        return user

    return _dependency
