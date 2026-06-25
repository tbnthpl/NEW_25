
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_EVEN, InvalidOperation
from typing import Iterable, Optional, Union

Number = Union[int, float, str, Decimal, None]

QUANT_PAISA = Decimal("0.01")

def to_decimal(value: Number, default: Decimal = Decimal("0")) -> Decimal:
    if value is None or value == "":
        return default
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default

def quantize_paisa(value: Number) -> Decimal:
    return to_decimal(value).quantize(QUANT_PAISA, rounding=ROUND_HALF_EVEN)

def sum_paisa(values: Iterable[Number]) -> Decimal:
    total = Decimal("0")
    for v in values:
        total += to_decimal(v)
    return quantize_paisa(total)

def to_float(value: Number) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
