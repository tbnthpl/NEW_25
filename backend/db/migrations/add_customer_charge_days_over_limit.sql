-- Days in the month where final recon amount exceeded the store daily pickup limit (per customer charge summary).
ALTER TABLE customer_charge_summary ADD days_over_limit NUMBER(10) DEFAULT 0;
