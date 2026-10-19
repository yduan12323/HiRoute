"""Linux owned-subtree accounting for a dedicated, serial queue process.

RUSAGE_CHILDREN already includes CPU charged through descendants waited by a
child. Do not sum it with worker-reported inclusive CPU. During execution, sum
live descendant self + already-waited child CPU; zombie CPU is not also charged
to its parent until wait. Sampling races are bounded observations, not a cgroup.
"""
from dataclasses import dataclass
import math
import os
from pathlib import Path
import resource
import time

CPU_BUDGET = 40 * 3600
WALL_BUDGET = 48 * 3600
PHASE_LIMITS = {'prepare': (600, 600), 'search': (1500, 1500),
                'replay': (180, 120), 'ref': (120, 120)}


def cpu_total():
    own = resource.getrusage(resource.RUSAGE_SELF)
    children = resource.getrusage(resource.RUSAGE_CHILDREN)
    return own.ru_utime + own.ru_stime + children.ru_utime + children.ru_stime


def memory_available():
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.startswith('MemAvailable:'):
            fields = line.split()
            if len(fields) != 3 or fields[2] != 'kB':
                break
            return int(fields[1]) * 1024
    raise RuntimeError('MemAvailable unavailable: fail closed')


def live_descendant_cpu():
    records = {}
    for entry in Path('/proc').iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            fields = (entry/'stat').read_text().rsplit(')', 1)[1].split()
            records[int(entry.name)] = (int(fields[1]), sum(int(fields[i]) for i in (11,12,13,14)))
        except (FileNotFoundError, ProcessLookupError):
            continue
    pending = [os.getpid()]; total = 0; seen = set(pending)
    while pending:
        parent = pending.pop()
        for pid, (ppid, ticks) in records.items():
            if ppid == parent and pid not in seen:
                seen.add(pid); pending.append(pid); total += ticks
    return total / os.sysconf('SC_CLK_TCK')


@dataclass
class Budget:
    cpu_seconds: float = CPU_BUDGET
    wall_seconds: float = WALL_BUDGET

    def __post_init__(self):
        for value in (self.cpu_seconds, self.wall_seconds):
            if type(value) not in (int,float) or not math.isfinite(value) or value <= 0:
                raise ValueError('Positive finite global budget required')
        if self.cpu_seconds > CPU_BUDGET or self.wall_seconds > WALL_BUDGET:
            raise ValueError('Cannot expand approved global budget')
        self.cpu_start = cpu_total()
        self.wall_start = time.monotonic()

    def measured(self):
        return {'cpu_seconds': cpu_total()-self.cpu_start,
                'wall_seconds': time.monotonic()-self.wall_start}

    def remaining(self):
        used = self.measured()
        return self.cpu_seconds-used['cpu_seconds'], self.wall_seconds-used['wall_seconds']

    def reserve_domain(self, operations):
        # Serial CPU capped to each slot including its supervisor; cleanup and
        # queue work reserve 10 CPU/wall seconds per operation plus 60 per domain.
        # Actual CPU remains measured globally, never debited twice as reservation.
        operations = tuple(operations)
        cpu = sum(PHASE_LIMITS[x][1]+10 for x in operations)+60
        wall = sum(PHASE_LIMITS[x][0]+10 for x in operations)+60
        remaining_cpu, remaining_wall = self.remaining()
        return {'admitted': remaining_cpu >= cpu and remaining_wall >= wall,
                'cpu_seconds': cpu, 'wall_seconds': wall,
                'remaining_cpu_seconds': remaining_cpu, 'remaining_wall_seconds': remaining_wall}


class ContinuationBudget(Budget):
    """Explicit conservative carry-in, never an inferred/reset real-run budget.

    Caller supplies the reviewed cumulative debit at transition and original
    absolute deadline. The carry-in is charged once, then SELF+waited CHILDREN
    accounting continues from that instant. This is not recovered measurement.
    """
    def __init__(self, *, carried_cpu_seconds, deadline_utc, transition_utc,
                 cpu_seconds=CPU_BUDGET, transition_cpu_capacity):
        from datetime import datetime, timezone
        def stamp(value):
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if parsed.tzinfo is None:
                raise ValueError('Timezone-aware UTC timestamp required')
            return parsed.astimezone(timezone.utc).timestamp()
        if (type(carried_cpu_seconds) not in (int, float)
                or not math.isfinite(carried_cpu_seconds) or carried_cpu_seconds < 0):
            raise ValueError('Finite nonnegative cumulative debit required')
        if type(transition_cpu_capacity) is not int or transition_cpu_capacity < 1:
            raise ValueError('Reviewed transition CPU capacity required')
        transition, deadline = stamp(transition_utc), stamp(deadline_utc)
        now = time.time()
        if transition > now or deadline <= transition or deadline-transition > WALL_BUDGET:
            raise ValueError('Invalid transition/deadline interval')
        super().__init__(cpu_seconds=cpu_seconds, wall_seconds=min(WALL_BUDGET, deadline-transition))
        now = max(now,time.time())  # Sample after the measured CPU baseline, conservatively overlapping setup.
        self.carried_cpu_seconds = float(carried_cpu_seconds) + transition_cpu_capacity*math.ceil(max(0,now-transition))
        self.deadline_timestamp = deadline
        self.transition_timestamp = transition
        self.wall_start -= now-transition
        self._deadline_monotonic = self.wall_start+self.wall_seconds

    def measured(self):
        used = super().measured()
        used['cpu_seconds'] += self.carried_cpu_seconds
        # Wall-clock jumps forward must tighten the deadline; backwards jumps
        # cannot enlarge the original monotonic allowance.
        monotonic_now=time.monotonic()
        self._deadline_monotonic=min(self._deadline_monotonic,
                                     monotonic_now+self.deadline_timestamp-time.time())
        used['wall_seconds']=self.wall_seconds-(self._deadline_monotonic-monotonic_now)
        return used


def conservative_transition_debit(*, prior_debit, active_since_utc,
                                  transition_utc, cpu_capacity):
    """Round active uncertain time upward; never infer topology from CPU count."""
    from datetime import datetime
    if (type(prior_debit) not in (int,float) or not math.isfinite(prior_debit)
            or prior_debit < 0 or type(cpu_capacity) is not int or cpu_capacity < 1):
        raise ValueError('Invalid conservative envelope')
    stamps=[]
    for value in (active_since_utc,transition_utc):
        parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
        if parsed.tzinfo is None:raise ValueError('Timezone-aware timestamp required')
        stamps.append(parsed.timestamp())
    elapsed=stamps[1]-stamps[0]
    if elapsed<0:raise ValueError('Negative active elapsed time')
    return prior_debit+cpu_capacity*math.ceil(elapsed)
