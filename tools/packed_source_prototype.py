"""Synthetic-only compact CSR construction; untrusted exact source exporter.

No real packing/scan entry point. The runtime uses bounded pread pages, dense
labels and an indexed heap, never per-edge SQL or a global denominator LCM.
Output is candidate JSONL for the unchanged independent full-graph checker.
"""
from array import array
from collections import OrderedDict
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
import os
import re
from pathlib import Path
import struct
import sys
import time

from exact_leg_table import identity
from streaming_road_graph import MAX_LINE,ResourceStop,sha,flush_file,json_line,lines
from streaming_road_certificate import Arithmetic,SOURCE_SCHEMA
from generate_exact_source_unit import domain,emit

MAGIC=b'HRCSR001'
HEAD=struct.Struct('<8s7Q')
ARC=struct.Struct('<IIQQ')
U64=struct.Struct('<Q')
U32=struct.Struct('<I')
SENTINEL=2**32-1
MAX_SYNTHETIC_N=8192
MAX_SYNTHETIC_E=32768


def ints(code,n,value=0):
    result=array(code,[value])*n
    if result.itemsize!={'I':4,'Q':8}[code]:raise ResourceStop('unsupported index storage width')
    return result


def write_q(stream,values):
    for v in values:
        if not 0<=v<2**64:raise ResourceStop('file offset envelope')
        stream.write(U64.pack(v))


