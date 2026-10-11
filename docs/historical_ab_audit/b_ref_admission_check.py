import gzip, hashlib, json, sys
from collections import Counter, defaultdict
from fractions import Fraction as F
from pathlib import Path

base = Path(__file__).resolve().parent
root = base / 'ab_evidence_tree/results/milestone_5_acceptance_b64/acceptance_populations'
audit = root / 'bound_audit'
sys.path.insert(0, str(audit / 'v2'))
from frozen_reference5.model import normalize_case, selected_legs, sequences
sys.path.insert(0, str(audit/'production_trace_v1'))
from frozen_timecut5.bounded import Problem
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
trace_root = audit/'production_trace_v1'
freeze = json.loads((trace_root/'trace_freeze.json').read_text())
for relative, digest in freeze['files'].items():
    assert sha(trace_root/relative) == digest
data = json.loads((base / 'b64_g8_node_reaudit_20261011_independent.json').read_text())
casepath = root / 'stage_b/cases.json'
cases = {c['case_id']: (c, normalize_case(c)) for c in json.loads(casepath.read_text())}
bycase = defaultdict(list)
for n in data['nodes']:
    bycase[n['case_id']].append(n)

rows = []
query_certificates = []
for cid, nodes in sorted(bycase.items()):
    source, case = cases[cid]
    legs = selected_legs(case)
    producer_legs = Problem(source).legs
    assert legs.keys() == producer_legs.keys()
    for pair, leg in legs.items():
        other = producer_legs[pair]
        assert (leg.time,leg.energy,leg.nodes,leg.edges)==(other.time,other.energy,other.path,other.edge_ids)
    terminal = []
    for seq, remaining, current in sequences(case, legs):
        if remaining or (current, case['destination']) not in legs: continue
        t = e = F(0); pos = case['origin']
        for site, effect in seq:
            leg = legs[pos, site]; t += leg.time; e += leg.energy; pos = site
        leg = legs[pos, case['destination']]; t += leg.time; e += leg.energy
        q = max(F(0), e + case['reserve_kwh'] - case['initial_energy_kwh'])
        slope = min((s[2] for s in case['charging_segments']), default=F(0))
        service = [(i, eff) for i, (_, eff) in enumerate(seq) if eff in ('S', 'CS')]
        lb = t + len(seq) * (case['overhead_s'] + case['lambda_stop_s']) + q * slope
        if service:
            i, eff = service[0]; duration = case['schedule']['D']
            lb = t + len(seq) * (case['overhead_s'] + case['lambda_stop_s']) + (q*slope + duration if eff == 'S' else max(q*slope, duration))
            pos = case['origin']; tail = t
            for j, (site, _) in enumerate(seq):
                if j <= i: tail -= legs[pos, site].time
                pos = site
            absolute = case['schedule']['a'] + duration - case['start_time_s'] + tail + (len(seq)-i-1)*case['overhead_s'] + len(seq)*case['lambda_stop_s']
            lb = max(lb, absolute)
        terminal.append((seq, lb))
    counts = Counter(); event_rows = []
    query_index = {}
    trace_hashes = {}
    for dom in (False, True):
        path = audit/'production_trace_v1/runs'/cid/f'D{int(dom)}.jsonl.gz'
        digest = sha(path)
        trace_hashes[str(path.relative_to(root))] = digest
        with gzip.open(path, 'rt') as handle:
            events = {e['index']:e['event'] for e in map(json.loads,handle) if e['kind']=='event'}
        expected = {i for i,e in events.items() if e['kind'] in ('region_decision','unreachable')}
        subset = [n for n in nodes if n['dominance']==dom]
        assert expected == {n['trace_event'] for n in subset}
        for n in subset:
            assert n['trace_sha256']==digest
            e = events[n['trace_event']]
            assert n['prefix']==e['prefix'] and n['actions']==e['actions']
            assert n['lower_bound']==e['lower_bound'] and n['region']==e['region']
    for n in nodes:
        prefix = tuple(map(tuple, n['prefix'])); actions = tuple(map(tuple, n['actions']))
        matches = [(s, b) for s,b in terminal if len(s)>len(prefix) and s[:len(prefix)] == prefix and s[len(prefix)] in actions]
        bound = min((b for _,b in matches), default=None)
        qkey = (prefix, actions)
        if qkey not in query_index:
            query_index[qkey] = len(query_certificates)
            query_certificates.append({'case_id':cid,'prefix':[list(x) for x in prefix],'actions':[list(x) for x in actions],'terminal_superset_sequences':[{'sequence':[list(x) for x in seq],'analytic_lower_bound':str(lb)} for seq,lb in matches],'analytic_superset_lower_bound':str(bound) if bound is not None else None})
        status = 'independent_structural_empty' if bound is None else ('independent_analytic_bound' if F(n['lower_bound']) <= bound else 'not_independently_certified')
        counts[status] += 1
        event_rows.append({'dominance':n['dominance'],'trace_event':n['trace_event'],'trace_sha256':n['trace_sha256'],'original_status':n['status'],'region_lower_bound':n['lower_bound'],'analytical_lower_bound':str(bound) if bound is not None else None,'terminal_superset_sequences':len(matches),'query_certificate_index':query_index[qkey],'status':status})
    provenance = nodes[0]['reference_provenance']
    report_path = root/provenance['path']
    assert all(n['reference_provenance']['path']==provenance['path'] for n in nodes)
    assert sha(report_path)==provenance['sha256']
    report = json.loads(report_path.read_text())
    stream_claim = report['replay']['stream_sha256'] if provenance['source']=='final_streamed_reference' else None
    ref = report['reference']
    rows.append({'case_id':cid,'case_sha256':hashlib.sha256(json.dumps(source,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'trace_hashes':trace_hashes,'reference_source':provenance['source'],'report_path':str(report_path.relative_to(root)),'report_sha256':sha(report_path),'missing_stream_sha256_claim':stream_claim,'reference_regimes_embedded':ref['regimes'] is not None,'node_count':len(nodes),'counts':dict(counts),'events':event_rows})

out = {'schema':'hiroute-b64-independent-analytic-node-admission-v1','source_population_sha256':sha(casepath),'auditor_output_sha256':sha(base/'b64_g8_node_reaudit_20261011_independent.json'),'producer_freeze_sha256':sha(audit/'production_trace_v1/trace_freeze.json'),'independent_leg_source_sha256':sha(audit/'v2/frozen_reference5/model.py'),'producer_leg_source_sha256':sha(audit/'production_trace_v1/frozen_timecut5/bounded.py'),'method':'Rational selected-leg terminal-sequence superset, with exact selected-leg equality to frozen producer: route time + stop overhead/penalty + minimum charging slope times unavoidable total charge; service duration and earliest completion included. Every exact node plan belongs to enumerated prefix/action terminal sequence. No stored passed field is used for inequalities. Structural emptiness means no reachable, service-complete static terminal sequence extends the trace prefix/action.','case_count':len(rows),'counts':dict(sum((Counter(r['counts']) for r in rows),Counter())),'query_certificates':query_certificates,'cases':rows}
p = base / 'b64_independent_admission_20261011.json'
p.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
print(p, out['counts'])
