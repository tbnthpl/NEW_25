-- =============================================================================
-- Doorstep Banking Application - Complete Oracle DDL
-- Single consolidated schema for fresh database setup. Run on an empty schema.
-- No DELETE operations. Use status + effective dates.
-- =============================================================================

-- =========================
-- Sequences
-- =========================
CREATE SEQUENCE seq_dsb_bank_store_master START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE seq_dsb_vendor_master START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE seq_dsb_vendor_store_mapping START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE seq_dsb_charge_config_master START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE seq_dsb_pickup_rules_master START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE seq_dsb_vendor_charge_master START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE seq_dsb_vendor_beat_slab START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE seq_dsb_waiver_master START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE seq_dsb_vendor_file_format START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE seq_dsb_finacle_upload_batch START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE seq_dsb_vendor_upload_batch START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE seq_dsb_finacle_raw_staging START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE seq_dsb_vendor_raw_staging START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE seq_dsb_canonical_txn START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE seq_dsb_reconciliation_result START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE seq_dsb_reconciliation_correction START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE seq_dsb_remittance_entry START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE seq_dsb_exception_record START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE seq_dsb_finacle_invalid_record START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE seq_dsb_vendor_invalid_record START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE seq_dsb_user_account START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE seq_dsb_user_session START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE seq_dsb_approval_request START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE seq_dsb_audit_log START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE seq_dsb_api_log START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE seq_dsb_month_lock START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE seq_dsb_vendor_charge_summary START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE seq_dsb_customer_charge_summary START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE seq_dsb_customer_charge_slab START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE seq_dsb_vendor_absence_record START WITH 1 INCREMENT BY 1 NOCACHE;

-- =========================
-- Master Tables
-- =========================
CREATE TABLE dsb_bank_store_master (
  store_id            NUMBER PRIMARY KEY,
  bank_store_code     VARCHAR2(30) NOT NULL UNIQUE,
  store_name          VARCHAR2(150),
  customer_id         VARCHAR2(50),
  customer_name       VARCHAR2(150),
  account_no          VARCHAR2(30),
  sol_id              VARCHAR2(20),
  location            VARCHAR2(150),
  frequency           VARCHAR2(30),
  pickup_type         VARCHAR2(10) DEFAULT 'BEAT',
  daily_pickup_limit  NUMBER(18,2),
  deposition_branch   VARCHAR2(50),
  deposition_branchname VARCHAR2(150),
  fixed_charge        NUMBER(18,2),
  vendor_charge       NUMBER(18,2),
  call_included_pickups           NUMBER(10),
  call_monthly_bank_charge        NUMBER(18,2),
  call_additional_bank_per_pickup NUMBER(18,2),
  call_vendor_pay_per_pickup      NUMBER(18,2),
  waiver_percentage   NUMBER(5,2),
  waiver_cap_amount   NUMBER(18,2),
  waiver_cap_from     DATE,
  waiver_cap_to       DATE,
  status              VARCHAR2(10) NOT NULL,
  effective_from      DATE NOT NULL,
  effective_to        DATE,
  created_by          VARCHAR2(50) NOT NULL,
  created_date        DATE DEFAULT SYSDATE NOT NULL,
  approved_by         VARCHAR2(50),
  approved_date       DATE,
  onboarded_date      DATE,
  last_modified_date  DATE,
  CONSTRAINT chk_bank_store_status CHECK (status IN ('ACTIVE','INACTIVE')),
  CONSTRAINT chk_store_pickup_type CHECK (pickup_type IN ('BEAT','CALL'))
);

CREATE TABLE dsb_vendor_master (
  vendor_id           NUMBER PRIMARY KEY,
  vendor_code         VARCHAR2(30) NOT NULL UNIQUE,
  vendor_name         VARCHAR2(150) NOT NULL,
  status              VARCHAR2(10) NOT NULL,
  effective_from      DATE NOT NULL,
  effective_to        DATE,
  created_by          VARCHAR2(50) NOT NULL,
  created_date        DATE DEFAULT SYSDATE NOT NULL,
  approved_by         VARCHAR2(50),
  approved_date       DATE,
  CONSTRAINT chk_vendor_status CHECK (status IN ('ACTIVE','INACTIVE'))
);

