import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status

from backend.auth import AuthUser, require_roles
from backend.audit import log_audit
from backend.db import SessionLocal
from backend.models import ApprovalRequest, CanonicalTransaction, RemittanceEntry
from backend.schemas import ApprovalDecision, RemittanceApprovalRequest, RemittanceRequest, RemittanceStatusRequest
from backend.utils_approval import append_comment_history, enforce_checker_rules, ensure_pending, init_comment_history, safe_json_loads_clob
from backend.utils_month_lock import enforce_month_unlocked


router = APIRouter(prefix="/api/remittances", tags=["remittances"])


@router.get("")
def list_remittances(
    status_filter: str | None = None,
    user: AuthUser = Depends(require_roles("MAKER", "CHECKER", "ADMIN", "AUDITOR")),
):
    db = SessionLocal()
    query = db.query(RemittanceEntry)
    if status_filter:
        query = query.filter(RemittanceEntry.status == status_filter)
    rows = query.order_by(RemittanceEntry.remittance_id.desc()).all()
    result = [
        {
            "remittance_id": r.remittance_id,
            "canonical_id": r.canonical_id,
            "source": r.source,
            "status": r.status,
        }
        for r in rows
    ]
    log_audit(db, "REMITTANCE", "LIST", "VIEW", None, f"count={len(result)}", user.employee_id)
    db.commit()
    db.close()
    return result


@router.post("/initialize")
def initialize(payload: RemittanceRequest, user: AuthUser = Depends(require_roles("MAKER", "ADMIN"))):
    if payload.maker_id != user.employee_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Maker mismatch")

    db = SessionLocal()
    created = 0
    for canonical_id in payload.canonical_ids:
        existing = db.query(RemittanceEntry).filter(RemittanceEntry.canonical_id == canonical_id).first()
        if existing:
            continue
        txn = db.query(CanonicalTransaction).filter(CanonicalTransaction.canonical_id == canonical_id).first()
        if not txn:
            continue
        base_date = txn.remittance_date or txn.pickup_date
        if base_date:
            enforce_month_unlocked(db, base_date.strftime("%Y%m"))
        entry = RemittanceEntry(
            canonical_id=canonical_id,
            source=txn.source,
            status="UPLOADED",
            created_by=payload.maker_id,
        )
        db.add(entry)
        created += 1

    log_audit(db, "REMITTANCE", "INIT", "CREATE", None, f"count={created}", user.employee_id)
    db.commit()
    db.close()
    return {"created": created}


@router.post("/validate")
def validate_remittance(payload: RemittanceStatusRequest, user: AuthUser = Depends(require_roles("MAKER", "ADMIN"))):
    if payload.maker_id != user.employee_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Maker mismatch")
    db = SessionLocal()
    entry = db.query(RemittanceEntry).filter(RemittanceEntry.remittance_id == payload.remittance_id).first()
    if not entry:
        db.close()
        raise HTTPException(status_code=404, detail="Remittance not found")
    txn = db.query(CanonicalTransaction).filter(CanonicalTransaction.canonical_id == entry.canonical_id).first()
    if txn and (txn.remittance_date or txn.pickup_date):
        enforce_month_unlocked(db, (txn.remittance_date or txn.pickup_date).strftime("%Y%m"))
    entry.status = "VALIDATED"
    log_audit(db, "REMITTANCE", entry.remittance_id, "VALIDATE", None, None, user.employee_id)
    db.commit()
    db.close()
    return {"status": "VALIDATED"}


@router.post("/close")
def close_remittance(payload: RemittanceStatusRequest, user: AuthUser = Depends(require_roles("MAKER", "ADMIN"))):
    if payload.maker_id != user.employee_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Maker mismatch")
    db = SessionLocal()
    entry = db.query(RemittanceEntry).filter(RemittanceEntry.remittance_id == payload.remittance_id).first()
    if not entry:
        db.close()
        raise HTTPException(status_code=404, detail="Remittance not found")
    txn = db.query(CanonicalTransaction).filter(CanonicalTransaction.canonical_id == entry.canonical_id).first()
    if txn and (txn.remittance_date or txn.pickup_date):
        enforce_month_unlocked(db, (txn.remittance_date or txn.pickup_date).strftime("%Y%m"))
    entry.status = "CLOSED"
    entry.closed_date = datetime.utcnow()
    log_audit(db, "REMITTANCE", entry.remittance_id, "CLOSE", None, None, user.employee_id)
    db.commit()
    db.close()
    return {"status": "CLOSED"}


