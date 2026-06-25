import json
from datetime import datetime, timedelta

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from backend.auth import AuthUser, require_roles
from backend.audit import log_audit
from backend.db import SessionLocal
from backend.models import ApprovalRequest, BankStoreMaster, VendorMaster, VendorStoreMappingMaster
from backend.schemas import ApprovalDecision, StoreMappingDeactivateRequest, StoreMappingRequest
from backend.utils_approval import append_comment_history, enforce_checker_rules, ensure_pending, init_comment_history, safe_json_loads_clob
from backend.utils_bulk_upload import read_bulk_upload_file
from backend.utils_month_lock import enforce_month_unlocked

router = APIRouter(prefix="/api/store-mappings", tags=["store-mappings"])

@router.get("")
def list_mappings(
    include_inactive: bool = False,
    user: AuthUser = Depends(require_roles("MAKER", "CHECKER", "ADMIN", "AUDITOR")),
):
    db = SessionLocal()
    enforce_month_unlocked(db, datetime.utcnow().strftime("%Y%m"))
    query = db.query(VendorStoreMappingMaster)
    if not include_inactive:
        query = query.filter(VendorStoreMappingMaster.status == "ACTIVE")
    mappings = query.all()
    mapping_ids = [m.mapping_id for m in mappings]
    latest_by_mapping: dict = {}
    if mapping_ids:
        approvals = (
            db.query(ApprovalRequest)
            .filter(ApprovalRequest.entity_type == "STORE_MAPPING")
            .filter(ApprovalRequest.entity_id.in_(mapping_ids))
            .order_by(ApprovalRequest.created_date.desc())
            .all()
        )
        for approval in approvals:
            if approval.entity_id in latest_by_mapping:
                continue
            proposed = safe_json_loads_clob(approval.proposed_data, raise_on_error=False)
            latest_by_mapping[approval.entity_id] = {
                "approval_id": approval.approval_id,
                "approval_status": approval.status,
                "approval_action": proposed.get("action") if isinstance(proposed, dict) else None,
                "maker_id": approval.maker_id,
                "checker_id": approval.checker_id,
                "checker_comment": approval.checker_comment,
                "approval_created_at": approval.created_date.isoformat() if approval.created_date else None,
                "approval_decided_at": approval.approved_date.isoformat() if approval.approved_date else None,
            }
    result = [
        {
            "mapping_id": m.mapping_id,
            "approval_id": latest_by_mapping.get(m.mapping_id, {}).get("approval_id"),
            "vendor_id": m.vendor_id,
            "vendor_store_code": m.vendor_store_code,
            "bank_store_code": m.bank_store_code,
            "customer_id": m.customer_id,
            "customer_name": m.customer_name,
            "account_no": m.account_no,
            "status": m.status,
            "effective_from": m.effective_from,
            "approval_status": latest_by_mapping.get(m.mapping_id, {}).get("approval_status"),
            "approval_action": latest_by_mapping.get(m.mapping_id, {}).get("approval_action"),
            "maker_id": latest_by_mapping.get(m.mapping_id, {}).get("maker_id"),
            "checker_id": latest_by_mapping.get(m.mapping_id, {}).get("checker_id"),
            "checker_comment": latest_by_mapping.get(m.mapping_id, {}).get("checker_comment"),
            "approval_created_at": latest_by_mapping.get(m.mapping_id, {}).get("approval_created_at"),
            "approval_decided_at": latest_by_mapping.get(m.mapping_id, {}).get("approval_decided_at"),
        }
        for m in mappings
    ]
    log_audit(db, "STORE_MAPPING", "LIST", "VIEW", None, f"count={len(result)}", user.employee_id)
    db.commit()
    db.close()
    return result

@router.post("/requests")
def request_mapping(payload: StoreMappingRequest, user: AuthUser = Depends(require_roles("MAKER", "ADMIN"))):
    if payload.maker_id != user.employee_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Maker mismatch")

    db = SessionLocal()
    approvals = []
    for row in payload.mappings:
        vendor = db.query(VendorMaster).filter(VendorMaster.vendor_id == row.vendor_id).first()
        if not vendor:
            db.close()
            raise HTTPException(status_code=404, detail="Vendor not found")
        mapping = VendorStoreMappingMaster(
            vendor_id=row.vendor_id,
            vendor_store_code=row.vendor_store_code,
            bank_store_code=row.bank_store_code,
            customer_id=row.customer_id,
            customer_name=row.customer_name,
            account_no=row.account_no,
            status="INACTIVE",
            effective_from=row.effective_from or datetime.utcnow().date(),
            created_by=payload.maker_id,
        )
        db.add(mapping)
        db.flush()
        approval = ApprovalRequest(
            entity_type="STORE_MAPPING",
            entity_id=mapping.mapping_id,
            original_data=json.dumps({}),
            proposed_data=json.dumps(row.model_dump(), default=str),
            reason=payload.reason,
            comments_history=init_comment_history(payload.reason, payload.maker_id),
            maker_id=payload.maker_id,
            status="PENDING",
        )
        db.add(approval)
        approvals.append(approval.approval_id)

    log_audit(
        db,
        "STORE_MAPPING",
        "BATCH",
        "REQUEST",
        None,
        f"count={len(payload.mappings)}",
        user.employee_id,
    )
    db.commit()
    db.close()
    return {"approval_ids": approvals}

@router.post("/requests/{approval_id}/approve")
def approve_mapping(
    approval_id: int,
    decision: ApprovalDecision,
    user: AuthUser = Depends(require_roles("CHECKER", "ADMIN")),
):
    db = SessionLocal()
    approval = db.query(ApprovalRequest).filter(ApprovalRequest.approval_id == approval_id).first()
    if not approval or approval.entity_type != "STORE_MAPPING":
        db.close()
        raise HTTPException(status_code=404, detail="Approval not found")
    try:
        ensure_pending(approval, "Approval")
    except HTTPException:
        db.close()
        raise

    enforce_checker_rules(user, approval.maker_id, decision.checker_id, decision.comment)

    db.refresh(approval)
    mapping = (
        db.query(VendorStoreMappingMaster)
        .filter(VendorStoreMappingMaster.mapping_id == approval.entity_id)
        .first()
    )
    if not mapping:
        db.close()
        raise HTTPException(status_code=404, detail="Mapping not found")

    proposed = safe_json_loads_clob(approval.proposed_data, raise_on_error=False)
    action = proposed.get("action")

    if action == "DEACTIVATE":
        mapping.status = "INACTIVE"
        mapping.effective_to = datetime.utcnow().date()
        mapping.approved_by = decision.checker_id
        mapping.approved_date = datetime.utcnow()
        approval.status = "APPROVED"
        approval.checker_id = decision.checker_id
        approval.checker_comment = decision.comment
        approval.comments_history = append_comment_history(
            approval.comments_history, "CHECKER", decision.checker_id, decision.comment
        )
        approval.approved_date = datetime.utcnow()
        log_audit(db, "STORE_MAPPING", mapping.mapping_id, "DEACTIVATE", None, decision.comment, user.employee_id)
        db.commit()
        db.close()
        return {"status": "APPROVED"}

    vendor = db.query(VendorMaster).filter(VendorMaster.vendor_id == mapping.vendor_id).first()
    if not vendor or (vendor.status or "").upper() != "ACTIVE":
        db.close()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Vendor is no longer ACTIVE; please reject this mapping request.",
        )
    store = (
        db.query(BankStoreMaster)
        .filter(BankStoreMaster.bank_store_code == mapping.bank_store_code)
        .filter(BankStoreMaster.status == "ACTIVE")
        .first()
    )
    if not store:
        db.close()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bank store is no longer ACTIVE; please reject this mapping request.",
        )

    active = (
        db.query(VendorStoreMappingMaster)
        .filter(VendorStoreMappingMaster.vendor_id == mapping.vendor_id)
        .filter(VendorStoreMappingMaster.vendor_store_code == mapping.vendor_store_code)
        .filter(VendorStoreMappingMaster.mapping_id != mapping.mapping_id)
        .filter(VendorStoreMappingMaster.status == "ACTIVE")
        .all()
    )
    for row in active:
        row.status = "INACTIVE"
        row.effective_to = mapping.effective_from - timedelta(days=1)

    mapping.status = "ACTIVE"
    mapping.approved_by = decision.checker_id
    mapping.approved_date = datetime.utcnow()
    approval.status = "APPROVED"
    approval.checker_id = decision.checker_id
    approval.checker_comment = decision.comment
    approval.comments_history = append_comment_history(
        approval.comments_history, "CHECKER", decision.checker_id, decision.comment
    )
    approval.approved_date = datetime.utcnow()

    log_audit(db, "STORE_MAPPING", mapping.mapping_id, "APPROVE", None, decision.comment, user.employee_id)
    db.commit()
    db.close()
    return {"status": "APPROVED"}

