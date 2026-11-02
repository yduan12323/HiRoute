"""Untrusted lossless certificate transport; mathematical checker unchanged.

Dense identities are resolved through the same immutable candidate mapping.
Decoded JSONL must still pass the independent raw-graph source checker. No
schema or checksum alone issues a road certificate.
"""
from fractions import Fraction
import hashlib
from pathlib import Path
import struct

from streaming_road_graph import ResourceStop,MAX_LINE,sha,flush_file
from streaming_road_certificate import Arithmetic,SOURCE_SCHEMA
from generate_exact_source_unit import domain

MAGIC=b'HRSCERT1'
HEAD=struct.Struct('<8sIII32s32s32s')
SENTINEL=2**32-1


def write_certificate(path,packed,header,paths_sha,labels,pred,masks,check=lambda:None):
    S,T=domain(header);N=packed.N;K=len(T);B=(K+7)//8;root=packed.find_node(header['source_unit'])
    with Path(path).open('xb') as out:
        out.write(HEAD.pack(MAGIC,N,K,root,bytes.fromhex(packed.graph_identity),bytes.fromhex(paths_sha),bytes.fromhex(packed.data_sha256)))
        for t in T:out.write(struct.pack('<I',packed.find_node(t)))
        for u in range(N):
            if u%1024==0:check()
            value=labels.values[u]
            if value is None:out.write(b'\x00');continue
            if value<0:raise ValueError('source label must be nonnegative')
            out.write(b'\x01')
            n=value.numerator.to_bytes(max(1,(value.numerator.bit_length()+7)//8),'little')
            d=value.denominator.to_bytes(max(1,(value.denominator.bit_length()+7)//8),'little')
            if len(n)+len(d)+8>MAX_LINE:raise ResourceStop('binary source record')
            out.write(struct.pack('<II',len(n),len(d)));out.write(n);out.write(d)
            eid=packed.arc(pred[u])[1] if pred[u]!=SENTINEL else SENTINEL
            out.write(struct.pack('<I',eid));out.write(masks[u*B:(u+1)*B])
    flush_file(path);return dict(encoded_sha256=sha(path),encoded_bytes=Path(path).stat().st_size,
        scope='untrusted lossless candidate transport; not independent certification')


def decode_certificate(path,output,packed,header,paths_sha,check=lambda:None):
    from packed_source_prototype import bounded_emit
    S,T=domain(header);K=len(T);B=(K+7)//8;before=sha(path);A=Arithmetic();consumed=hashlib.sha256()
    with Path(path).open('rb') as source,Path(output).open('x') as target:
        def read(n):
            if n<0 or n>MAX_LINE:raise ResourceStop('bounded certificate input buffer')
            value=source.read(n)
            if len(value)!=n:raise ValueError('truncated binary source')
            consumed.update(value);return value
        magic,N,declaredK,root,gid,tid,pid=HEAD.unpack(read(HEAD.size))
        if (magic,N,declaredK,gid.hex(),tid.hex(),pid.hex())!=(MAGIC,packed.N,K,packed.graph_identity,paths_sha,packed.data_sha256):raise ValueError('actual source/graph/table/mapping identity')
        if packed.node(root)!=header['source_unit']:raise ValueError('literal root identity')
        targets=[packed.node(struct.unpack('<I',read(4))[0]) for _ in range(K)]
        if targets!=list(T):raise ValueError('complete original target order')
        bounded_emit(target,dict(schema=SOURCE_SCHEMA,graph_sha256=packed.graph_identity,table_sha256=paths_sha,source=header['source_unit'],target_order=list(T)))
        for u in range(N):
            if u%1024==0:check()
            present=read(1)
            if present not in (b'\x00',b'\x01'):raise ValueError('exact source row flag')
            node=packed.node(u);value=eid=mask=None
            if present==b'\x01':
                n,d=struct.unpack('<II',read(8))
                if not n or not d or n+d+8>MAX_LINE:raise ResourceStop('source integer byte envelope')
                a=int.from_bytes(read(n),'little');b=int.from_bytes(read(d),'little')
                if not b:raise ValueError('zero source denominator')
                A.admit(Fraction(a),Fraction(b));value=Fraction(a,b);A.admit(value)
                rank=struct.unpack('<I',read(4))[0];eid=packed.eid(rank) if rank!=SENTINEL else None
                mask=int.from_bytes(read(B),'little')
                if mask.bit_length()>K:raise ValueError('target mask overcoverage')
                upper=256+6*(len(node.encode())+(len(eid.encode()) if eid else 0))+value.numerator.bit_length()+value.denominator.bit_length()+K
                if upper>MAX_LINE:raise ResourceStop('decoded exact record buffer')
            bounded_emit(target,dict(node=node,label=A.text(value) if value is not None else None,
                predecessor_edge_id=eid,mask=str(mask) if mask is not None else None))
        if source.read(1):raise ValueError('extra source rows/suffix')
    flush_file(output);packed.assert_unchanged();check()
    if consumed.hexdigest()!=before or sha(path)!=before:raise ValueError('binary source changed during decoding')
    return dict(encoded_sha256=before,decoded_sha256=sha(output),decoded_bytes=Path(output).stat().st_size,
        scope='lossless transport only; independent source proof still required')
