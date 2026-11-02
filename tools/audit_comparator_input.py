"""Non-solving, independent input/depth/size audit. No HiRoute or SMT imports.

Historical values are conditional sizing inputs, never independent certificates
or optimum oracles. This tool neither generates selected legs nor runs a solver.
"""
import argparse
from fractions import Fraction
import hashlib
import itertools
import json
from pathlib import Path
import re


def number(value):
    if type(value) is int:
        return Fraction(value)
    if type(value) is str and re.fullmatch(r'-?(?:0|[1-9][0-9]*)(?:/[1-9][0-9]*)?',value):
        return Fraction(value)
    raise TypeError('exact integer/rational string required')


def conditional_depths(upper, overhead, penalty, direct_time=None, duration='0'):
    """Complete floors IF an attained U and the road-time contract are certified.

    Every physical route has elapsed >= direct shortest time + H*h + pending D.
    Repeated Sites are allowed; no min(H,N) or strict-inequality adjustment.
    """
    h,lam,D=map(number,(overhead,penalty,duration))
    if h<=0 or lam<0 or D<0:
        raise ValueError('physical depth inputs')
    if upper is None:
        return dict(status='unknown_no_attained_witness',basic=None,road=None,road_activity=None)
    U=number(upper)
    if U<0:
        raise ValueError('negative primary cost')
    result=dict(status='conditional_not_certified',basic=int(U//(h+lam)),
                road=None,road_activity=None)
    if direct_time is not None:
        tau=number(direct_time)
        if tau<0 or U<tau+D:
            raise ValueError('inconsistent conditional upper/time/activity inputs')
        result.update(road=int((U-tau)//(h+lam)),
                      road_activity=int((U-tau-D)//(h+lam)))
    return result


def footprint(sites, capabilities, aliases, origin, destination, depth, segments):
    if len(set(sites))!=len(sites) or set(sites)!=set(capabilities):
        raise ValueError('Site identities/capabilities')
    if type(depth) is not int or depth<0 or type(segments) is not int or segments<0:
        raise ValueError('size inputs')
    keys=[origin,*sites,destination]
    if any(k not in aliases or type(aliases[k]) is not str or not aliases[k] for k in keys):
        raise ValueError('physical alias missing')
    for effects in capabilities.values():
        if not effects or len(effects)!=len(set(effects)) or not set(effects)<={'C','S','CS'}:
            raise ValueError('capabilities')
    sources={aliases[k] for k in [origin,*sites]}
    targets={aliases[k] for k in [*sites,destination]}
    A=sum(map(len,capabilities.values()));N=len(sites)
    P=len(sources)*len(targets);diagonal=len(sources&targets)
    return dict(sites=N,actions=A,physical_sources=len(sources),physical_targets=len(targets),
        required_physical_pair_records=P,zero_diagonal_records=diagonal,
        nontrivial_directed_pairs=P-diagonal,
        current_movement_pair_predicate_builds=depth*(N+1)*A,
        current_movement_numeric_ITE_builds_upper=2*depth*(N+1)*A,
        current_two_copy_curve_numeric_ITE_builds=4*segments*depth,
        proposed_shared_table_ground_records=P,
        proposed_direct_leg_lookups=depth+1,
        interpretation='Construction requests/components, not unique AST size or measured runtime/memory')


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            h.update(block)
    return h.hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def audit(preparation_path, results_path):
    prep,results=load(preparation_path),load(results_path)
    if prep['input_sha256']!=results['preparation']['input_sha256']:
        raise ValueError('historical input identity mismatch')
    def configurations(value):
        return {energy:{key:record[key] for key in ('config_sha256','preflight_sha256')}
                for energy,record in value['configs'].items()}
    if configurations(prep)!=configurations(results['preparation']):
        raise ValueError('historical configuration identity mismatch')
    for name,path in prep['inputs'].items():
        if digest(path)!=prep['input_sha256'][name]:
            raise ValueError('frozen physical input changed: '+name)
    grouped={}
    for row in results['rows']:
        identity=tuple(row[k] for k in ('query_id','initial_energy_kwh','scenario'))
        methods=grouped.setdefault(identity,{})
        if row['method'] in methods:
            raise ValueError('duplicate historical method row')
        methods[row['method']]=row
    cells=[];expected=set();config_hashes={}
    for energy,record in sorted(prep['configs'].items()):
        for name in ('config','preflight'):
            if digest(record[name])!=record[name+'_sha256']:
                raise ValueError('frozen configuration/manifest changed')
        config,manifest=load(record['config']),load(record['preflight'])
        if manifest['config']!=config:
            raise ValueError('config/manifest mismatch')
        config_hashes[energy]={k:record[k] for k in ('config_sha256','preflight_sha256')}
        model=config['model'];K=len(model['charging_curve'])
        for query,scenario in itertools.product(manifest['queries'],config['selection']['scenarios']):
            identity=(query['query_id'],energy,scenario);expected.add(identity)
            methods=grouped.get(identity,{})
            if set(methods)!={'flat_bb_strong','scale'}:
                raise ValueError('missing/unexpected historical method cell')
            strong=methods['flat_bb_strong'];rows=query['scenario_candidate_domains'][scenario]['64']
            if any(r['N']!=64 for r in methods.values()):
                raise ValueError('N64 declaration changed')
            available=len(rows)==64
            if any((r['status']!='input_domain_unavailable')!=available for r in methods.values()):
                raise ValueError('unavailable input silently relabeled')
            cell=dict(query_id=identity[0],initial_energy_kwh=energy,scenario=scenario,
                      requested_N=64,available_sites=len(rows),input_available=available,
                      charging_segments=K,history_status=strong['status'])
            if not available:
                cell.update(status='input_domain_unavailable',conditional_depths=None,footprints=None)
                cells.append(cell);continue
            value=dict(endpoints=query['endpoints'],candidates=rows)
            domain=hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            if any(r['candidate_domain_sha256']!=domain for r in methods.values()):
                raise ValueError('historical domain mismatch')
            sites=[r['site_id'] for r in rows]
            caps={r['site_id']:[e for e in r['capabilities'] if e=='C' or scenario=='schedule'] for r in rows}
            origin,destination=(query['endpoints'][k]['site_id'] for k in ('origin','destination'))
            if set(sites)&{origin,destination}:
                raise ValueError('unexpected endpoint Site collision in frozen workload')
            aliases={r['site_id']:r['access_node'] for r in rows}
            aliases.update({query['endpoints'][k]['site_id']:query['endpoints'][k]['access_node']
                            for k in ('origin','destination')})
            key=strong.get('feasible_key');w=strong.get('witness')
            if key is not None and (w is None or w.get('physical_verified') is not True):
                raise ValueError('historical feasible value lacks its physical-witness record')
            upper=key[0] if key else None
            D=config['selection']['schedule_recipe']['duration_s'] if scenario=='schedule' else '0'
            depths=conditional_depths(upper,model['stop_overhead_s'],model['stop_penalty_s'],
                                      strong.get('direct_selected_time_s'),D)
            sizes={name:footprint(sites,caps,aliases,origin,destination,H,K)
                   for name,H in depths.items() if name in ('basic','road','road_activity') and H is not None}
            cell.update(status='current_comparator_unsupported',candidate_domain_sha256=domain,
                historical_attained_feasible_U=upper,upper_is_optimum_oracle=False,
                independent_upper_replay_performed=False,independent_direct_time_certified=False,
                direct_selected_time_s=strong.get('direct_selected_time_s'),pending_duration_s=D,
                conditional_depths=depths,footprints=sizes,
                current_guard_failures=['N64 exceeds2 Sites']+
                ([f'{K} curve segments exceed2'] if K>2 else [])+
                (['basic complete depth exceeds6'] if depths['basic'] is not None and depths['basic']>6 else []))
            cells.append(cell)
    if set(grouped)!=expected:
        raise ValueError('unexpected/missing historical query cells')
    available=[c for c in cells if c['input_available']]
    def span(values):
        values=[v for v in values if v is not None]
        return dict(min=min(values),max=max(values)) if values else None
    return dict(schema='hiroute.comparator_input_audit.v1',
        scope='Input/proof/structural forecast only, not a solver or performance benchmark',
        input_sha256=prep['input_sha256'],config_hashes=config_hashes,
        preparation_sha256=digest(preparation_path),historical_results_sha256=digest(results_path),
        historical_method_row_denominator=len(results['rows']),query_cell_denominator=len(cells),
        input_available_cells=len(available),input_unavailable_cells=len(cells)-len(available),
        curve_segment_counts=sorted({c['charging_segments'] for c in available}),
        summary=dict(actions=span(c['footprints']['basic']['actions'] for c in available if c['footprints']),
          conditional_depth_spans={name:span(c['conditional_depths'][name] for c in available)
                                   for name in ('basic','road','road_activity')},
          cells_without_attained_U=sum(c['conditional_depths']['basic'] is None for c in available),
          road_activity_depth_above6=sum(c['conditional_depths']['road_activity'] is not None and
              c['conditional_depths']['road_activity']>6 for c in available)),
        selected_leg_table_generated=False,real_graph_loaded=False,road_query_calls=0,SMT_calls=0,
        historical_solver_reruns=0,independent_optimality_claim=False,holdout=False,
        decision='NO-GO current full-N64 comparator benchmark; conditional GO for input/lookup implementation only',
        cells=cells)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--preparation',required=True);p.add_argument('--results',required=True)
    p.add_argument('--output',required=True);args=p.parse_args()
    result=audit(args.preparation,args.results)
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('x') as stream:
        json.dump(result,stream,indent=2,sort_keys=True);stream.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k!='cells'},indent=2))
