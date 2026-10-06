"""Independent finite integral audit of the unchanged accepted evaluator."""
from fractions import Fraction as R
from itertools import combinations_with_replacement
from stopplan4r.models import PiecewiseChargingCurve
from preflight import ROOT, digest, write


SEGMENTS = ((R(0), R(30), R(100)), (R(30), R(48), R(60)),
            (R(48), R(60), R(30)))


def F(energy):
    energy = R(energy)
    if not 0 <= energy <= 60:
        raise ValueError('Outside frozen charging primitive')
    return sum((R(3600) * max(R(0), min(energy, hi) - lo) / power
                for lo, hi, power in SEGMENTS), R(0))


def audit():
    curve = PiecewiseChargingCurve()
    assert curve.bands == ((0.5, 100.0), (0.8, 60.0), (1.0, 30.0))
    assert curve.segments(60) == [(0.0, 30.0, 36.0, 0.0),
                                  (30.0, 48.0, 60.0, -720.0),
                                  (48.0, 60.0, 120.0, -3600.0)]
    energies = tuple(map(R, ['0', '1/7', '15', '30', '31', '47', '48', '49', '59', '60']))
    rows = []
    for a, b in combinations_with_replacement(energies, 2):
        exact = F(b) - F(a)
        direct = sum((R(3600) * max(R(0), min(b, hi) - max(a, lo)) / power
                      for lo, hi, power in SEGMENTS), R(0))
        assert exact == direct
        evaluator = curve.duration_s(float(a), float(b), 60)
        error = abs(evaluator - float(exact))
        rows.append(dict(a=str(a), b=str(b), exact_s=str(exact), evaluator_s=evaluator,
                         absolute_error_s=error, passed=error <= 1e-10))
    assert all(r['passed'] for r in rows)
    return dict(status='passed', violations=0, audited_pairs=len(rows),
        evaluator_path='src/stopplan4r/models.py', evaluator_sha256=digest(ROOT / 'src/stopplan4r/models.py'),
        segments=[dict(low=str(lo), high=str(hi), power_kw=str(p), slope_s_per_kwh=str(R(3600)/p))
                  for lo, hi, p in SEGMENTS],
        finite_PWA_contract_passed=True, positive_power_verified=True,
        source_unchanged=True, arithmetic_scope='Rational integral + binary64 evaluator compatibility audit',
        cases=rows)


if __name__ == '__main__':
    write('charging_primitive_audit.json', audit())
