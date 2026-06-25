import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status

from backend.auth import AuthUser, require_roles
from backend.audit import log_audit
from backend.db import SessionLocal
from backend.models import ApprovalRequest, VendorChargeMaster, VendorMaster
from backend.schemas import ApprovalDecision, VendorChargeRequest
from backend.utils_approval import append_comment_history, enforce_checker_rules, ensure_pending, init_comment_history
from backend.utils_month_lock import enforce_month_unlocked

router = APIRouter(prefix="/api/vendor-charges", tags=["vendor-charges"])

@router.get("")
def list_vendor_charges(
    vendor_id: int | None = None,
    include_inactive: bool = False,
    user: AuthUser = Depends(require_roles("MAKER", "CHECKER", "ADMIN", "AUDITOR")),
):
    db = SessionLocal()
    query = (
        db.query(VendorChargeMaster, VendorMaster.vendor_name, VendorMaster.vendor_code)
        .outerjoin(VendorMaster, VendorChargeMaster.vendor_id == VendorMaster.vendor_id)
        .order_by(VendorChargeMaster.vendor_id, VendorChargeMaster.pickup_type, VendorChargeMaster.effective_from.desc())
    )
    if vendor_id is not None:
        query = query.filter(VendorChargeMaster.vendor_id == vendor_id)
    if not include_inactive:
        query = query.filter(VendorChargeMaster.status == "ACTIVE")
    rows = query.all()
    result = [
        {
            "vendor_charge_id": c.vendor_charge_id,
            "vendor_id": c.vendor_id,
            "vendor_name": name or "",
            "vendor_code": code or "",
            "pickup_type": c.pickup_type,
            "base_charge": float(c.base_charge or 0),
            "status": c.status,
            "effective_from": c.effective_from.isoformat() if c.effective_from else None,
            "effective_to": c.effective_to.isoformat() if c.effective_to else None,
        }
        for c, name, code in rows
    ]
    db.close()
    return result

@router.post("/requests")
def request_vendor_charge(
    payload: VendorChargeRequest, user: AuthUser = Depends(require_roles("MAKER", "ADMIN"))
):
    if payload.maker_id != user.employee_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Maker mismatch")

    db = SessionLocal()
    enforce_month_unlocked(db, payload.effective_from.strftime("%Y%m"))
    charge = VendorChargeMaster(
        vendor_id=payload.vendor_id,
        pickup_type=payload.pickup_type,
        base_charge=payload.base_charge,
        status="INACTIVE",
        effective_from=payload.effective_from,
        created_by=payload.maker_id,
    )
    db.add(charge)
    db.flush()

    approval = ApprovalRequest(
        entity_type="VENDOR_CHARGE",
        entity_id=charge.vendor_charge_id,
        original_data=json.dumps({}),
        proposed_data=json.dumps(payload.model_dump(), default=str),
        reason=payload.reason,
        comments_history=init_comment_history(payload.reason, payload.maker_id),
        maker_id=payload.maker_id,
        status="PENDING",
    )
    db.add(approval)
    db.flush()
    log_audit(db, "VENDOR_CHARGE", charge.vendor_charge_id, "REQUEST", None, payload.model_dump(), user.employee_id)
    approval_id = approval.approval_id
    vendor_charge_id = charge.vendor_charge_id
    db.commit()
    db.close()
    return {"approval_id": approval_id, "vendor_charge_id": vendor_charge_id}

@router.post("/requests/{approval_id}/approve")
def approve_vendor_charge(
    approval_id: int,
    decision: ApprovalDecision,
    user: AuthUser = Depends(require_roles("CHECKER", "ADMIN")),
):
    db = SessionLocal()
    approval = db.query(ApprovalRequest).filter(ApprovalRequest.approval_id == approval_id).first()
    if not approval or approval.entity_type != "VENDOR_CHARGE":
        db.close()
        raise HTTPException(status_code=404, detail="Approval not found")
    try:
        ensure_pending(approval, "Approval")
    except HTTPException:
        db.close()
        raise

    enforce_checker_rules(user, approval.maker_id, decision.checker_id, decision.comment)

    charge = db.query(VendorChargeMaster).filter(VendorChargeMaster.vendor_charge_id == approval.entity_id).first()
    if not charge:
        db.close()
        raise HTTPException(status_code=404, detail="Charge not found")

    active = (
        db.query(VendorChargeMaster)
        .filter(VendorChargeMaster.vendor_id == charge.vendor_id)
        .filter(VendorChargeMaster.pickup_type == charge.pickup_type)
        .filter(VendorChargeMaster.vendor_charge_id != charge.vendor_charge_id)
        .filter(VendorChargeMaster.status == "ACTIVE")
        .all()
    )
    for row in active:
        row.status = "INACTIVE"
        row.effective_to = charge.effective_from - timedelta(days=1)

    charge.status = "ACTIVE"
    charge.approved_by = decision.checker_id
    charge.approved_date = datetime.utcnow()
    approval.status = "APPROVED"
    approval.checker_id = decision.checker_id
    approval.checker_comment = decision.comment
    approval.comments_history = append_comment_history(
        approval.comments_history, "CHECKER", decision.checker_id, decision.comment
    )
    approval.approved_date = datetime.utcnow()

    log_audit(db, "VENDOR_CHARGE", charge.vendor_charge_id, "APPROVE", None, decision.comment, user.employee_id)
    db.commit()
    db.close()
    return {"status": "APPROVED"}

@router.post("/requests/{approval_id}/reject")
def reject_vendor_charge(
    approval_id: int,
    decision: ApprovalDecision,
    user: AuthUser = Depends(require_roles("CHECKER", "ADMIN")),
):
    db = SessionLocal()
    approval = db.query(ApprovalRequest).filter(ApprovalRequest.approval_id == approval_id).first()
    if not approval or approval.entity_type != "VENDOR_CHARGE":
        db.close()
        raise HTTPException(status_code=404, detail="Approval not found")
    try:
        ensure_pending(approval, "Approval")
    except HTTPException:
        db.close()
        raise

    enforce_checker_rules(user, approval.maker_id, decision.checker_id, decision.comment)

    approval.status = "REJECTED"
    approval.checker_id = decision.checker_id
    approval.checker_comment = decision.comment
    approval.comments_history = append_comment_history(
        approval.comments_history, "CHECKER", decision.checker_id, decision.comment
    )
    approval.approved_date = datetime.utcnow()

    log_audit(db, "VENDOR_CHARGE", approval.entity_id, "REJECT", None, decision.comment, user.employee_id)
    db.commit()
    db.close()
    return {"status": "REJECTED"}
