import sys,json,hashlib,shutil,platform,importlib.metadata
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parent;S=B/'sparse_feasible_handoff_work';O=B/'optimized_od06_phase2'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
old=json.loads((O/'runner/source_provenance.json').read_bytes())
new=json.loads((S/'SOURCE_MANIFEST.json').read_bytes())
closure={}
for prefix,source in [(O/'runner',old),(S,new)]:
 for p,h in source['source_sha256'].items():
  assert sha(prefix/p)==h,p
  closure[str((prefix/p).relative_to(B))]=h
for p in ['witness_worker.py','run_witness.py','prepare_manifest.py']:closure[str((R/p).relative_to(B))]=sha(R/p)
verifier={'timecut5.'+Path(p).stem:h for p,h in new['source_sha256'].items() if p.startswith('src/timecut5/')}
verifier['validation.reference5.model']=new['source_sha256']['validation/reference5/model.py']
m=dict(schema='hiroute.real_sparse_witness_experiment.v1',scope='witness_only_no_exact_no_landmark',input_spec=dict(row_id='OD06_energy_and_scheduled_soc3_10_n128_flat',manifest=str(O/'inputs/frozen_manifest.json'),queries=str(O/'inputs/queries.json'),pools=str(O/'inputs/pools.json'),graph_dir=str(O/'inputs/graph')),hierarchy_path='hierarchy_input/hierarchy.json',checkpoint_path='optimized_od06_phase2/runner/runs/OD06_energy_and_scheduled_soc3_10_n128_flat/worker/diagnostic/snapshot.json',source_sha256=closure,approved_verifier_sha256=verifier,region_policy='sorted_site_ids_binary_split_leaf1_v1',source_hierarchy_bytes_verified=True,original_hierarchy_equivalence=False,region_tree_not_constructed_in_witness_stage=True,compiler_sha256=sha(shutil.which('g++')),compiler_flags=['-O3','-std=c++17'],interpreter=dict(path=sys.executable,sha256=sha(sys.executable),version=sys.version),limits=dict(wall_s=120,cpu_soft_s=115,cpu_hard_s=116,single_cpu_affinity=True,per_process_address_space_bytes=8*1024**3,cleanup_s=3),memory_limit_is_cgroup=False,denominator_included=False,exact_next_stage_review_required=True,loader_policy='prior_reviewed_seed_only_launcher.load_graph; preserved_parquet_row_order; metadata_and_row_count_checks_added; original_m5d_loader_source_unavailable',prior_review=sha(S/'INDEPENDENT_REVIEW.json'))
m['checkpoint_sha256']=sha(B/m['checkpoint_path'])
(R/'experiment_manifest.json').write_text(json.dumps(m,sort_keys=True,indent=2)+'\n')
print('manifest',sha(R/'experiment_manifest.json'),'source files',len(closure),'verifier files',len(verifier))
