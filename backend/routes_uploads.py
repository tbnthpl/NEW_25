import io
import json
from datetime import datetime
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import joinedload

from backend.auth import AuthUser, require_roles
from backend.audit import log_audit
from backend.db import SessionLocal
from backend.models import (
    BankStoreMaster,
    CanonicalTransaction,
    FinacleInvalidRecord,
    FinacleRawStaging,
    FinacleUploadBatch,
    RemittanceEntry,
    VendorInvalidRecord,
    VendorRawStaging,
    VendorStoreMappingMaster,
    VendorUploadBatch,
    VendorFileFormatConfig,
    VendorMaster,
)
from backend.schemas import UploadResponse
from backend.utils_approval import safe_json_loads_clob
from backend.utils_bulk_upload import EXCEL_MAX_ROWS
from backend.utils_finacle import get_finacle_mapping, get_finacle_required_headers
from backend.utils_month_lock import enforce_month_unlocked
from backend.utils_excel_export import sanitize_dataframe
from backend.utils_upload_security import read_validated_excel_upload

router = APIRouter(prefix="/api/uploads", tags=["uploads"])

PAYLOAD_MAX_LEN = 4000

def _truncate_payload(s: str) -> str:
    if not s or len(s) <= PAYLOAD_MAX_LEN:
        return s
    return s[:PAYLOAD_MAX_LEN]

def _row_to_payload(row) -> str:
    rec = pd.DataFrame([row]).to_json(orient="records", date_format="iso")
    return rec[1:-1] if len(rec) > 2 else "{}"

def _parse_date(value):
    if pd.isna(value):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, (int, float)) and 1000 < value < 1000000:
        try:
            return (pd.Timestamp("1899-12-30") + pd.Timedelta(days=float(value))).date()
        except Exception:
            pass
    try:
        return pd.to_datetime(value, dayfirst=True).date()
    except Exception:
        return None

def _parse_number(value):
    if pd.isna(value):
        return None
    try:
        return float(value)
    except Exception:
        return None

def _normalize_store_code(value):
    if pd.isna(value):
        return ""
    if isinstance(value, (int, float)):
        if value == int(value):
            return str(int(value))
        return str(value)
    return str(value).strip()

def _load_vendor_format(db, vendor_id):
    return (
        db.query(VendorFileFormatConfig)
        .options(joinedload(VendorFileFormatConfig.header_mappings))
        .filter(VendorFileFormatConfig.vendor_id == vendor_id)
        .filter(VendorFileFormatConfig.status == "ACTIVE")
        .order_by(VendorFileFormatConfig.effective_from.desc())
        .first()
    )

def _format_mapping_dict(format_config):
    return {m.mapping_key: m.source_column for m in (format_config.header_mappings or [])}

def _lookup_mapping(db, vendor_id, vendor_store_code, as_of_date):
    return (
        db.query(VendorStoreMappingMaster)
        .filter(VendorStoreMappingMaster.vendor_id == vendor_id)
        .filter(VendorStoreMappingMaster.vendor_store_code == vendor_store_code)
        .filter(VendorStoreMappingMaster.status == "ACTIVE")
        .filter(VendorStoreMappingMaster.effective_from <= as_of_date)
        .filter(
            (VendorStoreMappingMaster.effective_to.is_(None))
            | (VendorStoreMappingMaster.effective_to >= as_of_date)
        )
        .first()
    )

def _lookup_mapping_lenient(db, vendor_id, vendor_store_code):
    return (
        db.query(VendorStoreMappingMaster)
        .filter(VendorStoreMappingMaster.vendor_id == vendor_id)
        .filter(VendorStoreMappingMaster.vendor_store_code == vendor_store_code)
        .filter(VendorStoreMappingMaster.status == "ACTIVE")
        .order_by(VendorStoreMappingMaster.effective_from.desc())
        .first()
    )

def _read_excel_dataframe(file: UploadFile) -> pd.DataFrame:
    content = read_validated_excel_upload(file)
    try:
        df = pd.read_excel(io.BytesIO(content), nrows=EXCEL_MAX_ROWS + 1)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid or unsupported Excel file.") from exc
    if len(df) > EXCEL_MAX_ROWS:
        raise HTTPException(
            status_code=413,
            detail=f"Workbook exceeds {EXCEL_MAX_ROWS:,} rows. Split the file and try again.",
        )
    return df

def _can_view_batch(user: AuthUser, uploaded_by: str | None) -> bool:
    return True

