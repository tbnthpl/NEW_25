
import json
import logging
import traceback

from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from backend.db import SessionLocal
from backend.models import ApiLog

logger = logging.getLogger(__name__)

def _truncate(s: str | None, max_len: int = 4000) -> str | None:
    if s is None:
        return None
    return s[:max_len] if len(s) > max_len else s

def _log_api_error(
    method: str,
    path: str,
    status_code: int,
    message: str | None,
    detail: str | None,
    user_id: str | None = None,
):
    db = None
    try:
        db = SessionLocal()
        entry = ApiLog(
            method=method,
            path=_truncate(path, 500),
            status_code=status_code,
            log_level="ERROR" if status_code >= 500 else "WARNING",
            message=_truncate(message, 4000),
            detail=_truncate(detail, 4000),
            user_id=_truncate(user_id, 50) if user_id else None,
        )
        db.add(entry)
        db.commit()
    except Exception as e:
        logger.warning("Failed to write api_log: %s", e)
        if db is not None:
            try:
                db.rollback()
            except Exception:
                pass
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass

def _get_user_id_from_request(request: Request) -> str | None:
    try:
        auth = request.headers.get("Authorization")
        if not auth or not auth.startswith("Bearer "):
            return None
        from backend.auth import _TOKEN_STORE

        token = auth.replace("Bearer ", "").strip()
        session = _TOKEN_STORE.get(token)
        if not session:
            return None
        user = getattr(session, "user", session)
        return getattr(user, "employee_id", None)
    except Exception:
        return None

async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    raw_errors = exc.errors() or []
    redacted = []
    for err in raw_errors:
        loc = err.get("loc")
        if isinstance(loc, (list, tuple)):
            loc_path = ".".join(str(p) for p in loc)
        else:
            loc_path = str(loc) if loc is not None else ""
        redacted.append({"loc": loc_path, "type": err.get("type"), "msg": err.get("msg")})
    summary = json.dumps(redacted, default=str)

    try:
        logger.warning(
            "Validation error on %s %s: %s",
            request.method,
            request.url.path,
            json.dumps(raw_errors, default=str)[:4000],
        )
    except Exception:
        pass

    _log_api_error(
        method=request.method,
        path=str(request.url.path),
        status_code=422,
        message=summary[:500] if summary else "Validation error",
        detail=summary if len(summary) > 500 else None,
        user_id=_get_user_id_from_request(request),
    )
    return JSONResponse(status_code=422, content={"detail": raw_errors})

async def http_exception_handler(request: Request, exc) -> JSONResponse:
    detail_str = str(exc.detail) if exc.detail is not None else ""
    if isinstance(exc.detail, (list, dict)):
        import json
        try:
            detail_str = json.dumps(exc.detail, default=str)
        except Exception:
            detail_str = str(exc.detail)
    _log_api_error(
        method=request.method,
        path=str(request.url.path),
        status_code=exc.status_code,
        message=detail_str[:500] if detail_str else None,
        detail=detail_str if len(detail_str) > 500 else None,
        user_id=_get_user_id_from_request(request),
    )
    if isinstance(exc.detail, (list, dict)):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc.detail)})

async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    tb = traceback.format_exc()
    logger.exception("Unhandled %s on %s %s", type(exc).__name__, request.method, request.url.path)
    summary = f"{type(exc).__name__}: {str(exc)[:300]}"
    _log_api_error(
        method=request.method,
        path=str(request.url.path),
        status_code=500,
        message=str(exc)[:500],
        detail=summary,
        user_id=_get_user_id_from_request(request),
    )
    del tb
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )
