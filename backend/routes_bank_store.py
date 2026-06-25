import json
from datetime import datetime, timedelta, date

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from backend.auth import AuthUser, require_roles
from backend.audit import log_audit
from backend.db import SessionLocal
from backend.models import ApprovalRequest, BankStoreMaster
from backend.schemas import ApprovalDecision, BankStoreDeactivateRequest, BankStoreRequest, BankStoreUpdateRequest
from backend.utils_approval import append_comment_history, ensure_pending, enforce_checker_rules, init_comment_history, safe_json_loads_clob
from backend.utils_bulk_upload import read_bulk_upload_file
from backend.utils_month_lock import enforce_month_unlocked

router = APIRouter(prefix="/api/bank-stores", tags=["bank-stores"])

BULK_STORE_HEADERS = {"bank_store_code", "effective_from"}

@router.get("")
def list_bank_stores(
    include_inactive: bool = False,
    user: AuthUser = Depends(require_roles("MAKER", "CHECKER", "ADMIN", "AUDITOR")),
):
    db = SessionLocal()
    query = db.query(BankStoreMaster)
    if not include_inactive:
        query = query.filter(BankStoreMaster.status == "ACTIVE")
    stores = query.all()

    store_ids = [s.store_id for s in stores]
    latest_by_store: dict = {}
    if store_ids:
        approvals = (
            db.query(ApprovalRequest)
            .filter(ApprovalRequest.entity_type == "BANK_STORE_MASTER")
            .filter(ApprovalRequest.entity_id.in_(store_ids))
            .order_by(ApprovalRequest.created_date.desc())
            .all()
        )
        for ap in approvals:
            if ap.entity_id in latest_by_store:
                continue
            proposed = safe_json_loads_clob(ap.proposed_data, raise_on_error=False)
            latest_by_store[ap.entity_id] = {
                "approval_id": ap.approval_id,
                "approval_status": ap.status,
                "approval_action": proposed.get("action") if isinstance(proposed, dict) else None,
                "maker_id": ap.maker_id,
                "checker_id": ap.checker_id,
                "checker_comment": ap.checker_comment,
                "approval_created_at": ap.created_date.isoformat() if ap.created_date else None,
                "approval_decided_at": ap.approved_date.isoformat() if ap.approved_date else None,
            }

    result = [
        {
            "store_id": s.store_id,
            "bank_store_code": s.bank_store_code,
            "store_name": s.store_name,
            "customer_id": s.customer_id,
            "customer_name": s.customer_name,
            "account_no": s.account_no,
            "pickup_type": getattr(s, "pickup_type", None) or "BEAT",
            "daily_pickup_limit": float(s.daily_pickup_limit) if s.daily_pickup_limit is not None else None,
            "fixed_charge": float(s.fixed_charge) if s.fixed_charge is not None else None,
            "vendor_charge": float(s.vendor_charge) if getattr(s, "vendor_charge", None) is not None else None,
            "call_included_pickups": int(s.call_included_pickups)
            if getattr(s, "call_included_pickups", None) is not None
            else None,
            "call_monthly_bank_charge": float(s.call_monthly_bank_charge)
            if getattr(s, "call_monthly_bank_charge", None) is not None
            else None,
            "call_additional_bank_per_pickup": float(s.call_additional_bank_per_pickup)
            if getattr(s, "call_additional_bank_per_pickup", None) is not None
            else None,
            "call_vendor_pay_per_pickup": float(s.call_vendor_pay_per_pickup)
            if getattr(s, "call_vendor_pay_per_pickup", None) is not None
            else None,
            "waiver_percentage": float(s.waiver_percentage) if s.waiver_percentage is not None else None,
            "waiver_cap_amount": float(s.waiver_cap_amount) if getattr(s, "waiver_cap_amount", None) is not None else None,
            "waiver_cap_from": getattr(s, "waiver_cap_from", None),
            "waiver_cap_to": getattr(s, "waiver_cap_to", None),
            "status": s.status,
            "effective_from": s.effective_from,
            "onboarded_date": s.onboarded_date,
            "last_modified_date": s.last_modified_date,
            "approval_id": latest_by_store.get(s.store_id, {}).get("approval_id"),
            "approval_status": latest_by_store.get(s.store_id, {}).get("approval_status"),
            "approval_action": latest_by_store.get(s.store_id, {}).get("approval_action"),
            "maker_id": latest_by_store.get(s.store_id, {}).get("maker_id"),
            "checker_id": latest_by_store.get(s.store_id, {}).get("checker_id"),
            "checker_comment": latest_by_store.get(s.store_id, {}).get("checker_comment"),
            "approval_created_at": latest_by_store.get(s.store_id, {}).get("approval_created_at"),
            "approval_decided_at": latest_by_store.get(s.store_id, {}).get("approval_decided_at"),
        }
        for s in stores
    ]
    log_audit(db, "BANK_STORE_MASTER", "LIST", "VIEW", None, f"count={len(result)}", user.employee_id)
    db.commit()
    db.close()
    return result

