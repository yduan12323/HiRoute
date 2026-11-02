"""Independent on-disk selected paths and supplied-source certificate checking.

No router, optimizer, distances producer or common-denominator approximation.
One JSONL record at a time, bounded SQLite caches, all raw edges checked.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import itertools
import json
from pathlib import Path
import sqlite3
import sys
from types import MappingProxyType

from exact_leg_table import NUMERICAL,SELECTION,identity,sequence,number
from streaming_road_graph import Graph,ResourceStop,connect,lines,json_line,sha,flush_file

TABLE_SCHEMA='hiroute.streaming_selected_leg_table.v1'
SOURCE_SCHEMA='hiroute.streaming_source_certificate.v1'
UNIT_SCHEMA='hiroute.streaming_selected_leg_source_unit.v1'


def fields(value,names):
    if type(value) is not dict or set(value)!=set(names):raise ValueError('exact record fields required')


@contextmanager
def decimal_conversion():
    # Only after record/bit storage admission; single numerical thread. Restore
    # the interpreter's resource setting even when conversion raises.
    prior=sys.get_int_max_str_digits() if hasattr(sys,'get_int_max_str_digits') else None
    if prior is not None:sys.set_int_max_str_digits(0)
    try:yield
    finally:
        if prior is not None:sys.set_int_max_str_digits(prior)


class Arithmetic:
    def __init__(self,bytes_limit=16*1024**2):self.limit=bytes_limit
    def admit(self,*values):
        # Conservative storage reservation for operands and cross-products,
        # addition, gcd/remainders and normalized results. No precision clipping.
        bits=sum(abs(v.numerator).bit_length()+v.denominator.bit_length() for v in values)
        if 1024+8*((bits+7)//8)>self.limit:raise ResourceStop('exact arithmetic temporary envelope')
    def parse(self,value):
        if isinstance(value,str) and 1024+len(value)*4>self.limit:raise ResourceStop('exact input storage envelope')
        with decimal_conversion():v=number(value)
        self.admit(v);return v
    def text(self,value):
        self.admit(value)
        with decimal_conversion():return str(value)
    def add(self,a,b):self.admit(a,b);return a+b
    def less(self,a,b):self.admit(a,b);return a<b


@dataclass(frozen=True,init=False)
class Table:
    path: object
    payload_sha256: str
    representation_sha256: str
    sources: tuple
    targets: tuple
    candidate_order: tuple
    aliases: object
    capabilities: object
    _owner: object=None
    _validated: bool=False

    def pair(self,s,t):
        return self._db.execute('SELECT reach,duration,length FROM pairs WHERE s=? AND t=?',(s,t)).fetchone()
    def steps(self,s,t):
        for row in self._db.execute('SELECT u,v,eid FROM steps WHERE s=? AND t=? ORDER BY i',(s,t)):yield row
    def choices(self,s,u):
        # The primary(s,t,i) plan can scan every path of a source for each raw
        # edge. This owned covering index seeks the vertex as well, preserving
        # exactly the same target order and mathematical comparison rows.
        for row in self._db.execute('SELECT t,v,eid FROM steps INDEXED BY steps_choice_lookup WHERE s=? AND u=? ORDER BY t COLLATE BINARY',(s,u)):yield row
    def assert_unchanged(self):
        if sha(self.path)!=self.representation_sha256:raise ValueError('selected-path representation changed')
    def close(self):self._db.close()


@dataclass(frozen=True,init=False)
class SourceUnit(Table):
    """One source's paths, with the COMPLETE original source/target domain."""
    unit_source: str=None


def read_table(path,graph,db_path,**kwargs):
    return _read_paths(path,graph,db_path,unit=False,**kwargs)


def read_source_unit(path,graph,db_path,**kwargs):
    return _read_paths(path,graph,db_path,unit=True,**kwargs)


