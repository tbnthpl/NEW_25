
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status

from backend.auth import AuthUser, require_roles
from backend.audit import log_audit
from backend.db import SessionLocal
from backend.models import ApprovalRequest, VendorBeatSlab, VendorMaster
from backend.schemas import ApprovalDecision, VendorBeatSlabEditRequest, VendorBeatSlabRequest
from backend.utils_approval import append_comment_history, enforce_checker_rules, ensure_pending, init_comment_history

router = APIRouter(prefix="/api/vendor-beat-slabs", tags=["vendor-beat-slabs"])

@router.get("")
def list_vendor_beat_slabs(
    vendor_id: int | None = None,
    user: AuthUser = Depends(require_roles("MAKER", "CHECKER", "ADMIN", "AUDITOR")),
):
    db = SessionLocal()
    q = db.query(VendorBeatSlab, VendorMaster.vendor_name, VendorMaster.vendor_code).outerjoin(
        VendorMaster, VendorBeatSlab.vendor_id == VendorMaster.vendor_id
    )
    if vendor_id:
        q = q.filter(VendorBeatSlab.vendor_id == vendor_id)
    rows = q.filter(VendorBeatSlab.status == "ACTIVE").order_by(
        VendorBeatSlab.vendor_id, VendorBeatSlab.amount_from
    ).all()
    result = [
        {
            "slab_id": s.slab_id,
            "vendor_id": s.vendor_id,
            "vendor_name": name or "",
            "vendor_code": code or "",
            "amount_from": float(s.amount_from or 0),
            "amount_to": float(s.amount_to or 0),
            "charge_amount": float(s.charge_amount or 0),
            "slab_label": s.slab_label or "",
            "status": s.status,
            "effective_from": s.effective_from.isoformat() if s.effective_from else None,
        }
        for s, name, code in rows
    ]
    db.close()
    return result

@router.post("/requests")
def request_vendor_beat_slab(
    payload: VendorBeatSlabRequest,
    user: AuthUser = Depends(require_roles("MAKER", "ADMIN")),
):
    if payload.maker_id != user.employee_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Maker mismatch")

    db = SessionLocal()
    slab = VendorBeatSlab(
        vendor_id=payload.vendor_id,
        amount_from=payload.amount_from,
        amount_to=payload.amount_to,
        charge_amount=payload.charge_amount,
        slab_label=payload.slab_label or "",
        status="INACTIVE",
        effective_from=payload.effective_from,
        created_by=payload.maker_id,
    )
    db.add(slab)
    db.flush()

    approval = ApprovalRequest(
        entity_type="VENDOR_BEAT_SLAB",
        entity_id=slab.slab_id,
        original_data=json.dumps({}),
        proposed_data=json.dumps(payload.model_dump(), default=str),
        reason=payload.reason,
        comments_history=init_comment_history(payload.reason or "", payload.maker_id),
        maker_id=payload.maker_id,
        status="PENDING",
    )
    db.add(approval)
    db.flush()
    approval_id = approval.approval_id
    slab_id_val = slab.slab_id
    log_audit(db, "VENDOR_BEAT_SLAB", slab.slab_id, "REQUEST", None, payload.model_dump(), user.employee_id)
    db.commit()
    db.close()
    return {"approval_id": approval_id, "slab_id": slab_id_val}

@router.post("/requests/edit")
def request_vendor_beat_slab_edit(
    payload: VendorBeatSlabEditRequest,
    user: AuthUser = Depends(require_roles("MAKER", "ADMIN")),
):
    if payload.maker_id != user.employee_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Maker mismatch")

    db = SessionLocal()
    slab = db.query(VendorBeatSlab).filter(VendorBeatSlab.slab_id == payload.slab_id).first()
    if not slab or slab.status != "ACTIVE":
        db.close()
        raise HTTPException(status_code=404, detail="Slab not found or not active")

    proposed = payload.model_dump()
    proposed["action"] = "EDIT"
    approval = ApprovalRequest(
        entity_type="VENDOR_BEAT_SLAB",
        entity_id=slab.slab_id,
        original_data=json.dumps(
            {
                "amount_from": float(slab.amount_from or 0),
                "amount_to": float(slab.amount_to or 0),
                "charge_amount": float(slab.charge_amount or 0),
                "slab_label": slab.slab_label or "",
                "effective_from": slab.effective_from.isoformat() if slab.effective_from else None,
            }
        ),
        proposed_data=json.dumps(proposed, default=str),
        reason=payload.reason,
        comments_history=init_comment_history(payload.reason or "", payload.maker_id),
        maker_id=payload.maker_id,
        status="PENDING",
    )
    db.add(approval)
    db.flush()
    approval_id = approval.approval_id
    slab_id_val = slab.slab_id
    log_audit(db, "VENDOR_BEAT_SLAB", slab.slab_id, "EDIT_REQUEST", None, proposed, user.employee_id)
    db.commit()
    db.close()
    return {"approval_id": approval_id, "slab_id": slab_id_val}

