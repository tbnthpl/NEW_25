import json
from datetime import datetime, timedelta, date

from fastapi import APIRouter, Depends, HTTPException, status

from backend.auth import AuthUser, require_roles
from backend.audit import log_audit
from backend.db import SessionLocal
from backend.models import ApprovalRequest, VendorMaster
from backend.schemas import ApprovalDecision, VendorDeactivateRequest, VendorMasterRequest
from backend.utils_approval import append_comment_history, ensure_pending, enforce_checker_rules, init_comment_history, safe_json_loads_clob
from backend.utils_month_lock import enforce_month_unlocked

router = APIRouter(prefix="/api/vendors", tags=["vendors"])

@router.get("")
def list_vendors(
    include_inactive: bool = False,
    user: AuthUser = Depends(require_roles("MAKER", "CHECKER", "ADMIN", "AUDITOR")),
):
    db = SessionLocal()
    query = db.query(VendorMaster)
    if not include_inactive:
        query = query.filter(VendorMaster.status == "ACTIVE")
    vendors = query.all()

    vendor_ids = [v.vendor_id for v in vendors]
    latest_by_vendor: dict = {}
    if vendor_ids:
        approvals = (
            db.query(ApprovalRequest)
            .filter(ApprovalRequest.entity_type == "VENDOR_MASTER")
            .filter(ApprovalRequest.entity_id.in_(vendor_ids))
            .order_by(ApprovalRequest.created_date.desc())
            .all()
        )
        for ap in approvals:
            if ap.entity_id in latest_by_vendor:
                continue
            proposed = safe_json_loads_clob(ap.proposed_data, raise_on_error=False)
            latest_by_vendor[ap.entity_id] = {
                "approval_id": ap.approval_id,
                "approval_status": ap.status,
                "approval_action": proposed.get("action") if isinstance(proposed, dict) else None,
                "maker_id": ap.maker_id,
                "checker_id": ap.checker_id,
                "checker_comment": ap.checker_comment,
                "approval_created_at": ap.created_date.isoformat() if ap.created_date else None,
                "approval_decided_at": ap.approved_date.isoformat() if ap.approved_date else None,
            }

    result = []
    for v in vendors:
        meta = latest_by_vendor.get(v.vendor_id, {})
        result.append(
            {
                "vendor_id": v.vendor_id,
                "name": v.vendor_name,
                "code": v.vendor_code,
                "status": v.status,
                "approval_id": meta.get("approval_id"),
                "approval_status": meta.get("approval_status"),
                "approval_action": meta.get("approval_action"),
                "maker_id": meta.get("maker_id"),
                "checker_id": meta.get("checker_id"),
                "checker_comment": meta.get("checker_comment"),
                "approval_created_at": meta.get("approval_created_at"),
                "approval_decided_at": meta.get("approval_decided_at"),
            }
        )
    log_audit(db, "VENDOR_MASTER", "LIST", "VIEW", None, f"count={len(result)}", user.employee_id)
    db.commit()
    db.close()
    return result

@router.post("")
def request_vendor(payload: VendorMasterRequest, user: AuthUser = Depends(require_roles("MAKER", "ADMIN"))):
    if payload.maker_id != user.employee_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Maker mismatch")

    db = SessionLocal()
    enforce_month_unlocked(db, payload.effective_from.strftime("%Y%m"))
    existing = db.query(VendorMaster).filter(VendorMaster.vendor_code == payload.vendor_code).first()
    if existing:
        db.close()
        raise HTTPException(status_code=400, detail="Vendor code already exists or pending approval")

    vendor = VendorMaster(
        vendor_name=payload.vendor_name,
        vendor_code=payload.vendor_code,
        status="INACTIVE",
        effective_from=payload.effective_from,
        created_by=payload.maker_id,
    )
    db.add(vendor)
    db.flush()

    approval = ApprovalRequest(
        entity_type="VENDOR_MASTER",
        entity_id=vendor.vendor_id,
        original_data=json.dumps({}),
        proposed_data=json.dumps(payload.model_dump(), default=str),
        reason=payload.reason,
        comments_history=init_comment_history(payload.reason, payload.maker_id),
        maker_id=payload.maker_id,
        status="PENDING",
    )
    db.add(approval)
    db.flush()
    approval_id = approval.approval_id
    vendor_id = vendor.vendor_id
    log_audit(db, "VENDOR_MASTER", vendor.vendor_id, "REQUEST", None, payload.model_dump(), user.employee_id)
    db.commit()
    db.close()
    return {"approval_id": approval_id, "vendor_id": vendor_id}

