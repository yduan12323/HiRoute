"""Independent bounded-cache on-disk road representation; never routes.

Construction is untrusted until a separate full raw/DB identity join succeeds.
Exact input weights stay TEXT. No common denominator or integer-width inference.
"""
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import itertools
import json
import os
from pathlib import Path
import sqlite3
import sys

from exact_leg_table import NUMERICAL,SELECTION,identity,unique
from exact_road_certificate import Edge,Unsupported
from preflight_real_road_certificate import positive_parts,CONTROL

SCHEMA='hiroute.streaming_exact_road_representation.v1'
MAX_LINE=1024*1024
BATCH_BYTES=4*1024*1024


class ResourceStop(RuntimeError):pass


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as s:
        for b in iter(lambda:s.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def json_line(raw):
    return json.loads(raw,object_pairs_hook=unique,
        parse_constant=lambda v:(_ for _ in ()).throw(ValueError('nonfinite JSON')))


def lines(path,hasher=None):
    with Path(path).open('rb') as s:
        while True:
            row=s.readline(MAX_LINE+1)
            if not row:break
            if len(row)>MAX_LINE:raise ResourceStop('input record memory envelope; no truncation')
            if hasher is not None:hasher.update(row)
            yield row


def raw_fields(raw):
    f=raw.removesuffix(b'\n').decode('utf-8').split('\t')
    if len(f)!=5 or any(not x for x in f):raise ValueError('five nonempty road fields required')
    if any(CONTROL.search(x) for x in f[:3]):raise ValueError('control character in identity')
    for x in f[:3]:identity(x)
    try:
        for value in f[3:]:wide_conversion(positive_parts,value)
    except ValueError as exc:raise Unsupported('positive exact rational road weights required') from exc
    return tuple(f)


def wide_conversion(function,value):
    # Records already have an explicit memory/CPU envelope. Do not introduce
    # an undocumented fixed decimal-digit or int64 limit on exact quantities.
    prior=sys.get_int_max_str_digits() if hasattr(sys,'get_int_max_str_digits') else 0
    change=prior and len(value)>prior
    if change:sys.set_int_max_str_digits(0)
    try:return function(value)
    finally:
        if change:sys.set_int_max_str_digits(prior)


def declared_nodes(path):
    previous=None
    for raw in lines(path):
        node=identity(json_line(raw))
        if previous is not None and not previous<node:raise ValueError('explicit nodes must be unique, literal and sorted')
        previous=node;yield node


def connect(path,*,write=False,max_bytes=4*1024**3):
    if write:
        if Path(path).exists():raise ValueError('fresh DB path required; inspect uncertain outputs')
        db=sqlite3.connect(str(path));db.execute('PRAGMA journal_mode=OFF');db.execute('PRAGMA synchronous=OFF')
        db.execute('PRAGMA max_page_count='+str(max(1,max_bytes//4096)))
    else:
        if any(Path(str(path)+s).exists() for s in ('-wal','-journal')):raise ValueError('unresolved SQLite sidecar')
        db=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
        db.execute('PRAGMA query_only=ON')
    db.execute('PRAGMA trusted_schema=OFF');db.execute('PRAGMA cache_size=-16384')
    db.execute('PRAGMA mmap_size=0');db.execute('PRAGMA temp_store=FILE');db.execute('PRAGMA threads=1')
    heap=db.execute('PRAGMA hard_heap_limit=134217728').fetchone()
    if heap is None or not 0<heap[0]<=134217728:db.close();raise ResourceStop('bounded SQLite heap not available')
    db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH,2*MAX_LINE)
    return db


def graph_identity(raw_hash,nodes_hash):
    value=dict(schema=SCHEMA,numerical_contract=NUMERICAL,selected_leg_contract=SELECTION,
               raw_sha256=raw_hash,declared_nodes_sha256=nodes_hash,node_domain='explicit' if nodes_hash else 'all raw endpoints')
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def flush_file(path):
    with Path(path).open('rb') as s:os.fsync(s.fileno())


def build(raw_path,db_path,*,nodes_path=None,expected_raw_sha=None,max_bytes=4*1024**3,
          check=lambda:None,progress=lambda v:None):
    db=connect(db_path,write=True,max_bytes=max_bytes);h=hashlib.sha256();count=0
    try:
        db.executescript('CREATE TABLE nodes(node TEXT COLLATE BINARY PRIMARY KEY) WITHOUT ROWID;'
          'CREATE TABLE edges(ordinal INTEGER PRIMARY KEY,u TEXT COLLATE BINARY NOT NULL,v TEXT COLLATE BINARY NOT NULL,'
          'eid TEXT COLLATE BINARY UNIQUE NOT NULL,t TEXT NOT NULL,l TEXT NOT NULL);'
          'CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL) WITHOUT ROWID;')
        if nodes_path is not None:
            for node in declared_nodes(nodes_path):db.execute('INSERT INTO nodes VALUES(?)',(node,))
        batch=[];batch_bytes=0
        def write_batch():
            if nodes_path is None:
                db.executemany('INSERT OR IGNORE INTO nodes VALUES(?)',((n,) for r in batch for n in r[1:3]))
            db.executemany('INSERT INTO edges VALUES(?,?,?,?,?,?)',batch);batch.clear()
        for raw in lines(raw_path,h):
            if batch and batch_bytes+len(raw)>BATCH_BYTES:check();write_batch();batch_bytes=0
            batch.append((count,*raw_fields(raw)));count+=1;batch_bytes+=len(raw)
            if len(batch)>=4096:check();write_batch();batch_bytes=0
            if count%500000==0:progress(dict(phase='build',edge_rows=count))
        write_batch();check();raw_hash=h.hexdigest()
        if expected_raw_sha is not None and raw_hash!=expected_raw_sha:raise ValueError('frozen raw input mismatch')
        nh=sha(nodes_path) if nodes_path is not None else None
        meta=dict(schema=SCHEMA,numerical_contract=NUMERICAL,selected_leg_contract=SELECTION,
                  raw_sha256=raw_hash,declared_nodes_sha256=nh,graph_identity=graph_identity(raw_hash,nh))
        db.executemany('INSERT INTO meta VALUES(?,?)',((k,json.dumps(v)) for k,v in meta.items()))
        node_count=db.execute('SELECT COUNT(*) FROM nodes').fetchone()[0]
        if not node_count:raise ValueError('nonempty complete node domain required')
        db.commit()
    except sqlite3.IntegrityError as exc:raise ValueError('duplicate literal node/edge identity') from exc
    finally:db.close()
    flush_file(db_path)
    return dict(scope='untrusted construction only; not a road certificate',edge_rows=count,nodes=node_count,
                raw_sha256=raw_hash,declared_nodes_sha256=nh,graph_identity=meta['graph_identity'],db_bytes=Path(db_path).stat().st_size)


@dataclass(frozen=True,init=False)
class Graph:
    path: object
    raw_path: object
    nodes_path: object
    raw_sha256: str
    payload_sha256: str
    representation_sha256: str
    node_count: int
    edge_count: int
    _owner: object=None
    _validated: bool=False

    def nodes(self):
        cursor=self._db.execute('SELECT node FROM nodes ORDER BY node COLLATE BINARY')
        try:
            for row in cursor:yield row[0]
        finally:cursor.close()

    def has_node(self,node):
        identity(node)
        return self._db.execute('SELECT 1 FROM nodes WHERE node=?',(node,)).fetchone() is not None

    def edge(self,eid):
        identity(eid)
        row=self._db.execute('SELECT u,v,t,l FROM edges WHERE eid=? COLLATE BINARY',(eid,)).fetchone()
        if row is None:raise ValueError('missing literal edge ID')
        return Edge(row[0],row[1],wide_conversion(Fraction,row[2]),wide_conversion(Fraction,row[3]),eid)

    def raw_edges(self,check=lambda:None):
        h=hashlib.sha256();count=0
        for raw in lines(self.raw_path,h):
            if count%4096==0:check()
            u,v,eid,t,L=raw_fields(raw);count+=1
            yield Edge(u,v,wide_conversion(Fraction,t),wide_conversion(Fraction,L),eid)
        if h.hexdigest()!=self.raw_sha256 or count!=self.edge_count:raise ValueError('authoritative graph changed during source checking')

    def assert_unchanged(self):
        if sha(self.path)!=self.representation_sha256:raise ValueError('validated representation changed')
        if sha(self.raw_path)!=self.raw_sha256:raise ValueError('authoritative raw graph changed')
        if self.nodes_path is not None and sha(self.nodes_path)!=self._nodes_sha:raise ValueError('explicit node input changed')

    def close(self):self._db.close()


def validate(raw_path,db_path,workspace,*,nodes_path=None,expected_raw_sha=None,
             max_tracking_bytes=2*1024**3,check=lambda:None,progress=lambda v:None):
    """Independent ordinal/raw join, global ID order, and bidirectional node set.

    Uses a separate bounded-cache seen-node DB, never the builder's node flags.
    All numeric values are compared as raw literal exact input, no SQL numbers.
    """
    folder=Path(workspace);folder.mkdir(exist_ok=False);db=connect(db_path)
    tracking=connect(folder/'seen.sqlite',write=True,max_bytes=max_tracking_bytes)
    tracking.execute('CREATE TABLE seen(node TEXT COLLATE BINARY PRIMARY KEY) WITHOUT ROWID')
    h=hashlib.sha256();E=0;N=0;prior_digest=sha(db_path)
    try:
        tables={row[0]:row[1] for row in db.execute("SELECT name,type FROM sqlite_master WHERE name IN ('nodes','edges','meta')")}
        if tables!={'nodes':'table','edges':'table','meta':'table'}:raise ValueError('literal road tables required')
        actual=iter(db.execute('SELECT ordinal,u,v,eid,t,l FROM edges ORDER BY ordinal'))
        batch=[];batch_bytes=0
        for raw in lines(raw_path,h):
            f=raw_fields(raw);row=next(actual,None)
            if row!=(E,*f):raise ValueError('raw/representation edge identity, order or exact weight mismatch')
            if batch and batch_bytes+len(raw)>BATCH_BYTES:
                check();tracking.executemany('INSERT OR IGNORE INTO seen VALUES(?)',batch);batch.clear();batch_bytes=0
            batch.extend(((f[0],),(f[1],)));E+=1;batch_bytes+=len(raw)
            if len(batch)>=8192:
                check();tracking.executemany('INSERT OR IGNORE INTO seen VALUES(?)',batch);batch.clear();batch_bytes=0
            if E%500000==0:progress(dict(phase='independent_validate',edge_rows=E))
        tracking.executemany('INSERT OR IGNORE INTO seen VALUES(?)',batch);tracking.commit()
        if next(actual,None) is not None:raise ValueError('extra representation edge')
        raw_hash=h.hexdigest()
        if expected_raw_sha is not None and raw_hash!=expected_raw_sha:raise ValueError('frozen authoritative input mismatch')
        previous=None;count=0
        for (eid,) in db.execute('SELECT eid FROM edges ORDER BY eid COLLATE BINARY'):
            identity(eid)
            if previous is not None and not previous<eid:raise ValueError('global edge-ID collision/duplicate')
            previous=eid;count+=1
            if count%4096==0:check()
        if count!=E:raise ValueError('edge identity cardinality mismatch')
        seen=iter(row[0] for row in tracking.execute('SELECT node FROM seen ORDER BY node COLLATE BINARY'))
        expected=declared_nodes(nodes_path) if nodes_path is not None else seen
        node_rows=(row[0] for row in db.execute('SELECT node FROM nodes ORDER BY node COLLATE BINARY'))
        previous=None;needed=next(seen,None) if nodes_path is not None else None
        for want,got in itertools.zip_longest(expected,node_rows):
            if want is None or got is None or want!=got:raise ValueError('missing/extra node or literal mapping collision')
            identity(got)
            if previous is not None and not previous<got:raise ValueError('node duplicate/collation mismatch')
            if nodes_path is not None:
                if needed is not None and needed<got:raise ValueError('raw endpoint absent from explicit node domain')
                if needed==got:needed=next(seen,None)
            previous=got;N+=1
            if N%4096==0:check()
        if needed is not None or not N:raise ValueError('incomplete/empty node domain')
        nh=sha(nodes_path) if nodes_path is not None else None
        items=list(db.execute('SELECT key,value FROM meta'))
        if len({k for k,v in items})!=len(items):raise ValueError('duplicate representation metadata identity')
        meta={k:json.loads(v) for k,v in items}
        required=dict(schema=SCHEMA,numerical_contract=NUMERICAL,selected_leg_contract=SELECTION,
                      raw_sha256=raw_hash,declared_nodes_sha256=nh,graph_identity=graph_identity(raw_hash,nh))
        if meta!=required:raise ValueError('actual raw/node identity or numerical contract mismatch')
        if db.execute('PRAGMA quick_check').fetchone()!=('ok',):raise ValueError('SQLite structural corruption')
        check()
    finally:tracking.close();db.close()
    digest=sha(db_path)
    if digest!=prior_digest:raise ValueError('representation changed during validation')
    graph=object.__new__(Graph)
    for k,v in dict(path=Path(db_path).resolve(),raw_path=Path(raw_path).resolve(),nodes_path=Path(nodes_path).resolve() if nodes_path else None,
        raw_sha256=raw_hash,payload_sha256=required['graph_identity'],representation_sha256=digest,
        node_count=N,edge_count=E,_owner=object(),_validated=True,_nodes_sha=nh,_db=connect(db_path)).items():object.__setattr__(graph,k,v)
    return graph
