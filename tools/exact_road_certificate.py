"""Independent supplied-certificate checker; no routing/optimization algorithm.

Certifies paths only for the exact explicit graph/table supplied. Real graph
extraction/completeness is a separate input obligation. Positive times make the
shortest-time tight graph a DAG; zero-time edges/cycles are unsupported.
"""
from dataclasses import dataclass
import hashlib
import json
from types import MappingProxyType

from exact_leg_table import ExactLegTable,NUMERICAL,SELECTION,number,identity,sequence,unique

GRAPH_SCHEMA='hiroute.exact_directed_road_graph.v1'
CERT_SCHEMA='hiroute.exact_road_source_certificate.v1'


class Unsupported(ValueError):pass


def decode(data):
    if type(data) is not bytes:raise TypeError('literal input bytes required')
    return json.loads(data,object_pairs_hook=unique,
        parse_constant=lambda x:(_ for _ in ()).throw(ValueError('nonfinite JSON')))

def object_fields(value,fields,name):
    if type(value) is not dict or set(value)!=set(fields):raise ValueError(name+' fields')


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    time: object
    length: object
    edge_id: str


@dataclass(frozen=True,init=False)
class ExactRoadGraph:
    nodes: tuple
    edges: object
    outgoing: object
    payload_sha256: str
    _owner: object=None
    _validated: bool=False

    @classmethod
    def from_dict(cls,payload):
        # No public digest override: identity is derived from actual input.
        return cls.from_bytes(json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False).encode())

    @classmethod
    def from_bytes(cls,data,check=lambda:None):
        p=decode(data)
        object_fields(p,('schema','numerical_contract','selected_leg_contract','nodes','edges'),'graph')
        if p['schema']!=GRAPH_SCHEMA or p['numerical_contract']!=NUMERICAL or p['selected_leg_contract']!=SELECTION:
            raise Unsupported('graph/numerical/selection contract')
        nodes=tuple(identity(n) for n in sequence(p['nodes'],'nodes'))
        if not nodes or len(set(nodes))!=len(nodes):raise ValueError('nonempty unique graph node domain')
        domain=set(nodes);edges={};outgoing={n:[] for n in nodes}
        for i,row in enumerate(sequence(p['edges'],'edges')):
            if i%128==0:check()
            object_fields(row,('source','target','time_s','length_m','edge_id'),'edge')
            a,b,e=map(identity,(row['source'],row['target'],row['edge_id']))
            t,L=number(row['time_s']),number(row['length_m'])
            if t<=0:raise Unsupported('strictly positive edge times required; zero-time edges/cycles are unsupported')
            if L<=0:raise Unsupported('current selected-leg contract requires positive edge lengths')
            if a not in domain or b not in domain or e in edges:raise ValueError('edge node domain/duplicate edge identity')
            item=Edge(a,b,t,L,e);edges[e]=item;outgoing[a].append(item)
        # Static sorting is charged graph preparation. Full strings, never int casts.
        for n in nodes:outgoing[n]=tuple(sorted(outgoing[n],key=lambda e:(e.target,e.edge_id)))
        graph=object.__new__(cls)
        for name,value in dict(nodes=tuple(sorted(nodes)),edges=MappingProxyType(edges),
                outgoing=MappingProxyType(outgoing),payload_sha256=hashlib.sha256(data).hexdigest(),
                _owner=object(),_validated=True).items():object.__setattr__(graph,name,value)
        check()
        return graph


@dataclass(frozen=True,init=False)
class CheckedRoadCertificate:
    graph_sha256: str
    table_sha256: str
    source_receipts: tuple
    checked_pairs: int
    literal_sites: int
    _graph_owner: object=None
    _table_owner: object=None
    _checked: bool=False

    def is_for(self,graph,table):
        return (self._checked and isinstance(graph,ExactRoadGraph) and isinstance(table,ExactLegTable)
            and self._graph_owner is graph._owner and self._table_owner is table._owner
            and self.graph_sha256==graph.payload_sha256 and self.table_sha256==table.payload_sha256)


