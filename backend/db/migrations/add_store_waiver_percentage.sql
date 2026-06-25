-- Per-store waiver % for customer bank charges (applied before customer-level waiver master).
ALTER TABLE bank_store_master ADD waiver_percentage NUMBER(5, 2);
