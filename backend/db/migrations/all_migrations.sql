-- =============================================================================
-- Doorstep Banking – combined incremental migrations (Oracle)
-- =============================================================================
-- Use this file to upgrade an EXISTING database that was created from an older
-- baseline. Skip any section that already applies (Oracle will error on
-- duplicate object / column).
--
-- For a NEW empty schema, run ../schema.sql instead (includes these objects).
--
-- Suggested order reflects typical evolution. Sections:
--   1.  CLOB → VARCHAR2 (legacy only; skip if row_payload is already VARCHAR2)
--   2.  Finacle header mapping table
--   3.  API log table + sequence
--   4.  Store pickup_type column (skip if bank_store_master.pickup_type exists)
--   5.  Remove BOTH from pickup_type constraint
--   6.  Customer slabs: vendor_id → store_id (destructive; see script)
--   7.  Vendor absence records
--   8.  Vendor beat slabs
--   9.  Optional sample customer slabs (data)
--   10. Store waiver percentage / cap amount / cap period
--   11. Customer charge summary: days_over_limit
--   12. Charge config: drop UQ on config_code (rename-aware, idempotent)
--   13. Customer charge summary: charge_period_from / charge_period_to
--   14. Bank store master: onboarded_date / last_modified_date
--   15. Customer charge summary: re-grain by store_id + month_key
--   16. Customer charge summary: store_waiver_applied
--   17. Bank store master: vendor_charge (Beat monthly)
--   18. Bank store master: per-store CALL pricing (rename-aware, idempotent)
--   19. RENAME every table and sequence to dsb_* / seq_dsb_* (rename-aware, idempotent)
-- =============================================================================

-- =============================================================================
-- 1. CLOB → VARCHAR2 (Windows / legacy)
-- =============================================================================
-- finacle_raw_staging
ALTER TABLE finacle_raw_staging ADD row_payload_new VARCHAR2(4000);
UPDATE finacle_raw_staging SET row_payload_new = DBMS_LOB.SUBSTR(row_payload, 4000, 1);
ALTER TABLE finacle_raw_staging DROP COLUMN row_payload;
ALTER TABLE finacle_raw_staging RENAME COLUMN row_payload_new TO row_payload;
ALTER TABLE finacle_raw_staging MODIFY row_payload NOT NULL;

-- finacle_invalid_records
ALTER TABLE finacle_invalid_records ADD row_payload_new VARCHAR2(4000);
UPDATE finacle_invalid_records SET row_payload_new = DBMS_LOB.SUBSTR(row_payload, 4000, 1);
ALTER TABLE finacle_invalid_records DROP COLUMN row_payload;
ALTER TABLE finacle_invalid_records RENAME COLUMN row_payload_new TO row_payload;
ALTER TABLE finacle_invalid_records MODIFY row_payload NOT NULL;

-- vendor_raw_staging
ALTER TABLE vendor_raw_staging ADD row_payload_new VARCHAR2(4000);
UPDATE vendor_raw_staging SET row_payload_new = DBMS_LOB.SUBSTR(row_payload, 4000, 1);
ALTER TABLE vendor_raw_staging DROP COLUMN row_payload;
ALTER TABLE vendor_raw_staging RENAME COLUMN row_payload_new TO row_payload;
ALTER TABLE vendor_raw_staging MODIFY row_payload NOT NULL;

-- vendor_invalid_records
ALTER TABLE vendor_invalid_records ADD row_payload_new VARCHAR2(4000);
UPDATE vendor_invalid_records SET row_payload_new = DBMS_LOB.SUBSTR(row_payload, 4000, 1);
ALTER TABLE vendor_invalid_records DROP COLUMN row_payload;
ALTER TABLE vendor_invalid_records RENAME COLUMN row_payload_new TO row_payload;
ALTER TABLE vendor_invalid_records MODIFY row_payload NOT NULL;