def _read_paths(path,graph,db_path,*,unit,arithmetic=None,max_bytes=4*1024**3,check=lambda:None):
    if not isinstance(graph,Graph) or not graph._validated:raise TypeError('independently validated graph required')
    A=arithmetic or Arithmetic();h=hashlib.sha256();rows=iter(lines(path,h));first=next(rows,None)
    if first is None:raise ValueError('missing selected-path header')
    header=json_line(first)
    fields(header,('schema','numerical_contract','selected_leg_contract','graph_identity','origin_anchor','destination_anchor','candidate_order','sites')+(('source_unit',) if unit else ()))
    if (header['schema'],header['numerical_contract'],header['selected_leg_contract'],header['graph_identity'])!=(
        UNIT_SCHEMA if unit else TABLE_SCHEMA,NUMERICAL,SELECTION,'sha256:'+graph.payload_sha256):raise ValueError('actual graph/selection identity mismatch')
    origin,dest=map(identity,(header['origin_anchor'],header['destination_anchor']))
    order=sequence(header['candidate_order'],'candidate order');sites=header['sites']
    if type(sites) is not dict or len(set(order))!=len(order) or set(order)!=set(sites):raise ValueError('literal Site/capability domain')
    aliases={};caps={}
    for site in order:
        identity(site);fields(sites[site],('anchor','effects'));aliases[site]=identity(sites[site]['anchor'])
        effects=sequence(sites[site]['effects'],'effects')
        if not effects or len(set(effects))!=len(effects) or not set(effects)<={'C','S','CS'}:raise ValueError('effect domain')
        caps[site]=effects
    S=tuple(sorted({origin,*aliases.values()}));T=tuple(sorted({dest,*aliases.values()}))
    if not all(graph.has_node(v) for v in set(S)|set(T)):raise ValueError('source/terminal/alias absent')
    selected_source=identity(header['source_unit']) if unit else None
    if unit and selected_source not in S:raise ValueError('source unit outside complete domain')
    active=(selected_source,) if unit else S
    db=connect(db_path,write=True,max_bytes=max_bytes);count=0
    try:
        db.executescript('CREATE TABLE pairs(s TEXT COLLATE BINARY,t TEXT COLLATE BINARY,reach INTEGER,duration TEXT,length TEXT,PRIMARY KEY(s,t)) WITHOUT ROWID;'
          'CREATE TABLE steps(s TEXT COLLATE BINARY,t TEXT COLLATE BINARY,i INTEGER,u TEXT COLLATE BINARY,v TEXT COLLATE BINARY,eid TEXT COLLATE BINARY,'
          'PRIMARY KEY(s,t,i),UNIQUE(s,u,t)) WITHOUT ROWID;'
          'CREATE INDEX steps_choice_lookup ON steps(s,u,t,v,eid);'
          'CREATE TABLE path_nodes(s TEXT,t TEXT,node TEXT,PRIMARY KEY(s,t,node)) WITHOUT ROWID;')
        for raw in rows:
            check();p=json_line(raw);fields(p,('kind','source','target','reachable','time_s','length_m','first_node'))
            s,t=p['source'],p['target']
            if p['kind']!='pair' or type(p['reachable']) is not bool or s not in active or t not in T:raise ValueError('physical pair record/domain')
            reach=p['reachable'];time=A.parse(p['time_s']) if reach else None;length=A.parse(p['length_m']) if reach else None
            if not reach and (s==t or p['time_s'] is not None or p['length_m'] is not None or p['first_node'] is not None):raise ValueError('unreachable is not zero or partial path')
            if reach and p['first_node']!=s:raise ValueError('selected path first node')
            prev=s;total=Fraction(0);actual=Fraction(0);i=0
            if reach:db.execute('INSERT INTO path_nodes VALUES(?,?,?)',(s,t,s))
            for raw_step in rows:
                step=json_line(raw_step)
                if step=={'kind':'end_pair'}:break
                fields(step,('kind','u','v','edge_id'))
                if not reach or step['kind']!='step' or step['u']!=prev:raise ValueError('path continuity/unreachable steps')
                u,v,eid=map(identity,(step['u'],step['v'],step['edge_id']));edge=graph.edge(eid)
                if (edge.source,edge.target)!=(u,v):raise ValueError('unmatched actual edge tuple')
                total=A.add(total,edge.time);actual=A.add(actual,edge.length)
                db.execute('INSERT INTO path_nodes VALUES(?,?,?)',(s,t,v))
                db.execute('INSERT INTO steps VALUES(?,?,?,?,?,?)',(s,t,i,u,v,eid));prev=v;i+=1
                if i%1024==0:check()
            else:raise ValueError('unterminated pair')
            if reach and (prev!=t or total!=time or actual!=length):raise ValueError('actual path endpoint/time/length mismatch')
            if reach and ((s==t and (i or time!=0 or length!=0)) or (s!=t and (not i or time<=0 or length<=0))):raise ValueError('positive leg or exact alias-zero required')
            db.execute('INSERT INTO pairs VALUES(?,?,?,?,?)',(s,t,int(reach),A.text(time) if reach else None,A.text(length) if reach else None));count+=1
        if count!=len(active)*len(T):raise ValueError('missing source/terminal pair coverage')
        db.commit();check()
    except sqlite3.IntegrityError as exc:raise ValueError('duplicate pair/node/step identity') from exc
    finally:db.close()
    flush_file(db_path);graph.assert_unchanged();obj=object.__new__(SourceUnit if unit else Table)
    for k,v in dict(path=Path(db_path).resolve(),payload_sha256=h.hexdigest(),representation_sha256=sha(db_path),sources=S,targets=T,
        unit_source=selected_source,candidate_order=order,aliases=MappingProxyType(aliases),capabilities=MappingProxyType(caps),_owner=object(),
        _validated=True,_graph_owner=graph._owner,_db=connect(db_path)).items():object.__setattr__(obj,k,v)
    return obj


