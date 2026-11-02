"""Frozen synthetic pipeline and structural resource proof; no real input CLI."""
import argparse
import json
from pathlib import Path
import sys
import time

from exact_leg_fixtures import complete_payload
from road_certificate_fixtures import build as tiny_build,graph_payload,edge
from streaming_road_fixtures import graph_inputs,analytic_wide,write_jsonl
from streaming_road_graph import sha
from streaming_road_certificate import UNIT_SCHEMA,TABLE_SCHEMA,read_source_unit,SourceSession,read_table,Session
from packed_source_prototype import build_synthetic,Packed,validate_synthetic_pack,generate,HEAD,ARC

IDS=('base','deep','numeric','wide_rational','empty_prefix','unicode','full_N64','scaling_4096')


def admit(config):
    if config.get('profiles')!=list(IDS) or config.get('profile_denominator')!=8:raise ValueError('exact frozen eight-profile coverage')
    if config.get('scaling_nodes')!=4096 or config.get('full_width_sites')!=64:raise ValueError('frozen synthetic shapes')
    if config.get('real_sources')!=65 or config.get('real_pairs')!=4225:raise ValueError('original real denominator')
    expected=dict(profile_denominator=8,scaling_nodes=4096,full_width_sites=64,real_sources=65,real_pairs=4225,cap_CPU_s=600,cache_bytes=16*1024**2,label_bytes=512*1024**2,whole_tree_RSS_bytes=1024**3,host_start_bytes=3*1024**3,host_runtime_headroom_bytes=2*1024**3,worker_threads=1,synthetic_constructor_max_nodes=8192,synthetic_constructor_max_edges=32768)
    if any(type(config.get(k)) is not int or config.get(k)!=v for k,v in expected.items()):raise ValueError('frozen resource envelopes')
    if config.get('allocations_CPU_s')!=dict(development_controller=240,tiny_validation=180,resource_proof_report=120,close=60) or any(type(v) is not int for v in config['allocations_CPU_s'].values()):raise ValueError('frozen600allocation')
    if any(config.get(k) is not False for k in ('real_graph_scan','real_source','EV_solve','holdout')):raise ValueError('synthetic-only admission')


