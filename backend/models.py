from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Sequence,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship
from sqlalchemy import Numeric as Number

from backend.db import Base

class BankStoreMaster(Base):
    __tablename__ = "dsb_bank_store_master"

    store_id = Column(Number, Sequence("seq_dsb_bank_store_master"), primary_key=True)
    bank_store_code = Column(String(30), nullable=False, unique=True)
    store_name = Column(String(150))
    customer_id = Column(String(50))
    customer_name = Column(String(150))
    account_no = Column(String(30))
    sol_id = Column(String(20))
    location = Column(String(150))
    frequency = Column(String(30))
    pickup_type = Column(String(10), default="BEAT")
    daily_pickup_limit = Column(Number(18, 2))
    deposition_branch = Column(String(50))
    deposition_branchname = Column(String(150))
    fixed_charge = Column(Number(18, 2))
    vendor_charge = Column(Number(18, 2))
    call_included_pickups = Column(Number(10))
    call_monthly_bank_charge = Column(Number(18, 2))
    call_additional_bank_per_pickup = Column(Number(18, 2))
    call_vendor_pay_per_pickup = Column(Number(18, 2))
    waiver_percentage = Column(Number(5, 2))
    waiver_cap_amount = Column(Number(18, 2))
    waiver_cap_from = Column(Date)
    waiver_cap_to = Column(Date)
    status = Column(String(10), nullable=False)
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date)
    created_by = Column(String(50), nullable=False)
    created_date = Column(DateTime, server_default=func.now(), nullable=False)
    approved_by = Column(String(50))
    approved_date = Column(DateTime)
    onboarded_date = Column(Date)
    last_modified_date = Column(DateTime)

    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="chk_bank_store_status"),
        CheckConstraint("pickup_type IN ('BEAT','CALL')", name="chk_store_pickup_type"),
    )

class VendorMaster(Base):
    __tablename__ = "dsb_vendor_master"

    vendor_id = Column(Number, Sequence("seq_dsb_vendor_master"), primary_key=True)
    vendor_code = Column(String(30), nullable=False, unique=True)
    vendor_name = Column(String(150), nullable=False)
    status = Column(String(10), nullable=False)
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date)
    created_by = Column(String(50), nullable=False)
    created_date = Column(DateTime, server_default=func.now(), nullable=False)
    approved_by = Column(String(50))
    approved_date = Column(DateTime)

    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="chk_vendor_status"),
    )

class UserAccount(Base):
    __tablename__ = "dsb_user_account"

    user_id = Column(Number, Sequence("seq_dsb_user_account"), primary_key=True)
    employee_id = Column(String(50), nullable=False, unique=True)
    full_name = Column(String(150), nullable=False)
    role_code = Column(String(20), nullable=False)
    password_hash = Column(String(255), nullable=False)
    status = Column(String(10), nullable=False)
    created_date = Column(DateTime, server_default=func.now(), nullable=False)
    last_login_date = Column(DateTime)

    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="chk_user_status"),
    )

class UserSession(Base):

    __tablename__ = "dsb_user_session"

    session_id = Column(Number, Sequence("seq_dsb_user_session"), primary_key=True)
    token = Column(String(64), nullable=False, unique=True)
    employee_id = Column(String(50), nullable=False)
    role_code = Column(String(20), nullable=False)
    full_name = Column(String(150), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    last_seen_at = Column(DateTime, nullable=True)

class VendorStoreMappingMaster(Base):
    __tablename__ = "dsb_vendor_store_mapping_master"

    mapping_id = Column(Number, Sequence("seq_dsb_vendor_store_mapping"), primary_key=True)
    vendor_id = Column(Number, ForeignKey("dsb_vendor_master.vendor_id"), nullable=False)
    vendor_store_code = Column(String(50), nullable=False)
    bank_store_code = Column(String(30), nullable=False)
    customer_id = Column(String(50))
    customer_name = Column(String(150))
    account_no = Column(String(30))
    status = Column(String(10), nullable=False)
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date)
    created_by = Column(String(50), nullable=False)
    created_date = Column(DateTime, server_default=func.now(), nullable=False)
    approved_by = Column(String(50))
    approved_date = Column(DateTime)

    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="chk_mapping_status"),
    )

