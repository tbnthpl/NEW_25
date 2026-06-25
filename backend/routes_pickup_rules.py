import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status

from backend.auth import AuthUser, require_roles
from backend.audit import log_audit
from backend.db import SessionLocal
from backend.models import ApprovalRequest, PickupRulesMaster
from backend.schemas import ApprovalDecision, PickupRuleRequest
from backend.utils_approval import append_comment_history, enforce_checker_rules, ensure_pending, init_comment_history
from backend.utils_month_lock import enforce_month_unlocked


router = APIRouter(prefix="/api/pickup-rules", tags=["pickup-rules"])


@router.get("")
def list_rules(user: AuthUser = Depends(require_roles("MAKER", "CHECKER", "ADMIN", "AUDITOR"))):
    db = SessionLocal()
    rules = db.query(PickupRulesMaster).filter(PickupRulesMaster.status == "ACTIVE").all()
    result = [
        {
            "rule_id": r.rule_id,
            "pickup_type": r.pickup_type,
            "free_limit": float(r.free_limit) if r.free_limit is not None else None,
            "status": r.status,
            "effective_from": r.effective_from,
        }
        for r in rules
    ]
    log_audit(db, "PICKUP_RULE", "LIST", "VIEW", None, f"count={len(result)}", user.employee_id)
    db.commit()
    db.close()
    return result


@router.post("/requests")
def request_rule(payload: PickupRuleRequest, user: AuthUser = Depends(require_roles("MAKER", "ADMIN"))):
    if payload.maker_id != user.employee_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Maker mismatch")

    db = SessionLocal()
    rule = PickupRulesMaster(
        pickup_type=payload.pickup_type,
        free_limit=payload.free_limit,
        status="INACTIVE",
        effective_from=payload.effective_from,
        created_by=payload.maker_id,
    )
    db.add(rule)
    db.flush()

    approval = ApprovalRequest(
        entity_type="PICKUP_RULE",
        entity_id=rule.rule_id,
        original_data=json.dumps({}),
        proposed_data=json.dumps(payload.model_dump(), default=str),
        reason=payload.reason,
        comments_history=init_comment_history(payload.reason, payload.maker_id),
        maker_id=payload.maker_id,
        status="PENDING",
    )
    db.add(approval)
    db.flush()
    log_audit(db, "PICKUP_RULE", rule.rule_id, "REQUEST", None, payload.model_dump(), user.employee_id)
    approval_id = approval.approval_id
    rule_id = rule.rule_id
    db.commit()
    db.close()
    return {"approval_id": approval_id, "rule_id": rule_id}


@router.post("/requests/{approval_id}/approve")
def approve_rule(
    approval_id: int,
    decision: ApprovalDecision,
    user: AuthUser = Depends(require_roles("CHECKER", "ADMIN")),
):
    db = SessionLocal()
    approval = db.query(ApprovalRequest).filter(ApprovalRequest.approval_id == approval_id).first()
    if not approval or approval.entity_type != "PICKUP_RULE":
        db.close()
        raise HTTPException(status_code=404, detail="Approval not found")
    try:
        ensure_pending(approval, "Approval")
    except HTTPException:
        db.close()
        raise

    enforce_checker_rules(user, approval.maker_id, decision.checker_id, decision.comment)

    rule = db.query(PickupRulesMaster).filter(PickupRulesMaster.rule_id == approval.entity_id).first()
    if not rule:
        db.close()
        raise HTTPException(status_code=404, detail="Rule not found")

    active = (
        db.query(PickupRulesMaster)
        .filter(PickupRulesMaster.pickup_type == rule.pickup_type)
        .filter(PickupRulesMaster.rule_id != rule.rule_id)
        .filter(PickupRulesMaster.status == "ACTIVE")
        .all()
    )
    for row in active:
        row.status = "INACTIVE"
        row.effective_to = rule.effective_from - timedelta(days=1)

    rule.status = "ACTIVE"
    rule.approved_by = decision.checker_id
    rule.approved_date = datetime.utcnow()
    approval.status = "APPROVED"
    approval.checker_id = decision.checker_id
    approval.checker_comment = decision.comment
    approval.comments_history = append_comment_history(
        approval.comments_history, "CHECKER", decision.checker_id, decision.comment
    )
    approval.approved_date = datetime.utcnow()

    log_audit(db, "PICKUP_RULE", rule.rule_id, "APPROVE", None, decision.comment, user.employee_id)
    db.commit()
    db.close()
    return {"status": "APPROVED"}


@router.post("/requests/{approval_id}/reject")
def reject_rule(
    approval_id: int,
    decision: ApprovalDecision,
    user: AuthUser = Depends(require_roles("CHECKER", "ADMIN")),
):
    db = SessionLocal()
    approval = db.query(ApprovalRequest).filter(ApprovalRequest.approval_id == approval_id).first()
    if not approval or approval.entity_type != "PICKUP_RULE":
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

    log_audit(db, "PICKUP_RULE", approval.entity_id, "REJECT", None, decision.comment, user.employee_id)
    db.commit()
    db.close()
    return {"status": "REJECTED"}
