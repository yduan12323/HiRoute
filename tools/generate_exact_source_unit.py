"""UNTRUSTED disk-backed exact Dijkstra/source-path exporter.

No production router, result, seed, or relaxation is imported. Its output is
only a candidate certificate, never a shortest-path or whole-table assertion.
All quantities remain arbitrary-precision rationals; all identities literal.
"""
from fractions import Fraction
import heapq
import json
from pathlib import Path

from exact_leg_table import NUMERICAL,SELECTION,identity,sequence
from streaming_road_graph import connect,sha,flush_file
from streaming_road_certificate import Arithmetic,UNIT_SCHEMA,SOURCE_SCHEMA,fields


def emit(stream,row):
    stream.write(json.dumps(row,ensure_ascii=False,separators=(',',':'))+'\n')


def domain(header):
    fields(header,('schema','numerical_contract','selected_leg_contract','graph_identity',
        'origin_anchor','destination_anchor','candidate_order','sites','source_unit'))
    if (header['schema'],header['numerical_contract'],header['selected_leg_contract'])!=(UNIT_SCHEMA,NUMERICAL,SELECTION):
        raise ValueError('unit contract')
    order=sequence(header['candidate_order'],'candidate order');sites=header['sites']
    if type(sites) is not dict or set(sites)!=set(order) or len(set(order))!=len(order):raise ValueError('literal Site coverage')
    aliases=[]
    for site in order:
        identity(site);fields(sites[site],('anchor','effects'));aliases.append(identity(sites[site]['anchor']))
        effects=sequence(sites[site]['effects'],'effects')
        if not effects or len(set(effects))!=len(effects) or not set(effects)<={'C','S','CS'}:raise ValueError('effects')
    S=tuple(sorted({identity(header['origin_anchor']),*aliases}));T=tuple(sorted({identity(header['destination_anchor']),*aliases}))
    if identity(header['source_unit']) not in S:raise ValueError('unit source outside full domain')
    return S,T


