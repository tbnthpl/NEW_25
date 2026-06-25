from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field

class ApprovalDecision(BaseModel):
    checker_id: str
    comment: str

class CommentRequest(BaseModel):
    comment: str

class ResubmitRequest(BaseModel):
    comment: str
    proposed_data: dict | None = None

class UploadResponse(BaseModel):
    batch_id: int
    total_rows: int
    invalid_rows: int
    status: str
    missing_store_codes: Optional[list[str]] = None

class VendorFileFormatRequest(BaseModel):
    vendor_id: int
    format_name: str
    header_mapping_json: str
    effective_from: date
    status: str
    maker_id: str
    reason: Optional[str] = None

class VendorFileFormatResponse(BaseModel):
    config_id: int
    vendor_id: int
    format_name: str
    header_mapping_json: str
    status: str
    effective_from: date

class StoreMappingRow(BaseModel):
    vendor_id: int
    vendor_store_code: str
    bank_store_code: str
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    account_no: Optional[str] = None
    effective_from: Optional[date] = None

class StoreMappingRequest(BaseModel):
    mappings: list[StoreMappingRow]
    maker_id: str
    reason: Optional[str] = None

class StoreMappingDeactivateRequest(BaseModel):
    maker_id: str
    reason: Optional[str] = None

class AdminCleanupRequest(BaseModel):
    targets: list[str]
    reason: str
    confirm_text: str

class AdminResetAllRequest(BaseModel):
    reason: str
    confirm_text: str

class FinacleFormatUpdateRequest(BaseModel):
    mapping: dict[str, str]

class StoreMappingResponse(BaseModel):
    mapping_id: int
    vendor_id: int
    vendor_store_code: str
    bank_store_code: str
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    account_no: Optional[str] = None

class ReconciliationResultResponse(BaseModel):
    recon_id: int
    bank_store_code: str
    pickup_date: Optional[date]
    remittance_date: Optional[date]
    pickup_amount: Optional[float]
    remittance_amount: Optional[float]
    status: str
    reason: Optional[str] = None

class CorrectionRequest(BaseModel):
    recon_id: int
    requested_action: str
    details: Optional[str] = None
    maker_id: str
    reason: Optional[str] = None

class CorrectionResponse(BaseModel):
    correction_id: int
    recon_id: int
    requested_action: str
    details: Optional[str]
    status: str

class PickupRuleRequest(BaseModel):
    pickup_type: str
    free_limit: Optional[float] = Field(default=None, ge=0)
    effective_from: date
    status: str
    maker_id: str
    reason: Optional[str] = None

class PickupRuleResponse(BaseModel):
    rule_id: int
    pickup_type: str
    free_limit: Optional[float] = None
    status: str
    effective_from: date

class MonthLockRequest(BaseModel):
    lock_month: str

class MonthLockResponse(BaseModel):
    lock_id: int
    lock_month: str
    locked_by: str
    locked_at: datetime

class VendorMasterRequest(BaseModel):
    vendor_name: str
    vendor_code: str
    status: str
    effective_from: date
    maker_id: str
    reason: Optional[str] = None

class VendorMasterResponse(BaseModel):
    vendor_id: int
    name: str
    code: str
    status: str

class VendorDeactivateRequest(BaseModel):
    vendor_id: int
    maker_id: str
    reason: Optional[str] = None

class BankStoreRequest(BaseModel):
    bank_store_code: str
    store_name: Optional[str] = None
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    account_no: Optional[str] = None
    sol_id: Optional[str] = None
    pickup_type: Optional[str] = "BEAT"
    daily_pickup_limit: Optional[float] = Field(default=None, ge=0)
    fixed_charge: Optional[float] = Field(default=None, ge=0)
    vendor_charge: Optional[float] = Field(default=None, ge=0)
    call_included_pickups: Optional[int] = Field(default=None, ge=0)
    call_monthly_bank_charge: Optional[float] = Field(default=None, ge=0)
    call_additional_bank_per_pickup: Optional[float] = Field(default=None, ge=0)
    call_vendor_pay_per_pickup: Optional[float] = Field(default=None, ge=0)
    waiver_percentage: Optional[float] = Field(default=None, ge=0, le=100)
    waiver_cap_amount: Optional[float] = Field(default=None, ge=0)
    waiver_cap_from: Optional[date] = None
    waiver_cap_to: Optional[date] = None
    effective_from: date
    status: str
    maker_id: str
    reason: Optional[str] = None

class BankStoreDeactivateRequest(BaseModel):
    store_id: int
    maker_id: str
    reason: Optional[str] = None

