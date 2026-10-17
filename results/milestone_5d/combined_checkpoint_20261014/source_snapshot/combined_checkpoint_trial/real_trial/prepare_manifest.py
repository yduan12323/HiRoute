"""Prepare a new combined acceptance manifest; never launch a numerical worker."""
from pathlib import Path
import hashlib,json,sys,runpy
ROOT=Path(__file__).resolve().parent;BASE=ROOT.parents[1]
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def main():
    target=ROOT/'launch_manifest.json'
    if target.exists() or (ROOT/'ledger.json').exists():raise FileExistsError('Immutable phase already prepared or started')
    prior=BASE/'durable_incumbent_work/real_trial/launch_manifest.json'
    if (prior.parent/'ledger.json').exists():raise ValueError('Durable-only predecessor was already attempted')
    spec=json.loads(prior.read_bytes());old_hash=sha(prior)
    for name,digest in spec['source_sha256'].items():
        if sha(BASE/name)!=digest:raise ValueError('Predecessor source changed: '+name)
    for row in spec['verified_input_files'].values():
        if sha(row['path'])!=row['sha256']:raise ValueError('Frozen physical input changed')
    # Import worker dependencies only. No __main__, graph loading or native build.
    runpy.run_path(str(ROOT/'worker.py'),run_name='combined_manifest_import_check')
    from timecut5.feasible_incumbent import verifier_sources
    files=[*sorted((ROOT.parent/'candidate/src/timecut5').glob('*.py')),
           *sorted((ROOT.parent/'integration').glob('*.py')),
           *sorted(ROOT.glob('*.py'))]
    sources=dict(spec['source_sha256'])
    for p in files:sources[str(p.relative_to(BASE))]=sha(p)
    spec.update(schema='hiroute.combined_checkpoint_launch.v1',launchable=True,
        state='prepared_unrun_requires_exact_manifest_review_and_exclusive_slot',
        predecessor=dict(manifest_path=str(prior.relative_to(BASE)),manifest_sha256=old_hash,
            state='prepared_but_unrun',supersession='combined_witness_and_completed_layer_acceptance_no_durable_only_run'),
        source_sha256=sources,approved_verifier_sha256=verifier_sources(),
        scope='same_OD06_N128_cache2_exact120_plus_fresh_witness_and_completed_layer_reconstruction',
        native_path_normalization='verify_actual_loaded_binary_source_compiler_options_then_normalize_only_binary_output_path_and_matching_o_argument',
        layer_envelope=dict(enabled=True,original_seed_reconstruction=True,last_complete_layer_only=True,
            embedded_verified_incumbent=True,source_bound_observable_descriptors=True,
            conservative_primary_only=True,no_lexicographic_gap=True,no_optimality_claim=True),
        recovery=dict(total_wall_seconds=120,cpu_soft_seconds=115,cpu_hard_seconds=116,
            latest_witness_result_persisted_before_replay=True,original_seed_required=True,
            same_effective_H_ref=37,same_search_cache2=True,independent_verifier_cache_bytes=0,
            timeout_preserves_separate_witness_result=True,no_automatic_retry=True),
        accounting=dict(worker_reservations={'flat':370,'hier':370},fresh_verifier_reservations={'flat':150,'hier':150},
            conservative_preparation_allowance_cpu_seconds=120,total_reserved_cpu_seconds=1160,
            all_setup_hashing_verification_persistence_and_reconstruction_charged=True,
            charge_every_failure=True,historical_ledger_unchanged=True),
        progress_identity='full_source_closure_digest_with_complete_manifest_retained',
        launch_requirements=['combined_wrapper_independent_review','exact_manifest_and_source_hash_match',
            'fixed_supplement_releases_parent_owned_exclusive_graph_slot'])
    target.write_text(json.dumps(spec,sort_keys=True,indent=2)+'\n')
    if sha(prior)!=old_hash:raise ValueError('Predecessor manifest unexpectedly changed')
    print(json.dumps(dict(manifest_sha256=sha(target),source_entries=len(sources),graph_loaded=False,worker_started=False)))
if __name__=='__main__':main()
