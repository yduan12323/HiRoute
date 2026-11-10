"""Lossless bounded path transport for the same independent exact leg input.

No road selection certificate is implied. All public readers derive ownership
from actual files and validate every pair/frame before exposing numeric data.
"""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import zlib

from .exact_leg_table import ExactLegTable,unique
from .packing_output_limits import LimitedFile

SCHEMA='hiroute.split_exact_selected_legs.v1'
CHUNK=65536
LIMITS=dict(numeric=4*1024**2,index=4*1024**2,manifest=1024**2,
            paths=256*1024**2,frame=16*1024**2,decoded=1024**3,identity=65536)
NAMES=('numeric.json','paths.index.json','paths.bin')


def digest(path,check=lambda:None):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(CHUNK),b''):check();h.update(block)
    return h.hexdigest()


def metadata(path,limit):
    with Path(path).open('rb') as f:data=f.read(limit+1)
    if len(data)>limit:raise ValueError('metadata byte quota before decoding')
    return json.loads(data,object_pairs_hook=unique,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('nonfinite JSON'))),data


def integer(x):
    if type(x) is not int or x<0:raise ValueError('nonnegative integer descriptor required')
    return x


def write(root,header,records,provenance,check=lambda:None,progress=lambda n:None,limits=None):
    """One new output root. No partial recovery or promotion path exists."""
    root=Path(root);limits=dict(LIMITS,**(limits or {}))
    root.mkdir(exist_ok=True)
    if any((root/n).exists() or (root/(n+'.partial')).exists() for n in (*NAMES,'manifest.json')):
        raise ValueError('existing split output; inspect, never repeat')
    numeric=[];index=[];seen=set();decoded_total=0
    with LimitedFile(root/'paths.bin.partial','xb',limits['paths']) as f:
        for row in records:
            check();key=(row['source'],row['target'])
            if key in seen:raise ValueError('duplicate generated pair')
            seen.add(key)
            for x in (*row['nodes'],*row['edges']):
                if type(x) is not str or len(x.encode('utf-8'))>limits['identity']:raise ValueError('literal identity quota')
            plain=hashlib.sha256();encoded=hashlib.sha256();size=0;start=f.bytes
            c=zlib.compressobj()
            for token in json.JSONEncoder(separators=(',',':'),allow_nan=False).iterencode(row):
                # JSONEncoder may return a large literal token: bound each write.
                raw=token.encode('utf-8');size+=len(raw);decoded_total+=len(raw)
                if size>limits['frame'] or decoded_total>limits['decoded']:raise ValueError('decoded path quota')
                plain.update(raw)
                for i in range(0,len(raw),CHUNK):
                    block=c.compress(raw[i:i+CHUNK]);f.write(block);encoded.update(block)
            block=c.flush();f.write(block);encoded.update(block)
            numeric.append({k:v for k,v in row.items() if k not in ('nodes','edges')})
            index.append(dict(source=key[0],target=key[1],ordinal=len(index),offset=start,
                encoded_bytes=f.bytes-start,decoded_bytes=size,nodes=len(row['nodes']),edges=len(row['edges']),
                encoded_sha256=encoded.hexdigest(),decoded_sha256=plain.hexdigest()))
            progress(len(index))
        f.flush();os.fsync(f.fileno())
    for name,obj,cap in [('numeric.json',dict(header,pairs=numeric),limits['numeric']),('paths.index.json',index,limits['index'])]:
        with LimitedFile(root/(name+'.partial'),'x',cap) as f:
            for token in json.JSONEncoder(separators=(',',':'),allow_nan=False).iterencode(obj):f.write(token)
            f.flush();os.fsync(f.fileno())
    files={}
    for name in NAMES:
        path=root/(name+'.partial');files[name]=dict(bytes=path.stat().st_size,sha256=digest(path,check))
        path.replace(root/name);(root/name).chmod(0o444)
    manifest=dict(schema=SCHEMA,codec='zlib_single_json_record_v1',files=files,
                  pair_count=len(index),provenance=provenance)
    with LimitedFile(root/'manifest.json.partial','x',limits['manifest']) as f:
        f.write(json.dumps(manifest,separators=(',',':'),allow_nan=False));f.flush();os.fsync(f.fileno())
    (root/'manifest.json.partial').replace(root/'manifest.json');(root/'manifest.json').chmod(0o444)
    return len(index),digest(root/'manifest.json',check)