def _can_delete_batch(user: AuthUser, uploaded_by: str | None) -> bool:
    return user.role == "ADMIN" or uploaded_by == user.employee_id

@router.post("/finacle/validate")
def validate_finacle_upload(
    misDate: str = Form(...),
    file: UploadFile = File(...),
    user: AuthUser = Depends(require_roles("MAKER", "CHECKER", "ADMIN", "AUDITOR")),
):
    db = SessionLocal()
    try:
        mapping = get_finacle_mapping(db)
        required_headers = get_finacle_required_headers(mapping)
        mis_date = pd.to_datetime(misDate).date()
        df = _read_excel_dataframe(file)
    except Exception:
        db.close()
        raise
    df.columns = [str(c).strip() for c in df.columns]
    headers = set(df.columns)
    missing_headers = required_headers - headers
    if missing_headers:
        db.close()
        raise HTTPException(
            status_code=400, detail=f"Missing required headers: {', '.join(sorted(missing_headers))}"
        )
    store_rows = (
        db.query(BankStoreMaster.bank_store_code)
        .filter(BankStoreMaster.status == "ACTIVE")
        .filter(BankStoreMaster.effective_from <= mis_date)
        .filter(
            (BankStoreMaster.effective_to.is_(None))
            | (BankStoreMaster.effective_to >= mis_date)
        )
        .all()
    )
    valid_stores = {str(row[0]).strip() for row in store_rows if row and row[0]}
    valid_stores_normalized = {}
    for code in valid_stores:
        if code:
            valid_stores_normalized[code] = code
            valid_stores_normalized[code.upper()] = code
            valid_stores_normalized[code.lower()] = code
            try:
                n = int(float(code))
                valid_stores_normalized[str(n)] = code
            except (ValueError, TypeError):
                pass
    missing_store_codes = set()
    for _, row in df.iterrows():
        raw = _normalize_store_code(row.get(mapping.get("store_code_column", "STORE_CODE"), ""))
        if not raw:
            continue
        resolved = (
            valid_stores_normalized.get(raw)
            or valid_stores_normalized.get(raw.upper())
            or valid_stores_normalized.get(raw.lower())
            or (raw if raw in valid_stores else None)
        )
        if not resolved:
            missing_store_codes.add(raw)
    db.close()
    return {
        "total_rows": len(df.index),
        "missing_store_codes": sorted(missing_store_codes),
        "status": "OK" if not missing_store_codes else "MISSING_STORES",
    }