@router.post("/requests/{approval_id}/approve")
def approve_vendor_beat_slab(
    approval_id: int,
    decision: ApprovalDecision,
    user: AuthUser = Depends(require_roles("CHECKER", "ADMIN")),
):
    db = SessionLocal()
    approval = db.query(ApprovalRequest).filter(ApprovalRequest.approval_id == approval_id).first()
    if not approval or approval.entity_type != "VENDOR_BEAT_SLAB":
        db.close()
        raise HTTPException(status_code=404, detail="Approval not found")
    try:
        ensure_pending(approval, "Approval")
    except HTTPException:
        db.close()
        raise

    enforce_checker_rules(user, approval.maker_id, decision.checker_id, decision.comment)

    slab = db.query(VendorBeatSlab).filter(VendorBeatSlab.slab_id == approval.entity_id).first()
    if not slab:
        db.close()
        raise HTTPException(status_code=404, detail="Slab not found")

    proposed = json.loads(approval.proposed_data) if approval.proposed_data else {}
    if proposed.get("action") == "EDIT":
        slab.amount_from = proposed.get("amount_from", slab.amount_from)
        slab.amount_to = proposed.get("amount_to", slab.amount_to)
        slab.charge_amount = proposed.get("charge_amount", slab.charge_amount)
        slab.slab_label = proposed.get("slab_label") or ""
        if proposed.get("effective_from"):
            slab.effective_from = datetime.strptime(str(proposed["effective_from"])[:10], "%Y-%m-%d").date()
    else:
        slab.status = "ACTIVE"
    slab.approved_by = decision.checker_id
    slab.approved_date = datetime.utcnow()
    approval.status = "APPROVED"
    approval.checker_id = decision.checker_id
    approval.checker_comment = decision.comment
    approval.comments_history = append_comment_history(
        approval.comments_history, "CHECKER", decision.checker_id, decision.comment
    )
    approval.approved_date = datetime.utcnow()

    log_audit(db, "VENDOR_BEAT_SLAB", slab.slab_id, "APPROVE", None, decision.comment, user.employee_id)
    db.commit()
    db.close()
    return {"status": "APPROVED"}

@router.post("/requests/{approval_id}/reject")
def reject_vendor_beat_slab(
    approval_id: int,
    decision: ApprovalDecision,
    user: AuthUser = Depends(require_roles("CHECKER", "ADMIN")),
):
    db = SessionLocal()
    approval = db.query(ApprovalRequest).filter(ApprovalRequest.approval_id == approval_id).first()
    if not approval or approval.entity_type != "VENDOR_BEAT_SLAB":
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

    log_audit(db, "VENDOR_BEAT_SLAB", approval.entity_id, "REJECT", None, decision.comment, user.employee_id)
    db.commit()
    db.close()
    return {"status": "REJECTED"}

@router.delete("/{slab_id}")
def delete_vendor_beat_slab(
    slab_id: int,
    user: AuthUser = Depends(require_roles("ADMIN")),
):
    db = SessionLocal()
    try:
        slab = db.query(VendorBeatSlab).filter(VendorBeatSlab.slab_id == slab_id).first()
        if not slab:
            raise HTTPException(status_code=404, detail="Slab not found")
        old_data = {
            "slab_id": slab.slab_id,
            "vendor_id": slab.vendor_id,
            "amount_from": float(slab.amount_from) if slab.amount_from is not None else None,
            "amount_to": float(slab.amount_to) if slab.amount_to is not None else None,
            "charge_amount": float(slab.charge_amount) if slab.charge_amount is not None else None,
            "status": slab.status,
        }
        slab.status = "INACTIVE"
        log_audit(
            db,
            "VENDOR_BEAT_SLAB",
            slab.slab_id,
            "DELETE",
            old_data,
            {"status": "INACTIVE"},
            user.employee_id,
        )
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return {"status": "ok"}
