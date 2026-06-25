-- Migration: Add finacle_header_mapping table for configurable Finacle column mapping
-- Run on existing databases. Fresh installs use schema.sql which already includes this table.

CREATE TABLE finacle_header_mapping (
  mapping_key   VARCHAR2(100) PRIMARY KEY,
  source_column VARCHAR2(255) NOT NULL
);