@router.post("/requests")
def request_bank_store(payload: BankStoreRequest, user: AuthUser = Depends(require_roles("MAKER", "ADMIN"))):
    if payload.maker_id != user.employee_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Maker mismatch")

    db = SessionLocal()
    enforce_month_unlocked(db, payload.effective_from.strftime("%Y%m"))
    existing = db.query(BankStoreMaster).filter(BankStoreMaster.bank_store_code == payload.bank_store_code).first()
    if existing:
        db.close()
        raise HTTPException(status_code=400, detail="Bank store code already exists or pending approval")

    pickup_type_val = (payload.pickup_type or "BEAT").strip().upper()
    if pickup_type_val not in ("BEAT", "CALL"):
        pickup_type_val = "BEAT"
    store = BankStoreMaster(
        bank_store_code=payload.bank_store_code,
        store_name=payload.store_name,
        customer_id=payload.customer_id or None,
        customer_name=payload.customer_name or None,
        account_no=payload.account_no or None,
        sol_id=payload.sol_id,
        pickup_type=pickup_type_val,
        daily_pickup_limit=payload.daily_pickup_limit,
        fixed_charge=payload.fixed_charge,
        vendor_charge=payload.vendor_charge,
        call_included_pickups=payload.call_included_pickups,
        call_monthly_bank_charge=payload.call_monthly_bank_charge,
        call_additional_bank_per_pickup=payload.call_additional_bank_per_pickup,
        call_vendor_pay_per_pickup=payload.call_vendor_pay_per_pickup,
        waiver_percentage=payload.waiver_percentage,
        waiver_cap_amount=payload.waiver_cap_amount,
        waiver_cap_from=payload.waiver_cap_from,
        waiver_cap_to=payload.waiver_cap_to,
        status="INACTIVE",
        effective_from=payload.effective_from,
        created_by=payload.maker_id,
    )
    db.add(store)
    db.flush()

    approval = ApprovalRequest(
        entity_type="BANK_STORE_MASTER",
        entity_id=store.store_id,
        original_data=json.dumps({}),
        proposed_data=json.dumps(payload.model_dump(), default=str),
        reason=payload.reason,
        comments_history=init_comment_history(payload.reason, payload.maker_id),
        maker_id=payload.maker_id,
        status="PENDING",
    )
    db.add(approval)
    db.flush()
    log_audit(db, "BANK_STORE_MASTER", store.store_id, "REQUEST", None, payload.model_dump(), user.employee_id)
    approval_id = approval.approval_id
    store_id = store.store_id
    db.commit()
    db.close()
    return {"approval_id": approval_id, "store_id": store_id}

def _bank_store_pending_approval(db, store_id: int):
    return (
        db.query(ApprovalRequest)
        .filter(ApprovalRequest.entity_type == "BANK_STORE_MASTER")
        .filter(ApprovalRequest.entity_id == store_id)
        .filter(ApprovalRequest.status == "PENDING")
        .first()
    )

def _parse_json_date(val):
    if val is None:
        return None
    if isinstance(val, date):
        return val
    s = str(val).strip()
    if not s:
        return None
    return date.fromisoformat(s[:10])

