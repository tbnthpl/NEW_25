-- Bank charges: one saved row per store per billing month (not aggregated by customer_id).
-- Clears existing summaries because legacy rows cannot be split per store reliably.
ALTER TABLE customer_charge_summary ADD store_id NUMBER;
ALTER TABLE customer_charge_summary DROP CONSTRAINT uq_customer_charge_summary;
DELETE FROM customer_charge_summary;
ALTER TABLE customer_charge_summary MODIFY customer_id NULL;
ALTER TABLE customer_charge_summary MODIFY store_id NOT NULL;
ALTER TABLE customer_charge_summary ADD CONSTRAINT fk_cust_charge_summary_store
  FOREIGN KEY (store_id) REFERENCES bank_store_master(store_id);
ALTER TABLE customer_charge_summary ADD CONSTRAINT uq_customer_charge_summary UNIQUE (store_id, month_key);
