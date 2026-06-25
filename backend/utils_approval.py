import json
import logging
from datetime import datetime

from fastapi import HTTPException, status

from backend.auth import AuthUser
from backend.utils_datetime import to_utc_iso

logger = logging.getLogger(__name__)

def safe_json_loads_clob(raw, default=None, raise_on_error=True):
    if default is None:
        default = {}
    if raw is None:
        return default
    if hasattr(raw, "read"):
        raw = raw.read()
        if raw is None:
            return default
    s = str(raw).strip()
    if s.startswith("\ufeff"):
        s = s[1:].strip()
    if not s:
        return default
    try:
        return json.loads(s)
    except json.JSONDecodeError as e:
        if raise_on_error:
            logger.warning(
                "safe_json_loads_clob: failed to parse approval CLOB (len=%s)", len(s)
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Invalid approval data: could not parse proposed_data",
            ) from e
        return default

def ensure_pending(approval, label: str = "Request") -> None:
    if approval is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{label} not found")
    current = getattr(approval, "status", None)
    if current and str(current).upper() != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{label} already processed (status={current})",
        )

def enforce_checker_rules(user: AuthUser, maker_id: str, checker_id: str, comment: str) -> None:
    if not comment or not comment.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Comment required")
    if user.role != "ADMIN" and checker_id != user.employee_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Checker mismatch")
    if maker_id == checker_id and user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Maker cannot approve")

def init_comment_history(maker_comment: str | None, maker_id: str) -> str:
    history = []
    if maker_comment:
        history.append(
            {
                "role": "MAKER",
                "user_id": maker_id,
                "comment": maker_comment,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )
    return json.dumps(history, default=str)

def append_comment_history(existing: str | None, role: str, user_id: str, comment: str) -> str:
    history = []
    if existing:
        try:
            raw = existing
            if hasattr(raw, "read"):
                raw = raw.read()
            s = (raw or "").strip() if raw is not None else ""
            if s:
                history = json.loads(s)
            if not isinstance(history, list):
                history = []
        except (json.JSONDecodeError, TypeError, AttributeError):
            history = []
    history.append(
        {
            "role": role,
            "user_id": user_id,
            "comment": comment,
            "timestamp": to_utc_iso(datetime.utcnow()),
        }
    )
    return json.dumps(history, default=str)
