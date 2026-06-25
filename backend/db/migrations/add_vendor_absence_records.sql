-- Migration: Add vendor_absence_records table for tracking vendor pickup failures
-- Tracks cases where Finacle expected a scheduled pickup at a store but the vendor did not perform it.
-- Used for monitoring and reporting on vendor absence.

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
