"""Read-only prior-milestone checks; all records stay in Milestone 4A."""
import argparse
from datetime import datetime,timezone
import json
import subprocess
from _common import ROOT,read_config,sha256,configs,verified_dataset
from _regional_common import polygon_bytes,region_polygon


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture',action='store_true')
    args=parser.parse_args();result=ROOT/'results/milestone_4a';result.mkdir(exist_ok=True)
    for checkpoint in ['results/milestone_2/preservation_before.json','results/milestone_3a/preservation_before.json']:
        prior=json.loads((ROOT/checkpoint).read_text())
        changed=[p for p,h in prior['preserved_files'].items() if sha256(ROOT/p)!=h]
        if changed:raise ValueError(f'Previous checkpoint mismatch: {changed}')
    for name in ['configs/data.yaml','configs/data_extended.yaml']:
        data,routing=configs(name);verified_dataset(data)
        directory=ROOT/data['graph_dir'];metadata=json.loads((directory/'metadata.json').read_text())
        assert metadata['run']['configuration']['routing']==routing
        for n,record in metadata['files'].items():
            if sha256(directory/n)!=record['sha256']:raise ValueError('Frozen graph fingerprint mismatch')
    regional=read_config('configs/regional.yaml')
    if (ROOT/regional['polygon_path']).read_bytes()!=polygon_bytes(region_polygon(regional)[0]):raise ValueError('Polygon mismatch')
    sources=json.loads((ROOT/'results/milestone_3a/sources.json').read_text())['sources']
    for source in sources:
        path=ROOT/source['path']
        if sha256(path)!=source['sha256']:raise ValueError('Source hash mismatch')
        header=json.loads(subprocess.check_output(['../osmium-env/bin/osmium','fileinfo','-j',str(path)]))
        if header['header']['option']['osmosis_replication_timestamp']!='2026-09-29T20:22:51Z':raise ValueError('Snapshot mismatch')
    path=result/'preservation_before.json'
    if args.capture:
        preserved=[ROOT/'RESEARCH_SPEC.md',*[ROOT/'docs'/name for name in ['MILESTONE_1_REPORT.md','MILESTONE_2_REPORT.md','MILESTONE_3A_REPORT.md','MILESTONE_3A_DATA_DESIGN.md']],
                   *[p for p in (ROOT/'configs').glob('*.yaml') if p.name != 'opportunity.yaml'],
                   *[p for base in ['data/raw/osm','data/processed','results/milestone_1','results/milestone_2','results/milestone_3a'] for p in (ROOT/base).rglob('*')],
                   ROOT/'data/raw/DATA_MANIFEST.yaml',
                   *[p for base in ['src/graph','src/envelope'] for p in (ROOT/base).glob('*.py')]]
        record={'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                'git_status':subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True),
                'preserved_files':{str(p.relative_to(ROOT)):sha256(p) for p in preserved if p.is_file()},
                'previous_checkpoints_verified':True,'six_source_headers_verified':True,'graphs_verified':True}
        with path.open('x') as f:json.dump(record,f,indent=2)
        print('Captured',len(record['preserved_files']),'previous files');return
    record=json.loads(path.read_text())
    changed=[p for p,h in record['preserved_files'].items() if not (ROOT/p).is_file() or sha256(ROOT/p)!=h]
    after={'passed':not changed,'changed_files':changed,'verified_files':len(record['preserved_files']),
           'timestamp_utc':datetime.now(timezone.utc).isoformat(),'six_source_headers_verified':True,'graphs_verified':True}
    (result/'preservation_after.json').write_text(json.dumps(after,indent=2)+'\n')
    print(json.dumps(after,indent=2))
    if changed:raise RuntimeError('Milestone 1–3A preservation failed')

if __name__=='__main__':main()