CREATE TABLE dsb_user_account (
  user_id             NUMBER PRIMARY KEY,
  employee_id         VARCHAR2(50) NOT NULL UNIQUE,
  full_name           VARCHAR2(150) NOT NULL,
  role_code           VARCHAR2(20) NOT NULL,
  password_hash       VARCHAR2(255) NOT NULL,
  status              VARCHAR2(10) NOT NULL,
  created_date        DATE DEFAULT SYSDATE NOT NULL,
  last_login_date     DATE,
  CONSTRAINT chk_user_status CHECK (status IN ('ACTIVE','INACTIVE'))
);

-- H13: shared session store so issued tokens are visible across HPA pods.
CREATE TABLE dsb_user_session (
  session_id          NUMBER PRIMARY KEY,
  token               VARCHAR2(64) NOT NULL UNIQUE,
  employee_id         VARCHAR2(50) NOT NULL,
  role_code           VARCHAR2(20) NOT NULL,
  full_name           VARCHAR2(150) NOT NULL,
  expires_at          DATE NOT NULL,
  created_at          DATE DEFAULT SYSDATE NOT NULL,
  last_seen_at        DATE
);
CREATE INDEX ix_dsb_user_session_emp ON dsb_user_session (employee_id);
CREATE INDEX ix_dsb_user_session_exp ON dsb_user_session (expires_at);

CREATE TABLE dsb_vendor_store_mapping_master (
  mapping_id          NUMBER PRIMARY KEY,
  vendor_id           NUMBER NOT NULL,
  vendor_store_code   VARCHAR2(50) NOT NULL,
  bank_store_code     VARCHAR2(30) NOT NULL,
  customer_id         VARCHAR2(50),
  customer_name       VARCHAR2(150),
  account_no          VARCHAR2(30),
  status              VARCHAR2(10) NOT NULL,
  effective_from      DATE NOT NULL,
  effective_to        DATE,
  created_by          VARCHAR2(50) NOT NULL,
  created_date        DATE DEFAULT SYSDATE NOT NULL,
  approved_by         VARCHAR2(50),
  approved_date       DATE,
  CONSTRAINT fk_map_vendor FOREIGN KEY (vendor_id) REFERENCES dsb_vendor_master(vendor_id),
  CONSTRAINT chk_mapping_status CHECK (status IN ('ACTIVE','INACTIVE'))
);

CREATE TABLE dsb_charge_configuration_master (
  config_id           NUMBER PRIMARY KEY,
  config_code         VARCHAR2(50) NOT NULL,
  config_name         VARCHAR2(150) NOT NULL,
  value_number        NUMBER(18,4),
  value_text          VARCHAR2(200),
  value_date          DATE,
  unit_of_measure     VARCHAR2(30),
  status              VARCHAR2(10) NOT NULL,
  effective_from      DATE NOT NULL,
  effective_to        DATE,
  created_by          VARCHAR2(50) NOT NULL,
  created_date        DATE DEFAULT SYSDATE NOT NULL,
  approved_by         VARCHAR2(50),
  approved_date       DATE,
  CONSTRAINT chk_charge_config_status CHECK (status IN ('ACTIVE','INACTIVE'))
);

CREATE TABLE dsb_pickup_rules_master (
  rule_id             NUMBER PRIMARY KEY,
  pickup_type         VARCHAR2(10) NOT NULL,
  free_limit          NUMBER(10),
  status              VARCHAR2(10) NOT NULL,
  effective_from      DATE NOT NULL,
  effective_to        DATE,
  created_by          VARCHAR2(50) NOT NULL,
  created_date        DATE DEFAULT SYSDATE NOT NULL,
  approved_by         VARCHAR2(50),
  approved_date       DATE,
  CONSTRAINT chk_pickup_type CHECK (pickup_type IN ('BEAT','CALL')),
  CONSTRAINT chk_pickup_rules_status CHECK (status IN ('ACTIVE','INACTIVE'))
);

