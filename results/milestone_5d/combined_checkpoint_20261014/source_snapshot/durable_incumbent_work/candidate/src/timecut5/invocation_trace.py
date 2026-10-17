"""Opt-in deterministic HIER execution trace; validation lives independently.

Content family IDs describe mathematical cuts. Exact integer invocation/group
IDs describe occurrences, so repeated equivalent support cannot hide a skipped
call. Disabled tracing leaves the underlying implementation/results unchanged.
"""
from contextvars import ContextVar
import hashlib
import json
from . import provenance

_active=ContextVar('timecut5_invocation_trace',default=None)


class InvocationTrace:
    def __init__(self,recorder,representation=None):
        if representation not in (None,'exact-adjacent-cut-coalescing-v1'):
            raise ValueError('Unsupported recorded representation')
        self.recorder=recorder
        self.representation=representation
        self.coalescings=0
        self.events=[]
        self.invocations=0
        self.groups=0
        self.last_invocation_id=None
        self._token=None

    def __enter__(self):
        if _active.get() is not None or provenance._active.get() is not self.recorder:
            raise ValueError('Invocation trace requires its own active family Recorder')
        self._token=_active.set(self)
        return self

    def __exit__(self,*error):
        _active.reset(self._token);self._token=None

    def emit(self,kind,payload):
        seq=len(self.events)
        self.events.append(provenance.encoded(dict(seq=seq,kind=kind,payload=payload)))
        return seq

    def export(self):
        value=dict(schema='family5-hier-trace-v1',events=[json.loads(e) for e in self.events])
        if self.representation is not None:
            value.update(schema='family5-hier-trace-v2',representation=self.representation)
        return value


def require_coalescing_context():
    trace=_active.get()
    if (trace is None or trace.representation!='exact-adjacent-cut-coalescing-v1'
            or provenance._active.get() is not trace.recorder):
        raise ValueError('Recorded coalescing requires its active v2 trace and family Recorder')
    return trace


def record_coalescing(parents,outputs):
    trace=require_coalescing_context()
    position=len(trace.recorder.batches)
    trace.emit('coalesce',dict(coalescing_id=trace.coalescings,
        input_families=family_ids(parents),output_families=family_ids(outputs),
        input_guards=[provenance.signature(piece)['domain'] for piece in parents],
        batch_range=[position,position]))
    trace.coalescings+=1


def family_id(piece):
    trace=_active.get()
    if trace is None:return None
    ref=piece._family
    if ref is None or ref.node_id not in trace.recorder.nodes:
        raise ValueError('Invocation contains a foreign or missing family')
    ref.check_binding(piece)
    return ref.node_id


def family_ids(pieces):return [family_id(p) for p in pieces]


def emit(kind,**payload):
    trace=_active.get()
    return None if trace is None else trace.emit(kind,payload)


def invoke(operation,parents,params,function):
    trace=_active.get()
    if trace is None:return function()
    before=len(trace.recorder.batches)
    inputs=family_ids(parents)
    output=function()
    invocation_id=trace.invocations;trace.invocations+=1
    trace.last_invocation_id=invocation_id
    trace.emit('invoke',dict(invocation_id=invocation_id,operation=operation,
               input_families=inputs,output_families=family_ids(output),params=params,
               batch_range=[before,len(trace.recorder.batches)]))
    return output


def last_invocation():
    trace=_active.get()
    return None if trace is None else trace.last_invocation_id


def start_run(problem,dominance,root,incumbent):
    trace=_active.get()
    if trace is None:return
    if incumbent is not None:
        raise ValueError('First trace pilot does not support external incumbents')
    if trace.events:
        raise ValueError('One solver run per invocation trace')
    def region(node):
        return dict(id=node.identifier,members=list(node.members),children=[region(c) for c in node.children])
    emit('run_start',case_sha256=hashlib.sha256(provenance.encoded(problem.case).encode()).hexdigest(),
         dominance=dominance,H_ref=problem.bound,regions=region(root))


def start_layer(depth,layer):
    trace=_active.get()
    if trace is None:return [None for _ in layer]
    groups=[]
    for pieces in layer:
        groups.append(dict(group_id=trace.groups,families=family_ids(pieces)));trace.groups+=1
    emit('layer_start',depth=depth,groups=groups)
    return [g['group_id'] for g in groups]


def last_witness_family(witness):
    trace=_active.get()
    if trace is None or witness is None:return None
    if not trace.recorder.witness_requests:
        raise ValueError('Terminal witness lacks an observed original family')
    request=json.loads(trace.recorder.witness_requests[-1])
    if provenance.encoded(request['witness'])!=provenance.encoded(provenance.witness_dict(witness)):
        raise ValueError('Last observed callback is not the terminal witness')
    return request['node_id']
