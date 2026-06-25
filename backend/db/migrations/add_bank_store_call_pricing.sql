-- Per-store CALL pricing (bank package + per-pickup + vendor pay per pickup).
-- Vendor charge for CALL no longer uses vendor_charge_master or global pickup rules for CALL.
--
-- Idempotent AND rename-aware: works whether the table is still called
-- BANK_STORE_MASTER (legacy) or DSB_BANK_STORE_MASTER (post dsb_ rename).

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
  -- Resolve the actual table name in this schema (renamed first, legacy fallback)
  SELECT COUNT(*) INTO v_count FROM user_tables WHERE table_name = 'DSB_BANK_STORE_MASTER';
  IF v_count = 1 THEN
    v_table := 'DSB_BANK_STORE_MASTER';
  ELSE
    SELECT COUNT(*) INTO v_count FROM user_tables WHERE table_name = 'BANK_STORE_MASTER';
    IF v_count = 1 THEN
      v_table := 'BANK_STORE_MASTER';
    ELSE
      RETURN;  -- table not present in this schema; nothing to do
    END IF;
  END IF;

  add_col_if_missing('CALL_INCLUDED_PICKUPS',           'call_included_pickups NUMBER(10)');
  add_col_if_missing('CALL_MONTHLY_BANK_CHARGE',        'call_monthly_bank_charge NUMBER(18, 2)');
  add_col_if_missing('CALL_ADDITIONAL_BANK_PER_PICKUP', 'call_additional_bank_per_pickup NUMBER(18, 2)');
  add_col_if_missing('CALL_VENDOR_PAY_PER_PICKUP',      'call_vendor_pay_per_pickup NUMBER(18, 2)');
END;
/
