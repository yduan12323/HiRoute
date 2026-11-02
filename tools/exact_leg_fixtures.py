"""Explicitly synthetic construction fixtures, never a real-road producer."""
from fractions import Fraction
from exact_leg_table import SCHEMA,NUMERICAL,SELECTION


def synthetic_payload(site_count=64,alias_pairs=False):
    order=['Site/'+str(i).zfill(3) for i in range(site_count)]
    sites={site:dict(anchor='road/'+str(i//2 if alias_pairs else i).zfill(3),
                    effects=['C','S','CS'] if i<23 else ['C']) for i,site in enumerate(order)}
    return complete_payload('road/origin','road/destination',order,sites)


def complete_payload(origin,destination,order,sites):
    anchors=sorted({origin,destination,*[s['anchor'] for s in sites.values()]})
    ranks={a:i for i,a in enumerate(anchors)}
    sources=sorted({origin,*[s['anchor'] for s in sites.values()]})
    targets=sorted({destination,*[s['anchor'] for s in sites.values()]})
    pairs=[]
    for s in sources:
        for t in targets:
            # A synthetic complete digraph whose direct time is strictly below
            # every nontrivial concatenation. Length remains a path attribute.
            n=ranks[s]*1000+ranks[t]
            T=Fraction(10**38+n,2**127-1);L=Fraction(10**32+17*n,2**101-1)
            pairs.append(dict(source=s,target=t,reachable=True,time_s='0' if s==t else str(T),
                actual_length_m='0' if s==t else str(L),nodes=[s] if s==t else [s,t],
                edges=[] if s==t else ['synthetic:'+s+'>'+t]))
    return dict(schema=SCHEMA,numerical_contract=NUMERICAL,selected_leg_contract=SELECTION,
        graph_identity='SYNTHETIC_COMPLETE_DIRECTED_GRAPH_NOT_REAL_INPUT',road_selection_certified=False,
        origin_anchor=origin,destination_anchor=destination,candidate_order=list(order),sites=sites,pairs=pairs,
        scope='Synthetic constructor fixture; not a real road table or optimizer benchmark')
