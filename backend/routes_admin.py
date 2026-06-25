import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError

from backend.auth import AuthUser, require_roles
from backend.audit import log_audit
from backend.db import SessionLocal
from backend.models import (
    ApprovalRequest,
    BankStoreMaster,
    FinacleHeaderMapping,
    CanonicalTransaction,
    ChargeConfigurationMaster,
    CustomerChargeSlab,
    CustomerChargeSummary,
    ExceptionRecord,
    FinacleInvalidRecord,
    FinacleRawStaging,
    FinacleUploadBatch,
    MonthLock,
    PickupRulesMaster,
    ReconciliationCorrection,
    ReconciliationResult,
    RemittanceEntry,
    VendorChargeMaster,
    VendorChargeSummary,
    VendorFileFormatConfig,
    VendorFileFormatHeaderMapping,
    VendorInvalidRecord,
    VendorAbsenceRecord,
    VendorBeatSlab,
    VendorMaster,
    VendorRawStaging,
    VendorStoreMappingMaster,
    VendorUploadBatch,
    WaiverMaster,
)
from backend.schemas import AdminCleanupRequest, AdminResetAllRequest

router = APIRouter(prefix="/api/admin", tags=["admin"])

@router.post("/cleanup")
def cleanup_data(
    payload: AdminCleanupRequest,
    user: AuthUser = Depends(require_roles("ADMIN")),
):
    if not payload.reason or not payload.reason.strip():
        raise HTTPException(status_code=400, detail="Reason is required")
    if payload.confirm_text != "CONFIRM":
        raise HTTPException(status_code=400, detail='Type "CONFIRM" to proceed')

    allowed = {"UPLOADS", "TRANSACTIONS", "RECONCILIATION", "APPROVALS", "STORE_MAPPING", "VENDORS_STORES", "MASTERS", "CHARGES", "ALL"}
    targets = {target.strip().upper() for target in payload.targets or []}
    if not targets:
        raise HTTPException(status_code=400, detail="Select at least one target")
    if not targets.issubset(allowed):
        raise HTTPException(status_code=400, detail="Invalid cleanup target")
    if "ALL" in targets:
        targets = {"UPLOADS", "TRANSACTIONS", "RECONCILIATION", "APPROVALS", "VENDORS_STORES", "MASTERS", "CHARGES"}

    db = SessionLocal()
    deleted = {}

    def delete_model(model, label=None):
        count = db.query(model).delete(synchronize_session=False)
        deleted[label or model.__tablename__] = count

    try:
        if "CHARGES" in targets:
            delete_model(CustomerChargeSummary)
            delete_model(VendorChargeSummary)

        if "RECONCILIATION" in targets:
            delete_model(ExceptionRecord)
            delete_model(ReconciliationCorrection)
            delete_model(ReconciliationResult)

        if "TRANSACTIONS" in targets:
            delete_model(RemittanceEntry)
            delete_model(CanonicalTransaction)

        if "UPLOADS" in targets:
            delete_model(VendorRawStaging)
            delete_model(VendorInvalidRecord)
            delete_model(VendorUploadBatch)
            delete_model(FinacleRawStaging)
            delete_model(FinacleInvalidRecord)
            delete_model(FinacleUploadBatch)

        if "APPROVALS" in targets:
            delete_model(ApprovalRequest)

        if "STORE_MAPPING" in targets:
            delete_model(VendorStoreMappingMaster)

        if "VENDORS_STORES" in targets:
            delete_model(VendorStoreMappingMaster)
            delete_model(VendorFileFormatHeaderMapping)
            delete_model(VendorFileFormatConfig)
            delete_model(VendorChargeMaster)
            delete_model(CustomerChargeSlab)
            delete_model(VendorBeatSlab)
            delete_model(VendorAbsenceRecord)
            delete_model(VendorMaster)
            delete_model(BankStoreMaster)

        if "MASTERS" in targets:
            delete_model(WaiverMaster)
            delete_model(PickupRulesMaster)
            delete_model(ChargeConfigurationMaster)

        log_audit(
            db,
            "ADMIN_CLEANUP",
            "BATCH",
            "DELETE",
            None,
            f"targets={sorted(list(targets))}, reason={payload.reason}",
            user.employee_id,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        logging.getLogger(__name__).warning("Admin cleanup integrity error: %s", exc)
        hint = (
            "Cleanup blocked by related data. Include the dependent targets as well: "
            "if clearing Vendors/Stores or Masters, also select Charges, Reconciliation, "
            "Transactions, and Uploads (or use 'ALL'). Nothing was deleted."
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=hint) from exc
    finally:
        db.close()
    return {"deleted": deleted}

@router.post("/reset-all")
def reset_all(
    payload: AdminResetAllRequest,
    user: AuthUser = Depends(require_roles("ADMIN")),
):
    if not payload.reason or not payload.reason.strip():
        raise HTTPException(status_code=400, detail="Reason is required")
    if payload.confirm_text != "RESET ALL":
        raise HTTPException(
            status_code=400,
            detail='Type "RESET ALL" (exactly) to proceed. This clears all application data.',
        )

    db = SessionLocal()
    deleted = {}

    def delete_model(model, label=None):
        count = db.query(model).delete(synchronize_session=False)
        deleted[label or model.__tablename__] = count

    try:
        delete_model(VendorChargeSummary)
        delete_model(CustomerChargeSummary)
        delete_model(RemittanceEntry)
        delete_model(CanonicalTransaction)
        delete_model(ReconciliationCorrection)
        delete_model(ExceptionRecord)
        delete_model(ReconciliationResult)
        delete_model(ApprovalRequest)
        delete_model(VendorRawStaging)
        delete_model(VendorInvalidRecord)
        delete_model(VendorUploadBatch)
        delete_model(FinacleRawStaging)
        delete_model(FinacleInvalidRecord)
        delete_model(FinacleUploadBatch)
        delete_model(VendorStoreMappingMaster)
        delete_model(VendorFileFormatHeaderMapping)
        delete_model(VendorFileFormatConfig)
        delete_model(FinacleHeaderMapping)
        delete_model(VendorChargeMaster)
        delete_model(CustomerChargeSlab)
        delete_model(VendorBeatSlab)
        delete_model(VendorAbsenceRecord)
        delete_model(VendorMaster)
        delete_model(BankStoreMaster)
        delete_model(WaiverMaster)
        delete_model(PickupRulesMaster)
        delete_model(ChargeConfigurationMaster)
        delete_model(MonthLock)

        db.commit()
    except IntegrityError as exc:
        db.rollback()
        logging.getLogger(__name__).warning("Admin reset-all integrity error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Reset blocked by a foreign-key constraint. Nothing was deleted. "
                "Check DB schema for any custom child table pointing at master tables."
            ),
        ) from exc
    finally:
        db.close()
    return {
        "deleted": deleted,
        "message": "Application reset complete. Refresh the page to clear client cache.",
    }
