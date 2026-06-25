import json
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException

from backend.auth import AuthUser, require_roles
from backend.audit import log_audit
from backend.db import SessionLocal
from backend.utils_approval import safe_json_loads_clob
from backend.models import (
    BankStoreMaster,
    CanonicalTransaction,
    ExceptionRecord,
    FinacleUploadBatch,
    MonthLock,
    ReconciliationCorrection,
    ReconciliationResult,
    ApprovalRequest,
    VendorMaster,
    VendorStoreMappingMaster,
    VendorUploadBatch,
)

router = APIRouter(prefix="/api/reconciliation", tags=["reconciliation"])

def _bank_store_codes_for_vendor(db, vendor_id: int, as_of: date) -> set[str]:
    rows = (
        db.query(VendorStoreMappingMaster.bank_store_code)
        .filter(VendorStoreMappingMaster.vendor_id == vendor_id)
        .filter(VendorStoreMappingMaster.status == "ACTIVE")
        .filter(VendorStoreMappingMaster.effective_from <= as_of)
        .filter(
            (VendorStoreMappingMaster.effective_to.is_(None))
            | (VendorStoreMappingMaster.effective_to >= as_of)
        )
        .all()
    )
    return {str(r[0]).strip() for r in rows if r and r[0] is not None and str(r[0]).strip()}