class ChargeConfigurationMaster(Base):
    __tablename__ = "dsb_charge_configuration_master"

    config_id = Column(Number, Sequence("seq_dsb_charge_config_master"), primary_key=True)
    config_code = Column(String(50), nullable=False)
    config_name = Column(String(150), nullable=False)
    value_number = Column(Number(18, 4))
    value_text = Column(String(200))
    value_date = Column(Date)
    unit_of_measure = Column(String(30))
    status = Column(String(10), nullable=False)
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date)
    created_by = Column(String(50), nullable=False)
    created_date = Column(DateTime, server_default=func.now(), nullable=False)
    approved_by = Column(String(50))
    approved_date = Column(DateTime)

    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="chk_charge_config_status"),
    )

class PickupRulesMaster(Base):
    __tablename__ = "dsb_pickup_rules_master"

    rule_id = Column(Number, Sequence("seq_dsb_pickup_rules_master"), primary_key=True)
    pickup_type = Column(String(10), nullable=False)
    free_limit = Column(Number(10))
    status = Column(String(10), nullable=False)
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date)
    created_by = Column(String(50), nullable=False)
    created_date = Column(DateTime, server_default=func.now(), nullable=False)
    approved_by = Column(String(50))
    approved_date = Column(DateTime)

    __table_args__ = (
        CheckConstraint("pickup_type IN ('BEAT','CALL')", name="chk_pickup_type"),
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="chk_pickup_rules_status"),
    )

class VendorChargeMaster(Base):
    __tablename__ = "dsb_vendor_charge_master"

    vendor_charge_id = Column(Number, Sequence("seq_dsb_vendor_charge_master"), primary_key=True)
    vendor_id = Column(Number, ForeignKey("dsb_vendor_master.vendor_id"), nullable=False)
    pickup_type = Column(String(10), nullable=False)
    base_charge = Column(Number(18, 2), nullable=False)
    status = Column(String(10), nullable=False)
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date)
    created_by = Column(String(50), nullable=False)
    created_date = Column(DateTime, server_default=func.now(), nullable=False)
    approved_by = Column(String(50))
    approved_date = Column(DateTime)

    __table_args__ = (
        CheckConstraint("pickup_type IN ('BEAT','CALL')", name="chk_vendor_charge_type"),
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="chk_vendor_charge_status"),
    )

class CustomerChargeSlab(Base):
    __tablename__ = "dsb_customer_charge_slabs"

    slab_id = Column(Number, Sequence("seq_dsb_customer_charge_slab"), primary_key=True)
    store_id = Column(Number, ForeignKey("dsb_bank_store_master.store_id"), nullable=False)
    amount_from = Column(Number(18, 2), nullable=False)
    amount_to = Column(Number(18, 2), nullable=False)
    charge_amount = Column(Number(18, 2), nullable=False)
    slab_label = Column(String(100))
    status = Column(String(10), nullable=False)
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date)
    created_by = Column(String(50), nullable=False)
    created_date = Column(DateTime, server_default=func.now(), nullable=False)
    approved_by = Column(String(50))
    approved_date = Column(DateTime)

    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="chk_customer_slab_status"),
    )

class WaiverMaster(Base):
    __tablename__ = "dsb_waiver_master"

    waiver_id = Column(Number, Sequence("seq_dsb_waiver_master"), primary_key=True)
    customer_id = Column(String(50), nullable=False)
    waiver_type = Column(String(20), nullable=False)
    waiver_percentage = Column(Number(5, 2))
    waiver_cap_amount = Column(Number(18, 2))
    waiver_from = Column(Date, nullable=False)
    waiver_to = Column(Date)
    status = Column(String(10), nullable=False)
    created_by = Column(String(50), nullable=False)
    created_date = Column(DateTime, server_default=func.now(), nullable=False)
    approved_by = Column(String(50))
    approved_date = Column(DateTime)

    __table_args__ = (
        CheckConstraint("waiver_type IN ('PERCENT','CAP','BOTH')", name="chk_waiver_type"),
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="chk_waiver_status"),
    )

class VendorBeatSlab(Base):
    __tablename__ = "dsb_vendor_beat_slabs"

    slab_id = Column(Number, Sequence("seq_dsb_vendor_beat_slab"), primary_key=True)
    vendor_id = Column(Number, ForeignKey("dsb_vendor_master.vendor_id"), nullable=False)
    amount_from = Column(Number(18, 2), nullable=False)
    amount_to = Column(Number(18, 2), nullable=False)
    charge_amount = Column(Number(18, 2), nullable=False)
    slab_label = Column(String(100))
    status = Column(String(10), nullable=False)
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date)
    created_by = Column(String(50), nullable=False)
    created_date = Column(DateTime, server_default=func.now(), nullable=False)
    approved_by = Column(String(50))
    approved_date = Column(DateTime)

    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="chk_vendor_beat_slab_status"),
    )

