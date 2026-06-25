import json
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import joinedload

from backend.auth import AuthUser, require_roles
from backend.audit import log_audit
from backend.db import SessionLocal
from backend.models import (
    ApprovalRequest,
    VendorFileFormatConfig,
    VendorFileFormatHeaderMapping,
    VendorMaster,
)
from backend.schemas import ApprovalDecision, VendorFileFormatRequest
from backend.utils_approval import append_comment_history, enforce_checker_rules, ensure_pending, init_comment_history
from backend.utils_datetime import to_utc_iso

router = APIRouter(prefix="/api/vendor-file-formats", tags=["vendor-file-formats"])

def _header_mapping_to_json(mappings):
    d = {m.mapping_key: m.source_column for m in mappings}
    return json.dumps(d) if d else "{}"

@router.get("")
def list_vendor_formats(
    vendor_id: Optional[int] = None,
    user: AuthUser = Depends(require_roles("MAKER", "CHECKER", "ADMIN", "AUDITOR")),
):
    db = SessionLocal()
    query = (
        db.query(VendorFileFormatConfig, VendorMaster)
        .options(joinedload(VendorFileFormatConfig.header_mappings))
        .join(VendorMaster, VendorMaster.vendor_id == VendorFileFormatConfig.vendor_id)
        .filter(VendorFileFormatConfig.status == "ACTIVE")
    )
    if vendor_id is not None:
        query = query.filter(VendorFileFormatConfig.vendor_id == vendor_id)
    rows = query.all()
    result = [
        {
            "format_id": c.format_id,
            "vendor_id": c.vendor_id,
            "vendor_name": v.vendor_name,
            "vendor_code": v.vendor_code,
            "format_name": c.format_name,
            "header_mapping_json": _header_mapping_to_json(c.header_mappings),
            "status": c.status,
            "effective_from": c.effective_from,
        }
        for c, v in rows
    ]
    log_audit(db, "VENDOR_FILE_FORMAT", "LIST", "VIEW", None, f"count={len(result)}", user.employee_id)
    db.commit()
    db.close()
    return result

