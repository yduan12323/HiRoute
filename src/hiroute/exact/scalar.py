"""Exact scalar boundary for the migrated mathematical namespace."""
from __future__ import annotations
from fractions import Fraction
import re
from typing import Any

_RATIONAL = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:/[1-9][0-9]*)?$")

def exact(value: Any, name: str = "value") -> Fraction:
    """Parse integer or canonical rational text; reject bools and binary floats."""
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError(f"{name} must be an integer or exact rational string")
    if isinstance(value, int):
        return Fraction(value)
    if isinstance(value, Fraction):
        return value
    if isinstance(value, str) and _RATIONAL.fullmatch(value):
        return Fraction(value)
    raise TypeError(f"{name} must be an integer or canonical rational string")

def rational_text(value: Any, name: str = "value") -> str:
    return str(exact(value, name))
