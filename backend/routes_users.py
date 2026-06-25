
from fastapi import APIRouter, Depends, HTTPException, status

from backend.auth import AuthUser, require_roles
from backend.audit import log_audit
from backend.db import SessionLocal
from backend.models import UserAccount

router = APIRouter(prefix="/api/users", tags=["users"])

AD_PASSWORD_SENTINEL = "AD"
VALID_ROLES = ("MAKER", "CHECKER", "ADMIN", "AUDITOR")

@router.get("")
def list_users(user: AuthUser = Depends(require_roles("ADMIN"))):
    db = SessionLocal()
    rows = db.query(UserAccount).order_by(UserAccount.employee_id).all()
    result = [
        {
            "user_id": r.user_id,
            "employee_id": r.employee_id,
            "full_name": r.full_name,
            "role_code": r.role_code,
            "status": r.status,
            "last_login_date": r.last_login_date.isoformat() if r.last_login_date else None,
        }
        for r in rows
    ]
    db.close()
    return result

@router.post("")
def add_user(
    payload: dict,
    user: AuthUser = Depends(require_roles("ADMIN")),
):
    employee_id = (payload.get("employee_id") or "").strip()
    full_name = (payload.get("full_name") or "").strip()
    role_code = (payload.get("role_code") or "").strip().upper()

    if not employee_id:
        raise HTTPException(status_code=400, detail="employee_id is required")
    if not full_name:
        raise HTTPException(status_code=400, detail="full_name is required")
    if role_code not in VALID_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"role_code must be one of: {', '.join(VALID_ROLES)}",
        )

    db = SessionLocal()
    existing = (
        db.query(UserAccount)
        .filter(UserAccount.employee_id == employee_id)
        .first()
    )
    if existing:
        db.close()
        raise HTTPException(
            status_code=409,
            detail=f"User {employee_id} already has access. Use deactivate then add to change role.",
        )

    new_user = UserAccount(
        employee_id=employee_id,
        full_name=full_name,
        role_code=role_code,
        password_hash=AD_PASSWORD_SENTINEL,
        status="ACTIVE",
    )
    db.add(new_user)
    db.flush()
    log_audit(
        db,
        "USER_ACCOUNT",
        new_user.user_id,
        "ADD",
        None,
        f"employee_id={employee_id},role={role_code}",
        user.employee_id,
    )
    db.commit()
    db.refresh(new_user)
    db.close()
    return {
        "user_id": new_user.user_id,
        "employee_id": new_user.employee_id,
        "full_name": new_user.full_name,
        "role_code": new_user.role_code,
        "status": new_user.status,
    }

@router.patch("/{user_id}/deactivate")
def deactivate_user(
    user_id: int,
    user: AuthUser = Depends(require_roles("ADMIN")),
):
    db = SessionLocal()
    target = db.query(UserAccount).filter(UserAccount.user_id == user_id).first()
    if not target:
        db.close()
        raise HTTPException(status_code=404, detail="User not found")
    if target.employee_id == user.employee_id:
        db.close()
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")

    target.status = "INACTIVE"
    log_audit(
        db,
        "USER_ACCOUNT",
        target.user_id,
        "DEACTIVATE",
        "ACTIVE",
        "INACTIVE",
        user.employee_id,
    )
    db.commit()
    db.close()
    return {"status": "ok", "user_id": user_id}

@router.patch("/{user_id}/activate")
def activate_user(
    user_id: int,
    user: AuthUser = Depends(require_roles("ADMIN")),
):
    db = SessionLocal()
    target = db.query(UserAccount).filter(UserAccount.user_id == user_id).first()
    if not target:
        db.close()
        raise HTTPException(status_code=404, detail="User not found")

    target.status = "ACTIVE"
    log_audit(
        db,
        "USER_ACCOUNT",
        target.user_id,
        "ACTIVATE",
        "INACTIVE",
        "ACTIVE",
        user.employee_id,
    )
    db.commit()
    db.close()
    return {"status": "ok", "user_id": user_id}

@router.patch("/{user_id}/role")
def update_user_role(
    user_id: int,
    payload: dict,
    user: AuthUser = Depends(require_roles("ADMIN")),
):
    role_code = (payload.get("role_code") or "").strip().upper()
    if role_code not in VALID_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"role_code must be one of: {', '.join(VALID_ROLES)}",
        )

    db = SessionLocal()
    target = db.query(UserAccount).filter(UserAccount.user_id == user_id).first()
    if not target:
        db.close()
        raise HTTPException(status_code=404, detail="User not found")

    old_role = target.role_code
    target.role_code = role_code
    log_audit(
        db,
        "USER_ACCOUNT",
        target.user_id,
        "UPDATE_ROLE",
        old_role,
        role_code,
        user.employee_id,
    )
    db.commit()
    db.close()
    return {"status": "ok", "user_id": user_id, "role_code": role_code}