def build_synthetic(graph,folder,check=lambda:None):
    if graph.node_count>MAX_SYNTHETIC_N or graph.edge_count>MAX_SYNTHETIC_E:
        raise ResourceStop('synthetic constructor envelope; real packing not admitted')
    folder=Path(folder);folder.mkdir(exist_ok=False);nodes=tuple(graph.nodes());N=len(nodes)
    edges=tuple(graph.raw_edges(check));E=len(edges)
    if N>=SENTINEL or E>=SENTINEL:raise ResourceStop('proven uint32 index domain required')
    node_ids={n:i for i,n in enumerate(nodes)};ids=tuple(sorted(e.edge_id for e in edges));edge_ids={e:i for i,e in enumerate(ids)}
    if len(node_ids)!=N or len(edge_ids)!=E:raise ValueError('literal identity collision')
    ordered=sorted(edges,key=lambda e:(node_ids[e.source],node_ids[e.target],edge_ids[e.edge_id]))
    np=HEAD.size;ep=np+8*(N+1);ap=ep+8*(E+1);rp=ap+8*(N+1);arena=rp+ARC.size*E
    path=folder/'graph.csr';node_offsets=[];id_offsets=[];adj=[0]*(N+1);arcs=[]
    with path.open('xb') as stream:
        stream.seek(arena)
        for text in nodes:
            node_offsets.append(stream.tell());stream.write(text.encode('utf-8'))
        node_offsets.append(stream.tell())
        for text in ids:
            id_offsets.append(stream.tell());stream.write(text.encode('utf-8'))
        id_offsets.append(stream.tell())
        def rational(value):
            if value<=0:raise ValueError('positive graph weights required')
            n=value.numerator.to_bytes(max(1,(value.numerator.bit_length()+7)//8),'little')
            d=value.denominator.to_bytes(max(1,(value.denominator.bit_length()+7)//8),'little')
            if len(n)+len(d)+8>MAX_LINE:raise ResourceStop('binary rational record envelope')
            pos=stream.tell();stream.write(struct.pack('<II',len(n),len(d)));stream.write(n);stream.write(d);return pos
        for i,e in enumerate(ordered):
            if i%1024==0:check()
            arcs.append((node_ids[e.target],edge_ids[e.edge_id],rational(e.time),rational(e.length)))
            adj[node_ids[e.source]+1]+=1
        for i in range(N):adj[i+1]+=adj[i]
        size=stream.tell()
        if size>4*1024**3:raise ResourceStop('packed storage envelope')
        stream.seek(0);stream.write(HEAD.pack(MAGIC,N,E,np,ep,ap,rp,arena))
        write_q(stream,node_offsets);write_q(stream,id_offsets);write_q(stream,adj)
        for row in arcs:stream.write(ARC.pack(*row))
    flush_file(path)
    manifest=dict(schema='hiroute.synthetic_csr.v1',graph_identity=graph.payload_sha256,nodes=N,edges=E,
        data_bytes=size,data_sha256=sha(path),scope='untrusted candidate graph; not a road certificate')
    (folder/'manifest.jsonl').write_text(json.dumps(manifest,separators=(',',':'))+'\n')
    graph.assert_unchanged();return path


class Pages:
    def __init__(self,path,limit=16*1024**2,page=65536):
        if limit<page or limit%page:raise ValueError('whole bounded pages required')
        self.fd=os.open(path,os.O_RDONLY);self.size=os.fstat(self.fd).st_size;self.page=page;self.capacity=limit//page
        self.cache=OrderedDict();self.read_bytes=0;self.hits=0;self.misses=0;self.peak_bytes=0;self.resident_bytes=0
    def read(self,pos,size):
        if type(pos) is not int or type(size) is not int or pos<0 or size<0 or pos+size>self.size:raise ValueError('bounded packed record range')
        if size>MAX_LINE:raise ResourceStop('bounded record buffer')
        chunks=[];left=size
        while left:
            index=pos//self.page;within=pos%self.page
            if index in self.cache:self.hits+=1;data=self.cache.pop(index)
            else:
                self.misses+=1;data=os.pread(self.fd,self.page,index*self.page);self.read_bytes+=len(data)
                if len(self.cache)>=self.capacity:self.resident_bytes-=len(self.cache.popitem(last=False)[1])
                self.resident_bytes+=len(data)
            self.cache[index]=data;take=min(left,len(data)-within)
            if take<=0:raise ValueError('short packed page')
            chunks.append(data[within:within+take]);pos+=take;left-=take
            self.peak_bytes=max(self.peak_bytes,self.resident_bytes)
        return b''.join(chunks)
    def close(self):os.close(self.fd)


@dataclass(frozen=True,init=False)
class Packed:
    path: object
    manifest_path: object
    data_sha256: str
    manifest_sha256: str
    graph_identity: str
    N: int
    E: int
    np: int
    ep: int
    ap: int
    rp: int
    arena: int
    pages: object
    @classmethod
    def open(cls,path,cache_bytes=16*1024**2):
        path=Path(path);mp=path.parent/'manifest.jsonl';rows=iter(lines(mp))
        try:first=next(rows,None);extra=next(rows,None)
        finally:rows.close()
        if first is None or extra is not None:raise ValueError('single bounded manifest required')
        m=json_line(first);expected={'schema','graph_identity','nodes','edges','data_bytes','data_sha256','scope'}
        if type(m) is not dict or set(m)!=expected or m['schema'] not in ('hiroute.synthetic_csr.v1','hiroute.packed_csr.v1'):raise ValueError('manifest shape')
        if any(type(m[k]) is not str or not re.fullmatch('[0-9a-f]{64}',m[k]) for k in ('graph_identity','data_sha256')):raise ValueError('actual digest shape')
        if type(m['nodes']) is not int or type(m['edges']) is not int or not 0<m['nodes']<SENTINEL or not 0<=m['edges']<SENTINEL:raise ResourceStop('proven index envelope')
        if path.stat().st_size!=m['data_bytes'] or not HEAD.size<=m['data_bytes']<=4*1024**3:raise ValueError('actual packed size')
        digest=sha(path)
        if digest!=m['data_sha256']:raise ValueError('actual packed identity')
        pages=Pages(path,cache_bytes)
        try:
            magic,N,E,np,ep,ap,rp,arena=HEAD.unpack(pages.read(0,HEAD.size))
            if (magic,N,E)!=(MAGIC,m['nodes'],m['edges']) or (np,ep,ap,rp,arena)!=(HEAD.size,HEAD.size+8*(N+1),HEAD.size+8*(N+1)+8*(E+1),HEAD.size+16*(N+1)+8*(E+1),HEAD.size+16*(N+1)+8*(E+1)+ARC.size*E):raise ValueError('section layout/domain')
            if arena>pages.size:raise ValueError('truncated sections')
            obj=object.__new__(cls)
            for k,v in dict(path=path.resolve(),manifest_path=mp.resolve(),data_sha256=digest,manifest_sha256=sha(mp),graph_identity=identity(m['graph_identity']),N=N,E=E,np=np,ep=ep,ap=ap,rp=rp,arena=arena,pages=pages).items():object.__setattr__(obj,k,v)
            return obj
        except BaseException:pages.close();raise
    def q(self,pos):return U64.unpack(self.pages.read(pos,8))[0]
    def text(self,start,index,count):
        if type(index) is not int or not 0<=index<count:raise ValueError('literal index range')
        a,b=self.q(start+8*index),self.q(start+8*(index+1))
        if not self.arena<=a<b<=self.pages.size:raise ValueError('literal string offsets')
        return identity(self.pages.read(a,b-a).decode('utf-8'))
    def node(self,i):return self.text(self.np,i,self.N)
    def eid(self,i):return self.text(self.ep,i,self.E)
    def find_node(self,name):
        identity(name);a=0;b=self.N
        while a<b:
            mid=(a+b)//2;value=self.node(mid)
            if value<name:a=mid+1
            else:b=mid
        if a>=self.N or self.node(a)!=name:raise ValueError('source/target anchor missing')
        return a
    def arc(self,i):
        if not 0<=i<self.E:raise ValueError('arc index')
        row=ARC.unpack(self.pages.read(self.rp+i*ARC.size,ARC.size))
        if row[0]>=self.N or row[1]>=self.E or not all(self.arena<=p<self.pages.size for p in row[2:]):raise ValueError('arc reference bounds')
        return row
    def outgoing(self,u):
        if not 0<=u<self.N:raise ValueError('vertex index')
        a,b=self.q(self.ap+8*u),self.q(self.ap+8*(u+1))
        if not 0<=a<=b<=self.E:raise ValueError('adjacency offsets')
        prior=None
        for i in range(a,b):
            row=self.arc(i);key=row[:2]
            if prior is not None and not prior<key:raise ValueError('noncanonical/duplicate arc order')
            prior=key;yield i,row
    def rational(self,pos,A):
        n,d=struct.unpack('<II',self.pages.read(pos,8))
        if not n or not d or n+d+8>MAX_LINE:raise ResourceStop('binary rational byte envelope')
        raw=self.pages.read(pos+8,n+d);a=int.from_bytes(raw[:n],'little');b=int.from_bytes(raw[n:],'little')
        if not a or not b:raise ValueError('positive rational required')
        A.admit(Fraction(a),Fraction(b));value=Fraction(a,b);A.admit(value);return value
    def assert_unchanged(self):
        if sha(self.path)!=self.data_sha256 or sha(self.manifest_path)!=self.manifest_sha256:raise ValueError('packed input changed')
    def close(self):self.pages.close()


def validate_synthetic_pack(graph,packed,check=lambda:None):
    if graph.node_count>MAX_SYNTHETIC_N or graph.edge_count>MAX_SYNTHETIC_E:raise ResourceStop('synthetic validation only')
    if (graph.payload_sha256,graph.node_count,graph.edge_count)!=(packed.graph_identity,packed.N,packed.E):raise ValueError('actual source graph identity/counts')
    if tuple(packed.node(i) for i in range(packed.N))!=tuple(graph.nodes()):raise ValueError('literal node bijection/order')
    previous=None;seen=bytearray(packed.E);count=0;A=Arithmetic()
    for i in range(packed.E):
        text=packed.eid(i)
        if previous is not None and not previous<text:raise ValueError('literal edge bijection/order')
        previous=text
    if packed.q(packed.ap)!=0 or packed.q(packed.ap+8*packed.N)!=packed.E:raise ValueError('adjacency coverage')
    for u in range(packed.N):
        check()
        for index,(v,eid,t,L) in packed.outgoing(u):
            if seen[eid]:raise ValueError('duplicate packed edge identity')
            seen[eid]=1;e=graph.edge(packed.eid(eid))
            if (e.source,e.target,e.time,e.length)!=(packed.node(u),packed.node(v),packed.rational(t,A),packed.rational(L,A)):raise ValueError('actual edge tuple/weights')
            count+=1
    if count!=packed.E or not all(seen):raise ValueError('missing packed edge')
    packed.assert_unchanged();graph.assert_unchanged();return dict(scope='synthetic representation only',nodes=packed.N,edges=count)


class Transcript:
    """Hash reference JSON without retaining a duplicate uncompressed file."""
    def __init__(self):self.hash=hashlib.sha256();self.bytes=0
    def __enter__(self):return self
    def __exit__(self,*unused):return False
    def write(self,text):
        value=text.encode('utf-8');self.hash.update(value);self.bytes+=len(value);return len(text)


class Labels:
    def __init__(self,n,limit):self.values=[None]*n;self.bytes=0;self.peak=0;self.max_bits=0;self.limit=limit
    @staticmethod
    def size(v):return 0 if v is None else sys.getsizeof(v)+sys.getsizeof(v.numerator)+sys.getsizeof(v.denominator)
    def put(self,i,value):
        if type(value) is not Fraction:raise TypeError('exact Fraction labels required')
        amount=self.size(value)
        if self.bytes+amount>self.limit:raise ResourceStop('exact label storage; no precision clipping')
        self.peak=max(self.peak,self.bytes+amount);self.bytes+=amount-self.size(self.values[i]);self.values[i]=value
        self.max_bits=max(self.max_bits,value.numerator.bit_length()+value.denominator.bit_length())


class IndexedHeap:
    def __init__(self,n,labels,A):self.ids=ints('I',n);self.positions=ints('I',n,SENTINEL);self.size=0;self.peak=0;self.labels=labels;self.A=A;self.compares=0
    def less(self,a,b):
        x,y=self.labels.values[a],self.labels.values[b];self.A.admit(x,y);self.compares+=1
        return x<y or (x==y and a<b)
    def swap(self,a,b):
        x,y=self.ids[a],self.ids[b];self.ids[a],self.ids[b]=y,x;self.positions[x],self.positions[y]=b,a
    def changed(self,v):
        p=self.positions[v]
        if p==SENTINEL:
            if self.size>=len(self.ids):raise ValueError('indexed frontier overflow')
            p=self.size;self.ids[p]=v;self.positions[v]=p;self.size+=1;self.peak=max(self.peak,self.size)
        while p and self.less(self.ids[p],self.ids[(p-1)//2]):self.swap(p,(p-1)//2);p=(p-1)//2
    def pop(self):
        if not self.size:raise ValueError('empty frontier')
        result=self.ids[0];self.size-=1;self.positions[result]=SENTINEL
        if self.size:
            self.ids[0]=self.ids[self.size];self.positions[self.ids[0]]=0;p=0
            while 2*p+1<self.size:
                c=2*p+1
                if c+1<self.size and self.less(self.ids[c+1],self.ids[c]):c+=1
                if not self.less(self.ids[c],self.ids[p]):break
                self.swap(p,c);p=c
        return result


def bounded_emit(stream,value):
    def size(v):
        if type(v) is str:return 2+6*len(v.encode('utf-8'))
        if v is None or type(v) is bool:return 5
        if type(v) is dict:
            total=2
            for k,w in v.items():
                total+=size(k)+size(w)+2
                if total>MAX_LINE:raise ResourceStop('JSON record buffer')
            return total
        if isinstance(v,(list,tuple)):
            total=2
            for w in v:
                total+=size(w)+1
                if total>MAX_LINE:raise ResourceStop('JSON record buffer')
            return total
        raise TypeError('bounded JSON output type')
    if size(value)>MAX_LINE:raise ResourceStop('JSON record buffer')
    emit(stream,value)


def generate(packed,header,folder,*,label_bytes=512*1024**2,check=lambda:None):
    call_cpu,call_wall=time.process_time(),time.monotonic()
    if struct.calcsize('P')>8:raise ResourceStop('pointer-size resource profile')
    S,T=domain(header)
    if header['graph_identity']!='sha256:'+packed.graph_identity:raise ValueError('original graph identity')
    N=packed.N;K=len(T);B=(K+7)//8
    # Structural state allocation admission, independent of a tiny RSS sample.
    fixed=8*N+4*N*4+N+B*N # refs,pred/order/heap/positions,settled,masks
    if fixed+label_bytes+(16+16+16+128+4)*1024**2>1024**3:raise ResourceStop('whole prototype state admission')
    out=Path(folder);out.mkdir(exist_ok=False);A=Arithmetic();labels=Labels(N,label_bytes);source=packed.find_node(header['source_unit'])
    targets=[packed.find_node(t) for t in T];bits={v:1<<i for i,v in enumerate(targets)}
    pred=ints('I',N,SENTINEL);order=ints('I',N);done=bytearray(N);masks=bytearray(N*B);front=IndexedHeap(N,labels,A);labels.put(source,Fraction(0));front.changed(source)
    phases=[];metrics=dict(SQL_execute_calls=0,edge_visits=0,weight_decodes=0,settled_nodes=0);c0=call_cpu;w0=call_wall
    io_start=(packed.pages.hits,packed.pages.misses,packed.pages.read_bytes)
    def phase(name):
        nonlocal c0,w0
        check();c,w=time.process_time(),time.monotonic();phases.append(dict(phase=name,CPU_s=c-c0,wall_s=w-w0));c0,w0=c,w
    def value(pos):metrics['weight_decodes']+=1;return packed.rational(pos,A)
    def mask(i):return int.from_bytes(masks[i*B:(i+1)*B],'little')
    def setmask(i,v):
        if v<0 or v.bit_length()>K:raise ValueError('mask bit domain')
        masks[i*B:(i+1)*B]=v.to_bytes(B,'little')
    packed.assert_unchanged();phase('identity_and_admission')
    count=0
    while front.size:
        check();u=front.pop()
        if done[u]:raise ValueError('duplicate settled vertex')
        done[u]=1;order[count]=u;count+=1;du=labels.values[u]
        for index,(v,eid,tp,lp) in packed.outgoing(u):
            dt=value(tp);candidate=A.add(du,dt);old=labels.values[v]
            if old is None or A.less(candidate,old):
                if done[v]:raise ValueError('positive settled label improved')
                labels.put(v,candidate);pred[v]=index;front.changed(v)
            metrics['edge_visits']+=1
            if metrics['edge_visits']%1024==0:check()
    metrics['settled_nodes']=count;phase('labels')
    for k in range(count-1,-1,-1):
        u=order[k];m=bits.get(u,0);du=labels.values[u]
        for index,(v,eid,tp,lp) in packed.outgoing(u):
            if labels.values[v] is not None and A.add(du,value(tp))==labels.values[v]:m|=mask(v)
        setmask(u,m)
        if k%1024==0:check()
    phase('tight_masks')
    def path(target):
        u=source;visited=0
        while u!=target:
            check();chosen=None;du=labels.values[u]
            for index,(v,eid,tp,lp) in packed.outgoing(u):
                if labels.values[v] is not None and mask(v)&bits[target] and A.add(du,value(tp))==labels.values[v]:chosen=(index,v,eid,lp);break
            if chosen is None:raise ValueError('no tight target successor')
            index,v,eid,lp=chosen;yield u,v,eid,lp;u=v;visited+=1
            if visited>=N:raise ValueError('positive tight DAG path cannot cycle')
    paths=out/'paths.jsonl'
    with paths.open('x') as stream:
        bounded_emit(stream,header)
        for name,target in zip(T,targets):
            dt=labels.values[target];L=Fraction(0)
            if dt is not None:
                for u,v,eid,lp in path(target):L=A.add(L,value(lp))
            pair_bound=512+6*(len(header['source_unit'].encode())+len(name.encode()))
            if dt is not None:pair_bound+=dt.numerator.bit_length()+dt.denominator.bit_length()+L.numerator.bit_length()+L.denominator.bit_length()
            if pair_bound>MAX_LINE:raise ResourceStop('exact pair record buffer')
            bounded_emit(stream,dict(kind='pair',source=header['source_unit'],target=name,reachable=dt is not None,time_s=A.text(dt) if dt is not None else None,length_m=A.text(L) if dt is not None else None,first_node=header['source_unit'] if dt is not None else None))
            if dt is not None:
                for u,v,eid,lp in path(target):bounded_emit(stream,dict(kind='step',u=packed.node(u),v=packed.node(v),edge_id=packed.eid(eid)))
            bounded_emit(stream,dict(kind='end_pair'))
    flush_file(paths);phase('paths_two_pass_stream')
    certificate=out/'source.jsonl'
    reference=Transcript()
    with reference as stream:
        bounded_emit(stream,dict(schema=SOURCE_SCHEMA,graph_sha256=packed.graph_identity,table_sha256=sha(paths),source=header['source_unit'],target_order=list(T)))
        for u in range(N):
            if u%1024==0:check()
            dt=labels.values[u];eid=packed.eid(packed.arc(pred[u])[1]) if pred[u]!=SENTINEL else None
            # Pre-admit decimal/JSON buffers from bit lengths before conversion.
            node=packed.node(u);upper=256+6*(len(node.encode())+len(eid.encode()) if eid else len(node.encode()))
            if dt is not None:upper+=dt.numerator.bit_length()+dt.denominator.bit_length()+K
            if upper>MAX_LINE:raise ResourceStop('source record buffer; no precision clipping')
            bounded_emit(stream,dict(node=node,label=A.text(dt) if dt is not None else None,predecessor_edge_id=eid,mask=str(mask(u)) if dt is not None else None))
    phase('source_reference_transcript')
    from packed_source_certificate_codec import write_certificate,decode_certificate
    encoded=write_certificate(out/'source.binary',packed,header,sha(paths),labels,pred,masks,check)
    phase('binary_certificate')
    decoded=decode_certificate(out/'source.binary',certificate,packed,header,sha(paths),check)
    if decoded['decoded_sha256']!=reference.hash.hexdigest() or decoded['decoded_bytes']!=reference.bytes:raise ValueError('lossless source transcript mismatch')
    phase('lossless_decode_and_source_file');packed.assert_unchanged();phase('final_identity')
    paths_hash,source_hash=sha(paths),sha(certificate);phase('output_hashes')
    return dict(scope='untrusted synthetic prototype only',source=header['source_unit'],source_denominator=len(S),pair_denominator=len(S)*len(T),candidate_pairs=K,
        paths_sha256=paths_hash,source_sha256=source_hash,whole_table_certified=False,metrics=dict(metrics,heap_peak=front.peak,heap_compares=front.compares,label_peak_accounted_bytes=labels.peak,max_label_bits=labels.max_bits,cache_peak_bytes=packed.pages.peak_bytes,page_hits=packed.pages.hits-io_start[0],page_misses=packed.pages.misses-io_start[1],pread_bytes=packed.pages.read_bytes-io_start[2],IO_counter_scope='pread only; SHA reads excluded; cache can be shared/warm; generator SQL zero does not describe pack/check',fixed_state_formula_bytes=fixed),phases=phases,output_bytes=dict(paths=paths.stat().st_size,certificate=certificate.stat().st_size,binary=encoded['encoded_bytes']),lossless_codec={**encoded,**decoded})