def spec(name):
    if name in ('base','deep','numeric'):
        b=tiny_build(graph_payload(name),sites=None if name=='base' else {});return b['graph_payload'],b['table_payload'],('o',),b
    if name=='full_N64':
        b=analytic_wide()['bundle'];return b['graph_payload'],b['table_payload'],b['table'].sources,b
    if name=='empty_prefix':
        b=tiny_build(sites={},destination='o');return b['graph_payload'],b['table_payload'],('o',),b
    if name=='wide_rational':
        p,q=2**83-9,2**83-71;gp=graph_payload();gp.update(nodes=['o','a','z'],edges=[edge('o','a','1/'+str(p),2**140,'01'),edge('a','z','1/'+str(q),1,'10')]);b=tiny_build(gp,sites={});return gp,b['table_payload'],('o',),b
    if name=='unicode':
        gp=graph_payload();gp.update(nodes=['o','01','1','ss','ß','z'],edges=[edge('o','01',1,2,'01'),edge('01','1',1,3,'1'),edge('1','z',1,4,'10'),edge('o','ss',1,2,'ss'),edge('ss','ß',1,2,'ß'),edge('ß','z',1,2,'z')]);b=tiny_build(gp,sites={});return gp,b['table_payload'],('o',),b
    if name!='scaling_4096':raise ValueError('unknown frozen profile')
    N=4096;nodes=['o']+['n'+str(i).zfill(5) for i in range(1,N)];edges=[]
    for i in range(N-1):
        edges.extend((edge(nodes[i],nodes[i+1],'1/3',1,'f/'+str(i)),edge(nodes[i],nodes[i+1],'1/3',2,'p/'+str(i)),edge(nodes[i+1],nodes[i],1,2,'b/'+str(i))))
        if i+4<N:edges.append(edge(nodes[i],nodes[i+4],'4/3',3,'s/'+str(i)))
    gp=graph_payload();gp.update(nodes=nodes,edges=edges)
    sites={'Site/'+str(i):dict(anchor=nodes[(i+1)*(N-1)//65],effects=['C','S','CS']) for i in range(64)}
    # No simple-path enumeration is called for the scaling graph.
    return gp,complete_payload('o',nodes[-1],list(sites),sites),('o',),None


def unit_header(p,g,source):
    return dict(schema=UNIT_SCHEMA,numerical_contract=p['numerical_contract'],selected_leg_contract=p['selected_leg_contract'],
        graph_identity='sha256:'+g.payload_sha256,source_unit=source,**{k:p[k] for k in ('origin_anchor','destination_anchor','candidate_order','sites')})


def resource_proof():
    N,E=2986695,5900232;raw=530374281;K=65
    # Frozen graph node-domain is the union of raw endpoints. Unique node text
    # contributes no more bytes than all endpoint occurrences. Per weight,
    # reduced binary magnitudes use <= decimal input bytes+1, plus8byte lengths.
    fixed_pack=HEAD.size+16*(N+1)+8*(E+1)+ARC.size*E
    arena_upper=raw+18*E
    fixed_state=8*N+4*N*4+N+((K+7)//8)*N
    reserves=dict(label_objects_and_integer_payload=512*1024**2,page_cache=16*1024**2,
        arithmetic_temporaries=16*1024**2,serialization_buffers=16*1024**2,
        interpreter_allocator_reserve=128*1024**2,container_header_and_cache_overhead=4*1024**2)
    from fractions import Fraction
    from packed_source_certificate_codec import HEAD as CERT_HEAD
    label_quota=512*1024**2;F=sys.getsizeof(Fraction(0));I=int.__basicsize__;extra=8+4+(K+7)//8
    layout_supported=(sys.int_info.bits_per_digit<=8*sys.int_info.sizeof_digit and F+2*I>extra)
    binary_upper=CERT_HEAD.size+4*K+N+label_quota-(F+2*I-extra) if layout_supported else None
    json_upper=(8*label_quota+2)//3+2*raw+(64+(K+2)//3+1)*N+1024**2 if layout_supported else None
    storage_total=(65*binary_upper+json_upper+2*1024**3+2*1024**3+fixed_pack+arena_upper+2*1024**3) if layout_supported else None
    return dict(scope='symbolic frozen-count storage/layout estimates, not measured real RSS or runtime',
        nodes=N,edges=E,raw_bytes=raw,node_domain='all raw endpoints, already independently established',
        packed_fixed_sections_bytes=fixed_pack,packed_arena_conservative_upper_bytes=arena_upper,
        packed_file_conservative_upper_bytes=fixed_pack+arena_upper,
        index_proof=dict(node_and_edge_counts_below_uint32_sentinel=(N<2**32-1 and E<2**32-1),
            byte_offsets_fit_uint64_under_explicit_4GiB_file_limit=True,numeric_weights_and_labels='unbounded Fraction integers; explicit storage stop, never fixed-width rounding'),
        generator_fixed_state_formula_bytes=fixed_state,generator_reserves_bytes=reserves,
        generator_layout_admission_bytes=fixed_state+sum(reserves.values()),
        generator_external_RSS_limit_bytes=1024**3,
        limitations=['512MiB exact label quota may resource-stop real input; no path-bit distribution measured',
            '128MiB interpreter/allocator allowance is an explicit admission reserve, not a universal CPython RSS theorem; external whole-tree guard remains necessary',
            'Synthetic constructor holds identities/edges in memory and refuses real counts; a bounded external-join real constructor is absent',
            'Independent checker is unchanged and sequentially separate; its real source cost and SQLite workspace/output sizes are unmeasured'],
        whole_table_counts=dict(node_certificate_records=65*N,raw_edge_check_visits=65*E,
            pair_denominator=4225,sources=65),
        compact_certificate_proof=dict(conditional_layout_supported=layout_supported,Fraction_object_bytes=F,int_header_bytes=I,
            int_bits_per_digit=sys.int_info.bits_per_digit,int_sizeof_digit=sys.int_info.sizeof_digit,label_quota_bytes=label_quota,
            one_binary_certificate_upper_bytes=binary_upper,all65_binary_upper_bytes=65*binary_upper if binary_upper else None,
            one_decoded_JSON_upper_bytes=json_upper,prospective_total_storage_with_quotas_bytes=storage_total,
            assumptions='Exact Fraction/int instances,512MiB summed label accounting,65targets, positive root present; node+attaining-predecessor text bounded by disjoint raw identity fields; JSON escaping<=2x valid raw UTF8. Decimal digits<=ceil(bits/3)+1 since2^3<10.',
            not_implemented_or_admitted='Real external pack builder; lossless-only retention/cleanup driver;3GiB JSON limit;1GiB each active SQL file;2GiB cumulative selected-path quota; stop first incomplete source. Live preflight must reserve total plus other temporary files.'),
        whole_table_storage='No full-source byte measurement. Binary/storage bounds are conditional quotas, not measured or required sizes, and do not admit a real batch.',
        sequential_memory='Generator exits before independent checking; generator and checker state must not silently coexist. No real worker is launched here.',
        checker_memory='Existing checker uses bounded SQLite global128MiB heap and streaming records. Completed-real-source checker RSS remains unmeasured; cannot substitute the generator layout for it.',
        budget=dict(carried_research_CPU_s='16726.757521741',gate_cap_CPU_s=600,
            remaining_before_gate_CPU_s='12073.242478259',unchanged_remaining64_pair_reservation_CPU_s=19200),
        decision='NO_GO_REAL_END_TO_END_RELEASE',reason='No real packed construction/identity validation or completed source+independent check/storage cost exists; unchanged64source reservation exceeds remaining budget. Synthetic component success cannot close these gaps.')


def save(path,value):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');temp.replace(path)


def run(config,output,source_commit):
    cfg=json.loads(Path(config).read_text());admit(cfg);out=Path(output);out.mkdir(exist_ok=False)
    report=dict(schema='hiroute.packed_source_feasibility.results.v1',source_commit=source_commit,
        config_sha256=sha(config),profile_denominator=8,profiles=[dict(id=x,status='UNRUN') for x in IDS],
        real_source_denominator=65,real_pair_denominator=4225,real_source=False,real_graph_scan=False,
        EV_solve=False,holdout=False,real_whole_table_certified=False,resource_proof=resource_proof())
    save(out/'results.json',report)
    for row in report['profiles']:
        row['status']='STARTED';save(out/'results.json',report);folder=out/row['id'];folder.mkdir();g=p=None;cpu=time.process_time();wall=time.monotonic()
        try:
            gp,tp,sources,b=spec(row['id']);g=graph_inputs(gp,folder);t0=time.process_time();path=build_synthetic(g,folder/'pack');p=Packed.open(path);validate_synthetic_pack(g,p);pack_cpu=time.process_time()-t0
            units=[];unit_receipts=[];checks=[]
            row.update(unit_receipts=unit_receipts,source_checks=checks,source_executions=[dict(source=s,status='UNRUN') for s in sources])
            for i,source in enumerate(sources):
                row['source_executions'][i]['status']='STARTED';save(out/'results.json',report)
                header=unit_header(tp,g,source);where=folder/f'unit-{i}';generated=generate(p,header,where)
                c0=time.process_time();w0=time.monotonic();t=read_source_unit(where/'paths.jsonl',g,folder/f'table-{i}.sqlite')
                try:
                    session=SourceSession(g,t);session.check_source(where/'source.jsonl',folder/f'check-{i}');receipt=dict(session.finish())
                finally:t.close()
                units.append(where);unit_receipts.append(dict(generated,independent_receipt=receipt));checks.append(dict(CPU_s=time.process_time()-c0,wall_s=time.monotonic()-w0))
                row['source_executions'][i]['status']='INDEPENDENTLY_VERIFIED_SYNTHETIC'
                row.update(status='CHECKING',completed_sources=i+1,scheduled_source_denominator=len(sources));save(out/'results.json',report)
            full=None
            if row['id']=='full_N64':
                fc,fw=time.process_time(),time.monotonic();full_path=folder/'complete-table.jsonl';h=unit_header(tp,g,'o');h.pop('source_unit');h['schema']=TABLE_SCHEMA
                with full_path.open('x') as stream:
                    stream.write(json.dumps(h,separators=(',',':'))+'\n')
                    for unit in units:
                        with (unit/'paths.jsonl').open() as rows:
                            next(rows)
                            for line in rows:stream.write(line)
                table=read_table(full_path,g,folder/'complete-table.sqlite')
                try:
                    complete=Session(g,table)
                    for i,unit in enumerate(units):
                        def rebound():
                            with (unit/'source.jsonl').open() as rows:
                                head=json.loads(next(rows));head['table_sha256']=table.payload_sha256;yield head
                                for line in rows:yield json.loads(line)
                        cert=folder/f'complete-source-{i}.jsonl';write_jsonl(cert,rebound());complete.check_source(cert,folder/f'complete-check-{i}')
                    checked=complete.finish();full=dict(checked_pairs=checked.checked_pairs,checked_sources=len(checked.source_receipts),owned=checked.is_for(g,table),scope='synthetic full table only',CPU_s=time.process_time()-fc,wall_s=time.monotonic()-fw)
                    if full['checked_pairs']!=4225 or full['checked_sources']!=65 or not full['owned']:raise ValueError('full synthetic coverage')
                finally:table.close()
            row.update(status='INDEPENDENTLY_VERIFIED_SYNTHETIC',nodes=g.node_count,edges=g.edge_count,pack_bytes=path.stat().st_size,
                pack_build_and_validation_CPU_s=pack_cpu,unit_receipts=unit_receipts,source_checks=checks,
                synthetic_full_table=full,body_CPU_s=time.process_time()-cpu,body_wall_s=time.monotonic()-wall)
        except BaseException as exc:
            for source_row in row.get('source_executions',[]):
                if source_row['status']=='STARTED':source_row['status']='ERROR';source_row['error']=repr(exc)
            row.update(status='ERROR',error=repr(exc),body_CPU_s=time.process_time()-cpu,body_wall_s=time.monotonic()-wall);save(out/'results.json',report);raise
        finally:
            if p is not None:p.close()
            if g is not None:g.close()
        save(out/'results.json',report)
    if len(report['profiles'])!=8 or [r['id'] for r in report['profiles']]!=list(IDS) or not all(r['status']=='INDEPENDENTLY_VERIFIED_SYNTHETIC' for r in report['profiles']):raise ValueError('complete frozen profile coverage')
    report['component_decision']='PASS_SYNTHETIC_COMPONENT_ONLY';report['real_pipeline_decision']='NO_GO_REAL_END_TO_END_RELEASE';save(out/'results.json',report)
    print(json.dumps({'component_decision':report['component_decision'],'real_pipeline_decision':report['real_pipeline_decision'],'profiles':8}))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ('config','output','source-commit'):parser.add_argument('--'+name,required=True)
    a=parser.parse_args();run(a.config,a.output,a.source_commit)
