"""Bounded non-routing real TSV audit. Never releases source work by itself.

The current object/JSON verifier needs a compact bridge before real use. This
tool can prove its existing loader cannot fit a measured admission allowance;
it never treats a memory lower bound below that allowance as proof of safety.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import time
from fractions import Fraction

from .exact_road_certificate import Edge

POSITIVE=re.compile(r'[1-9][0-9]*(?:/[1-9][0-9]*)?\Z')
CONTROL=re.compile(r'[\x00-\x1f]')
GIB=1024**3


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def positive_parts(text):
    if not POSITIVE.fullmatch(text):raise ValueError('unsupported nonpositive/nonrational TSV weight')
    fields=text.split('/');return int(fields[0]),int(fields[1]) if len(fields)==2 else 1


def memory_units():
    if sys.implementation.name!='cpython' or struct.calcsize('P')!=8:
        raise ValueError('memory lower-bound audit supports 64-bit CPython only')
    e=Edge('source','target',Fraction(1),Fraction(2),'edge')
    # JSON keeps each five-field edge dict alive while Edge/Fraction objects
    # are built. Count no numeric ints, graph maps, node array, raw JSON bytes,
    # adjacency, sort workspace, labels, masks or certificate parser objects.
    # 5 pointer slots is a deliberately conservative dictionary-values floor.
    return dict(json_row=sys.getsizeof(dict(source='',target='',time_s='',length_m='',edge_id='')),
        list_slot=8,edge_object=sys.getsizeof(e),edge_dictionary_value_slots=5*8,
        fractions=2*sys.getsizeof(Fraction(1)),string_header=sys.getsizeof(''))


def scan(path,anchors,units,progress=lambda value:None):
    h=hashlib.sha256();seen=set();count=lower=0;bits=[0,0,0,0]
    fixed=sum(units[k] for k in ('json_row','list_slot','edge_object','edge_dictionary_value_slots','fractions'))
    with Path(path).open('rb') as stream:
        for raw in stream:
            h.update(raw);fields=raw.removesuffix(b'\n').decode('utf-8').split('\t')
            if len(fields)!=5 or any(not f for f in fields):raise ValueError('malformed TSV edge row')
            a,b,e,t,L=fields
            if any(CONTROL.search(value) for value in (a,b,e)):raise ValueError('control character in literal road identity')
            tn,td=positive_parts(t);ln,ld=positive_parts(L)
            for i,v in enumerate((tn,td,ln,ld)):bits[i]=max(bits[i],v.bit_length())
            seen.update({a,b}&anchors);count+=1
            # CPython JSON does not intern multi-character value strings.
            # Count only these three literal identity values; omit weights.
            lower+=fixed+sum(units['string_header']+len(v) for v in (a,b,e) if len(v)>1)
            if count%500000==0:progress(dict(edges_scanned=count,loader_lower_bound_bytes=lower))
    if not count:raise ValueError('empty road edge file')
    return dict(sha256=h.hexdigest(),observed_edge_rows=count,seen_anchors=sorted(seen),
        missing_anchors=sorted(anchors-seen),max_weight_component_bits=bits,
        current_JSON_loader_lower_bound_bytes=lower,
        distinct_graph_nodes_counted=False,global_edge_ID_uniqueness_checked=False,
        full_file_scanned=True,all_weights_exact_positive=True)


def validate_domain(f):
    if (f['query_id'],f['initial_energy_kwh'],f['scenario'],f['N'])!=('WD01','18','schedule',64):
        raise ValueError('frozen original query changed')
    rows=f['domain']['candidates'];ends=f['domain']['endpoints']
    if len(rows)!=64 or len({r['site_id'] for r in rows})!=64:raise ValueError('full literal Site domain required')
    S=sorted({ends['origin']['access_node'],*(r['access_node'] for r in rows)})
    T=sorted({ends['destination']['access_node'],*(r['access_node'] for r in rows)})
    if len(S)!=65 or len(T)!=65 or f['physical_sources']!=S or f['physical_targets']!=T:
        raise ValueError('full alias/source/terminal identity mismatch')
    pairs=[(p['source'],p['target']) for p in f['pairs']]
    if len(pairs)!=4225 or set(pairs)!={(s,t) for s in S for t in T}:raise ValueError('complete directed pair denominator required')
    domain_hash=hashlib.sha256(json.dumps(f['domain'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if domain_hash!=f['candidate_domain_sha256']:raise ValueError('frozen domain digest mismatch')
    return S,T


def preflight(f,host_available_bytes,progress=lambda value:None):
    S,T=validate_domain(f)
    for name in ('config','preflight'):
        if digest(f[name+'_path'])!=f[name+'_sha256']:raise ValueError('frozen '+name+' changed')
    config=json.loads(Path(f['config_path']).read_text());manifest=json.loads(Path(f['preflight_path']).read_text())
    q=next(q for q in manifest['queries'] if q['query_id']=='WD01')
    if (manifest['config']!=config or config['model']!=f['physical_model'] or
        q['endpoints']!=f['domain']['endpoints'] or q['scenario_candidate_domains']['schedule']['64']!=f['domain']['candidates']):
        raise ValueError('actual config/manifest/frozen domain mismatch')
    inputs={}
    for name,path in f['input_paths'].items():
        if name!='graph':inputs[name]=digest(path)
    if any(inputs[k]!=f['expected_input_sha256'][k] for k in inputs):raise ValueError('frozen physical input changed')
    units=memory_units();observed=scan(f['input_paths']['graph'],set(S)|set(T),units,progress)
    inputs['graph']=observed['sha256']
    if inputs['graph']!=f['expected_input_sha256']['graph']:raise ValueError('full graph input digest mismatch')
    if observed['missing_anchors']:raise ValueError('frozen source/terminal/Site anchor absent from full graph scan')
    allowance=max(0,min(8*GIB,host_available_bytes-2*GIB))
    too_large=observed['current_JSON_loader_lower_bound_bytes']>allowance
    return dict(schema='hiroute.real_road_certificate_preflight.v1',
        decision='NO_GO_CURRENT_LOADER_MEMORY' if too_large else 'NO_GO_SAFE_COMPACT_BRIDGE_NOT_ESTABLISHED',
        frozen_query=dict(query_id='WD01',initial_energy_kwh='18',scenario='schedule',N=64),
        candidate_domain_sha256=f['candidate_domain_sha256'],input_sha256=inputs,
        literal_sites=64,physical_sources=65,physical_targets=65,pair_denominator=4225,zero_pairs=len(set(S)&set(T)),
        source_work_released=False,whole_table_certified=False,table_generated=False,
        upper_witness_independently_replayed=False,relevant_depth_certified=False,real_EV_optimization=False,holdout=False,
        host_available_bytes_at_admission=host_available_bytes,required_host_headroom_bytes=2*GIB,
        process_extra_limit_bytes=8*GIB,admitted_additional_memory_bytes=allowance,
        memory_lower_bound_exceeds_admission=too_large,memory_units=units,observed=observed,
        memory_scope='Lower bound for existing CPython JSON graph-object loader at graph construction; not a compact implementation lower bound or measured real loader peak',
        omitted_memory='raw JSON and nodes, numeric strings/ints, graph maps/adjacency/sort work, all source certificates, labels/masks, table and paths',
        unresolved=['compact streaming graph/certificate bridge and safe peak upper bound',
                    'independent complete node/edge-identity validation',
                    'all source distances, canonical selected paths and complete table',
                    'independent physical upper-witness replay and complete relevant H'],
        source_statuses=[dict(source=s,status='unrun_preflight_blocked') for s in S],
        pairs=[dict(source=s,target=t,status='unrun_preflight_blocked') for s in S for t in T])


def save(path,value):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n');temp.replace(path)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--frozen-domain',required=True)
    p.add_argument('--host-available-bytes',required=True,type=int);p.add_argument('--output',required=True);a=p.parse_args()
    out=Path(a.output);out.mkdir(exist_ok=False);frozen=Path(a.frozen_domain)
    started=dict(started_at=time.time(),frozen_domain_sha256=digest(frozen),host_available_bytes=a.host_available_bytes,
        source_work_released=False,stage='input/memory preflight only')
    save(out/'started.json',started);cpu=time.process_time();wall=time.monotonic()
    try:
        result=preflight(json.loads(frozen.read_text()),a.host_available_bytes,lambda v:save(out/'progress.json',v))
    except BaseException as exc:
        save(out/'failure.json',dict(error=repr(exc),source_work_released=False,body_CPU_s=time.process_time()-cpu))
        raise
    result.update(started=started,body_CPU_s=time.process_time()-cpu,body_wall_s=time.monotonic()-wall,
        source_identity='per-run committed producer recorded by external resource supervisor')
    save(out/'results.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('pairs','source_statuses')},indent=2))
