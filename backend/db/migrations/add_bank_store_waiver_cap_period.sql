-- Optional validity window for store waiver cap (customer charges use billing month-end).
ALTER TABLE bank_store_master ADD waiver_cap_from DATE;
ALTER TABLE bank_store_master ADD waiver_cap_to DATE;
