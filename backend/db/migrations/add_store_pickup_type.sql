-- Migration: Add pickup_type to bank_store_master for vendor absence filtering
-- BEAT = scheduled daily pickup (absence applies), CALL = on-demand (no absence)

ALTER TABLE bank_store_master ADD pickup_type VARCHAR2(10) DEFAULT 'BEAT';
ALTER TABLE bank_store_master ADD CONSTRAINT chk_store_pickup_type CHECK (pickup_type IN ('BEAT','CALL'));
