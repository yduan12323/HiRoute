"""Bounded independent exhaustive tiny certificate producer, never real tables."""
from fractions import Fraction as F
import copy
import json

from exact_leg_table import ExactLegTable,NUMERICAL,SELECTION
from exact_leg_fixtures import complete_payload
from exact_road_certificate import ExactRoadGraph,GRAPH_SCHEMA,CERT_SCHEMA,CertificateSession,Unsupported

IDS=('valid_full_table','valid_noncanonical_predecessor','valid_empty_alias_zero','string_node_tuple','deep_tuple_ties',
     'wrong_shortest_lower_certificate','wrong_node_tuple','wrong_parallel_string_edge',
     'wrong_selected_length','false_unreachable_cut','forged_target_masks',
     'missing_source_coverage','missing_terminal_pair','zero_time_acyclic','zero_time_cycle')


def raw(value):return (json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()
def edge(a,b,time,length,eid):return dict(source=a,target=b,time_s=str(time),length_m=str(length),edge_id=eid)
def graph_payload(kind='base'):
    if kind=='deep':
        nodes=['o','p','a','b','z'];edges=[edge('o','p',1,1,'prefix'),edge('p','a',1,10,'10'),
            edge('p','a',1,1,'2'),edge('p','b',1,1,'00'),edge('a','z',1,10,'az'),
            edge('b','z',1,1,'bz'),edge('o','z',3,1,'direct')]
    elif kind=='numeric':
        nodes=['o','10','2','z'];edges=[edge('o','10',1,10,'z-ten'),edge('10','z',1,10,'ten-z'),
            edge('o','2',1,1,'a-two'),edge('2','z',1,1,'two-z')]
    else:
        nodes=['o','a','b','z','dead'];edges=[edge('o','a',1,10,'10'),edge('o','a',1,1,'2'),
            edge('o','b',1,1,'00'),edge('a','z',1,10,'az'),edge('b','z',1,1,'bz'),
            edge('o','z',2,1,'direct'),edge('a','o',3,3,'back-positive-cycle')]
    return dict(schema=GRAPH_SCHEMA,numerical_contract=NUMERICAL,selected_leg_contract=SELECTION,nodes=nodes,edges=edges)


def exhaustive(graph):
    """Reference only: enumerate bounded tiny simple prefixes, not checker logic."""
    if len(graph.nodes)>6 or len(graph.edges)>12:raise Unsupported('tiny producer guard, not a real-table generator')
    best={}
    for source in graph.nodes:
        count=0
        def walk(v,nodes,ids,T,L):
            nonlocal count
            count+=1
            if count>2048:raise Unsupported('tiny prefix enumeration guard')
            key=(T,nodes,ids)
            if (source,v) not in best or key<best[source,v][:3]:best[source,v]=(T,nodes,ids,L)
            for e in graph.outgoing[v]:
                if e.target not in nodes:walk(e.target,nodes+(e.target,),ids+(e.edge_id,),T+e.time,L+e.length)
        walk(source,(source,),(),F(0),F(0))
    return best


def build(payload=None,sites=None,destination='z'):
    gp=graph_payload() if payload is None else payload;graph=ExactRoadGraph.from_bytes(raw(gp));best=exhaustive(graph)
    if sites is None:
        sites={'o':dict(anchor='a',effects=['C','S','CS']),'Alias/A':dict(anchor='a',effects=['C']),
            'Site/B':dict(anchor='b',effects=['S']),'OriginAlias':dict(anchor='o',effects=['C']),
            'Dead':dict(anchor='dead',effects=['S'])}
    table_payload=complete_payload('o',destination,list(sites),sites)
    table_payload['graph_identity']='sha256:'+graph.payload_sha256
    for row in table_payload['pairs']:
        value=best.get((row['source'],row['target']))
        row.update(reachable=value is not None,time_s=str(value[0]) if value else None,
            actual_length_m=str(value[3]) if value else None,nodes=list(value[1]) if value else [],edges=list(value[2]) if value else [])
    table=ExactLegTable.from_bytes(raw(table_payload));certs=[]
    for source in table.sources:
        labels={v:str(best[source,v][0]) if (source,v) in best else None for v in graph.nodes}
        R={v for v in graph.nodes if labels[v] is not None}
        pred={v:best[source,v][2][-1] for v in R-{source}}
        masks={}
        for v in R:
            mask=0
            for i,target in enumerate(table.targets):
                if ((source,target) in best and (v,target) in best and
                    best[source,v][0]+best[v,target][0]==best[source,target][0]):mask|=1<<i
            masks[v]=mask
        certs.append(dict(schema=CERT_SCHEMA,graph_sha256=graph.payload_sha256,table_sha256=table.payload_sha256,
            source=source,target_order=list(table.targets),labels=labels,predecessors=pred,target_masks=masks))
    return dict(graph_payload=gp,graph=graph,table_payload=table_payload,table=table,certificates=certs)


def rebound(bundle):
    bundle['table']=ExactLegTable.from_bytes(raw(bundle['table_payload']))
    for cert in bundle['certificates']:cert['table_sha256']=bundle['table'].payload_sha256
    return bundle

def source_row(bundle,source='o'):return next(c for c in bundle['certificates'] if c['source']==source)
def pair_row(bundle,s='o',t='z'):return next(p for p in bundle['table_payload']['pairs'] if (p['source'],p['target'])==(s,t))


def fixture(name):
    if name not in IDS:raise ValueError('outside frozen tiny checker gate')
    if name in ('zero_time_acyclic','zero_time_cycle'):
        p=graph_payload();p['edges'][0]['time_s']='0'
        if name=='zero_time_cycle':next(e for e in p['edges'] if e['edge_id']=='back-positive-cycle')['time_s']='0'
        return dict(name=name,expected='unsupported',unsupported_graph=p)
    b=build(graph_payload('deep'),sites={}) if name=='deep_tuple_ties' else (
      build(graph_payload('numeric'),sites={}) if name=='string_node_tuple' else (
      build(sites={},destination='o') if name=='valid_empty_alias_zero' else build()))
    expected='verified' if name.startswith('valid_') or name in ('string_node_tuple','deep_tuple_ties') else 'rejected'
    if name=='valid_noncanonical_predecessor':source_row(b)['predecessors']['z']='direct'
    elif name=='wrong_shortest_lower_certificate':
        gp=graph_payload();gp['edges'].append(edge('o','z',3,1,'slow-valid-path'))
        b=build(gp,sites={});r=pair_row(b);r.update(time_s='3',actual_length_m='1',nodes=['o','z'],edges=['slow-valid-path'])
        c=source_row(b);c['labels']['z']='3';c['predecessors']['z']='slow-valid-path'
        c['target_masks']={v:int(v in ('o','z')) for v in ('o','a','b','z')}
        rebound(b)
    elif name=='wrong_node_tuple':
        pair_row(b).update(nodes=['o','b','z'],edges=['00','bz'],actual_length_m='2');rebound(b)
    elif name=='wrong_parallel_string_edge':
        pair_row(b,'o','a').update(edges=['2'],actual_length_m='1');rebound(b)
    elif name=='wrong_selected_length':pair_row(b)['actual_length_m']='1';rebound(b)
    elif name=='false_unreachable_cut':
        c=source_row(b);c['labels']['b']=None;c['predecessors'].pop('b');c['target_masks'].pop('b')
    elif name=='forged_target_masks':
        pair_row(b).update(nodes=['o','b','z'],edges=['00','bz'],actual_length_m='2')
        source_row(b)['target_masks']['a']=1<<list(b['table'].targets).index('a')
        rebound(b)
    elif name=='missing_source_coverage':b['certificates'].pop()
    elif name=='missing_terminal_pair':
        b['table_payload']['pairs']=[r for r in b['table_payload']['pairs'] if (r['source'],r['target'])!=('a','z')]
        b['table']=None  # Parsing the incomplete table must fail, before certificate checking.
    return dict(name=name,expected=expected,bundle=b)


def evaluate(f):
    """No production route/solver calls. Exception classes stay distinct."""
    try:
        if 'unsupported_graph' in f:
            ExactRoadGraph.from_bytes(raw(f['unsupported_graph']))
            return dict(status='incorrectly_accepted_unsupported')
        b=f['bundle'];table=b['table']
        if table is None:table=ExactLegTable.from_bytes(raw(b['table_payload']))
        session=CertificateSession(b['graph'],table)
        for cert in b['certificates']:session.check_source(raw(cert))
        result=session.finish()
        return dict(status='verified',checked_pairs=result.checked_pairs,literal_sites=result.literal_sites,
            physical_sources=len(table.sources),physical_targets=len(table.targets),
            zero_pairs=sum(r['zero_pairs'] for r in result.source_receipts),
            graph_sha256=result.graph_sha256,table_sha256=result.table_sha256,
            graph_nodes=len(b['graph'].nodes),graph_edges=len(b['graph'].edges),
            owns_exact_inputs=result.is_for(b['graph'],table),scope='exact supplied synthetic graph/table only',
            source_receipts=[dict(r) for r in result.source_receipts],
            selected_example=dict(nodes=table.pairs['o',table.destination_anchor].nodes,
                edges=table.pairs['o',table.destination_anchor].edges,
                actual_length=str(table.pairs['o',table.destination_anchor].length)))
    except Unsupported as exc:return dict(status='unsupported',reason=str(exc))
    except (ValueError,TypeError) as exc:return dict(status='rejected',reason=str(exc))
