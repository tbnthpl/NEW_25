from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func

from backend.auth import AuthUser, require_roles
from backend.db import SessionLocal
from backend.models import (
    ApprovalRequest,
    BankStoreMaster,
    CustomerChargeSummary,
    FinacleUploadBatch,
    ReconciliationResult,
    VendorChargeSummary,
    VendorMaster,
    VendorStoreMappingMaster,
    VendorUploadBatch,
    MonthLock,
)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

def _month_bounds(d: date) -> tuple[date, date, str]:
    last_day = calendar.monthrange(d.year, d.month)[1]
    start = date(d.year, d.month, 1)
    end = date(d.year, d.month, last_day)
    return start, end, f"{d.year:04d}{d.month:02d}"

def _prev_month_keys(d: date, count: int) -> list[str]:
    keys: list[str] = []
    y, m = d.year, d.month
    for _ in range(count):
        keys.append(f"{y:04d}{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return list(reversed(keys))

@router.get("/summary")
def dashboard_summary(user: AuthUser = Depends(require_roles("MAKER", "CHECKER", "ADMIN", "AUDITOR"))):
    today = date.today()
    month_start, month_end, month_key = _month_bounds(today)
    db = SessionLocal()
    try:
        active_stores = (
            db.query(func.count(BankStoreMaster.store_id))
            .filter(BankStoreMaster.status == "ACTIVE")
            .scalar()
            or 0
        )
        active_vendors = (
            db.query(func.count(VendorMaster.vendor_id))
            .filter(VendorMaster.status == "ACTIVE")
            .scalar()
            or 0
        )
        active_mappings = (
            db.query(func.count(VendorStoreMappingMaster.mapping_id))
            .filter(VendorStoreMappingMaster.status == "ACTIVE")
            .scalar()
            or 0
        )

        seven_days_ago = datetime.now() - timedelta(days=7)
        finacle_uploads_7d = (
            db.query(func.count(FinacleUploadBatch.batch_id))
            .filter(FinacleUploadBatch.uploaded_at >= seven_days_ago)
            .scalar()
            or 0
        )
        vendor_uploads_7d = (
            db.query(func.count(VendorUploadBatch.batch_id))
            .filter(VendorUploadBatch.uploaded_at >= seven_days_ago)
            .scalar()
            or 0
        )

        recon_rows = (
            db.query(ReconciliationResult.status, func.count(ReconciliationResult.recon_id))
            .filter(ReconciliationResult.mis_date >= month_start)
            .filter(ReconciliationResult.mis_date <= month_end)
            .group_by(ReconciliationResult.status)
            .all()
        )
        recon_breakdown = {status: int(cnt) for status, cnt in recon_rows}
        recon_total = sum(recon_breakdown.values())
        recon_matched = recon_breakdown.get("MATCHED", 0)
        recon_rate = round((recon_matched / recon_total) * 100, 1) if recon_total else 0.0

        pending_approvals = (
            db.query(func.count(ApprovalRequest.approval_id))
            .filter(ApprovalRequest.status == "PENDING")
            .scalar()
            or 0
        )
        clarification_approvals = (
            db.query(func.count(ApprovalRequest.approval_id))
            .filter(ApprovalRequest.status == "CLARIFICATION")
            .scalar()
            or 0
        )

        vendor_charge_total = (
            db.query(func.coalesce(func.sum(VendorChargeSummary.total_with_tax), 0))
            .filter(VendorChargeSummary.month_key == month_key)
            .scalar()
            or 0
        )
        vendor_charge_count = (
            db.query(func.count(VendorChargeSummary.summary_id))
            .filter(VendorChargeSummary.month_key == month_key)
            .scalar()
            or 0
        )
        customer_charge_total = (
            db.query(func.coalesce(func.sum(CustomerChargeSummary.total_with_tax), 0))
            .filter(CustomerChargeSummary.month_key == month_key)
            .scalar()
            or 0
        )
        customer_charge_count = (
            db.query(func.count(CustomerChargeSummary.summary_id))
            .filter(CustomerChargeSummary.month_key == month_key)
            .scalar()
            or 0
        )

        lock = db.query(MonthLock).filter(MonthLock.month_key == month_key).first()
        month_locked = bool(lock and (lock.status or "").upper() == "LOCKED")

        vendors_with_mis = {
            vid
            for (vid,) in db.query(VendorUploadBatch.vendor_id)
            .filter(VendorUploadBatch.mis_date >= month_start)
            .filter(VendorUploadBatch.mis_date <= month_end)
            .distinct()
            .all()
        }
        active_vendor_rows = (
            db.query(VendorMaster.vendor_id, VendorMaster.vendor_name)
            .filter(VendorMaster.status == "ACTIVE")
            .all()
        )
        vendors_no_mis = [name or str(vid) for vid, name in active_vendor_rows if vid not in vendors_with_mis]

        finacle_dates = {
            d
            for (d,) in db.query(FinacleUploadBatch.mis_date)
            .filter(FinacleUploadBatch.mis_date >= month_start)
            .filter(FinacleUploadBatch.mis_date <= month_end)
            .distinct()
            .all()
        }
        recon_dates = {
            d
            for (d,) in db.query(ReconciliationResult.mis_date)
            .filter(ReconciliationResult.mis_date >= month_start)
            .filter(ReconciliationResult.mis_date <= month_end)
            .distinct()
            .all()
        }
        unreconciled_dates = sorted(d.isoformat() for d in (finacle_dates - recon_dates) if d)

        trend_keys = _prev_month_keys(today, 6)
        charge_trend = []
        for mk in trend_keys:
            v = (
                db.query(func.coalesce(func.sum(VendorChargeSummary.total_with_tax), 0))
                .filter(VendorChargeSummary.month_key == mk)
                .scalar()
                or 0
            )
            c = (
                db.query(func.coalesce(func.sum(CustomerChargeSummary.total_with_tax), 0))
                .filter(CustomerChargeSummary.month_key == mk)
                .scalar()
                or 0
            )
            charge_trend.append(
                {"month_key": mk, "vendor_total": float(v), "customer_total": float(c)}
            )

        return {
            "as_of": datetime.now().isoformat(),
            "month_key": month_key,
            "masters": {
                "active_stores": int(active_stores),
                "active_vendors": int(active_vendors),
                "active_mappings": int(active_mappings),
            },
            "uploads": {
                "finacle_last_7_days": int(finacle_uploads_7d),
                "vendor_last_7_days": int(vendor_uploads_7d),
            },
            "reconciliation": {
                "total": recon_total,
                "matched": recon_matched,
                "exceptions": recon_total - recon_matched,
                "match_rate": recon_rate,
                "breakdown": recon_breakdown,
            },
            "approvals": {
                "pending": int(pending_approvals),
                "clarification": int(clarification_approvals),
            },
            "charges": {
                "vendor_total": float(vendor_charge_total),
                "vendor_count": int(vendor_charge_count),
                "customer_total": float(customer_charge_total),
                "customer_count": int(customer_charge_count),
            },
            "month_lock": {"locked": month_locked},
            "actions": {
                "pending_approvals": int(pending_approvals),
                "month_unlocked": not month_locked,
                "vendors_no_mis": vendors_no_mis,
                "vendors_no_mis_count": len(vendors_no_mis),
                "unreconciled_dates": unreconciled_dates,
                "unreconciled_dates_count": len(unreconciled_dates),
            },
            "charge_trend": charge_trend,
        }
    finally:
        db.close()