@router.post("/run")
def run_reconciliation(payload: dict, user: AuthUser = Depends(require_roles("MAKER", "ADMIN", "CHECKER"))):
    db = SessionLocal()
    mis_date_raw = payload.get("misDate")
    if not mis_date_raw:
        db.close()
        raise HTTPException(status_code=400, detail="misDate is required")
    try:
        mis_date = datetime.strptime(mis_date_raw, "%Y-%m-%d").date()
    except ValueError:
        db.close()
        raise HTTPException(status_code=400, detail="misDate must be YYYY-MM-DD")

    month_key = mis_date.strftime("%Y%m")
    locked_months = {
        lock.month_key for lock in db.query(MonthLock).filter(MonthLock.status == "LOCKED").all()
    }
    if month_key in locked_months:
        db.close()
        raise HTTPException(status_code=409, detail="Month is locked for reconciliation")

    vendor_id_filter = payload.get("vendor_id") if payload.get("vendor_id") is not None else payload.get("vendorId")
    vendor_id_int = None
    if vendor_id_filter not in (None, ""):
        try:
            vendor_id_int = int(vendor_id_filter)
        except (TypeError, ValueError):
            db.close()
            raise HTTPException(status_code=400, detail="vendor_id must be an integer when provided")
        vm = db.query(VendorMaster).filter(VendorMaster.vendor_id == vendor_id_int).first()
        if not vm:
            db.close()
            raise HTTPException(status_code=404, detail="Vendor not found")
        scope_stores = _bank_store_codes_for_vendor(db, vendor_id_int, mis_date)
        if not scope_stores:
            db.close()
            raise HTTPException(
                status_code=400,
                detail=f"No active store mappings for this vendor on MIS date {mis_date_raw}",
            )

    finacle_batch = (
        db.query(FinacleUploadBatch)
        .filter(FinacleUploadBatch.mis_date == mis_date)
        .order_by(FinacleUploadBatch.uploaded_at.desc())
        .first()
    )
    if not finacle_batch:
        db.close()
        raise HTTPException(status_code=404, detail="Finacle MIS not uploaded for date")

    vbatch_q = db.query(VendorUploadBatch).filter(VendorUploadBatch.mis_date == mis_date)
    if vendor_id_int is not None:
        vbatch_q = vbatch_q.filter(VendorUploadBatch.vendor_id == vendor_id_int)
    vendor_batches = vbatch_q.all()

    finacle = (
        db.query(CanonicalTransaction)
        .filter(CanonicalTransaction.source == "FINACLE")
        .filter(CanonicalTransaction.raw_batch_id == finacle_batch.batch_id)
        .all()
    )
    if vendor_batches:
        vendor = (
            db.query(CanonicalTransaction)
            .filter(CanonicalTransaction.source == "VENDOR")
            .filter(CanonicalTransaction.raw_batch_id.in_([b.batch_id for b in vendor_batches]))
            .all()
        )
    else:
        vendor = []

    finacle_agg = {}
    for f in finacle:
        store_code = str(f.bank_store_code or "").strip()
        if not store_code:
            continue
        if vendor_id_int is not None and store_code not in scope_stores:
            continue
        date_key = mis_date
        key = (store_code, date_key)
        finacle_agg[key] = (finacle_agg.get(key, 0.0) + float(f.remittance_amount or 0))

    vendor_id_by_batch = {b.batch_id: b.vendor_id for b in vendor_batches}
    vendor_agg = {}
    for v in vendor:
        store_code = str(v.bank_store_code or "").strip()
        if not store_code:
            continue
        if vendor_id_int is not None and store_code not in scope_stores:
            continue
        date_key = mis_date
        vendor_id = vendor_id_by_batch.get(v.raw_batch_id)
        vendor_name = None
        if vendor_id:
            vm = db.query(VendorMaster.vendor_name).filter(VendorMaster.vendor_id == vendor_id).first()
            vendor_name = vm[0] if vm else None
        key = (store_code, date_key)
        entry = vendor_agg.setdefault(key, {"amount": 0.0, "vendor_names": set()})
        line_amt = v.pickup_amount if v.pickup_amount is not None else v.remittance_amount
        entry["amount"] += float(line_amt or 0)
        if vendor_name:
            entry["vendor_names"].add(vendor_name)

    results = []
    extra_by_id = {}
    if vendor_id_int is not None:
        all_keys = {(code, mis_date) for code in scope_stores}
    else:
        all_keys = set(finacle_agg.keys()) | set(vendor_agg.keys())
    for bank_store_code, date_key in sorted(all_keys):
        finacle_amount = finacle_agg.get((bank_store_code, date_key))
        vendor_entry = vendor_agg.get((bank_store_code, date_key))
        vendor_amount = vendor_entry["amount"] if vendor_entry else None
        vendor_names = sorted(vendor_entry["vendor_names"]) if vendor_entry else []
        store_row = (
            db.query(BankStoreMaster.store_name)
            .filter(BankStoreMaster.bank_store_code == bank_store_code)
            .filter(BankStoreMaster.status == "ACTIVE")
            .first()
        )
        store_name = store_row[0] if store_row else None
        if finacle_amount is None:
            status = "MISSING_FINACLE"
            reason = "Finacle record not found for store/date"
        elif vendor_amount is None:
            status = "MISSING_VENDOR"
            reason = "Vendor record not found for store/date"
        else:
            fa, va = float(finacle_amount), float(vendor_amount)
            if abs(fa - va) < 0.01:
                status = "MATCHED"
                reason = None
            else:
                status = "AMOUNT_MISMATCH"
                reason = "Amount mismatch"

        existing = (
            db.query(ReconciliationResult)
            .filter(ReconciliationResult.bank_store_code == bank_store_code)
            .filter(ReconciliationResult.mis_date == mis_date)
            .order_by(ReconciliationResult.created_date.desc())
            .first()
        )

        has_approved_correction = False
        if existing:
            correction_row = (
                db.query(ReconciliationCorrection, ApprovalRequest)
                .join(ApprovalRequest, ApprovalRequest.approval_id == ReconciliationCorrection.approval_id)
                .filter(ReconciliationCorrection.recon_id == existing.recon_id)
                .filter(ApprovalRequest.status == "APPROVED")
                .order_by(ReconciliationCorrection.created_date.desc())
                .first()
            )
            if correction_row:
                proposed = safe_json_loads_clob(correction_row[0].proposed_data, raise_on_error=False)
                if proposed.get("requested_action") in ("AMOUNT_EDIT", "FIELD_EDIT"):
                    has_approved_correction = True

        if existing:
            recon = existing
            recon.mis_date = mis_date
            if not has_approved_correction:
                recon.pickup_date = date_key
                recon.remittance_date = date_key
                recon.pickup_amount = vendor_amount
                recon.remittance_amount = finacle_amount
                recon.status = status
                recon.reason = reason
            recon.is_final = 0
        else:
            recon = ReconciliationResult(
                finacle_canonical_id=None,
                vendor_canonical_id=None,
                bank_store_code=bank_store_code,
                mis_date=mis_date,
                pickup_date=date_key,
                remittance_date=date_key,
                pickup_amount=vendor_amount,
                remittance_amount=finacle_amount,
                status=status,
                reason=reason,
                is_final=0,
            )
            db.add(recon)
            db.flush()
        extra_by_id[recon.recon_id] = {
            "vendor_names": ", ".join(vendor_names) if vendor_names else None,
            "store_name": store_name,
        }
        if recon.status != "MATCHED":
            existing_exception = (
                db.query(ExceptionRecord)
                .filter(ExceptionRecord.recon_id == recon.recon_id)
                .filter(ExceptionRecord.status == "OPEN")
                .first()
            )
            if not existing_exception:
                db.add(
                    ExceptionRecord(
                        recon_id=recon.recon_id,
                        exception_type=status,
                        status="OPEN",
                        details=reason,
                        created_by=user.employee_id,
                    )
                )
            else:
                existing_exception.exception_type = status
                existing_exception.details = reason
        else:
            (
                db.query(ExceptionRecord)
                .filter(ExceptionRecord.recon_id == recon.recon_id)
                .filter(ExceptionRecord.status == "OPEN")
                .update(
                    {
                        "status": "RESOLVED",
                        "resolved_by": user.employee_id,
                        "resolved_date": datetime.utcnow(),
                        "remarks": "Auto-resolved after reconciliation rerun",
                    }
                )
            )
        results.append(recon)

    log_audit(
        db,
        entity_type="RECONCILIATION",
        entity_id="RUN",
        action="EXECUTE",
        old_data=None,
        new_data=f"results={len(results)},mis_date={mis_date_raw},vendor_id={vendor_id_int if vendor_id_int is not None else 'all'}",
        changed_by=user.employee_id,
    )
    db.commit()

    recon_ids = [r.recon_id for r in results]
    correction_status_by_recon = {}
    if recon_ids:
        correction_rows = (
            db.query(ReconciliationCorrection.recon_id, ApprovalRequest.status, ApprovalRequest.reason)
            .join(ApprovalRequest, ApprovalRequest.approval_id == ReconciliationCorrection.approval_id)
            .filter(ReconciliationCorrection.recon_id.in_(recon_ids))
            .order_by(ReconciliationCorrection.created_date.desc())
            .all()
        )
        for recon_id, approval_status, approval_reason in correction_rows:
            if recon_id not in correction_status_by_recon:
                correction_status_by_recon[recon_id] = {
                    "correction_status": approval_status,
                    "correction_reason": approval_reason,
                }

    payload = []
    for r in results:
        extras = extra_by_id.get(r.recon_id, {})
        corr = correction_status_by_recon.get(r.recon_id, {})
        payload.append(
            {
                "recon_id": r.recon_id,
                "bank_store_code": r.bank_store_code,
                "store_name": extras.get("store_name"),
                "vendor_names": extras.get("vendor_names"),
                "pickup_date": r.pickup_date,
                "remittance_date": r.remittance_date,
                "pickup_amount": float(r.pickup_amount) if r.pickup_amount is not None else None,
                "remittance_amount": float(r.remittance_amount)
                if r.remittance_amount is not None
                else None,
                "status": r.status,
                "reason": r.reason,
                "correction_status": corr.get("correction_status"),
                "correction_reason": corr.get("correction_reason"),
                "is_final": bool(r.is_final),
            }
        )
    db.close()
    return payload