@router.post("/requests/{store_id}/update")
def request_update_bank_store(
    store_id: int,
    payload: BankStoreUpdateRequest,
    user: AuthUser = Depends(require_roles("MAKER", "ADMIN")),
):
    if payload.store_id != store_id:
        raise HTTPException(status_code=400, detail="Store ID mismatch")
    if payload.maker_id != user.employee_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Maker mismatch")

    db = SessionLocal()
    store = db.query(BankStoreMaster).filter(BankStoreMaster.store_id == store_id).first()
    if not store:
        db.close()
        raise HTTPException(status_code=404, detail="Store not found")
    if store.status != "ACTIVE":
        db.close()
        raise HTTPException(status_code=400, detail="Only ACTIVE stores can be updated via this request")

    if _bank_store_pending_approval(db, store_id):
        db.close()
        raise HTTPException(status_code=400, detail="This store already has a pending approval request")

    enforce_month_unlocked(db, payload.effective_from.strftime("%Y%m"))

    new_code = (payload.bank_store_code or "").strip()
    if not new_code:
        db.close()
        raise HTTPException(status_code=400, detail="Bank store code is required")

    if new_code != store.bank_store_code:
        conflict = (
            db.query(BankStoreMaster)
            .filter(BankStoreMaster.bank_store_code == new_code)
            .filter(BankStoreMaster.store_id != store_id)
            .first()
        )
        if conflict:
            db.close()
            raise HTTPException(status_code=400, detail="Bank store code already exists")

    pickup_type_val = (payload.pickup_type or "BEAT").strip().upper()
    if pickup_type_val not in ("BEAT", "CALL"):
        pickup_type_val = "BEAT"

    proposed_body = payload.model_dump()
    proposed_body["pickup_type"] = pickup_type_val
    if not proposed_body.get("sol_id") or not str(proposed_body.get("sol_id")).strip():
        proposed_body["sol_id"] = store.sol_id
    proposed_body["action"] = "UPDATE"
    proposed_data = json.dumps(proposed_body, default=str)

    original_data = json.dumps(
        {
            "store_id": store.store_id,
            "bank_store_code": store.bank_store_code,
            "store_name": store.store_name,
            "customer_id": store.customer_id,
            "customer_name": store.customer_name,
            "account_no": store.account_no,
            "sol_id": store.sol_id,
            "pickup_type": store.pickup_type,
            "daily_pickup_limit": float(store.daily_pickup_limit) if store.daily_pickup_limit is not None else None,
            "fixed_charge": float(store.fixed_charge) if store.fixed_charge is not None else None,
            "vendor_charge": float(store.vendor_charge) if getattr(store, "vendor_charge", None) is not None else None,
            "call_included_pickups": int(store.call_included_pickups)
            if getattr(store, "call_included_pickups", None) is not None
            else None,
            "call_monthly_bank_charge": float(store.call_monthly_bank_charge)
            if getattr(store, "call_monthly_bank_charge", None) is not None
            else None,
            "call_additional_bank_per_pickup": float(store.call_additional_bank_per_pickup)
            if getattr(store, "call_additional_bank_per_pickup", None) is not None
            else None,
            "call_vendor_pay_per_pickup": float(store.call_vendor_pay_per_pickup)
            if getattr(store, "call_vendor_pay_per_pickup", None) is not None
            else None,
            "waiver_percentage": float(store.waiver_percentage) if store.waiver_percentage is not None else None,
            "waiver_cap_amount": float(store.waiver_cap_amount) if getattr(store, "waiver_cap_amount", None) is not None else None,
            "waiver_cap_from": store.waiver_cap_from,
            "waiver_cap_to": store.waiver_cap_to,
            "effective_from": store.effective_from,
            "status": store.status,
        },
        default=str,
    )

    approval = ApprovalRequest(
        entity_type="BANK_STORE_MASTER",
        entity_id=store.store_id,
        original_data=original_data,
        proposed_data=proposed_data,
        reason=payload.reason,
        comments_history=init_comment_history(payload.reason or "Update store", payload.maker_id),
        maker_id=payload.maker_id,
        status="PENDING",
    )
    db.add(approval)
    db.flush()
    approval_id = approval.approval_id
    log_audit(db, "BANK_STORE_MASTER", store_id, "UPDATE_REQUEST", None, proposed_body, user.employee_id)
    db.commit()
    db.close()
    return {"approval_id": approval_id}

