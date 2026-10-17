"""Synthetic point-antichain mechanism only; not a road/search speed claim."""
from fractions import Fraction as R
import hashlib
import json
from pathlib import Path
import platform
import random
import statistics
import subprocess
import sys
import time
from types import SimpleNamespace
from timecut5.probe import Cut, State, Witness, reduce_cuts
from timecut5.pwa import _same_state_energy_skyline
import timecut5.pwa

class Counted:
    calls = 0
    def __init__(self, value): self.value = value
    def __lt__(self, other):
        type(self).calls += 1
        return self.value < other.value
    def __le__(self, other):
        type(self).calls += 1
        return self.value <= other.value
    def __eq__(self, other):
        type(self).calls += 1
        return self.value == other.value

state = State('synthetic', 0, 1)
pi = (('a', 'C'),)
rows = []
for n in (32, 128, 512):
    order = list(range(n))
    random.Random(20261017).shuffle(order)
    cuts = tuple(Cut(R(i, 7), True, R(0), R(n-i, 11), pi, state,
                     lambda eps, i=i: Witness(R(i, 7), R(0), R(n-i, 11), pi, state))
                 for i in order)
    expected = tuple(map(id, reduce_cuts(cuts)))
    if tuple(map(id, _same_state_energy_skyline(cuts))) != expected:
        raise RuntimeError('Point identity parity failed')
    timings = {'baseline': [], 'skyline': []}
    # Alternate order to avoid always awarding the second run a warm process.
    algorithms = [('baseline', reduce_cuts), ('skyline', _same_state_energy_skyline)]
    for repetition in range(5):
        for name, reducer in algorithms[::1 if repetition % 2 == 0 else -1]:
            start = time.perf_counter_ns()
            result = reducer(cuts)
            elapsed = time.perf_counter_ns() - start
            if tuple(map(id, result)) != expected:
                raise RuntimeError('Timed point identity parity failed')
            timings[name].append(elapsed)
    counts = {}
    wrapped = tuple(SimpleNamespace(tau=Counted(cut.tau), chi=cut.chi,
        energy=cut.energy, rho=Counted(cut.rho), pi=cut.pi, state=cut.state) for cut in cuts)
    for name, reducer in algorithms:
        Counted.calls = 0
        result = reducer(wrapped)
        if tuple(map(id, result)) != tuple(map(id, wrapped)):
            raise RuntimeError('Counted point identity parity failed')
        counts[name] = Counted.calls
    rows.append(dict(point_count=n, output_count=len(expected), all_retained=True,
        exact_object_identity_order_equal=True, rational_scalar_comparisons=counts,
        wall_ns_samples=timings,
        median_wall_ns={name: statistics.median(values) for name, values in timings.items()}))
source = Path(timecut5.pwa.__file__).resolve()
script = Path(__file__).resolve()
report = dict(schema='hiroute.synthetic_skyline_microbenchmark.v1',
    scope='same-state same-energy antichain; point algorithm only; no road, arrangement, witness, provenance or full-search timing',
    performance_claim='descriptive local microbenchmark only; not whole-search speedup or N32/N128 admission',
    input='all nondominated shuffled rational antichain tau=i/7,rho=(n-i)/11; seed=20261017',
    scalar_counter_scope='exact comparison calls on tau and rho; excludes state, energy and pi comparisons',
    repetitions=5, source_path=str(source), pwa_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    script_sha256=hashlib.sha256(script.read_bytes()).hexdigest(), python=sys.version,
    executable=sys.executable, platform=platform.platform(), rows=rows)
print(json.dumps(report, sort_keys=True, indent=2))
