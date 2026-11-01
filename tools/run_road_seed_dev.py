"""Frozen ten-row second-segment DEV; reuses the existing guarded pilot runner."""
from __future__ import annotations
import argparse
import copy
import json
from pathlib import Path
import time
from types import SimpleNamespace

from real_scale_inputs import select_domains
import run_real_scale_pilot as pilot

ROOT=Path(__file__).resolve().parents[1]


def jobs(config):
    result=[]
    for domain in config['domains']:
        for profile,methods in domain['profiles'].items():
            if profile not in config['profiles']:
                raise ValueError('undeclared implementation profile')
            for method in methods:
                if method not in ('flat_bb_strong','scale'):
                    raise ValueError('undeclared method')
                result.append((domain,profile,method))
    identities=[(d['id'],p,m) for d,p,m in result]
    if len(set(identities))!=len(identities):
        raise ValueError('duplicate DEV jobs')
    return result


def prepare(config_path,input_root,output_root):
    """Selection is measured preprocessing, before any solver is invoked."""
    config=json.loads(config_path.read_text())
    base=json.loads((ROOT/config['base_config']).read_text())
    if config['model']!=base['model']:
        raise ValueError('second segment must preserve the declared physical model')
    if config['resources']!=base['resources']:
        raise ValueError('second segment must preserve the original resource limits')
    start,cpu=time.monotonic(),time.process_time()
    sites=json.loads((input_root/'shared-sites.json').read_text())
    bindings=json.loads((input_root/'site-bindings.json').read_text())
    assessment={}
    for width in config['selection_assessment']['corridor_halfwidths_km']:
        c=copy.deepcopy(base);c['selection']['corridor_km']=width
        manifest=select_domains(c,sites,bindings)
        assessment[str(width)]={q['query_id']:q['scenario_eligible_counts'] for q in manifest['queries']}
    prepared=[]
    for d,profile,method in jobs(config):
        identity=f"{d['id']}-{profile}-{method}"
        c=copy.deepcopy(base)
        c['selection'].update(corridor_km=d['corridor_km'],candidate_counts=[d['N']])
        c['selection']['candidate_rule']=c['selection']['candidate_rule'].replace('50 km',str(d['corridor_km'])+' km')
        c['implementation']=config['profiles'][profile]
        c['pilot_matrix']=[dict(N=d['N'],query_ids=[d['query_id']],scenarios=[d['scenario']])]
        manifest=select_domains(c,sites,bindings)
        cp,mp=output_root/(identity+'.config.json'),output_root/(identity+'.preflight.json')
        pilot.atomic(cp,c);pilot.atomic(mp,manifest)
        prepared.append(dict(identity=identity,domain=d,profile=profile,method=method,
                             config=str(cp),preflight=str(mp)))
    receipt=dict(scope=config['scope'],assessment=assessment,jobs=prepared,
        preparation_wall_s=time.monotonic()-start,preparation_cpu_s=time.process_time()-cpu,
        solver_called=False,graph_preparation='Reuse existing exact Shandong TSV; no conversion or download',
        carried_cpu_s=config['accounting']['carried_cpu_s'],
        development_validation_cpu_s=config['accounting']['development_validation_cpu_s'])
    pilot.atomic(output_root/'preparation.json',receipt)
    return config,receipt


def main(args):
    output=Path(args.output_root).resolve()
    output.mkdir(parents=True,exist_ok=False)
    source=Path(args.input_root).resolve()
    config,receipt=prepare(Path(args.config),source,output)
    total=config['accounting']['carried_cpu_s']+config['accounting']['development_validation_cpu_s']
    # Preparation is separately charged above; each worker's entire observed CPU
    # (including cold index and compiler) is conservatively added to solve budget.
    for job in receipt['jobs']:
        result=output/(job['identity']+'.jsonl')
        run=SimpleNamespace(config=job['config'],preflight=job['preflight'],
            graph_tsv=str(source/'real-scale-road.tsv'),native_cache=str(output/'native-cache'),
            output=str(result),preflight_only=args.preflight_only,
            domains=str(job['domain']['N']),queries=job['domain']['query_id'],
            scenarios=job['domain']['scenario'],methods=job['method'],
            diagnostic=False,ablation=False,no_bound=False,solve_limit_seconds=None,
            development_cpu_s=total,cold_load_allowance_s=180,process_memory_gib=8)
        pilot.main(run)
        if args.preflight_only:
            continue
        rows=[json.loads(line) for line in result.read_text().splitlines()]
        if len(rows)!=1:
            raise ValueError('one guarded worker result required per declared job')
        row=rows[0]
        row.update(domain_id=job['domain']['id'],profile=job['profile'],
            corridor_km=job['domain']['corridor_km'],domain_note=job['domain'].get('domain_note'))
        total=row['new_total_cpu_s']
        with (output/'results.jsonl').open('a') as stream:
            stream.write(json.dumps(row,sort_keys=True)+'\n')
        pilot.atomic(output/'status.json',dict(completed_job=job['identity'],
            completed_rows=sum(1 for _ in (output/'results.jsonl').open()),charged_cpu_s=total,
            state='running'))
    pilot.atomic(output/'status.json',dict(state='preflight_only' if args.preflight_only else 'complete',
        charged_cpu_s=total,declared_rows=len(receipt['jobs'])))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',default=str(ROOT/'configs/real_scale_road_seed_dev.json'))
    p.add_argument('--input-root',required=True)
    p.add_argument('--output-root',required=True)
    p.add_argument('--preflight-only',action='store_true')
    main(p.parse_args())
