"""Pure, immutable declarations. This module never opens an input file.

Digesting an explicitly supplied synthetic declaration is not holdout freezing.
Real data binding, selection, generation, hashing and execution remain disabled.
"""
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json

SCHEMA = 'hiroute.m6h.held_contract.v1'
SEED_POLICY = 'first_feasible_streamed_proposal_fresh_double_replay_v1'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def require_real_authorization(*args, **kwargs):
    # Deliberately no boolean, manifest field or environment-variable bypass.
    raise PermissionError('M6-H held: final protocol/selection approval and reviewed real adapter required')


freeze = consume = generate = execute = require_real_authorization


def positive(value, name):
    if type(value) is not int or value <= 0:
        raise ValueError('Positive integer required: ' + name)
    return value


def plan(group_slots=6):
    """Anonymous numbered slots, not selected OD identities or geography."""
    positive(group_slots, 'group_slots')
    if group_slots > 6:
        raise ValueError('Held proposal permits at most six anonymous groups')
    domains = []
    for n in (8, 32, 128):
        ordinal = 0
        for group in range(group_slots):
            for soc in (('3/10',) if n == 8 else ('3/10', '19/25')):
                domains.append(dict(id=f'n{n}-g{group}-s{soc.replace("/", "_")}',
                    group_slot=group, soc=soc, candidate_count=n, ref=n == 8,
                    method_order=['flat', 'hier'] if ordinal % 2 == 0 else ['hier', 'flat']))
                ordinal += 1
    return dict(schema=SCHEMA, status='HELD', launchable=False, domains=domains,
        denominator=dict(domains=5*group_slots, operational_slots=26*group_slots,
            method_results=10*group_slots, reference_results=group_slots,
            main_domains=4*group_slots, main_method_results=8*group_slots),
        budget=dict(cpu_seconds=144000, wall_seconds=172800),
        phase_limits=dict(prepare=[600,600], search=[1500,1500], replay=[180,120], ref=[120,120]),
        exact_phase_seconds=1200, seed_policy=SEED_POLICY,
        max_heavy_workers=1, retries=0)


def validate_plan(value):
    groups = {d['group_slot'] for d in value['domains']}
    if canonical(value) != canonical(plan(len(groups))):
        raise ValueError('Fixed stage order, scope, denominator or policy changed')
    return value


@dataclass(frozen=True)
class BoundSyntheticInput:
    """Immutable byte snapshot, explicit identity instead of DEV case allowlists.

    Only the built-in mock vocabulary is admitted in this held implementation.
    A production input validator must replace it after review, not loosen it.
    """
    payload: bytes

    @classmethod
    def fixture(cls, domain):
        if canonical(domain) not in {canonical(d) for d in plan()['domains']}:
            raise ValueError('Unknown anonymous synthetic domain slot')
        n = domain['candidate_count']
        value = dict(schema=SCHEMA, synthetic=True, domain=domain,
            query=dict(overhead_s='2', lambda_stop_s='1'),
            sites=[dict(site_id=f'mock-site-{i}', anchor_id=f'mock-anchor-{i}', effects=['C']) for i in range(n)],
            source='builtin-mock-source-v1', runtime='builtin-mock-runtime-v1',
            policy=SEED_POLICY, tree='builtin-mock-tree-v1')
        return cls(canonical(value))

    def value(self):
        value = json.loads(self.payload)
        expected = self.fixture(value['domain']).payload
        if type(self.payload) is not bytes or self.payload != expected:
            raise ValueError('Only exact built-in synthetic immutable input is admitted')
        return value

    @property
    def sha256(self):
        self.value()
        return hashlib.sha256(self.payload).hexdigest()


def depth(query, primary):
    if any(type(v) is not str for v in (query['overhead_s'], query['lambda_stop_s'], primary)):
        raise ValueError('Exact rational string fields required for depth')
    overhead = Fraction(query['overhead_s'])
    denominator = overhead + Fraction(query['lambda_stop_s'])
    primary = Fraction(primary)
    if overhead <= 0 or denominator <= 0 or primary < 0:
        raise ValueError('Positive-overhead depth theorem violated')
    return int(primary // denominator)


def identity(bound, operation, method=None):
    value = bound.value()
    return dict(input_sha256=bound.sha256, domain_id=value['domain']['id'],
        source=value['source'], runtime=value['runtime'], policy=value['policy'],
        tree=value['tree'], operation=operation, method=method)


def admit(value, bound, operation, method=None, common=None):
    """Mock contract admission only; never certifies a physical witness."""
    if operation not in ('prepare', 'search', 'replay', 'ref') or (
        method not in ('flat', 'hier') if operation in ('search', 'replay') else method is not None
    ):
        raise ValueError('Unknown operation or method for slot')
    expected = identity(bound, operation, method)
    if type(value) is not dict or value.get('identity') != expected or value.get('evidence') != 'MOCK_ONLY':
        raise ValueError('Source/runtime/input/method identity drift')
    status = value.get('outcome')
    if operation == 'prepare':
        if status == 'seed_exhausted_unknown':
            if (set(value) != {'identity','evidence','outcome','stream_exhausted','proposals','rejections','feasibility'} or
                value['stream_exhausted'] is not True or value['feasibility'] != 'unknown' or
                type(value['proposals']) is not int or value['proposals'] < 0 or
                type(value['rejections']) is not int or value['proposals'] != value['rejections']):
                raise ValueError('No-seed is not authenticated normal stream exhaustion')
        elif status == 'common_feasible_seed':
            if (value.get('seed') != 'builtin-mock-seed-v1' or canonical(value.get('key')) != canonical(['12','0',0,[]]) or
                type(value.get('hmax')) is not int or value['hmax'] != depth(bound.value()['query'], value['key'][0]) or
                type(value.get('fresh_replays')) is not int or value['fresh_replays'] != 2):
                raise ValueError('Seed/key/depth/double replay mismatch')
        else:
            raise ValueError('Unknown preparation outcome')
    else:
        if common is None or common.get('outcome') != 'common_feasible_seed':
            raise ValueError('Common feasible seed required')
        admit(common, bound, 'prepare')
        if (value.get('common_sha256') != digest(common) or type(value.get('hmax')) is not int or
            value['hmax'] != common['hmax']):
            raise ValueError('Seed or Hmax changed between methods/REF')
        if status not in ('exact_attained','exact_unattained','proven_infeasible','feasible_timeout','unknown'):
            raise ValueError('Untyped outcome')
        if status == 'proven_infeasible':
            raise ValueError('Infeasibility contradicts admitted feasible common seed')
        # This harness intentionally supports only one exact mocked outcome.
        # Other terminal classes are retained but cannot claim exact evidence.
        if status == 'exact_attained' and (canonical(value.get('key')) != canonical(common['key']) or value.get('attained') is not True):
            raise ValueError('Full key/attainment mismatch')
        if operation == 'replay' and (value.get('fresh_process_replay') is not True or status != 'exact_attained'):
            raise ValueError('Fresh mocked replay required')
        if operation == 'ref' and value.get('implementation') != 'independent_mock_ref_no_physical_claim':
            raise ValueError('REF must be explicitly independent and mock-only')
    return value
