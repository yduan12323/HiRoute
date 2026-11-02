"""Bounded external CSR writer and independent full raw-TSV representation check.

No routing, source certificates, EV model or optimizer. The validator rebuilds
its own literal rank maps from authoritative raw rows, never writer maps.
"""
from array import array
from fractions import Fraction
import hashlib
import itertools
import json
import os
from pathlib import Path
import sqlite3
import struct
import sys
import time

from exact_leg_table import identity
from packed_source_prototype import HEAD,ARC,U64,MAGIC,SENTINEL,Packed
from streaming_road_graph import (ResourceStop,MAX_LINE,BATCH_BYTES,connect,sha,
    raw_fields,lines,wide_conversion,declared_nodes,graph_identity,flush_file)

GIB=1024**3
SCHEMA='hiroute.packed_csr.v1'


def database(path,max_bytes):
    if type(max_bytes) is not int or not 4096<=max_bytes<=2*GIB:raise ResourceStop('SQLite file quota domain')
    if Path(path).exists():raise ValueError('fresh DB required; inspect prior/uncertain outputs')
    # URI support must be enabled on the writer connection too, so ATTACH's
    # mode=ro&immutable=1 is interpreted instead of treated as a file name.
    db=sqlite3.connect(Path(path).resolve().as_uri(),uri=True)
    db.execute('PRAGMA journal_mode=OFF');db.execute('PRAGMA synchronous=OFF')
    db.execute('PRAGMA max_page_count='+str(max(1,max_bytes//4096)))
    db.execute('PRAGMA trusted_schema=OFF');db.execute('PRAGMA cache_size=-16384')
    db.execute('PRAGMA mmap_size=0');db.execute('PRAGMA threads=1')
    heap=db.execute('PRAGMA hard_heap_limit=134217728').fetchone()
    if heap is None or not 0<heap[0]<=134217728:db.close();raise ResourceStop('bounded SQLite heap required')
    db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH,2*MAX_LINE)
    # Unexpected sorting must fail against the global SQLite heap envelope,
    # rather than allocate untracked, possibly unlinked temporary disk files.
    db.execute('PRAGMA temp_store=MEMORY');db.execute('PRAGMA automatic_index=OFF')
    return db


def no_sort(db,sql):
    plan=[r[3] for r in db.execute('EXPLAIN QUERY PLAN '+sql)]
    if any('TEMP B-TREE' in p.upper() for p in plan):
        raise ResourceStop('unexpected temporary sort; no full-graph release')
    return plan


def ranks(db,table,select):
    db.execute('CREATE TABLE '+table+'(name TEXT COLLATE BINARY PRIMARY KEY,r INTEGER NOT NULL) WITHOUT ROWID')
    plan=no_sort(db,select)
    db.execute('INSERT INTO '+table+' '+select)
    return plan


def pwrite(fd,data,offset):
    view=memoryview(data)
    while view:
        n=os.pwrite(fd,view,offset)
        if not n:raise OSError('short positional write')
        offset+=n;view=view[n:]


class Section:
    def __init__(self,fd,start,record):self.fd=fd;self.start=start;self.record=record;self.buffer=bytearray();self.count=0
    def add(self,*values):
        self.buffer.extend(self.record.pack(*values));self.count+=1
        if len(self.buffer)>=65536:self.flush()
    def flush(self):
        if self.buffer:pwrite(self.fd,self.buffer,self.start);self.start+=len(self.buffer);self.buffer.clear()


def exact_binary(text):
    if type(text) is not str or len(text.encode('utf-8'))>MAX_LINE:raise ResourceStop('exact component input envelope')
    value=wide_conversion(Fraction,text)
    if value<=0:raise ValueError('positive exact weights required')
    n,d=value.numerator,value.denominator
    a=max(1,(n.bit_length()+7)//8);b=max(1,(d.bit_length()+7)//8)
    if a+b+8>MAX_LINE:raise ResourceStop('exact magnitude memory envelope; no clipping')
    return struct.pack('<II',a,b)+n.to_bytes(a,'little')+d.to_bytes(b,'little')


def build(source_db,folder,*,expected_db_sha,expected_identity,expected_N,expected_E,
          max_db_bytes=2*GIB,max_packed_bytes=4*GIB,check=lambda:None,progress=lambda v:None):
    """Untrusted writer, with bounded disk maps and no all-graph Python map."""
    if type(expected_N) is not int or type(expected_E) is not int or not 0<expected_N<SENTINEL or not 0<=expected_E<SENTINEL:raise ResourceStop('proven index counts required')
    if not HEAD.size<=max_packed_bytes<=4*GIB:raise ResourceStop('packed file quota')
    identity(expected_identity)
    folder=Path(folder)
    if folder.exists():raise ValueError('existing output; inspect uncertain construction')
    if any(Path(str(source_db)+s).exists() for s in ('-wal','-journal')):raise ValueError('unresolved source SQLite sidecar')
    if sha(source_db)!=expected_db_sha:raise ValueError('frozen representation bytes changed')
    folder.mkdir(exist_ok=False)
    db=database(folder/'maps.sqlite',max_db_bytes);plans={}
    try:
        db.execute('ATTACH DATABASE ? AS src',(Path(source_db).resolve().as_uri()+'?mode=ro&immutable=1',))
        db.execute('ATTACH DATABASE ? AS arcs',(str(folder/'arcs.sqlite'),))
        db.execute('PRAGMA arcs.journal_mode=OFF');db.execute('PRAGMA arcs.synchronous=OFF')
        db.execute('PRAGMA arcs.max_page_count='+str(max_db_bytes//4096))
        plans['nodes']=ranks(db,'n','SELECT node,row_number() OVER(ORDER BY node COLLATE BINARY)-1 FROM src.nodes')
        check();progress(dict(phase='node_ranks',nodes=db.execute('SELECT count(*) FROM n').fetchone()[0]))
        plans['edges']=ranks(db,'e','SELECT eid,row_number() OVER(ORDER BY eid COLLATE BINARY)-1 FROM src.edges')
        N=db.execute('SELECT count(*) FROM n').fetchone()[0];E=db.execute('SELECT count(*) FROM e').fetchone()[0]
        if (N,E)!=(expected_N,expected_E):raise ValueError('full frozen node/edge count mismatch')
        db.execute('CREATE TABLE arcs.a(u INTEGER,v INTEGER,eid INTEGER,t TEXT NOT NULL,l TEXT NOT NULL,PRIMARY KEY(u,v,eid)) WITHOUT ROWID')
        sql='''SELECT nu.r,nv.r,em.r,g.t,g.l FROM src.edges g
          CROSS JOIN n nu ON nu.name=g.u COLLATE BINARY
          CROSS JOIN n nv ON nv.name=g.v COLLATE BINARY
          CROSS JOIN e em ON em.name=g.eid COLLATE BINARY'''
        plans['join']=no_sort(db,sql);db.execute('INSERT INTO arcs.a '+sql);db.commit()
        if db.execute('SELECT count(*) FROM arcs.a').fetchone()[0]!=E:raise ValueError('missing endpoint/edge rank')
        check();progress(dict(phase='arcs_ranked',edges=E))
        np=HEAD.size;ep=np+8*(N+1);ap=ep+8*(E+1);rp=ap+8*(N+1);arena=rp+ARC.size*E
        path=folder/'graph.csr'
        with path.open('xb+',buffering=65536) as out:
            out.seek(arena)
            def append(data):
                if out.tell()+len(data)>max_packed_bytes:raise ResourceStop('packed file quota; no truncation')
                out.write(data)
            def strings(table,start):
                section=Section(out.fileno(),start,U64)
                for i,(name,rank) in enumerate(db.execute('SELECT name,r FROM '+table+' ORDER BY name COLLATE BINARY')):
                    if i!=rank:raise ValueError('literal rank order')
                    raw=identity(name).encode('utf-8')
                    if len(raw)>MAX_LINE:raise ResourceStop('literal record envelope')
                    section.add(out.tell());append(raw)
                    if i%4096==0:check()
                section.add(out.tell());section.flush()
            strings('n',np);strings('e',ep)
            adjacency=Section(out.fileno(),ap,U64);records=Section(out.fileno(),rp,ARC);next_u=0
            for i,(u,v,eid,t,L) in enumerate(db.execute('SELECT u,v,eid,t,l FROM arcs.a ORDER BY u,v,eid')):
                if not 0<=u<N or not 0<=v<N or not 0<=eid<E:raise ValueError('rank outside full domain')
                while next_u<=u:adjacency.add(i);next_u+=1
                tpos=out.tell();append(exact_binary(t));lpos=out.tell();append(exact_binary(L))
                records.add(v,eid,tpos,lpos)
                if i%4096==0:check()
                if i and i%500000==0:progress(dict(phase='write_packed',edges=i))
            while next_u<=N:adjacency.add(E);next_u+=1
            if records.count!=E:raise ValueError('arc coverage')
            size=out.tell();out.flush();adjacency.flush();records.flush()
            pwrite(out.fileno(),HEAD.pack(MAGIC,N,E,np,ep,ap,rp,arena),0);out.flush();os.fsync(out.fileno())
        manifest=dict(schema=SCHEMA,graph_identity=expected_identity,nodes=N,edges=E,data_bytes=size,
            data_sha256=sha(path),scope='untrusted complete representation only; no source certificate')
        (folder/'manifest.jsonl').write_text(json.dumps(manifest,separators=(',',':'))+'\n')
        if sha(source_db)!=expected_db_sha:raise ValueError('representation changed during construction')
        return dict(decision='CONSTRUCTED_UNTRUSTED',nodes=N,edges=E,packed_bytes=size,
            packed_sha256=manifest['data_sha256'],source_DB_sha256=expected_db_sha,
            workspace_bytes={p.name:p.stat().st_size for p in folder.iterdir() if p.is_file()},query_plans=plans)
    finally:db.close()


def pool(packed,start,count,expected_start):
    """Sequential bounded literal reader, validating every offset/byte boundary."""
    with packed.path.open('rb',buffering=65536) as offsets,packed.path.open('rb',buffering=65536) as data:
        offsets.seek(start);raw=offsets.read(8)
        if len(raw)!=8:raise ValueError('truncated literal offset')
        at=U64.unpack(raw)[0]
        if at!=expected_start:raise ValueError('uncovered/overlapping literal arena')
        data.seek(at)
        for i in range(count):
            raw=offsets.read(8)
            if len(raw)!=8:raise ValueError('truncated literal offset')
            end=U64.unpack(raw)[0]
            if not at<end<=packed.pages.size:raise ValueError('literal offset order/range')
            if end-at>MAX_LINE:raise ResourceStop('literal byte envelope')
            raw=data.read(end-at)
            if len(raw)!=end-at:raise ValueError('truncated literal arena')
            yield identity(raw.decode('utf-8'));at=end


def arc_rows(packed):
    with packed.path.open('rb',buffering=65536) as f:
        f.seek(packed.rp);remaining=packed.E
        while remaining:
            k=min(4096,remaining);data=f.read(k*ARC.size)
            if len(data)!=k*ARC.size:raise ValueError('truncated arc section')
            yield from ARC.iter_unpack(data);remaining-=k


def compare_quantity(stream,position,text):
    """Independent decode and exact cross-product equality, not writer helper."""
    if stream.tell()!=position:raise ValueError('overlapping/gapped/noncanonical weight arena')
    header=stream.read(8)
    if len(header)!=8:raise ValueError('truncated magnitude header')
    n,d=struct.unpack('<II',header)
    if not n or not d or n+d+8>MAX_LINE:raise ResourceStop('magnitude record envelope')
    a=stream.read(n);b=stream.read(d)
    if len(a)!=n or len(b)!=d:raise ValueError('truncated magnitude')
    if (n>1 and not a[-1]) or (d>1 and not b[-1]):raise ValueError('nonminimal magnitude')
    x,y=int.from_bytes(a,'little'),int.from_bytes(b,'little')
    if x<=0 or y<=0:raise ValueError('nonpositive exact magnitude')
    value=wide_conversion(Fraction,text)
    if x*value.denominator!=y*value.numerator:raise ValueError('exact time/actual length mismatch')
    return max(x.bit_length(),y.bit_length())


def validate(raw_path,packed_path,workspace,*,expected_raw_sha,expected_N,expected_E,
             nodes_path=None,anchors=(),max_db_bytes=2*GIB,max_adjacency_bytes=64*1024**2,
             check=lambda:None,progress=lambda v:None):
    """Full independent raw relation -> literal ranks -> sequential packed join.

    Composite raw PK fixes the edge order without an external sort. UNIQUE eid
    proves injectivity. New rank tables are derived ONLY from raw/explicit nodes.
    Passing certifies graph representation, never shortest paths or EV optima.
    """
    folder=Path(workspace);folder.mkdir(exist_ok=False);db=database(folder/'raw.sqlite',max_db_bytes)
    packed=None;raw_hash=hashlib.sha256();E=0;plans={}
    try:
        db.executescript('''CREATE TABLE nodes(node TEXT COLLATE BINARY PRIMARY KEY) WITHOUT ROWID;
          CREATE TABLE raw(u TEXT COLLATE BINARY,v TEXT COLLATE BINARY,eid TEXT COLLATE BINARY,
            t TEXT NOT NULL,l TEXT NOT NULL,PRIMARY KEY(u,v,eid),UNIQUE(eid)) WITHOUT ROWID;''')
        if nodes_path is not None:db.executemany('INSERT INTO nodes VALUES(?)',((n,) for n in declared_nodes(nodes_path)))
        batch=[];batch_bytes=0
        def flush():
            if nodes_path is None:db.executemany('INSERT OR IGNORE INTO nodes VALUES(?)',((n,) for r in batch for n in r[:2]))
            db.executemany('INSERT INTO raw VALUES(?,?,?,?,?)',batch);batch.clear()
        for row in lines(raw_path,raw_hash):
            if batch and batch_bytes+len(row)>BATCH_BYTES:check();flush();batch_bytes=0
            batch.append(raw_fields(row));batch_bytes+=len(row);E+=1
            if len(batch)>=4096:check();flush();batch_bytes=0
            if E%500000==0:progress(dict(phase='independent_raw',edges=E))
        flush();db.commit()
        if raw_hash.hexdigest()!=expected_raw_sha or E!=expected_E:raise ValueError('full frozen raw identity/count')
        N=db.execute('SELECT count(*) FROM nodes').fetchone()[0]
        if N!=expected_N:raise ValueError('full raw node count')
        packed=Packed.open(packed_path)
        nh=sha(nodes_path) if nodes_path is not None else None
        if (packed.N,packed.E,packed.graph_identity)!=(N,E,graph_identity(expected_raw_sha,nh)):raise ValueError('raw graph ownership/count mismatch')
        plans['nodes']=ranks(db,'nr','SELECT node,row_number() OVER(ORDER BY node COLLATE BINARY)-1 FROM nodes')
        plans['edges']=ranks(db,'er','SELECT eid,row_number() OVER(ORDER BY eid COLLATE BINARY)-1 FROM raw')
        db.commit();check()
        for section,count,table,start in ((packed.np,N,'nr',packed.arena),(packed.ep,E,'er',packed.q(packed.np+8*N))):
            seen=0
            expected=db.execute('SELECT name,r FROM '+table+' ORDER BY name COLLATE BINARY')
            for want,got in itertools.zip_longest(expected,pool(packed,section,count,start)):
                if want is None or got is None or want!=(got,seen):raise ValueError('literal identity bijection/order/coverage mismatch')
                seen+=1
                if seen%4096==0:check()
            if seen!=count:raise ValueError('literal coverage count')
        for anchor in anchors:
            if db.execute('SELECT 1 FROM nr WHERE name=? COLLATE BINARY',(identity(anchor),)).fetchone() is None:raise ValueError('source/terminal/Site anchor absent')
        if 8*(N+1)>max_adjacency_bytes:raise ResourceStop('adjacency offset memory admission; no cropping')
        adjacency=array('Q')
        if adjacency.itemsize!=8:raise ResourceStop('uint64 offset storage unsupported')
        with packed.path.open('rb') as f:f.seek(packed.ap);adjacency.fromfile(f,N+1)
        if sys.byteorder!='little':adjacency.byteswap()
        if adjacency[0]!=0 or adjacency[-1]!=E or any(a>b or b>E for a,b in zip(adjacency,itertools.islice(adjacency,1,None))):raise ValueError('adjacency coverage/ranges')
        sql='''SELECT nu.r,nv.r,em.r,g.t,g.l FROM raw g
          CROSS JOIN nr nu ON nu.name=g.u COLLATE BINARY
          CROSS JOIN nr nv ON nv.name=g.v COLLATE BINARY
          CROSS JOIN er em ON em.name=g.eid COLLATE BINARY
          ORDER BY g.u COLLATE BINARY,g.v COLLATE BINARY,g.eid COLLATE BINARY'''
        plans['join']=no_sort(db,sql);u=0;seen=0;max_bits=0;before=None
        with packed.path.open('rb',buffering=65536) as weights:
            weights.seek(packed.q(packed.ep+8*E))
            for want,got in itertools.zip_longest(db.execute(sql),arc_rows(packed)):
                if want is None or got is None:raise ValueError('missing/extra packed edge')
                while u<N and seen>=adjacency[u+1]:u+=1
                v,eid,t,L=got
                if (u,v,eid)!=want[:3] or not 0<=v<N or not 0<=eid<E:raise ValueError('literal arc bijection/order/direction mismatch')
                key=(u,v,eid)
                if before is not None and not before<key:raise ValueError('noncanonical/duplicate arc')
                before=key
                max_bits=max(max_bits,compare_quantity(weights,t,want[3]),compare_quantity(weights,L,want[4]));seen+=1
                if seen%4096==0:check()
                if seen%500000==0:progress(dict(phase='independent_arc_join',edges=seen))
            if seen!=E or weights.tell()!=packed.pages.size:raise ValueError('uncovered/trailing magnitude bytes')
        packed.assert_unchanged()
        if sha(raw_path)!=expected_raw_sha or (nodes_path is not None and sha(nodes_path)!=nh):raise ValueError('authoritative inputs changed during checking')
        return dict(decision='PASS_COMPLETE_REPRESENTATION_IDENTITY_ONLY',nodes=N,edges=E,
            raw_sha256=expected_raw_sha,packed_sha256=packed.data_sha256,graph_identity=packed.graph_identity,
            literal_node_bijection=True,literal_edge_bijection=True,exact_weights=True,anchors_checked=len(set(anchors)),
            max_observed_component_bits=max_bits,packed_bytes=packed.pages.size,tracking_DB_bytes=(folder/'raw.sqlite').stat().st_size,
            query_plans=plans,source_certified=False,EV_solved=False)
    except sqlite3.IntegrityError as exc:raise ValueError('duplicate raw edge/node identity') from exc
    finally:
        if packed is not None:packed.close()
        db.close()