def generate(graph_path,header,folder,*,expected_graph_sha,check=lambda:None,progress=lambda v:None):
    """One complete source or an exception/partial workspace. No restart path."""
    S,T=domain(header);source=header['source_unit'];folder=Path(folder);folder.mkdir(exist_ok=False)
    if sha(graph_path)!=expected_graph_sha:raise ValueError('actual frozen graph DB bytes')
    original=connect(graph_path);work=connect(folder/'producer.sqlite',write=True)
    A=Arithmetic();settled=0;edge_visits=0
    try:
        # Additional sorted copy is charged construction, not a free resident
        # adjacency index. SQLite global heap/cache and disk limits apply.
        work.executescript('CREATE TABLE adj(u TEXT COLLATE BINARY,v TEXT COLLATE BINARY,eid TEXT COLLATE BINARY,t TEXT,l TEXT,PRIMARY KEY(u,v,eid)) WITHOUT ROWID;'
            'CREATE TABLE state(n TEXT COLLATE BINARY PRIMARY KEY,d TEXT,pred TEXT,mask TEXT,ord INTEGER UNIQUE) WITHOUT ROWID;')
        for i,(u,v,eid,t,L) in enumerate(original.execute('SELECT u,v,eid,t,l FROM edges')):
            if i%4096==0:check()
            work.execute('INSERT INTO adj VALUES(?,?,?,?,?)',(u,v,eid,t,L))
        for i,(n,) in enumerate(original.execute('SELECT node FROM nodes ORDER BY node COLLATE BINARY')):
            if i%4096==0:check()
            work.execute('INSERT INTO state VALUES(?,NULL,NULL,NULL,NULL)',(n,))
        if not all(work.execute('SELECT 1 FROM state WHERE n=?',(n,)).fetchone() for n in set(S)|set(T)):
            raise ValueError('complete source/terminal/alias anchors missing')
        work.execute('UPDATE state SET d=? WHERE n=?',('0',source));work.commit()
        queue=[(Fraction(0),source)];bits={t:1<<i for i,t in enumerate(T)}
        progress(dict(phase='producer_index_ready',settled_nodes=0))
        while queue:
            d,u=heapq.heappop(queue);prior,order=work.execute('SELECT d,ord FROM state WHERE n=?',(u,)).fetchone()
            if order is not None or A.parse(prior)!=d:continue
            work.execute('UPDATE state SET ord=?,mask=? WHERE n=?',(settled,str(bits.get(u,0)),u));settled+=1
            for v,eid,t,L in work.execute('SELECT v,eid,t,l FROM adj WHERE u=?',(u,)):
                dt=A.parse(t)
                if dt<=0 or A.parse(L)<=0:raise ValueError('strictly positive edge support required')
                candidate=A.add(d,dt);old,order=work.execute('SELECT d,ord FROM state WHERE n=?',(v,)).fetchone()
                if old is None or A.less(candidate,A.parse(old)):
                    if order is not None:raise ValueError('settled label improved: unsupported graph/corruption')
                    work.execute('UPDATE state SET d=?,pred=? WHERE n=?',(A.text(candidate),eid,v));heapq.heappush(queue,(candidate,v))
                edge_visits+=1
                if edge_visits%1024==0:check()
            if settled%4096==0:
                check();work.commit();progress(dict(phase='dijkstra',settled_nodes=settled,edge_visits=edge_visits,heap_entries=len(queue)))
        work.commit();check();progress(dict(phase='all_labels',settled_nodes=settled,edge_visits=edge_visits))
        # Positive tight edges form a DAG. Reverse settlement order computes
        # exact target-reach masks; no floating label ordering or depth cap.
        for i,(u,du,mask) in enumerate(work.execute('SELECT n,d,mask FROM state WHERE ord IS NOT NULL ORDER BY ord DESC')):
            value=A.parse(du);m=int(mask)
            for v,t in work.execute('SELECT v,t FROM adj WHERE u=?',(u,)):
                dv,mv=work.execute('SELECT d,mask FROM state WHERE n=?',(v,)).fetchone()
                if dv is not None and A.add(value,A.parse(t))==A.parse(dv):m|=int(mv)
            work.execute('UPDATE state SET mask=? WHERE n=?',(str(m),u))
            if i%1024==0:check()
        work.commit();check()
        paths=folder/'paths.jsonl'
        with paths.open('x') as stream:
            emit(stream,header)
            for target in T:
                check();dt=work.execute('SELECT d FROM state WHERE n=?',(target,)).fetchone()[0]
                steps=[];length=Fraction(0);u=source
                if dt is not None:
                    while u!=target:
                        check();du=A.parse(work.execute('SELECT d FROM state WHERE n=?',(u,)).fetchone()[0]);chosen=None
                        # (next literal node, full literal edge-ID) order gives
                        # canonical full node tuple, then full edge-ID tuple.
                        for v,eid,t,L in work.execute('SELECT v,eid,t,l FROM adj WHERE u=? ORDER BY v COLLATE BINARY,eid COLLATE BINARY',(u,)):
                            dv,mv=work.execute('SELECT d,mask FROM state WHERE n=?',(v,)).fetchone()
                            if dv is not None and int(mv)&bits[target] and A.add(du,A.parse(t))==A.parse(dv):
                                chosen=(v,eid,L);break
                        if chosen is None:raise ValueError('no tight target-reaching successor')
                        v,eid,L=chosen;steps.append((u,v,eid));length=A.add(length,A.parse(L));u=v
                emit(stream,dict(kind='pair',source=source,target=target,reachable=dt is not None,
                    time_s=dt,length_m=A.text(length) if dt is not None else None,first_node=source if dt is not None else None))
                for u,v,eid in steps:emit(stream,dict(kind='step',u=u,v=v,edge_id=eid))
                emit(stream,dict(kind='end_pair'))
        flush_file(paths);table_hash=sha(paths)
        certificate=folder/'source.jsonl'
        with certificate.open('x') as stream:
            emit(stream,dict(schema=SOURCE_SCHEMA,graph_sha256=header['graph_identity'].removeprefix('sha256:'),
                table_sha256=table_hash,source=source,target_order=list(T)))
            for i,(n,d,p,m) in enumerate(work.execute('SELECT n,d,pred,mask FROM state ORDER BY n COLLATE BINARY')):
                if i%4096==0:check()
                emit(stream,dict(node=n,label=d,predecessor_edge_id=p,mask=m))
        flush_file(certificate);check()
        if sha(graph_path)!=expected_graph_sha:raise ValueError('graph changed during untrusted generation')
        return dict(scope='untrusted single-source candidate only',source=source,source_denominator=len(S),pair_denominator=len(S)*len(T),
            candidate_pairs=len(T),settled_nodes=settled,edge_visits=edge_visits,paths_sha256=table_hash,
            source_sha256=sha(certificate),whole_table_certified=False)
    finally:work.close();original.close()