@router.post("/finacle", response_model=UploadResponse)
def upload_finacle(
    misDate: str = Form(...),
    file: UploadFile = File(...),
    skipUnmapped: bool = Form(False),
    user: AuthUser = Depends(require_roles("MAKER", "ADMIN")),
):
    db = SessionLocal()
    try:
        mis_date = pd.to_datetime(misDate).date()
        enforce_month_unlocked(db, mis_date.strftime("%Y%m"))
        df = _read_excel_dataframe(file)
    except Exception:
        db.close()
        raise

    existing = db.query(FinacleUploadBatch).filter(FinacleUploadBatch.mis_date == mis_date).first()
    if existing:
        db.close()
        raise HTTPException(status_code=409, detail="Finacle MIS already uploaded for this date")

    mapping = get_finacle_mapping(db)
    required_headers = get_finacle_required_headers(mapping)
    df.columns = [str(c).strip() for c in df.columns]
    headers = set(df.columns)
    missing_headers = required_headers - headers
    if missing_headers:
        db.close()
        raise HTTPException(
            status_code=400, detail=f"Missing required headers: {', '.join(sorted(missing_headers))}"
        )

    batch = FinacleUploadBatch(
        mis_date=mis_date,
        file_name=file.filename,
        uploaded_by=user.employee_id,
        status="RECEIVED",
    )
    db.add(batch)
    db.flush()

    store_rows = (
        db.query(BankStoreMaster.bank_store_code)
        .filter(BankStoreMaster.status == "ACTIVE")
        .filter(BankStoreMaster.effective_from <= mis_date)
        .filter(
            (BankStoreMaster.effective_to.is_(None))
            | (BankStoreMaster.effective_to >= mis_date)
        )
        .all()
    )
    valid_stores = {str(row[0]).strip() for row in store_rows if row and row[0]}
    valid_stores_normalized = {}
    for code in valid_stores:
        if code:
            valid_stores_normalized[code] = code
            valid_stores_normalized[code.upper()] = code
            valid_stores_normalized[code.lower()] = code
            try:
                n = int(float(code))
                valid_stores_normalized[str(n)] = code
            except (ValueError, TypeError):
                pass

    invalid_rows = 0
    has_unmapped_stores = False
    missing_store_codes = set()
    for index, row in df.iterrows():
        row_payload = _truncate_payload(_row_to_payload(row))
        db.add(
            FinacleRawStaging(
                batch_id=batch.batch_id,
                row_number=index + 1,
                row_payload=row_payload,
            )
        )

        bank_store_code_raw = _normalize_store_code(row.get(mapping.get("store_code_column", "STORE_CODE"), ""))
        remittance_amount = _parse_number(row.get(mapping.get("remittance_amount_column", "COLLN_AMT")))
        remittance_date = _parse_date(row.get(mapping.get("remittance_date_column", "TRAN_DATE")))
        account_no = str(row.get(mapping.get("account_no_column", "FORACID"), "")).strip() or None
        customer_id = str(row.get(mapping.get("customer_id_column", "CUST_ID"), "")).strip() or None
        customer_name = str(row.get(mapping.get("customer_name_column", "ACCT_NAME"), "")).strip() or None

        if not bank_store_code_raw or remittance_amount is None or remittance_date is None:
            invalid_rows += 1
            db.add(
                FinacleInvalidRecord(
                    batch_id=batch.batch_id,
                    row_number=index + 1,
                    reason="Missing required fields",
                    row_payload=row_payload,
                )
            )
            continue

        bank_store_code = (
            valid_stores_normalized.get(bank_store_code_raw)
            or valid_stores_normalized.get(bank_store_code_raw.upper())
            or valid_stores_normalized.get(bank_store_code_raw.lower())
            or (bank_store_code_raw if bank_store_code_raw in valid_stores else None)
        )
        if not bank_store_code:
            missing_store_codes.add(bank_store_code_raw)
            invalid_rows += 1
            has_unmapped_stores = True
            db.add(
                FinacleInvalidRecord(
                    batch_id=batch.batch_id,
                    row_number=index + 1,
                    reason="Store not onboarded – add store in Store Onboarding first",
                    row_payload=row_payload,
                )
            )
            continue

        txn = CanonicalTransaction(
            source="FINACLE",
            bank_store_code=bank_store_code,
            vendor_store_code=None,
            account_no=account_no,
            customer_id=customer_id,
            pickup_date=remittance_date,
            remittance_date=remittance_date,
            pickup_amount=remittance_amount,
            remittance_amount=remittance_amount,
            pickup_type=None,
            raw_batch_id=batch.batch_id,
        )
        db.add(txn)
        db.flush()
        db.add(
            RemittanceEntry(
                canonical_id=txn.canonical_id,
                source="FINACLE",
                status="UPLOADED",
                created_by=user.employee_id,
            )
        )

    valid_count = len(df.index) - invalid_rows
    if has_unmapped_stores and not skipUnmapped:
        batch.status = "FAILED"
    elif valid_count > 0:
        batch.status = "PROCESSED"
    else:
        batch.status = "FAILED"

    log_audit(
        db,
        entity_type="UPLOAD",
        entity_id=batch.batch_id,
        action="FINACLE_UPLOAD",
        old_data=None,
        new_data=(
            f"rows={len(df.index)},invalid={invalid_rows},"
            f"unmapped_stores={has_unmapped_stores},skip_unmapped={skipUnmapped}"
        ),
        changed_by=user.employee_id,
    )
    db.flush()
    batch_id = batch.batch_id
    batch_status = batch.status
    db.commit()
    db.close()
    return UploadResponse(
        batch_id=batch_id,
        total_rows=len(df.index),
        invalid_rows=invalid_rows,
        status=batch_status,
        missing_store_codes=sorted(missing_store_codes) if missing_store_codes else None,
    )

@router.get("/finacle/batches")
def list_finacle_batches(
    limit: int = 50,
    date_from: str | None = None,
    date_to: str | None = None,
    user: AuthUser = Depends(require_roles("MAKER", "CHECKER", "ADMIN", "AUDITOR")),
):
    db = SessionLocal()
    q = db.query(FinacleUploadBatch)
    if date_from:
        try:
            q = q.filter(FinacleUploadBatch.mis_date >= datetime.strptime(date_from, "%Y-%m-%d").date())
        except ValueError:
            pass
    if date_to:
        try:
            q = q.filter(FinacleUploadBatch.mis_date <= datetime.strptime(date_to, "%Y-%m-%d").date())
        except ValueError:
            pass
    rows = (
        q.order_by(FinacleUploadBatch.uploaded_at.desc())
        .limit(limit)
        .all()
    )
    result = [
        {
            "batch_id": b.batch_id,
            "mis_date": b.mis_date,
            "file_name": b.file_name,
            "uploaded_by": b.uploaded_by,
            "uploaded_at": b.uploaded_at,
            "status": b.status,
        }
        for b in rows
    ]
    log_audit(db, "UPLOAD", "FINACLE_BATCHES", "VIEW", None, f"count={len(result)}", user.employee_id)
    db.commit()
    db.close()
    return result