class VendorChargeSummary(Base):
    __tablename__ = "dsb_vendor_charge_summary"

    summary_id = Column(Number, Sequence("seq_dsb_vendor_charge_summary"), primary_key=True)
    vendor_id = Column(Number, ForeignKey("dsb_vendor_master.vendor_id"), nullable=False)
    month_key = Column(String(6), nullable=False)
    beat_pickups = Column(Number(10), default=0)
    call_pickups = Column(Number(10), default=0)
    base_charge_amount = Column(Number(18, 2), default=0)
    enhancement_charge = Column(Number(18, 2), default=0)
    tax_amount = Column(Number(18, 2), default=0)
    total_charge_amount = Column(Number(18, 2), default=0)
    total_with_tax = Column(Number(18, 2), default=0)
    status = Column(String(20), nullable=False)
    computed_by = Column(String(50), nullable=False)
    computed_at = Column(DateTime, server_default=func.now(), nullable=False)

class CustomerChargeSummary(Base):
    __tablename__ = "dsb_customer_charge_summary"

    summary_id = Column(Number, Sequence("seq_dsb_customer_charge_summary"), primary_key=True)
    store_id = Column(Number, ForeignKey("dsb_bank_store_master.store_id"), nullable=False)
    customer_id = Column(String(50))
    month_key = Column(String(6), nullable=False)
    charge_period_from = Column(Date)
    charge_period_to = Column(Date)
    total_remittance = Column(Number(18, 2), default=0)
    base_charge_amount = Column(Number(18, 2), default=0)
    enhancement_charge = Column(Number(18, 2), default=0)
    days_over_limit = Column(Number(10), default=0)
    waiver_amount = Column(Number(18, 2), default=0)
    store_waiver_applied = Column(Number(18, 2), default=0)
    net_charge_amount = Column(Number(18, 2), default=0)
    tax_amount = Column(Number(18, 2), default=0)
    total_with_tax = Column(Number(18, 2), default=0)
    status = Column(String(20), nullable=False)
    computed_by = Column(String(50), nullable=False)
    computed_at = Column(DateTime, server_default=func.now(), nullable=False)

class VendorFileFormatConfig(Base):
    __tablename__ = "dsb_vendor_file_format_config"

    format_id = Column(Number, Sequence("seq_dsb_vendor_file_format"), primary_key=True)
    vendor_id = Column(Number, ForeignKey("dsb_vendor_master.vendor_id"), nullable=False)
    format_name = Column(String(100), nullable=False)
    status = Column(String(10), nullable=False)
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date)
    created_by = Column(String(50), nullable=False)
    created_date = Column(DateTime, server_default=func.now(), nullable=False)
    approved_by = Column(String(50))
    approved_date = Column(DateTime)

    header_mappings = relationship("VendorFileFormatHeaderMapping", back_populates="format_config", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="chk_format_status"),
    )

class VendorFileFormatHeaderMapping(Base):
    __tablename__ = "dsb_vendor_file_format_header_mapping"

    format_id = Column(Number, ForeignKey("dsb_vendor_file_format_config.format_id", ondelete="CASCADE"), primary_key=True)
    mapping_key = Column(String(100), primary_key=True)
    source_column = Column(String(255), nullable=False)

    format_config = relationship("VendorFileFormatConfig", back_populates="header_mappings")

class FinacleHeaderMapping(Base):
    __tablename__ = "dsb_finacle_header_mapping"

    mapping_key = Column(String(100), primary_key=True)
    source_column = Column(String(255), nullable=False)

class FinacleUploadBatch(Base):
    __tablename__ = "dsb_finacle_upload_batch"

    batch_id = Column(Number, Sequence("seq_dsb_finacle_upload_batch"), primary_key=True)
    mis_date = Column(Date, nullable=False)
    file_name = Column(String(255), nullable=False)
    uploaded_by = Column(String(50), nullable=False)
    uploaded_at = Column(DateTime, server_default=func.now(), nullable=False)
    status = Column(String(20), nullable=False)

class VendorUploadBatch(Base):
    __tablename__ = "dsb_vendor_upload_batch"

    batch_id = Column(Number, Sequence("seq_dsb_vendor_upload_batch"), primary_key=True)
    vendor_id = Column(Number, ForeignKey("dsb_vendor_master.vendor_id"), nullable=False)
    mis_date = Column(Date, nullable=False)
    file_name = Column(String(255), nullable=False)
    uploaded_by = Column(String(50), nullable=False)
    uploaded_at = Column(DateTime, server_default=func.now(), nullable=False)
    status = Column(String(20), nullable=False)

