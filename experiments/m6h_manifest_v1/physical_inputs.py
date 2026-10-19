"""Exact bound physical input contract; no DEV membership or implicit defaults.

Pure validators operate on already supplied objects. Opening/creating real inputs
remains held until root reviews the complete source/selection/protocol freeze.
"""
from fractions import Fraction as F
import re
from .contract import canonical, digest

INPUT_NAMES = ('nodes.parquet','edges.parquet','metadata.json','queries.json','pools.json','hierarchy.json')
ROOT_FREEZE_STATUS = 'pending_root_protocol_source_freeze'
SCHEMA = 'hiroute.m6h.physical.v1'
PHYSICAL = dict(start_time_s='0',capacity_kwh='60',minimum_energy_kwh='0',reserve_kwh='6',
    consumption_kwh_per_m='1/6250',overhead_s='300',lambda_stop_s='600',
    charging_segments=[['0','30','36','0'],['30','48','60','-720'],['48','60','120','-3600']])


class InvalidGraphInput(ValueError):
    """Authenticated graph bytes violate the physical graph schema, not identity."""


def require_root_freeze():
    # Source-reviewed release must replace this guard after full freeze review.
    # Approval of the proposal does not by itself authenticate generated inputs.
    from .recovery_runtime import require_active
    return require_active()


def sha(value):
    if type(value) is not str or re.fullmatch('[0-9a-f]{64}',value) is None:
        raise ValueError('Expected lowercase SHA256')
    return value


def rational(value, *, nonnegative=False):
    if type(value) is not str:
        raise ValueError('Exact canonical rational string required')
    try:
        parsed=F(value)
    except (ValueError,ZeroDivisionError) as exc:
        raise ValueError('Invalid rational') from exc
    if str(parsed)!=value or nonnegative and parsed<0:
        raise ValueError('Noncanonical or negative rational')
    return parsed