def _format_finacle_cell(key, val, date_column: str = "TRAN_DATE"):
    if key == date_column and isinstance(val, (int, float)) and 1000 < val < 1000000:
        try:
            dt = pd.Timestamp("1899-12-30") + pd.Timedelta(days=float(val))
            return dt.strftime("%Y-%m-%d")
        except Exception:
            pass
    return val if val is not None and not (isinstance(val, float) and pd.isna(val)) else ""

@router.get("/finacle/{batch_id}/preview")
def preview_finacle_batch(
    batch_id: int,
    limit: int = 25,
    user: AuthUser = Depends(require_roles("MAKER", "CHECKER", "ADMIN", "AUDITOR")),
):
    db = SessionLocal()
    batch = db.query(FinacleUploadBatch).filter(FinacleUploadBatch.batch_id == batch_id).first()
    if not batch:
        db.close()
        raise HTTPException(status_code=404, detail="Batch not found")
    if not _can_view_batch(user, batch.uploaded_by):
        db.close()
        raise HTTPException(status_code=403, detail="Access denied")
    mapping = get_finacle_mapping(db)
    date_column = mapping.get("remittance_date_column", "TRAN_DATE")
    rows = (
        db.query(FinacleRawStaging)
        .filter(FinacleRawStaging.batch_id == batch_id)
        .order_by(FinacleRawStaging.row_number)
        .limit(limit)
        .all()
    )
    parsed = []
    for row in rows:
        raw = row.row_payload
        if hasattr(raw, "read"):
            raw = raw.read()
        parsed.append(safe_json_loads_clob(raw, default={}, raise_on_error=False))
    headers = list(parsed[0].keys()) if parsed else []
    data_rows = [[_format_finacle_cell(key, item.get(key), date_column) for key in headers] for item in parsed]
    log_audit(db, "UPLOAD", batch_id, "PREVIEW", None, f"rows={len(parsed)}", user.employee_id)
    db.commit()
    db.close()
    return {"headers": headers, "rows": data_rows}

@router.get("/finacle/{batch_id}/download")
def download_finacle_batch(
    batch_id: int,
    user: AuthUser = Depends(require_roles("MAKER", "CHECKER", "ADMIN", "AUDITOR")),
):
    db = SessionLocal()
    batch = db.query(FinacleUploadBatch).filter(FinacleUploadBatch.batch_id == batch_id).first()
    if not batch:
        db.close()
        raise HTTPException(status_code=404, detail="Batch not found")
    if not _can_view_batch(user, batch.uploaded_by):
        db.close()
        raise HTTPException(status_code=403, detail="Access denied")
    mapping = get_finacle_mapping(db)
    date_column = mapping.get("remittance_date_column", "TRAN_DATE")
    raw_rows = (
        db.query(FinacleRawStaging)
        .filter(FinacleRawStaging.batch_id == batch_id)
        .order_by(FinacleRawStaging.row_number)
        .all()
    )
    parsed = []
    for row in raw_rows:
        raw = row.row_payload
        if hasattr(raw, "read"):
            raw = raw.read()
        parsed.append(safe_json_loads_clob(raw, default={}, raise_on_error=False))
    headers = list(parsed[0].keys()) if parsed else []
    df = pd.DataFrame(parsed, columns=headers if headers else None)
    if date_column in df.columns:
        def _excel_serial_to_date(val):
            if isinstance(val, (int, float)) and 1000 < val < 1000000:
                try:
                    return (pd.Timestamp("1899-12-30") + pd.Timedelta(days=float(val))).strftime("%Y-%m-%d")
                except Exception:
                    pass
            return val
        df[date_column] = df[date_column].apply(_excel_serial_to_date)
    df = sanitize_dataframe(df)
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False)
    buffer.seek(0)
    filename = f"finacle_upload_{batch_id}.xlsx"
    log_audit(db, "UPLOAD", batch_id, "DOWNLOAD", None, f"rows={len(parsed)}", user.employee_id)
    db.commit()
    db.close()
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

