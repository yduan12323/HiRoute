"""Data-only affine cut pieces over exact domains; no solver or family reduction."""
from __future__ import annotations
from dataclasses import dataclass
from fractions import Fraction
from .interval import Interval
from .scalar import exact

@dataclass(frozen=True)
class AffineCutPiece:
    domain: Interval
    slope: Fraction
    intercept: Fraction
    attained: bool
    rho: Fraction = Fraction(0)
    prefix: tuple[tuple[str, str], ...] = ()
    state_key: tuple[object, ...] = ()

    def __post_init__(self):
        if not isinstance(self.domain, Interval):
            raise TypeError("domain must be Interval")
        for name in ("slope", "intercept", "rho"):
            object.__setattr__(self, name, exact(getattr(self, name), name))
        if type(self.attained) is not bool:
            raise TypeError("attained must be bool")
        object.__setattr__(self, "prefix", tuple(tuple(x) for x in self.prefix))
        object.__setattr__(self, "state_key", tuple(self.state_key))

    def cut_time_at(self, energy) -> Fraction:
        energy = exact(energy, "energy")
        if not self.domain.contains(energy):
            raise ValueError("Energy outside represented PWA subfamily")
        return self.slope * energy + self.intercept

    def infimum(self) -> tuple[Fraction, bool, Fraction]:
        energy, endpoint_attained = self.domain.affine_infimum(self.slope)
        return (self.slope * energy + self.intercept,
                self.attained and endpoint_attained, energy)
