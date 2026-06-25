-- Add sample Customer Charge Slabs for stores 001-005 (covers remittance 0-50K)
-- Run after stores are onboarded. Enables customer charge computation for sample data.
INSERT INTO customer_charge_slabs (slab_id, store_id, amount_from, amount_to, charge_amount, slab_label, status, effective_from, created_by)
SELECT seq_customer_charge_slab.nextval, s.store_id, 0, 50000, 4000, 'Upto 50K', 'ACTIVE', DATE '2025-01-01', 'SYSTEM'
FROM bank_store_master s
WHERE s.bank_store_code IN ('001','002','003','004','005') AND s.status = 'ACTIVE'
  AND NOT EXISTS (SELECT 1 FROM customer_charge_slabs c WHERE c.store_id = s.store_id AND c.status = 'ACTIVE');
COMMIT;