@router.delete("/finacle/{batch_id}")
def delete_finacle_batch(
    batch_id: int,
    user: AuthUser = Depends(require_roles("MAKER", "ADMIN")),
):
    db = SessionLocal()
    batch = db.query(FinacleUploadBatch).filter(FinacleUploadBatch.batch_id == batch_id).first()
    if not batch:
        db.close()
        raise HTTPException(status_code=404, detail="Batch not found")
    if not _can_delete_batch(user, batch.uploaded_by):
        db.close()
        raise HTTPException(status_code=403, detail="Access denied")
    canon_ids = [
        row[0]
        for row in db.query(CanonicalTransaction.canonical_id)
        .filter(CanonicalTransaction.raw_batch_id == batch_id)
        .all()
    ]
    if canon_ids:
        db.query(RemittanceEntry).filter(RemittanceEntry.canonical_id.in_(canon_ids)).delete(
            synchronize_session=False
        )
    db.query(CanonicalTransaction).filter(CanonicalTransaction.raw_batch_id == batch_id).delete(
        synchronize_session=False
    )
    db.query(FinacleInvalidRecord).filter(FinacleInvalidRecord.batch_id == batch_id).delete(
        synchronize_session=False
    )
    db.query(FinacleRawStaging).filter(FinacleRawStaging.batch_id == batch_id).delete(
        synchronize_session=False
    )
    db.delete(batch)
    log_audit(db, "UPLOAD", batch_id, "DELETE", None, None, user.employee_id)
    db.commit()
    db.close()
    return {"status": "DELETED"}

@router.get("/vendor/batches")
def list_vendor_batches(
    vendor_id: Optional[int] = None,
    limit: int = 50,
    user: AuthUser = Depends(require_roles("MAKER", "CHECKER", "ADMIN", "AUDITOR")),
):
    db = SessionLocal()
    query = (
        db.query(VendorUploadBatch, VendorMaster)
        .join(VendorMaster, VendorMaster.vendor_id == VendorUploadBatch.vendor_id)
        .order_by(VendorUploadBatch.uploaded_at.desc())
    )
    if vendor_id is not None:
        query = query.filter(VendorUploadBatch.vendor_id == vendor_id)
    rows = query.limit(limit).all()
    result = [
        {
            "batch_id": b.batch_id,
            "vendor_id": b.vendor_id,
            "vendor_name": v.vendor_name,
            "vendor_code": v.vendor_code,
            "mis_date": b.mis_date,
            "file_name": b.file_name,
            "uploaded_by": b.uploaded_by,
            "uploaded_at": b.uploaded_at,
            "status": b.status,
        }
        for b, v in rows
    ]
    log_audit(db, "UPLOAD", "VENDOR_BATCHES", "VIEW", None, f"count={len(result)}", user.employee_id)
    db.commit()
    db.close()
    return result

@router.get("/vendor/{batch_id}/preview")
def preview_vendor_batch(
    batch_id: int,
    limit: int = 25,
    user: AuthUser = Depends(require_roles("MAKER", "CHECKER", "ADMIN", "AUDITOR")),
):
    db = SessionLocal()
    batch = db.query(VendorUploadBatch).filter(VendorUploadBatch.batch_id == batch_id).first()
    if not batch:
        db.close()
        raise HTTPException(status_code=404, detail="Batch not found")
    if not _can_view_batch(user, batch.uploaded_by):
        db.close()
        raise HTTPException(status_code=403, detail="Access denied")
    rows = (
        db.query(VendorRawStaging)
        .filter(VendorRawStaging.batch_id == batch_id)
        .order_by(VendorRawStaging.row_number)
        .limit(limit)
        .all()
    )
    parsed = []
    for row in rows:
        raw = row.row_payload
        if hasattr(raw, "read"):
            raw = raw.read()
        parsed.append(safe_json_loads_clob(raw, default={}, raise_on_error=False))
    headers = list(parsed[0].keys()) if parsed else []
    data_rows = [[item.get(key, "") for key in headers] for item in parsed]
    log_audit(db, "UPLOAD", batch_id, "PREVIEW", None, f"rows={len(parsed)}", user.employee_id)
    db.commit()
    db.close()
    return {"headers": headers, "rows": data_rows}