@router.post("/save")
def save_reconciliation_final(
    payload: dict, user: AuthUser = Depends(require_roles("MAKER", "ADMIN", "CHECKER"))
):
    db = SessionLocal()
    try:
        mis_date_raw = payload.get("misDate")
        recon_ids = payload.get("recon_ids") or []
        if not mis_date_raw:
            raise HTTPException(status_code=400, detail="misDate is required")
        try:
            mis_date = datetime.strptime(mis_date_raw, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="misDate must be YYYY-MM-DD")

        if recon_ids:
            rows = (
                db.query(ReconciliationResult)
                .filter(ReconciliationResult.recon_id.in_(recon_ids))
                .all()
            )
        else:
            results = (
                db.query(ReconciliationResult)
                .filter(ReconciliationResult.mis_date == mis_date)
                .order_by(ReconciliationResult.created_date.desc())
                .all()
            )
            unique_results = {}
            for r in results:
                if r.bank_store_code not in unique_results:
                    unique_results[r.bank_store_code] = r
            rows = list(unique_results.values())

        if not rows:
            raise HTTPException(status_code=404, detail="No reconciliation results found for this date")

        not_matched = [r for r in rows if r.status != "MATCHED"]
        if not_matched:
            raise HTTPException(
                status_code=400,
                detail="Cannot save: all rows must be MATCHED. Resolve mismatches first.",
            )

        recon_ids = [r.recon_id for r in rows]
        if not payload.get("recon_ids"):
            db.query(ReconciliationResult).filter(
                (ReconciliationResult.mis_date == mis_date)
                | (
                    (ReconciliationResult.mis_date.is_(None))
                    & (
                        (ReconciliationResult.pickup_date == mis_date)
                        | (ReconciliationResult.remittance_date == mis_date)
                    )
                )
            ).update({"is_final": 0}, synchronize_session="fetch")
        db.query(ReconciliationResult).filter(ReconciliationResult.recon_id.in_(recon_ids)).update(
            {"is_final": 1, "mis_date": mis_date}, synchronize_session="fetch"
        )
        log_audit(
            db,
            entity_type="RECONCILIATION",
            entity_id="SAVE_FINAL",
            action="SAVE",
            old_data=None,
            new_data=f"mis_date={mis_date_raw},rows={len(rows)}",
            changed_by=user.employee_id,
        )
        db.commit()
        return {"status": "SAVED", "message": f"Reconciliation saved as final for {mis_date_raw}"}
    except HTTPException:
        try:
            db.rollback()
        except Exception:
            pass
        raise
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            db.close()
        except Exception:
            pass

