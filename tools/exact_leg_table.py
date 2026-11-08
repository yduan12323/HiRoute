"""Independent exact input representation and grounded lookup, not an optimizer.

Structural/time consistency is necessary, not proof of real-road selection.
No production optimizer, routing or lower-bound module is imported.
"""
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
import re
from types import MappingProxyType

SCHEMA='hiroute.exact_selected_leg_table.v1'
NUMERICAL='exact_rational_inputs_v1'
SELECTION='positive_time_node_path_edge_path_tie_v1'


def number(value):
    if type(value) is int:return Fraction(value)
    if type(value) is str and re.fullmatch(r'-?(?:0|[1-9][0-9]*)(?:/[1-9][0-9]*)?',value):
        return Fraction(value)
    raise TypeError('exact integer/rational string required')


def identity(value):
    if type(value) is not str or not value.strip():raise ValueError('literal nonempty identity required')
    return value


def sequence(value,field):
    if not isinstance(value,(list,tuple)):
        raise TypeError(field+' requires an explicit array, never a string/object iteration')
    return tuple(value)


def unique(pairs):
    result={}
    for k,v in pairs:
        if k in result:raise ValueError('duplicate JSON key')
        result[k]=v
    return result


@dataclass(frozen=True)
class Pair:
    source: str
    target: str
    reachable: bool
    time: Fraction | None
    length: Fraction | None
    nodes: tuple
    edges: tuple


@dataclass(frozen=True,init=False)
class ExactLegTable:
    origin_anchor: str
    destination_anchor: str
    candidate_order: tuple
    aliases: object
    capabilities: object
    sources: tuple
    targets: tuple
    pairs: object
    graph_identity: str
    payload_sha256: str
    road_selection_certified: bool=False
    _validated: bool=False
    _owner: object=None

    @classmethod
    def from_bytes(cls,data,check=None):
        if type(data) is not bytes:raise TypeError('input bytes required')
        payload=json.loads(data,object_pairs_hook=unique,
                           parse_constant=lambda x:(_ for _ in ()).throw(ValueError('nonfinite JSON')))
        result=cls.from_dict(payload,check=check)
        # Raw byte provenance is computed here, never caller-supplied.
        object.__setattr__(result,'payload_sha256',hashlib.sha256(data).hexdigest())
        return result

    @classmethod
    def from_dict(cls,payload,check=None):
        if not isinstance(payload,dict):raise TypeError('table requires an object')
        def records():yield from sequence(payload['pairs'],'pairs')
        result=cls._from_records(payload,records(),check=check)
        digest=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
        object.__setattr__(result,'payload_sha256',digest)
        return result

    @classmethod
    def _from_records(cls,payload,records,check=None,pair_factory=Pair,edge_endpoints=None):
        """Internal streaming validation; identity is derived, never supplied."""
        if not isinstance(payload,dict):raise TypeError('table requires an object')
        if (payload.get('schema')!=SCHEMA or payload.get('numerical_contract')!=NUMERICAL or
                payload.get('selected_leg_contract')!=SELECTION):
            raise ValueError('incompatible table/numerical/selected-leg contract')
        if payload.get('road_selection_certified') is not False:
            raise ValueError('self-declared certification is not an independent road certificate')
        origin,destination=map(identity,(payload['origin_anchor'],payload['destination_anchor']))
        graph=identity(payload['graph_identity']);order=sequence(payload['candidate_order'],'candidate_order')
        if len(set(order))!=len(order):raise ValueError('duplicate Site identity')
        sites=payload['sites']
        if not isinstance(sites,dict):raise TypeError('sites requires an object')
        if set(order)!=set(sites):raise ValueError('candidate/capability domain mismatch')
        aliases={};capabilities={}
        for site in order:
            identity(site);record=sites[site]
            if not isinstance(record,dict):raise TypeError('Site record requires an object')
            aliases[site]=identity(record['anchor'])
            effects=sequence(record['effects'],'effects')
            if not effects or len(set(effects))!=len(effects) or not set(effects)<={'C','S','CS'}:
                raise ValueError('invalid effect set')
            capabilities[site]=effects
        sources=tuple(sorted({origin,*aliases.values()}));targets=tuple(sorted({destination,*aliases.values()}))
        required={(s,t) for s in sources for t in targets};pairs={}
        if edge_endpoints is None:edge_endpoints={}
        semantic=hashlib.sha256()
        semantic.update(json.dumps({k:v for k,v in payload.items() if k!='pairs'},sort_keys=True,separators=(',',':'),allow_nan=False).encode())
        for i,record in enumerate(records):
            if check is not None and i%128==0:check()
            if not isinstance(record,dict):raise TypeError('pair record requires an object')
            s,t=identity(record['source']),identity(record['target']);key=(s,t)
            if key not in required or key in pairs:raise ValueError('unexpected/duplicate physical pair')
            reach=record['reachable']
            if type(reach) is not bool:raise TypeError('literal reachable boolean required')
            nodes=sequence(record['nodes'],'nodes');edges=sequence(record['edges'],'edges')
            for x in (*nodes,*edges):identity(x)
            if not reach:
                if record['time_s'] is not None or record['actual_length_m'] is not None or nodes or edges or s==t:
                    raise ValueError('unreachable is not zero/alias or a partial path')
                time=length=None
            else:
                time,length=number(record['time_s']),number(record['actual_length_m'])
                if s==t:
                    if time!=0 or length!=0 or nodes!=(s,) or edges:
                        raise ValueError('coincident anchors require the exact zero leg')
                elif (time<=0 or length<=0 or len(nodes)<2 or nodes[0]!=s or nodes[-1]!=t
                      or len(edges)!=len(nodes)-1 or len(set(nodes))!=len(nodes)):
                    raise ValueError('invalid positive simple selected path')
                for edge,u,v in zip(edges,nodes,nodes[1:]):
                    prior=edge_endpoints.get(edge)
                    if prior is not None and prior!=(u,v):
                        raise ValueError('edge identity has inconsistent endpoints')
                    if prior is None:edge_endpoints[edge]=(u,v)
            pairs[key]=pair_factory(s,t,reach,time,length,nodes,edges)
            for token in json.JSONEncoder(sort_keys=True,separators=(',',':'),allow_nan=False).iterencode(record):
                semantic.update(token.encode('utf-8'))
        if set(pairs)!=required:raise ValueError('missing physical pair, not implicit unreachable')
        # Necessary directed reachability/time consistency only. Selected LENGTH
        # need not satisfy a triangle inequality and is never rerouted here.
        work=0
        for mid in set(aliases.values()):
            for s in sources:
                first=pairs[s,mid]
                if not first.reachable:continue
                for t in targets:
                    work+=1
                    if check is not None and work%1024==0:check()
                    second=pairs[mid,t]
                    if second.reachable:
                        direct=pairs[s,t]
                        if not direct.reachable or direct.time>first.time+second.time:
                            raise ValueError('inconsistent directed reachability/shortest time')
        payload_sha256=semantic.hexdigest()
        result=object.__new__(cls)
        values=dict(origin_anchor=origin,destination_anchor=destination,candidate_order=order,
            aliases=MappingProxyType(aliases),capabilities=MappingProxyType(capabilities),
            sources=sources,targets=targets,pairs=MappingProxyType(pairs),graph_identity=graph,
            payload_sha256=payload_sha256,road_selection_certified=False,_validated=True,_owner=object())
        for name,value in values.items():object.__setattr__(result,name,value)
        return result

    @property
    def actions(self):return tuple(sorted((s,e) for s in self.candidate_order for e in self.capabilities[s]))

    def literal_plan_legs(self,plan,remaining_activity):
        if type(remaining_activity) is not int or remaining_activity not in (0,1):
            raise ValueError('pending activity state')
        current=self.origin_anchor;legs=[]
        for site,effect in plan:
            if site not in self.capabilities or effect not in self.capabilities[site]:
                raise ValueError('illegal literal Site/effect')
            if effect in ('S','CS'):
                if not remaining_activity:raise ValueError('activity already completed')
                remaining_activity=0
            pair=self.pairs[current,self.aliases[site]]
            if not pair.reachable:raise ValueError('declared unreachable input pair')
            legs.append(pair);current=self.aliases[site]
        if remaining_activity:raise ValueError('activity still pending')
        pair=self.pairs[current,self.destination_anchor]
        if not pair.reachable:raise ValueError('declared unreachable terminal pair')
        return tuple(legs)+(pair,)