@router.get("/vendor/{batch_id}/download")
def download_vendor_batch(
    batch_id: int,
    user: AuthUser = Depends(require_roles("MAKER", "CHECKER", "ADMIN", "AUDITOR")),
):
    db = SessionLocal()
    batch = db.query(VendorUploadBatch).filter(VendorUploadBatch.batch_id == batch_id).first()
    if not batch:
        db.close()
        raise HTTPException(status_code=404, detail="Batch not found")
    if not _can_view_batch(user, batch.uploaded_by):
        db.close()
        raise HTTPException(status_code=403, detail="Access denied")
    raw_rows = (
        db.query(VendorRawStaging)
        .filter(VendorRawStaging.batch_id == batch_id)
        .order_by(VendorRawStaging.row_number)
        .all()
    )
    parsed = []
    for row in raw_rows:
        raw = row.row_payload
        if hasattr(raw, "read"):
            raw = raw.read()
        parsed.append(safe_json_loads_clob(raw, default={}, raise_on_error=False))
    headers = list(parsed[0].keys()) if parsed else []
    df = pd.DataFrame(parsed, columns=headers if headers else None)
    df = sanitize_dataframe(df)
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False)
    buffer.seek(0)
    filename = f"vendor_upload_{batch_id}.xlsx"
    log_audit(db, "UPLOAD", batch_id, "DOWNLOAD", None, f"rows={len(parsed)}", user.employee_id)
    db.commit()
    db.close()
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

@router.delete("/vendor/{batch_id}")
def delete_vendor_batch(
    batch_id: int,
    user: AuthUser = Depends(require_roles("MAKER", "ADMIN")),
):
    db = SessionLocal()
    batch = db.query(VendorUploadBatch).filter(VendorUploadBatch.batch_id == batch_id).first()
    if not batch:
        db.close()
        raise HTTPException(status_code=404, detail="Batch not found")
    if not _can_delete_batch(user, batch.uploaded_by):
        db.close()
        raise HTTPException(status_code=403, detail="Access denied")
    canon_ids = [
        row[0]
        for row in db.query(CanonicalTransaction.canonical_id)
        .filter(CanonicalTransaction.raw_batch_id == batch_id)
        .all()
    ]
    if canon_ids:
        db.query(RemittanceEntry).filter(RemittanceEntry.canonical_id.in_(canon_ids)).delete(
            synchronize_session=False
        )
    db.query(CanonicalTransaction).filter(CanonicalTransaction.raw_batch_id == batch_id).delete(
        synchronize_session=False
    )
    db.query(VendorInvalidRecord).filter(VendorInvalidRecord.batch_id == batch_id).delete(
        synchronize_session=False
    )
    db.query(VendorRawStaging).filter(VendorRawStaging.batch_id == batch_id).delete(
        synchronize_session=False
    )
    db.delete(batch)
    log_audit(db, "UPLOAD", batch_id, "DELETE", None, None, user.employee_id)
    db.commit()
    db.close()
    return {"status": "DELETED"}

