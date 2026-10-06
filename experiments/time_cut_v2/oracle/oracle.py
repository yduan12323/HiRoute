"""Independent exact C/CS oracle: analytic one-dimensional convex optimization.

No production imports, no elimination/projection library, no floating point.
The independent symbolic partition is an exhaustive arrangement of all candidate
arrival-energy paths and candidate objective values, not an energy grid.
"""
from __future__ import annotations
from dataclasses import dataclass
from fractions import Fraction as Q
from itertools import combinations


def rat(x):
    if isinstance(x, bool) or not isinstance(x, (int, Q)):
        raise TypeError("exact int/Fraction required")
    return Q(x)


@dataclass(frozen=True)
class Span:
    lo: Q
    hi: Q
    lc: bool = True
    rc: bool = True

    def __post_init__(self):
        object.__setattr__(self, 'lo', rat(self.lo))
        object.__setattr__(self, 'hi', rat(self.hi))
        if self.lo > self.hi or self.lo == self.hi and not (self.lc and self.rc):
            raise ValueError("empty span")

    def contains(self, x):
        return ((x > self.lo or x == self.lo and self.lc)
                and (x < self.hi or x == self.hi and self.rc))

    def intersect(self, other):
        lo, hi = max(self.lo, other.lo), min(self.hi, other.hi)
        lc, rc = self.contains(lo) and other.contains(lo), self.contains(hi) and other.contains(hi)
        return None if lo > hi or lo == hi and not (lc and rc) else Span(lo, hi, lc, rc)

    def bound(self, slope, rhs, strict=False):
        """Intersect with slope*x <= rhs (or < rhs), directly in one dimension."""
        if slope == 0:
            return self if (0 < rhs if strict else 0 <= rhs) else None
        edge = rhs / slope
        if slope > 0:
            hi = min(self.hi, edge)
            rc = self.contains(hi) and (hi < edge or not strict)
            return None if self.lo > hi or self.lo == hi and not (self.lc and rc) else Span(self.lo, hi, self.lc, rc)
        lo = max(self.lo, edge)
        lc = self.contains(lo) and (lo > edge or not strict)
        return None if lo > self.hi or lo == self.hi and not (lc and self.rc) else Span(lo, self.hi, lc, self.rc)

    def member(self):
        return self.lo if self.lo == self.hi else (self.lo + self.hi) / 2


@dataclass(frozen=True, order=True)
class Aff:
    slope: Q = Q(0)
    intercept: Q = Q(0)

    def __call__(self, y):
        return self.slope*y+self.intercept

    def root_against(self, other):
        return None if self.slope == other.slope else (other.intercept-self.intercept)/(self.slope-other.slope)


@dataclass(frozen=True)
class Plane:
    """Objective alpha*Ea + beta*Ed + gamma."""
    alpha: Q
    beta: Q
    gamma: Q

    def at(self, x, y):
        return self.alpha*x+self.beta*y+self.gamma

    def along(self, path):
        return Aff(self.alpha*path.slope+self.beta, self.alpha*path.intercept+self.gamma)


@dataclass(frozen=True)
class Seed:
    domain: Span
    slope: Q
    intercept: Q
    chi: bool

    @classmethod
    def from_piece(cls, piece):
        """Read only public input data; never evaluate a production transform."""
        d = piece.domain
        return cls(Span(d.lo, d.hi, d.left_closed, d.right_closed), rat(piece.slope), rat(piece.intercept), piece.chi)


@dataclass(frozen=True)
class Answer:
    tau: Q
    chi: bool


@dataclass(frozen=True)
class Regime:
    domain: Span
    input: Seed
    departure: Span
    planes: tuple[Plane, ...]
    combined: bool
    plateau: Q | None

    def candidates(self):
        paths = {Aff(Q(0), self.domain.lo), Aff(Q(0), self.domain.hi), Aff(Q(1), Q(0))}
        for p, q in combinations(self.planes, 2):
            if p.alpha != q.alpha:
                paths.add(Aff((q.beta-p.beta)/(p.alpha-q.alpha), (q.gamma-p.gamma)/(p.alpha-q.alpha)))
        return tuple(sorted(paths))

    def energy_domain(self, y):
        if not self.departure.contains(y):
            return None
        return self.domain.bound(Q(1), y, strict=True)

    def answer(self, y):
        domain = self.energy_domain(y)
        if domain is None:
            return None
        # The closure is compact. A convex PWA minimum lies at a boundary or
        # at an intersection of two affine objective planes, unless constant.
        candidates = {domain.lo, domain.hi}
        for path in self.candidates():
            x = path(y)
            if domain.lo <= x <= domain.hi:
                candidates.add(x)
        value = min(max(p.at(x,y) for p in self.planes) for x in candidates)
        optimal = domain
        if self.input.chi:
            for p in self.planes:
                optimal = optimal.bound(p.alpha, value-p.beta*y-p.gamma) if optimal else None
        elif not self.combined or value != self.plateau:
            optimal = None
        else:
            # Open input can hit the constant schedule plateau only with
            # strict slack in BOTH time-dependent planes. Equality is open.
            for p in self.planes[1:]:
                optimal = optimal.bound(p.alpha, value-p.beta*y-p.gamma, strict=True) if optimal else None
        return Answer(value, optimal is not None)


