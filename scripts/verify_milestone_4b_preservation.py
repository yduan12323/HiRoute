"""Read-only M1–4A verification; records are written exclusively under M4B."""
import argparse
from datetime import datetime,timezone
import json
import subprocess
from _common import ROOT,sha256,read_config,configs,verified_dataset


def verify_inputs():
    checks={}
    for milestone in ['milestone_2','milestone_3a','milestone_4a']:
        path=ROOT/'results'/milestone/'preservation_before.json'
        checkpoint=json.loads(path.read_text())
        changed=[p for p,h in checkpoint['preserved_files'].items() if not (ROOT/p).exists() or sha256(ROOT/p)!=h]
        if changed:raise ValueError(f'Previous checkpoint mismatch: {changed}')
        checks[milestone]=len(checkpoint['preserved_files'])
    for config in ['configs/data.yaml','configs/data_extended.yaml']:
        data,routing=configs(config);verified_dataset(data)
        directory=ROOT/data['graph_dir'];meta=json.loads((directory/'metadata.json').read_text())
        assert meta['run']['configuration']['routing']==routing
        for p,record in meta['files'].items():assert sha256(directory/p)==record['sha256']
    manifest=read_config('data/raw/opportunities/slovenia_extended_75km/MANIFEST.yaml')
    for p,h in manifest['files'].items():assert sha256(ROOT/'data/raw/opportunities/slovenia_extended_75km'/p)==h
    for source in json.loads((ROOT/'results/milestone_3a/sources.json').read_text())['sources']:
        assert sha256(ROOT/source['path'])==source['sha256']
        header=json.loads(subprocess.check_output(['../osmium-env/bin/osmium','fileinfo','-j',source['path']]))
        assert header['header']['option']['osmosis_replication_timestamp']=='2026-09-29T20:22:51Z'
    benchmark=json.loads((ROOT/'results/milestone_4a/benchmark.json').read_text())
    for p,h in benchmark['result_files'].items():assert sha256(ROOT/'results/milestone_4a'/p)==h
    return checks


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture',action='store_true')
    parser.add_argument('--checkpoint',default='results/milestone_4b/preservation_before.json')
    args=parser.parse_args();checks=verify_inputs();path=ROOT/args.checkpoint
    if args.capture:
        bases=['data/raw','data/processed','results/milestone_1','results/milestone_2','results/milestone_3a','results/milestone_4a','src/graph','src/envelope','src/opportunity']
        files=[p for base in bases for p in (ROOT/base).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
        files+=list((ROOT/'configs').glob('*.yaml'))+list((ROOT/'docs').glob('MILESTONE*.md'))+[ROOT/'RESEARCH_SPEC.md']
        files=[p for p in files if p.name not in ['microplan.yaml','MILESTONE_4B_REPORT.md']]
        record={'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
                'git_status':subprocess.check_output(['git','status','--porcelain'],text=True),
                'previous_checkpoints':checks,'preserved_files':{str(p.relative_to(ROOT)):sha256(p) for p in files}}
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('x') as stream:json.dump(record,stream,indent=2)
        print('Captured',len(record['preserved_files']),'files');return
    before=json.loads(path.read_text())
    changed=[p for p,h in before['preserved_files'].items() if not (ROOT/p).is_file() or sha256(ROOT/p)!=h]
    record={'passed':not changed,'changed_files':changed,'verified_files':len(before['preserved_files']),
            'previous_checkpoints':checks,'timestamp_utc':datetime.now(timezone.utc).isoformat()}
    (ROOT/'results/milestone_4b/preservation_after.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record,indent=2))
    if changed:raise ValueError(f'Protected artifact changed: {changed}')

if __name__=='__main__':main()
