import json
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from backend.auth import AuthUser, require_roles
from backend.audit import log_audit
from backend.db import SessionLocal
from backend.models import ApprovalRequest, ChargeConfigurationMaster
from backend.schemas import ApprovalDecision, ChargeConfigRequest, CustomerExcessChargePairRequest
from backend.utils_approval import append_comment_history, enforce_checker_rules, ensure_pending, init_comment_history

logger = logging.getLogger(__name__)

THRESHOLD_CODE = "ENHANCEMENT_THRESHOLD_AMOUNT"
CHARGE_PER_STEP_CODE = "ENHANCEMENT_CHARGE_AMOUNT"

def _integrity_detail(exc: IntegrityError) -> str:
    orig = getattr(exc, "orig", None)
    raw = str(orig) if orig else str(exc)
    logger.warning("IntegrityError in charge config: %s", raw)
    if "ORA-00001" in raw or "unique constraint" in raw.lower():
        return (
            "This change conflicts with an existing record (duplicate value). "
            "If this is a charge configuration with the same code, ask the DBA to "
            "run backend/db/migrations/drop_charge_config_code_unique.sql, then retry."
        )
    if "ORA-02292" in raw or "child record found" in raw.lower():
        return "This record cannot be changed because other records reference it."
    if "ORA-02291" in raw or "parent key not found" in raw.lower():
        return "A referenced record could not be found. Refresh and try again."
    return "The database rejected this change due to a constraint violation."

router = APIRouter(prefix="/api/charge-configs", tags=["charge-configs"])

@router.get("")
def list_charge_configs(user: AuthUser = Depends(require_roles("MAKER", "CHECKER", "ADMIN", "AUDITOR"))):
    db = SessionLocal()
    configs = db.query(ChargeConfigurationMaster).filter(ChargeConfigurationMaster.status == "ACTIVE").all()
    result = [
        {
            "config_code": (c.config_code or "").strip(),
            "config_name": c.config_name,
            "value_number": float(c.value_number) if c.value_number is not None else None,
            "status": c.status,
            "effective_from": c.effective_from.isoformat() if c.effective_from else None,
            "effective_to": c.effective_to.isoformat() if c.effective_to else None,
        }
        for c in configs
    ]
    log_audit(db, "CHARGE_CONFIG", "LIST", "VIEW", None, f"count={len(result)}", user.employee_id)
    db.commit()
    db.close()
    return result

def _serialize_excess_row(c: ChargeConfigurationMaster, row_status: str) -> dict:
    return {
        "config_code": (c.config_code or "").strip(),
        "value_number": float(c.value_number) if c.value_number is not None else None,
        "effective_from": c.effective_from.isoformat() if c.effective_from else None,
        "effective_to": c.effective_to.isoformat() if c.effective_to else None,
        "row_status": row_status,
    }

@router.get("/customer-excess-display")
def customer_excess_display(
    user: AuthUser = Depends(require_roles("MAKER", "CHECKER", "ADMIN", "AUDITOR")),
):
    db = SessionLocal()

    def trim_eq(col, code: str):
        return func.trim(col) == code

    def active_for(code: str):
        return (
            db.query(ChargeConfigurationMaster)
            .filter(trim_eq(ChargeConfigurationMaster.config_code, code))
            .filter(ChargeConfigurationMaster.status == "ACTIVE")
            .order_by(ChargeConfigurationMaster.effective_from.desc())
            .first()
        )

    def pending_for(code: str):
        return (
            db.query(ChargeConfigurationMaster)
            .join(ApprovalRequest, ApprovalRequest.entity_id == ChargeConfigurationMaster.config_id)
            .filter(ApprovalRequest.entity_type == "CHARGE_CONFIG")
            .filter(ApprovalRequest.status == "PENDING")
            .filter(trim_eq(ChargeConfigurationMaster.config_code, code))
            .filter(ChargeConfigurationMaster.status == "INACTIVE")
            .order_by(ApprovalRequest.created_date.desc())
            .first()
        )

    out: dict = {
        "threshold": None,
        "charge_per_step": None,
        "defaults": {"threshold_amount": 50000.0, "charge_per_step": 60.0},
    }
    for key, code in [("threshold", THRESHOLD_CODE), ("charge_per_step", CHARGE_PER_STEP_CODE)]:
        active = active_for(code)
        if active:
            out[key] = _serialize_excess_row(active, "ACTIVE")
        else:
            pend = pending_for(code)
            if pend:
                out[key] = _serialize_excess_row(pend, "PENDING")

    log_audit(db, "CHARGE_CONFIG", "EXCESS", "VIEW", None, "customer-excess-display", user.employee_id)
    db.commit()
    db.close()
    return out

