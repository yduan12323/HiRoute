"""Mock-only reproducer. Run once normally and once with python -O."""
import hashlib,json,sys
from pathlib import Path
sys.path.insert(0,'/workspace/shared/navigation_audit/worktrees/HiRoute-m5-time-cut/src')
from timecut5.real_legs import ImmutableLegTable,restrict_frozen_tree
from timecut5.real_adapter import solve_hierarchical_real,replay_real_witness
from timecut5.probe import Event,State,Witness
root=Path('/workspace/shared/navigation_audit/worktrees/HiRoute-m5-time-cut')
case=json.loads((root/'results/milestone_5_real_leg_contract/mock_solver_cases.json').read_text())[1]
blob=lambda x:json.dumps(x,sort_keys=True,separators=(',',':')).encode()
table=ImmutableLegTable.from_bytes(blob(case['table']),case['table_sha256'])
tree=restrict_frozen_tree(blob(case['original_tree']),case['original_tree_sha256'],list(table.sites))
q=case['query']
forged=Witness(0,2,-2,(),State('road:z',0,0),(Event('initial','road:o',0,0,2,2),))
try:
 print('forged_incumbent_key',replay_real_witness(q,table,forged))
 print('with_forged_incumbent',solve_hierarchical_real(q,table,tree,incumbent=forged).canonical()['result'])
except Exception as e:
 print('rejected',type(e).__name__,str(e))
print('without_external_incumbent',solve_hierarchical_real(q,table,tree).canonical()['result'])
