"""One-pass original-node domain equality over a genuine checked C01 trace.

This checks domains and occurrence order, not numerical certificates. A caller
must separately cold-admit the retained numerical registry and bind its query
projections before reporting any combined acceptance.
"""
import hashlib

from validation.family5.checker import _plain, canonical, require, wire_equal
from validation.trace5 import CheckedTrace


def _regions(root):
    found = {}
    stack = [root]
    while stack:
        region = stack.pop()
        ident = region['id']
        require(ident not in found, 'duplicate original region')
        found[ident] = region
        stack.extend(reversed(region['children']))
    return found


def check_domains(checked, projected=None, *, before=lambda: None):
    """Index Region/groups once, then compare every query and empty event.

    ``projected`` is a callback returning an authenticated admitted query
    projection for a nonempty query sequence. It must raise on a missing row.
    No stored pass flag grants authority to this function.
    """
    require(type(checked) is CheckedTrace and checked.summary['verified'] is True,
            'genuine verified trace required')
    require(projected is None or callable(projected), 'projection callback required')
    events = checked._trace['events']
    require(checked.summary['events'] == len(events) and
            checked.summary['exact_node_queries'] == len(checked.queries) and
            checked.summary['empty_action_queries'] == len(checked.empty_action_queries),
            'checked trace summary differs from original events')
    starts = [event for event in events if event['kind'] == 'run_start']
    require(len(starts) == 1, 'one original Region tree required')
    regions = _regions(starts[0]['payload']['regions'])
    physics = checked.bundle._physics
    families = checked.bundle._pieces
    groups = {}
    indexed = {row['query_seq']: row for row in checked.queries}
    empty = {row['query_seq']: row for row in checked.empty_action_queries}
    require(len(indexed) == len(checked.queries) and len(empty) == len(checked.empty_action_queries)
            and not (set(indexed) & set(empty)), 'checked query identities duplicate or overlap')
    seen_indexed = seen_empty = slots = 0
    digest = hashlib.sha256()
    digest.update(b'[')
    previous = -1
    for position, event in enumerate(events):
        if position % 128 == 0: before()
        require(event['seq'] == position, 'original event sequence differs')
        if event['kind'] == 'layer_start':
            for group in event['payload']['groups']:
                ident = group['group_id']
                require(ident not in groups and group['families'], 'duplicate or empty original group')
                groups[ident] = group
            continue
        if event['kind'] != 'query':
            continue
        seq = event['seq']
        require(seq > previous, 'original query order differs')
        previous = seq
        payload = event['payload']
        group = groups.get(payload['group_id'])
        region = regions.get(payload['region_id'])
        require(group is not None and region is not None, 'missing original group or region')
        roots = _plain(group['families'])
        states = [families[fid].state for fid in roots]
        require(all(state == states[0] for state in states), 'mixed guarded family states')
        state = _plain(states[0])
        rho = str(families[roots[0]].rho)
        pi = _plain(families[roots[0]].pi)
        require(all(str(families[fid].rho) == rho and _plain(families[fid].pi) == pi
                    for fid in roots), 'mixed guarded family context')
        effect = payload['effect']
        actions = ([] if effect in ('S', 'CS') and not state[1] else
                   [[site, effect] for site in region['members']
                    if physics.anchors[site] != physics.destination and
                    effect in physics.sites[site]])
        require(wire_equal(_plain(payload['actions']), actions), 'original Region actions differ')
        if actions:
            require(seq in indexed and seq not in empty, 'missing indexed nonempty query')
            row = indexed[seq]
            for key, value in (('family_ids', roots), ('actions', actions),
                               ('state', state), ('region_id', region['id']),
                               ('region_members', _plain(region['members'])),
                               ('rho', rho), ('pi', pi),
                               ('H_remaining', physics.bound-state[2]),
                               ('effect', effect), ('bound', payload['bound']),
                               ('classification', payload['classification']),
                               ('queue_serial', payload['queue_serial'])):
                require(wire_equal(_plain(row[key]), _plain(value)), 'original indexed domain differs: '+key)
            if projected is not None:
                projection = projected(seq)
                for key, value in (('family_ids', roots), ('actions', actions),
                                   ('recorded_bound', payload['bound']),
                                   ('classification', payload['classification'])):
                    require(wire_equal(projection[key], _plain(value)),
                            'admitted projection differs from original domain: '+key)
                require(projection['query_seq'] == seq and
                        type(projection['model_slots']) is int and projection['model_slots'] > 0,
                        'admitted original model occurrence missing')
                require(projection['ancestry_bundle_sha256'] == row['ancestry_bundle_sha256'],
                        'admitted original ancestry differs')
                ranges = projection['ranges']
                require(type(ranges) is list and len(ranges) == len(roots)*len(actions),
                        'admitted original occurrence ranges missing')
                offset = 0
                for family_position in range(len(roots)):
                    for action_position in range(len(actions)):
                        item = ranges[family_position*len(actions)+action_position]
                        require(item['family_position'] == family_position and
                                item['action_position'] == action_position and
                                item['query_start'] == offset and
                                type(item['query_end']) is int and item['query_end'] > offset and
                                item['logical_end']-item['logical_start'] == item['query_end']-offset,
                                'admitted original occurrence range differs')
                        offset = item['query_end']
                require(offset == projection['model_slots'], 'admitted occurrence range coverage differs')
                slots += projection['model_slots']
            seen_indexed += 1
        else:
            require(seq in empty and seq not in indexed, 'missing checked empty-action event')
            require(wire_equal(_plain(empty[seq]), dict(query_seq=seq, **_plain(payload))),
                    'checked empty-action event differs')
            seen_empty += 1
        record = dict(query_seq=seq, region_id=region['id'], group_id=payload['group_id'],
                      family_ids=roots, actions=actions, state=state,
                      classification=payload['classification'], bound=payload['bound'])
        if seen_indexed + seen_empty > 1: digest.update(b',')
        digest.update(canonical(record).encode())
    digest.update(b']')
    require(seen_indexed == len(indexed) and seen_empty == len(empty),
            'unconsumed original checked query event')
    before()
    return dict(schema='hiroute-original-node-domain-batch-v1',
                checked_queries=seen_indexed, checked_empty_action_events=seen_empty,
                total_query_events=seen_indexed+seen_empty, admitted_model_occurrences=slots,
                region_count=len(regions), group_count=len(groups),
                ordered_domain_sha256=digest.hexdigest(), numerical_certificates_rechecked=0,
                scope='original C01 query domain equality only')


