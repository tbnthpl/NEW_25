import calendar
import math
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, status

from backend.auth import AuthUser, require_roles
from backend.audit import log_audit
from backend.db import SessionLocal
from sqlalchemy import and_, or_

from backend.models import (
    BankStoreMaster,
    CanonicalTransaction,
    ChargeConfigurationMaster,
    CustomerChargeSummary,
    MonthLock,
    ReconciliationResult,
    VendorChargeSummary,
    VendorMaster,
    VendorStoreMappingMaster,
    VendorUploadBatch,
)

router = APIRouter(prefix="/api/charges", tags=["charges"])

ENHANCEMENT_THRESHOLD_CODE = "ENHANCEMENT_THRESHOLD_AMOUNT"
ENHANCEMENT_CHARGE_CODE = "ENHANCEMENT_CHARGE_AMOUNT"
GST_ENABLED_CODE = "GST_ENABLED"
GST_RATE_CODE = "GST_RATE_PERCENT"

def _vendor_mapped_stores_at(db, vendor_id: int, as_of: date, pickup_type: str):
    return (
        db.query(BankStoreMaster)
        .join(
            VendorStoreMappingMaster,
            (VendorStoreMappingMaster.bank_store_code == BankStoreMaster.bank_store_code)
            & (VendorStoreMappingMaster.vendor_id == vendor_id)
            & (VendorStoreMappingMaster.status == "ACTIVE")
            & (VendorStoreMappingMaster.effective_from <= as_of)
            & (
                (VendorStoreMappingMaster.effective_to.is_(None))
                | (VendorStoreMappingMaster.effective_to >= as_of)
            ),
        )
        .filter(BankStoreMaster.pickup_type == pickup_type)
        .filter(BankStoreMaster.status == "ACTIVE")
        .filter(BankStoreMaster.effective_from <= as_of)
        .filter(
            (BankStoreMaster.effective_to.is_(None))
            | (BankStoreMaster.effective_to >= as_of)
        )
        .all()
    )

def _call_pickup_counts_by_store(db, month_key: str) -> dict[int, int]:
    batches = [
        b
        for b in db.query(VendorUploadBatch)
        .filter(VendorUploadBatch.status == "PROCESSED")
        .filter(VendorUploadBatch.mis_date.isnot(None))
        .all()
        if b.mis_date.strftime("%Y%m") == month_key
    ]
    if not batches:
        return {}
    batch_ids = [b.batch_id for b in batches]
    rows = db.query(BankStoreMaster.store_id, BankStoreMaster.bank_store_code).filter(BankStoreMaster.status == "ACTIVE").all()
    code_to_id = {str(r.bank_store_code or "").strip(): int(r.store_id) for r in rows}
    txns = (
        db.query(CanonicalTransaction)
        .filter(CanonicalTransaction.source == "VENDOR")
        .filter(CanonicalTransaction.raw_batch_id.in_(batch_ids))
        .filter(CanonicalTransaction.pickup_type == "CALL")
        .all()
    )
    counts: dict[int, int] = {}
    for t in txns:
        code = str(t.bank_store_code or "").strip()
        sid = code_to_id.get(code)
        if sid is None:
            continue
        counts[sid] = counts.get(sid, 0) + 1
    return counts

def _month_key_to_month_last_date(month_key: str) -> date | None:
    if not month_key or len(month_key) < 6:
        return None
    try:
        y = int(month_key[:4])
        m = int(month_key[4:6])
        last_d = calendar.monthrange(y, m)[1]
        return date(y, m, last_d)
    except ValueError:
        return None


def _vendor_names_for_stores_at(db, store_codes: list[str], as_of: date) -> dict[str, str]:
    codes = [str(c or "").strip() for c in store_codes if str(c or "").strip()]
    if not codes:
        return {}
    rows = (
        db.query(VendorStoreMappingMaster.bank_store_code, VendorMaster.vendor_name)
        .join(VendorMaster, VendorMaster.vendor_id == VendorStoreMappingMaster.vendor_id)
        .filter(VendorStoreMappingMaster.bank_store_code.in_(codes))
        .filter(VendorStoreMappingMaster.status == "ACTIVE")
        .filter(VendorStoreMappingMaster.effective_from <= as_of)
        .filter(
            or_(
                VendorStoreMappingMaster.effective_to.is_(None),
                VendorStoreMappingMaster.effective_to >= as_of,
            )
        )
        .all()
    )
    grouped: dict[str, list[str]] = {}
    for code, name in rows:
        code = str(code or "").strip()
        if not code:
            continue
        label = (name or "").strip()
        if not label:
            continue
        bucket = grouped.setdefault(code, [])
        if label not in bucket:
            bucket.append(label)
    return {code: ", ".join(names) for code, names in grouped.items()}