@router.post("/requests/{mapping_id}/deactivate")
def request_deactivate_mapping(
    mapping_id: int,
    payload: StoreMappingDeactivateRequest,
    user: AuthUser = Depends(require_roles("MAKER", "ADMIN")),
):
    if payload.maker_id != user.employee_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Maker mismatch")

    db = SessionLocal()
    mapping = (
        db.query(VendorStoreMappingMaster)
        .filter(VendorStoreMappingMaster.mapping_id == mapping_id)
        .first()
    )
    if not mapping:
        db.close()
        raise HTTPException(status_code=404, detail="Mapping not found")

    approval = ApprovalRequest(
        entity_type="STORE_MAPPING",
        entity_id=mapping.mapping_id,
        original_data=json.dumps(
            {
                "vendor_id": mapping.vendor_id,
                "vendor_store_code": mapping.vendor_store_code,
                "bank_store_code": mapping.bank_store_code,
                "customer_id": mapping.customer_id,
                "customer_name": mapping.customer_name,
                "account_no": mapping.account_no,
                "status": mapping.status,
            },
            default=str,
        ),
        proposed_data=json.dumps({"action": "DEACTIVATE"}, default=str),
        reason=payload.reason,
        comments_history=init_comment_history(payload.reason, payload.maker_id),
        maker_id=payload.maker_id,
        status="PENDING",
    )
    db.add(approval)
    db.flush()
    approval_id = approval.approval_id

    log_audit(
        db,
        "STORE_MAPPING",
        mapping.mapping_id,
        "DEACTIVATE_REQUEST",
        None,
        payload.reason,
        user.employee_id,
    )
    db.commit()
    db.close()
    return {"approval_id": approval_id}

@router.post("/requests/{approval_id}/reject")
def reject_mapping(
    approval_id: int,
    decision: ApprovalDecision,
    user: AuthUser = Depends(require_roles("CHECKER", "ADMIN")),
):
    db = SessionLocal()
    approval = db.query(ApprovalRequest).filter(ApprovalRequest.approval_id == approval_id).first()
    if not approval or approval.entity_type != "STORE_MAPPING":
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

    log_audit(db, "STORE_MAPPING", approval.entity_id, "REJECT", None, decision.comment, user.employee_id)
    db.commit()
    db.close()
    return {"status": "REJECTED"}

def _parse_bulk_mapping_row(row, col_map):
    vendor = row.get(col_map.get("vendor_id", "vendor_id")) or row.get(col_map.get("vendor_code", "vendor_code"))
    vendor_code = str(vendor).strip() if vendor is not None and not pd.isna(vendor) else ""
    vendor_store = str(row.get(col_map.get("vendor_store_code", "vendor_store_code"), "")).strip()
    bank_store = str(row.get(col_map.get("bank_store_code", "bank_store_code"), "")).strip()
    eff = row.get(col_map.get("effective_from", "effective_from"))
    if not vendor_code or not vendor_store or not bank_store or pd.isna(eff):
        return None
    try:
        if isinstance(eff, (int, float)) and 1000 < eff < 1000000:
            eff_date = (pd.Timestamp("1899-12-30") + pd.Timedelta(days=float(eff))).date()
        else:
            eff_date = pd.to_datetime(eff).date()
    except Exception:
        return None
    return {
        "vendor_id_or_code": vendor_code,
        "vendor_store_code": vendor_store,
        "bank_store_code": bank_store,
        "customer_id": str(row.get(col_map.get("customer_id", "customer_id"), "")).strip() or None,
        "customer_name": str(row.get(col_map.get("customer_name", "customer_name"), "")).strip() or None,
        "account_no": str(row.get(col_map.get("account_no", "account_no"), "")).strip() or None,
        "effective_from": eff_date,
    }

