import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status

from backend.auth import AuthUser, require_roles
from backend.audit import log_audit
from backend.db import SessionLocal
from backend.models import ApprovalRequest, WaiverMaster
from backend.schemas import ApprovalDecision, WaiverRequest
from backend.utils_approval import append_comment_history, ensure_pending, enforce_checker_rules, init_comment_history
from backend.utils_month_lock import enforce_month_unlocked


router = APIRouter(prefix="/api/waivers", tags=["waivers"])


@router.post("/requests")
def request_waiver(payload: WaiverRequest, user: AuthUser = Depends(require_roles("MAKER", "ADMIN"))):
    if payload.maker_id != user.employee_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Maker mismatch")

    db = SessionLocal()
    enforce_month_unlocked(db, payload.waiver_from.strftime("%Y%m"))
    waiver = WaiverMaster(
        customer_id=payload.customer_id,
        waiver_type=payload.waiver_type,
        waiver_percentage=payload.waiver_percentage,
        waiver_cap_amount=payload.waiver_cap_amount,
        waiver_from=payload.waiver_from,
        waiver_to=payload.waiver_to,
        status="INACTIVE",
        created_by=payload.maker_id,
    )
    db.add(waiver)
    db.flush()

    approval = ApprovalRequest(
        entity_type="WAIVER",
        entity_id=waiver.waiver_id,
        original_data=json.dumps({}),
        proposed_data=json.dumps(payload.model_dump(), default=str),
        reason=payload.reason,
        comments_history=init_comment_history(payload.reason, payload.maker_id),
        maker_id=payload.maker_id,
        status="PENDING",
    )
    db.add(approval)
    log_audit(db, "WAIVER", waiver.waiver_id, "REQUEST", None, payload.model_dump(), user.employee_id)
    db.commit()
    db.close()
    return {"approval_id": approval.approval_id, "waiver_id": waiver.waiver_id}


@router.post("/requests/{approval_id}/approve")
def approve_waiver(
    approval_id: int,
    decision: ApprovalDecision,
    user: AuthUser = Depends(require_roles("CHECKER", "ADMIN")),
):
    db = SessionLocal()
    approval = db.query(ApprovalRequest).filter(ApprovalRequest.approval_id == approval_id).first()
    if not approval or approval.entity_type != "WAIVER":
        db.close()
        raise HTTPException(status_code=404, detail="Approval not found")
    try:
        ensure_pending(approval, "Approval")
    except HTTPException:
        db.close()
        raise
    enforce_checker_rules(user, approval.maker_id, decision.checker_id, decision.comment)

    waiver = db.query(WaiverMaster).filter(WaiverMaster.waiver_id == approval.entity_id).first()
    if not waiver:
        db.close()
        raise HTTPException(status_code=404, detail="Waiver not found")

    active = (
        db.query(WaiverMaster)
        .filter(WaiverMaster.customer_id == waiver.customer_id)
        .filter(WaiverMaster.waiver_id != waiver.waiver_id)
        .filter(WaiverMaster.status == "ACTIVE")
        .all()
    )
    for row in active:
        row.status = "INACTIVE"
        row.waiver_to = waiver.waiver_from - timedelta(days=1)

    waiver.status = "ACTIVE"
    waiver.approved_by = decision.checker_id
    waiver.approved_date = datetime.utcnow()
    approval.status = "APPROVED"
    approval.checker_id = decision.checker_id
    approval.checker_comment = decision.comment
    approval.comments_history = append_comment_history(
        approval.comments_history, "CHECKER", decision.checker_id, decision.comment
    )
    approval.approved_date = datetime.utcnow()

    log_audit(db, "WAIVER", waiver.waiver_id, "APPROVE", None, decision.comment, user.employee_id)
    db.commit()
    db.close()
    return {"status": "APPROVED"}


@router.post("/requests/{approval_id}/reject")
def reject_waiver(
    approval_id: int,
    decision: ApprovalDecision,
    user: AuthUser = Depends(require_roles("CHECKER", "ADMIN")),
):
    db = SessionLocal()
    approval = db.query(ApprovalRequest).filter(ApprovalRequest.approval_id == approval_id).first()
    if not approval or approval.entity_type != "WAIVER":
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

    log_audit(db, "WAIVER", approval.entity_id, "REJECT", None, decision.comment, user.employee_id)
    db.commit()
    db.close()
    return {"status": "REJECTED"}