@router.post("/vendor", response_model=UploadResponse)
def upload_vendor(
    vendorName: str = Form(...),
    misDate: str = Form(...),
    file: UploadFile = File(...),
    skipUnmapped: bool = Form(False),
    user: AuthUser = Depends(require_roles("MAKER", "ADMIN")),
):
    db = SessionLocal()
    try:
        mis_date = pd.to_datetime(misDate).date()
        enforce_month_unlocked(db, mis_date.strftime("%Y%m"))
        df = _read_excel_dataframe(file)
    except Exception:
        db.close()
        raise

    vendor = (
        db.query(VendorMaster)
        .filter(VendorMaster.vendor_name == vendorName)
        .filter(VendorMaster.status == "ACTIVE")
        .first()
    )
    if not vendor:
        db.close()
        raise HTTPException(status_code=404, detail="Vendor not found or inactive")

    existing = (
        db.query(VendorUploadBatch)
        .filter(VendorUploadBatch.vendor_id == vendor.vendor_id)
        .filter(VendorUploadBatch.mis_date == mis_date)
        .order_by(VendorUploadBatch.uploaded_at.desc())
        .first()
    )
    if existing and existing.status != "FAILED":
        db.close()
        raise HTTPException(status_code=409, detail="Vendor MIS already uploaded for this date")
    if existing and existing.status == "FAILED":
        canon_ids = [
            row[0]
            for row in db.query(CanonicalTransaction.canonical_id)
            .filter(CanonicalTransaction.raw_batch_id == existing.batch_id)
            .all()
        ]
        if canon_ids:
            db.query(RemittanceEntry).filter(RemittanceEntry.canonical_id.in_(canon_ids)).delete(
                synchronize_session=False
            )
        db.query(CanonicalTransaction).filter(
            CanonicalTransaction.raw_batch_id == existing.batch_id
        ).delete(synchronize_session=False)
        db.query(VendorInvalidRecord).filter(
            VendorInvalidRecord.batch_id == existing.batch_id
        ).delete(synchronize_session=False)
        db.query(VendorRawStaging).filter(VendorRawStaging.batch_id == existing.batch_id).delete(
            synchronize_session=False
        )
        existing.status = "RECEIVED"
        existing.file_name = file.filename
        existing.uploaded_by = user.employee_id
        existing.uploaded_at = datetime.utcnow()

    format_config = _load_vendor_format(db, vendor.vendor_id)
    if not format_config:
        db.close()
        raise HTTPException(status_code=400, detail="Vendor file format config not active")

    mapping = _format_mapping_dict(format_config)
    if not mapping:
        db.close()
        raise HTTPException(status_code=400, detail="Vendor file format has no header mapping")

    headers = set(df.columns.astype(str))
    required = [
        mapping.get("pickup_date_column"),
        mapping.get("pickup_amount_column"),
        mapping.get("vendor_store_code_column"),
    ]
    missing = [col for col in required if col and col not in headers]
    if missing:
        db.close()
        raise HTTPException(status_code=400, detail=f"Missing required headers: {', '.join(missing)}")

    if existing:
        batch = existing
    else:
        batch = VendorUploadBatch(
            vendor_id=vendor.vendor_id,
            mis_date=mis_date,
            file_name=file.filename,
            uploaded_by=user.employee_id,
            status="RECEIVED",
        )
        db.add(batch)
        db.flush()

    invalid_rows = 0
    has_unmapped = False
    unmapped_codes: set[str] = set()
    valid_rows = []
    for index, row in df.iterrows():
        row_payload = _truncate_payload(_row_to_payload(row))
        db.add(
            VendorRawStaging(
                batch_id=batch.batch_id,
                row_number=index + 1,
                row_payload=row_payload,
            )
        )

        vendor_store_code = str(row.get(mapping.get("vendor_store_code_column"), "")).strip()
        pickup_date = _parse_date(row.get(mapping.get("pickup_date_column")))
        pickup_amount = _parse_number(row.get(mapping.get("pickup_amount_column")))
        pickup_type_raw = row.get(mapping.get("pickup_type_column")) if mapping.get("pickup_type_column") else None
        account_no = (
            str(row.get(mapping.get("account_no_column"), "")).strip()
            if mapping.get("account_no_column")
            else None
        )
        customer_id = (
            str(row.get(mapping.get("customer_id_column"), "")).strip()
            if mapping.get("customer_id_column")
            else None
        )
        customer_name = (
            str(row.get(mapping.get("customer_name_column"), "")).strip()
            if mapping.get("customer_name_column")
            else None
        )
        remittance_amount = (
            _parse_number(row.get(mapping.get("remittance_amount_column")))
            if mapping.get("remittance_amount_column")
            else None
        )
        remittance_date = (
            _parse_date(row.get(mapping.get("remittance_date_column")))
            if mapping.get("remittance_date_column")
            else None
        )

        if not vendor_store_code or pickup_date is None or pickup_amount is None:
            invalid_rows += 1
            db.add(
                VendorInvalidRecord(
                    batch_id=batch.batch_id,
                    row_number=index + 1,
                    reason="Missing required fields",
                    row_payload=row_payload,
                )
            )
            continue

        mapping_row = _lookup_mapping_lenient(db, vendor.vendor_id, vendor_store_code)
        if not mapping_row:
            invalid_rows += 1
            has_unmapped = True
            if vendor_store_code:
                unmapped_codes.add(vendor_store_code)
            db.add(
                VendorInvalidRecord(
                    batch_id=batch.batch_id,
                    row_number=index + 1,
                    reason="Vendor store code not mapped",
                    row_payload=row_payload,
                )
            )
            continue

        pickup_type = None
        if pickup_type_raw is not None:
            value = str(pickup_type_raw).strip().upper()
            pickup_type = "CALL" if "CALL" in value else "BEAT"

        valid_rows.append(
            {
                "mapping_row": mapping_row,
                "vendor_store_code": vendor_store_code,
                "pickup_date": pickup_date,
                "pickup_amount": pickup_amount,
                "pickup_type": pickup_type,
                "account_no": account_no,
                "customer_id": customer_id,
                "remittance_amount": remittance_amount,
                "remittance_date": remittance_date,
            }
        )

    if has_unmapped and not skipUnmapped:
        batch.status = "FAILED"
    else:
        for row in valid_rows:
            txn = CanonicalTransaction(
                source="VENDOR",
                bank_store_code=row["mapping_row"].bank_store_code,
                vendor_store_code=row["vendor_store_code"],
                account_no=row["account_no"] or row["mapping_row"].account_no,
                customer_id=row["customer_id"] or row["mapping_row"].customer_id,
                pickup_date=row["pickup_date"],
                remittance_date=row["remittance_date"],
                pickup_amount=row["pickup_amount"],
                remittance_amount=row["remittance_amount"],
                pickup_type=row["pickup_type"],
                raw_batch_id=batch.batch_id,
            )
            db.add(txn)
            db.flush()
            db.add(
                RemittanceEntry(
                    canonical_id=txn.canonical_id,
                    source="VENDOR",
                    status="UPLOADED",
                    created_by=user.employee_id,
                )
            )
        batch.status = "PROCESSED" if invalid_rows < len(df.index) else "FAILED"

    log_audit(
        db,
        entity_type="UPLOAD",
        entity_id=batch.batch_id,
        action="VENDOR_UPLOAD",
        old_data=None,
        new_data=(
            f"rows={len(df.index)},invalid={invalid_rows},"
            f"unmapped={has_unmapped},skip_unmapped={skipUnmapped}"
        ),
        changed_by=user.employee_id,
    )
    db.flush()
    batch_id = batch.batch_id
    batch_status = batch.status
    db.commit()
    db.close()
    return UploadResponse(
        batch_id=batch_id,
        total_rows=len(df.index),
        invalid_rows=invalid_rows,
        status=batch_status,
        missing_store_codes=sorted(unmapped_codes) if unmapped_codes else None,
    )