class Endpoints:
    """A bounded-cache temporary consistency map, not a second road graph."""
    def __init__(self,path):
        self.db=sqlite3.connect(path)
        self.db.execute('PRAGMA cache_size=-4096');self.db.execute('PRAGMA journal_mode=OFF')
        self.db.execute('CREATE TABLE endpoints(e TEXT PRIMARY KEY COLLATE BINARY,u TEXT,v TEXT) WITHOUT ROWID')
    def __contains__(self,e):return self.db.execute('SELECT 1 FROM endpoints WHERE e=?',(e,)).fetchone() is not None
    def get(self,e):
        row=self.db.execute('SELECT u,v FROM endpoints WHERE e=?',(e,)).fetchone()
        return tuple(row) if row is not None else None
    def __getitem__(self,e):return tuple(self.db.execute('SELECT u,v FROM endpoints WHERE e=?',(e,)).fetchone())
    def __setitem__(self,e,p):self.db.execute('INSERT OR IGNORE INTO endpoints VALUES(?,?,?)',(e,*p))
    def close(self):self.db.close()


class Store:
    def __init__(self,root,check,limits):
        self.root=Path(root);self.check=check;self.limits=limits;self.f=None
        manifest,data=metadata(self.root/'manifest.json',limits['manifest'])
        if manifest.get('schema')!=SCHEMA or manifest.get('codec')!='zlib_single_json_record_v1' or set(manifest['files'])!=set(NAMES):
            raise ValueError('split schema/files mismatch')
        self.sha=hashlib.sha256(data).hexdigest();self.manifest=manifest
        for name in NAMES:
            cap=limits['paths' if name=='paths.bin' else 'numeric' if name=='numeric.json' else 'index']
            path=self.root/name;record=manifest['files'][name]
            if path.stat().st_size>cap or path.stat().st_size!=integer(record['bytes']) or digest(path,check)!=record['sha256']:
                raise ValueError('immutable split file mismatch')
        self.numeric,numeric_bytes=metadata(self.root/'numeric.json',limits['numeric'])
        self.index,index_bytes=metadata(self.root/'paths.index.json',limits['index'])
        for name,data in [('numeric.json',numeric_bytes),('paths.index.json',index_bytes)]:
            if len(data)!=manifest['files'][name]['bytes'] or hashlib.sha256(data).hexdigest()!=manifest['files'][name]['sha256']:
                raise ValueError('parsed metadata bytes changed')
        if type(self.index) is not list or type(self.numeric.get('pairs')) is not list:raise ValueError('explicit pair/index arrays')
        if len(self.index)!=len(self.numeric['pairs']) or len(self.index)!=integer(manifest['pair_count']):raise ValueError('pair/index cardinality')
        # Bound Cartesian construction by the physically bounded explicit index.
        sources={self.numeric['origin_anchor'],*(x['anchor'] for x in self.numeric['sites'].values())}
        targets={self.numeric['destination_anchor'],*(x['anchor'] for x in self.numeric['sites'].values())}
        if len(sources)*len(targets)!=len(self.index):raise ValueError('exhaustive pair cardinality')
        self.bykey={};offset=total=0
        fields={'source','target','ordinal','offset','encoded_bytes','decoded_bytes','nodes','edges','encoded_sha256','decoded_sha256'}
        for i,(item,row) in enumerate(zip(self.index,self.numeric['pairs'])):
            if set(item)!=fields:raise ValueError('frame descriptor shape')
            key=(item['source'],item['target'])
            if key in self.bykey or key!=(row['source'],row['target']) or integer(item['ordinal'])!=i or integer(item['offset'])!=offset:
                raise ValueError('duplicate/mismatched/gapped frame')
            n=integer(item['encoded_bytes']);decoded=integer(item['decoded_bytes'])
            if n==0 or n>limits['paths'] or decoded>limits['frame']:raise ValueError('frame resource bound')
            integer(item['nodes']);integer(item['edges']);offset+=n;total+=decoded;self.bykey[key]=i
        if offset!=manifest['files']['paths.bin']['bytes'] or total>limits['decoded']:raise ValueError('trailing/missing frames or decoded quota')
        self.f=(self.root/'paths.bin').open('rb',buffering=0)
        # Bind the descriptor actually opened, rather than an unchecked replacement.
        try:
            h=hashlib.sha256()
            for block in iter(lambda:self.f.read(CHUNK),b''):check();h.update(block)
            if h.hexdigest()!=manifest['files']['paths.bin']['sha256']:raise ValueError('opened path descriptor changed')
            stat=os.fstat(self.f.fileno())
            self.stamp=(stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)
        except BaseException:self.close();raise
    def close(self):
        if self.f is not None:self.f.close();self.f=None
    def row(self,key):
        self.check();i=self.bykey[key];item=self.index[i]
        if self.f is None:raise ValueError('closed owned path store')
        stat=os.fstat(self.f.fileno())
        if (stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)!=self.stamp:
            raise ValueError('owned path descriptor modified')
        self.f.seek(item['offset']);remaining=item['encoded_bytes'];d=zlib.decompressobj()
        encoded=hashlib.sha256();plain=hashlib.sha256();out=bytearray()
        while remaining:
            self.check();block=self.f.read(min(CHUNK,remaining))
            if not block:raise ValueError('truncated path frame')
            remaining-=len(block);encoded.update(block)
            while block:
                piece=d.decompress(block,min(CHUNK,item['decoded_bytes']-len(out)+1))
                out.extend(piece);plain.update(piece)
                if len(out)>item['decoded_bytes'] or len(out)>self.limits['frame']:raise ValueError('decompression quota')
                if d.unused_data:raise ValueError('extra compressed stream/data')
                block=d.unconsumed_tail
        if not d.eof or len(out)!=item['decoded_bytes'] or encoded.hexdigest()!=item['encoded_sha256'] or plain.hexdigest()!=item['decoded_sha256']:
            raise ValueError('incomplete/mismatched path frame')
        row=json.loads(out,object_pairs_hook=unique,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('nonfinite JSON')))
        if type(row) is not dict or set(row)!={'source','target','reachable','time_s','actual_length_m','nodes','edges'}:
            raise ValueError('path record shape')
        if {k:v for k,v in row.items() if k not in ('nodes','edges')}!=self.numeric['pairs'][i]:raise ValueError('numeric/path mismatch')
        if type(row['nodes']) is not list or type(row['edges']) is not list or (len(row['nodes']),len(row['edges']))!=(item['nodes'],item['edges']):raise ValueError('path count/shape mismatch')
        for x in (*row['nodes'],*row['edges']):
            if type(x) is not str or len(x.encode('utf-8'))>self.limits['identity']:raise ValueError('literal identity quota')
        return row


@dataclass(frozen=True)
class LazyPair:
    source:str
    target:str
    reachable:bool
    time:object
    length:object
    store:object
    @property
    def nodes(self):return tuple(self.store.row((self.source,self.target))['nodes'])
    @property
    def edges(self):return tuple(self.store.row((self.source,self.target))['edges'])


def read(root,check=lambda:None,limits=None):
    store=Store(root,check,dict(LIMITS,**(limits or {})))
    try:
        def records():
            for row in store.numeric['pairs']:yield store.row((row['source'],row['target']))
        def pair(s,t,r,dt,ds,nodes,edges):return LazyPair(s,t,r,dt,ds,store)
        with tempfile.TemporaryDirectory(prefix='leg-endpoints-') as temp:
            endpoints=Endpoints(Path(temp)/'endpoints.sqlite')
            try:table=ExactLegTable._from_records(store.numeric,records(),check,pair,endpoints)
            finally:endpoints.close()
        object.__setattr__(table,'payload_sha256',store.sha)
        object.__setattr__(table,'_path_store',store)
        return table
    except BaseException:store.close();raise


def close(table):table._path_store.close()
