"""Literal v1 branchwise-infimum/attainment algebra probe, not FLAT-P or REF-v1.

There is no SOC sampling: the single output energy is an exact disproof witness.
All infima and endpoint feasibility follow analytically from rational affine slopes.
"""
from dataclasses import dataclass
from fractions import Fraction as R
from charging_audit import F


@dataclass(frozen=True)
class Branch:
    name: str
    lo: R
    hi: R
    left_open: bool
    right_open: bool
    slope: R
    intercept: R
    rho: R
    pi: tuple
    state: tuple = ('v', 1, 1)

    def contains(self, energy):
        return ((energy > self.lo if self.left_open else energy >= self.lo)
                and (energy < self.hi if self.right_open else energy <= self.hi))

    def time(self, energy):
        if not self.contains(energy):
            raise ValueError('Energy not attained in input domain')
        return self.slope * energy + self.intercept


@dataclass(frozen=True)
class Output:
    name: str
    energy: R
    time: R
    rho: R
    pi: tuple
    attained: bool
    input_energy: R | None
    state: tuple = ('site3', 1, 2)


def inputs():
    return (Branch('A', R(0), R(1), True, False, R(60), R(1000), R(0), ((1, 'C'),)),
            Branch('B', R(1, 2), R(1, 2), False, False, R(0), R(1031), R(1), ((2, 'C'),)))


def safe(t_A, rho_A, pi_A, t_B, rho_B, pi_B):
    return (t_A <= t_B and rho_A <= rho_B
            and (rho_A != rho_B or pi_A <= pi_B)
            and (t_A < t_B or rho_A < rho_B or pi_A < pi_B))


def reduce_input_hand_object(branches):
    """B is a singleton. Prove its entire deletion at its identical energy."""
    retained = []
    for b in branches:
        if b.lo != b.hi:
            retained.append(b)
            continue
        e = b.lo
        dominated = any(a is not b and a.state == b.state and a.contains(e)
            and safe(a.time(e), a.rho, a.pi, b.time(e), b.rho, b.pi) for a in branches)
        if not dominated:
            retained.append(b)
    return tuple(retained)


def C_hand_piece(branch, output_energy=R(1), h=R(300)):
    """Core section 26, analytically restricted to one frozen power segment."""
    assert 0 <= branch.lo <= branch.hi <= 1 and output_energy == 1
    upper = min(branch.hi, output_energy)
    if branch.lo > upper or (branch.lo == upper and
        (branch.left_open or branch.right_open or branch.lo == output_energy)):
        return None
    # t(E_a) - F(E_a) is affine with slope slope-36 on this interval.
    slope = branch.slope - 36
    if slope > 0:
        optimizer = branch.lo
        attained = branch.contains(optimizer) and optimizer < output_energy
    elif slope < 0:
        optimizer = upper
        attained = branch.contains(optimizer) and optimizer < output_energy
    else:
        optimizer = branch.lo if branch.lo == upper else (branch.lo + upper) / 2
        attained = branch.contains(optimizer) and optimizer < output_energy
    value = h + F(output_energy) + slope * optimizer + branch.intercept
    return Output(branch.name, output_energy, value, branch.rho,
                  branch.pi + ((3, 'C'),), attained, optimizer if attained else None)


def reduce_output(outputs):
    """Only attained outputs may dominate attained outputs. L cannot delete A."""
    result = []
    for b in outputs:
        if b is None:
            continue
        dominated = b.attained and any(a is not None and a is not b and a.attained
            and a.state == b.state and a.energy == b.energy
            and safe(a.time, a.rho, a.pi, b.time, b.rho, b.pi) for a in outputs)
        if not dominated:
            result.append(b)
    return tuple(result)


def attained_signature(outputs):
    return tuple(sorted((o.time, o.rho, o.pi) for o in outputs if o.attained))


def run():
    A, B = inputs()
    reduced = reduce_input_hand_object((A, B))
    left = reduce_output(tuple(C_hand_piece(b) for b in reduced))
    right = reduce_output(tuple(C_hand_piece(b) for b in (A, B)))
    # A valid noninfimal output discarded by branchwise earliest-time closure.
    e = R(1, 4)
    witness_time = A.time(e) + 300 + F(1) - F(e)
    assert A.contains(e) and e < 1 and witness_time == 1342
    assert safe(witness_time, A.rho, A.pi + ((3, 'C'),),
                right[1].time, right[1].rho, right[1].pi)
    return dict(left=left, right=right, reduced_input=reduced,
                congruent=attained_signature(left) == attained_signature(right),
                witness_time=witness_time,
                attained_waiting_completion=max(R(2000), witness_time + 300) + 100)
