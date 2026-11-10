"""Declared workload validation shared by coordinator and query worker."""
import argparse
import math

def _scope(value, convert=str):
    if value is None:
        return None
    parts = value.split(',')
    if not parts or any(not part.strip() for part in parts):
        raise ValueError('empty workload scope')
    result = tuple(convert(part.strip()) for part in parts)
    if len(set(result)) != len(result):
        raise ValueError('duplicate workload scope')
    return set(result)


def selected_workload(config, args):
    """Select only predeclared matrix entries, never create a Cartesian extension."""
    if args.diagnostic and args.ablation:
        raise ValueError('diagnostic and ablation modes are mutually exclusive')
    normal_methods = ('flat_bb_strong','scale')
    limit_override = args.solve_limit_seconds
    if limit_override is not None and (not math.isfinite(limit_override) or limit_override <= 0):
        raise ValueError('solve limit must be finite and positive')
    rows = []
    if args.diagnostic:
        spec = config['diagnostics']['legacy_common_domain']
        limit = spec['wall_s']
        if args.no_bound or (limit_override is not None and limit_override != limit):
            raise ValueError('legacy diagnostic must match declared bound policy and wall limit')
        for method in ('flat_bb_legacy',)+normal_methods:
            rows.append(dict(N=spec['N'],query_id=spec['query_id'],scenario=spec['scenario'],
                method=method,use_bound=True,solve_limit_s=limit,mode='diagnostic'))
    elif args.ablation:
        spec = config['diagnostics']['bound_ablation']
        limit = spec['wall_s']
        if limit_override is not None and limit_override != limit:
            raise ValueError('bound ablation must match declared wall limit')
        variants = spec['use_bound_values']
        if not variants or any(type(v) is not bool for v in variants) or len(set(variants)) != len(variants):
            raise ValueError('invalid declared bound ablation variants')
        for use_bound in variants:
            if args.no_bound and use_bound:
                continue
            rows.append(dict(N=spec['N'],query_id=spec['query_id'],scenario=spec['scenario'],
                method=spec['method'],use_bound=use_bound,solve_limit_s=limit,mode='ablation'))
    else:
        if args.no_bound:
            raise ValueError('--no-bound requires the declared --ablation mode')
        resources = config['resources']
        limit = resources['pilot_method_query_wall_s'] if limit_override is None else limit_override
        if limit not in (resources['pilot_method_query_wall_s'],resources['main_threshold_s']):
            raise ValueError('undeclared pilot/main comparison wall limit')
        allowed_queries = {od['query_id'] for od in config['selection']['ods']}
        for block in config['pilot_matrix']:
            if (block['N'] not in config['selection']['candidate_counts'] or
                    not set(block['query_ids']) <= allowed_queries or
                    not set(block['scenarios']) <= set(config['selection']['scenarios'])):
                raise ValueError('pilot matrix contains an undeclared domain/query/scenario')
            for query in block['query_ids']:
                for scenario in block['scenarios']:
                    for method in normal_methods:
                        rows.append(dict(N=block['N'],query_id=query,scenario=scenario,
                            method=method,use_bound=True,solve_limit_s=limit,mode='pilot'))
    scopes = {'N':_scope(args.domains,int),'query_id':_scope(args.queries),
              'scenario':_scope(args.scenarios),'method':_scope(args.methods)}
    for field, values in scopes.items():
        if values is not None and not values <= {row[field] for row in rows}:
            raise ValueError('undeclared '+field+' scope')
    result = [row for row in rows if all(values is None or row[field] in values
        for field,values in scopes.items())]
    if not result:
        raise ValueError('no declared workload entries match the requested scopes')
    for field, values in scopes.items():
        if values is not None and not values <= {row[field] for row in result}:
            raise ValueError('requested '+field+' scope has no entry after other filters')
    identities = {(r['N'],r['query_id'],r['scenario'],r['method'],r['use_bound']) for r in result}
    if len(identities) != len(result):
        raise ValueError('duplicate configured workload entries')
    return result


def declared_worker_job(config,args):
    """Check direct worker invocations against the same configured workload."""
    scoped = argparse.Namespace(diagnostic=args.diagnostic,ablation=args.ablation,
        no_bound=args.no_bound,solve_limit_seconds=args.solve_limit_seconds,
        domains=str(args.n),queries=args.query,scenarios=args.scenario,methods=args.method)
    matches = [row for row in selected_workload(config,scoped)
               if row['use_bound'] == (not args.no_bound)]
    if len(matches) != 1:
        raise ValueError('worker must identify exactly one declared workload entry')
    return matches[0]

