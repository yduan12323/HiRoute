"""Exact strict linear rows, Fourier–Motzkin projection, and constructive lift."""
from __future__ import annotations
from dataclasses import dataclass
from fractions import Fraction
from typing import Iterable
from .scalar import exact

@dataclass(frozen=True)
class Row:
    """One affine condition coefficients·x <= rhs (or < rhs if strict)."""
    coefficients: tuple[Fraction, ...]
    rhs: Fraction
    strict: bool = False
    def __post_init__(self):
        object.__setattr__(self, "coefficients", tuple(exact(a, "coefficient") for a in self.coefficients))
        object.__setattr__(self, "rhs", exact(self.rhs, "rhs"))
        if type(self.strict) is not bool:
            raise TypeError("strict must be bool")
    def holds(self, point: tuple[Fraction, ...]) -> bool:
        if len(point) != len(self.coefficients):
            raise ValueError("Wrong point dimension")
        value = sum((a * exact(x, "coordinate") for a, x in zip(self.coefficients, point)), Fraction(0))
        return value < self.rhs if self.strict else value <= self.rhs

def normalize(rows: Iterable[Row]) -> tuple[Row, ...] | None:
    """Normalize only by positive scale, deduplicate, and retain strictness."""
    result = {}
    dimension = None
    for row in rows:
        if dimension is not None and len(row.coefficients) != dimension:
            raise ValueError("Inconsistent row dimensions")
        dimension = len(row.coefficients)
        first = next((a for a in row.coefficients if a), None)
        if first is None:
            if row.rhs < 0 or (row.rhs == 0 and row.strict):
                return None
            continue
        scale = abs(first)
        coefficients = tuple(a / scale for a in row.coefficients)
        rhs = row.rhs / scale
        key = (coefficients, rhs)
        result[key] = result.get(key, False) or row.strict
    return tuple(Row(c, b, strict) for (c, b), strict in sorted(result.items()))

def eliminate(rows: Iterable[Row], variable: int) -> tuple[Row, ...] | None:
    """Existential strict Fourier–Motzkin elimination with exact rational rows."""
    current = normalize(rows)
    if current is None:
        return None
    if any(variable < 0 or variable >= len(row.coefficients) for row in current):
        raise IndexError("Eliminated variable is outside the row dimension")
    positive, negative, zero = [], [], []
    for row in current:
        a = row.coefficients[variable]
        (positive if a > 0 else negative if a < 0 else zero).append(row)
    output = list(zero)
    for upper in positive:
        for lower in negative:
            up, down = upper.coefficients[variable], -lower.coefficients[variable]
            output.append(Row(
                tuple(a / up + b / down for a, b in zip(upper.coefficients, lower.coefficients)),
                upper.rhs / up + lower.rhs / down,
                upper.strict or lower.strict))
    return normalize(output)

def _choose(bounds: Iterable[tuple[Fraction, Fraction, bool]]) -> Fraction:
    lower = upper = None
    lower_strict = upper_strict = False
    for a, b, strict in bounds:
        if a == 0:
            if b < 0 or (b == 0 and strict):
                raise ValueError("Infeasible zero row in witness fiber")
            continue
        value = b / a
        if a < 0:
            if lower is None or value > lower:
                lower, lower_strict = value, strict
            elif value == lower:
                lower_strict = lower_strict or strict
        else:
            if upper is None or value < upper:
                upper, upper_strict = value, strict
            elif value == upper:
                upper_strict = upper_strict or strict
    if lower is not None and upper is not None:
        if lower > upper or (lower == upper and (lower_strict or upper_strict)):
            raise ValueError("Empty strict witness fiber")
        return (lower + upper) / 2
    if lower is not None:
        return lower + 1 if lower_strict else lower
    if upper is not None:
        return upper - 1 if upper_strict else upper
    return Fraction(0)

@dataclass(frozen=True)
class Projection:
    original: tuple[Row, ...]
    rows: tuple[Row, ...]
    history: tuple[tuple[int, tuple[Row, ...]], ...]
    @classmethod
    def build(cls, rows: Iterable[Row], variables: Iterable[int]) -> "Projection | None":
        original = normalize(rows)
        if original is None:
            return None
        variables = tuple(variables)
        if len(set(variables)) != len(variables):
            raise ValueError("Cannot eliminate a variable twice")
        current, history = original, []
        dimension = len(original[0].coefficients) if original else 0
        if any(type(v) is not int or v < 0 or v >= dimension for v in variables):
            raise IndexError("Eliminated variable is outside the row dimension")
        for variable in variables:
            history.append((variable, current))
            current = eliminate(current, variable)
            if current is None:
                return None
        return cls(original, current, tuple(history))
    def lift(self, fixed: dict[int, Fraction]) -> tuple[Fraction, ...]:
        values = {i: exact(value, "fixed coordinate") for i, value in fixed.items()}
        for variable, rows in reversed(self.history):
            if variable in values:
                raise ValueError("An eliminated variable was already fixed")
            bounds = []
            for row in rows:
                residual = row.rhs
                for i, coefficient in enumerate(row.coefficients):
                    if i == variable or not coefficient:
                        continue
                    if i not in values:
                        raise ValueError("Missing retained coordinate during lifting")
                    residual -= coefficient * values[i]
                bounds.append((row.coefficients[variable], residual, row.strict))
            values[variable] = _choose(bounds)
        dimension = len(self.original[0].coefficients) if self.original else len(values)
        if any(i not in values for i in range(dimension)):
            raise ValueError("Missing projected coordinate during lifting")
        point = tuple(values[i] for i in range(dimension))
        if not all(row.holds(point) for row in self.original):
            raise AssertionError("Lifted point violates its original strict system")
        return point
