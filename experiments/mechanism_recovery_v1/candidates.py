"""Recovered OD07 candidate proposal for a *new* mechanism experiment.

This module does not load a graph, launch search, or admit a seed. The caller
must authenticate the immutable loaded graph/native implementation and supply
an unused router. A successful receipt still requires fresh physical replay.
"""
from pathlib import Path
import hashlib
import json

from timecut5.frozen_candidate_catalog import build_catalog
from timecut5.portable_candidate_policy import (
    build_portable_domain, canonical, digest, ProposalStatus,
)
from timecut5.portable_candidate_binding import derive_binding
from timecut5.real_adapter import site_catalog_digest
from timecut5.real_legs import RealSite, TIE_POLICY
from timecut5.sparse_seed import sparse_domain_digest

CASE_ID = 'OD07_energy_and_scheduled_soc3_10'
CATALOG_FILES = {
    'sites': 'stop_sites.parquet',
    'pools': 'pools.json',
    'geo': 'geographic_screen_v5_grid14.json',
    'slate': 'fixed_12od_candidate_slate.json',
}
RECOVERED_SHA256 = {
    'stop_sites.parquet': 'e3e7d6d6667f7ab684ff83eb2646920516b01aef2e6ceb8170c689e71f6afd38',
    'geographic_screen_v5_grid14.json': 'eab8a107f31a6a966cf2a1f215f832494511ffa694da4532186ac025b232784f',
    'fixed_12od_candidate_slate.json': '68917b71ff74cc13a4f35d2b7c7fb7ca577e572295c2d091bb0a0957a3789b95',
}
EXPECTED_COUNTS = dict(baseline=128, eligible_chargers=641,
                       unique_eligible_anchors=442, added=21, total=149)
CAP = 256