@router.post("/requests/{approval_id}/approve")
def approve_bank_store(
    approval_id: int,
    decision: ApprovalDecision,
    user: AuthUser = Depends(require_roles("CHECKER", "ADMIN")),
):
    db = SessionLocal()
    approval = db.query(ApprovalRequest).filter(ApprovalRequest.approval_id == approval_id).first()
    if not approval or approval.entity_type != "BANK_STORE_MASTER":
        db.close()
        raise HTTPException(status_code=404, detail="Approval not found")
    try:
        ensure_pending(approval, "Approval")
    except HTTPException:
        db.close()
        raise
    enforce_checker_rules(user, approval.maker_id, decision.checker_id, decision.comment)

    db.refresh(approval)
    store = db.query(BankStoreMaster).filter(BankStoreMaster.store_id == approval.entity_id).first()
    if not store:
        db.close()
        raise HTTPException(status_code=404, detail="Store not found")

    proposed = safe_json_loads_clob(approval.proposed_data, raise_on_error=False)
    is_deactivate = proposed.get("action") == "DEACTIVATE"
    is_update = proposed.get("action") == "UPDATE"

    if is_deactivate:
        store.status = "INACTIVE"
        store.effective_to = date.today()
    elif is_update:
        new_code = (proposed.get("bank_store_code") or "").strip()
        if not new_code:
            db.close()
            raise HTTPException(status_code=400, detail="Invalid update payload: missing bank store code")
        if new_code != store.bank_store_code:
            conflict = (
                db.query(BankStoreMaster)
                .filter(BankStoreMaster.bank_store_code == new_code)
                .filter(BankStoreMaster.store_id != store.store_id)
                .first()
            )
            if conflict:
                db.close()
                raise HTTPException(status_code=400, detail="Bank store code already exists")
        pickup_type_val = (proposed.get("pickup_type") or "BEAT").strip().upper()
        if pickup_type_val not in ("BEAT", "CALL"):
            pickup_type_val = "BEAT"
        eff = _parse_json_date(proposed.get("effective_from"))
        if not eff:
            db.close()
            raise HTTPException(status_code=400, detail="Invalid update payload: effective_from")

        store.bank_store_code = new_code
        store.store_name = proposed.get("store_name")
        store.customer_id = proposed.get("customer_id") or None
        store.customer_name = proposed.get("customer_name") or None
        store.account_no = proposed.get("account_no") or None
        sol = proposed.get("sol_id")
        store.sol_id = str(sol).strip() if sol is not None and str(sol).strip() else None
        store.pickup_type = pickup_type_val
        lim = proposed.get("daily_pickup_limit")
        store.daily_pickup_limit = float(lim) if lim is not None and lim != "" else None
        fc = proposed.get("fixed_charge")
        store.fixed_charge = float(fc) if fc is not None and fc != "" else None
        vc = proposed.get("vendor_charge")
        store.vendor_charge = float(vc) if vc is not None and vc != "" else None
        cip = proposed.get("call_included_pickups")
        store.call_included_pickups = int(cip) if cip is not None and cip != "" else None
        cmb = proposed.get("call_monthly_bank_charge")
        store.call_monthly_bank_charge = float(cmb) if cmb is not None and cmb != "" else None
        cab = proposed.get("call_additional_bank_per_pickup")
        store.call_additional_bank_per_pickup = float(cab) if cab is not None and cab != "" else None
        cvp = proposed.get("call_vendor_pay_per_pickup")
        store.call_vendor_pay_per_pickup = float(cvp) if cvp is not None and cvp != "" else None
        wv = proposed.get("waiver_percentage")
        store.waiver_percentage = float(wv) if wv is not None and wv != "" else None
        wc = proposed.get("waiver_cap_amount")
        store.waiver_cap_amount = float(wc) if wc is not None and wc != "" else None
        store.waiver_cap_from = _parse_json_date(proposed.get("waiver_cap_from"))
        store.waiver_cap_to = _parse_json_date(proposed.get("waiver_cap_to"))
        store.effective_from = eff
        store.status = "ACTIVE"
    else:
        active = (
            db.query(BankStoreMaster)
            .filter(BankStoreMaster.bank_store_code == store.bank_store_code)
            .filter(BankStoreMaster.store_id != store.store_id)
            .filter(BankStoreMaster.status == "ACTIVE")
            .all()
        )
        for row in active:
            row.status = "INACTIVE"
            row.effective_to = store.effective_from - timedelta(days=1)
        store.status = "ACTIVE"
    now = datetime.utcnow()
    store.approved_by = decision.checker_id
    store.approved_date = now
    store.last_modified_date = now
    if not is_deactivate and not is_update and store.onboarded_date is None:
        store.onboarded_date = now.date()
    approval.status = "APPROVED"
    approval.checker_id = decision.checker_id
    approval.checker_comment = decision.comment
    approval.comments_history = append_comment_history(
        approval.comments_history, "CHECKER", decision.checker_id, decision.comment
    )
    approval.approved_date = datetime.utcnow()

    log_audit(db, "BANK_STORE_MASTER", store.store_id, "APPROVE", None, decision.comment, user.employee_id)
    db.commit()
    db.close()
    return {"status": "APPROVED"}