class BankStoreUpdateRequest(BaseModel):
    store_id: int
    bank_store_code: str
    store_name: Optional[str] = None
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    account_no: Optional[str] = None
    sol_id: Optional[str] = None
    pickup_type: Optional[str] = "BEAT"
    daily_pickup_limit: Optional[float] = Field(default=None, ge=0)
    fixed_charge: Optional[float] = Field(default=None, ge=0)
    vendor_charge: Optional[float] = Field(default=None, ge=0)
    call_included_pickups: Optional[int] = Field(default=None, ge=0)
    call_monthly_bank_charge: Optional[float] = Field(default=None, ge=0)
    call_additional_bank_per_pickup: Optional[float] = Field(default=None, ge=0)
    call_vendor_pay_per_pickup: Optional[float] = Field(default=None, ge=0)
    waiver_percentage: Optional[float] = Field(default=None, ge=0, le=100)
    waiver_cap_amount: Optional[float] = Field(default=None, ge=0)
    waiver_cap_from: Optional[date] = None
    waiver_cap_to: Optional[date] = None
    effective_from: date
    maker_id: str
    reason: Optional[str] = None

class BankStoreResponse(BaseModel):
    bank_store_code: str
    store_name: Optional[str]
    customer_id: Optional[str]
    customer_name: Optional[str]
    account_no: Optional[str]
    status: str
    effective_from: date
    call_included_pickups: Optional[int] = None
    call_monthly_bank_charge: Optional[float] = None
    call_additional_bank_per_pickup: Optional[float] = None
    call_vendor_pay_per_pickup: Optional[float] = None

class ChargeConfigRequest(BaseModel):
    config_code: str
    config_name: str
    value_number: Optional[float] = Field(default=None, ge=0)
    value_text: Optional[str] = None
    effective_from: date
    status: str
    maker_id: str
    reason: Optional[str] = None

class CustomerExcessChargePairRequest(BaseModel):

    excess_step_amount: float = Field(..., ge=0)
    charge_per_step: float = Field(..., ge=0)
    effective_from: date
    maker_id: str
    reason: Optional[str] = None

class ChargeConfigResponse(BaseModel):
    config_code: str
    config_name: str
    value_number: Optional[float]
    status: str

class VendorChargeRequest(BaseModel):
    vendor_id: int
    pickup_type: str
    base_charge: float = Field(..., ge=0)
    effective_from: date
    status: str
    maker_id: str
    reason: Optional[str] = None

class VendorChargeResponse(BaseModel):
    vendor_id: int
    pickup_type: str
    base_charge: float
    status: str

class CustomerChargeSlabRequest(BaseModel):
    store_id: int
    amount_from: float = Field(..., ge=0)
    amount_to: float = Field(..., ge=0)
    charge_amount: float = Field(..., ge=0)
    slab_label: Optional[str] = None
    effective_from: date
    maker_id: str
    reason: Optional[str] = None

class VendorBeatSlabRequest(BaseModel):
    vendor_id: int
    amount_from: float = Field(..., ge=0)
    amount_to: float = Field(..., ge=0)
    charge_amount: float = Field(..., ge=0)
    slab_label: Optional[str] = None
    effective_from: date
    maker_id: str
    reason: Optional[str] = None

class VendorBeatSlabEditRequest(BaseModel):
    slab_id: int
    amount_from: float = Field(..., ge=0)
    amount_to: float = Field(..., ge=0)
    charge_amount: float = Field(..., ge=0)
    slab_label: Optional[str] = None
    effective_from: date
    maker_id: str
    reason: Optional[str] = None

class CustomerChargeSlabEditRequest(BaseModel):
    slab_id: int
    amount_from: float = Field(..., ge=0)
    amount_to: float = Field(..., ge=0)
    charge_amount: float = Field(..., ge=0)
    slab_label: Optional[str] = None
    effective_from: date
    maker_id: str
    reason: Optional[str] = None

class WaiverRequest(BaseModel):
    customer_id: str
    waiver_type: str
    waiver_percentage: Optional[float] = Field(default=None, ge=0, le=100)
    waiver_cap_amount: Optional[float] = Field(default=None, ge=0)
    waiver_from: date
    waiver_to: Optional[date] = None
    status: str
    maker_id: str
    reason: Optional[str] = None

class WaiverResponse(BaseModel):
    waiver_id: int
    customer_id: str
    waiver_type: str
    status: str

class RemittanceRequest(BaseModel):
    canonical_ids: list[int]
    maker_id: str
    reason: Optional[str] = None

class RemittanceStatusRequest(BaseModel):
    remittance_id: int
    maker_id: str
    reason: Optional[str] = None

class RemittanceApprovalRequest(BaseModel):
    remittance_id: int
    action: str
    maker_id: str
    rejection_reason: Optional[str] = None
    reason: Optional[str] = None

class RemittanceResponse(BaseModel):
    remittance_id: int
    canonical_id: int
    source: str
    status: str

class ExceptionRequest(BaseModel):
    recon_id: int
    exception_type: str
    details: Optional[str] = None
    maker_id: str
    reason: Optional[str] = None

class ExceptionResolutionRequest(BaseModel):
    exception_id: int
    proposed_status: str
    remarks: Optional[str] = None
    maker_id: str
    reason: Optional[str] = None

class ExceptionResponse(BaseModel):
    exception_id: int
    recon_id: int
    exception_type: str
    status: str
