"""Fail-closed accounting/coverage report, independent of producer assertions."""
from decimal import Decimal
import json
from pathlib import Path

from run_one_source_gate import frozen_header


def six(value):return str(Decimal(str(value)).quantize(Decimal('0.000001')))


def summarize(config,frozen_path,budget,progress,*,producer_result=None,checker_result=None):
    h=frozen_header(config,frozen_path)
    from generate_exact_source_unit import domain
    S,T=domain(h)
    if budget.get('active') is not None:raise ValueError('uncertain active worker cannot be terminal')
    records=budget['records'];gen=[r for r in records if r['label']=='real_origin_generation'];checks=[r for r in records if r['label']=='real_origin_check']
    if len(gen)!=1 or len(checks)>1:raise ValueError('exactly one real attempt; no duplicate or vacuous coverage')
    source=config['source'];g=gen[0]
    if set(budget['phase_charged_CPU_s'])!={'tiny_validation','real_pair','verification_tails'} or budget['fixed_precharge_CPU_s']!=240:
        raise ValueError('frozen budget phases/precharge')
    if any(r['phase'] not in budget['phase_charged_CPU_s'] for r in records):raise ValueError('unaccounted phase')
    if g['phase']!='real_pair' or g['child_CPU_limit']!=120 or g['wall_limit']!=120:raise ValueError('frozen attempt limits')
    if (budget['source'],budget['source_denominator'],budget['pair_denominator'])!=(source,65,4225):raise ValueError('budget domain drift')
    if any(r.get('reserved_CPU_s',0)<=0 or r.get('charged_CPU_s',-1)<0 or 'finished_at' not in r for r in records):raise ValueError('nonterminal/invalid resource receipt')
    for phase,used in budget['phase_charged_CPU_s'].items():
        actual=sum(Decimal(str(r['charged_CPU_s'])) for r in records if r['phase']==phase)
        if abs(actual-Decimal(str(used)))>Decimal('0.000001') or used>budget['allocations_CPU_s'][phase]:raise ValueError('phase accounting drift')
    charged=Decimal(str(budget['fixed_precharge_CPU_s']))+sum(Decimal(str(v)) for v in budget['phase_charged_CPU_s'].values())
    total=Decimal(budget['carried_research_CPU_s'])+Decimal(six(charged))
    if charged>900 or total>28800:raise ValueError('stage/original budget exceeded')
    complete=bool(producer_result and producer_result.get('decision')=='UNTRUSTED_SOURCE_CANDIDATE_COMPLETE' and g['returncode']==0 and not g.get('guard_reason'))
    verified=False
    if checks:
        if not complete:raise ValueError('checker cannot follow incomplete generation')
        c=checks[0]
        if c['phase']!='real_pair' or c['child_CPU_limit']!=120 or c['wall_limit']!=120:raise ValueError('frozen independent check limits')
        verified=bool(c['returncode']==0 and not c.get('guard_reason') and checker_result and checker_result.get('decision')=='VERIFIED_SINGLE_SOURCE_ONLY')
        if verified:
            result=checker_result['result']
            if (result['source'],result['checked_pairs'],result['source_denominator'],result['pair_denominator'],result['unrun_sources'],result['whole_table_certified'])!=(source,65,65,4225,64,False):raise ValueError('source-only proof coverage drift')
    status='VERIFIED_SINGLE_SOURCE_ONLY' if verified else 'UNKNOWN_UNCERTIFIED'
    source_rows=[dict(source=s,status=status if s==source else 'UNRUN_NOT_ADMITTED') for s in S]
    return dict(schema='hiroute.one_source_gate.report.v1',decision=status,source=source,source_denominator=65,pair_denominator=4225,
        literal_Sites=64,target_count=65,source_statuses=source_rows,
        source_status_counts={status:1,'UNRUN_NOT_ADMITTED':64},
        pair_status_counts={status:65,'UNRUN_NOT_ADMITTED':4160},independently_certified_sources=int(verified),
        independently_certified_pairs=65 if verified else 0,whole_table_certified=False,
        generation_outcome=g.get('guard_reason') or ('completed' if complete else 'failed'),
        checker_outcome=('verified' if verified else 'UNKNOWN_UNCERTIFIED') if checks else 'UNRUN_INCOMPLETE_GENERATION' if not complete else 'UNRUN',
        last_untrusted_progress=progress,real_generation_receipt=g,real_checker_receipts=checks,
        accounting=dict(stage_CPU_s=six(charged),stage_cap_CPU_s=900,carried_research_CPU_s=budget['carried_research_CPU_s'],
            research_total_CPU_s=str(total),remaining_original_CPU_s=str(Decimal(28800)-total),
            phase_CPU_s={k:six(v) for k,v in budget['phase_charged_CPU_s'].items()},
            fixed_development_controller_CPU_s=240,prior_representation_stage_CPU_s='325.696447',
            current_gate_plus_prior_representation_CPU_s=six(charged+Decimal('325.696447')),
            prior_setup_not_free=True,ordinary_software_CI='separate approved scope; prior inclusive charges retained'),
        EV_solve=False,upper_replay=False,holdout=False,original_taskbook_complete=False)


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser()
    for name in ('config','frozen-domain','artifacts','output'):p.add_argument('--'+name,required=True)
    a=p.parse_args();root=Path(a.artifacts)
    def optional(path):return json.loads(path.read_text()) if path.exists() else None
    result=summarize(json.loads(Path(a.config).read_text()),a.frozen_domain,json.loads((root/'budget.json').read_text()),
        optional(root/'generation/progress.json'),producer_result=optional(root/'generation/result.json'),checker_result=optional(root/'check/result.json'))
    Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'decision':result['decision'],'accounting':result['accounting']}))
