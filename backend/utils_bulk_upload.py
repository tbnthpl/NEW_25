
import io
import os

import pandas as pd
from fastapi import HTTPException

from backend.utils_upload_security import read_validated_excel_upload

EXCEL_MAX_ROWS = int(os.environ.get("EXCEL_MAX_ROWS", "200000"))

def read_bulk_upload_dataframe(content: bytes, filename: str | None) -> pd.DataFrame:
    name = (filename or "").lower()
    if name.endswith(".csv"):
        raise HTTPException(
            status_code=400,
            detail="CSV is not supported for bulk upload. Use Excel (.xlsx or .xls).",
        )
    if name and not (name.endswith(".xlsx") or name.endswith(".xls")):
        raise HTTPException(
            status_code=400,
            detail="Upload an Excel file (.xlsx or .xls).",
        )
    try:
        df = pd.read_excel(io.BytesIO(content), nrows=EXCEL_MAX_ROWS + 1)
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid or unsupported Excel file.") from e
    if len(df) > EXCEL_MAX_ROWS:
        raise HTTPException(
            status_code=413,
            detail=f"Workbook exceeds {EXCEL_MAX_ROWS:,} rows. Split the file and try again.",
        )
    return df

def read_bulk_upload_file(file) -> pd.DataFrame:
    content = read_validated_excel_upload(file)
    return read_bulk_upload_dataframe(content, file.filename)
