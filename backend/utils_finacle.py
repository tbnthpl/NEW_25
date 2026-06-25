
from backend.models import FinacleHeaderMapping

FINACLE_DEFAULT_MAPPING = {
    "store_code_column": "STORE_CODE",
    "remittance_amount_column": "COLLN_AMT",
    "remittance_date_column": "TRAN_DATE",
    "account_no_column": "FORACID",
    "customer_id_column": "CUST_ID",
    "customer_name_column": "ACCT_NAME",
    "sol_id_column": "SOL_ID",
    "location_column": "LOCATION",
    "tran_id_column": "TRAN_ID",
    "tran_type_column": "TRAN_TYPE",
}

def get_finacle_mapping(db) -> dict:
    rows = db.query(FinacleHeaderMapping).all()
    if not rows:
        return dict(FINACLE_DEFAULT_MAPPING)
    return {m.mapping_key: m.source_column for m in rows}

def get_finacle_required_headers(mapping: dict) -> set:
    return set(mapping.values())