@router.post("/requests")
def request_vendor_format(
    payload: VendorFileFormatRequest, user: AuthUser = Depends(require_roles("MAKER", "ADMIN"))
):
    if payload.maker_id != user.employee_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Maker mismatch")

    db = SessionLocal()
    config = VendorFileFormatConfig(
        vendor_id=payload.vendor_id,
        format_name=payload.format_name,
        status="INACTIVE",
        effective_from=payload.effective_from,
        created_by=payload.maker_id,
    )
    db.add(config)
    db.flush()

    mapping_data = json.loads(payload.header_mapping_json or "{}")
    for key, value in mapping_data.items():
        if value:
            db.add(
                VendorFileFormatHeaderMapping(
                    format_id=config.format_id,
                    mapping_key=str(key).strip(),
                    source_column=str(value).strip(),
                )
            )

    approval = ApprovalRequest(
        entity_type="VENDOR_FILE_FORMAT",
        entity_id=config.format_id,
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
    format_id = config.format_id
    log_audit(db, "VENDOR_FILE_FORMAT", config.format_id, "REQUEST", None, payload.model_dump(), user.employee_id)
    db.commit()
    db.close()
    return {"approval_id": approval_id, "format_id": format_id}

@router.get("/requests")
def list_vendor_format_requests(
    vendor_id: Optional[int] = None,
    user: AuthUser = Depends(require_roles("MAKER", "CHECKER", "ADMIN", "AUDITOR")),
):
    db = SessionLocal()
    query = (
        db.query(ApprovalRequest, VendorFileFormatConfig, VendorMaster)
        .join(
            VendorFileFormatConfig,
            VendorFileFormatConfig.format_id == ApprovalRequest.entity_id,
        )
        .join(VendorMaster, VendorMaster.vendor_id == VendorFileFormatConfig.vendor_id)
        .filter(ApprovalRequest.entity_type == "VENDOR_FILE_FORMAT")
    )
    if vendor_id is not None:
        query = query.filter(VendorFileFormatConfig.vendor_id == vendor_id)
    rows = query.order_by(ApprovalRequest.created_date.desc()).all()
    result = [
        {
            "approval_id": a.approval_id,
            "format_id": c.format_id,
            "vendor_id": c.vendor_id,
            "vendor_name": v.vendor_name,
            "vendor_code": v.vendor_code,
            "format_name": c.format_name,
            "status": a.status,
            "created_date": to_utc_iso(a.created_date),
            "checker_comment": a.checker_comment,
            "reason": a.reason,
        }
        for a, c, v in rows
    ]
    log_audit(db, "VENDOR_FILE_FORMAT", "REQUEST_LIST", "VIEW", None, f"count={len(result)}", user.employee_id)
    db.commit()
    db.close()
    return result

@router.post("/requests/{approval_id}/approve")
def approve_vendor_format(
    approval_id: int,
    decision: ApprovalDecision,
    user: AuthUser = Depends(require_roles("CHECKER", "ADMIN")),
):
    db = SessionLocal()
    approval = db.query(ApprovalRequest).filter(ApprovalRequest.approval_id == approval_id).first()
    if not approval or approval.entity_type != "VENDOR_FILE_FORMAT":
        db.close()
        raise HTTPException(status_code=404, detail="Approval not found")
    try:
        ensure_pending(approval, "Approval")
    except HTTPException:
        db.close()
        raise

    enforce_checker_rules(user, approval.maker_id, decision.checker_id, decision.comment)

    config = db.query(VendorFileFormatConfig).filter(VendorFileFormatConfig.format_id == approval.entity_id).first()
    if not config:
        db.close()
        raise HTTPException(status_code=404, detail="Config not found")

    active = (
        db.query(VendorFileFormatConfig)
        .filter(VendorFileFormatConfig.vendor_id == config.vendor_id)
        .filter(VendorFileFormatConfig.format_id != config.format_id)
        .filter(VendorFileFormatConfig.status == "ACTIVE")
        .all()
    )
    for row in active:
        row.status = "INACTIVE"
        row.effective_to = config.effective_from - timedelta(days=1)

    config.status = "ACTIVE"
    config.approved_by = decision.checker_id
    config.approved_date = datetime.utcnow()
    approval.status = "APPROVED"
    approval.checker_id = decision.checker_id
    approval.checker_comment = decision.comment
    approval.comments_history = append_comment_history(
        approval.comments_history, "CHECKER", decision.checker_id, decision.comment
    )
    approval.approved_date = datetime.utcnow()

    log_audit(db, "VENDOR_FILE_FORMAT", config.format_id, "APPROVE", None, decision.comment, user.employee_id)
    db.commit()
    db.close()
    return {"status": "APPROVED"}

@router.delete("/{format_id}")
def delete_vendor_format(
    format_id: int,
    user: AuthUser = Depends(require_roles("MAKER", "ADMIN")),
):
    db = SessionLocal()
    config = (
        db.query(VendorFileFormatConfig)
        .filter(VendorFileFormatConfig.format_id == format_id)
        .first()
    )
    if not config:
        db.close()
        raise HTTPException(status_code=404, detail="Vendor file format not found")
    if config.status != "ACTIVE":
        db.close()
        raise HTTPException(status_code=400, detail="Only ACTIVE formats can be deleted")

    config.status = "INACTIVE"
    config.effective_to = datetime.utcnow().date()
    log_audit(db, "VENDOR_FILE_FORMAT", format_id, "DELETE", None, "Deactivated by user", user.employee_id)
    db.commit()
    db.close()
    return {"status": "DELETED", "format_id": format_id}

@router.post("/requests/{approval_id}/reject")
def reject_vendor_format(
    approval_id: int,
    decision: ApprovalDecision,
    user: AuthUser = Depends(require_roles("CHECKER", "ADMIN")),
):
    db = SessionLocal()
    approval = db.query(ApprovalRequest).filter(ApprovalRequest.approval_id == approval_id).first()
    if not approval or approval.entity_type != "VENDOR_FILE_FORMAT":
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

    log_audit(db, "VENDOR_FILE_FORMAT", approval.entity_id, "REJECT", None, decision.comment, user.employee_id)
    db.commit()
    db.close()
    return {"status": "REJECTED"}