@dataclass(frozen=True,init=False)
class Checked:
    graph_sha256: str
    table_sha256: str
    source_receipts: tuple
    checked_pairs: int
    _checked: bool=False
    def is_for(self,g,t):
        owned=(self._checked and isinstance(g,Graph) and isinstance(t,Table) and
                self._g is g._owner and self._t is t._owner and
                self.graph_sha256==g.payload_sha256 and self.table_sha256==t.payload_sha256)
        if not owned:return False
        try:g.assert_unchanged();t.assert_unchanged()
        except (ValueError,OSError):return False
        return True


class Session:
    __slots__=('_g','_t','_A','_check','_receipts','_failed','_result','_max_state_bytes')
    def __init__(self,graph,table,*,arithmetic=None,check=lambda:None,max_state_bytes=4*1024**3):
        if (not isinstance(graph,Graph) or not graph._validated or type(table) is not Table or
            not table._validated or table._graph_owner is not graph._owner):raise TypeError('owned validated inputs required')
        self._g,self._t,self._A,self._check=graph,table,arithmetic or Arithmetic(),check
        if type(max_state_bytes) is not int or not 4096<=max_state_bytes<=4*1024**3:raise ValueError('source state DB byte quota')
        self._max_state_bytes=max_state_bytes
        self._receipts=[];self._failed=False;self._result=None
    @property
    def receipts(self):return tuple(self._receipts)
    @property
    def failed(self):return self._failed
    def check_source(self,path,workspace):
        if self._failed or self._result is not None:raise ValueError('failed or finished session')
        try:return self._source(path,workspace)
        except BaseException:self._failed=True;raise
    def _expected_sources(self):return self._t.sources
    def _source(self,path,workspace):
        g,t,A=self._g,self._t,self._A;self._check();folder=Path(workspace);folder.mkdir(exist_ok=False)
        h=hashlib.sha256();rows=iter(lines(path,h));first=next(rows,None)
        if first is None:raise ValueError('missing source-certificate header')
        header=json_line(first)
        fields(header,('schema','graph_sha256','table_sha256','source','target_order'))
        if (header['schema'],header['graph_sha256'],header['table_sha256'],header['target_order'])!=(
            SOURCE_SCHEMA,g.payload_sha256,t.payload_sha256,list(t.targets)):raise ValueError('source actual identity/target domain')
        expected_sources=self._expected_sources()
        if len(self._receipts)>=len(expected_sources) or header['source']!=expected_sources[len(self._receipts)]:raise ValueError('source order/coverage')
        source=header['source'];bits={v:1<<i for i,v in enumerate(t.targets)};limit=1<<len(t.targets)
        db=connect(folder/'state.sqlite',write=True,max_bytes=self._max_state_bytes);reachable=0
        try:
            db.execute('CREATE TABLE state(node TEXT COLLATE BINARY PRIMARY KEY,d TEXT,pred TEXT,mask TEXT,expected TEXT,seen INTEGER) WITHOUT ROWID')
            for index,(raw_node,node) in enumerate(itertools.zip_longest(rows,g.nodes())):
                if raw_node is None or node is None:raise ValueError('source must cover every actual graph node')
                row=json_line(raw_node);fields(row,('node','label','predecessor_edge_id','mask'))
                if row['node']!=node:raise ValueError('node mapping/coverage/order mismatch')
                value=A.parse(row['label']) if row['label'] is not None else None
                pred=row['predecessor_edge_id'];mask=row['mask']
                if value is None:
                    if pred is not None or mask is not None:raise ValueError('unreachable has no predecessor or mask')
                else:
                    if value<0 or (node==source and (value!=0 or pred is not None)):raise ValueError('root/nonnegative labels')
                    if node!=source:identity(pred)
                    if type(mask) is not str or not mask.isascii() or not mask.isdecimal() or len(mask)>len(str(limit)):
                        raise ValueError('literal bounded exact target mask')
                    mask=int(mask)
                    if not 0<=mask<limit:raise ValueError('target bitset range')
                    reachable+=1
                db.execute('INSERT INTO state VALUES(?,?,?,?,?,?)',(node,A.text(value) if value is not None else None,pred,
                  str(mask) if value is not None else None,str(bits.get(node,0)) if value is not None else None,0))
                if index%4096==0:self._check()
            db.commit()
            def state(n):
                d,p,m=db.execute('SELECT d,pred,mask FROM state WHERE node=?',(n,)).fetchone()
                return (A.parse(d) if d is not None else None,p,int(m) if m is not None else None)
            if state(source)[0]!=0:raise ValueError('source reachable zero required')
            for target in t.targets:
                self._check();reach,T,L=t.pair(source,target);d,_,_=state(target)
                if bool(reach)!=(d is not None) or (reach and A.parse(T)!=d):raise ValueError('proven shortest time/reachability differs from pair')
                if reach:
                    for index,(u,v,eid) in enumerate(t.steps(source,target)):
                        if index%1024==0:self._check()
                        edge=g.edge(eid);du,_,_=state(u);dv,_,mv=state(v)
                        if du is None or dv is None or A.add(du,edge.time)!=dv or not mv&bits[target]:raise ValueError('path step not tight target-reaching')
            E=0
            for edge in g.raw_edges(self._check):
                u,v,eid=edge.source,edge.target,edge.edge_id;du,_,mu=state(u);dv,pv,mv=state(v)
                if du is not None:
                    if dv is None:raise ValueError('directed unreachable cut violated')
                    proposed=A.add(du,edge.time)
                    if A.less(proposed,dv):raise ValueError('global shortest-time lower inequality violated')
                    if proposed==dv:
                        prior=db.execute('SELECT expected FROM state WHERE node=?',(u,)).fetchone()[0]
                        db.execute('UPDATE state SET expected=? WHERE node=?',(str(int(prior)|mv),u))
                        for index,(target,next_node,chosen_eid) in enumerate(t.choices(source,u)):
                            if index%1024==0:self._check()
                            if mv&bits[target] and (v,eid)<(next_node,chosen_eid):
                                raise ValueError('noncanonical full node/string-edge tuple')
                    if pv==eid:
                        if proposed!=dv or not A.less(du,dv):raise ValueError('predecessor does not strictly attain label')
                        db.execute('UPDATE state SET seen=1 WHERE node=?',(v,))
                E+=1
                if E%4096==0:self._check()
            for index,(n,d,p,m,expected,seen) in enumerate(db.execute('SELECT * FROM state')):
                if index%4096==0:self._check()
                if d is not None and (m!=expected or (n!=source and not seen)):raise ValueError('DAG mask equation or attaining predecessor incomplete')
            db.commit();g.assert_unchanged();t.assert_unchanged();self._check()
        finally:db.close()
        receipt=MappingProxyType(dict(source=source,certificate_sha256=h.hexdigest(),checked_pairs=len(t.targets),
            full_edge_rows=E,reachable_nodes=reachable,scope='one source only; no whole-table certificate'))
        self._receipts.append(receipt);return receipt
    def finish(self):
        if type(self._t) is not Table:raise ValueError('source unit cannot certify whole table')
        if self._failed:raise ValueError('failed source session')
        if len(self._receipts)!=len(self._t.sources):raise ValueError('incomplete source/terminal/alias coverage')
        try:self._g.assert_unchanged();self._t.assert_unchanged();self._check()
        except BaseException:self._failed=True;raise
        if self._result is not None:return self._result
        result=object.__new__(Checked)
        for k,v in dict(graph_sha256=self._g.payload_sha256,table_sha256=self._t.payload_sha256,
            source_receipts=tuple(self._receipts),checked_pairs=len(self._t.sources)*len(self._t.targets),
            _g=self._g._owner,_t=self._t._owner,_checked=True).items():object.__setattr__(result,k,v)
        self._result=result;return result