@router.post("/requests/{approval_id}/approve")
def approve_vendor(
    approval_id: int,
    decision: ApprovalDecision,
    user: AuthUser = Depends(require_roles("CHECKER", "ADMIN")),
):
    db = SessionLocal()
    approval = db.query(ApprovalRequest).filter(ApprovalRequest.approval_id == approval_id).first()
    if not approval or approval.entity_type != "VENDOR_MASTER":
        db.close()
        raise HTTPException(status_code=404, detail="Approval not found")
    try:
        ensure_pending(approval, "Approval")
    except HTTPException:
        db.close()
        raise
    enforce_checker_rules(user, approval.maker_id, decision.checker_id, decision.comment)

    db.refresh(approval)
    vendor = db.query(VendorMaster).filter(VendorMaster.vendor_id == approval.entity_id).first()
    if not vendor:
        db.close()
        raise HTTPException(status_code=404, detail="Vendor not found")

    proposed = safe_json_loads_clob(approval.proposed_data, raise_on_error=False)
    is_deactivate = proposed.get("action") == "DEACTIVATE"

    if is_deactivate:
        vendor.status = "INACTIVE"
        vendor.effective_to = date.today()
    else:
        active = (
            db.query(VendorMaster)
            .filter(VendorMaster.vendor_code == vendor.vendor_code)
            .filter(VendorMaster.vendor_id != vendor.vendor_id)
            .filter(VendorMaster.status == "ACTIVE")
            .all()
        )
        for row in active:
            row.status = "INACTIVE"
            row.effective_to = vendor.effective_from - timedelta(days=1)
        vendor.status = "ACTIVE"
    vendor.approved_by = decision.checker_id
    vendor.approved_date = datetime.utcnow()
    approval.status = "APPROVED"
    approval.checker_id = decision.checker_id
    approval.checker_comment = decision.comment
    approval.comments_history = append_comment_history(
        approval.comments_history, "CHECKER", decision.checker_id, decision.comment
    )
    approval.approved_date = datetime.utcnow()

    log_audit(db, "VENDOR_MASTER", vendor.vendor_id, "APPROVE", None, decision.comment, user.employee_id)
    db.commit()
    db.close()
    return {"status": "APPROVED"}

@router.post("/requests/{approval_id}/reject")
def reject_vendor(
    approval_id: int,
    decision: ApprovalDecision,
    user: AuthUser = Depends(require_roles("CHECKER", "ADMIN")),
):
    db = SessionLocal()
    approval = db.query(ApprovalRequest).filter(ApprovalRequest.approval_id == approval_id).first()
    if not approval or approval.entity_type != "VENDOR_MASTER":
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

    log_audit(db, "VENDOR_MASTER", approval.entity_id, "REJECT", None, decision.comment, user.employee_id)
    db.commit()
    db.close()
    return {"status": "REJECTED"}

@router.post("/requests/{vendor_id}/deactivate")
def request_deactivate_vendor(
    vendor_id: int,
    payload: VendorDeactivateRequest,
    user: AuthUser = Depends(require_roles("MAKER", "ADMIN")),
):
    if payload.vendor_id != vendor_id:
        raise HTTPException(status_code=400, detail="Vendor ID mismatch")
    if payload.maker_id != user.employee_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Maker mismatch")

    db = SessionLocal()
    vendor = db.query(VendorMaster).filter(VendorMaster.vendor_id == vendor_id).first()
    if not vendor:
        db.close()
        raise HTTPException(status_code=404, detail="Vendor not found")
    if vendor.status != "ACTIVE":
        db.close()
        raise HTTPException(status_code=400, detail="Only ACTIVE vendors can be deactivated")

    original_data = json.dumps(
        {"vendor_id": vendor.vendor_id, "vendor_name": vendor.vendor_name, "vendor_code": vendor.vendor_code, "status": vendor.status},
        default=str,
    )
    proposed_data = json.dumps({"action": "DEACTIVATE", "vendor_id": vendor_id}, default=str)

    approval = ApprovalRequest(
        entity_type="VENDOR_MASTER",
        entity_id=vendor.vendor_id,
        original_data=original_data,
        proposed_data=proposed_data,
        reason=payload.reason,
        comments_history=init_comment_history(payload.reason or "Deactivate vendor", payload.maker_id),
        maker_id=payload.maker_id,
        status="PENDING",
    )
    db.add(approval)
    db.flush()
    approval_id = approval.approval_id
    log_audit(db, "VENDOR_MASTER", vendor_id, "DEACTIVATE_REQUEST", None, payload.reason, user.employee_id)
    db.commit()
    db.close()
    return {"approval_id": approval_id}