@router.post("/requests/{approval_id}/reject")
def reject_bank_store(
    approval_id: int,
    decision: ApprovalDecision,
    user: AuthUser = Depends(require_roles("CHECKER", "ADMIN")),
):
    db = SessionLocal()
    approval = db.query(ApprovalRequest).filter(ApprovalRequest.approval_id == approval_id).first()
    if not approval or approval.entity_type != "BANK_STORE_MASTER":
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

    log_audit(db, "BANK_STORE_MASTER", approval.entity_id, "REJECT", None, decision.comment, user.employee_id)
    db.commit()
    db.close()
    return {"status": "REJECTED"}

@router.post("/requests/{store_id}/deactivate")
def request_deactivate_store(
    store_id: int,
    payload: BankStoreDeactivateRequest,
    user: AuthUser = Depends(require_roles("MAKER", "ADMIN")),
):
    if payload.store_id != store_id:
        raise HTTPException(status_code=400, detail="Store ID mismatch")
    if payload.maker_id != user.employee_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Maker mismatch")

    db = SessionLocal()
    store = db.query(BankStoreMaster).filter(BankStoreMaster.store_id == store_id).first()
    if not store:
        db.close()
        raise HTTPException(status_code=404, detail="Store not found")
    if store.status != "ACTIVE":
        db.close()
        raise HTTPException(status_code=400, detail="Only ACTIVE stores can be deactivated")

    if _bank_store_pending_approval(db, store_id):
        db.close()
        raise HTTPException(status_code=400, detail="Resolve the pending store approval before deactivation")

    original_data = json.dumps(
        {
            "store_id": store.store_id,
            "bank_store_code": store.bank_store_code,
            "store_name": store.store_name,
            "status": store.status,
        },
        default=str,
    )
    proposed_data = json.dumps({"action": "DEACTIVATE", "store_id": store_id}, default=str)

    approval = ApprovalRequest(
        entity_type="BANK_STORE_MASTER",
        entity_id=store.store_id,
        original_data=original_data,
        proposed_data=proposed_data,
        reason=payload.reason,
        comments_history=init_comment_history(payload.reason or "Deactivate store", payload.maker_id),
        maker_id=payload.maker_id,
        status="PENDING",
    )
    db.add(approval)
    db.flush()
    approval_id = approval.approval_id
    log_audit(db, "BANK_STORE_MASTER", store_id, "DEACTIVATE_REQUEST", None, payload.reason, user.employee_id)
    db.commit()
    db.close()
    return {"approval_id": approval_id}