def _cumulative_store_charges_in_cap_window(
    db,
    store_id: int,
    store: BankStoreMaster,
    current_month_key: str,
) -> float:
    cf = getattr(store, "waiver_cap_from", None)
    ct = getattr(store, "waiver_cap_to", None)
    rows = (
        db.query(CustomerChargeSummary)
        .filter(CustomerChargeSummary.store_id == store_id)
        .filter(CustomerChargeSummary.month_key < current_month_key)
        .all()
    )
    total = 0.0
    for s in rows:
        d_end = _month_key_to_month_last_date(s.month_key)
        if not d_end:
            continue
        if cf is not None and d_end < cf:
            continue
        if ct is not None and d_end > ct:
            continue
        base = float(s.base_charge_amount or 0)
        enh = float(s.enhancement_charge or 0)
        total += base + enh
    return total

def _effective_store_waiver_cap(store: BankStoreMaster, as_of_date: date) -> float | None:
    amt = getattr(store, "waiver_cap_amount", None)
    if amt is None or float(amt) <= 0:
        return None
    cf = getattr(store, "waiver_cap_from", None)
    ct = getattr(store, "waiver_cap_to", None)
    if cf is None and ct is None:
        return float(amt)
    if cf is not None and as_of_date < cf:
        return None
    if ct is not None and as_of_date > ct:
        return None
    return float(amt)

def _apply_store_waiver_for_charge(
    base_store: float,
    enh_store: float,
    waiver_pct: float | None,
    cap_total: float | None,
    billed_before_in_window: float,
) -> tuple[float, float, float]:
    b = float(base_store or 0)
    e = float(enh_store or 0)
    raw = b + e
    if raw <= 0:
        return 0.0, 0.0, 0.0
    wp = float(waiver_pct or 0)

    if cap_total is not None and cap_total > 0:
        headroom = max(0.0, float(cap_total) - float(billed_before_in_window or 0))
        if wp:
            pct_waiver = raw * (wp / 100.0)
            waiver_amt = min(raw, pct_waiver + headroom)
        else:
            waiver_amt = min(raw, headroom)
        total_after = max(0.0, raw - waiver_amt)
    elif wp:
        waiver_amt = raw * (wp / 100.0)
        total_after = max(0.0, raw - waiver_amt)
    else:
        waiver_amt = 0.0
        total_after = raw

    share_b = b / raw
    share_e = e / raw
    return total_after * share_b, total_after * share_e, waiver_amt

def _get_config_number(db, code, as_of_date):
    row = (
        db.query(ChargeConfigurationMaster)
        .filter(ChargeConfigurationMaster.config_code == code)
        .filter(ChargeConfigurationMaster.status == "ACTIVE")
        .filter(ChargeConfigurationMaster.effective_from <= as_of_date)
        .filter(
            (ChargeConfigurationMaster.effective_to.is_(None))
            | (ChargeConfigurationMaster.effective_to >= as_of_date)
        )
        .order_by(ChargeConfigurationMaster.effective_from.desc())
        .first()
    )
    return float(row.value_number) if row and row.value_number is not None else None

def _get_config_text(db, code, as_of_date):
    row = (
        db.query(ChargeConfigurationMaster)
        .filter(ChargeConfigurationMaster.config_code == code)
        .filter(ChargeConfigurationMaster.status == "ACTIVE")
        .filter(ChargeConfigurationMaster.effective_from <= as_of_date)
        .filter(
            (ChargeConfigurationMaster.effective_to.is_(None))
            | (ChargeConfigurationMaster.effective_to >= as_of_date)
        )
        .order_by(ChargeConfigurationMaster.effective_from.desc())
        .first()
    )
    return row.value_text if row else None

def _enforce_unlocked(db, month_key):
    lock = db.query(MonthLock).filter(MonthLock.month_key == month_key).first()
    if lock and lock.status == "LOCKED":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Month is locked")

def _active_store_code_to_id(db) -> dict[str, int]:
    by_code: dict[str, int] = {}
    for s in db.query(BankStoreMaster).filter(BankStoreMaster.status == "ACTIVE").all():
        code = str(s.bank_store_code or "").strip()
        if not code:
            continue
        by_code[code] = s.store_id
        if code.isdigit():
            by_code[code.lstrip("0") or "0"] = s.store_id
            by_code[code.zfill(3)] = s.store_id
    return by_code

def _store_id_from_recon_code(store_by_code: dict[str, int], code_raw: str | None) -> int | None:
    c = str(code_raw or "").strip()
    if not c:
        return None
    sid = store_by_code.get(c)
    if sid is not None:
        return sid
    if c.isdigit():
        sid = store_by_code.get(c.lstrip("0") or "0")
        if sid is not None:
            return sid
        sid = store_by_code.get(c.zfill(3))
        if sid is not None:
            return sid
    return None

