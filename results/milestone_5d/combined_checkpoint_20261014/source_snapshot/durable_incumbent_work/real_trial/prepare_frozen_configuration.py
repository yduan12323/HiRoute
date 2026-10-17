"""Freeze actual inputs/source configuration, never load graph or start workers."""
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parent;BASE=ROOT.parents[1]
CANDIDATE=ROOT.parent/'candidate'
sys.path[:0]=[str(CANDIDATE/'src'),str(CANDIDATE)]
from timecut5.feasible_incumbent import verifier_sources

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(4*1024**2),b''):h.update(block)
    return h.hexdigest()

def main():
    target=ROOT/'frozen_configuration.json'
    if target.exists():raise FileExistsError('Do not silently replace a frozen trial configuration')
    prior=BASE/'exact_cache2_trial_work/diagnostics_manifest.json'
    spec=json.loads(prior.read_bytes())
    for name,digest in spec['source_sha256'].items():
        if sha(BASE/name)!=digest:raise ValueError('Prior source changed: '+name)
    inputs=spec['input_spec'];graph=Path(inputs['graph_dir'])
    expected=json.loads((graph/'metadata.json').read_bytes())
    for name in ('nodes.parquet','edges.parquet'):
        if sha(graph/name)!=expected['files'][name]['sha256']:raise ValueError('Graph source changed')
    if sha(BASE/spec['checkpoint_path'])!=spec['checkpoint_sha256']:raise ValueError('Initial witness changed')
    if sha(BASE/spec['hierarchy_path'])!=spec['hierarchy_sha256']:raise ValueError('Hierarchy changed')
    input_hashes={k:dict(path=str(p),sha256=sha(p)) for k,p in inputs.items() if k in ('manifest','pools','queries')}
    input_hashes.update({name:dict(path=str(graph/name),sha256=sha(graph/name)) for name in ('nodes.parquet','edges.parquet','metadata.json')})
    sources=dict(spec['source_sha256'])
    files=[*sorted((CANDIDATE/'src/timecut5').glob('*.py')),
           ROOT.parent/'integration/production_boundary.py',ROOT.parent/'integration/sparse_durable_session.py',Path(__file__)]
    for file in files:sources[str(file.relative_to(BASE))]=sha(file)
    spec.update(schema='hiroute.durable_incumbent_fixed_od06_configuration.v1',launchable=False,
        state='frozen_inputs_and_config_pending_worker_review_and_resource_slot',
        parent_manifest_sha256=sha(prior),source_sha256=sources,approved_verifier_sha256=verifier_sources(),
        verified_input_files=input_hashes,
        scope='same_OD06_N128_cache2_exact120_with_independent_durable_feasible_evidence',
        durable_witness=dict(enabled=True,initial_seed_saved_before_search=True,
            capture='synchronous_selected_edge_and_physical_replay_before_atomic_save',
            source_cache_max_bytes=0,source_cache_max_sources=1,distinct_router=True,distinct_provider=True,
            graph_arrays_shared_readonly=True,persistence_failure='abort_invocation_recover_file_fresh',
            bound_semantics='fixed_H_ref_37_feasible_only_no_global_gap'),
        post_timeout_verification=dict(separate_process=True,one_per_method=True,cold_provider=True,
            wall_seconds=120,cpu_soft_seconds=115,cpu_hard_seconds=116,address_space_bytes=8*1024**3,
            cpu_cores=1,parent_cpu_soft_seconds=20,parent_cpu_hard_seconds=25,cleanup_seconds=3,
            reservation_cpu_seconds=150,write_search_record=False),
        accounting=dict(worker_reservations={'flat':370,'hier':370},fresh_verifier_reservations={'flat':150,'hier':150},
            conservative_preparation_allowance_cpu_seconds=120,total_reserved_cpu_seconds=1160,
            initial_and_improved_verification_in_exact_phase=True,charge_every_failure=True,
            no_resource_claim_for_prior_historical_runs=True),
        execution_order=['flat_worker','flat_fresh_verifier','hier_worker','hier_fresh_verifier'],
        resource_gate='exclusive_large_graph_slot_no_concurrent_supplement_or_other_large_graph_worker',
        launch_requirements=['new_worker_implements_reviewed_factory_and_cleanup','new_verifier_worker_is_reviewed',
            'new_supervisor_ledger_is_frozen_and_reviewed','all_runtime_source_hashes_match','parent_releases_exclusive_resource_slot'],
        holdout=False,denominator_included=False)
    target.write_text(json.dumps(spec,sort_keys=True,indent=2)+'\n')
    print(json.dumps(dict(path=str(target),sha256=sha(target),source_entries=len(sources),graph_loaded=False,worker_started=False)))
if __name__=='__main__':main()