def _hash_file(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _check_files(directory, bindings):
    """Authenticate metadata only; graph authentication belongs to the caller."""
    names = set(CATALOG_FILES.values()) | {'queries.json', 'hierarchy.json'}
    for name in sorted(names):
        identity = bindings.get(name)
        path = Path(directory) / name
        if (not isinstance(identity, dict) or set(identity) != {'size', 'sha256'}
                or path.stat().st_size != identity['size']
                or _hash_file(path) != identity['sha256']):
            raise ValueError('Recovered candidate input identity mismatch: ' + name)
        if name in RECOVERED_SHA256 and identity['sha256'] != RECOVERED_SHA256[name]:
            raise ValueError('Recovered catalog differs from pinned source: ' + name)
    return ({key: Path(directory) / name for key, name in CATALOG_FILES.items()},
            {key: bindings[name]['sha256'] for key, name in CATALOG_FILES.items()})


def _complete_proposal(graph, fresh_router, query, baseline_rows, eligible,
                       eligibility, catalog_sources, provider_sources):
    """Use the public complete-union policy, never a nearest/prefix shortcut."""
    bound = dict(
        source_sha256=provider_sources, catalog_source_sha256=catalog_sources,
        baseline_domain_sha256=query['sparse_domain_sha256'],
        baseline_candidate_sha256=digest(canonical(sorted(r['site_id'] for r in baseline_rows))),
        baseline_sites_sha256=digest(canonical(baseline_rows)),
        eligible_catalog_sha256=digest(canonical(eligible)),
        eligibility_sha256=digest(canonical(eligibility)),
        query_sha256=digest(canonical(query)),
        native_provenance_sha256=digest(canonical(fresh_router.provenance)),
    )
    proposal = build_portable_domain(
        graph=graph, router=fresh_router, baseline_sites=baseline_rows,
        eligible_charging_sites=eligible, eligibility=eligibility,
        query=query, bindings=bound, cap=CAP,
    )
    payload = proposal.as_dict()
    if proposal.status is not ProposalStatus.PROPOSED_COMPLETE:
        raise ValueError('OD07 complete candidate proposal failed: '
                         + payload['reason_code'] + ': ' + payload['reason'])
    # Check completeness independently against every returned anchor verdict.
    verdicts = {v['anchor_node']: v for v in payload['anchor_verdicts']}
    if set(verdicts) != {r['access_node'] for r in eligible}:
        raise ValueError('OD07 selected-leg verdict coverage differs')
    baseline_ids = {r['site_id'] for r in baseline_rows}
    all_added = sorted(r['site_id'] for r in eligible
                       if r['site_id'] not in baseline_ids
                       and verdicts[r['access_node']]['minimum_floor_pass'])
    if payload['added_ids'] != all_added:
        raise ValueError('OD07 complete added set differs')
    if any(payload['counts'].get(k) != v for k, v in EXPECTED_COUNTS.items()):
        raise ValueError('OD07 recovered validation target differs: '
                         + json.dumps(payload['counts'], sort_keys=True))
    derived = derive_binding(
        proposal=proposal, expected_payload_sha256=digest(proposal.payload_bytes),
        baseline_query=query, baseline_sites=baseline_rows,
        baseline_provider_sources=provider_sources,
    )
    return payload, derived


def repair_od07(directory, bindings, graph, fresh_router, baseline_query,
                baseline_sites, provider_sources):
    """Return unchanged physical query, baseline-first sites, and proposal receipt.

    ``bindings`` contains filename -> {size, sha256}, including the six frozen
    inputs and three recovered catalog sources. ``baseline_sites`` is the
    original insertion-ordered RealSite dictionary. Provider sources bind the current authenticated native source and legacy
    graph/anchor/tie keys, before any new terminal-policy binding. The original
    domain is independently authenticated before runtime-only rebinding.
    No historical run is relabeled, and 149 is a validation target, never a cap.
    """
    paths, expected = _check_files(directory, bindings)
    root = Path(directory)
    query_document = json.loads((root / 'queries.json').read_bytes())
    rows = query_document['queries']
    matches = [r for r in rows if r['query_id'] == CASE_ID]
    if len(matches) != 1:
        raise ValueError('OD07 frozen query identity is ambiguous')
    frozen = matches[0]['bindings']['128']
    pools = json.loads(paths['pools'].read_bytes())['pools']
    matches = [p for p in pools if p['od_id'] == 'OD07']
    if len(matches) != 1:
        raise ValueError('OD07 original pool identity is ambiguous')
    baseline_rows = matches[0]['sites'][:128]
    original_sites = {r['site_id']: RealSite(r['site_id'], r['anchor_id'], tuple(r['effects']))
                      for r in baseline_rows}
    if (len(original_sites) != EXPECTED_COUNTS['baseline']
            or list(original_sites) != list(baseline_sites)
            or original_sites != baseline_sites
            or baseline_query != frozen['query']
            or baseline_query['case_id'] != CASE_ID
            or baseline_query['hierarchy_sha256'] != bindings['hierarchy.json']['sha256']
            or list(original_sites) != frozen['candidate_site_ids']
            or digest(canonical(sorted(original_sites))) != frozen['candidate_sha256']
            or site_catalog_digest(original_sites) != frozen['site_catalog_sha256']
            or digest(canonical(baseline_query)) != frozen['query_sha256']):
        raise ValueError('OD07 original query, candidate order, or site semantics differ')
    for key, name in (('nodes', 'nodes.parquet'), ('edges', 'edges.parquet')):
        if provider_sources.get(key) != bindings[name]['sha256']:
            raise ValueError('OD07 loaded graph source binding differs: ' + key)
    historical_sources = query_document['source_sha256']
    for key, name in (('graph_nodes', 'nodes.parquet'), ('graph_edges', 'edges.parquet'),
                      ('hierarchy', 'hierarchy.json'), ('pools', 'pools.json')):
        if historical_sources.get(key) != bindings[name]['sha256']:
            raise ValueError('OD07 historical source identity differs: ' + key)
    anchors = {a: int(a.removeprefix('road:')) for a in dict.fromkeys(
        [baseline_query['origin']] + [r['anchor_id'] for r in baseline_rows]
        + [baseline_query['destination']])}
    anchor_sha = digest(canonical(anchors))
    if anchor_sha != frozen['anchor_catalog_sha256']:
        raise ValueError('OD07 historical anchor catalog differs')
    old_sources = dict(nodes=historical_sources['graph_nodes'],
                       edges=historical_sources['graph_edges'],
                       router=historical_sources['router_cpp'], anchors=anchor_sha,
                       tie_policy=digest(TIE_POLICY.encode()))
    original_domain = sparse_domain_digest(
        old_sources, site_catalog_digest(original_sites), frozen['candidate_sha256'],
        baseline_query['hierarchy_sha256'], baseline_query['origin'], baseline_query['destination'],
    )
    if (original_domain != baseline_query['sparse_domain_sha256']
            or original_domain != frozen['sparse_domain_sha256']):
        raise ValueError('OD07 historical provider/domain identity differs')
    # Only native source identity may differ in this baseline transition. Energy
    # and explicit-role settlement identities are bound later by the caller.
    current_sources = dict(old_sources, router=fresh_router.provenance['source_sha256'])
    if provider_sources != current_sources:
        raise ValueError('OD07 current provider/domain identity differs')
    native_provenance = json.loads(canonical(fresh_router.provenance))
    native_artifact = json.loads(canonical(getattr(fresh_router, 'artifact', None)))
    if getattr(fresh_router, 'role', None) is not None:
        fresh_router.verify_artifact()
        if not isinstance(native_artifact, dict) or not native_artifact.get('artifact_identity_sha256'):
            raise ValueError('OD07 current native artifact identity missing')
    runtime_query = dict(baseline_query, sparse_domain_sha256=sparse_domain_digest(
        current_sources, site_catalog_digest(original_sites), frozen['candidate_sha256'],
        baseline_query['hierarchy_sha256'], baseline_query['origin'], baseline_query['destination']))
    eligible, eligibility = build_catalog(
        paths=paths, expected=expected, od_id='OD07', query=runtime_query,
        baseline_sites=baseline_rows,
    )
    if (len(eligible) != EXPECTED_COUNTS['eligible_chargers']
            or len({r['access_node'] for r in eligible}) != EXPECTED_COUNTS['unique_eligible_anchors']):
        raise ValueError('OD07 complete recovered catalog count differs')
    payload, derived = _complete_proposal(
        graph, fresh_router, runtime_query, baseline_rows, eligible,
        eligibility, expected, provider_sources,
    )
    by_id = {r['site_id']: r for r in derived['sites']}
    order = list(original_sites) + payload['added_ids']
    sites = {sid: RealSite(sid, by_id[sid]['anchor_id'], tuple(by_id[sid]['effects']))
             for sid in order}
    if set(sites) != set(derived['candidate_site_ids']):
        raise ValueError('OD07 insertion order lost candidate membership')
    _check_files(directory, bindings)
    if getattr(fresh_router, 'role', None) is not None:
        fresh_router.verify_artifact()
    if (fresh_router.provenance != native_provenance
            or getattr(fresh_router, 'artifact', None) != native_artifact):
        raise ValueError('OD07 current native identity changed during repair')
    receipt = dict(
        schema='hiroute.mechanism_recovery_candidate_receipt.v1',
        experiment_kind='new_recovered_full_catalog_initial_reachability_repair',
        historical_result_reused=False, launchable=False,
        runtime_admission_complete=False, fresh_physical_seed_replay_required=True,
        source_sha256=expected, eligibility=eligibility,
        historical_baseline_query=baseline_query,
        historical_baseline_query_sha256=digest(canonical(baseline_query)),
        historical_provider_sources=old_sources,
        historical_query_source_manifest=historical_sources,
        runtime_baseline_query=runtime_query,
        runtime_baseline_query_sha256=digest(canonical(runtime_query)),
        runtime_provider_sources=current_sources,
        runtime_native_provenance=native_provenance,
        runtime_native_provenance_sha256=digest(canonical(native_provenance)),
        runtime_native_artifact=native_artifact,
        runtime_native_artifact_sha256=digest(canonical(native_artifact)),
        baseline_rebinding_fields=['sparse_domain_sha256'],
        proposal=payload, binding=derived, insertion_order=order,
        insertion_order_sha256=digest(canonical(order)),
        candidate_set_sha256=derived['candidate_sha256'],
        insertion_order_policy='original_baseline_then_sorted_complete_additions',
        historical_149_insertion_order_authenticated=False,
        baseline_insertion_order=list(original_sites),
        hierarchy_sha256=baseline_query['hierarchy_sha256'],
        hierarchy_policy='restrict_original_topology_preserving_region_ids',
    )
    return derived['query'], sites, receipt