-- approval_requests
ALTER TABLE approval_requests ADD original_data_new VARCHAR2(4000);
ALTER TABLE approval_requests ADD proposed_data_new VARCHAR2(4000);
ALTER TABLE approval_requests ADD comments_history_new VARCHAR2(4000);
UPDATE approval_requests SET original_data_new = DBMS_LOB.SUBSTR(original_data, 4000, 1);
UPDATE approval_requests SET proposed_data_new = DBMS_LOB.SUBSTR(proposed_data, 4000, 1);
UPDATE approval_requests SET comments_history_new = DBMS_LOB.SUBSTR(comments_history, 4000, 1) WHERE comments_history IS NOT NULL;
ALTER TABLE approval_requests DROP COLUMN original_data;
ALTER TABLE approval_requests DROP COLUMN proposed_data;
ALTER TABLE approval_requests DROP COLUMN comments_history;
ALTER TABLE approval_requests RENAME COLUMN original_data_new TO original_data;
ALTER TABLE approval_requests RENAME COLUMN proposed_data_new TO proposed_data;
ALTER TABLE approval_requests RENAME COLUMN comments_history_new TO comments_history;
ALTER TABLE approval_requests MODIFY original_data NOT NULL;
ALTER TABLE approval_requests MODIFY proposed_data NOT NULL;

-- reconciliation_corrections
ALTER TABLE reconciliation_corrections ADD proposed_data_new VARCHAR2(4000);
UPDATE reconciliation_corrections SET proposed_data_new = DBMS_LOB.SUBSTR(proposed_data, 4000, 1);
ALTER TABLE reconciliation_corrections DROP COLUMN proposed_data;
ALTER TABLE reconciliation_corrections RENAME COLUMN proposed_data_new TO proposed_data;
ALTER TABLE reconciliation_corrections MODIFY proposed_data NOT NULL;

-- audit_log
ALTER TABLE audit_log ADD old_data_new VARCHAR2(4000);
ALTER TABLE audit_log ADD new_data_new VARCHAR2(4000);
UPDATE audit_log SET old_data_new = DBMS_LOB.SUBSTR(old_data, 4000, 1) WHERE old_data IS NOT NULL;
UPDATE audit_log SET new_data_new = DBMS_LOB.SUBSTR(new_data, 4000, 1) WHERE new_data IS NOT NULL;
ALTER TABLE audit_log DROP COLUMN old_data;
ALTER TABLE audit_log DROP COLUMN new_data;
ALTER TABLE audit_log RENAME COLUMN old_data_new TO old_data;
ALTER TABLE audit_log RENAME COLUMN new_data_new TO new_data;

COMMIT;

-- =============================================================================
-- 2. Finacle header mapping
-- =============================================================================
CREATE TABLE finacle_header_mapping (
  mapping_key   VARCHAR2(100) PRIMARY KEY,
  source_column VARCHAR2(255) NOT NULL
);

-- =============================================================================
-- 3. API log
-- =============================================================================
CREATE SEQUENCE seq_api_log START WITH 1 INCREMENT BY 1 NOCACHE;

