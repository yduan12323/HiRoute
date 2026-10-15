"""Production-only feasible admission. Does not modify synthetic admission APIs."""
from dataclasses import dataclass
from fractions import Fraction as R
from pathlib import Path
import math,json
from timecut5.feasible_incumbent import recover_feasible_incumbent,canonical,sha,_file_sha,verifier_sources
from timecut5.sparse_feasible_execution import POLICY,_tree
from timecut5.deployable import _json_object
from timecut5.sparse_seed import replay_sparse_seed
from timecut5.real_adapter import TableFreeRealProblem,site_catalog_digest
from timecut5.road_provider import TableFreeRegionBoundProvider
from timecut5.hierarchy import build_regions,_solve_hierarchical_problem
from timecut5.bounded import _solve_problem

@dataclass(frozen=True)
class ProductionAdmission:
    incumbent: object
    policy_bytes: bytes
    policy_sha256: str

def runtime_policy(inputs,spec,native):
    catalog=inputs['catalog'];p=catalog.provider;g=p.graph
    if (g.node_count!=5892498 or g.edge_count!=11561067 or len(catalog.sites)!=128 or
        p.router.provenance.get('implementation_kind')=='synthetic_python_fixture_v1'):
        raise ValueError('Only the explicitly frozen production graph and N128 domain are admitted')
    b=spec['domain_binding']
    for key,value in [('sparse_domain_sha256',catalog.domain_sha256),('site_catalog_sha256',site_catalog_digest(catalog.sites)),('candidate_sha256',catalog.candidate_sha256),('query_sha256',sha(inputs['query_bytes']))]:
        if b[key]!=value:raise ValueError('Production domain mismatch: '+key)
    if (catalog.hierarchy_sha256!=spec['hierarchy_sha256'] or
        _file_sha(spec['hierarchy_absolute_path'])!=spec['hierarchy_sha256'] or
        p.source_sha256!=spec['provider_source_sha256'] or
        _file_sha(native['binary_path'])!=native['binary_sha256'] or
        str(Path(native['binary_path']).resolve()) not in Path('/proc/self/maps').read_text() or
        _file_sha(spec['compiler_path'])!=spec['compiler_sha256'] or
        native['source_sha256']!=p.source_sha256['router']):
        raise ValueError('Production hierarchy/source/native chain differs')
    for key,source in [('nodes_path','nodes'),('edges_path','edges'),('router_source_path','router')]:
        if _file_sha(inputs[key])!=p.source_sha256[source]:raise ValueError('Production input changed')
    if verifier_sources()!=dict(inputs['approved_verifier_sha256']):raise ValueError('Verifier closure differs')
    region=sha(canonical(_tree(build_regions(catalog.sites,leaf_size=1))))
    if region!=spec['region_tree_sha256']:raise ValueError('Actual Region tree differs')
    return canonical(dict(schema='hiroute.production_sparse_feasible_policy.v1',region_policy=POLICY,region_tree_sha256=region,source_hierarchy_sha256=catalog.hierarchy_sha256,source_hierarchy_file_verified=True,frozen_hierarchy_equivalence=False,native=native,domain_binding=b,source_sha256=p.source_sha256,query_sha256=sha(inputs['query_bytes']),numeric_policy='binary64_totals_as_exact_rationals_v1',mobility_policy='unrestricted',denominator_included=False))

def run_production(*,inputs,spec,native,method,router_factory,stage,save,closure_check,landmark_only=False):
    if method not in ('flat','hier'):raise ValueError('Unknown method')
    policy=runtime_policy(inputs,spec,native)
    incumbent=recover_feasible_incumbent(**inputs)
    admission=ProductionAdmission(incumbent,policy,sha(policy))
    catalog=inputs['catalog'];provider=catalog.provider
    if (provider.source_run_count!=3 or len(provider.legs)!=3 or
        str(incumbent.primary_upper)!=spec['initial_upper_bound'] or incumbent.max_depth!=37):raise ValueError('Witness initial state differs')
    initial=sha(canonical(sorted((a,b,str(leg.time),str(leg.actual_length),provider.edge_witnesses[a,b]) for (a,b),leg in provider.legs.items())))
    save('feasible_incumbent.json',dict(status=incumbent.status,primary_upper=str(incumbent.primary_upper),max_depth=incumbent.max_depth,witness=json.loads(incumbent.witness_bytes),initial_witness_cache_sha256=initial,policy_sha256=admission.policy_sha256,exact_optimum_claimed=False))
    save('runtime_policy.json',json.loads(policy))
    stage('fresh_three_leg_witness_verified',source_runs=provider.source_run_count,initial_witness_cache_sha256=initial)
    root=build_regions(catalog.sites,leaf_size=1)
    stage('region_policy_tree_verified',region_tree_sha256=spec['region_tree_sha256'])
    stage('landmark_preparation_started')
    bound=TableFreeRegionBoundProvider(provider,catalog.sites,root,destination_anchor=catalog.destination_anchor,landmark_anchor=catalog.origin_anchor,site_catalog_sha256=catalog.site_catalog_sha256,router_factory=router_factory)
    certificate=_json_object(bound.landmark_certificate)
    labels={name:[None if math.isinf(bound.landmarks[0].from_landmark[name]) else bound.landmarks[0].from_landmark[name],None if math.isinf(bound.landmarks[0].to_landmark[name]) else bound.landmarks[0].to_landmark[name]] for name in sorted(provider.anchor_nodes)}
    if (sha(bound.landmark_certificate)!=bound.landmark_sha256 or certificate.get('anchor_labels')!=labels or certificate.get('graph_nodes_sha256')!=provider.source_sha256['nodes'] or certificate.get('graph_edges_sha256')!=provider.source_sha256['edges'] or certificate.get('router_source_sha256')!=provider.source_sha256['router'] or certificate.get('root_anchor')!=catalog.origin_anchor):raise ValueError('Landmark certificate differs')
    save('landmark_certificate.json',certificate)
    stage('landmark_edge_inequalities_verified_certificate_saved',landmark_sha256=bound.landmark_sha256)
    closure_check()
    if runtime_policy(inputs,spec,native)!=policy:raise ValueError('Production policy changed')
    if landmark_only:return dict(status='landmark_verified_exact_not_started',landmark_sha256=bound.landmark_sha256,initial_witness_cache_sha256=initial)
    def policy_check():
        closure_check()
        if runtime_policy(inputs,spec,native)!=policy:raise ValueError('Post-terminal production policy changed')
    return _execute_admitted(admission=admission,catalog=catalog,provider=provider,bound=bound,root=root,method=method,initial=initial,spec=spec,stage=stage,policy_check=policy_check)

