import io
from datetime import date, datetime, time

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
import pandas as pd

from backend.auth import AuthUser, require_roles
from backend.audit import log_audit
from backend.db import SessionLocal
from backend.utils_datetime import format_ist_date, format_ist_datetime, format_ist_time, to_utc_iso
from backend.utils_excel_export import sanitize_dataframe
from backend.models import (
    ApiLog,
    ApprovalRequest,
    AuditLog,
    BankStoreMaster,
    CanonicalTransaction,
    CustomerChargeSummary,
    ExceptionRecord,
    FinacleUploadBatch,
    ReconciliationCorrection,
    ReconciliationResult,
    VendorAbsenceRecord,
    VendorChargeSummary,
    VendorMaster,
    VendorStoreMappingMaster,
    VendorUploadBatch,
)

router = APIRouter(prefix="/api/reports", tags=["reports"])

def _xlsx_response(filename: str, rows: list[list]):
    name = filename if filename.lower().endswith(".xlsx") else f"{filename.rsplit('.', 1)[0]}.xlsx"
    buf = io.BytesIO()
    if not rows:
        df = pd.DataFrame()
    else:
        headers = [str(h) for h in rows[0]]
        body = rows[1:] if len(rows) > 1 else []
        df = pd.DataFrame(body, columns=headers)
    df = sanitize_dataframe(df)
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Report")
    buf.seek(0)
    return Response(
        content=buf.read(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )

def _vendor_charges_rows(db, from_date: str | None, to_date: str | None):
    import calendar as cal
    q = db.query(VendorChargeSummary, VendorMaster.vendor_name).outerjoin(
        VendorMaster, VendorChargeSummary.vendor_id == VendorMaster.vendor_id
    )
    if from_date and to_date:
        try:
            from_dt = datetime.strptime(from_date, "%Y-%m-%d").date()
            to_dt = datetime.strptime(to_date, "%Y-%m-%d").date()
            month_from = from_dt.strftime("%Y%m")
            month_to = to_dt.strftime("%Y%m")
            if month_from > month_to:
                month_from, month_to = month_to, month_from
            q = q.filter(VendorChargeSummary.month_key >= month_from, VendorChargeSummary.month_key <= month_to)
        except ValueError:
            pass
    items = q.order_by(VendorChargeSummary.month_key.desc(), VendorChargeSummary.vendor_id).all()
    rows = []
    for item, vendor_name in items:
        month_key = item.month_key or ""
        y, m = (int(month_key[:4]), int(month_key[4:6])) if len(month_key) >= 6 else (None, None)
        from_str = f"{y}-{m:02d}-01" if y and m else ""
        to_str = f"{y}-{m:02d}-{cal.monthrange(y, m)[1]:02d}" if y and m else ""
        rows.append({
            "Vendor": vendor_name or "",
            "Vendor ID": str(item.vendor_id),
            "Month": month_key,
            "From Date": from_str,
            "To Date": to_str,
            "Beat stores": str(item.beat_pickups),
            "Call pickups": str(item.call_pickups),
            "Base (₹)": str(item.base_charge_amount),
            "Enhancement (₹)": str(item.enhancement_charge),
            "Tax (₹)": str(item.tax_amount),
            "Total (₹)": str(item.total_with_tax),
        })
    return rows

@router.get("/vendor-charges")
def vendor_charges(
    from_date: str | None = None,
    to_date: str | None = None,
    user: AuthUser = Depends(require_roles("MAKER", "CHECKER", "ADMIN", "AUDITOR")),
):
    db = SessionLocal()
    data_rows = _vendor_charges_rows(db, from_date, to_date)
    rows = [
        ["VENDOR_ID", "VENDOR_NAME", "MONTH_KEY", "FROM_DATE", "TO_DATE", "BEAT_STORES", "CALL_PICKUPS", "BASE_CHARGE", "ENHANCEMENT_CHARGE", "TAX_AMOUNT", "TOTAL"]
    ]
    for r in data_rows:
        rows.append([
            r["Vendor ID"], r["Vendor"], r["Month"], r["From Date"], r["To Date"],
            r["Beat stores"], r["Call pickups"], r["Base (₹)"], r["Enhancement (₹)"], r["Tax (₹)"], r["Total (₹)"],
        ])
    log_audit(db, "REPORT", "VENDOR_CHARGES", "DOWNLOAD", None, f"from={from_date},to={to_date}", user.employee_id)
    db.commit()
    db.close()
    return _xlsx_response("vendor-charges.xlsx", rows)

@router.get("/vendor-charges/preview")
def vendor_charges_preview(
    from_date: str | None = None,
    to_date: str | None = None,
    user: AuthUser = Depends(require_roles("MAKER", "CHECKER", "ADMIN", "AUDITOR")),
):
    db = SessionLocal()
    rows = _vendor_charges_rows(db, from_date, to_date)
    db.close()
    return rows[:100]

@router.get("/customer-charges")
def customer_charges(
    from_date: str | None = None,
    to_date: str | None = None,
    user: AuthUser = Depends(require_roles("MAKER", "CHECKER", "ADMIN", "AUDITOR")),
):
    db = SessionLocal()
    q = db.query(CustomerChargeSummary)
    if from_date and to_date:
        try:
            from_dt = datetime.strptime(from_date, "%Y-%m-%d").date()
            to_dt = datetime.strptime(to_date, "%Y-%m-%d").date()
            month_from = from_dt.strftime("%Y%m")
            month_to = to_dt.strftime("%Y%m")
            if month_from > month_to:
                month_from, month_to = month_to, month_from
            q = q.filter(CustomerChargeSummary.month_key >= month_from, CustomerChargeSummary.month_key <= month_to)
        except ValueError:
            pass
    items = q.order_by(CustomerChargeSummary.month_key.desc(), CustomerChargeSummary.store_id).all()
    sid_list = [i.store_id for i in items]
    meta = {}
    if sid_list:
        for s in db.query(BankStoreMaster).filter(BankStoreMaster.store_id.in_(sid_list)).all():
            meta[s.store_id] = s
    rows = [
        [
            "STORE_ID",
            "BANK_STORE_CODE",
            "STORE_NAME",
            "MONTH_KEY",
            "CHARGE_PERIOD_FROM",
            "CHARGE_PERIOD_TO",
            "TOTAL_REMITTANCE",
            "BASE_CHARGE",
            "ENHANCEMENT_CHARGE",
            "DAYS_OVER_LIMIT",
            "STORE_WAIVER_RUPEES",
            "NET_CHARGE",
            "TAX_AMOUNT",
            "TOTAL",
        ]
    ]
    for item in items:
        st = meta.get(item.store_id)
        rows.append(
            [
                item.store_id,
                (st.bank_store_code if st else "") or "",
                (st.store_name if st else "") or "",
                item.month_key,
                str(item.charge_period_from) if getattr(item, "charge_period_from", None) else "",
                str(item.charge_period_to) if getattr(item, "charge_period_to", None) else "",
                str(item.total_remittance),
                str(item.base_charge_amount),
                str(item.enhancement_charge or 0),
                str(int(getattr(item, "days_over_limit", None) or 0)),
                str(getattr(item, "store_waiver_applied", None) or item.waiver_amount or 0),
                str(item.net_charge_amount),
                str(item.tax_amount),
                str(item.total_with_tax),
            ]
        )
    log_audit(db, "REPORT", "CUSTOMER_CHARGES", "DOWNLOAD", None, f"from={from_date},to={to_date}", user.employee_id)
    db.commit()
    db.close()
    return _xlsx_response("customer-charges.xlsx", rows)

@router.get("/customer-charges/preview")
def customer_charges_preview(
    from_date: str | None = None,
    to_date: str | None = None,
    user: AuthUser = Depends(require_roles("MAKER", "CHECKER", "ADMIN", "AUDITOR")),
):
    db = SessionLocal()
    q = db.query(CustomerChargeSummary)
    if from_date and to_date:
        try:
            from_dt = datetime.strptime(from_date, "%Y-%m-%d").date()
            to_dt = datetime.strptime(to_date, "%Y-%m-%d").date()
            month_from = from_dt.strftime("%Y%m")
            month_to = to_dt.strftime("%Y%m")
            if month_from > month_to:
                month_from, month_to = month_to, month_from
            q = q.filter(CustomerChargeSummary.month_key >= month_from, CustomerChargeSummary.month_key <= month_to)
        except ValueError:
            pass
    items = q.order_by(CustomerChargeSummary.month_key.desc(), CustomerChargeSummary.store_id).all()
    sid_list = [i.store_id for i in items]
    meta = {}
    if sid_list:
        for s in db.query(BankStoreMaster).filter(BankStoreMaster.store_id.in_(sid_list)).all():
            meta[s.store_id] = s
    rows = []
    for item in items:
        st = meta.get(item.store_id)
        rows.append(
            {
                "Store ID": item.store_id,
                "Store Code": (st.bank_store_code if st else "") or "",
                "Store Name": (st.store_name if st else "") or "",
                "Month": item.month_key,
                "Period from": str(item.charge_period_from) if getattr(item, "charge_period_from", None) else "",
                "Period to": str(item.charge_period_to) if getattr(item, "charge_period_to", None) else "",
                "Total Remittance (₹)": str(item.total_remittance),
                "Base (₹)": str(item.base_charge_amount),
                "Enhancement (₹)": str(item.enhancement_charge or 0),
                "Days > daily limit": str(int(getattr(item, "days_over_limit", None) or 0)),
                "Store waiver (₹)": str(getattr(item, "store_waiver_applied", None) or item.waiver_amount or 0),
                "Net (₹)": str(item.net_charge_amount),
                "Tax (₹)": str(item.tax_amount),
                "Total (₹)": str(item.total_with_tax),
            }
        )
    db.close()
    return rows[:100]

@router.get("/store-summary")
def store_summary(user: AuthUser = Depends(require_roles("MAKER", "CHECKER", "ADMIN", "AUDITOR"))):
    db = SessionLocal()
    rows = [["BANK_STORE_CODE", "STATUS", "REASON", "REMITTANCE_DATE", "PICKUP_DATE"]]
    for item in db.query(ReconciliationResult).all():
        rows.append(
            [
                item.bank_store_code,
                item.status,
                item.reason or "",
                str(item.remittance_date) if item.remittance_date else "",
                str(item.pickup_date) if item.pickup_date else "",
            ]
        )
    log_audit(db, "REPORT", "STORE_SUMMARY", "DOWNLOAD", None, None, user.employee_id)
    db.commit()
    db.close()
    return _xlsx_response("store-summary.xlsx", rows)

@router.get("/reconciliation-status")
def reconciliation_status(user: AuthUser = Depends(require_roles("MAKER", "CHECKER", "ADMIN", "AUDITOR"))):
    db = SessionLocal()
    rows = [["RECON_ID", "STATUS", "REASON", "REMITTANCE_DATE", "PICKUP_DATE"]]
    for item in db.query(ReconciliationResult).all():
        rows.append(
            [
                str(item.recon_id),
                item.status,
                item.reason or "",
                str(item.remittance_date) if item.remittance_date else "",
                str(item.pickup_date) if item.pickup_date else "",
            ]
        )
    log_audit(db, "REPORT", "RECON_STATUS", "DOWNLOAD", None, None, user.employee_id)
    db.commit()
    db.close()
    return _xlsx_response("reconciliation-status.xlsx", rows)

@router.get("/exception-aging")
def exception_aging(user: AuthUser = Depends(require_roles("MAKER", "CHECKER", "ADMIN", "AUDITOR"))):
    db = SessionLocal()
    rows = [["EXCEPTION_ID", "STATUS", "AGE_DAYS"]]
    now = datetime.utcnow()
    for item in db.query(ExceptionRecord).all():
        age_days = (now - item.created_date).days if item.created_date else 0
        rows.append([str(item.exception_id), item.status, str(age_days)])
    log_audit(db, "REPORT", "EXCEPTION_AGING", "DOWNLOAD", None, None, user.employee_id)
    db.commit()
    db.close()
    return _xlsx_response("exception-aging.xlsx", rows)

@router.get("/audit-logs/list")
def audit_logs_list(
    user: AuthUser = Depends(require_roles("ADMIN", "AUDITOR")),
    limit: int = Query(500, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    entity_type: str | None = Query(None, description="Filter by entity type"),
    from_date: str | None = Query(None, description="From date YYYY-MM-DD"),
    to_date: str | None = Query(None, description="To date YYYY-MM-DD"),
):
    db = SessionLocal()
    q = db.query(AuditLog).order_by(AuditLog.changed_at.desc())
    if entity_type and entity_type.strip():
        q = q.filter(AuditLog.entity_type == entity_type.strip().upper())
    if from_date:
        try:
            from_dt = datetime.strptime(from_date, "%Y-%m-%d").date()
            q = q.filter(AuditLog.changed_at >= datetime.combine(from_dt, time.min))
        except ValueError:
            pass
    if to_date:
        try:
            to_dt = datetime.strptime(to_date, "%Y-%m-%d").date()
            q = q.filter(AuditLog.changed_at <= datetime.combine(to_dt, time.max))
        except ValueError:
            pass
    total = q.count()
    items = q.offset(offset).limit(limit).all()
    rows = []
    for item in items:
        changed_at = item.changed_at
        rows.append(
            {
                "audit_id": item.audit_id,
                "entity_type": item.entity_type,
                "entity_id": item.entity_id,
                "action": item.action,
                "old_data": item.old_data,
                "new_data": item.new_data,
                "changed_by": item.changed_by,
                "changed_at": to_utc_iso(changed_at),
            }
        )
    db.close()
    return {"total": total, "items": rows, "limit": limit, "offset": offset}

@router.get("/audit-logs")
def audit_logs(
    user: AuthUser = Depends(require_roles("ADMIN", "AUDITOR")),
    entity_type: str | None = Query(None),
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
):
    db = SessionLocal()
    q = db.query(AuditLog).order_by(AuditLog.changed_at.desc())
    if entity_type and entity_type.strip():
        q = q.filter(AuditLog.entity_type == entity_type.strip().upper())
    if from_date:
        try:
            from_dt = datetime.strptime(from_date, "%Y-%m-%d").date()
            q = q.filter(AuditLog.changed_at >= datetime.combine(from_dt, time.min))
        except ValueError:
            pass
    if to_date:
        try:
            to_dt = datetime.strptime(to_date, "%Y-%m-%d").date()
            q = q.filter(AuditLog.changed_at <= datetime.combine(to_dt, time.max))
        except ValueError:
            pass
    rows = [["ENTITY_TYPE", "ENTITY_ID", "ACTION", "CHANGED_BY", "CHANGED_DATE (IST)", "CHANGED_TIME (IST)", "OLD_DATA", "NEW_DATA"]]
    for item in q.all():
        changed_at = item.changed_at
        changed_date = format_ist_date(changed_at)
        changed_time = format_ist_time(changed_at)
        rows.append(
            [
                item.entity_type,
                item.entity_id or "",
                item.action,
                item.changed_by,
                changed_date,
                changed_time,
                (item.old_data or "")[:4000],
                (item.new_data or "")[:4000],
            ]
        )
    log_audit(db, "REPORT", "AUDIT_LOGS", "DOWNLOAD", None, None, user.employee_id)
    db.commit()
    db.close()
    return _xlsx_response("audit-logs.xlsx", rows)

@router.get("/api-logs/list")
def api_logs_list(
    user: AuthUser = Depends(require_roles("ADMIN", "AUDITOR")),
    limit: int = Query(500, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    status_code: int | None = Query(None, description="Filter by HTTP status code"),
    from_date: str | None = Query(None, description="From date YYYY-MM-DD"),
    to_date: str | None = Query(None, description="To date YYYY-MM-DD"),
):
    db = SessionLocal()
    q = db.query(ApiLog).order_by(ApiLog.created_at.desc())
    if status_code is not None:
        q = q.filter(ApiLog.status_code == status_code)
    if from_date:
        try:
            from_dt = datetime.strptime(from_date, "%Y-%m-%d").date()
            q = q.filter(ApiLog.created_at >= datetime.combine(from_dt, time.min))
        except ValueError:
            pass
    if to_date:
        try:
            to_dt = datetime.strptime(to_date, "%Y-%m-%d").date()
            q = q.filter(ApiLog.created_at <= datetime.combine(to_dt, time.max))
        except ValueError:
            pass
    total = q.count()
    items = q.offset(offset).limit(limit).all()
    rows = []
    for item in items:
        created_at = item.created_at
        rows.append(
            {
                "log_id": item.log_id,
                "method": item.method,
                "path": item.path,
                "status_code": item.status_code,
                "level": item.log_level,
                "message": item.message,
                "detail": item.detail,
                "user_id": item.user_id,
                "created_at": to_utc_iso(created_at),
            }
        )
    db.close()
    return {"total": total, "items": rows, "limit": limit, "offset": offset}

@router.get("/api-logs")
def api_logs_csv(
    user: AuthUser = Depends(require_roles("ADMIN", "AUDITOR")),
    status_code: int | None = Query(None),
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
):
    db = SessionLocal()
    q = db.query(ApiLog).order_by(ApiLog.created_at.desc())
    if status_code is not None:
        q = q.filter(ApiLog.status_code == status_code)
    if from_date:
        try:
            from_dt = datetime.strptime(from_date, "%Y-%m-%d").date()
            q = q.filter(ApiLog.created_at >= datetime.combine(from_dt, time.min))
        except ValueError:
            pass
    if to_date:
        try:
            to_dt = datetime.strptime(to_date, "%Y-%m-%d").date()
            q = q.filter(ApiLog.created_at <= datetime.combine(to_dt, time.max))
        except ValueError:
            pass
    rows = [["METHOD", "PATH", "STATUS_CODE", "LEVEL", "MESSAGE", "DETAIL", "USER_ID", "CREATED_AT (IST)"]]
    for item in q.all():
        created_at = item.created_at
        rows.append(
            [
                item.method or "",
                item.path or "",
                str(item.status_code or ""),
                item.log_level or "",
                (item.message or "")[:4000],
                (item.detail or "")[:4000],
                item.user_id or "",
                format_ist_datetime(created_at),
            ]
        )
    db.close()
    return _xlsx_response("api-logs.xlsx", rows)

def _vendor_pickups_rows(db, vendor_id: int, from_dt, to_dt, store_id: int | None = None):
    vendor = db.query(VendorMaster).filter(VendorMaster.vendor_id == vendor_id).first()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    store_code_filter: str | None = None
    if store_id is not None:
        store_obj = (
            db.query(BankStoreMaster).filter(BankStoreMaster.store_id == store_id).first()
        )
        if not store_obj:
            raise HTTPException(status_code=404, detail="Store not found")
        store_code_filter = str(store_obj.bank_store_code or "").strip() or None
        if not store_code_filter:
            return vendor, []

    txn_query = (
        db.query(CanonicalTransaction)
        .filter(CanonicalTransaction.source == "VENDOR")
        .filter(CanonicalTransaction.pickup_date >= from_dt)
        .filter(CanonicalTransaction.pickup_date <= to_dt)
    )
    if store_code_filter is not None:
        txn_query = txn_query.filter(
            CanonicalTransaction.bank_store_code == store_code_filter
        )
    txns = txn_query.all()

    rows = []
    for txn in txns:
        mapping = (
            db.query(VendorStoreMappingMaster)
            .filter(VendorStoreMappingMaster.vendor_id == vendor_id)
            .filter(VendorStoreMappingMaster.vendor_store_code == txn.vendor_store_code)
            .filter(VendorStoreMappingMaster.bank_store_code == txn.bank_store_code)
            .filter(VendorStoreMappingMaster.status == "ACTIVE")
            .filter(VendorStoreMappingMaster.effective_from <= txn.pickup_date)
            .filter(
                (VendorStoreMappingMaster.effective_to.is_(None))
                | (VendorStoreMappingMaster.effective_to >= txn.pickup_date)
            )
            .first()
        )
        if not mapping:
            continue

        store_row = (
            db.query(BankStoreMaster.store_name)
            .filter(BankStoreMaster.bank_store_code == txn.bank_store_code)
            .filter(BankStoreMaster.status == "ACTIVE")
            .filter(BankStoreMaster.effective_from <= txn.pickup_date)
            .filter(
                (BankStoreMaster.effective_to.is_(None))
                | (BankStoreMaster.effective_to >= txn.pickup_date)
            )
            .first()
        )
        store_name = store_row[0] if store_row else ""

        rows.append(
            {
                "Vendor Name": vendor.vendor_name,
                "Bank Store Code": txn.bank_store_code,
                "Store Name": store_name,
                "Vendor Store Code": txn.vendor_store_code or "",
                "Pickup Date": str(txn.pickup_date) if txn.pickup_date else "",
                "Pickup Amount": str(txn.pickup_amount) if txn.pickup_amount is not None else "",
                "Pickup Type": txn.pickup_type or "",
                "Account No": txn.account_no or "",
                "Customer ID": txn.customer_id or "",
            }
        )
    return vendor, rows

@router.get("/vendor-pickups")
def vendor_pickups(
    vendor_id: int,
    from_date: str,
    to_date: str,
    store_id: int | None = None,
    user: AuthUser = Depends(require_roles("MAKER", "CHECKER", "ADMIN", "AUDITOR")),
):
    db = SessionLocal()
    try:
        from_dt = datetime.strptime(from_date, "%Y-%m-%d").date()
        to_dt = datetime.strptime(to_date, "%Y-%m-%d").date()
    except ValueError:
        db.close()
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")

    vendor, rows = _vendor_pickups_rows(db, vendor_id, from_dt, to_dt, store_id=store_id)

    df = sanitize_dataframe(pd.DataFrame(rows))
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Vendor Pickups")
    output.seek(0)

    log_audit(
        db,
        "REPORT",
        "VENDOR_PICKUPS",
        "DOWNLOAD",
        None,
        f"vendor_id={vendor_id},from={from_date},to={to_date},store_id={store_id}",
        user.employee_id,
    )
    db.commit()
    db.close()
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="vendor-pickups.xlsx"'},
    )

@router.get("/vendor-pickups/preview")
def vendor_pickups_preview(
    vendor_id: int,
    from_date: str,
    to_date: str,
    store_id: int | None = None,
    user: AuthUser = Depends(require_roles("MAKER", "CHECKER", "ADMIN", "AUDITOR")),
):
    db = SessionLocal()
    try:
        from_dt = datetime.strptime(from_date, "%Y-%m-%d").date()
        to_dt = datetime.strptime(to_date, "%Y-%m-%d").date()
    except ValueError:
        db.close()
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")

    _, rows = _vendor_pickups_rows(db, vendor_id, from_dt, to_dt, store_id=store_id)
    db.close()
    return rows[:50]

def _vendor_absence_rows(db, from_dt, to_dt, vendor_id: int | None = None):
    finacle_batches = (
        db.query(FinacleUploadBatch)
        .filter(FinacleUploadBatch.mis_date >= from_dt)
        .filter(FinacleUploadBatch.mis_date <= to_dt)
        .filter(FinacleUploadBatch.status == "PROCESSED")
        .all()
    )
    if not finacle_batches:
        return []

    finacle_store_dates: set[tuple[str, date]] = set()
    for batch in finacle_batches:
        mis_d = batch.mis_date
        if not mis_d:
            continue
        for (raw_store,) in (
            db.query(CanonicalTransaction.bank_store_code)
            .filter(CanonicalTransaction.source == "FINACLE")
            .filter(CanonicalTransaction.raw_batch_id == batch.batch_id)
            .all()
        ):
            store = str(raw_store or "").strip()
            if store:
                finacle_store_dates.add((store, mis_d))
    if not finacle_store_dates:
        return []

    expected_stores = {s for (s, _) in finacle_store_dates}
    beat_codes: set[str] = set()
    store_name_by_code: dict[str, str] = {}
    for code, pt, name in (
        db.query(
            BankStoreMaster.bank_store_code,
            BankStoreMaster.pickup_type,
            BankStoreMaster.store_name,
        )
        .filter(BankStoreMaster.bank_store_code.in_(expected_stores))
        .filter(BankStoreMaster.status == "ACTIVE")
        .all()
    ):
        code_s = str(code or "").strip()
        if not code_s:
            continue
        store_name_by_code[code_s] = name or ""
        if (str(pt or "BEAT").strip().upper()) == "BEAT":
            beat_codes.add(code_s)

    dates_by_store: dict[str, set] = {}
    for store, d in finacle_store_dates:
        if store in beat_codes:
            dates_by_store.setdefault(store, set()).add(d)
    if not dates_by_store:
        return []

    vendor_batches = (
        db.query(VendorUploadBatch)
        .filter(VendorUploadBatch.mis_date >= from_dt)
        .filter(VendorUploadBatch.mis_date <= to_dt)
        .filter(VendorUploadBatch.status == "PROCESSED")
        .all()
    )
    vendor_id_by_batch = {b.batch_id: b.vendor_id for b in vendor_batches}
    mis_by_batch = {b.batch_id: b.mis_date for b in vendor_batches}
    vendor_pickups: set[tuple[int, str, date]] = set()
    if vendor_id_by_batch:
        for batch_id, raw_store in (
            db.query(
                CanonicalTransaction.raw_batch_id,
                CanonicalTransaction.bank_store_code,
            )
            .filter(CanonicalTransaction.source == "VENDOR")
            .filter(CanonicalTransaction.raw_batch_id.in_(list(vendor_id_by_batch.keys())))
            .all()
        ):
            vid = vendor_id_by_batch.get(batch_id)
            mis_d = mis_by_batch.get(batch_id)
            store = str(raw_store or "").strip()
            if vid is None or mis_d is None or not store:
                continue
            vendor_pickups.add((int(vid), store, mis_d))

    mappings_q = (
        db.query(VendorStoreMappingMaster, VendorMaster.vendor_name, VendorMaster.vendor_code)
        .join(VendorMaster, VendorStoreMappingMaster.vendor_id == VendorMaster.vendor_id)
        .filter(VendorStoreMappingMaster.status == "ACTIVE")
        .filter(VendorStoreMappingMaster.effective_from <= to_dt)
        .filter(
            (VendorStoreMappingMaster.effective_to.is_(None))
            | (VendorStoreMappingMaster.effective_to >= from_dt)
        )
    )
    if vendor_id is not None:
        mappings_q = mappings_q.filter(VendorStoreMappingMaster.vendor_id == vendor_id)

    absences: list[dict] = []
    seen: set[tuple[int, str, date]] = set()
    for mapping, vname, vcode in mappings_q.all():
        vid = int(mapping.vendor_id)
        bank_store = str(mapping.bank_store_code or "").strip()
        if not bank_store:
            continue
        expected_dates = dates_by_store.get(bank_store)
        if not expected_dates:
            continue
        eff_from = mapping.effective_from
        eff_to = mapping.effective_to
        vendor_store = str(mapping.vendor_store_code or "").strip()
        for date_val in expected_dates:
            if eff_from and date_val < eff_from:
                continue
            if eff_to and date_val > eff_to:
                continue
            if (vid, bank_store, date_val) in vendor_pickups:
                continue
            key = (vid, bank_store, date_val)
            if key in seen:
                continue
            seen.add(key)
            absences.append(
                {
                    "vendor_id": vid,
                    "vendor_name": vname or "",
                    "vendor_code": vcode or "",
                    "bank_store_code": bank_store,
                    "store_name": store_name_by_code.get(bank_store, ""),
                    "vendor_store_code": vendor_store,
                    "absence_date": date_val.isoformat() if hasattr(date_val, "isoformat") else str(date_val),
                }
            )

    return sorted(absences, key=lambda x: (x["absence_date"], x["vendor_name"], x["bank_store_code"]))

def _vendor_absence_from_stored(db, from_dt, to_dt, vendor_id: int | None = None):
    q = (
        db.query(VendorAbsenceRecord, VendorMaster.vendor_name, VendorMaster.vendor_code)
        .join(VendorMaster, VendorAbsenceRecord.vendor_id == VendorMaster.vendor_id)
        .filter(VendorAbsenceRecord.absence_date >= from_dt)
        .filter(VendorAbsenceRecord.absence_date <= to_dt)
    )
    if vendor_id is not None:
        q = q.filter(VendorAbsenceRecord.vendor_id == vendor_id)
    rows = q.order_by(VendorAbsenceRecord.absence_date, VendorMaster.vendor_name).all()
    return [
        {
            "vendor_id": r.vendor_id,
            "vendor_name": vname or "",
            "vendor_code": vcode or "",
            "bank_store_code": r.bank_store_code or "",
            "store_name": r.store_name or "",
            "vendor_store_code": r.vendor_store_code or "",
            "absence_date": str(r.absence_date) if r.absence_date else "",
        }
        for r, vname, vcode in rows
    ]

def _parse_date_range(from_date: str, to_date: str):
    try:
        return (
            datetime.strptime(from_date, "%Y-%m-%d").date(),
            datetime.strptime(to_date, "%Y-%m-%d").date(),
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")

@router.post("/vendor-absence/detect")
def vendor_absence_detect(
    from_date: str = Query(..., description="From date YYYY-MM-DD"),
    to_date: str = Query(..., description="To date YYYY-MM-DD"),
    user: AuthUser = Depends(require_roles("MAKER", "CHECKER", "ADMIN")),
):
    from_dt, to_dt = _parse_date_range(from_date, to_date)
    db = SessionLocal()
    try:
        rows = _vendor_absence_rows(db, from_dt, to_dt, vendor_id=None)
        db.query(VendorAbsenceRecord).filter(
            VendorAbsenceRecord.absence_date >= from_dt,
            VendorAbsenceRecord.absence_date <= to_dt,
        ).delete(synchronize_session=False)
        inserted = 0
        for r in rows:
            ad = r.get("absence_date")
            if not ad:
                continue
            try:
                absence_dt = datetime.strptime(str(ad), "%Y-%m-%d").date()
            except ValueError:
                continue
            db.add(
                VendorAbsenceRecord(
                    vendor_id=r["vendor_id"],
                    bank_store_code=r["bank_store_code"],
                    vendor_store_code=r.get("vendor_store_code") or None,
                    store_name=r.get("store_name") or None,
                    absence_date=absence_dt,
                    recorded_by=user.employee_id,
                )
            )
            inserted += 1
        log_audit(db, "REPORT", "VENDOR_ABSENCE", "DETECT", None,
                  f"from={from_date},to={to_date},count={inserted}", user.employee_id)
        db.commit()
        return {"recorded": inserted, "from_date": from_date, "to_date": to_date}
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to detect vendor absences")
    finally:
        db.close()

@router.get("/vendor-absence")
def vendor_absence(
    from_date: str = Query(..., description="From date YYYY-MM-DD"),
    to_date: str = Query(..., description="To date YYYY-MM-DD"),
    vendor_id: int | None = Query(None, description="Filter by vendor ID"),
    use_stored: bool = Query(False, description="Read from stored records (run detect first)"),
    user: AuthUser = Depends(require_roles("MAKER", "CHECKER", "ADMIN", "AUDITOR")),
):
    from_dt, to_dt = _parse_date_range(from_date, to_date)
    db = SessionLocal()
    try:
        rows = (
            _vendor_absence_from_stored(db, from_dt, to_dt, vendor_id)
            if use_stored
            else _vendor_absence_rows(db, from_dt, to_dt, vendor_id)
        )
        return {"items": rows, "total": len(rows)}
    finally:
        db.close()

@router.get("/vendor-absence/download")
def vendor_absence_download(
    from_date: str = Query(..., description="From date YYYY-MM-DD"),
    to_date: str = Query(..., description="To date YYYY-MM-DD"),
    vendor_id: int | None = Query(None, description="Filter by vendor ID"),
    use_stored: bool = Query(False, description="Read from stored records (run detect first)"),
    user: AuthUser = Depends(require_roles("MAKER", "CHECKER", "ADMIN", "AUDITOR")),
):
    from_dt, to_dt = _parse_date_range(from_date, to_date)
    db = SessionLocal()
    try:
        rows = (
            _vendor_absence_from_stored(db, from_dt, to_dt, vendor_id)
            if use_stored
            else _vendor_absence_rows(db, from_dt, to_dt, vendor_id)
        )
        header = ["Vendor ID", "Vendor Name", "Vendor Code", "Bank Store Code",
                  "Store Name", "Vendor Store Code", "Absence Date"]
        csv_rows = [header] + [
            [str(r.get(k, "")) for k in [
                "vendor_id", "vendor_name", "vendor_code", "bank_store_code",
                "store_name", "vendor_store_code", "absence_date",
            ]]
            for r in rows
        ]
        log_audit(db, "REPORT", "VENDOR_ABSENCE", "DOWNLOAD", None,
                  f"from={from_date},to={to_date},vendor_id={vendor_id}", user.employee_id)
        db.commit()
        return _xlsx_response("vendor-absence.xlsx", csv_rows)
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to build vendor absence report")
    finally:
        db.close()

@router.get("/customers")
def list_customers(user: AuthUser = Depends(require_roles("MAKER", "CHECKER", "ADMIN", "AUDITOR"))):
    db = SessionLocal()
    rows = (
        db.query(VendorStoreMappingMaster.customer_id, VendorStoreMappingMaster.customer_name)
        .filter(VendorStoreMappingMaster.customer_id.is_not(None))
        .distinct()
        .all()
    )
    payload = [
        {"customer_id": row[0], "customer_name": row[1] or ""} for row in rows if row and row[0]
    ]
    db.close()
    return payload

def _customer_pickups_rows(db, customer_id: str, from_dt, to_dt):
    rows = []
    txns = (
        db.query(CanonicalTransaction)
        .filter(CanonicalTransaction.source == "VENDOR")
        .filter(CanonicalTransaction.pickup_date >= from_dt)
        .filter(CanonicalTransaction.pickup_date <= to_dt)
        .all()
    )

    for txn in txns:
        mapping = (
            db.query(VendorStoreMappingMaster, VendorMaster)
            .join(VendorMaster, VendorStoreMappingMaster.vendor_id == VendorMaster.vendor_id)
            .filter(VendorStoreMappingMaster.customer_id == customer_id)
            .filter(VendorStoreMappingMaster.vendor_store_code == txn.vendor_store_code)
            .filter(VendorStoreMappingMaster.bank_store_code == txn.bank_store_code)
            .filter(VendorStoreMappingMaster.status == "ACTIVE")
            .filter(VendorStoreMappingMaster.effective_from <= txn.pickup_date)
            .filter(
                (VendorStoreMappingMaster.effective_to.is_(None))
                | (VendorStoreMappingMaster.effective_to >= txn.pickup_date)
            )
            .first()
        )
        if not mapping:
            continue
        mapping_row, vendor = mapping

        store_row = (
            db.query(BankStoreMaster.store_name)
            .filter(BankStoreMaster.bank_store_code == txn.bank_store_code)
            .filter(BankStoreMaster.status == "ACTIVE")
            .filter(BankStoreMaster.effective_from <= txn.pickup_date)
            .filter(
                (BankStoreMaster.effective_to.is_(None))
                | (BankStoreMaster.effective_to >= txn.pickup_date)
            )
            .first()
        )
        store_name = store_row[0] if store_row else ""

        rows.append(
            {
                "Customer ID": mapping_row.customer_id or "",
                "Customer Name": mapping_row.customer_name or "",
                "Vendor Name": vendor.vendor_name,
                "Bank Store Code": txn.bank_store_code,
                "Store Name": store_name,
                "Vendor Store Code": txn.vendor_store_code or "",
                "Pickup Date": str(txn.pickup_date) if txn.pickup_date else "",
                "Pickup Amount": str(txn.pickup_amount) if txn.pickup_amount is not None else "",
                "Pickup Type": txn.pickup_type or "",
                "Account No": txn.account_no or "",
            }
        )
    return rows

@router.get("/customer-pickups")
def customer_pickups(
    customer_id: str,
    from_date: str,
    to_date: str,
    user: AuthUser = Depends(require_roles("MAKER", "CHECKER", "ADMIN", "AUDITOR")),
):
    db = SessionLocal()
    try:
        from_dt = datetime.strptime(from_date, "%Y-%m-%d").date()
        to_dt = datetime.strptime(to_date, "%Y-%m-%d").date()
    except ValueError:
        db.close()
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")

    rows = _customer_pickups_rows(db, customer_id, from_dt, to_dt)
    df = sanitize_dataframe(pd.DataFrame(rows))
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Customer Pickups")
    output.seek(0)

    log_audit(
        db,
        "REPORT",
        "CUSTOMER_PICKUPS",
        "DOWNLOAD",
        None,
        f"customer_id={customer_id},from={from_date},to={to_date}",
        user.employee_id,
    )
    db.commit()
    db.close()
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="customer-pickups.xlsx"'},
    )

@router.get("/customer-pickups/preview")
def customer_pickups_preview(
    customer_id: str,
    from_date: str,
    to_date: str,
    user: AuthUser = Depends(require_roles("MAKER", "CHECKER", "ADMIN", "AUDITOR")),
):
    db = SessionLocal()
    try:
        from_dt = datetime.strptime(from_date, "%Y-%m-%d").date()
        to_dt = datetime.strptime(to_date, "%Y-%m-%d").date()
    except ValueError:
        db.close()
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")

    rows = _customer_pickups_rows(db, customer_id, from_dt, to_dt)
    db.close()
    return rows[:50]

def _recon_final_rows(db, from_dt, to_dt):
    results = (
        db.query(ReconciliationResult)
        .filter(ReconciliationResult.is_final == 1)
        .filter(
            (
                (ReconciliationResult.mis_date >= from_dt)
                & (ReconciliationResult.mis_date <= to_dt)
            )
            | (
                (ReconciliationResult.mis_date.is_(None))
                & (
                    (
                        (ReconciliationResult.pickup_date >= from_dt)
                        & (ReconciliationResult.pickup_date <= to_dt)
                    )
                    | (
                        (ReconciliationResult.remittance_date >= from_dt)
                        & (ReconciliationResult.remittance_date <= to_dt)
                    )
                )
            )
        )
        .order_by(ReconciliationResult.created_date.desc())
        .all()
    )

    latest_status = {}
    correction_rows = (
        db.query(ReconciliationCorrection, ApprovalRequest)
        .join(ApprovalRequest, ApprovalRequest.approval_id == ReconciliationCorrection.approval_id)
        .order_by(ReconciliationCorrection.created_date.desc())
        .all()
    )
    for correction, approval in correction_rows:
        if correction.recon_id not in latest_status:
            latest_status[correction.recon_id] = approval.status

    rows = []
    for item in results:
        status = latest_status.get(item.recon_id)
        if status and status != "APPROVED":
            continue

        date_key = item.remittance_date or item.pickup_date
        store_row = (
            db.query(BankStoreMaster.store_name)
            .filter(BankStoreMaster.bank_store_code == item.bank_store_code)
            .filter(BankStoreMaster.status == "ACTIVE")
            .filter(BankStoreMaster.effective_from <= date_key)
            .filter(
                (BankStoreMaster.effective_to.is_(None))
                | (BankStoreMaster.effective_to >= date_key)
            )
            .first()
        )
        store_name = store_row[0] if store_row else ""

        vendor_rows = (
            db.query(VendorMaster.vendor_name)
            .join(
                VendorStoreMappingMaster,
                VendorStoreMappingMaster.vendor_id == VendorMaster.vendor_id,
            )
            .filter(VendorStoreMappingMaster.bank_store_code == item.bank_store_code)
            .filter(VendorStoreMappingMaster.status == "ACTIVE")
            .filter(VendorStoreMappingMaster.effective_from <= date_key)
            .filter(
                (VendorStoreMappingMaster.effective_to.is_(None))
                | (VendorStoreMappingMaster.effective_to >= date_key)
            )
            .all()
        )
        vendor_names = ", ".join(sorted({row[0] for row in vendor_rows if row and row[0]}))

        rows.append(
            {
                "Bank Store Code": item.bank_store_code,
                "Store Name": store_name,
                "Vendor Names": vendor_names,
                "Pickup Date": str(item.pickup_date) if item.pickup_date else "",
                "Pickup Amount": str(item.pickup_amount) if item.pickup_amount is not None else "",
                "Remittance Date": str(item.remittance_date) if item.remittance_date else "",
                "Remittance Amount": str(item.remittance_amount) if item.remittance_amount is not None else "",
                "Status": item.status,
                "Reason": item.reason or "",
            }
        )
    return rows

@router.get("/reconciliation-final")
def reconciliation_final(
    from_date: str,
    to_date: str,
    user: AuthUser = Depends(require_roles("MAKER", "CHECKER", "ADMIN", "AUDITOR")),
):
    db = SessionLocal()
    try:
        from_dt = datetime.strptime(from_date, "%Y-%m-%d").date()
        to_dt = datetime.strptime(to_date, "%Y-%m-%d").date()
    except ValueError:
        db.close()
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")

    rows = _recon_final_rows(db, from_dt, to_dt)
    df = sanitize_dataframe(pd.DataFrame(rows))
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Reconciliation Final")
    output.seek(0)

    log_audit(
        db,
        "REPORT",
        "RECON_FINAL",
        "DOWNLOAD",
        None,
        f"from={from_date},to={to_date}",
        user.employee_id,
    )
    db.commit()
    db.close()
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="reconciliation-final.xlsx"'},
    )

@router.get("/reconciliation-final/preview")
def reconciliation_final_preview(
    from_date: str,
    to_date: str,
    user: AuthUser = Depends(require_roles("MAKER", "CHECKER", "ADMIN", "AUDITOR")),
):
    db = SessionLocal()
    try:
        from_dt = datetime.strptime(from_date, "%Y-%m-%d").date()
        to_dt = datetime.strptime(to_date, "%Y-%m-%d").date()
    except ValueError:
        db.close()
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")

    rows = _recon_final_rows(db, from_dt, to_dt)
    db.close()
    return rows[:50]
