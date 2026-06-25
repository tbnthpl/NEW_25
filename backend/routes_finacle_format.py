
from fastapi import APIRouter, Depends, HTTPException, status

from backend.auth import AuthUser, require_roles
from backend.audit import log_audit
from backend.db import SessionLocal
from backend.models import FinacleHeaderMapping
from backend.schemas import FinacleFormatUpdateRequest
from backend.utils_finacle import FINACLE_DEFAULT_MAPPING, get_finacle_mapping

router = APIRouter(prefix="/api/finacle-format", tags=["finacle-format"])

@router.get("")
def get_mapping(user: AuthUser = Depends(require_roles("ADMIN"))):
    db = SessionLocal()
    mapping = get_finacle_mapping(db)
    log_audit(db, "FINACLE_FORMAT", "MAPPING", "VIEW", None, f"keys={len(mapping)}", user.employee_id)
    db.commit()
    db.close()
    return {"mapping": mapping}

@router.put("")
def update_mapping(
    payload: FinacleFormatUpdateRequest,
    user: AuthUser = Depends(require_roles("ADMIN")),
):
    mapping = payload.mapping or {}
    if not isinstance(mapping, dict):
        raise HTTPException(status_code=400, detail="mapping must be an object")

    allowed_keys = set(FINACLE_DEFAULT_MAPPING.keys())
    for key, val in mapping.items():
        if key not in allowed_keys:
            raise HTTPException(status_code=400, detail=f"Unknown mapping key: {key}")
        if not val or not str(val).strip():
            raise HTTPException(status_code=400, detail=f"Empty value for {key}")

    db = SessionLocal()
    db.query(FinacleHeaderMapping).delete(synchronize_session=False)
    for key, val in mapping.items():
        v = str(val).strip()
        if key in allowed_keys and v:
            db.add(FinacleHeaderMapping(mapping_key=key, source_column=v))

    log_audit(
        db,
        "FINACLE_FORMAT",
        "MAPPING",
        "UPDATE",
        None,
        f"keys={list(mapping.keys())}",
        user.employee_id,
    )
    db.commit()
    result = {m.mapping_key: m.source_column for m in db.query(FinacleHeaderMapping).all()}
    if not result:
        result = dict(FINACLE_DEFAULT_MAPPING)
    db.close()
    return {"status": "OK", "mapping": result}

@router.post("/reset")
def reset_mapping(user: AuthUser = Depends(require_roles("ADMIN"))):
    db = SessionLocal()
    db.query(FinacleHeaderMapping).delete(synchronize_session=False)
    for key, val in FINACLE_DEFAULT_MAPPING.items():
        db.add(FinacleHeaderMapping(mapping_key=key, source_column=val))

    log_audit(db, "FINACLE_FORMAT", "MAPPING", "RESET", None, "Defaults restored", user.employee_id)
    db.commit()
    db.close()
    return {"status": "OK", "mapping": dict(FINACLE_DEFAULT_MAPPING)}