CREATE TABLE dsb_vendor_charge_master (
  vendor_charge_id    NUMBER PRIMARY KEY,
  vendor_id           NUMBER NOT NULL,
  pickup_type         VARCHAR2(10) NOT NULL,
  base_charge         NUMBER(18,2) NOT NULL,
  status              VARCHAR2(10) NOT NULL,
  effective_from      DATE NOT NULL,
  effective_to        DATE,
  created_by          VARCHAR2(50) NOT NULL,
  created_date        DATE DEFAULT SYSDATE NOT NULL,
  approved_by         VARCHAR2(50),
  approved_date       DATE,
  CONSTRAINT fk_vendor_charge_vendor FOREIGN KEY (vendor_id) REFERENCES dsb_vendor_master(vendor_id),
  CONSTRAINT chk_vendor_charge_type CHECK (pickup_type IN ('BEAT','CALL')),
  CONSTRAINT chk_vendor_charge_status CHECK (status IN ('ACTIVE','INACTIVE'))
);

CREATE TABLE dsb_vendor_beat_slabs (
  slab_id           NUMBER PRIMARY KEY,
  vendor_id         NUMBER NOT NULL,
  amount_from       NUMBER(18,2) NOT NULL,
  amount_to         NUMBER(18,2) NOT NULL,
  charge_amount     NUMBER(18,2) NOT NULL,
  slab_label        VARCHAR2(100),
  status            VARCHAR2(10) NOT NULL,
  effective_from    DATE NOT NULL,
  effective_to      DATE,
  created_by        VARCHAR2(50) NOT NULL,
  created_date      DATE DEFAULT SYSDATE NOT NULL,
  approved_by       VARCHAR2(50),
  approved_date     DATE,
  CONSTRAINT fk_vendor_beat_slab_vendor FOREIGN KEY (vendor_id) REFERENCES dsb_vendor_master(vendor_id),
  CONSTRAINT chk_vendor_beat_slab_status CHECK (status IN ('ACTIVE','INACTIVE'))
);

CREATE TABLE dsb_customer_charge_slabs (
  slab_id            NUMBER PRIMARY KEY,
  store_id           NUMBER NOT NULL,
  amount_from        NUMBER(18,2) NOT NULL,
  amount_to          NUMBER(18,2) NOT NULL,
  charge_amount      NUMBER(18,2) NOT NULL,
  slab_label         VARCHAR2(100),
  status             VARCHAR2(10) NOT NULL,
  effective_from     DATE NOT NULL,
  effective_to       DATE,
  created_by         VARCHAR2(50) NOT NULL,
  created_date       DATE DEFAULT SYSDATE NOT NULL,
  approved_by        VARCHAR2(50),
  approved_date      DATE,
  CONSTRAINT fk_customer_slab_store FOREIGN KEY (store_id) REFERENCES dsb_bank_store_master(store_id),
  CONSTRAINT chk_customer_slab_status CHECK (status IN ('ACTIVE','INACTIVE'))
);

CREATE TABLE dsb_waiver_master (
  waiver_id           NUMBER PRIMARY KEY,
  customer_id         VARCHAR2(50) NOT NULL,
  waiver_type         VARCHAR2(20) NOT NULL,
  waiver_percentage   NUMBER(5,2),
  waiver_cap_amount   NUMBER(18,2),
  waiver_from         DATE NOT NULL,
  waiver_to           DATE,
  status              VARCHAR2(10) NOT NULL,
  created_by          VARCHAR2(50) NOT NULL,
  created_date        DATE DEFAULT SYSDATE NOT NULL,
  approved_by         VARCHAR2(50),
  approved_date       DATE,
  CONSTRAINT chk_waiver_type CHECK (waiver_type IN ('PERCENT','CAP','BOTH')),
  CONSTRAINT chk_waiver_status CHECK (status IN ('ACTIVE','INACTIVE'))
);

-- =========================
-- Charge Summaries
-- =========================
CREATE TABLE dsb_vendor_charge_summary (
  summary_id          NUMBER PRIMARY KEY,
  vendor_id           NUMBER NOT NULL,
  month_key           VARCHAR2(6) NOT NULL,
  beat_pickups        NUMBER(10) DEFAULT 0,
  call_pickups        NUMBER(10) DEFAULT 0,
  base_charge_amount  NUMBER(18,2) DEFAULT 0,
  enhancement_charge  NUMBER(18,2) DEFAULT 0,
  tax_amount          NUMBER(18,2) DEFAULT 0,
  total_charge_amount NUMBER(18,2) DEFAULT 0,
  total_with_tax      NUMBER(18,2) DEFAULT 0,
  status              VARCHAR2(20) NOT NULL,
  computed_by         VARCHAR2(50) NOT NULL,
  computed_at         DATE DEFAULT SYSDATE NOT NULL,
  CONSTRAINT fk_vendor_charge_summary_vendor FOREIGN KEY (vendor_id) REFERENCES dsb_vendor_master(vendor_id),
  CONSTRAINT uq_vendor_charge_summary UNIQUE (vendor_id, month_key)
);

