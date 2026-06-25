-- =============================================================================
-- Rename all tables and sequences to the dsb_ / seq_dsb_ prefix.
--
-- Safe to run multiple times: each rename is only attempted when the OLD
-- name still exists in the current schema AND the NEW name does not.
-- Oracle preserves primary keys, indexes, foreign-key dependencies, check
-- constraints and grants through a RENAME, so no FK rebuild is needed.
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
  -- Tables ---------------------------------------------------------------
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

  -- Sequences ------------------------------------------------------------
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
