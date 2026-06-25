-- Charge config maker-checker inserts a new row per request with the same config_code;
-- drop the unique constraint so multiple version rows can exist (only one ACTIVE enforced in app).
--
-- Idempotent AND rename-aware: works whether the table is still called
-- CHARGE_CONFIGURATION_MASTER (legacy) or DSB_CHARGE_CONFIGURATION_MASTER (post dsb_ rename).
-- A NO_DATA_FOUND exception (no UQ on CONFIG_CODE) is treated as a no-op.

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