@router.get("/results")
def list_results(misDate: str, user: AuthUser = Depends(require_roles("MAKER", "ADMIN", "CHECKER", "AUDITOR"))):
    db = SessionLocal()
    try:
        mis_date = datetime.strptime(misDate, "%Y-%m-%d").date()
    except ValueError:
        db.close()
        raise HTTPException(status_code=400, detail="misDate must be YYYY-MM-DD")

    results = (
        db.query(ReconciliationResult)
        .filter(ReconciliationResult.is_final == 1)
        .filter(
            (ReconciliationResult.mis_date == mis_date)
            | (
                (ReconciliationResult.mis_date.is_(None))
                & (
                    (ReconciliationResult.pickup_date == mis_date)
                    | (ReconciliationResult.remittance_date == mis_date)
                )
            )
        )
        .order_by(ReconciliationResult.created_date.desc())
        .all()
    )

    unique_results = {}
    for r in results:
        if r.bank_store_code not in unique_results:
            unique_results[r.bank_store_code] = r

    payload = []
    for r in unique_results.values():
        store_row = (
            db.query(BankStoreMaster.store_name)
            .filter(BankStoreMaster.bank_store_code == r.bank_store_code)
            .filter(BankStoreMaster.status == "ACTIVE")
            .first()
        )
        store_name = store_row[0] if store_row else None

        vendor_rows = (
            db.query(VendorMaster.vendor_name)
            .join(
                VendorStoreMappingMaster,
                VendorStoreMappingMaster.vendor_id == VendorMaster.vendor_id,
            )
            .filter(VendorStoreMappingMaster.bank_store_code == r.bank_store_code)
            .filter(VendorStoreMappingMaster.status == "ACTIVE")
            .all()
        )
        vendor_names = ", ".join(sorted({row[0] for row in vendor_rows if row and row[0]}))

        correction_row = (
            db.query(ReconciliationCorrection, ApprovalRequest)
            .join(ApprovalRequest, ApprovalRequest.approval_id == ReconciliationCorrection.approval_id)
            .filter(ReconciliationCorrection.recon_id == r.recon_id)
            .order_by(ReconciliationCorrection.created_date.desc())
            .first()
        )
        correction_status = None
        correction_reason = None
        if correction_row:
            correction_status = correction_row[1].status
            correction_reason = correction_row[1].reason

        payload.append(
            {
                "recon_id": r.recon_id,
                "bank_store_code": r.bank_store_code,
                "store_name": store_name,
                "vendor_names": vendor_names or None,
                "pickup_date": r.pickup_date,
                "remittance_date": r.remittance_date,
                "pickup_amount": float(r.pickup_amount) if r.pickup_amount is not None else None,
                "remittance_amount": float(r.remittance_amount)
                if r.remittance_amount is not None
                else None,
                "status": r.status,
                "reason": r.reason,
                "correction_status": correction_status,
                "correction_reason": correction_reason,
            }
        )

    db.close()
    return payload