@router.post("/bulk")
def bulk_upload_mappings(
    file: UploadFile = File(...),
    user: AuthUser = Depends(require_roles("ADMIN")),
):
    db = SessionLocal()
    try:
        df = read_bulk_upload_file(file)
    except HTTPException:
        db.close()
        raise
    except Exception as e:
        db.close()
        raise HTTPException(status_code=400, detail="Invalid or unsupported Excel file.") from e

    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    cols = set(df.columns)
    aliases = {
        "vendor_id": ["vendor_id", "vendorid"],
        "vendor_code": ["vendor_code", "vendorcode"],
        "vendor_store_code": ["vendor_store_code", "vendor_storecode", "vendorstorecode"],
        "bank_store_code": ["bank_store_code", "bank_storecode", "bankstorecode"],
        "effective_from": ["effective_from", "effectivefrom", "eff_from"],
        "customer_id": ["customer_id", "customerid"],
        "customer_name": ["customer_name", "customername"],
        "account_no": ["account_no", "accountno"],
    }
    col_map = {}
    for std, alts in aliases.items():
        for a in alts:
            if a in cols:
                col_map[std] = a
                break

    has_vendor = "vendor_id" in col_map or "vendor_code" in col_map
    if not has_vendor or "vendor_store_code" not in col_map or "bank_store_code" not in col_map or "effective_from" not in col_map:
        db.close()
        raise HTTPException(
            status_code=400,
            detail="Missing required columns: vendor_id or vendor_code, vendor_store_code, bank_store_code, effective_from",
        )

    vendors = db.query(VendorMaster).filter(VendorMaster.status == "ACTIVE").all()
    vendor_by_id = {str(v.vendor_id): v.vendor_id for v in vendors}
    vendor_by_code = {str(v.vendor_code).strip().upper(): v.vendor_id for v in vendors}
    bank_store_rows = db.query(BankStoreMaster.bank_store_code).filter(BankStoreMaster.status == "ACTIVE").all()
    bank_stores = {str(r[0]).strip() for r in bank_store_rows if r and r[0]}

    created = 0
    skipped = 0
    errors = []

    for idx, row in df.iterrows():
        data = _parse_bulk_mapping_row(row, col_map)
        if not data:
            errors.append({"row": int(idx) + 2, "reason": "Missing required fields"})
            skipped += 1
            continue

        vendor_id = vendor_by_id.get(data["vendor_id_or_code"])
        if not vendor_id:
            vendor_id = vendor_by_code.get(data["vendor_id_or_code"].upper())
        if not vendor_id:
            errors.append({"row": int(idx) + 2, "reason": f"Vendor not found: {data['vendor_id_or_code']}"})
            skipped += 1
            continue

        if data["bank_store_code"] not in bank_stores:
            errors.append({"row": int(idx) + 2, "reason": f"Bank store not onboarded: {data['bank_store_code']}"})
            skipped += 1
            continue

        existing = (
            db.query(VendorStoreMappingMaster)
            .filter(VendorStoreMappingMaster.vendor_id == vendor_id)
            .filter(VendorStoreMappingMaster.vendor_store_code == data["vendor_store_code"])
            .filter(VendorStoreMappingMaster.status == "ACTIVE")
            .first()
        )
        if existing:
            errors.append({"row": int(idx) + 2, "reason": f"Mapping already exists: {data['vendor_store_code']} -> {data['bank_store_code']}"})
            skipped += 1
            continue

        mapping = VendorStoreMappingMaster(
            vendor_id=vendor_id,
            vendor_store_code=data["vendor_store_code"],
            bank_store_code=data["bank_store_code"],
            customer_id=data["customer_id"],
            customer_name=data["customer_name"],
            account_no=data["account_no"],
            status="ACTIVE",
            effective_from=data["effective_from"],
            created_by=user.employee_id,
            approved_by=user.employee_id,
            approved_date=datetime.utcnow(),
        )
        db.add(mapping)
        created += 1

    log_audit(
        db,
        "STORE_MAPPING",
        "BULK",
        "UPLOAD",
        None,
        f"created={created}, skipped={skipped}",
        user.employee_id,
    )
    db.commit()
    db.close()
    return {"created": created, "skipped": skipped, "errors": errors[:50]}
