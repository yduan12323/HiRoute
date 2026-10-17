"""Opt-in completed-layer reconstruction envelope; no mid-layer resume or gap.

Replays from the ORIGINAL seed and charges all reconstruction. Exact callable
witness lifts are regenerated, never deserialized from piece signatures. The
trusted caller must bind actual input bytes and bound-provider policy/config to
binding_supplier; independent physical verification uses verifier_factory.
"""
from fractions import Fraction as R
import hashlib
import json
import os
from pathlib import Path
import tempfile

from .bounded import _solve_problem, prefix_primary_lower_bound
from .hierarchy import _solve_hierarchical_problem
from .durable_incumbent import AtomicIncumbentStore, load_verified, _binding, _decode
from .live_replay import source_manifest
from .provenance import encoded, primitive, signature, witness_dict

SCHEMA = 'hiroute.completed_layer_envelope.v2'
COALESCING_VERSION = 'exact-adjacent-cut-coalescing-v1'


def _bytes(value):
    return encoded(value).encode()


def _hash(value):
    return hashlib.sha256(_bytes(value)).hexdigest()


def _root(root):
    return None if root is None else dict(identifier=root.identifier,
        members=list(root.members), children=[_root(c) for c in root.children])


class LayerEnvelopeStop(Exception):
    def __init__(self, data):
        self.checkpoint_bytes = data
        super().__init__('Stopped at a verified complete-layer boundary')