@router.get("/vendor/summary")
def list_vendor_charges(
    month_key: str | None = None,
    month_from: str | None = None,
    month_to: str | None = None,
    vendor_id: int | None = None,
    user: AuthUser = Depends(require_roles("MAKER", "CHECKER", "ADMIN", "AUDITOR")),
):
    db = SessionLocal()
    try:
        q = db.query(VendorChargeSummary, VendorMaster.vendor_name, VendorMaster.vendor_code).outerjoin(
            VendorMaster, VendorChargeSummary.vendor_id == VendorMaster.vendor_id
        )
        if vendor_id is not None:
            q = q.filter(VendorChargeSummary.vendor_id == vendor_id)
        if month_from and month_to:
            q = q.filter(VendorChargeSummary.month_key >= month_from, VendorChargeSummary.month_key <= month_to)
        elif month_key:
            q = q.filter(VendorChargeSummary.month_key == month_key)
        rows = q.order_by(VendorChargeSummary.month_key.desc(), VendorChargeSummary.vendor_id).all()
        month_keys = sorted({s.month_key for s, _, _ in rows})
        remittance_by_vendor_month, _ = _vendor_remittance_maps(db, month_keys)
        return [
            {
                "summary_id": s.summary_id,
                "vendor_id": s.vendor_id,
                "vendor_name": name or "",
                "vendor_code": code or "",
                "month_key": s.month_key,
                "beat_pickups": s.beat_pickups,
                "call_pickups": s.call_pickups,
                "total_remittance": remittance_by_vendor_month.get((s.vendor_id, s.month_key), 0.0),
                "base_charge_amount": float(s.base_charge_amount or 0),
                "enhancement_charge": float(s.enhancement_charge or 0),
                "tax_amount": float(s.tax_amount or 0),
                "total_with_tax": float(s.total_with_tax or 0),
                "status": s.status,
                "computed_by": s.computed_by,
                "computed_at": s.computed_at.isoformat() if s.computed_at else None,
            }
            for s, name, code in rows
        ]
    finally:
        db.close()

