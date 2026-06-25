from __future__ import annotations

from typing import Any

import pandas as pd

_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")

def sanitize_excel_cell(value: Any) -> Any:
    if value is None:
        return value
    if isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        if value and value[0] in _TRIGGERS:
            return "'" + value
        return value
    s = str(value)
    if s and s[0] in _TRIGGERS:
        return "'" + s
    return s

def sanitize_rows(rows: list[list[Any]]) -> list[list[Any]]:
    return [[sanitize_excel_cell(v) for v in row] for row in rows]

def sanitize_dataframe(df: "pd.DataFrame") -> "pd.DataFrame":
    if df is None or df.empty:
        return df
    out = df.copy()
    for col in out.columns:
        s = out[col]
        if pd.api.types.is_string_dtype(s) or pd.api.types.is_object_dtype(s):
            out[col] = s.map(sanitize_excel_cell)
    return out
