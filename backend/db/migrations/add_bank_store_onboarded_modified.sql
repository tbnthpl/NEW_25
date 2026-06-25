-- Store onboarding: first ACTIVE approval date + last change timestamp
ALTER TABLE bank_store_master ADD onboarded_date DATE;
ALTER TABLE bank_store_master ADD last_modified_date DATE;

-- Best-effort backfill for rows that already have audit timestamps (onboarded_date left NULL for legacy)
UPDATE bank_store_master
SET last_modified_date = NVL(approved_date, created_date)
WHERE last_modified_date IS NULL;