@dataclass(frozen=True)
class GroundedLeg:
    guard: object
    time: object
    length: object


@dataclass(frozen=True)
class SlotTrace:
    table_owner: object
    table_sha256: str
    choices: tuple
    constraints: tuple
    legs: tuple
    terminal: GroundedLeg
    actions: tuple
    charging: tuple
    service: tuple
    stop_count: object


class GroundedLookup:
    """Shared finite arrays. Outside values cannot enter a guarded transition."""
    def __init__(self,table,check=None):
        import z3
        if not isinstance(table,ExactLegTable) or not getattr(table,'_validated',False):
            raise TypeError('use the exact table parser before constructing lookups')
        self.z3,self.table=z3,table
        self.source_index={a:i for i,a in enumerate(table.sources)}
        self.target_index={a:i for i,a in enumerate(table.targets)}
        self.width=len(table.targets)
        self.T=z3.K(z3.IntSort(),z3.RealVal(0));self.L=z3.K(z3.IntSort(),z3.RealVal(0))
        self.R=z3.K(z3.IntSort(),z3.BoolVal(False))
        for n,((s,t),pair) in enumerate(table.pairs.items()):
            if check is not None and n%128==0:check()
            k=self.source_index[s]*self.width+self.target_index[t]
            self.T=z3.Store(self.T,k,z3.RealVal(str(pair.time if pair.reachable else 0)))
            self.L=z3.Store(self.L,k,z3.RealVal(str(pair.length if pair.reachable else 0)))
            self.R=z3.Store(self.R,k,pair.reachable)
        self.actions=table.actions
        self.AS=z3.K(z3.IntSort(),z3.IntVal(0));self.AT=z3.K(z3.IntSort(),z3.IntVal(0))
        self.C=z3.K(z3.IntSort(),z3.BoolVal(False));self.S=z3.K(z3.IntSort(),z3.BoolVal(False))
        for rank,(site,effect) in enumerate(self.actions,1):
            anchor=table.aliases[site]
            self.AS=z3.Store(self.AS,rank,self.source_index[anchor])
            self.AT=z3.Store(self.AT,rank,self.target_index[anchor])
            self.C=z3.Store(self.C,rank,effect in ('C','CS'))
            self.S=z3.Store(self.S,rank,effect in ('S','CS'))

    def _select(self,array,index):
        return self.z3.Select(array,index)

    def at(self,source,target):
        z=self.z3
        for value in (source,target):
            if type(value) is int:continue
            if not isinstance(value,z.ArithRef) or value.sort().kind()!=z.Z3_INT_SORT:
                raise TypeError('lookup indices must be integers, never bool/real/coerced values')
        key=source*self.width+target
        guard=z.And(source>=0,source<len(self.source_index),target>=0,target<self.width,self._select(self.R,key))
        return GroundedLeg(guard,self._select(self.T,key),self._select(self.L,key))

    def trace(self,depth,remaining_activity,prefix='input',check=None):
        z=self.z3
        if type(depth) is not int or depth<0:raise ValueError('nonnegative slot count required; no hidden H cap')
        if type(remaining_activity) is not int or remaining_activity not in (0,1):raise ValueError('activity state')
        choices=tuple(z.FreshInt(prefix+'_'+str(i)) for i in range(depth));constraints=[];legs=[];charging=[];service=[]
        previous=z.IntVal(self.source_index[self.table.origin_anchor]);pending=z.BoolVal(bool(remaining_activity))
        for i,choice in enumerate(choices):
            if check is not None:check()
            active=choice>0;effect_service=self._select(self.S,choice)
            constraints.extend((choice>=0,choice<=len(self.actions),z.Implies(effect_service,pending)))
            if i:constraints.append(z.Implies(choices[i-1]==0,choice==0))
            leg=self.at(previous,self._select(self.AT,choice));constraints.append(z.Implies(active,leg.guard))
            legs.append(GroundedLeg(z.Implies(active,leg.guard),z.If(active,leg.time,0),z.If(active,leg.length,0)))
            charging.append(self._select(self.C,choice));service.append(effect_service)
            pending=z.And(pending,z.Not(effect_service))
            # Source and target index spaces differ; never reuse AT as AS.
            previous=z.If(active,self._select(self.AS,choice),previous)
        terminal=self.at(previous,self.target_index[self.table.destination_anchor])
        constraints.extend((z.Not(pending),terminal.guard))
        H=z.Sum([z.If(c>0,1,0) for c in choices]) if choices else z.IntVal(0)
        return SlotTrace(self.table._owner,self.table.payload_sha256,choices,tuple(constraints),tuple(legs),terminal,self.actions,tuple(charging),tuple(service),H)

    def resolve(self,trace,plan):
        """Ground one literal sequence; no energy/continuous/optimality claim."""
        z=self.z3
        self._require_own_trace(trace)
        if len(plan)>len(trace.choices):raise ValueError('plan exceeds supplied construction slots')
        ranks={a:i for i,a in enumerate(self.actions,1)}
        try:values=[ranks[tuple(action)] for action in plan]
        except KeyError as exc:raise ValueError('unknown literal action') from exc
        substitutions=[(c,z.IntVal(values[i] if i<len(values) else 0)) for i,c in enumerate(trace.choices)]
        def ground(expr):return z.simplify(z.substitute(expr,*substitutions)) if substitutions else z.simplify(expr)
        if any(not z.is_true(ground(c)) for c in trace.constraints):raise ValueError('invalid or declared-unreachable trace')
        def rational(expr):
            x=ground(expr)
            if not z.is_rational_value(x):raise ValueError('ungrounded numeric input')
            return Fraction(x.numerator_as_long(),x.denominator_as_long())
        legs=tuple((rational(leg.time),rational(leg.length)) for leg in (*trace.legs,trace.terminal))
        return dict(plan=tuple(tuple(a) for a in plan),legs=legs,stop_count=len(plan),
                    scope='fixed-input trace only; not physical feasibility or optimality')

    def _require_own_trace(self,trace):
        if (not isinstance(trace,SlotTrace) or trace.table_owner is not self.table._owner or
                trace.table_sha256!=self.table.payload_sha256 or trace.actions!=self.actions):
            raise ValueError('trace belongs to another immutable input')

    def roots(self,trace):
        self._require_own_trace(trace)
        return (self.T,self.L,self.R,self.AS,self.AT,self.C,self.S,*trace.constraints,
                *(e for leg in (*trace.legs,trace.terminal) for e in (leg.guard,leg.time,leg.length)),
                *trace.charging,*trace.service,trace.stop_count)


def dag_nodes(expressions):
    seen=set();stack=list(expressions)
    while stack:
        e=stack.pop();key=e.get_id()
        if key in seen:continue
        seen.add(key);stack.extend(e.children())
    return len(seen)