CREATE TABLE dsb_customer_charge_summary (
  summary_id          NUMBER PRIMARY KEY,
  store_id            NUMBER NOT NULL,
  customer_id         VARCHAR2(50),
  month_key           VARCHAR2(6) NOT NULL,
  charge_period_from  DATE,
  charge_period_to    DATE,
  total_remittance    NUMBER(18,2) DEFAULT 0,
  base_charge_amount  NUMBER(18,2) DEFAULT 0,
  enhancement_charge  NUMBER(18,2) DEFAULT 0,
  days_over_limit     NUMBER(10) DEFAULT 0,
  waiver_amount       NUMBER(18,2) DEFAULT 0,
  store_waiver_applied NUMBER(18,2) DEFAULT 0,
  net_charge_amount   NUMBER(18,2) DEFAULT 0,
  tax_amount          NUMBER(18,2) DEFAULT 0,
  total_with_tax      NUMBER(18,2) DEFAULT 0,
  status              VARCHAR2(20) NOT NULL,
  computed_by         VARCHAR2(50) NOT NULL,
  computed_at         DATE DEFAULT SYSDATE NOT NULL,
  CONSTRAINT fk_cust_charge_summary_store FOREIGN KEY (store_id) REFERENCES dsb_bank_store_master(store_id),
  CONSTRAINT uq_customer_charge_summary UNIQUE (store_id, month_key)
);

CREATE TABLE dsb_vendor_file_format_config (
  format_id           NUMBER PRIMARY KEY,
  vendor_id           NUMBER NOT NULL,
  format_name         VARCHAR2(100) NOT NULL,
  status              VARCHAR2(10) NOT NULL,
  effective_from      DATE NOT NULL,
  effective_to        DATE,
  created_by          VARCHAR2(50) NOT NULL,
  created_date        DATE DEFAULT SYSDATE NOT NULL,
  approved_by         VARCHAR2(50),
  approved_date       DATE,
  CONSTRAINT fk_format_vendor FOREIGN KEY (vendor_id) REFERENCES dsb_vendor_master(vendor_id),
  CONSTRAINT chk_format_status CHECK (status IN ('ACTIVE','INACTIVE'))
);

CREATE TABLE dsb_vendor_file_format_header_mapping (
  format_id     NUMBER NOT NULL,
  mapping_key   VARCHAR2(100) NOT NULL,
  source_column VARCHAR2(255) NOT NULL,
  CONSTRAINT pk_vendor_format_header_mapping PRIMARY KEY (format_id, mapping_key),
  CONSTRAINT fk_header_mapping_format FOREIGN KEY (format_id) REFERENCES dsb_vendor_file_format_config(format_id) ON DELETE CASCADE
);

-- Finacle file column mapping (admin-configurable, system-wide)
CREATE TABLE dsb_finacle_header_mapping (
  mapping_key   VARCHAR2(100) PRIMARY KEY,
  source_column VARCHAR2(255) NOT NULL
);

-- =========================
-- Upload Batches & Raw Staging
-- =========================
CREATE TABLE dsb_finacle_upload_batch (
  batch_id            NUMBER PRIMARY KEY,
  mis_date            DATE NOT NULL,
  file_name           VARCHAR2(255) NOT NULL,
  uploaded_by         VARCHAR2(50) NOT NULL,
  uploaded_at         DATE DEFAULT SYSDATE NOT NULL,
  status              VARCHAR2(20) NOT NULL,
  CONSTRAINT uq_finacle_batch_date UNIQUE (mis_date),
  CONSTRAINT chk_finacle_batch_status CHECK (status IN ('RECEIVED','PROCESSED','FAILED'))
);

