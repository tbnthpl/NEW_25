-- Migration: Customer Charge Slabs - change from vendor to store
-- Customer Charge Slabs are now per store (bank_store_master), not per vendor.
-- Run on existing databases. Fresh installs use schema.sql.

-- Add store_id column
ALTER TABLE customer_charge_slabs ADD store_id NUMBER;

-- Migrate existing data: map vendor_id to first store per vendor (min store_id)
UPDATE customer_charge_slabs c
SET c.store_id = (
  SELECT MIN(b.store_id)
  FROM vendor_store_mapping_master v
  JOIN bank_store_master b ON b.bank_store_code = v.bank_store_code AND b.status = 'ACTIVE'
  WHERE v.vendor_id = c.vendor_id AND v.status = 'ACTIVE'
)
WHERE c.vendor_id IS NOT NULL;

-- For slabs with no matching store, delete or set to a default (user must recreate)
DELETE FROM customer_charge_slabs WHERE store_id IS NULL;

-- Drop vendor FK and column
ALTER TABLE customer_charge_slabs DROP CONSTRAINT fk_customer_slab_vendor;
ALTER TABLE customer_charge_slabs DROP COLUMN vendor_id;

-- Make store_id required and add FK
ALTER TABLE customer_charge_slabs MODIFY store_id NOT NULL;
ALTER TABLE customer_charge_slabs ADD CONSTRAINT fk_customer_slab_store FOREIGN KEY (store_id) REFERENCES bank_store_master(store_id);
