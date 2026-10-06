"""Opt-in immutable diagnostic family provenance; not an acceptance checker.

Every node binds the exact output tuple to its ancestry. Selection means the
chosen inherited family, not equality of raw union witness sets. The independent
checker consumes exported primitives and never imports this module.
"""
from __future__ import annotations
from contextvars import ContextVar
from dataclasses import dataclass, replace
from fractions import Fraction
import hashlib
import json


def primitive(value):
    if isinstance(value, Fraction):
        return str(value)
    if isinstance(value, dict):
        return {str(k): primitive(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [primitive(v) for v in value]
    if value is None or type(value) in (str, int, bool):
        return value
    raise TypeError(f"Unserializable provenance value: {type(value).__name__}")


def encoded(value):
    return json.dumps(primitive(value), sort_keys=True, separators=(",", ":"))


def signature(piece):
    d, s = piece.domain, piece.state
    return dict(domain=[str(d.lo), str(d.hi), d.left_closed, d.right_closed],
                m=str(piece.slope), b=str(piece.intercept), chi=piece.chi,
                rho=str(piece.rho), pi=primitive(piece.pi),
                state=[s.anchor, s.remaining_schedule, s.stop_count])


@dataclass(frozen=True)
class FamilyRef:
    node_id: str
    payload: str
    parents: tuple[FamilyRef, ...]

    def check_binding(self, piece):
        if json.loads(self.payload)["output"] != signature(piece):
            raise ValueError("Stale family reference: output changed without provenance")
        if hashlib.sha256(self.payload.encode()).hexdigest() != self.node_id:
            raise ValueError("Tampered immutable family reference")


_active = ContextVar("timecut5_family_recorder", default=None)


class Recorder:
    """Diagnostic context. Disabled by default; no changes to optimization keys."""
    def __init__(self, capture_pieces=False):
        self.nodes = {}
        self.capture_pieces = bool(capture_pieces)
        self.recorded_pieces = {}
        self.batches = []
        self.witness_requests = []
        self._token = None

    def __enter__(self):
        if _active.get() is not None:
            raise ValueError("Nested family recording is unsupported")
        self._token = _active.set(self)
        return self

    def __exit__(self, *exception):
        _active.reset(self._token)
        self._token = None

    def export_witness_requests(self):
        """Actual callback outputs, separate from the immutable mathematical DAG."""
        return [json.loads(row) for row in self.witness_requests]

    def export(self, roots=()):
        roots = tuple(roots)
        refs = []
        for piece in roots:
            ref = piece._family
            if ref is None:
                raise ValueError("Unrecorded root")
            ref.check_binding(piece)
            refs.append(ref.node_id)
        return dict(schema="family5-v1", nodes={k: json.loads(v.payload)
                    for k, v in sorted(self.nodes.items())},
                    batches=[json.loads(v) for v in self.batches],
                    batch_ids=[hashlib.sha256(v.encode()).hexdigest() for v in self.batches],
                    roots=refs)


def _parent_refs(parents):
    result = []
    for p in parents:
        ref = p._family
        if ref is None:
            raise ValueError("Missing inherited family provenance")
        ref.check_binding(p)
        result.append(ref)
    return tuple(result)


def bind(piece, kind, parents=(), **params):
    recorder = _active.get()
    parents = tuple(parents)
    if recorder is None:
        if any(p._family is not None for p in parents):
            raise ValueError("Continue recorded families inside their Recorder context")
        return piece
    refs = _parent_refs(parents)
    if any(r.node_id not in recorder.nodes for r in refs):
        raise ValueError("Parent belongs to a different recording context")
    record = dict(kind=kind, parents=[r.node_id for r in refs],
                  output=signature(piece), params=primitive(params))
    payload = encoded(record)
    ref = FamilyRef(hashlib.sha256(payload.encode()).hexdigest(), payload, refs)
    previous = recorder.nodes.setdefault(ref.node_id, ref)
    if previous.payload != payload:
        raise AssertionError("Family digest collision")
    output = replace(piece, _family=ref)
    if recorder.capture_pieces:
        recorder.recorded_pieces.setdefault(ref.node_id, output)
    return output


def restrict(piece, domain, reason="restriction"):
    if piece.domain.intersect(domain) != domain:
        raise ValueError("A restriction cannot enlarge its parent domain")
    output = replace(piece, domain=domain, _family=None)
    return bind(output, "restrict", (piece,),
                domain=[domain.lo, domain.hi, domain.left_closed, domain.right_closed],
                reason=reason)


def select(piece, parents, domain, chosen, mode):
    output = replace(piece, domain=domain, _family=None)
    return bind(output, "select", parents,
                domain=[domain.lo, domain.hi, domain.left_closed, domain.right_closed],
                chosen=chosen, mode=mode)


def batch(kind, parents, outputs, **params):
    recorder = _active.get()
    if recorder is None:
        return
    ps, os = _parent_refs(tuple(parents)), _parent_refs(tuple(outputs))
    record = dict(kind=kind, parents=[r.node_id for r in ps],
                  outputs=[r.node_id for r in os], params=primitive(params))
    recorder.batches.append(encoded(record))


def witness_dict(witness):
    return dict(time=str(witness.time), energy=str(witness.energy), rho=str(witness.rho),
                pi=primitive(witness.pi), state=[witness.state.anchor,
                    witness.state.remaining_schedule, witness.state.stop_count],
                events=[dict(effect=e.effect, site=e.site,
                    arrival_time=str(e.arrival_time), departure_time=str(e.departure_time),
                    arrival_energy=str(e.arrival_energy), departure_energy=str(e.departure_energy))
                    for e in witness.events])


def guarded_union(output, ordered_parents, guards=None):
    """Bind a fresh coalesced family with first-covering-parent dispatch.

    ``ordered_parents`` must be the exact original callback parents in dispatch
    order. Guard equality is mandatory; callers cannot enlarge an inherited
    parent. This records evidence, while the independent checker verifies the
    connected union and identical scalar/context metadata.
    """
    parents = tuple(ordered_parents)
    if not parents:
        raise ValueError("A guarded union needs an original parent")
    domains = tuple(p.domain for p in parents)
    if guards is not None and tuple(guards) != domains:
        raise ValueError("Guarded-union guards must equal the original parent domains")
    fresh = replace(output, _family=None)
    return bind(fresh, "guarded_union", parents,
                guards=[[d.lo, d.hi, d.left_closed, d.right_closed] for d in domains])


def observe_witness(piece, witness, epsilon, requested_energy):
    """Bind each executed callback result to its original expected FamilyRef."""
    recorder = _active.get()
    if recorder is None:
        return
    ref = piece._family
    if ref is None or ref.node_id not in recorder.nodes:
        raise ValueError("Observed callback has no family in this recorder")
    ref.check_binding(piece)
    record = dict(node_id=ref.node_id,
                  contract=dict(kind="approach", energy=str(requested_energy), epsilon=str(epsilon)),
                  witness=witness_dict(witness))
    recorder.witness_requests.append(encoded(record))