CREATE TABLE dsb_vendor_upload_batch (
  batch_id            NUMBER PRIMARY KEY,
  vendor_id           NUMBER NOT NULL,
  mis_date            DATE NOT NULL,
  file_name           VARCHAR2(255) NOT NULL,
  uploaded_by         VARCHAR2(50) NOT NULL,
  uploaded_at         DATE DEFAULT SYSDATE NOT NULL,
  status              VARCHAR2(20) NOT NULL,
  CONSTRAINT fk_vendor_batch_vendor FOREIGN KEY (vendor_id) REFERENCES dsb_vendor_master(vendor_id),
  CONSTRAINT uq_vendor_batch UNIQUE (vendor_id, mis_date),
  CONSTRAINT chk_vendor_batch_status CHECK (status IN ('RECEIVED','PROCESSED','FAILED'))
);

CREATE TABLE dsb_finacle_raw_staging (
  raw_id              NUMBER PRIMARY KEY,
  batch_id            NUMBER NOT NULL,
  row_number          NUMBER NOT NULL,
  row_payload         VARCHAR2(4000) NOT NULL,
  created_date        DATE DEFAULT SYSDATE NOT NULL,
  CONSTRAINT fk_finacle_raw_batch FOREIGN KEY (batch_id) REFERENCES dsb_finacle_upload_batch(batch_id)
);

CREATE TABLE dsb_finacle_invalid_records (
  invalid_id          NUMBER PRIMARY KEY,
  batch_id            NUMBER NOT NULL,
  row_number          NUMBER NOT NULL,
  reason              VARCHAR2(255) NOT NULL,
  row_payload         VARCHAR2(4000) NOT NULL,
  created_date        DATE DEFAULT SYSDATE NOT NULL,
  CONSTRAINT fk_finacle_invalid_batch FOREIGN KEY (batch_id) REFERENCES dsb_finacle_upload_batch(batch_id)
);

CREATE TABLE dsb_vendor_raw_staging (
  raw_id              NUMBER PRIMARY KEY,
  batch_id            NUMBER NOT NULL,
  row_number          NUMBER NOT NULL,
  row_payload         VARCHAR2(4000) NOT NULL,
  created_date        DATE DEFAULT SYSDATE NOT NULL,
  CONSTRAINT fk_vendor_raw_batch FOREIGN KEY (batch_id) REFERENCES dsb_vendor_upload_batch(batch_id)
);

CREATE TABLE dsb_vendor_invalid_records (
  invalid_id          NUMBER PRIMARY KEY,
  batch_id            NUMBER NOT NULL,
  row_number          NUMBER NOT NULL,
  reason              VARCHAR2(255) NOT NULL,
  row_payload         VARCHAR2(4000) NOT NULL,
  created_date        DATE DEFAULT SYSDATE NOT NULL,
  CONSTRAINT fk_vendor_invalid_batch FOREIGN KEY (batch_id) REFERENCES dsb_vendor_upload_batch(batch_id)
);

-- =========================
-- Canonical Data Model
-- =========================
CREATE TABLE dsb_canonical_transactions (
  canonical_id        NUMBER PRIMARY KEY,
  source              VARCHAR2(10) NOT NULL,
  bank_store_code     VARCHAR2(30) NOT NULL,
  vendor_store_code   VARCHAR2(50),
  account_no          VARCHAR2(30),
  customer_id         VARCHAR2(50),
  pickup_date         DATE,
  remittance_date     DATE,
  pickup_amount       NUMBER(18,2),
  remittance_amount   NUMBER(18,2),
  pickup_type         VARCHAR2(10),
  raw_batch_id        NUMBER NOT NULL,
  created_date        DATE DEFAULT SYSDATE NOT NULL,
  CONSTRAINT chk_canonical_source CHECK (source IN ('FINACLE','VENDOR')),
  CONSTRAINT chk_canonical_pickup_type CHECK (pickup_type IN ('BEAT','CALL'))
);

