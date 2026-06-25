-- Migration: Add api_log table for API/application error logging
-- Run on existing databases. Logs API errors (4xx, 5xx) for troubleshooting.

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
