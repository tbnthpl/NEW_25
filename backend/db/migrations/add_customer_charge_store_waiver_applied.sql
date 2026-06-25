-- Rupees waived on the store line this month (debited from cumulative waiver_cap_amount pool when cap is set)
ALTER TABLE customer_charge_summary ADD store_waiver_applied NUMBER(18,2) DEFAULT 0;