def _execute_admitted(*,admission,catalog,provider,bound,root,method,initial,spec,stage,policy_check):
    """Shared exact/terminal algorithm, separately unit-tested with tiny fixtures."""
    stage('exact_engine_started',method=method)
    query=_json_object(admission.incumbent.query_bytes)
    exact_query=dict(query,H_ref=admission.incumbent.max_depth)
    problem=TableFreeRealProblem(exact_query,catalog.sites,provider,
        origin_anchor=query['origin'],destination_anchor=query['destination'],
        site_catalog_sha256=catalog.site_catalog_sha256)
    solved=(_solve_problem(problem,verified_primary_upper=admission.incumbent.primary_upper,
            singleton_bound=bound.singleton_bound) if method=='flat' else
        _solve_hierarchical_problem(problem,True,root,
            verified_primary_upper=admission.incumbent.primary_upper,bound_provider=bound))
    bounded=solved if method=='flat' else solved.bounded
    stage('exact_engine_returned',method=method)
    result=bounded.result;witness=result.witness
    saved_key=_json_object(admission.incumbent.witness_bytes)['lex_key']
    incumbent_key=(R(saved_key[0]),R(saved_key[1]),saved_key[2],tuple(map(tuple,saved_key[3])))
    if result.status=='attained_optimum':
        if (witness is None or type(result.key) is not tuple or len(result.key)!=4 or
                type(result.key[0]) is not R or type(result.key[1]) is not R or
                type(result.key[2]) is not int or type(result.key[3]) is not tuple or
                result.key>incumbent_key):
            raise ValueError('Malformed attained or incumbent-contradicting terminal')
    elif result.status=='infimum_unattained':
        if (witness is not None or result.key is not None or
                result.unattained_component not in ('J','Q') or
                (result.unattained_component=='J' and result.secondary_infimum is not None) or
                type(result.primary_infimum) is not R or
                not 0<=result.primary_infimum<=admission.incumbent.primary_upper or
                (result.unattained_component=='Q' and
                 (type(result.secondary_infimum) is not R or result.secondary_infimum<0))):
            raise ValueError('Malformed unattained terminal')
        if (result.unattained_component=='J' and result.primary_infimum>=incumbent_key[0] or
                result.unattained_component=='Q' and result.primary_infimum==incumbent_key[0] and
                result.secondary_infimum>=incumbent_key[1]):
            raise ValueError('Unattained terminal contradicts attained incumbent coordinates')
    else:
        raise ValueError('Verified feasible incumbent contradicts infeasible or unknown terminal')
    if witness is not None:
        charges=tuple(e.departure_energy-e.arrival_energy for e in witness.events if e.effect in ('C','CS'))
        replay=replay_sparse_seed(exact_query,catalog,witness.pi,charges)
        if replay['lex_key']!=result.key:
            raise ValueError('Independent full-depth terminal physical replay differs')
    policy_check()
    stage('terminal_physics_and_source_checks_completed',method=method)
    return dict(status=result.status,key=result.key,primary_infimum=result.primary_infimum,secondary_infimum=result.secondary_infimum,unattained_component=result.unattained_component,initial_witness_cache_sha256=initial,landmark_sha256=bound.landmark_sha256,region_tree_sha256=spec['region_tree_sha256'],source_runs=provider.source_run_count,requested_pairs=len(provider.legs),terminal_replayed=witness is not None)
