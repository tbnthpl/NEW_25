-- H13: persistent token store so the auth layer can scale beyond a single pod.
-- Idempotent: safe to run multiple times.

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
