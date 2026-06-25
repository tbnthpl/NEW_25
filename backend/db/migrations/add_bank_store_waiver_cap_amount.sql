-- Per-store monthly waiver cap (₹) on customer charges, optional; used with waiver_percentage.
ALTER TABLE bank_store_master ADD waiver_cap_amount NUMBER(18, 2);