def _months_in_range(month_from: str, month_to: str) -> list[str]:
    if not month_from or not month_to:
        return []
    mf, mt = (month_from, month_to) if month_from <= month_to else (month_to, month_from)
    try:
        y0, m0 = int(mf[:4]), int(mf[4:6])
        y1, m1 = int(mt[:4]), int(mt[4:6])
    except ValueError:
        return []
    months: list[str] = []
    y, m = y0, m0
    while (y, m) <= (y1, m1):
        months.append(f"{y:04d}{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


def _vendor_remittance_maps(db, month_keys: list[str]) -> tuple[dict[tuple[int, str], float], dict[tuple[int, str, str], float]]:
    vendor_month: dict[tuple[int, str], float] = {}
    vendor_store: dict[tuple[int, str, str], float] = {}
    if not month_keys:
        return vendor_month, vendor_store
    month_set = set(month_keys)
    batches = [
        b
        for b in db.query(VendorUploadBatch).filter(VendorUploadBatch.mis_date.isnot(None)).all()
        if b.mis_date.strftime("%Y%m") in month_set
    ]
    if not batches:
        return vendor_month, vendor_store
    batch_to_vendor = {b.batch_id: b.vendor_id for b in batches}
    batch_to_month = {b.batch_id: b.mis_date.strftime("%Y%m") for b in batches if b.mis_date}
    txns = (
        db.query(CanonicalTransaction)
        .filter(CanonicalTransaction.source == "VENDOR")
        .filter(CanonicalTransaction.raw_batch_id.in_(list(batch_to_vendor.keys())))
        .all()
    )
    for t in txns:
        vid = batch_to_vendor.get(t.raw_batch_id)
        mk = batch_to_month.get(t.raw_batch_id)
        if vid is None or not mk:
            continue
        amt = float(t.pickup_amount or 0)
        vendor_month[(vid, mk)] = vendor_month.get((vid, mk), 0.0) + amt
        code = str(t.bank_store_code or "").strip()
        if code:
            vendor_store[(vid, mk, code)] = vendor_store.get((vid, mk, code), 0.0) + amt
    return vendor_month, vendor_store


@router.get("/vendor/by-store")
def list_vendor_charges_by_store(
    month_key: str | None = None,
    month_from: str | None = None,
    month_to: str | None = None,
    vendor_id: int | None = None,
    store_id: int | None = None,
    user: AuthUser = Depends(require_roles("MAKER", "CHECKER", "ADMIN", "AUDITOR")),
):
    if month_from and month_to:
        months = _months_in_range(month_from, month_to)
    elif month_key:
        months = _months_in_range(month_key, month_key)
    else:
        raise HTTPException(status_code=400, detail="Provide month_key or month_from/month_to (YYYYMM)")
    if not months:
        raise HTTPException(status_code=400, detail="Invalid month key (expected YYYYMM)")

    db = SessionLocal()
    try:
        vendor_meta = {v.vendor_id: v for v in db.query(VendorMaster).all()}
        active_vendor_ids = [
            v.vendor_id for v in vendor_meta.values() if (v.status or "").upper() == "ACTIVE"
        ]
        if vendor_id is not None:
            active_vendor_ids = [vendor_id] if vendor_id in active_vendor_ids else []

        summ_q = db.query(VendorChargeSummary).filter(VendorChargeSummary.month_key.in_(months))
        if vendor_id is not None:
            summ_q = summ_q.filter(VendorChargeSummary.vendor_id == vendor_id)
        computed_at_by_key = {
            (s.vendor_id, s.month_key): (s.computed_at.isoformat() if s.computed_at else None)
            for s in summ_q.all()
        }
        _, remittance_by_vendor_store = _vendor_remittance_maps(db, months)

        results: list[dict] = []
        for mk in months:
            as_of_date = _month_key_to_month_last_date(mk)
            if not as_of_date:
                continue

            month_batches = [
                b
                for b in db.query(VendorUploadBatch).filter(VendorUploadBatch.mis_date.isnot(None)).all()
                if b.mis_date.strftime("%Y%m") == mk
            ]
            batch_to_vendor = {b.batch_id: b.vendor_id for b in month_batches}
            vendors_with_data = {b.vendor_id for b in month_batches}
            call_counts_by_vendor: dict[int, dict[str, int]] = {}

            month_start = as_of_date.replace(day=1)
            month_end = as_of_date
            matched_pickups_by_code: dict[str, int] = {}
            matched_rows = (
                db.query(ReconciliationResult)
                .filter(ReconciliationResult.is_final == 1)
                .filter(ReconciliationResult.status == "MATCHED")
                .filter(
                    or_(
                        and_(
                            ReconciliationResult.mis_date >= month_start,
                            ReconciliationResult.mis_date <= month_end,
                        ),
                        and_(
                            ReconciliationResult.mis_date.is_(None),
                            ReconciliationResult.pickup_date >= month_start,
                            ReconciliationResult.pickup_date <= month_end,
                        ),
                    )
                )
                .all()
            )
            for rr in matched_rows:
                code = str(rr.bank_store_code or "").strip()
                if not code:
                    continue
                matched_pickups_by_code[code] = matched_pickups_by_code.get(code, 0) + 1
            if month_batches:
                txns = (
                    db.query(CanonicalTransaction)
                    .filter(CanonicalTransaction.source == "VENDOR")
                    .filter(CanonicalTransaction.raw_batch_id.in_(list(batch_to_vendor.keys())))
                    .filter(CanonicalTransaction.pickup_type == "CALL")
                    .all()
                )
                for t in txns:
                    vid = batch_to_vendor.get(t.raw_batch_id)
                    if vid is None:
                        continue
                    code = str(t.bank_store_code or "").strip()
                    if not code:
                        continue
                    call_counts_by_vendor.setdefault(vid, {})
                    call_counts_by_vendor[vid][code] = call_counts_by_vendor[vid].get(code, 0) + 1

            for vid in sorted(active_vendor_ids):
                if vid not in vendors_with_data:
                    continue
                v = vendor_meta.get(vid)
                vname = (v.vendor_name if v else "") or ""
                vcode = (v.vendor_code if v else "") or ""

                beat_stores = _vendor_mapped_stores_at(db, vid, as_of_date, "BEAT")
                for st in beat_stores:
                    if store_id is not None and st.store_id != store_id:
                        continue
                    rate = float(getattr(st, "vendor_charge", None) or 0)
                    beat_code = str(st.bank_store_code or "").strip()
                    results.append(
                        {
                            "month_key": mk,
                            "vendor_id": vid,
                            "vendor_name": vname,
                            "vendor_code": vcode,
                            "store_id": st.store_id,
                            "bank_store_code": st.bank_store_code or "",
                            "store_name": st.store_name or "",
                            "pickup_type": "BEAT",
                            "pickups": matched_pickups_by_code.get(beat_code, 0),
                            "total_remittance": remittance_by_vendor_store.get((vid, mk, beat_code), 0.0),
                            "rate": rate,
                            "charge_amount": rate,
                            "computed_at": computed_at_by_key.get((vid, mk)),
                        }
                    )

                call_stores = _vendor_mapped_stores_at(db, vid, as_of_date, "CALL")
                vendor_call_counts = call_counts_by_vendor.get(vid, {})
                for st in call_stores:
                    if store_id is not None and st.store_id != store_id:
                        continue
                    code = str(st.bank_store_code or "").strip()
                    n = int(vendor_call_counts.get(code, 0))
                    if n <= 0 and store_id is None:
                        continue
                    rate_raw = getattr(st, "call_vendor_pay_per_pickup", None)
                    rate = float(rate_raw) if rate_raw is not None else None
                    if rate is None or rate <= 0:
                        charge_amount = 0.0
                    else:
                        charge_amount = float(n) * rate
                    results.append(
                        {
                            "month_key": mk,
                            "vendor_id": vid,
                            "vendor_name": vname,
                            "vendor_code": vcode,
                            "store_id": st.store_id,
                            "bank_store_code": st.bank_store_code or "",
                            "store_name": st.store_name or "",
                            "pickup_type": "CALL",
                            "pickups": n,
                            "total_remittance": remittance_by_vendor_store.get((vid, mk, code), 0.0),
                            "rate": rate,
                            "charge_amount": charge_amount,
                            "computed_at": computed_at_by_key.get((vid, mk)),
                        }
                    )

        results.sort(key=lambda r: (r["month_key"], r["vendor_name"] or "", r["bank_store_code"] or ""))
        return results
    finally:
        db.close()

@router.get("/customer/summary")
def list_customer_charges(
    month_key: str | None = None,
    month_from: str | None = None,
    month_to: str | None = None,
    store_id: int | None = None,
    user: AuthUser = Depends(require_roles("MAKER", "CHECKER", "ADMIN", "AUDITOR")),
):
    db = SessionLocal()
    try:
        q = db.query(CustomerChargeSummary)
        if store_id is not None:
            q = q.filter(CustomerChargeSummary.store_id == store_id)
        if month_from and month_to:
            q = q.filter(CustomerChargeSummary.month_key >= month_from, CustomerChargeSummary.month_key <= month_to)
        elif month_key:
            q = q.filter(CustomerChargeSummary.month_key == month_key)
        rows = q.order_by(CustomerChargeSummary.month_key.desc(), CustomerChargeSummary.store_id).all()
        store_ids = [s.store_id for s in rows]
        st_rows = (
            db.query(BankStoreMaster)
            .filter(BankStoreMaster.store_id.in_(store_ids))
            .all()
            if store_ids
            else []
        )
        meta = {s.store_id: s for s in st_rows}
        vendor_name_cache: dict[tuple[str, str], str] = {}

        def _vendor_name_for_row(store_id: int, month_key: str) -> str:
            st = meta.get(store_id)
            code = str(st.bank_store_code or "").strip() if st else ""
            if not code or not month_key:
                return ""
            cache_key = (code, month_key)
            if cache_key in vendor_name_cache:
                return vendor_name_cache[cache_key]
            as_of = _month_key_to_month_last_date(month_key)
            name = ""
            if as_of:
                name = _vendor_names_for_stores_at(db, [code], as_of).get(code, "")
            vendor_name_cache[cache_key] = name
            return name

        return [
            {
                "summary_id": s.summary_id,
                "store_id": s.store_id,
                "bank_store_code": (meta.get(s.store_id).bank_store_code if meta.get(s.store_id) else "") or "",
                "store_name": (meta.get(s.store_id).store_name if meta.get(s.store_id) else "") or "",
                "vendor_name": _vendor_name_for_row(s.store_id, s.month_key),
                "customer_id": (meta.get(s.store_id).customer_id if meta.get(s.store_id) else None) or "",
                "customer_name": (meta.get(s.store_id).customer_name if meta.get(s.store_id) else None) or "",
                "month_key": s.month_key,
                "charge_period_from": s.charge_period_from.isoformat() if getattr(s, "charge_period_from", None) else None,
                "charge_period_to": s.charge_period_to.isoformat() if getattr(s, "charge_period_to", None) else None,
                "total_remittance": float(s.total_remittance or 0),
                "base_charge_amount": float(s.base_charge_amount or 0),
                "enhancement_charge": float(s.enhancement_charge or 0),
                "days_over_limit": int(getattr(s, "days_over_limit", None) or 0),
                "waiver_amount": float(s.waiver_amount or 0),
                "store_waiver_applied": float(getattr(s, "store_waiver_applied", None) or 0),
                "net_charge_amount": float(s.net_charge_amount or 0),
                "tax_amount": float(s.tax_amount or 0),
                "total_with_tax": float(s.total_with_tax or 0),
                "status": s.status,
                "computed_by": s.computed_by,
                "computed_at": s.computed_at.isoformat() if s.computed_at else None,
            }
            for s in rows
        ]
    finally:
        db.close()

@router.get("/months")
def list_charge_months(user: AuthUser = Depends(require_roles("MAKER", "CHECKER", "ADMIN", "AUDITOR"))):
    db = SessionLocal()
    try:
        v_months = db.query(VendorChargeSummary.month_key).distinct().all()
        c_months = db.query(CustomerChargeSummary.month_key).distinct().all()
        all_months = sorted(set(m[0] for m in v_months + c_months), reverse=True)
        return {"months": all_months}
    finally:
        db.close()

@router.post("/vendor/compute")
def compute_vendor_charges(payload: dict, user: AuthUser = Depends(require_roles("MAKER", "ADMIN"))):
    month_key = payload.get("month_key")
    if not month_key:
        raise HTTPException(status_code=400, detail="month_key is required (YYYYMM)")
    if not (isinstance(month_key, str) and len(month_key) == 6 and month_key.isdigit()):
        raise HTTPException(status_code=400, detail="month_key must be 6 digits formatted YYYYMM")
    try:
        year = int(month_key[:4])
        month = int(month_key[4:6])
        if not (1 <= month <= 12) or year < 2000 or year > 2100:
            raise ValueError
        last_day = calendar.monthrange(year, month)[1]
        as_of_date = datetime(year, month, last_day).date()
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="month_key must be a valid YYYYMM (e.g. 202601)")

    db = SessionLocal()
    try:
        _enforce_unlocked(db, month_key)
        return _compute_vendor_charges_impl(db, payload, user, month_key, year, month, as_of_date)
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def _compute_vendor_charges_impl(db, payload, user, month_key, year, month, as_of_date):

    ow = payload.get("overwrite")
    overwrite = ow is True or (isinstance(ow, str) and str(ow).strip().lower() in ("1", "true", "yes"))
    vendor_ids_filter = payload.get("vendor_ids")
    if overwrite:
        qdel = db.query(VendorChargeSummary).filter(VendorChargeSummary.month_key == month_key)
        if vendor_ids_filter:
            qdel = qdel.filter(VendorChargeSummary.vendor_id.in_(vendor_ids_filter))
        qdel.delete(synchronize_session=False)

    threshold = _get_config_number(db, ENHANCEMENT_THRESHOLD_CODE, as_of_date) or 50000.0
    enhancement_charge = _get_config_number(db, ENHANCEMENT_CHARGE_CODE, as_of_date) or 60.0

    gst_enabled = _get_config_text(db, GST_ENABLED_CODE, as_of_date)
    gst_rate = _get_config_number(db, GST_RATE_CODE, as_of_date) or 0.0

    vendor_ids = payload.get("vendor_ids")
    batch_query = db.query(VendorUploadBatch).filter(VendorUploadBatch.mis_date.isnot(None))
    if vendor_ids:
        batch_query = batch_query.filter(VendorUploadBatch.vendor_id.in_(vendor_ids))
    batches = [b for b in batch_query.all() if b.mis_date.strftime("%Y%m") == month_key]

    batch_vendor_ids_set = {b.vendor_id for b in batches}
    batch_vendor_ids = sorted(batch_vendor_ids_set)
    if vendor_ids:
        vendor_ids_in_month = sorted(batch_vendor_ids_set & set(vendor_ids))
    else:
        vendor_ids_in_month = batch_vendor_ids

    results = []
    for vendor_id in vendor_ids_in_month:
        if not overwrite:
            existing = (
                db.query(VendorChargeSummary)
                .filter(VendorChargeSummary.vendor_id == vendor_id)
                .filter(VendorChargeSummary.month_key == month_key)
                .first()
            )
            if existing:
                month_label = f"{calendar.month_name[month]} {year}" if month_key and len(month_key) >= 6 else month_key
                raise HTTPException(
                    status_code=409,
                    detail=f"Vendor charges already computed for {month_label}. Retry with overwrite=true to replace saved rows (all vendors for that month, or only selected vendors if vendor_ids is set).",
                )

        batch_ids = [b.batch_id for b in batches if b.vendor_id == vendor_id]
        if batch_ids:
            vendor_txns = (
                db.query(CanonicalTransaction)
                .filter(CanonicalTransaction.source == "VENDOR")
                .filter(CanonicalTransaction.raw_batch_id.in_(batch_ids))
                .all()
            )
        else:
            vendor_txns = []
        call_stores = _vendor_mapped_stores_at(db, vendor_id, as_of_date, "CALL")
        call_store_by_code = {str(s.bank_store_code or "").strip(): s for s in call_stores}
        call_store_codes = set(call_store_by_code.keys())
        call_pickups = sum(
            1
            for t in vendor_txns
            if t.pickup_type == "CALL" and str(t.bank_store_code or "").strip() in call_store_codes
        )

        beat_stores = _vendor_mapped_stores_at(db, vendor_id, as_of_date, "BEAT")
        beat_charge = 0.0
        for store in beat_stores:
            beat_charge += float(getattr(store, "vendor_charge", None) or 0)
        beat_pickups = len(beat_stores)

        per_store_call_counts: dict[str, int] = {}
        for t in vendor_txns:
            if t.pickup_type != "CALL":
                continue
            code = str(t.bank_store_code or "").strip()
            if code in call_store_by_code:
                per_store_call_counts[code] = per_store_call_counts.get(code, 0) + 1
        call_charge = 0.0
        for code, st in call_store_by_code.items():
            n = per_store_call_counts.get(code, 0)
            if n <= 0:
                continue
            rate = getattr(st, "call_vendor_pay_per_pickup", None)
            if rate is None or float(rate) <= 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"CALL store {code}: set Vendor pay per CALL pickup (₹) on Store Onboarding for month-end {as_of_date.isoformat()}.",
                )
            call_charge += n * float(rate)

        base_charge_amount = beat_charge + call_charge

        if vendor_id not in batch_vendor_ids_set and beat_charge == 0.0 and call_charge == 0.0:
            continue

        total_remittance = sum(float(t.pickup_amount or 0) for t in vendor_txns)
        enhancement_units = math.floor(total_remittance / threshold)
        enhancement_amount = 0

        total_charge_amount = base_charge_amount + enhancement_amount
        tax_amount = total_charge_amount * (gst_rate / 100) if str(gst_enabled).upper() == "Y" else 0.0
        total_with_tax = total_charge_amount + tax_amount

        summary = VendorChargeSummary(
            vendor_id=vendor_id,
            month_key=month_key,
            beat_pickups=beat_pickups,
            call_pickups=call_pickups,
            base_charge_amount=base_charge_amount,
            enhancement_charge=enhancement_amount,
            tax_amount=tax_amount,
            total_charge_amount=total_charge_amount,
            total_with_tax=total_with_tax,
            status="COMPUTED",
            computed_by=user.employee_id,
        )
        db.add(summary)
        results.append(summary)

    log_audit(
        db,
        entity_type="CHARGES",
        entity_id="VENDOR",
        action="COMPUTE",
        old_data=None,
        new_data=f"month_key={month_key},count={len(results)},overwrite={overwrite}",
        changed_by=user.employee_id,
    )
    db.commit()
    return {"status": "ok", "computed": len(results)}