class CertificateSession:
    """Sequential one-source-at-a-time checking; prefixes are not whole-table certificates."""
    __slots__=('_graph','_table','_check','_receipts','_failed','_result','_target_bits')

    @property
    def graph(self):return self._graph
    @property
    def table(self):return self._table
    @property
    def receipts(self):return tuple(self._receipts)
    @property
    def failed(self):return self._failed

    def __init__(self,graph,table,check=lambda:None):
        if not isinstance(graph,ExactRoadGraph) or not graph._validated:raise TypeError('parser-owned graph required')
        if not isinstance(table,ExactLegTable) or not table._validated:raise TypeError('parser-owned table required')
        if table.graph_identity!='sha256:'+graph.payload_sha256:raise ValueError('actual graph/table identity mismatch')
        if not (set(table.sources)|set(table.targets))<=set(graph.nodes):raise ValueError('table anchors outside graph')
        self._graph,self._table,self._check=graph,table,check
        self._receipts=[];self._failed=False;self._result=None
        self._target_bits={t:1<<i for i,t in enumerate(table.targets)}

    def check_source(self,data):
        if self.failed or self._result is not None:raise ValueError('session failed or already finished')
        try:return self._check_source(data)
        except BaseException:
            self._failed=True
            raise

    def _check_source(self,data):
        self._check()
        g,t=self.graph,self.table;p=decode(data)
        object_fields(p,('schema','graph_sha256','table_sha256','source','target_order','labels','predecessors','target_masks'),'source certificate')
        if (p['schema']!=CERT_SCHEMA or p['graph_sha256']!=g.payload_sha256 or p['table_sha256']!=t.payload_sha256):
            raise ValueError('certificate contract or actual input digest mismatch')
        if len(self._receipts)>=len(t.sources) or p['source']!=t.sources[len(self._receipts)]:raise ValueError('missing/duplicate/out-of-order physical source')
        if type(p['target_order']) is not list or p['target_order']!=list(t.targets):raise ValueError('complete target identity/order required')
        source=p['source'];labels=p['labels'];pred=p['predecessors'];masks=p['target_masks']
        if type(labels) is not dict or set(labels)!=set(g.nodes):raise ValueError('labels must cover every graph node, with explicit unreachable nulls')
        d={v:None if labels[v] is None else number(labels[v]) for v in g.nodes}
        R={v for v in g.nodes if d[v] is not None}
        if d[source]!=0 or any(d[v]<0 for v in R):raise ValueError('root/nonnegative distance labels')
        if type(pred) is not dict or set(pred)!=R-{source}:raise ValueError('complete attaining predecessor domain')
        if type(masks) is not dict or set(masks)!=R:raise ValueError('complete reachable-node target masks')
        limit=1<<len(t.targets)
        for i,v in enumerate(R):
            if i%128==0:self._check()
            if type(masks[v]) is not int or not 0<=masks[v]<limit:raise ValueError('literal finite target bitset required')
            if v==source:continue
            edge=g.edges.get(identity(pred[v]))
            if edge is None or edge.target!=v or edge.source not in R:raise ValueError('invalid attaining predecessor')
            if d[v]!=d[edge.source]+edge.time or not d[edge.source]<d[v]:raise ValueError('predecessor must strictly attain distance')
        tight={v:[] for v in R};tight_count=0
        for i,edge in enumerate(g.edges.values()):
            if i%128==0:self._check()
            if edge.source not in R:continue
            if edge.target not in R:raise ValueError('unreachable cut has an outgoing edge')
            if d[edge.target]>d[edge.source]+edge.time:raise ValueError('shortest-time lower inequality violated')
            if d[edge.target]==d[edge.source]+edge.time:
                tight[edge.source].append(edge);tight_count+=1
        # All tight edges strictly increase d, hence these local equations have
        # a unique DAG solution. Supplied masks cannot invent or hide a suffix.
        for i,v in enumerate(R):
            if i%128==0:self._check()
            expected=self._target_bits.get(v,0)
            for j,edge in enumerate(tight[v]):
                if j%128==0:self._check()
                expected|=masks[edge.target]
            if masks[v]!=expected:raise ValueError('tight-DAG target reachability bitset equation violated')
        required={};steps=0;zero=0
        for target in t.targets:
            self._check();pair=t.pairs[source,target];reachable=target in R
            if pair.reachable!=reachable:raise ValueError('declared reachable/unreachable pair contradicts certificate')
            if not reachable:continue
            if pair.time!=d[target]:raise ValueError('pair time differs from proven shortest-time label')
            T=L=0
            for a,b,eid in zip(pair.nodes,pair.nodes[1:],pair.edges):
                self._check();edge=g.edges.get(eid)
                if edge is None or (edge.source,edge.target)!=(a,b):raise ValueError('selected path edge/endpoints absent from graph')
                T+=edge.time;L+=edge.length
                required.setdefault(a,{})[target]=(b,eid);steps+=1
            if T!=pair.time or L!=pair.length:raise ValueError('selected path time/actual length sum mismatch')
            if source==target:
                zero+=1
                if pair.nodes!=(source,) or pair.edges or T!=0 or L!=0:raise ValueError('exact alias-zero path required')
        # Check all requested path steps at a vertex in one sorted adjacency
        # pass, rather than scanning the whole graph separately for each pair.
        for v,choices in required.items():
            self._check();unassigned=0
            for target in choices:unassigned|=self._target_bits[target]
            for j,edge in enumerate(g.outgoing[v]):
                if j%128==0:self._check()
                if edge.target not in R or d[edge.target]!=d[v]+edge.time:continue
                eligible=unassigned&masks[edge.target]
                while eligible:
                    bit=eligible&-eligible;index=bit.bit_length()-1;target=t.targets[index]
                    if choices[target]!=(edge.target,edge.edge_id):
                        raise ValueError('selected path is not canonical by full node tuple then full string edge-ID tuple')
                    eligible^=bit;unassigned^=bit
                if not unassigned:break
            if unassigned:raise ValueError('selected path has no tight target-reaching canonical successor')
        receipt=dict(source=source,certificate_sha256=hashlib.sha256(data).hexdigest(),reachable_nodes=len(R),
            checked_pairs=len(t.targets),zero_pairs=zero,tight_edges=tight_count,checked_path_steps=steps,
            scope='one physical source only; not a complete-table certificate')
        self._check()
        self._receipts.append(MappingProxyType(receipt));return self._receipts[-1]

    def finish(self):
        if self.failed:raise ValueError('failed source check invalidates this session')
        if self._result is not None:return self._result
        if len(self._receipts)!=len(self.table.sources):raise ValueError('incomplete source/terminal/alias-zero coverage')
        try:self._check()
        except BaseException:
            self._failed=True
            raise
        result=object.__new__(CheckedRoadCertificate)
        values=dict(graph_sha256=self.graph.payload_sha256,table_sha256=self.table.payload_sha256,
            source_receipts=tuple(self._receipts),checked_pairs=len(self.table.pairs),literal_sites=len(self.table.candidate_order),
            _graph_owner=self.graph._owner,_table_owner=self.table._owner,_checked=True)
        for name,value in values.items():object.__setattr__(result,name,value)
        self._result=result;return result
