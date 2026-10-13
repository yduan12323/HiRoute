"""Separate sparse feasible-bound receipt; deliberately not a solver certificate.

The caller must freshly load the graph using the approved loader after checking
its source bytes, as required by TableFreeRoadSelectedLegProvider. This API
rechecks files, code, catalog bindings, native selected paths and physics. It
never upgrades an interrupted stream to a completed heuristic minimum.
"""
from dataclasses import dataclass, field
from fractions import Fraction as R
import hashlib
import inspect
import json
from pathlib import Path

from . import sparse_seed, road_provider, real_adapter, real_legs, deployable
from .deployable import _json_object


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def _file_sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def verifier_sources():
    """Inventory only: approval must come from a separately reviewed manifest."""
    from validation.reference5 import model
    # Include transitive local helpers (notably probe.exact), not just the
    # immediate replay entrypoint. Standard-library/runtime trust is external.
    paths = {"timecut5." + p.stem: p for p in Path(__file__).parent.glob("*.py")}
    paths[model.__name__] = Path(inspect.getsourcefile(model))
    return {name: _file_sha(path) for name, path in paths.items()}


@dataclass(frozen=True)
class FeasibleIncumbent:
    query_bytes: bytes
    checkpoint_sha256: str
    domain_sha256: str
    source_sha256: tuple
    verifier_sha256: tuple
    witness_bytes: bytes
    witness_sha256: str
    primary_upper: R
    max_depth: int
    status: str = field(default='feasible_incumbent_available', init=False)
    heuristic_minimum_claimed: bool = field(default=False, init=False)
    exact_optimum_claimed: bool = field(default=False, init=False)
    exact_solver_admitted: bool = field(default=False, init=False)


def recover_feasible_incumbent(checkpoint_path, *, expected_checkpoint_sha256,
        query_bytes, catalog, nodes_path, edges_path, router_source_path, approved_verifier_sha256):
    """Recover only a complete atomic snapshot, and independently reverify it.

    snapshot.json can describe an INCOMPLETE run; complete means whole durable
    checkpoint bytes, not completed generation. Never read the journal or tmp.
    Expected checkpoint digest must be frozen by the caller before recovery.
    A new, unused provider is mandatory; cached feasibility is not evidence.
    Return value is not accepted by solve_deployable_pair. Do not cast it.
    """
    path = Path(checkpoint_path)
    if path.name != 'snapshot.json' or type(query_bytes) is not bytes:
        raise ValueError('Atomic snapshot.json and immutable query bytes required')
    data = path.read_bytes()
    if sha(data) != expected_checkpoint_sha256:
        raise ValueError('Checkpoint digest mismatch')
    snap, query = _json_object(data), _json_object(query_bytes)
    if (snap.get('schema') != 'hiroute.streaming_seed_diagnostic.v1' or
            snap.get('exact_optimum_claimed') is not False or
            snap.get('solver_started') is not False or
            snap.get('denominator_included') is not False):
        raise ValueError('Unsupported checkpoint provenance or claims')
    provider = catalog.provider
    if (not isinstance(catalog, sparse_seed.SparseSeedCatalog) or
            provider.source_run_count != 0 or provider.legs or
            provider.edge_witnesses or provider._source_labels):
        raise ValueError('Fresh unused source-bound catalog required')
    source = dict(provider.source_sha256)
    approved = dict(approved_verifier_sha256)
    def recheck():
        if (verifier_sources() != approved or
                _file_sha(nodes_path) != source['nodes'] or
                _file_sha(edges_path) != source['edges'] or
                _file_sha(router_source_path) != source['router'] or
                dict(provider.source_sha256) != source):
            raise ValueError('Source or approved verifier closure mismatch')
        if (sha(canonical(provider.anchor_nodes)) != source['anchors'] or
                real_adapter.site_catalog_digest(catalog.sites) != catalog.site_catalog_sha256 or
                sha(canonical(sorted(catalog.sites))) != catalog.candidate_sha256 or
                sparse_seed.sparse_domain_digest(source, catalog.site_catalog_sha256,
                    catalog.candidate_sha256, catalog.hierarchy_sha256,
                    catalog.origin_anchor, catalog.destination_anchor) != catalog.domain_sha256):
            raise ValueError('Mutable catalog binding mismatch')
    recheck()
    if (snap.get('canonical_query_sha256') != sha(canonical(query)) or
            snap.get('domain_sha256') != catalog.domain_sha256 or
            snap.get('source_sha256') != source or
            snap.get('graph_node_count') != provider.graph.node_count):
        raise ValueError('Frozen query/source/domain mismatch')
    sparse_seed.validate_sparse_query(query, catalog)
    inc = snap.get('provisional_incumbent')
    if not isinstance(inc, dict) or inc.get('status') != 'replayed_feasible_incumbent':
        raise ValueError('No durable feasible witness')
    sequence, charges, paths = inc.get('sequence'), inc.get('charges'), inc.get('edge_witnesses')
    if (type(sequence) is not list or any(type(s) is not list or len(s) != 2 or
            any(type(x) is not str for x in s) for s in sequence) or
            type(charges) is not list or any(type(x) not in (str, int) for x in charges) or
            type(paths) is not list or len(paths) != len(sequence) + 1 or
            any(type(p) is not list or any(type(e) is not int or e < 0 for e in p) for p in paths)):
        raise ValueError('Incomplete or malformed durable witness')
    # This starts with empty caches, routes under the same declared native
    # policy, then independently checks every edge and the physical schedule.
    fresh = sparse_seed.replay_sparse_seed(query, catalog, sequence, charges)
    if (canonical(fresh['lex_key']) != canonical(inc.get('lex_key')) or
            canonical(fresh['edge_witnesses']) != canonical(paths)):
        raise ValueError('Fresh physical/selected-edge witness disagreement')
    j = fresh['lex_key'][0]
    overhead, penalty = R(query['overhead_s']), R(query['lambda_stop_s'])
    if overhead <= 0 or penalty < 0 or j < 0:
        raise ValueError('Positive-overhead nonnegative-cost depth theorem required')
    depth = j // (overhead + penalty)  # equality depth is INCLUDED
    if len(sequence) > depth:
        raise ValueError('Witness contradicts certified depth')
    recheck()
    witness = canonical(dict(sequence=sequence, charges=[str(R(x)) for x in charges],
                             edge_witnesses=paths, lex_key=fresh['lex_key']))
    return FeasibleIncumbent(query_bytes, sha(data), catalog.domain_sha256,
        tuple(sorted(source.items())), tuple(sorted(approved.items())), witness,
        sha(witness), j, depth)


def reverify_feasible_incumbent(receipt, **recovery_inputs):
    """Boundary revalidation; never trust editable or deserialized U_J/Hmax."""
    if type(receipt) is not FeasibleIncumbent:
        raise ValueError('Separate feasible-incumbent receipt required')
    fresh = recover_feasible_incumbent(**recovery_inputs)
    if fresh != receipt:
        raise ValueError('Feasible incumbent failed boundary revalidation')
    return fresh