def validate_binding(spec, case_id, count, hierarchy_sha256):
    """Validate source-supplied domain including ordered prefix and physical model."""
    from timecut5.real_adapter import site_catalog_digest
    from timecut5.real_legs import RealSite
    if (type(spec) is not dict or set(spec)!={'case_id','candidate_count','original_binding','original_pool_prefix'} or
        type(count) is not int or count not in (8,32,128) or type(spec['candidate_count']) is not int or
        spec['candidate_count']!=count or type(spec['case_id']) is not str or spec['case_id']!=f'{case_id}:N{count}'):
        raise ValueError('Explicit domain binding required')
    binding=spec['original_binding'];prefix=spec['original_pool_prefix']
    if type(binding) is not dict or set(binding)!={'query','query_sha256','candidate_site_ids','candidate_sha256',
        'site_catalog_sha256','anchor_catalog_sha256','sparse_domain_sha256'}:
        raise ValueError('Complete physical identity binding required')
    query=binding['query']
    expected_query={'case_id','origin','destination','H_ref',*PHYSICAL,'initial_energy_kwh','schedule',
                    'hierarchy_sha256','sparse_domain_sha256'}
    if type(query) is not dict or set(query)!=expected_query or query['case_id']!=case_id:
        raise ValueError('Exact physical query fields/case identity required')
    for key,value in PHYSICAL.items():
        if canonical(query[key])!=canonical(value):
            raise ValueError('Approved physical template differs: '+key)
    if query['initial_energy_kwh'] not in ('18','228/5') or count==8 and query['initial_energy_kwh']!='18':
        raise ValueError('Approved SOC domain differs')
    if type(query['H_ref']) is not int or query['H_ref']!=4:
        raise ValueError('Input H_ref placeholder must stay 4; execution uses seed-derived full depth')
    schedule=query['schedule']
    if type(schedule) is not dict or set(schedule)!={'a','b','D'} or schedule['D']!='2700':
        raise ValueError('Scheduled physical template required')
    a=rational(schedule['a'],nonnegative=True);b=rational(schedule['b'],nonnegative=True)
    if a<=0 or b*4!=a*7:
        raise ValueError('Direct-road-based scheduled window ratio differs')
    # The direct selected-fastest baseline itself is authenticated separately
    # against the query-row provenance in extract_case; ratio alone is insufficient.
    if type(prefix) is not list or len(prefix)!=count:
        raise ValueError('Candidate shortage is a retained failure, never a smaller domain')
    sites={};ids=[]
    for record in prefix:
        if type(record) is not dict or not {'site_id','anchor_id','effects'}<=set(record):
            raise ValueError('Site physical record missing')
        sid=record['site_id'];anchor=record['anchor_id'];effects=record['effects']
        if (type(sid) is not str or not sid or sid in sites or type(anchor) is not str or
            re.fullmatch(r'road:[0-9]+',anchor) is None or effects not in (['C'],['S'],['C','S','CS'])):
            raise ValueError('Duplicate Site identity, invalid anchor or effects')
        if anchor in (query['origin'],query['destination']):
            raise ValueError('Candidate collides with endpoint anchor')
        sites[sid]=RealSite(sid,anchor,tuple(effects));ids.append(sid)
    for endpoint in ('origin','destination'):
        if type(query[endpoint]) is not str or re.fullmatch(r'road:[0-9]+',query[endpoint]) is None:
            raise ValueError('Invalid endpoint anchor')
    if query['origin']==query['destination']:
        raise ValueError('Zero OD domain')
    if (canonical(binding['candidate_site_ids'])!=canonical(ids) or
        binding['query_sha256']!=digest(query) or binding['candidate_sha256']!=digest(sorted(ids)) or
        binding['site_catalog_sha256']!=site_catalog_digest(sites) or
        query['hierarchy_sha256']!=hierarchy_sha256 or binding['sparse_domain_sha256']!=query['sparse_domain_sha256']):
        raise ValueError('Query/candidate/Site/hierarchy identity differs')
    anchors=list(dict.fromkeys([query['origin']]+[s.anchor_id for s in sites.values()]+[query['destination']]))
    if binding['anchor_catalog_sha256']!=digest({a:int(a.removeprefix('road:')) for a in anchors}):
        raise ValueError('Anchor catalog differs')
    for key in ('query_sha256','candidate_sha256','site_catalog_sha256','anchor_catalog_sha256','sparse_domain_sha256'):
        sha(binding[key])
    sha(hierarchy_sha256)
    return spec


def spec_for(manifest,case_id):
    if manifest.get('case_id')!=case_id or type(case_id) is not str or not case_id:
        raise ValueError('Manifest case differs')
    return validate_binding(manifest['case_binding'],case_id,manifest['candidate_count'],
                            manifest['inputs']['hierarchy.json']['sha256'])