def _parse_bulk_store_row(row, col_map):
    code = str(row.get(col_map.get("bank_store_code", "bank_store_code"), "")).strip()
    eff = row.get(col_map.get("effective_from", "effective_from"))
    if not code or pd.isna(eff):
        return None
    try:
        if isinstance(eff, (int, float)) and 1000 < eff < 1000000:
            eff_date = (pd.Timestamp("1899-12-30") + pd.Timedelta(days=float(eff))).date()
        else:
            eff_date = pd.to_datetime(eff).date()
    except Exception:
        return None
    pickup_raw = str(row.get(col_map.get("pickup_type", "pickup_type"), "")).strip().upper()
    pickup_type = pickup_raw if pickup_raw in ("BEAT", "CALL") else "BEAT"

    def _bulk_cell_date(std_key):
        col = col_map.get(std_key)
        if not col:
            return None
        return _parse_optional_bulk_date(row.get(col))

    return {
        "bank_store_code": code,
        "store_name": str(row.get(col_map.get("store_name", "store_name"), "")).strip() or None,
        "customer_id": str(row.get(col_map.get("customer_id", "customer_id"), "")).strip() or None,
        "customer_name": str(row.get(col_map.get("customer_name", "customer_name"), "")).strip() or None,
        "account_no": str(row.get(col_map.get("account_no", "account_no"), "")).strip() or None,
        "sol_id": str(row.get(col_map.get("sol_id", "sol_id"), "")).strip() or None,
        "pickup_type": pickup_type,
        "daily_pickup_limit": _parse_float(row.get(col_map.get("daily_pickup_limit", "daily_pickup_limit"))),
        "fixed_charge": _parse_float(
            row.get(col_map.get("fixed_charge", "fixed_charge"))
            or row.get(col_map.get("monthly_bank_charge", "monthly_bank_charge"))
        ),
        "vendor_charge": _parse_float(
            row.get(col_map.get("vendor_charge", "vendor_charge"))
            or row.get(col_map.get("monthly_vendor_charge", "monthly_vendor_charge"))
        ),
        "call_included_pickups": _parse_int(row.get(col_map["call_included_pickups"]))
        if "call_included_pickups" in col_map
        else None,
        "call_monthly_bank_charge": _parse_float(row.get(col_map["call_monthly_bank_charge"]))
        if "call_monthly_bank_charge" in col_map
        else None,
        "call_additional_bank_per_pickup": _parse_float(row.get(col_map["call_additional_bank_per_pickup"]))
        if "call_additional_bank_per_pickup" in col_map
        else None,
        "call_vendor_pay_per_pickup": _parse_float(row.get(col_map["call_vendor_pay_per_pickup"]))
        if "call_vendor_pay_per_pickup" in col_map
        else None,
        "waiver_percentage": _parse_float(row.get(col_map.get("waiver_percentage", "waiver_percentage"))),
        "waiver_cap_amount": _parse_float(row.get(col_map.get("waiver_cap_amount", "waiver_cap_amount"))),
        "waiver_cap_from": _bulk_cell_date("waiver_cap_from"),
        "waiver_cap_to": _bulk_cell_date("waiver_cap_to"),
        "effective_from": eff_date,
    }

def _parse_float(v):
    if v is None or pd.isna(v):
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None

def _parse_int(v):
    if v is None or pd.isna(v):
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None

def _parse_optional_bulk_date(val):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        if isinstance(val, (int, float)) and 1000 < val < 1000000:
            return (pd.Timestamp("1899-12-30") + pd.Timedelta(days=float(val))).date()
        return pd.to_datetime(val, dayfirst=False).date()
    except Exception:
        return None