-- =========================
-- Remittance Entries
-- =========================
CREATE TABLE dsb_remittance_entries (
  remittance_id       NUMBER PRIMARY KEY,
  canonical_id        NUMBER NOT NULL,
  source              VARCHAR2(10) NOT NULL,
  status              VARCHAR2(20) NOT NULL,
  rejection_reason    VARCHAR2(255),
  created_by          VARCHAR2(50) NOT NULL,
  created_date        DATE DEFAULT SYSDATE NOT NULL,
  approved_by         VARCHAR2(50),
  approved_date       DATE,
  closed_date         DATE,
  CONSTRAINT fk_remittance_canonical FOREIGN KEY (canonical_id) REFERENCES dsb_canonical_transactions(canonical_id),
  CONSTRAINT chk_remittance_status CHECK (
    status IN ('UPLOADED','VALIDATED','APPROVED','REJECTED','CLOSED')
  )
);

-- =========================
-- Reconciliation Results
-- =========================
CREATE TABLE dsb_reconciliation_results (
  recon_id            NUMBER PRIMARY KEY,
  finacle_canonical_id NUMBER,
  vendor_canonical_id  NUMBER,
  bank_store_code     VARCHAR2(30) NOT NULL,
  mis_date            DATE,
  pickup_date         DATE,
  remittance_date     DATE,
  pickup_amount       NUMBER(18,2),
  remittance_amount   NUMBER(18,2),
  status              VARCHAR2(20) NOT NULL,
  reason              VARCHAR2(255),
  is_final            NUMBER(1) DEFAULT 0,
  created_date        DATE DEFAULT SYSDATE NOT NULL,
  CONSTRAINT chk_recon_status CHECK (
    status IN ('MATCHED','AMOUNT_MISMATCH','DATE_MISMATCH','MISSING_FINACLE','MISSING_VENDOR')
  )
);

-- =========================
-- Exception Records
-- =========================
CREATE TABLE dsb_exception_records (
  exception_id        NUMBER PRIMARY KEY,
  recon_id            NUMBER,
  exception_type      VARCHAR2(50) NOT NULL,
  status              VARCHAR2(20) NOT NULL,
  details             VARCHAR2(255),
  remarks             VARCHAR2(255),
  created_by          VARCHAR2(50) NOT NULL,
  created_date        DATE DEFAULT SYSDATE NOT NULL,
  resolved_by         VARCHAR2(50),
  resolved_date       DATE,
  CONSTRAINT fk_exception_recon FOREIGN KEY (recon_id) REFERENCES dsb_reconciliation_results(recon_id),
  CONSTRAINT chk_exception_status CHECK (status IN ('OPEN','RESOLVED','ESCALATED'))
);

-- =========================
-- Maker-Checker Approvals
-- =========================
CREATE TABLE dsb_approval_requests (
  approval_id         NUMBER PRIMARY KEY,
  entity_type         VARCHAR2(50) NOT NULL,
  entity_id           NUMBER,
  original_data       VARCHAR2(4000) NOT NULL,
  proposed_data       VARCHAR2(4000) NOT NULL,
  reason              VARCHAR2(255),
  maker_id            VARCHAR2(50) NOT NULL,
  checker_id          VARCHAR2(50),
  checker_comment     VARCHAR2(255),
  comments_history    VARCHAR2(4000),
  status              VARCHAR2(20) NOT NULL,
  created_date        DATE DEFAULT SYSDATE NOT NULL,
  approved_date       DATE,
  CONSTRAINT chk_approval_status CHECK (status IN ('PENDING','APPROVED','REJECTED','CLARIFICATION'))
);

-- =========================
-- Reconciliation Corrections
-- =========================
CREATE TABLE dsb_reconciliation_corrections (
  correction_id       NUMBER PRIMARY KEY,
  recon_id            NUMBER NOT NULL,
  approval_id         NUMBER NOT NULL,
  proposed_data       VARCHAR2(4000) NOT NULL,
  status              VARCHAR2(20) NOT NULL,
  maker_id            VARCHAR2(50) NOT NULL,
  checker_id         VARCHAR2(50),
  created_date        DATE DEFAULT SYSDATE NOT NULL,
  approved_date       DATE,
  CONSTRAINT fk_corr_recon FOREIGN KEY (recon_id) REFERENCES dsb_reconciliation_results(recon_id),
  CONSTRAINT fk_corr_approval FOREIGN KEY (approval_id) REFERENCES dsb_approval_requests(approval_id),
  CONSTRAINT chk_corr_status CHECK (status IN ('PENDING','APPROVED','REJECTED'))
);

