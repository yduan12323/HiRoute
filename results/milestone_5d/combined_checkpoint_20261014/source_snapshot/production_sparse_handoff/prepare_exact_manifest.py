"""Prepare review material only. Never starts production native or exact work."""
from pathlib import Path
import json,sys,hashlib,shutil,subprocess,importlib.metadata
R=Path(__file__).resolve().parent;B=R.parent;S=B/'sparse_feasible_handoff_work';O=B/'optimized_od06_phase2'
sys.path[:0]=[str(S/'src'),str(S),str(O/'deps')]
from timecut5.feasible_incumbent import canonical,sha
from timecut5.hierarchy import build_regions
from timecut5.sparse_feasible_execution import _tree
m=json.loads((R/'experiment_manifest.json').read_bytes())
qs=json.loads((O/'inputs/queries.json').read_bytes())
b=next(x for x in qs['queries'] if x['query_id']=='OD06_energy_and_scheduled_soc3_10')['bindings']['128']
m.update(schema='hiroute.production_sparse_exact_experiment.v1',scope='two_separately_budgeted_cold_methods_no_heuristic',domain_binding=b,hierarchy_sha256=b['query']['hierarchy_sha256'],hierarchy_absolute_path=str(B/'hierarchy_input/hierarchy.json'),region_tree_sha256=sha(canonical(_tree(build_regions(b['candidate_site_ids'],leaf_size=1)))),region_tree_not_constructed_in_witness_stage=False,initial_upper_bound='232876014671007378489/6871947673600000',initial_max_depth=37,protocol_sha256=sha((R/'NEXT_PHASE_PROTOCOL.json').read_bytes()),compiler_path=shutil.which('g++'))
m['provider_source_sha256']=json.loads((B/m['checkpoint_path']).read_bytes())['source_sha256']
m['limits']=dict(wall_s=600,cpu_soft_s=595,cpu_hard_s=596,single_cpu_affinity=True,per_process_address_space_bytes=8*1024**3,cleanup_s=3)
m['runtime_packages']={name:importlib.metadata.version(name) for name in ['numpy','pandas','pyarrow','psutil','igraph','pyproj','scipy','matplotlib','texttable','certifi']}
tools=[m['compiler_path']]
for arg in ['-print-prog-name=cc1plus','-print-prog-name=collect2','-print-prog-name=ld','-print-prog-name=as']:
 p=subprocess.check_output([m['compiler_path'],arg],text=True).strip();tools.append(shutil.which(p) or p)
m['toolchain_sha256']={str(Path(p).resolve()):sha(Path(p).read_bytes()) for p in tools}
for name in ['production_boundary.py','exact_worker.py','run_exact.py','prepare_exact_manifest.py','test_production_boundary.py','test_controller.py']:
 m['source_sha256'][str((R/name).relative_to(B))]=sha((R/name).read_bytes())
(R/'exact_manifest.json').write_text(json.dumps(m,sort_keys=True,indent=2)+'\n')
print(sha((R/'exact_manifest.json').read_bytes()))