CREATE TABLE api_log (
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

-- =============================================================================
-- 4. bank_store_master pickup_type
-- =============================================================================
ALTER TABLE bank_store_master ADD pickup_type VARCHAR2(10) DEFAULT 'BEAT';
ALTER TABLE bank_store_master ADD CONSTRAINT chk_store_pickup_type CHECK (pickup_type IN ('BEAT','CALL'));

-- =============================================================================
-- 5. Remove BOTH from pickup_type
-- =============================================================================
UPDATE bank_store_master SET pickup_type = 'BEAT' WHERE pickup_type = 'BOTH';
COMMIT;

ALTER TABLE bank_store_master DROP CONSTRAINT chk_store_pickup_type;
ALTER TABLE bank_store_master ADD CONSTRAINT chk_store_pickup_type CHECK (pickup_type IN ('BEAT','CALL'));

-- =============================================================================
-- 6. Customer charge slabs: vendor → store
-- =============================================================================
ALTER TABLE customer_charge_slabs ADD store_id NUMBER;

UPDATE customer_charge_slabs c
SET c.store_id = (
  SELECT MIN(b.store_id)
  FROM vendor_store_mapping_master v
  JOIN bank_store_master b ON b.bank_store_code = v.bank_store_code AND b.status = 'ACTIVE'
  WHERE v.vendor_id = c.vendor_id AND v.status = 'ACTIVE'
)
WHERE c.vendor_id IS NOT NULL;

DELETE FROM customer_charge_slabs WHERE store_id IS NULL;

ALTER TABLE customer_charge_slabs DROP CONSTRAINT fk_customer_slab_vendor;
ALTER TABLE customer_charge_slabs DROP COLUMN vendor_id;

ALTER TABLE customer_charge_slabs MODIFY store_id NOT NULL;
ALTER TABLE customer_charge_slabs ADD CONSTRAINT fk_customer_slab_store FOREIGN KEY (store_id) REFERENCES bank_store_master(store_id);

-- =============================================================================
-- 7. Vendor absence records
-- =============================================================================
CREATE SEQUENCE seq_vendor_absence_record START WITH 1 INCREMENT BY 1 NOCACHE;

CREATE TABLE vendor_absence_records (
  absence_id        NUMBER PRIMARY KEY,
  vendor_id         NUMBER NOT NULL,
  bank_store_code   VARCHAR2(30) NOT NULL,
  vendor_store_code VARCHAR2(50),
  store_name        VARCHAR2(150),
  absence_date      DATE NOT NULL,
  recorded_at       DATE DEFAULT SYSDATE NOT NULL,
  recorded_by       VARCHAR2(50),
  CONSTRAINT fk_vendor_absence_vendor FOREIGN KEY (vendor_id) REFERENCES vendor_master(vendor_id)
);

CREATE INDEX idx_vendor_absence_date ON vendor_absence_records(absence_date);
CREATE INDEX idx_vendor_absence_vendor ON vendor_absence_records(vendor_id);
CREATE INDEX idx_vendor_absence_store ON vendor_absence_records(bank_store_code);

-- =============================================================================
-- 8. Vendor beat slabs
-- =============================================================================
CREATE SEQUENCE seq_vendor_beat_slab START WITH 1 INCREMENT BY 1 NOCACHE;

CREATE TABLE vendor_beat_slabs (
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
  CONSTRAINT fk_vendor_beat_slab_vendor FOREIGN KEY (vendor_id) REFERENCES vendor_master(vendor_id),
  CONSTRAINT chk_vendor_beat_slab_status CHECK (status IN ('ACTIVE','INACTIVE'))
);

-- =============================================================================
-- 9. Optional sample customer slabs (stores 001–005)
-- =============================================================================
INSERT INTO customer_charge_slabs (slab_id, store_id, amount_from, amount_to, charge_amount, slab_label, status, effective_from, created_by)
SELECT seq_customer_charge_slab.nextval, s.store_id, 0, 50000, 4000, 'Upto 50K', 'ACTIVE', DATE '2025-01-01', 'SYSTEM'
FROM bank_store_master s
WHERE s.bank_store_code IN ('001','002','003','004','005') AND s.status = 'ACTIVE'
  AND NOT EXISTS (SELECT 1 FROM customer_charge_slabs c WHERE c.store_id = s.store_id AND c.status = 'ACTIVE');
COMMIT;

-- =============================================================================
-- 10. Store waiver % (customer charge)
-- =============================================================================
ALTER TABLE bank_store_master ADD waiver_percentage NUMBER(5, 2);

-- Per-store monthly waiver cap (₹) for customer charges
ALTER TABLE bank_store_master ADD waiver_cap_amount NUMBER(18, 2);

-- Optional validity for store waiver cap
ALTER TABLE bank_store_master ADD waiver_cap_from DATE;
ALTER TABLE bank_store_master ADD waiver_cap_to DATE;

-- =============================================================================
-- 11. Customer charge: days above daily limit count
-- =============================================================================
ALTER TABLE customer_charge_summary ADD days_over_limit NUMBER(10) DEFAULT 0;

-- =============================================================================
-- 12. Charge config: allow multiple rows per config_code (maker-checker versions)
--     Rename-aware: works whether the table is still CHARGE_CONFIGURATION_MASTER
--     or has been renamed to DSB_CHARGE_CONFIGURATION_MASTER.
-- =============================================================================
DECLARE
  v_table VARCHAR2(128);
  v_name  VARCHAR2(128);
  v_count NUMBER;
BEGIN
  SELECT COUNT(*) INTO v_count FROM user_tables WHERE table_name = 'DSB_CHARGE_CONFIGURATION_MASTER';
  IF v_count = 1 THEN
    v_table := 'DSB_CHARGE_CONFIGURATION_MASTER';
  ELSE
    SELECT COUNT(*) INTO v_count FROM user_tables WHERE table_name = 'CHARGE_CONFIGURATION_MASTER';
    IF v_count = 1 THEN
      v_table := 'CHARGE_CONFIGURATION_MASTER';
    ELSE
      RETURN;
    END IF;
  END IF;

  BEGIN
    SELECT uc.constraint_name INTO v_name
    FROM user_constraints uc
    JOIN user_cons_columns ucc
      ON ucc.constraint_name = uc.constraint_name AND ucc.owner = uc.owner
    WHERE uc.table_name = v_table
      AND uc.constraint_type = 'U'
      AND UPPER(ucc.column_name) = 'CONFIG_CODE'
      AND ROWNUM = 1;

    EXECUTE IMMEDIATE 'ALTER TABLE ' || v_table
                   || ' DROP CONSTRAINT ' || DBMS_ASSERT.SIMPLE_SQL_NAME(v_name);
  EXCEPTION
    WHEN NO_DATA_FOUND THEN NULL;
  END;
END;
/

-- =============================================================================
-- 13. Customer charge summary: recon window for partial-month / overwrite computes
-- =============================================================================
ALTER TABLE customer_charge_summary ADD charge_period_from DATE;
ALTER TABLE customer_charge_summary ADD charge_period_to DATE;

-- =============================================================================
-- 14. Bank store master: onboarded date + last modified
-- =============================================================================
ALTER TABLE bank_store_master ADD onboarded_date DATE;
ALTER TABLE bank_store_master ADD last_modified_date DATE;
UPDATE bank_store_master
SET last_modified_date = NVL(approved_date, created_date)
WHERE last_modified_date IS NULL;

-- =============================================================================
-- 15. Customer charge summary: per store_id + month_key (not per customer)
-- =============================================================================
ALTER TABLE customer_charge_summary ADD store_id NUMBER;
ALTER TABLE customer_charge_summary DROP CONSTRAINT uq_customer_charge_summary;
DELETE FROM customer_charge_summary;
ALTER TABLE customer_charge_summary MODIFY customer_id NULL;
ALTER TABLE customer_charge_summary MODIFY store_id NOT NULL;
ALTER TABLE customer_charge_summary ADD CONSTRAINT fk_cust_charge_summary_store
  FOREIGN KEY (store_id) REFERENCES bank_store_master(store_id);
ALTER TABLE customer_charge_summary ADD CONSTRAINT uq_customer_charge_summary UNIQUE (store_id, month_key);

-- =============================================================================
-- 16. Customer charge summary: store waiver rupees (cumulative cap consumption)
-- =============================================================================
ALTER TABLE customer_charge_summary ADD store_waiver_applied NUMBER(18,2) DEFAULT 0;

-- =============================================================================
-- 17. Bank store master: monthly vendor charge (Beat stores; replaces slab lookup)
-- =============================================================================
ALTER TABLE bank_store_master ADD vendor_charge NUMBER(18, 2);

-- =============================================================================
-- 18. Bank store master: per-store CALL pricing (replaces vendor-level CALL rate)
--     Rename-aware AND idempotent: works whether the table is still
--     BANK_STORE_MASTER or has been renamed to DSB_BANK_STORE_MASTER.
-- =============================================================================
DECLARE
  v_table  VARCHAR2(128);
  v_count  NUMBER;

  PROCEDURE add_col_if_missing(p_col IN VARCHAR2, p_ddl IN VARCHAR2) IS
  BEGIN
    SELECT COUNT(*) INTO v_count FROM user_tab_columns
      WHERE table_name = v_table AND column_name = UPPER(p_col);
    IF v_count = 0 THEN
      EXECUTE IMMEDIATE 'ALTER TABLE ' || v_table || ' ADD ' || p_ddl;
    END IF;
  END;
BEGIN
  SELECT COUNT(*) INTO v_count FROM user_tables WHERE table_name = 'DSB_BANK_STORE_MASTER';
  IF v_count = 1 THEN
    v_table := 'DSB_BANK_STORE_MASTER';
  ELSE
    SELECT COUNT(*) INTO v_count FROM user_tables WHERE table_name = 'BANK_STORE_MASTER';
    IF v_count = 1 THEN
      v_table := 'BANK_STORE_MASTER';
    ELSE
      RETURN;
    END IF;
  END IF;

  add_col_if_missing('CALL_INCLUDED_PICKUPS',           'call_included_pickups NUMBER(10)');
  add_col_if_missing('CALL_MONTHLY_BANK_CHARGE',        'call_monthly_bank_charge NUMBER(18, 2)');
  add_col_if_missing('CALL_ADDITIONAL_BANK_PER_PICKUP', 'call_additional_bank_per_pickup NUMBER(18, 2)');
  add_col_if_missing('CALL_VENDOR_PAY_PER_PICKUP',      'call_vendor_pay_per_pickup NUMBER(18, 2)');
END;
/

-- =============================================================================
-- 19. Rename every table and sequence to the dsb_ / seq_dsb_ prefix.
--     Idempotent: each rename runs only when the OLD name still exists and
--     the NEW name does not. FKs, PKs, indexes and check constraints are
--     preserved automatically by Oracle across RENAME.
-- =============================================================================
DECLARE
  v_old_exists NUMBER;
  v_new_exists NUMBER;
  TYPE t_pair  IS RECORD (old_name VARCHAR2(128), new_name VARCHAR2(128));
  TYPE t_pairs IS TABLE OF t_pair INDEX BY PLS_INTEGER;
  tables    t_pairs;
  sequences t_pairs;

  PROCEDURE rename_object(p_kind IN VARCHAR2, p_old IN VARCHAR2, p_new IN VARCHAR2) IS
  BEGIN
    IF p_kind = 'TABLE' THEN
      SELECT COUNT(*) INTO v_old_exists FROM user_tables    WHERE table_name    = UPPER(p_old);
      SELECT COUNT(*) INTO v_new_exists FROM user_tables    WHERE table_name    = UPPER(p_new);
    ELSE
      SELECT COUNT(*) INTO v_old_exists FROM user_sequences WHERE sequence_name = UPPER(p_old);
      SELECT COUNT(*) INTO v_new_exists FROM user_sequences WHERE sequence_name = UPPER(p_new);
    END IF;

    IF v_old_exists = 1 AND v_new_exists = 0 THEN
      EXECUTE IMMEDIATE 'RENAME ' || p_old || ' TO ' || p_new;
    END IF;
  END;
BEGIN
  tables( 1).old_name := 'bank_store_master';                  tables( 1).new_name := 'dsb_bank_store_master';
  tables( 2).old_name := 'vendor_master';                      tables( 2).new_name := 'dsb_vendor_master';
  tables( 3).old_name := 'user_account';                       tables( 3).new_name := 'dsb_user_account';
  tables( 4).old_name := 'vendor_store_mapping_master';        tables( 4).new_name := 'dsb_vendor_store_mapping_master';
  tables( 5).old_name := 'charge_configuration_master';        tables( 5).new_name := 'dsb_charge_configuration_master';
  tables( 6).old_name := 'pickup_rules_master';                tables( 6).new_name := 'dsb_pickup_rules_master';
  tables( 7).old_name := 'vendor_charge_master';               tables( 7).new_name := 'dsb_vendor_charge_master';
  tables( 8).old_name := 'vendor_beat_slabs';                  tables( 8).new_name := 'dsb_vendor_beat_slabs';
  tables( 9).old_name := 'customer_charge_slabs';              tables( 9).new_name := 'dsb_customer_charge_slabs';
  tables(10).old_name := 'waiver_master';                      tables(10).new_name := 'dsb_waiver_master';
  tables(11).old_name := 'vendor_charge_summary';              tables(11).new_name := 'dsb_vendor_charge_summary';
  tables(12).old_name := 'customer_charge_summary';            tables(12).new_name := 'dsb_customer_charge_summary';
  tables(13).old_name := 'vendor_file_format_config';          tables(13).new_name := 'dsb_vendor_file_format_config';
  tables(14).old_name := 'vendor_file_format_header_mapping';  tables(14).new_name := 'dsb_vendor_file_format_header_mapping';
  tables(15).old_name := 'finacle_header_mapping';             tables(15).new_name := 'dsb_finacle_header_mapping';
  tables(16).old_name := 'finacle_upload_batch';               tables(16).new_name := 'dsb_finacle_upload_batch';
  tables(17).old_name := 'vendor_upload_batch';                tables(17).new_name := 'dsb_vendor_upload_batch';
  tables(18).old_name := 'finacle_raw_staging';                tables(18).new_name := 'dsb_finacle_raw_staging';
  tables(19).old_name := 'finacle_invalid_records';            tables(19).new_name := 'dsb_finacle_invalid_records';
  tables(20).old_name := 'vendor_raw_staging';                 tables(20).new_name := 'dsb_vendor_raw_staging';
  tables(21).old_name := 'vendor_invalid_records';             tables(21).new_name := 'dsb_vendor_invalid_records';
  tables(22).old_name := 'canonical_transactions';             tables(22).new_name := 'dsb_canonical_transactions';
  tables(23).old_name := 'remittance_entries';                 tables(23).new_name := 'dsb_remittance_entries';
  tables(24).old_name := 'reconciliation_results';             tables(24).new_name := 'dsb_reconciliation_results';
  tables(25).old_name := 'exception_records';                  tables(25).new_name := 'dsb_exception_records';
  tables(26).old_name := 'approval_requests';                  tables(26).new_name := 'dsb_approval_requests';
  tables(27).old_name := 'reconciliation_corrections';         tables(27).new_name := 'dsb_reconciliation_corrections';
  tables(28).old_name := 'audit_log';                          tables(28).new_name := 'dsb_audit_log';
  tables(29).old_name := 'api_log';                            tables(29).new_name := 'dsb_api_log';
  tables(30).old_name := 'vendor_absence_records';             tables(30).new_name := 'dsb_vendor_absence_records';
  tables(31).old_name := 'month_lock';                         tables(31).new_name := 'dsb_month_lock';

  FOR i IN 1 .. tables.COUNT LOOP
    rename_object('TABLE', tables(i).old_name, tables(i).new_name);
  END LOOP;

  sequences( 1).old_name := 'seq_bank_store_master';           sequences( 1).new_name := 'seq_dsb_bank_store_master';
  sequences( 2).old_name := 'seq_vendor_master';               sequences( 2).new_name := 'seq_dsb_vendor_master';
  sequences( 3).old_name := 'seq_vendor_store_mapping';        sequences( 3).new_name := 'seq_dsb_vendor_store_mapping';
  sequences( 4).old_name := 'seq_charge_config_master';        sequences( 4).new_name := 'seq_dsb_charge_config_master';
  sequences( 5).old_name := 'seq_pickup_rules_master';         sequences( 5).new_name := 'seq_dsb_pickup_rules_master';
  sequences( 6).old_name := 'seq_vendor_charge_master';        sequences( 6).new_name := 'seq_dsb_vendor_charge_master';
  sequences( 7).old_name := 'seq_vendor_beat_slab';            sequences( 7).new_name := 'seq_dsb_vendor_beat_slab';
  sequences( 8).old_name := 'seq_waiver_master';               sequences( 8).new_name := 'seq_dsb_waiver_master';
  sequences( 9).old_name := 'seq_vendor_file_format';          sequences( 9).new_name := 'seq_dsb_vendor_file_format';
  sequences(10).old_name := 'seq_finacle_upload_batch';        sequences(10).new_name := 'seq_dsb_finacle_upload_batch';
  sequences(11).old_name := 'seq_vendor_upload_batch';         sequences(11).new_name := 'seq_dsb_vendor_upload_batch';
  sequences(12).old_name := 'seq_finacle_raw_staging';         sequences(12).new_name := 'seq_dsb_finacle_raw_staging';
  sequences(13).old_name := 'seq_vendor_raw_staging';          sequences(13).new_name := 'seq_dsb_vendor_raw_staging';
  sequences(14).old_name := 'seq_canonical_txn';               sequences(14).new_name := 'seq_dsb_canonical_txn';
  sequences(15).old_name := 'seq_reconciliation_result';       sequences(15).new_name := 'seq_dsb_reconciliation_result';
  sequences(16).old_name := 'seq_reconciliation_correction';   sequences(16).new_name := 'seq_dsb_reconciliation_correction';
  sequences(17).old_name := 'seq_remittance_entry';            sequences(17).new_name := 'seq_dsb_remittance_entry';
  sequences(18).old_name := 'seq_exception_record';            sequences(18).new_name := 'seq_dsb_exception_record';
  sequences(19).old_name := 'seq_finacle_invalid_record';      sequences(19).new_name := 'seq_dsb_finacle_invalid_record';
  sequences(20).old_name := 'seq_vendor_invalid_record';       sequences(20).new_name := 'seq_dsb_vendor_invalid_record';
  sequences(21).old_name := 'seq_user_account';                sequences(21).new_name := 'seq_dsb_user_account';
  sequences(22).old_name := 'seq_approval_request';            sequences(22).new_name := 'seq_dsb_approval_request';
  sequences(23).old_name := 'seq_audit_log';                   sequences(23).new_name := 'seq_dsb_audit_log';
  sequences(24).old_name := 'seq_api_log';                     sequences(24).new_name := 'seq_dsb_api_log';
  sequences(25).old_name := 'seq_month_lock';                  sequences(25).new_name := 'seq_dsb_month_lock';
  sequences(26).old_name := 'seq_vendor_charge_summary';       sequences(26).new_name := 'seq_dsb_vendor_charge_summary';
  sequences(27).old_name := 'seq_customer_charge_summary';     sequences(27).new_name := 'seq_dsb_customer_charge_summary';
  sequences(28).old_name := 'seq_customer_charge_slab';        sequences(28).new_name := 'seq_dsb_customer_charge_slab';
  sequences(29).old_name := 'seq_vendor_absence_record';       sequences(29).new_name := 'seq_dsb_vendor_absence_record';

  FOR i IN 1 .. sequences.COUNT LOOP
    rename_object('SEQUENCE', sequences(i).old_name, sequences(i).new_name);
  END LOOP;
END;
/

-- =============================================================================
-- 19. add_user_session (H13: persistent token store for HPA-scaled deployments)
-- =============================================================================
DECLARE
  v_count NUMBER;
BEGIN
  SELECT COUNT(*) INTO v_count FROM user_sequences WHERE sequence_name = 'SEQ_DSB_USER_SESSION';
  IF v_count = 0 THEN
    EXECUTE IMMEDIATE 'CREATE SEQUENCE seq_dsb_user_session START WITH 1 INCREMENT BY 1 NOCACHE';
  END IF;
END;
/

DECLARE
  v_count NUMBER;
BEGIN
  SELECT COUNT(*) INTO v_count FROM user_tables WHERE table_name = 'DSB_USER_SESSION';
  IF v_count = 0 THEN
    EXECUTE IMMEDIATE q'[
      CREATE TABLE dsb_user_session (
        session_id          NUMBER PRIMARY KEY,
        token               VARCHAR2(64) NOT NULL UNIQUE,
        employee_id         VARCHAR2(50) NOT NULL,
        role_code           VARCHAR2(20) NOT NULL,
        full_name           VARCHAR2(150) NOT NULL,
        expires_at          DATE NOT NULL,
        created_at          DATE DEFAULT SYSDATE NOT NULL,
        last_seen_at        DATE
      )
    ]';
    EXECUTE IMMEDIATE 'CREATE INDEX ix_dsb_user_session_emp ON dsb_user_session (employee_id)';
    EXECUTE IMMEDIATE 'CREATE INDEX ix_dsb_user_session_exp ON dsb_user_session (expires_at)';
  END IF;
END;
/

-- =============================================================================
-- End of combined migrations
-- =============================================================================