class FinacleRawStaging(Base):
    __tablename__ = "dsb_finacle_raw_staging"

    raw_id = Column(Number, Sequence("seq_dsb_finacle_raw_staging"), primary_key=True)
    batch_id = Column(Number, ForeignKey("dsb_finacle_upload_batch.batch_id"), nullable=False)
    row_number = Column(Number, nullable=False)
    row_payload = Column(String(4000), nullable=False)
    created_date = Column(DateTime, server_default=func.now(), nullable=False)

class FinacleInvalidRecord(Base):
    __tablename__ = "dsb_finacle_invalid_records"

    invalid_id = Column(Number, Sequence("seq_dsb_finacle_invalid_record"), primary_key=True)
    batch_id = Column(Number, ForeignKey("dsb_finacle_upload_batch.batch_id"), nullable=False)
    row_number = Column(Number, nullable=False)
    reason = Column(String(255), nullable=False)
    row_payload = Column(String(4000), nullable=False)
    created_date = Column(DateTime, server_default=func.now(), nullable=False)

class VendorRawStaging(Base):
    __tablename__ = "dsb_vendor_raw_staging"

    raw_id = Column(Number, Sequence("seq_dsb_vendor_raw_staging"), primary_key=True)
    batch_id = Column(Number, ForeignKey("dsb_vendor_upload_batch.batch_id"), nullable=False)
    row_number = Column(Number, nullable=False)
    row_payload = Column(String(4000), nullable=False)
    created_date = Column(DateTime, server_default=func.now(), nullable=False)

class VendorInvalidRecord(Base):
    __tablename__ = "dsb_vendor_invalid_records"

    invalid_id = Column(Number, Sequence("seq_dsb_vendor_invalid_record"), primary_key=True)
    batch_id = Column(Number, ForeignKey("dsb_vendor_upload_batch.batch_id"), nullable=False)
    row_number = Column(Number, nullable=False)
    reason = Column(String(255), nullable=False)
    row_payload = Column(String(4000), nullable=False)
    created_date = Column(DateTime, server_default=func.now(), nullable=False)

class CanonicalTransaction(Base):
    __tablename__ = "dsb_canonical_transactions"

    canonical_id = Column(Number, Sequence("seq_dsb_canonical_txn"), primary_key=True)
    source = Column(String(10), nullable=False)
    bank_store_code = Column(String(30), nullable=False)
    vendor_store_code = Column(String(50))
    account_no = Column(String(30))
    customer_id = Column(String(50))
    pickup_date = Column(Date)
    remittance_date = Column(Date)
    pickup_amount = Column(Number(18, 2))
    remittance_amount = Column(Number(18, 2))
    pickup_type = Column(String(10))
    raw_batch_id = Column(Number, nullable=False)
    created_date = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("source IN ('FINACLE','VENDOR')", name="chk_canonical_source"),
        CheckConstraint("pickup_type IN ('BEAT','CALL')", name="chk_canonical_pickup_type"),
    )

class RemittanceEntry(Base):
    __tablename__ = "dsb_remittance_entries"

    remittance_id = Column(Number, Sequence("seq_dsb_remittance_entry"), primary_key=True)
    canonical_id = Column(Number, ForeignKey("dsb_canonical_transactions.canonical_id"), nullable=False)
    source = Column(String(10), nullable=False)
    status = Column(String(20), nullable=False)
    rejection_reason = Column(String(255))
    created_by = Column(String(50), nullable=False)
    created_date = Column(DateTime, server_default=func.now(), nullable=False)
    approved_by = Column(String(50))
    approved_date = Column(DateTime)
    closed_date = Column(DateTime)

    __table_args__ = (
        CheckConstraint("status IN ('UPLOADED','VALIDATED','APPROVED','REJECTED','CLOSED')", name="chk_remittance_status"),
    )

class ReconciliationResult(Base):
    __tablename__ = "dsb_reconciliation_results"

    recon_id = Column(Number, Sequence("seq_dsb_reconciliation_result"), primary_key=True)
    finacle_canonical_id = Column(Number)
    vendor_canonical_id = Column(Number)
    bank_store_code = Column(String(30), nullable=False)
    mis_date = Column(Date)
    pickup_date = Column(Date)
    remittance_date = Column(Date)
    pickup_amount = Column(Number(18, 2))
    remittance_amount = Column(Number(18, 2))
    status = Column(String(20), nullable=False)
    reason = Column(String(255))
    is_final = Column(Number(1), default=0)
    created_date = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "status IN ('MATCHED','AMOUNT_MISMATCH','DATE_MISMATCH','MISSING_FINACLE','MISSING_VENDOR')",
            name="chk_recon_status",
        ),
    )

