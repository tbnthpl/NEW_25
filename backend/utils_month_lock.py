from fastapi import HTTPException, status

from backend.models import MonthLock


def is_month_locked(db, month_key: str) -> bool:
    return (
        db.query(MonthLock)
        .filter(MonthLock.month_key == month_key)
        .filter(MonthLock.status == "LOCKED")
        .first()
        is not None
    )


def enforce_month_unlocked(db, month_key: str) -> None:
    if is_month_locked(db, month_key):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Month {month_key} is locked.",
        )