@router.post("/requests")
def request_charge_config(payload: ChargeConfigRequest, user: AuthUser = Depends(require_roles("MAKER", "ADMIN"))):
    if payload.maker_id != user.employee_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Maker mismatch")

    db = SessionLocal()
    try:
        config = ChargeConfigurationMaster(
            config_code=payload.config_code,
            config_name=payload.config_name,
            value_number=payload.value_number,
            value_text=payload.value_text,
            status="INACTIVE",
            effective_from=payload.effective_from,
            created_by=payload.maker_id,
        )
        db.add(config)
        db.flush()

        approval = ApprovalRequest(
            entity_type="CHARGE_CONFIG",
            entity_id=config.config_id,
            original_data=json.dumps({}),
            proposed_data=json.dumps(payload.model_dump(), default=str),
            reason=payload.reason,
            comments_history=init_comment_history(payload.reason, payload.maker_id),
            maker_id=payload.maker_id,
            status="PENDING",
        )
        db.add(approval)
        log_audit(db, "CHARGE_CONFIG", config.config_id, "REQUEST", None, payload.model_dump(), user.employee_id)
        db.commit()
        return {"approval_id": approval.approval_id, "config_id": config.config_id}
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_integrity_detail(e)) from e
    finally:
        db.close()

@router.post("/requests/customer-excess-pair")
def request_customer_excess_pair(
    payload: CustomerExcessChargePairRequest,
    user: AuthUser = Depends(require_roles("MAKER", "ADMIN")),
):
    if payload.maker_id != user.employee_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Maker mismatch")

    specs = [
        (THRESHOLD_CODE, "Customer excess - amount per step (Rs)", payload.excess_step_amount),
        (CHARGE_PER_STEP_CODE, "Customer excess - charge per step (Rs)", payload.charge_per_step),
    ]
    db = SessionLocal()
    results = []
    try:
        for code, name, value in specs:
            row_payload = ChargeConfigRequest(
                config_code=code,
                config_name=name,
                value_number=value,
                value_text=None,
                effective_from=payload.effective_from,
                status="ACTIVE",
                maker_id=payload.maker_id,
                reason=payload.reason,
            )
            config = ChargeConfigurationMaster(
                config_code=code,
                config_name=name,
                value_number=value,
                value_text=None,
                status="INACTIVE",
                effective_from=payload.effective_from,
                created_by=payload.maker_id,
            )
            db.add(config)
            db.flush()
            approval = ApprovalRequest(
                entity_type="CHARGE_CONFIG",
                entity_id=config.config_id,
                original_data=json.dumps({}),
                proposed_data=json.dumps(row_payload.model_dump(), default=str),
                reason=payload.reason,
                comments_history=init_comment_history(payload.reason, payload.maker_id),
                maker_id=payload.maker_id,
                status="PENDING",
            )
            db.add(approval)
            db.flush()
            results.append({"approval_id": approval.approval_id, "config_id": config.config_id, "config_code": code})

        log_audit(
            db,
            "CHARGE_CONFIG",
            results[0]["config_id"],
            "REQUEST",
            None,
            {"pair": True, "payload": payload.model_dump()},
            user.employee_id,
        )
        db.commit()
        return {"status": "ok", "requests": results}
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_integrity_detail(e)) from e
    finally:
        db.close()

@router.post("/requests/{approval_id}/approve")
def approve_charge_config(
    approval_id: int,
    decision: ApprovalDecision,
    user: AuthUser = Depends(require_roles("CHECKER", "ADMIN")),
):
    db = SessionLocal()
    approval = db.query(ApprovalRequest).filter(ApprovalRequest.approval_id == approval_id).first()
    if not approval or approval.entity_type != "CHARGE_CONFIG":
        db.close()
        raise HTTPException(status_code=404, detail="Approval not found")
    try:
        ensure_pending(approval, "Approval")
    except HTTPException:
        db.close()
        raise

    enforce_checker_rules(user, approval.maker_id, decision.checker_id, decision.comment)

    config = db.query(ChargeConfigurationMaster).filter(ChargeConfigurationMaster.config_id == approval.entity_id).first()
    if not config:
        db.close()
        raise HTTPException(status_code=404, detail="Config not found")

    active = (
        db.query(ChargeConfigurationMaster)
        .filter(ChargeConfigurationMaster.config_code == config.config_code)
        .filter(ChargeConfigurationMaster.config_id != config.config_id)
        .filter(ChargeConfigurationMaster.status == "ACTIVE")
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

    log_audit(db, "CHARGE_CONFIG", config.config_id, "APPROVE", None, decision.comment, user.employee_id)
    db.commit()
    db.close()
    return {"status": "APPROVED"}

@router.post("/requests/{approval_id}/reject")
def reject_charge_config(
    approval_id: int,
    decision: ApprovalDecision,
    user: AuthUser = Depends(require_roles("CHECKER", "ADMIN")),
):
    db = SessionLocal()
    approval = db.query(ApprovalRequest).filter(ApprovalRequest.approval_id == approval_id).first()
    if not approval or approval.entity_type != "CHARGE_CONFIG":
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

    log_audit(db, "CHARGE_CONFIG", approval.entity_id, "REJECT", None, decision.comment, user.employee_id)
    db.commit()
    db.close()
    return {"status": "REJECTED"}