def validate_manifest_contract(manifest):
    """Exact per-domain manifest; no extra mutable policy fields admitted."""
    from .physical_domain import CONFIGS,COMPLETION_POLICY,PENDING_WINDOW_POLICY,POST_SERVICE_POLICY,ANALYTIC_POLICY,METHOD_POLICY
    from experiments.dev_cohort_v1.domain import shared_configuration
    from experiments.mechanism_recovery_v1.run import CACHE_POLICY
    from .physical import LIMITS
    fields={'schema','launchable','status','case_id','candidate_count','case_binding','selection_sha256',
        'protocol_sha256','method_order','domain_ordinal','shared_configuration','arms','pending_window_policy',
        'post_service_policy','analytic_charge_policy','completion_policy','method_policy','limits','cache_policy',
        'inputs','repo','input_directory','compiler','source'}
    if type(manifest) is not dict or set(manifest)!=fields or manifest['schema']!=SCHEMA:
        raise ValueError('M6-H manifest schema/fields differ')
    if manifest['launchable'] is not True or manifest['status']!='frozen_m6h_domain_not_launched':
        raise ValueError('Manifest not frozen')
    sha(manifest['selection_sha256']);sha(manifest['protocol_sha256'])
    ordinal=manifest['domain_ordinal']
    if type(ordinal) is not int or not 0<=ordinal<30 or manifest['method_order']!=(['flat','hier'] if ordinal%2==0 else ['hier','flat']):
        raise ValueError('Predetermined alternating order differs')
    for key,expected in dict(shared_configuration=shared_configuration(False),arms=CONFIGS,
        pending_window_policy=PENDING_WINDOW_POLICY,post_service_policy=POST_SERVICE_POLICY,
        analytic_charge_policy=ANALYTIC_POLICY,completion_policy=COMPLETION_POLICY,method_policy=METHOD_POLICY,
        limits=LIMITS,cache_policy=CACHE_POLICY).items():
        if canonical(manifest[key])!=canonical(expected):raise ValueError('Frozen policy differs: '+key)
    inputs=manifest['inputs']
    if type(inputs) is not dict or set(inputs)!=set(INPUT_NAMES):
        raise ValueError('Exact six-file input closure required')
    for name,binding in inputs.items():
        if type(binding) is not dict or set(binding)!={'size','sha256'} or type(binding['size']) is not int or binding['size']<=0:
            raise ValueError('Invalid input identity: '+name)
        sha(binding['sha256'])
    spec_for(manifest,manifest['case_id'])
    for name in ('repo','input_directory'):
        if type(manifest[name]) is not str or not manifest[name].startswith('/'):
            raise ValueError('Absolute physical source/input directory required')
    if type(manifest['source']) is not dict or type(manifest['compiler']) is not dict:
        raise ValueError('Complete executable source/runtime closure required')
    return manifest


INPUT_FAILURE_REASONS = frozenset(('INSUFFICIENT_CAPABLE_SITES','INSUFFICIENT_CAPABILITY_AT_FIRST_RADIUS',
    'CAPABILITY_EXHAUSTED','INVALID_ANCHOR','INVALID_NUMERIC','INVALID_WINDOW','DUPLICATE_SITE_ID',
    'MISSING_SITE','HIERARCHY_COVERAGE','INVALID_INPUT'))


def validate_input_failure(value,domain,ordinal):
    """Pre-search frozen failure record, never a result-dependent replacement."""
    fields={'schema','status','domain_id','domain_ordinal','case_id','candidate_count','method_order',
        'selection_sha256','protocol_sha256','reason_code','failure_stage','solver_invoked','replacement',
        'inputs','source','compiler','repo','input_directory'}
    if (type(value) is not dict or set(value)!=fields or value['schema']!='hiroute.m6h.input_failure.v1' or
        value['status']!='FAILED_INPUT' or value['domain_id']!=domain['id'] or
        type(value['domain_ordinal']) is not int or value['domain_ordinal']!=ordinal or
        type(value['candidate_count']) is not int or value['candidate_count']!=domain['candidate_count'] or
        value['method_order']!=domain['method_order'] or type(value['case_id']) is not str or not value['case_id'] or
        value['reason_code'] not in INPUT_FAILURE_REASONS or value['failure_stage']!='input_generation' or
        value['solver_invoked'] is not False or value['replacement'] is not False):
        raise ValueError('Invalid frozen generation-stage input failure')
    sha(value['selection_sha256']);sha(value['protocol_sha256'])
    inputs=value['inputs']
    if type(inputs) is not dict or set(inputs)!=set(INPUT_NAMES):raise ValueError('Failed domain requires same six-file source closure')
    for item in inputs.values():
        if type(item) is not dict or set(item)!={'size','sha256'} or type(item['size']) is not int or item['size']<=0:
            raise ValueError('Failed input byte identity malformed')
        sha(item['sha256'])
    if type(value['source']) is not dict or type(value['compiler']) is not dict:
        raise ValueError('Failed input runtime/source closure missing')
    if any(type(value[k]) is not str or not value[k].startswith('/') for k in ('repo','input_directory')):
        raise ValueError('Failed input must bind absolute source locations')
    return value
