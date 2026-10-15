"""Experimental tiny table-free exact boundary; no full-table conversion.

The explicit sorted-ID Region policy is NOT original frozen hierarchy replay.
Production loading/native binary provenance is not admitted by this prototype.
"""
from dataclasses import dataclass
from fractions import Fraction as R
import math

from .feasible_incumbent import FeasibleIncumbent, recover_feasible_incumbent, verifier_sources, canonical, sha, _file_sha
from .deployable import _json_object
from .sparse_seed import replay_sparse_seed
from .real_adapter import TableFreeRealProblem, site_catalog_digest
from .road_provider import TableFreeRegionBoundProvider
from .hierarchy import build_regions
from .bounded import _solve_problem
from .hierarchy import _solve_hierarchical_problem

POLICY='sorted_site_ids_binary_split_leaf1_v1'


def _tree(region):
    return [region.identifier,list(region.members),[_tree(c) for c in region.children]]


def experimental_policy(query_bytes,catalog):
    """Freeze before admission. This manifest explicitly permits only tiny fixtures."""
    graph=catalog.provider.graph
    if (graph.node_count>16 or graph.edge_count>128 or
            catalog.provider.router.provenance.get('implementation_kind')!='synthetic_python_fixture_v1'):
        raise ValueError('Only tiny synthetic fixtures are admitted')
    return canonical(dict(schema='hiroute.sparse_feasible_experiment.v1',
        scope='synthetic_tablefree_fixture_only',query_sha256=sha(query_bytes),
        sparse_domain_sha256=catalog.domain_sha256,source_sha256=dict(catalog.provider.source_sha256),
        site_catalog_sha256=site_catalog_digest(catalog.sites),
        candidate_sha256=catalog.candidate_sha256,candidate_ids=sorted(catalog.sites),
        source_hierarchy_reference_sha256=catalog.hierarchy_sha256,
        source_hierarchy_file_verified=False,frozen_hierarchy_equivalence=False,
        region_policy=POLICY,region_tree_sha256=sha(canonical(_tree(build_regions(catalog.sites,leaf_size=1)))),
        mobility_policy='unrestricted',depth_policy='positive_overhead_verified_feasible_incumbent',
        numeric_policy='binary64_totals_as_exact_rationals_v1',
        native_provenance='not_admitted_synthetic_python_router_only',
        code_sha256=verifier_sources(),graph_node_count=graph.node_count,
        graph_edge_count=graph.edge_count,denominator_included=False))


@dataclass(frozen=True)
class SparseFeasibleAdmission:
    incumbent: FeasibleIncumbent
    policy_bytes: bytes
    policy_sha256: str
    status: str='sparse_feasible_incumbent_available'


@dataclass(frozen=True)
class SparseFeasibleSearchResult:
    method: str
    admission: SparseFeasibleAdmission
    bounded: object
    terminal_replayed: bool
    region_policy: str
    landmark_certificate: bytes
    landmark_sha256: str
    initial_witness_cache_sha256: str
    verified_source_runs: int
    final_source_runs: int
    requested_pair_count: int
    status_scope: str='synthetic_sparse_exact_domain_only'


def _check_policy(policy_bytes,expected_policy_sha256,inputs):
    if (type(policy_bytes) is not bytes or sha(policy_bytes)!=expected_policy_sha256 or
            policy_bytes!=experimental_policy(inputs['query_bytes'],inputs['catalog'])):
        raise ValueError('Frozen experimental source/query/Region policy mismatch')
    # The external immutable snapshot digest remains a separate mandatory input.
    for key,source in [('nodes_path','nodes'),('edges_path','edges'),('router_source_path','router')]:
        if _file_sha(inputs[key])!=inputs['catalog'].provider.source_sha256[source]:
            raise ValueError('Source bytes changed before search')
    if verifier_sources()!=dict(inputs['approved_verifier_sha256']):
        raise ValueError('Approved transitive implementation closure changed')


def admit_sparse_feasible(*,recovery_inputs,policy_bytes,expected_policy_sha256):
    _check_policy(policy_bytes,expected_policy_sha256,recovery_inputs)
    incumbent=recover_feasible_incumbent(**recovery_inputs)
    _check_policy(policy_bytes,expected_policy_sha256,recovery_inputs)
    return SparseFeasibleAdmission(incumbent,policy_bytes,expected_policy_sha256)


def solve_sparse_with_feasible_incumbent(admission,*,method,recovery_inputs,
        expected_policy_sha256,router_factory):
    """Freshly admit, build the real table-free bound, execute one isolated method.

    Supply a fresh provider per invocation. Each starts empty and performs the
    same witness-only prewarming, charged to that method. No search/OPEN cache
    is resumed or shared. No heuristic is called and no verified seed dict is
    fabricated. The original completed-seed launcher is untouched.
    """
    if type(admission) is not SparseFeasibleAdmission or method not in ('flat','hier'):
        raise ValueError('Distinct sparse feasible admission and recognized method required')
    fresh=admit_sparse_feasible(recovery_inputs=recovery_inputs,
        policy_bytes=admission.policy_bytes,expected_policy_sha256=expected_policy_sha256)
    if fresh!=admission:
        raise ValueError('Sparse feasible admission failed fresh boundary replay')
    catalog=recovery_inputs['catalog'];provider=catalog.provider
    policy=_json_object(admission.policy_bytes)
    initial=sha(canonical(sorted((a,b,str(leg.time),str(leg.actual_length),provider.edge_witnesses[a,b])
                                 for (a,b),leg in provider.legs.items())))
    verified_runs=provider.source_run_count
    root=build_regions(catalog.sites,leaf_size=1)
    if sha(canonical(_tree(root)))!=policy['region_tree_sha256']:
        raise ValueError('Constructed Region tree differs from explicit policy')
    bound=TableFreeRegionBoundProvider(provider,catalog.sites,root,
        destination_anchor=catalog.destination_anchor,landmark_anchor=catalog.origin_anchor,
        site_catalog_sha256=catalog.site_catalog_sha256,router_factory=router_factory)
    certificate=_json_object(bound.landmark_certificate)
    labels={name:[None if math.isinf(bound.landmarks[0].from_landmark[name]) else bound.landmarks[0].from_landmark[name],
                  None if math.isinf(bound.landmarks[0].to_landmark[name]) else bound.landmarks[0].to_landmark[name]]
            for name in sorted(provider.anchor_nodes)}
    if (sha(bound.landmark_certificate)!=bound.landmark_sha256 or
            certificate.get('anchor_labels')!=labels or
            certificate.get('graph_nodes_sha256')!=provider.source_sha256['nodes'] or
            certificate.get('graph_edges_sha256')!=provider.source_sha256['edges'] or
            certificate.get('router_source_sha256')!=provider.source_sha256['router'] or
            certificate.get('root_anchor')!=catalog.origin_anchor):
        raise ValueError('Landmark certificate/labels/source identity changed')
    _check_policy(admission.policy_bytes,expected_policy_sha256,recovery_inputs)
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
    _check_policy(admission.policy_bytes,expected_policy_sha256,recovery_inputs)
    return SparseFeasibleSearchResult(method,admission,bounded,witness is not None,POLICY,
        bound.landmark_certificate,bound.landmark_sha256,initial,verified_runs,
        provider.source_run_count,len(provider.legs))
