"""Opt-in durable feasible witnesses, never a search checkpoint or optimality proof.

The caller supplies a fresh independent physical problem factory and a binding
supplier recomputed from the admitted source/query/domain bytes. No saved label,
frontier, incumbent scalar, or claimed objective is trusted during recovery.
Persistence is synchronous and fail-closed: any validation or I/O failure
propagates to the caller. A previously committed file remains usable; a failure
after rename may have committed the new file, so recovery must verify it.
"""
from fractions import Fraction as R
import hashlib
import json
import os
from pathlib import Path
import tempfile

from .bounded import _replay_problem
from .probe import Event, State, Witness
from .provenance import encoded, primitive, witness_dict

SCHEMA = 'hiroute.durable_feasible_witness.v1'


def _binding(value):
    if type(value) is not dict or set(value) != {'domain_sha256', 'source_sha256'}:
        raise ValueError('Explicit domain and source binding required')
    sources = value['source_sha256']
    if type(sources) is not dict or not sources:
        raise ValueError('Nonempty source binding required')
    for digest in [value['domain_sha256'], *sources.values()]:
        if type(digest) is not str or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('Canonical SHA256 binding required')
    if any(type(k) is not str or not k for k in sources):
        raise ValueError('Named source bindings required')
    return json.loads(encoded(value))


def _decode(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate JSON field')
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=pairs)


def _witness(value):
    if type(value) is not dict or set(value) != {'time','energy','rho','pi','state','events'}:
        raise ValueError('Malformed witness')
    def rational(v):
        if type(v) is not str or str(R(v)) != v:
            raise ValueError('Canonical exact rational required')
        return R(v)
    if (type(value['state']) is not list or len(value['state']) != 3 or
            type(value['state'][0]) is not str or
            any(type(v) is not int for v in value['state'][1:]) or type(value['pi']) is not list or
            any(type(p) is not list or len(p) != 2 or any(type(x) is not str for x in p)
                for p in value['pi']) or type(value['events']) is not list):
        raise ValueError('Malformed discrete witness')
    events=[]
    for event in value['events']:
        if type(event) is not dict or set(event) != {'effect','site','arrival_time','departure_time','arrival_energy','departure_energy'}:
            raise ValueError('Malformed event')
        if type(event['effect']) is not str or type(event['site']) is not str:
            raise ValueError('Malformed event identity')
        events.append(Event(event['effect'],event['site'],*(rational(event[k]) for k in
            ('arrival_time','departure_time','arrival_energy','departure_energy'))))
    return Witness(*(rational(value[k]) for k in ('time','energy','rho')),
        tuple(map(tuple,value['pi'])),State(*value['state']),tuple(events))


def load_verified(path, *, problem_factory, binding_supplier):
    """Recover only feasible route evidence, using fresh independent replay.

    SHA256 detects corruption, not authenticity. The trusted binding supplier
    must hash the actual admitted domain (including query, candidates, H_ref,
    numeric/route policies) and transitive source inputs, not copy this record.
    """
    expected=_binding(binding_supplier())
    record=_decode(Path(path).read_bytes())
    if type(record) is not dict or set(record) != {'payload','sha256'}:
        raise ValueError('Malformed durable record')
    payload=record['payload']
    if hashlib.sha256(encoded(payload).encode()).hexdigest()!=record['sha256']:
        raise ValueError('Durable record digest mismatch')
    if (type(payload) is not dict or set(payload) != {'schema','binding','method','status','witness','lex_key'} or
            payload['schema']!=SCHEMA or payload['status']!='feasible_only' or
            payload['method'] not in ('flat','hier') or payload['binding']!=expected):
        raise ValueError('Durable record schema/domain/source mismatch')
    witness=_witness(payload['witness'])
    key=_replay_problem(problem_factory(),witness)
    if encoded(key)!=encoded(payload['lex_key']) or _binding(binding_supplier())!=expected:
        raise ValueError('Replay key or current binding mismatch')
    return witness,key


class AtomicIncumbentStore:
    """One writer per file. Fresh invocation refuses an existing destination.

    Only lexicographically improving candidates are written. A caller wanting
    restart must first load_verified, then create a new run destination.
    No directory creation, background thread, swallowed failure, or async queue.
    """
    def __init__(self,path,*,method,problem_factory,binding_supplier):
        if method not in ('flat','hier'):
            raise ValueError('Unknown exact method')
        self.path=Path(path)
        if self.path.exists():
            raise FileExistsError(self.path)
        self.method=method
        self.problem_factory=problem_factory
        self.binding_supplier=binding_supplier
        self.binding=_binding(binding_supplier())
        self.best_key=None
        self.writes=0
        self._failed=False

    def __call__(self,witness,key):
        if self._failed:
            raise RuntimeError('Persistence failed; independently recover into a new run destination')
        if _binding(self.binding_supplier())!=self.binding:
            raise ValueError('Current domain/source changed')
        # This replay is independent of the solver that emitted the candidate.
        replayed=_replay_problem(self.problem_factory(),witness)
        if replayed!=key or _binding(self.binding_supplier())!=self.binding:
            raise ValueError('Candidate key or current domain/source mismatch')
        if self.best_key is not None and key>=self.best_key:
            return
        payload=dict(schema=SCHEMA,binding=self.binding,method=self.method,
                     status='feasible_only',witness=witness_dict(witness),lex_key=primitive(key))
        data=encoded(dict(payload=payload,sha256=hashlib.sha256(encoded(payload).encode()).hexdigest())).encode()
        temporary=None
        try:
            fd,temporary=tempfile.mkstemp(prefix='.'+self.path.name+'.',dir=self.path.parent)
            with os.fdopen(fd,'wb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary,self.path)
            temporary=None
            directory=os.open(self.path.parent,os.O_RDONLY | getattr(os,'O_DIRECTORY',0))
            try: os.fsync(directory)
            finally: os.close(directory)
        except BaseException:
            self._failed=True
            raise
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except BaseException:
                    self._failed=True
                    raise
        self.best_key=key
        self.writes+=1