class Oracle:
    """Independent one-step union oracle over same-context affine input pieces."""
    def __init__(self, seeds, segments, overhead, *, a=None, b=None, duration=None):
        self.seeds = tuple(seeds)
        self.segments = tuple(tuple(map(rat,row)) for row in segments)
        self.overhead = rat(overhead)
        if self.overhead <= 0:
            raise ValueError("positive overhead required")
        self.combined = a is not None
        self.a, self.b, self.duration = (None, None, None) if not self.combined else tuple(map(rat,(a,b,duration)))
        self.capacity = self.segments[-1][1]
        regimes = []
        if self.combined and (self.a > self.b or self.duration < 0):
            self.regimes = ()
            return
        for seed in self.seeds:
            for lo,hi,ma,ca in self.segments:
                domain = seed.domain.intersect(Span(lo,hi))
                if domain and self.combined:
                    domain = domain.bound(seed.slope,self.b-self.overhead-seed.intercept,strict=not seed.chi)
                if domain is None:
                    continue
                for ld,hd,md,cd in self.segments:
                    charge = Plane(seed.slope-ma,md,seed.intercept+self.overhead+cd-ca)
                    plateau = None
                    if self.combined:
                        plateau = self.a+self.duration
                        planes = (Plane(Q(0),Q(0),plateau), Plane(seed.slope,Q(0),seed.intercept+self.overhead+self.duration),charge)
                    else:
                        planes = (charge,)
                    regimes.append(Regime(domain,seed,Span(ld,hd),planes,self.combined,plateau))
        self.regimes = tuple(regimes)

    @classmethod
    def from_public_inputs(cls, pieces, curve, overhead, **kwargs):
        return cls([Seed.from_piece(p) for p in pieces],curve.segments,overhead,**kwargs)

    def at(self, energy):
        energy = rat(energy)
        if not 0 <= energy <= self.capacity:
            return None
        answers = [a for r in self.regimes if (a := r.answer(energy)) is not None]
        if not answers:
            return None
        tau = min(a.tau for a in answers)
        return Answer(tau,any(a.chi for a in answers if a.tau == tau))

    def boundaries(self):
        """Complete rational Ed arrangement, potentially intentionally redundant.

        Candidate path crossings stabilize feasible candidate membership and
        minimizer-face endpoint membership. Candidate plane-value crossings
        stabilize max-plane selection and cross-regime winner selection.
        Strictness and input chi are constant on every remaining open cell.
        """
        boundaries = {Q(0),self.capacity}
        lines = set()
        for regime in self.regimes:
            boundaries.update((regime.departure.lo,regime.departure.hi))
            paths = regime.candidates()
            for p,q in combinations(paths,2):
                root = p.root_against(q)
                if root is not None and 0 <= root <= self.capacity:
                    boundaries.add(root)
            lines.update(p.along(path) for p in regime.planes for path in paths)
        for p,q in combinations(sorted(lines),2):
            root = p.root_against(q)
            if root is not None and 0 <= root <= self.capacity:
                boundaries.add(root)
        return tuple(sorted(boundaries))

    def pieces(self):
        """Return complete cells as (Span, affine tau, constant chi).

        Two evaluations identify the affine coefficients only AFTER the
        independently complete arrangement proves affine/chi constancy.
        Singleton boundaries are evaluated separately, including capacity.
        """
        knots = self.boundaries()
        out = []
        for x in knots:
            answer = self.at(x)
            if answer is not None:
                out.append((Span(x,x),Aff(Q(0),answer.tau),answer.chi))
        for lo,hi in zip(knots,knots[1:]):
            p,q = (2*lo+hi)/3,(lo+2*hi)/3
            ap,aq = self.at(p),self.at(q)
            assert (ap is None) == (aq is None)
            if ap is None:
                continue
            assert ap.chi == aq.chi
            slope = (aq.tau-ap.tau)/(q-p)
            out.append((Span(lo,hi,False,False),Aff(slope,ap.tau-slope*p),ap.chi))
        return tuple(sorted(out,key=lambda r:(r[0].lo,r[0].hi)))