@router.post("/vendor/validate")
def validate_vendor_upload(
    vendorName: str = Form(...),
    misDate: str = Form(...),
    file: UploadFile = File(...),
    user: AuthUser = Depends(require_roles("MAKER", "CHECKER", "ADMIN", "AUDITOR")),
):
    db = SessionLocal()
    try:
        mis_date = pd.to_datetime(misDate).date()
        df = _read_excel_dataframe(file)
    except Exception:
        db.close()
        raise

    vendor = (
        db.query(VendorMaster)
        .filter(VendorMaster.vendor_name == vendorName)
        .filter(VendorMaster.status == "ACTIVE")
        .first()
    )
    if not vendor:
        db.close()
        raise HTTPException(status_code=404, detail="Vendor not found or inactive")

    format_config = _load_vendor_format(db, vendor.vendor_id)
    if not format_config:
        db.close()
        raise HTTPException(status_code=400, detail="Vendor file format config not active")

    mapping = _format_mapping_dict(format_config)
    if not mapping:
        db.close()
        raise HTTPException(status_code=400, detail="Vendor file format has no header mapping")

    df.columns = [str(c).strip() for c in df.columns]
    pickup_date_col = mapping.get("pickup_date_column")
    if pickup_date_col and pickup_date_col in df.columns:
        df[pickup_date_col] = df[pickup_date_col].apply(
            lambda v: _parse_date(v) if pd.notna(v) else pd.NaT
        )
    headers = set(df.columns.astype(str))
    required = [
        mapping.get("pickup_date_column"),
        mapping.get("pickup_amount_column"),
        mapping.get("vendor_store_code_column"),
    ]
    missing = [col for col in required if col and col not in headers]
    if missing:
        db.close()
        raise HTTPException(status_code=400, detail=f"Missing required headers: {', '.join(missing)}")

    invalid_rows = 0
    unmapped_codes = set()
    for _, row in df.iterrows():
        vendor_store_code = str(row.get(mapping.get("vendor_store_code_column"), "")).strip()
        pickup_date = _parse_date(row.get(mapping.get("pickup_date_column")))
        pickup_amount = _parse_number(row.get(mapping.get("pickup_amount_column")))

        if not vendor_store_code or pickup_date is None or pickup_amount is None:
            invalid_rows += 1
            continue

        mapping_row = _lookup_mapping_lenient(db, vendor.vendor_id, vendor_store_code)
        if not mapping_row:
            unmapped_codes.add(vendor_store_code)

    db.close()
    return {
        "total_rows": len(df.index),
        "invalid_rows": invalid_rows,
        "unmapped_codes": sorted(unmapped_codes),
        "out_of_range_codes": [],
        "status": "OK" if not unmapped_codes else "UNMAPPED",
    }