@router.post("/customer/compute")
def compute_customer_charges(payload: dict, user: AuthUser = Depends(require_roles("MAKER", "ADMIN"))):
    month_key = payload.get("month_key")
    if not month_key:
        raise HTTPException(status_code=400, detail="month_key is required (YYYYMM)")
    if not (isinstance(month_key, str) and len(month_key) == 6 and month_key.isdigit()):
        raise HTTPException(status_code=400, detail="month_key must be 6 digits formatted YYYYMM")
    try:
        year = int(month_key[:4])
        month = int(month_key[4:6])
        if not (1 <= month <= 12) or year < 2000 or year > 2100:
            raise ValueError
        last_day = calendar.monthrange(year, month)[1]
        as_of_date = datetime(year, month, last_day).date()
        month_start = datetime(year, month, 1).date()
        month_end = datetime(year, month, last_day).date()
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="month_key must be a valid YYYYMM (e.g. 202601)")

    db = SessionLocal()
    try:
        _enforce_unlocked(db, month_key)
        return _compute_customer_charges_impl(
            db, payload, user, month_key, year, month, as_of_date, month_start, month_end
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def _compute_customer_charges_impl(
    db, payload, user, month_key, year, month, as_of_date, month_start, month_end
):

    from_date = None
    to_date = None
    if payload.get("from_date"):
        try:
            from_date = datetime.strptime(str(payload["from_date"])[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            pass
    if payload.get("to_date"):
        try:
            to_date = datetime.strptime(str(payload["to_date"])[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            pass
    txn_from = max(month_start, from_date) if from_date else month_start
    txn_to = min(month_end, to_date) if to_date else month_end

    ow = payload.get("overwrite")
    overwrite = ow is True or (isinstance(ow, str) and str(ow).strip().lower() in ("1", "true", "yes"))
    if overwrite:
        db.query(CustomerChargeSummary).filter(CustomerChargeSummary.month_key == month_key).delete(
            synchronize_session=False
        )

    gst_enabled = _get_config_text(db, GST_ENABLED_CODE, as_of_date)
    gst_rate = _get_config_number(db, GST_RATE_CODE, as_of_date) or 0.0
    threshold = _get_config_number(db, ENHANCEMENT_THRESHOLD_CODE, as_of_date) or 50000.0
    enhancement_per_unit = _get_config_number(db, ENHANCEMENT_CHARGE_CODE, as_of_date) or 60.0

    store_by_code = _active_store_code_to_id(db)
    active_stores_by_id = {
        s.store_id: s for s in db.query(BankStoreMaster).filter(BankStoreMaster.status == "ACTIVE").all()
    }
    final_candidates = (
        db.query(ReconciliationResult)
        .filter(ReconciliationResult.is_final == 1)
        .filter(
            or_(
                and_(ReconciliationResult.mis_date >= month_start, ReconciliationResult.mis_date <= month_end),
                and_(
                    ReconciliationResult.mis_date.is_(None),
                    or_(
                        and_(
                            ReconciliationResult.pickup_date >= month_start,
                            ReconciliationResult.pickup_date <= month_end,
                        ),
                        and_(
                            ReconciliationResult.remittance_date >= month_start,
                            ReconciliationResult.remittance_date <= month_end,
                        ),
                    ),
                ),
            )
        )
        .all()
    )

    by_store_day: dict[tuple[int, object], float] = {}
    for r in final_candidates:
        date_val = r.mis_date or r.pickup_date or r.remittance_date
        if not date_val or date_val.strftime("%Y%m") != month_key:
            continue
        if date_val < txn_from or date_val > txn_to:
            continue
        store_id = _store_id_from_recon_code(store_by_code, r.bank_store_code)
        if not store_id:
            continue
        store_row = active_stores_by_id.get(store_id)
        if not store_row:
            continue
        amt = float(r.remittance_amount) if r.remittance_amount is not None else 0.0
        if amt == 0.0 and r.pickup_amount is not None:
            amt = float(r.pickup_amount)
        by_store_day[(store_id, date_val)] = amt

    store_data: dict[int, dict[str, float]] = {}
    daily_totals: dict[int, dict[object, float]] = {}
    reconciliation_rows_used = len(by_store_day)
    for (store_id, date_val), amt in by_store_day.items():
        if store_id not in store_data:
            store_data[store_id] = {"remittance": 0.0}
        store_data[store_id]["remittance"] += amt
        if store_id not in daily_totals:
            daily_totals[store_id] = {}
        daily_totals[store_id][date_val] = amt

    store_totals: dict[int, dict[str, float | int]] = {}
    for store_id, data in store_data.items():
        store_totals[store_id] = {
            "total_remittance": data["remittance"],
            "base_charge": 0.0,
            "enhancement": 0.0,
            "days_over_limit": 0,
            "store_waiver_applied": 0.0,
        }

    call_pickup_counts = _call_pickup_counts_by_store(db, month_key)
    for sid, _cnt in call_pickup_counts.items():
        store_row = active_stores_by_id.get(sid)
        if not store_row or (store_row.pickup_type or "BEAT").upper() != "CALL":
            continue
        if sid not in store_totals:
            rem = float(store_data.get(sid, {}).get("remittance", 0.0))
            store_totals[sid] = {
                "total_remittance": rem,
                "base_charge": 0.0,
                "enhancement": 0.0,
                "days_over_limit": 0,
                "store_waiver_applied": 0.0,
            }
            if sid not in store_data:
                store_data[sid] = {"remittance": rem}

    store_ids_all = set(store_totals.keys())
    stores_by_id = (
        {
            s.store_id: s
            for s in db.query(BankStoreMaster).filter(BankStoreMaster.store_id.in_(store_ids_all)).all()
        }
        if store_ids_all
        else {}
    )

    for store_id, agg in store_totals.items():
        store = stores_by_id.get(store_id)
        if not store:
            continue
        wp = store.waiver_percentage
        wcap = _effective_store_waiver_cap(store, as_of_date)

        if (store.pickup_type or "BEAT").upper() == "CALL":
            pickup_count = int(call_pickup_counts.get(store_id, 0))
            included = int(getattr(store, "call_included_pickups", None) or 0)
            pkg = float(getattr(store, "call_monthly_bank_charge", None) or 0)
            addl = float(getattr(store, "call_additional_bank_per_pickup", None) or 0)
            base_store = pkg + max(0, pickup_count - included) * addl
            enh_store = 0.0
            days_over = 0
        else:
            limit = float(store.daily_pickup_limit or 0)
            monthly = float(store.fixed_charge or 0)
            base_store = monthly
            enh_store = 0.0
            days_over = 0
            for _d, daily_amt in daily_totals.get(store_id, {}).items():
                if limit > 0 and daily_amt > limit:
                    days_over += 1
                    excess = daily_amt - limit
                    if threshold > 0:
                        enh_store += math.floor(excess / threshold) * enhancement_per_unit

        billed_prior = (
            _cumulative_store_charges_in_cap_window(db, store_id, store, month_key) if wcap is not None else 0.0
        )
        contrib_b, contrib_e, sw = _apply_store_waiver_for_charge(
            base_store,
            enh_store,
            float(wp) if wp is not None else None,
            float(wcap) if wcap is not None else None,
            billed_prior,
        )
        agg["base_charge"] = float(agg["base_charge"]) + contrib_b
        agg["enhancement"] = float(agg["enhancement"]) + contrib_e
        agg["days_over_limit"] = int(agg["days_over_limit"]) + days_over
        agg["store_waiver_applied"] = float(agg["store_waiver_applied"]) + sw

    results = []
    for store_id, data in store_totals.items():
        if not overwrite:
            existing = (
                db.query(CustomerChargeSummary)
                .filter(CustomerChargeSummary.store_id == store_id)
                .filter(CustomerChargeSummary.month_key == month_key)
                .first()
            )
            if existing:
                month_label = f"{calendar.month_name[month]} {year}" if month_key and len(month_key) >= 6 else month_key
                raise HTTPException(
                    status_code=409,
                    detail=f"Store charges already computed for {month_label}. Retry with overwrite=true to replace all saved rows for that month using the current From/To window.",
                )

        base_charge_amount = float(data["base_charge"]) + float(data["enhancement"])
        enhancement_amount = float(data["enhancement"])
        net_charge_amount = base_charge_amount
        tax_amount = net_charge_amount * (gst_rate / 100) if str(gst_enabled).upper() == "Y" else 0.0
        total_with_tax = net_charge_amount + tax_amount

        sw_applied = float(data.get("store_waiver_applied", 0))
        summary = CustomerChargeSummary(
            store_id=store_id,
            customer_id=None,
            month_key=month_key,
            charge_period_from=txn_from,
            charge_period_to=txn_to,
            total_remittance=float(data["total_remittance"]),
            base_charge_amount=float(data["base_charge"]),
            enhancement_charge=enhancement_amount,
            days_over_limit=int(data.get("days_over_limit", 0)),
            waiver_amount=0.0,
            store_waiver_applied=sw_applied,
            net_charge_amount=net_charge_amount,
            tax_amount=tax_amount,
            total_with_tax=total_with_tax,
            status="COMPUTED",
            computed_by=user.employee_id,
        )
        db.add(summary)
        results.append(summary)

    log_audit(
        db,
        entity_type="CHARGES",
        entity_id="STORE",
        action="COMPUTE",
        old_data=None,
        new_data=f"month_key={month_key},count={len(results)},overwrite={overwrite},period={txn_from}..{txn_to}",
        changed_by=user.employee_id,
    )
    db.commit()
    stored_month_count = (
        db.query(CustomerChargeSummary).filter(CustomerChargeSummary.month_key == month_key).count()
    )
    return {
        "status": "ok",
        "computed": len(results),
        "reconciliation_final_rows": reconciliation_rows_used,
        "customer_summaries_in_db_for_month": stored_month_count,
    }