class ExceptionRecord(Base):
    __tablename__ = "dsb_exception_records"

    exception_id = Column(Number, Sequence("seq_dsb_exception_record"), primary_key=True)
    recon_id = Column(Number, ForeignKey("dsb_reconciliation_results.recon_id"))
    exception_type = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False)
    details = Column(String(255))
    remarks = Column(String(255))
    created_by = Column(String(50), nullable=False)
    created_date = Column(DateTime, server_default=func.now(), nullable=False)
    resolved_by = Column(String(50))
    resolved_date = Column(DateTime)

    __table_args__ = (
        CheckConstraint("status IN ('OPEN','RESOLVED','ESCALATED')", name="chk_exception_status"),
    )

class ApprovalRequest(Base):
    __tablename__ = "dsb_approval_requests"

    approval_id = Column(Number, Sequence("seq_dsb_approval_request"), primary_key=True)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(Number)
    original_data = Column(String(4000), nullable=False)
    proposed_data = Column(String(4000), nullable=False)
    reason = Column(String(255))
    maker_id = Column(String(50), nullable=False)
    checker_id = Column(String(50))
    checker_comment = Column(String(255))
    comments_history = Column(String(4000))
    status = Column(String(20), nullable=False)
    created_date = Column(DateTime, server_default=func.now(), nullable=False)
    approved_date = Column(DateTime)

    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING','APPROVED','REJECTED','CLARIFICATION')", name="chk_approval_status"
        ),
    )

class ReconciliationCorrection(Base):
    __tablename__ = "dsb_reconciliation_corrections"

    correction_id = Column(Number, Sequence("seq_dsb_reconciliation_correction"), primary_key=True)
    recon_id = Column(Number, ForeignKey("dsb_reconciliation_results.recon_id"), nullable=False)
    approval_id = Column(Number, ForeignKey("dsb_approval_requests.approval_id"), nullable=False)
    proposed_data = Column(String(4000), nullable=False)
    status = Column(String(20), nullable=False)
    maker_id = Column(String(50), nullable=False)
    checker_id = Column(String(50))
    created_date = Column(DateTime, server_default=func.now(), nullable=False)
    approved_date = Column(DateTime)

    __table_args__ = (
        CheckConstraint("status IN ('PENDING','APPROVED','REJECTED')", name="chk_corr_status"),
    )

class AuditLog(Base):
    __tablename__ = "dsb_audit_log"

    audit_id = Column(Number, Sequence("seq_dsb_audit_log"), primary_key=True)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(Number)
    action = Column(String(50), nullable=False)
    old_data = Column(String(4000))
    new_data = Column(String(4000))
    changed_by = Column(String(50), nullable=False)
    changed_at = Column(DateTime, server_default=func.now(), nullable=False)

class ApiLog(Base):
    __tablename__ = "dsb_api_log"

    log_id = Column(Number, Sequence("seq_dsb_api_log"), primary_key=True)
    method = Column(String(10))
    path = Column(String(500))
    status_code = Column(Number)
    log_level = Column(String(20), default="ERROR")
    message = Column(String(4000))
    detail = Column(String(4000))
    user_id = Column(String(50))
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

class VendorAbsenceRecord(Base):

    __tablename__ = "dsb_vendor_absence_records"

    absence_id = Column(Number, Sequence("seq_dsb_vendor_absence_record"), primary_key=True)
    vendor_id = Column(Number, ForeignKey("dsb_vendor_master.vendor_id"), nullable=False)
    bank_store_code = Column(String(30), nullable=False)
    vendor_store_code = Column(String(50))
    store_name = Column(String(150))
    absence_date = Column(Date, nullable=False)
    recorded_at = Column(DateTime, server_default=func.now(), nullable=False)
    recorded_by = Column(String(50))

class MonthLock(Base):
    __tablename__ = "dsb_month_lock"

    lock_id = Column(Number, Sequence("seq_dsb_month_lock"), primary_key=True)
    month_key = Column(String(6), nullable=False, unique=True)
    status = Column(String(10), nullable=False)
    locked_by = Column(String(50))
    locked_at = Column(DateTime)

    __table_args__ = (
        CheckConstraint("status IN ('OPEN','LOCKED')", name="chk_month_lock_status"),
    )