def cold_collect(checked, root, args, policy, *, before=lambda: None):
    """Admit retained certificates once, then join every original occurrence.

    The caller supplies a live, independently verified trace and a running
    retained-node supervisor. The returned plan is provisional until that
    supervisor reports an actual successful, reaped return.
    """
    from .final_collector import load_registry, require_complete_registry
    from .indexed_population import admit_population
    from .query_collection import plan_query_collection
    from .window_receipts import reconcile_registry

    before()
    admitted = admit_population(root, args, checked.bundle, args.deadline, before)
    _, scheduling = load_registry(args, policy, admitted=admitted,
                                  deadline=args.deadline, before=before)
    registry = reconcile_registry(scheduling, admitted, reviewed_sources=policy,
                                  deadline=args.deadline, before=before)
    require_complete_registry(admitted, registry)
    domain = check_domains(checked, admitted.query_projection, before=before)
    commitment = admitted.commitment()
    require(domain['checked_queries'] == commitment['queries'] and
            domain['checked_empty_action_events'] == commitment['empty_action_queries'] and
            domain['admitted_model_occurrences'] == commitment['original_model_occurrences'] and
            checked.summary['query_freeze_sha256'] == commitment['query_freeze_sha256'] and
            checked.summary['trace_sha256'] == admitted._index['trace_sha256'],
            'live original node domain differs from admitted population')
    plan = plan_query_collection(admitted, registry, before=before)
    partition = plan.recover_empty_partition(checked._trace, before=before)
    summary = plan.summary()
    require(summary['planning_complete'] is True and
            summary['original_model_occurrences'] == domain['admitted_model_occurrences'] and
            partition.report()['recovered']['total_query_events'] == domain['total_query_events'],
            'retained join or empty partition differs from live original domain')
    before()
    return dict(domain=domain, population=commitment, registry=registry.metadata(),
                query_plan=summary, empty_partition=partition.report(),
                mathematical_authority='reviewed retained certificates cold admitted from historical executions',
                fresh_lp_calls=0, supervisor_acceptance=False)
