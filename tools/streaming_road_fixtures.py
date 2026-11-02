"""Tiny format conversion/gate helpers only, not a real path producer."""
import json
from pathlib import Path
from streaming_road_graph import build,validate
from streaming_road_certificate import read_table,Session,TABLE_SCHEMA,SOURCE_SCHEMA
from exact_leg_table import NUMERICAL,SELECTION


def write_jsonl(path,rows):
    with Path(path).open('x') as s:
        for row in rows:s.write(json.dumps(row,sort_keys=True,separators=(',',':'))+'\n')


def graph_inputs(gp,root):
    root=Path(root);raw=root/'graph.tsv';nodes=root/'nodes.jsonl'
    raw.write_text(''.join('\t'.join(str(e[k]) for k in ('source','target','edge_id','time_s','length_m'))+'\n' for e in gp['edges']))
    write_jsonl(nodes,sorted(gp['nodes']));build(raw,root/'graph.sqlite',nodes_path=nodes)
    return validate(raw,root/'graph.sqlite',root/'identity-validation',nodes_path=nodes)


def table_rows(p,g):
    yield dict(schema=TABLE_SCHEMA,numerical_contract=NUMERICAL,selected_leg_contract=SELECTION,
        graph_identity='sha256:'+g.payload_sha256,**{k:p[k] for k in ('origin_anchor','destination_anchor','candidate_order','sites')})
    for row in p['pairs']:
        yield dict(kind='pair',source=row['source'],target=row['target'],reachable=row['reachable'],time_s=row['time_s'],length_m=row['actual_length_m'],first_node=row['nodes'][0] if row['nodes'] else None)
        for u,v,eid in zip(row['nodes'],row['nodes'][1:],row['edges']):yield dict(kind='step',u=u,v=v,edge_id=eid)
        yield dict(kind='end_pair')


def source_rows(c,g,t):
    yield dict(schema=SOURCE_SCHEMA,graph_sha256=g.payload_sha256,table_sha256=t.payload_sha256,source=c['source'],target_order=list(t.targets))
    for node in g.nodes():
        yield dict(node=node,label=c['labels'][node],predecessor_edge_id=c['predecessors'].get(node),
                   mask=str(c['target_masks'][node]) if node in c['target_masks'] else None)


def evaluate(f,root):
    root=Path(root);root.mkdir();g=t=None
    try:
        if 'unsupported_graph' in f:graph_inputs(f['unsupported_graph'],root);raise ValueError('unsupported graph was accepted')
        b=f['bundle'];g=graph_inputs(b['graph_payload'],root)
        write_jsonl(root/'table.jsonl',table_rows(b['table_payload'],g));t=read_table(root/'table.jsonl',g,root/'table.sqlite')
        session=Session(g,t)
        for i,c in enumerate(b['certificates']):
            path=root/f'source-{i}.jsonl';write_jsonl(path,source_rows(c,g,t));session.check_source(path,root/f'state-{i}')
        result=session.finish()
        return dict(status='verified',pairs=result.checked_pairs,sources=len(result.source_receipts),owned=result.is_for(g,t))
    finally:
        if t is not None:t.close()
        if g is not None:g.close()


def analytic_wide():
    """Closed-form positive star, not a routing/path-enumeration producer."""
    from exact_leg_fixtures import complete_payload
    from exact_leg_table import ExactLegTable
    from exact_road_certificate import ExactRoadGraph,GRAPH_SCHEMA,CERT_SCHEMA
    from road_certificate_fixtures import raw
    anchors=['anchor-'+str(i) for i in range(64)];targets=anchors+['terminal']
    gp=dict(schema=GRAPH_SCHEMA,numerical_contract=NUMERICAL,selected_leg_contract=SELECTION,
        nodes=['o',*targets],edges=[dict(source='o',target=v,edge_id='edge-'+v,time_s='1',length_m='1') for v in targets])
    g=ExactRoadGraph.from_bytes(raw(gp));sites={'Site/'+str(i):dict(anchor=v,effects=['C','S','CS']) for i,v in enumerate(anchors)}
    p=complete_payload('o','terminal',list(sites),sites);p['graph_identity']='sha256:'+g.payload_sha256
    for row in p['pairs']:
        s,t=row['source'],row['target'];reach=s=='o' or s==t
        row.update(reachable=reach,time_s=('0' if s==t else '1') if reach else None,
            actual_length_m=('0' if s==t else '1') if reach else None,
            nodes=([s] if s==t else [s,t]) if reach else [],edges=([] if s==t else ['edge-'+t]) if reach else [])
    table=ExactLegTable.from_bytes(raw(p));certs=[];bits={v:1<<i for i,v in enumerate(table.targets)}
    for s in table.sources:
        labels={v:('0' if v==s else ('1' if s=='o' else None)) for v in g.nodes}
        R={v for v,d in labels.items() if d is not None}
        certs.append(dict(schema=CERT_SCHEMA,graph_sha256=g.payload_sha256,table_sha256=table.payload_sha256,
            source=s,target_order=list(table.targets),labels=labels,
            predecessors={v:'edge-'+v for v in R-{s}},
            target_masks={v:((1<<65)-1 if v=='o' else bits.get(v,0)) for v in R}))
    return dict(name='analytic_N64_65bit',expected='verified',bundle=dict(graph_payload=gp,graph=g,table_payload=p,table=table,certificates=certs))
