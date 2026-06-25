-- Migration: Change CLOB columns to VARCHAR2(4000) for Windows compatibility
-- Run this on existing databases. Data longer than 4000 chars will be truncated.
-- Fresh installs use schema.sql which already has VARCHAR2.

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
