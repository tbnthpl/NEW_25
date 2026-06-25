-- Vendor Beat Slabs: slab-based monthly charge per Beat store
-- amount_from/to = daily pickup limit range, charge_amount = monthly charge
-- Each vendor has its own slabs

CREATE SEQUENCE seq_vendor_beat_slab START WITH 1 INCREMENT BY 1 NOCACHE;

CREATE TABLE vendor_beat_slabs (
  slab_id           NUMBER PRIMARY KEY,
  vendor_id         NUMBER NOT NULL,
  amount_from       NUMBER(18,2) NOT NULL,
  amount_to         NUMBER(18,2) NOT NULL,
  charge_amount     NUMBER(18,2) NOT NULL,
  slab_label        VARCHAR2(100),
  status            VARCHAR2(10) NOT NULL,
  effective_from    DATE NOT NULL,
  effective_to      DATE,
  created_by        VARCHAR2(50) NOT NULL,
  created_date      DATE DEFAULT SYSDATE NOT NULL,
  approved_by       VARCHAR2(50),
  approved_date     DATE,
  CONSTRAINT fk_vendor_beat_slab_vendor FOREIGN KEY (vendor_id) REFERENCES vendor_master(vendor_id),
  CONSTRAINT chk_vendor_beat_slab_status CHECK (status IN ('ACTIVE','INACTIVE'))
);
