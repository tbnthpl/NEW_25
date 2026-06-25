from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status

from backend.auth import AuthUser, require_roles
from backend.audit import log_audit
from backend.db import SessionLocal
from backend.models import ApprovalRequest, MonthLock


router = APIRouter(prefix="/api/month-locks", tags=["month-locks"])


@router.get("")
def list_locks(user: AuthUser = Depends(require_roles("ADMIN", "AUDITOR"))):
    db = SessionLocal()
    locks = db.query(MonthLock).order_by(MonthLock.locked_at.desc()).all()
    result = [
        {
            "lock_id": l.lock_id,
            "month_key": l.month_key,
            "status": l.status,
            "locked_by": l.locked_by,
            "locked_at": l.locked_at,
        }
        for l in locks
    ]
    log_audit(db, "MONTH_LOCK", "LIST", "VIEW", None, f"count={len(result)}", user.employee_id)
    db.commit()
    db.close()
    return result


@router.post("/lock")
def lock_month(payload: dict, user: AuthUser = Depends(require_roles("ADMIN"))):
    month_key = payload.get("month_key")
    if not month_key:
        raise HTTPException(status_code=400, detail="month_key required")

    db = SessionLocal()
    pending = db.query(ApprovalRequest).filter(ApprovalRequest.status == "PENDING").count()
    if pending:
        db.close()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Pending approvals exist")

    existing = db.query(MonthLock).filter(MonthLock.month_key == month_key).first()
    if existing and existing.status == "LOCKED":
        db.close()
        raise HTTPException(status_code=409, detail="Month already locked")

    lock = MonthLock(
        month_key=month_key,
        status="LOCKED",
        locked_by=user.employee_id,
        locked_at=datetime.utcnow(),
    )
    db.add(lock)
    log_audit(db, "MONTH_LOCK", month_key, "LOCK", None, None, user.employee_id)
    db.commit()
    db.close()
    return {"status": "LOCKED", "month_key": month_key}