-- =========================
-- API / Application Error Logs (non-deletable)
-- =========================
CREATE TABLE dsb_api_log (
  log_id        NUMBER PRIMARY KEY,
  method        VARCHAR2(10),
  path          VARCHAR2(500),
  status_code   NUMBER,
  log_level     VARCHAR2(20) DEFAULT 'ERROR',
  message       VARCHAR2(4000),
  detail        VARCHAR2(4000),
  user_id       VARCHAR2(50),
  created_at    DATE DEFAULT SYSDATE NOT NULL,
  CONSTRAINT chk_api_log_level CHECK (log_level IN ('ERROR','WARNING','INFO'))
);

-- =========================
-- Vendor Absence Tracking
-- =========================
CREATE TABLE dsb_vendor_absence_records (
  absence_id        NUMBER PRIMARY KEY,
  vendor_id         NUMBER NOT NULL,
  bank_store_code   VARCHAR2(30) NOT NULL,
  vendor_store_code VARCHAR2(50),
  store_name        VARCHAR2(150),
  absence_date      DATE NOT NULL,
  recorded_at       DATE DEFAULT SYSDATE NOT NULL,
  recorded_by       VARCHAR2(50),
  CONSTRAINT fk_vendor_absence_vendor FOREIGN KEY (vendor_id) REFERENCES dsb_vendor_master(vendor_id)
);
CREATE INDEX idx_vendor_absence_date ON dsb_vendor_absence_records(absence_date);
CREATE INDEX idx_vendor_absence_vendor ON dsb_vendor_absence_records(vendor_id);
CREATE INDEX idx_vendor_absence_store ON dsb_vendor_absence_records(bank_store_code);

-- =========================
-- Audit Logs
-- =========================
CREATE TABLE dsb_audit_log (
  audit_id            NUMBER PRIMARY KEY,
  entity_type         VARCHAR2(50) NOT NULL,
  entity_id           NUMBER,
  action              VARCHAR2(50) NOT NULL,
  old_data            VARCHAR2(4000),
  new_data            VARCHAR2(4000),
  changed_by          VARCHAR2(50) NOT NULL,
  changed_at          DATE DEFAULT SYSDATE NOT NULL
);

-- =========================
-- Month End Lock
-- =========================
CREATE TABLE dsb_month_lock (
  lock_id             NUMBER PRIMARY KEY,
  month_key           VARCHAR2(6) NOT NULL UNIQUE,
  status              VARCHAR2(10) NOT NULL,
  locked_by           VARCHAR2(50),
  locked_at           DATE,
  CONSTRAINT chk_month_lock_status CHECK (status IN ('OPEN','LOCKED'))
);

-- =============================================================================
-- Optional Seed Data (uncomment as needed)
-- =============================================================================

-- Charge Configuration (required for charge engine)
/*
INSERT INTO dsb_charge_configuration_master (config_id, config_code, config_name, value_number, value_text, status, effective_from, created_by)
VALUES (seq_dsb_charge_config_master.nextval, 'ENHANCEMENT_THRESHOLD_AMOUNT', 'Enhancement threshold', 50000, NULL, 'ACTIVE', SYSDATE, 'SYSTEM');
INSERT INTO dsb_charge_configuration_master (config_id, config_code, config_name, value_number, value_text, status, effective_from, created_by)
VALUES (seq_dsb_charge_config_master.nextval, 'ENHANCEMENT_CHARGE_AMOUNT', 'Enhancement charge', 60, NULL, 'ACTIVE', SYSDATE, 'SYSTEM');
INSERT INTO dsb_charge_configuration_master (config_id, config_code, config_name, value_number, value_text, status, effective_from, created_by)
VALUES (seq_dsb_charge_config_master.nextval, 'GST_ENABLED', 'GST enabled', NULL, 'Y', 'ACTIVE', SYSDATE, 'SYSTEM');
INSERT INTO dsb_charge_configuration_master (config_id, config_code, config_name, value_number, value_text, status, effective_from, created_by)
VALUES (seq_dsb_charge_config_master.nextval, 'GST_RATE_PERCENT', 'GST percent', 18, NULL, 'ACTIVE', SYSDATE, 'SYSTEM');
INSERT INTO dsb_charge_configuration_master (config_id, config_code, config_name, value_number, value_text, status, effective_from, created_by)
VALUES (seq_dsb_charge_config_master.nextval, 'CUSTOMER_CHARGE_RATE_PERCENT', 'Customer charge rate', 0.5, NULL, 'ACTIVE', SYSDATE, 'SYSTEM');
*/