@router.post("/bulk")
def bulk_upload_stores(
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
        "bank_store_code": ["bank_store_code", "store_code", "storecode"],
        "effective_from": ["effective_from", "effectivefrom", "eff_from"],
        "store_name": ["store_name", "storename"],
        "customer_id": ["customer_id", "customerid"],
        "customer_name": ["customer_name", "customername"],
        "account_no": ["account_no", "accountno"],
        "sol_id": ["sol_id", "solid"],
        "pickup_type": ["pickup_type", "pickuptype"],
        "daily_pickup_limit": ["daily_pickup_limit", "dailypickuplimit"],
        "fixed_charge": ["fixed_charge", "monthly_bank_charge", "monthlybankcharge", "bank_charge"],
        "vendor_charge": ["vendor_charge", "monthly_vendor_charge", "vendor_monthly_charge", "monthlyvendorcharge"],
        "call_included_pickups": [
            "call_included_pickups",
            "call_included",
            "call_free_pickups",
            "call_package_pickups",
        ],
        "call_monthly_bank_charge": ["call_monthly_bank_charge", "call_monthly_package", "call_bank_monthly"],
        "call_additional_bank_per_pickup": [
            "call_additional_bank_per_pickup",
            "call_extra_bank_per_pickup",
            "call_bank_per_pickup",
        ],
        "call_vendor_pay_per_pickup": [
            "call_vendor_pay_per_pickup",
            "call_vendor_per_pickup",
            "vendor_pay_per_call_pickup",
        ],
        "waiver_percentage": ["waiver_percentage", "waiverpercent", "waiver_pct"],
        "waiver_cap_amount": ["waiver_cap_amount", "waiv_cap", "waiver_cap", "store_waiver_cap"],
        "waiver_cap_from": ["waiver_cap_from", "waivercapfrom", "cap_from", "store_waiver_cap_from"],
        "waiver_cap_to": ["waiver_cap_to", "waivercapto", "cap_to", "store_waiver_cap_to"],
    }
    col_map = {}
    for std, alts in aliases.items():
        for a in alts:
            if a in cols:
                col_map[std] = a
                break

    if "bank_store_code" not in col_map or "effective_from" not in col_map:
        db.close()
        raise HTTPException(
            status_code=400,
            detail=f"Missing required columns: bank_store_code, effective_from. Found: {list(df.columns)}",
        )

    created = 0
    skipped = 0
    errors = []
    bulk_now = datetime.utcnow()

    for idx, row in df.iterrows():
        data = _parse_bulk_store_row(row, col_map)
        if not data:
            errors.append({"row": int(idx) + 2, "reason": "Missing bank_store_code or effective_from"})
            skipped += 1
            continue

        existing = (
            db.query(BankStoreMaster)
            .filter(BankStoreMaster.bank_store_code == data["bank_store_code"])
            .filter(BankStoreMaster.status == "ACTIVE")
            .first()
        )
        if existing:
            errors.append({"row": int(idx) + 2, "reason": f"Store {data['bank_store_code']} already exists"})
            skipped += 1
            continue

        store = BankStoreMaster(
            bank_store_code=data["bank_store_code"],
            store_name=data["store_name"],
            customer_id=data["customer_id"],
            customer_name=data["customer_name"],
            account_no=data["account_no"],
            sol_id=data["sol_id"],
            pickup_type=data.get("pickup_type", "BEAT"),
            daily_pickup_limit=data["daily_pickup_limit"],
            fixed_charge=data.get("fixed_charge"),
            vendor_charge=data.get("vendor_charge"),
            call_included_pickups=data.get("call_included_pickups"),
            call_monthly_bank_charge=data.get("call_monthly_bank_charge"),
            call_additional_bank_per_pickup=data.get("call_additional_bank_per_pickup"),
            call_vendor_pay_per_pickup=data.get("call_vendor_pay_per_pickup"),
            waiver_percentage=data.get("waiver_percentage"),
            waiver_cap_amount=data.get("waiver_cap_amount"),
            waiver_cap_from=data.get("waiver_cap_from"),
            waiver_cap_to=data.get("waiver_cap_to"),
            status="ACTIVE",
            effective_from=data["effective_from"],
            created_by=user.employee_id,
            approved_by=user.employee_id,
            approved_date=bulk_now,
            onboarded_date=bulk_now.date(),
            last_modified_date=bulk_now,
        )
        db.add(store)
        created += 1

    log_audit(
        db,
        "BANK_STORE_MASTER",
        "BULK",
        "UPLOAD",
        None,
        f"created={created}, skipped={skipped}",
        user.employee_id,
    )
    db.commit()
    db.close()
    return {"created": created, "skipped": skipped, "errors": errors[:50]}