class SourceSession(Session):
    """Independent source-unit checker; cannot produce a whole-table Checked."""
    def __init__(self,graph,table,*,arithmetic=None,check=lambda:None,max_state_bytes=4*1024**3):
        if (not isinstance(graph,Graph) or not graph._validated or type(table) is not SourceUnit or
            not table._validated or table._graph_owner is not graph._owner):
            raise TypeError('owned validated source-unit inputs required')
        self._g,self._t,self._A,self._check=graph,table,arithmetic or Arithmetic(),check
        if type(max_state_bytes) is not int or not 4096<=max_state_bytes<=4*1024**3:raise ValueError('source state DB byte quota')
        self._max_state_bytes=max_state_bytes
        self._receipts=[];self._failed=False;self._result=None
    def _expected_sources(self):return (self._t.unit_source,)
    def finish(self):
        if self._failed:raise ValueError('failed source session')
        if len(self._receipts)!=1:raise ValueError('single source not independently checked')
        try:self._g.assert_unchanged();self._t.assert_unchanged();self._check()
        except BaseException:self._failed=True;raise
        if self._result is None:
            self._result=MappingProxyType(dict(scope='verified single source only',source=self._t.unit_source,
                source_denominator=len(self._t.sources),pair_denominator=len(self._t.sources)*len(self._t.targets),
                checked_sources=1,checked_pairs=len(self._t.targets),unrun_sources=len(self._t.sources)-1,
                graph_sha256=self._g.payload_sha256,unit_sha256=self._t.payload_sha256,
                certificate_sha256=self._receipts[0]['certificate_sha256'],whole_table_certified=False))
        return self._result
