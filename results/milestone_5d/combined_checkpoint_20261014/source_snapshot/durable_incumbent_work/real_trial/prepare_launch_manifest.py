"""Derive runnable configuration; does not execute any experiment."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent;BASE=ROOT.parents[1]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main():
    target=ROOT/'launch_manifest.json'
    if target.exists() or (ROOT/'ledger.json').exists():raise FileExistsError('Immutable manifest already exists or trial started')
    frozen=ROOT/'frozen_configuration.json';spec=json.loads(frozen.read_bytes())
    for name,digest in spec['source_sha256'].items():
        if sha(BASE/name)!=digest:raise ValueError('Frozen source changed: '+name)
    spec.update(schema='hiroute.durable_incumbent_launch.v1',launchable=True,state='requires_review_of_this_exact_manifest_and_exclusive_slot',frozen_configuration_sha256=sha(frozen))
    for name in ('worker.py','run_stage.py','phase_supervisor.py','prepare_launch_manifest.py','test_wrappers.py'):
        p=ROOT/name;spec['source_sha256'][str(p.relative_to(BASE))]=sha(p)
    if len(spec['source_sha256'])>128:raise ValueError('Observer identity bound exceeded')
    target.write_text(json.dumps(spec,sort_keys=True,indent=2)+'\n')
    print(json.dumps(dict(manifest_sha256=sha(target),source_entries=len(spec['source_sha256']),worker_started=False)))
if __name__=='__main__':main()
