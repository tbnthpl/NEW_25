-- Migration: Remove BOTH from store pickup_type. Only BEAT and CALL allowed.
-- Migrate existing BOTH values to BEAT.

UPDATE bank_store_master SET pickup_type = 'BEAT' WHERE pickup_type = 'BOTH';
COMMIT;

ALTER TABLE bank_store_master DROP CONSTRAINT chk_store_pickup_type;
ALTER TABLE bank_store_master ADD CONSTRAINT chk_store_pickup_type CHECK (pickup_type IN ('BEAT','CALL'));