-- User Accounts (replace YOUR_EMPLOYEE_ID and Your Full Name for AD login)
/*
INSERT INTO dsb_user_account (user_id, employee_id, full_name, role_code, password_hash, status, created_date)
VALUES (seq_dsb_user_account.nextval, 'YOUR_EMPLOYEE_ID', 'Your Full Name', 'ADMIN', 'AD', 'ACTIVE', SYSDATE);
*/

-- Dummy users for local dev (AD_SKIP=true)
/*
INSERT INTO dsb_user_account (user_id, employee_id, full_name, role_code, password_hash, status, created_date)
VALUES (seq_dsb_user_account.nextval, 'FED001', 'Maker User', 'MAKER', 'AD', 'ACTIVE', SYSDATE);
INSERT INTO dsb_user_account (user_id, employee_id, full_name, role_code, password_hash, status, created_date)
VALUES (seq_dsb_user_account.nextval, 'FED002', 'Checker User', 'CHECKER', 'AD', 'ACTIVE', SYSDATE);
INSERT INTO dsb_user_account (user_id, employee_id, full_name, role_code, password_hash, status, created_date)
VALUES (seq_dsb_user_account.nextval, 'FED003', 'Admin User', 'ADMIN', 'AD', 'ACTIVE', SYSDATE);
*/

-- Customer Charge Slabs (replace 1 with store_id from dsb_bank_store_master)
/*
INSERT INTO dsb_customer_charge_slabs (slab_id, store_id, amount_from, amount_to, charge_amount, slab_label, status, effective_from, created_by)
SELECT seq_dsb_customer_charge_slab.nextval, 1, 0, 50000, 4000, 'Upto 50K', 'ACTIVE', SYSDATE, 'SYSTEM' FROM dual
UNION ALL SELECT seq_dsb_customer_charge_slab.nextval, 1, 50001, 100000, 4500, 'Above 50K to 1L', 'ACTIVE', SYSDATE, 'SYSTEM' FROM dual
UNION ALL SELECT seq_dsb_customer_charge_slab.nextval, 1, 100001, 200000, 5750, 'Above 1L to 2L', 'ACTIVE', SYSDATE, 'SYSTEM' FROM dual
UNION ALL SELECT seq_dsb_customer_charge_slab.nextval, 1, 200001, 400000, 8750, 'Above 2L to 4L', 'ACTIVE', SYSDATE, 'SYSTEM' FROM dual
UNION ALL SELECT seq_dsb_customer_charge_slab.nextval, 1, 400001, 600000, 12000, 'Above 4L to 6L', 'ACTIVE', SYSDATE, 'SYSTEM' FROM dual
UNION ALL SELECT seq_dsb_customer_charge_slab.nextval, 1, 600001, 800000, 16000, 'Above 6L to 8L', 'ACTIVE', SYSDATE, 'SYSTEM' FROM dual
UNION ALL SELECT seq_dsb_customer_charge_slab.nextval, 1, 800001, 1000000, 18500, 'Above 8L to 10L', 'ACTIVE', SYSDATE, 'SYSTEM' FROM dual
UNION ALL SELECT seq_dsb_customer_charge_slab.nextval, 1, 1000001, 1500000, 26000, 'Above 10L to 15L', 'ACTIVE', SYSDATE, 'SYSTEM' FROM dual
UNION ALL SELECT seq_dsb_customer_charge_slab.nextval, 1, 1500001, 2000000, 33000, 'Above 15L to 20L', 'ACTIVE', SYSDATE, 'SYSTEM' FROM dual
UNION ALL SELECT seq_dsb_customer_charge_slab.nextval, 1, 2000001, 5000000, 42000, 'Above 20L to 50L', 'ACTIVE', SYSDATE, 'SYSTEM' FROM dual
UNION ALL SELECT seq_dsb_customer_charge_slab.nextval, 1, 5000001, 10000000, 58500, 'Above 50L to 1 Cr', 'ACTIVE', SYSDATE, 'SYSTEM' FROM dual;
*/

COMMIT;