def _atomic(path, data):
    temporary = None
    try:
        fd, temporary = tempfile.mkstemp(prefix='.'+path.name+'.', dir=path.parent)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path); temporary = None
        directory = os.open(path.parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        if temporary is not None:
            os.unlink(temporary)


class _Envelope:
    def __init__(self, *, problem, verifier_factory, binding_supplier, initial_witness,
                 method, path, config, previous_checkpoint, stop_after_depth):
        self.problem, self.method = problem, method
        self.path = Path(path)
        if self.path.exists():
            raise FileExistsError(self.path)
        self.binding_supplier, self.verifier_factory = binding_supplier, verifier_factory
        self.binding = _binding(binding_supplier())
        self.search_sources = source_manifest()
        self.stop_after_depth = stop_after_depth
        self.failed = False
        self.history = []
        self.expected = None
        self.replayed_layers = 0
        self.store = AtomicIncumbentStore(self.path.with_name(self.path.name+'.incumbent'),
            method=method, problem_factory=verifier_factory, binding_supplier=binding_supplier)
        from .bounded import _replay_problem
        seed_key = _replay_problem(verifier_factory(), initial_witness)
        if initial_witness.state.stop_count > problem.bound:
            raise ValueError('Initial witness outside unchanged H_ref')
        self.store(initial_witness, seed_key)
        self.seed_key = seed_key
        self.header = dict(schema=SCHEMA, binding=self.binding,
            search_source_sha256=self.search_sources, config=config,
            initial_seed=dict(witness=witness_dict(initial_witness), lex_key=primitive(seed_key)),
            reconstruction='original_seed_same_source_full_replay_charged',
            complete=False, status='incomplete_boundary_evidence')
        if previous_checkpoint is not None:
            saved = _decode(previous_checkpoint)
            if (type(saved) is not dict or set(saved) != {'header','history','state'} or
                    _bytes(saved['header']) != _bytes(self.header) or type(saved['history']) is not list or
                    not saved['history'] or any(type(h) is not str or len(h)!=64 or
                        any(c not in '0123456789abcdef' for c in h) for h in saved['history']) or
                    _bytes(saved) != previous_checkpoint or
                    _hash(saved['state']) != saved['history'][-1]):
                raise ValueError('Checkpoint schema, source, domain, policy or digest mismatch')
            self.expected = saved

    def candidate(self, witness, key):
        if self.failed:
            raise RuntimeError('Failed envelope session cannot be reused')
        try:
            if witness.state.stop_count > self.problem.bound:
                raise ValueError('Incumbent outside unchanged H_ref')
            self.store(witness, key)
        except BaseException:
            self.failed = True
            raise

    def __call__(self, depth, layer, terminals, incumbent, counters):
        if self.failed:
            raise RuntimeError('Failed envelope session cannot be reused')
        try:
            self._checkpoint(depth, layer, terminals, incumbent, counters)
        except LayerEnvelopeStop:
            raise
        except BaseException:
            self.failed = True
            raise

    def _checkpoint(self, depth, layer, terminals, incumbent, counters):
        if (type(depth) is not int or depth != len(self.history) or
                not 0 <= depth <= self.problem.bound):
            raise ValueError('Discontinuous layer depth')
        if _binding(self.binding_supplier()) != self.binding or source_manifest() != self.search_sources:
            raise ValueError('Current domain/source changed')
        for group in layer:
            if not group or any(p.state != group[0].state for p in group):
                raise ValueError('Frontier group must have one homogeneous state')
            if group[0].state.stop_count != depth:
                raise ValueError('Frontier depth differs from layer depth')
        # The durable store is a separate feasible recovery artifact. Embed a
        # verified copy, not a mutable pathname, in the atomic layer generation.
        before = self.store.path.read_bytes()
        witness, key = load_verified(self.store.path, problem_factory=self.verifier_factory,
                                    binding_supplier=self.binding_supplier)
        if self.store.path.read_bytes() != before:
            raise ValueError('Concurrent incumbent mutation')
        if witness.state.stop_count > self.problem.bound:
            raise ValueError('Saved incumbent outside unchanged H_ref')
        engine_j = (incumbent if self.method == 'flat' else
                    None if incumbent[0] is None else incumbent[0][0])
        effective = min(v for v in (self.seed_key[0], engine_j) if v is not None)
        if key[0] > effective:
            raise ValueError('Saved incumbent does not cover historical pruning thresholds')
        open_l = min((prefix_primary_lower_bound(self.problem, g) for g in layer), default=None)
        term_l = min((prefix_primary_lower_bound(self.problem, (p,)) for p in terminals), default=None)
        lower = min(v for v in (key[0], open_l, term_l) if v is not None)
        engine = (primitive(incumbent) if self.method == 'flat' else
            dict(key=primitive(incumbent[0]), witness=None if incumbent[1] is None else witness_dict(incumbent[1])))
        state = dict(depth=depth, H_ref=self.problem.bound,
            frontier=[[signature(p) for p in g] for g in layer],
            terminals=[signature(p) for p in terminals], counters=primitive(counters),
            engine_incumbent=engine, feasible_incumbent=_decode(before),
            lower_bounds=primitive(dict(open_suffix_primary=open_l,
                saved_terminal_relaxation_primary=term_l, bounded_domain_conservative_primary=lower)),
            bound_contract='primary_only_complete_layer_no_gap_no_attainment_claim')
        self.history.append(_hash(state))
        if self.expected is not None and depth < len(self.expected['history']):
            if self.history[-1] != self.expected['history'][depth]:
                raise ValueError('Reconstructed layer descriptor or incumbent differs')
            if depth == len(self.expected['history'])-1 and state != self.expected['state']:
                raise ValueError('Reconstructed final envelope differs')
            self.replayed_layers += 1
        data = _bytes(dict(header=self.header, history=self.history, state=state))
        # Do not publish a purported restored checkpoint until the full saved
        # boundary has been reconstructed and compared.
        if self.expected is None or depth >= len(self.expected['history'])-1:
            _atomic(self.path, data)
        if self.stop_after_depth == depth:
            if self.expected is not None and self.replayed_layers < len(self.expected['history']):
                raise ValueError('Cannot stop before saved reconstruction boundary')
            raise LayerEnvelopeStop(data)

    def finish(self):
        if self.expected is not None and self.replayed_layers != len(self.expected['history']):
            raise ValueError('Search ended before saved reconstruction boundary')


def run_layer_envelope(*, problem_factory, verifier_factory, binding_supplier,
                       initial_witness, method, output_path, bound_policy_sha256,
                       root=None, bound_provider=None, singleton_bound=None,
                       dominance=True, coalescing=False, previous_checkpoint=None, stop_after_depth=None):
    """Run unchanged exact engines with an atomic last-complete-layer envelope.

    The caller binds actual policies and transitive inputs, not saved hashes.
    A new output destination is mandatory. No restored descriptor is used for
    pruning. Completion is returned by the solver, never inferred from a file.
    Coalescing requires the unrecorded table_free_problem(coalescing=True)
    adapter. Recovery replays all work from the original seed, including reducer
    and native provider work; it is not warm or arbitrary mid-layer recovery.
    """
    if (method not in ('flat','hier') or type(dominance) is not bool or
            type(coalescing) is not bool):
        raise ValueError('Invalid exact method/policy')
    if (type(bound_policy_sha256) is not str or len(bound_policy_sha256)!=64 or
            any(c not in '0123456789abcdef' for c in bound_policy_sha256)):
        raise ValueError('Explicit bound policy digest required')
    if stop_after_depth is not None and (type(stop_after_depth) is not int or stop_after_depth < 0):
        raise ValueError('Invalid layer stop')
    if (method=='hier' and (root is None or singleton_bound is not None) or
            method=='flat' and (root is not None or bound_provider is not None)):
        raise ValueError('Method-specific bound configuration required')
    problem = problem_factory()
    from . import coalesced_solver, coalesce
    if coalescing:
        if (type(problem) is not coalesced_solver._TableFreeProblem or
                problem._record_lineage is not False or
                coalesced_solver.VERSION != COALESCING_VERSION or
                coalesce.VERSION != COALESCING_VERSION or
                getattr(problem.reduce, '__func__', None) is not coalesced_solver._Coalescing.reduce):
            raise ValueError('Coalescing requires the supported unrecorded table-free adapter/version')
    elif isinstance(problem, coalesced_solver._Coalescing):
        raise ValueError('Coalescing adapter requires explicit coalescing=True')
    config = dict(method=method, dominance=dominance, H_ref=problem.bound,
        coalescing=coalescing, representation_version=COALESCING_VERSION if coalescing else None,
        root=_root(root), bound_policy_sha256=bound_policy_sha256,
        indexed_region=bound_provider is not None, singleton_bound=singleton_bound is not None)
    hook = _Envelope(problem=problem, verifier_factory=verifier_factory,
        binding_supplier=binding_supplier, initial_witness=initial_witness,
        method=method, path=output_path, config=config, previous_checkpoint=previous_checkpoint,
        stop_after_depth=stop_after_depth)
    kwargs = dict(verified_primary_upper=hook.seed_key[0],
                  checkpoint_hook=hook, incumbent_hook=hook.candidate)
    if coalescing:
        kwargs['reducer'] = problem.reduce
    if method=='flat':
        return _solve_problem(problem, dominance, singleton_bound=singleton_bound, **kwargs)
    return _solve_hierarchical_problem(problem, dominance, root,
                                      bound_provider=bound_provider, **kwargs).bounded
