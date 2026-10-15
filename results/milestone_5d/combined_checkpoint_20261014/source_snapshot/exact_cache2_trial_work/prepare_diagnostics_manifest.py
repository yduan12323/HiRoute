"""Small metadata/source preparation only. Never loads graph or launches a worker."""
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parent;BASE=ROOT.parent
sys.path[:0]=[str(ROOT/'src'),str(BASE/'optimized_od06_phase2/runner')]
from timecut5.feasible_incumbent import canonical,sha,verifier_sources

def main():
    original=BASE/'production_sparse_handoff/exact_manifest.json'
    spec=json.loads(original.read_bytes())
    for name,digest in spec['source_sha256'].items():
        if sha((BASE/name).read_bytes())!=digest:
            raise ValueError('Baseline source changed: '+name)
    protocol=json.loads((ROOT/'DIAGNOSTIC_PROTOCOL.json').read_bytes())
    effective=dict(spec['domain_binding']['query'],H_ref=spec['initial_max_depth'])
    spec.update(schema='hiroute.exact_search_cache2_phase.v1',
        scope='two_sequential_cold_methods_cache2_config_trial_no_heuristic',
        baseline_diagnostic_manifest_sha256='f5dcb77997b32b47ad0204a5aaad00e9bb37aaf2226ca509eb80ed6cd1bb68e4',
        cache=protocol['cache'],
        prior_manifest_sha256=sha(original.read_bytes()),
        protocol_sha256=sha((ROOT/'DIAGNOSTIC_PROTOCOL.json').read_bytes()),
        containment=protocol['containment'],limits=protocol['containment'],
        progress_enabled=True,progress_interval_seconds=.25,progress_max_events=64,
        effective_exact_query_sha256=sha(canonical(effective)),
        approved_verifier_sha256=verifier_sources())
    files=[*sorted((ROOT/'src/timecut5').glob('*.py')),
           *[ROOT/name for name in ('production_boundary.py','experimental_exact_worker.py',
              'phase_supervisor.py','run_diagnostics.py','prepare_diagnostics_manifest.py',
              'test_progress.py','test_phase_controller.py','test_cache_configuration.py','compare_sources.py','DIAGNOSTIC_PROTOCOL.json')]]
    for path in files:
        spec['source_sha256'][str(path.relative_to(BASE))]=sha(path.read_bytes())
    if len(spec['source_sha256'])>128:raise ValueError('Observer source identity count exceeded')
    target=ROOT/'diagnostics_manifest.json'
    # Preparing a replacement is forbidden once actual execution state exists.
    if (ROOT/'diagnostics_ledger.json').exists() or any((ROOT/name).exists() for name in ('diagnostic_flat','diagnostic_hier')):
        raise ValueError('Cannot regenerate an admitted/executed phase manifest')
    target.write_text(json.dumps(spec,sort_keys=True,indent=2)+'\n')
    print(json.dumps(dict(manifest_sha256=sha(target.read_bytes()),source_entries=len(spec['source_sha256']),
                         verifier_entries=len(spec['approved_verifier_sha256']),
                         effective_exact_query_sha256=spec['effective_exact_query_sha256'],
                         graph_loaded=False,worker_started=False,ledger_created=False)))
if __name__=='__main__':main()
