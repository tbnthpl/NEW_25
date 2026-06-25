import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status

from backend.auth import AuthUser, require_roles
from backend.audit import log_audit
from backend.db import SessionLocal
from backend.models import (
    ApprovalRequest,
    BankStoreMaster,
    VendorMaster,
    VendorStoreMappingMaster,
)
from backend.schemas import ApprovalDecision, CommentRequest, ResubmitRequest
from backend.utils_approval import append_comment_history
from backend.utils_datetime import to_utc_iso
from backend.routes_corrections import enrich_recon_correction_proposed_data

router = APIRouter(prefix="/api/approvals", tags=["approvals"])

def _coerce_date(value):
    from datetime import date as _date

    if value is None or value == "":
        return None
    if isinstance(value, _date):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None

def _coerce_num(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

_EDITABLE_ENTITY_FIELDS = {
    "VENDOR_MASTER": {
        "vendor_name": "str",
        "vendor_code": "str",
        "effective_from": "date",
    },
    "BANK_STORE_MASTER": {
        "bank_store_code": "str",
        "store_name": "str",
        "customer_id": "str",
        "customer_name": "str",
        "account_no": "str",
        "sol_id": "str",
        "pickup_type": "str",
        "daily_pickup_limit": "num",
        "fixed_charge": "num",
        "vendor_charge": "num",
        "call_included_pickups": "num",
        "call_monthly_bank_charge": "num",
        "call_additional_bank_per_pickup": "num",
        "call_vendor_pay_per_pickup": "num",
        "waiver_percentage": "num",
        "waiver_cap_amount": "num",
        "waiver_cap_from": "date",
        "waiver_cap_to": "date",
        "effective_from": "date",
    },
    "STORE_MAPPING": {
        "vendor_store_code": "str",
        "bank_store_code": "str",
        "customer_id": "str",
        "customer_name": "str",
        "account_no": "str",
        "effective_from": "date",
    },
}

_ENTITY_ROW_LOOKUP = {
    "VENDOR_MASTER": (VendorMaster, "vendor_id"),
    "BANK_STORE_MASTER": (BankStoreMaster, "store_id"),
    "STORE_MAPPING": (VendorStoreMappingMaster, "mapping_id"),
}

def _sync_entity_row_on_resubmit(db, approval, merged):
    action = str((merged or {}).get("action") or "").upper()
    if action in ("UPDATE", "EDIT", "DEACTIVATE"):
        return

    spec = _EDITABLE_ENTITY_FIELDS.get(approval.entity_type)
    lookup = _ENTITY_ROW_LOOKUP.get(approval.entity_type)
    if not spec or not lookup or approval.entity_id is None:
        return

    model, pk = lookup
    row = db.query(model).filter(getattr(model, pk) == approval.entity_id).first()
    if not row:
        return
    if str(getattr(row, "status", "") or "").upper() == "ACTIVE":
        return

    for key, kind in spec.items():
        if key not in merged:
            continue
        raw = merged.get(key)
        if kind == "date":
            setattr(row, key, _coerce_date(raw))
        elif kind == "num":
            setattr(row, key, _coerce_num(raw))
        else:
            val = None if raw is None or str(raw).strip() == "" else str(raw).strip()
            if key == "pickup_type" and val:
                val = val.upper()
                if val not in ("BEAT", "CALL"):
                    val = "BEAT"
            setattr(row, key, val)

@router.get("/pending/count")
def pending_count(user: AuthUser = Depends(require_roles("CHECKER", "ADMIN"))):
    db = SessionLocal()
    try:
        count = db.query(ApprovalRequest).filter(ApprovalRequest.status == "PENDING").count()
        return {"count": count}
    finally:
        db.close()

@router.get("/pending")
def list_pending(user: AuthUser = Depends(require_roles("MAKER", "CHECKER", "ADMIN"))):
    db = SessionLocal()
    try:
        approvals = (
            db.query(ApprovalRequest)
            .filter(ApprovalRequest.status == "PENDING")
            .order_by(ApprovalRequest.created_date.desc())
            .all()
        )
        payload = [
            {
                "approval_id": item.approval_id,
                "entity_type": item.entity_type,
                "entity_id": item.entity_id,
                "maker_id": item.maker_id,
                "status": item.status,
                "created_date": to_utc_iso(item.created_date),
                "reason": item.reason,
                "checker_comment": item.checker_comment,
                "comments_history": item.comments_history,
                "original_data": item.original_data,
                "proposed_data": enrich_recon_correction_proposed_data(
                    db, item.proposed_data, item.entity_id
                )
                if item.entity_type == "RECONCILIATION_CORRECTION"
                else item.proposed_data,
            }
            for item in approvals
        ]
        log_audit(
            db,
            entity_type="APPROVAL",
            entity_id="LIST",
            action="VIEW",
            old_data=None,
            new_data=f"count={len(payload)}",
            changed_by=user.employee_id,
        )
        db.commit()
        return payload
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

@router.get("/{approval_id}/status")
def approval_status(
    approval_id: int,
    user: AuthUser = Depends(require_roles("MAKER", "CHECKER", "ADMIN", "AUDITOR")),
):
    db = SessionLocal()
    try:
        item = (
            db.query(ApprovalRequest)
            .filter(ApprovalRequest.approval_id == approval_id)
            .first()
        )
        if not item:
            raise HTTPException(status_code=404, detail=f"No request found with ID {approval_id}")
        return {
            "approval_id": item.approval_id,
            "entity_type": item.entity_type,
            "status": item.status,
            "maker_id": item.maker_id,
            "checker_id": item.checker_id,
            "reason": item.reason,
            "checker_comment": item.checker_comment,
            "comments_history": item.comments_history,
            "created_date": to_utc_iso(item.created_date),
            "approved_date": to_utc_iso(item.approved_date),
        }
    finally:
        db.close()

@router.get("/clarifications/count")
def clarifications_count(user: AuthUser = Depends(require_roles("MAKER", "ADMIN"))):
    db = SessionLocal()
    try:
        count = (
            db.query(ApprovalRequest)
            .filter(ApprovalRequest.status == "CLARIFICATION")
            .filter(ApprovalRequest.maker_id == user.employee_id)
            .count()
        )
        return {"count": count}
    finally:
        db.close()

@router.get("/clarifications")
def list_clarifications(user: AuthUser = Depends(require_roles("MAKER", "CHECKER", "ADMIN"))):
    db = SessionLocal()
    try:
        query = (
            db.query(ApprovalRequest)
            .filter(ApprovalRequest.status == "CLARIFICATION")
        )
        if (user.role or "").upper() == "MAKER":
            query = query.filter(ApprovalRequest.maker_id == user.employee_id)
        approvals = query.order_by(ApprovalRequest.created_date.desc()).all()
        payload = [
            {
                "approval_id": item.approval_id,
                "entity_type": item.entity_type,
                "maker_id": item.maker_id,
                "status": item.status,
                "created_date": to_utc_iso(item.created_date),
                "reason": item.reason,
                "checker_comment": item.checker_comment,
                "comments_history": item.comments_history,
                "proposed_data": item.proposed_data,
                "original_data": item.original_data,
            }
            for item in approvals
        ]
        log_audit(
            db,
            entity_type="APPROVAL",
            entity_id="CLARIFICATIONS",
            action="VIEW",
            old_data=None,
            new_data=f"count={len(payload)}",
            changed_by=user.employee_id,
        )
        db.commit()
        return payload
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

@router.post("/{approval_id}/clarify")
def request_clarification(
    approval_id: int,
    decision: ApprovalDecision,
    user: AuthUser = Depends(require_roles("CHECKER", "ADMIN")),
):
    db = SessionLocal()
    try:
        approval = db.query(ApprovalRequest).filter(ApprovalRequest.approval_id == approval_id).first()
        if not approval:
            raise HTTPException(status_code=404, detail="Approval not found")
        if approval.status != "PENDING":
            raise HTTPException(status_code=400, detail="Only pending approvals can be clarified")

        approval.status = "CLARIFICATION"
        approval.checker_id = decision.checker_id
        approval.checker_comment = decision.comment
        approval.comments_history = append_comment_history(
            approval.comments_history, "CHECKER", decision.checker_id, decision.comment
        )
        approval.approved_date = datetime.utcnow()

        log_audit(db, "APPROVAL", approval_id, "CLARIFY", None, decision.comment, user.employee_id)
        db.commit()
        return {"status": "CLARIFICATION"}
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

@router.post("/{approval_id}/resubmit")
def resubmit_approval(
    approval_id: int,
    payload: ResubmitRequest,
    user: AuthUser = Depends(require_roles("MAKER", "ADMIN")),
):
    db = SessionLocal()
    try:
        approval = db.query(ApprovalRequest).filter(ApprovalRequest.approval_id == approval_id).first()
        if not approval:
            raise HTTPException(status_code=404, detail="Approval not found")
        if approval.maker_id != user.employee_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the maker who created this request can edit and resubmit it",
            )
        if approval.status != "CLARIFICATION":
            raise HTTPException(status_code=400, detail="Only clarification requests can be resubmitted")
        if not payload.comment or not payload.comment.strip():
            raise HTTPException(status_code=400, detail="Comment required")

        old_data = approval.proposed_data
        if payload.proposed_data is not None:
            try:
                current = json.loads(approval.proposed_data) if approval.proposed_data else {}
            except (TypeError, ValueError):
                current = {}
            if not isinstance(current, dict):
                current = {}
            merged = {**current, **payload.proposed_data}
            approval.proposed_data = json.dumps(merged)
            _sync_entity_row_on_resubmit(db, approval, merged)

        approval.status = "PENDING"
        approval.checker_id = None
        approval.checker_comment = None
        approval.comments_history = append_comment_history(
            approval.comments_history, "MAKER", user.employee_id, payload.comment
        )
        approval.approved_date = None

        log_audit(
            db,
            "APPROVAL",
            approval_id,
            "RESUBMIT",
            old_data if payload.proposed_data is not None else None,
            approval.proposed_data if payload.proposed_data is not None else None,
            user.employee_id,
        )
        db.commit()
        return {"status": "PENDING"}
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