@router.post("/requests")
def request_remittance_action(
    payload: RemittanceApprovalRequest, user: AuthUser = Depends(require_roles("MAKER", "ADMIN"))
):
    if payload.maker_id != user.employee_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Maker mismatch")
    db = SessionLocal()
    entry = db.query(RemittanceEntry).filter(RemittanceEntry.remittance_id == payload.remittance_id).first()
    if not entry:
        db.close()
        raise HTTPException(status_code=404, detail="Remittance not found")
    txn = db.query(CanonicalTransaction).filter(CanonicalTransaction.canonical_id == entry.canonical_id).first()
    if txn and (txn.remittance_date or txn.pickup_date):
        enforce_month_unlocked(db, (txn.remittance_date or txn.pickup_date).strftime("%Y%m"))
    approval = ApprovalRequest(
        entity_type="REMITTANCE",
        entity_id=entry.remittance_id,
        original_data=json.dumps({"status": entry.status}),
        proposed_data=json.dumps(payload.model_dump(), default=str),
        reason=payload.reason,
        comments_history=init_comment_history(payload.reason, payload.maker_id),
        maker_id=payload.maker_id,
        status="PENDING",
    )
    db.add(approval)
    log_audit(
        db,
        "REMITTANCE",
        entry.remittance_id,
        "REQUEST",
        None,
        payload.model_dump(),
        user.employee_id,
    )
    db.commit()
    db.close()
    return {"approval_id": approval.approval_id}


@router.post("/requests/{approval_id}/approve")
def approve_remittance(
    approval_id: int,
    decision: ApprovalDecision,
    user: AuthUser = Depends(require_roles("CHECKER", "ADMIN")),
):
    db = SessionLocal()
    approval = db.query(ApprovalRequest).filter(ApprovalRequest.approval_id == approval_id).first()
    if not approval or approval.entity_type != "REMITTANCE":
        db.close()
        raise HTTPException(status_code=404, detail="Approval not found")
    try:
        ensure_pending(approval, "Approval")
    except HTTPException:
        db.close()
        raise

    enforce_checker_rules(user, approval.maker_id, decision.checker_id, decision.comment)
    entry = db.query(RemittanceEntry).filter(RemittanceEntry.remittance_id == approval.entity_id).first()
    if not entry:
        db.close()
        raise HTTPException(status_code=404, detail="Remittance not found")
    entry.status = "APPROVED"
    entry.approved_by = decision.checker_id
    entry.approved_date = datetime.utcnow()
    approval.status = "APPROVED"
    approval.checker_id = decision.checker_id
    approval.checker_comment = decision.comment
    approval.comments_history = append_comment_history(
        approval.comments_history, "CHECKER", decision.checker_id, decision.comment
    )
    approval.approved_date = datetime.utcnow()
    log_audit(db, "REMITTANCE", entry.remittance_id, "APPROVE", None, decision.comment, user.employee_id)
    db.commit()
    db.close()
    return {"status": "APPROVED"}


@router.post("/requests/{approval_id}/reject")
def reject_remittance(
    approval_id: int,
    decision: ApprovalDecision,
    user: AuthUser = Depends(require_roles("CHECKER", "ADMIN")),
):
    db = SessionLocal()
    approval = db.query(ApprovalRequest).filter(ApprovalRequest.approval_id == approval_id).first()
    if not approval or approval.entity_type != "REMITTANCE":
        db.close()
        raise HTTPException(status_code=404, detail="Approval not found")
    try:
        ensure_pending(approval, "Approval")
    except HTTPException:
        db.close()
        raise

    enforce_checker_rules(user, approval.maker_id, decision.checker_id, decision.comment)
    entry = db.query(RemittanceEntry).filter(RemittanceEntry.remittance_id == approval.entity_id).first()
    if not entry:
        db.close()
        raise HTTPException(status_code=404, detail="Remittance not found")
    entry.status = "REJECTED"
    proposed = safe_json_loads_clob(approval.proposed_data, raise_on_error=False)
    entry.rejection_reason = proposed.get("rejection_reason")
    entry.approved_by = decision.checker_id
    entry.approved_date = datetime.utcnow()
    approval.status = "REJECTED"
    approval.checker_id = decision.checker_id
    approval.checker_comment = decision.comment
    approval.comments_history = append_comment_history(
        approval.comments_history, "CHECKER", decision.checker_id, decision.comment
    )
    approval.approved_date = datetime.utcnow()
    log_audit(db, "REMITTANCE", entry.remittance_id, "REJECT", None, decision.comment, user.employee_id)
    db.commit()
    db.close()
    return {"status": "REJECTED"}
