"""Importer tests use tiny mock bundles and never optimize real queries."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from timecut5.real_export_input import load_exported_case
from timecut5.real_legs import encode_binary64,restrict_frozen_tree

ROOT=Path(__file__).resolve().parents[1]
MOCK=json.loads((ROOT/'results/milestone_5_real_leg_contract/mock_solver_cases.json').read_text())[1]


def blob(value):return (json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
def digest(value):return hashlib.sha256(value).hexdigest()


class TestRealExportInput(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        table=deepcopy(MOCK['table']);query=MOCK['query']
        tree=blob(MOCK['original_tree']);tree_hash=digest(tree)
        self.write('tree.json',tree)
        chosen=[dict(site_id=s['site_id'],access_node=s['anchor_id'].split(':')[1],eligible_actions=s['effects']) for s in table['sites']]
        selection=dict(original_hierarchy_sha256=tree_hash,pools=[dict(pool_id='p',instance_id=0,mode='energy_only',chosen=chosen,selected_site_ids=[x['site_id'] for x in chosen])])
        self.selection_hash=self.write('selection.json',selection)
        table['hierarchy_sha256']=tree_hash;table['selection_certificate_sha256']=self.selection_hash
        self.table_spec=dict(path='table.json',sha256=self.write('table.json',table))
        restricted=restrict_frozen_tree(tree,tree_hash,[s['site_id'] for s in table['sites']])
        restriction=dict(schema='hiroute.original_tree_restriction.v1',original_sha256=tree_hash,selection_certificate_sha256=self.selection_hash,pool_id='p',selected_site_ids=list(restricted.selected_site_ids),regions=[dict(region_id=r.region_id,parent_id=r.parent_id,child_ids=list(r.child_ids),site_ids=list(r.site_ids)) for r in restricted.regions])
        self.r_spec=dict(path='restriction.json',sha256=self.write('restriction.json',restriction))
        baseline=next(l for l in table['legs'] if l['source_anchor']==table['origin_anchor'] and l['target_anchor']==table['destination_anchor'])
        self.state=dict(state_id='mock',pool_id='p',instance_id=0,mode='energy_only',origin_road_anchor='o',destination_road_anchor='z',immutable_direct_leg_table=self.table_spec,original_tree_restriction=self.r_spec,accepted_baseline_time_s=baseline['time_s'],accepted_baseline_actual_length_m=baseline['actual_length_m'],H_ref=query['H_ref'],start_time_s=query['start_time_s'],initial_energy_kwh=query['initial_energy_kwh'],capacity_kwh=query['capacity_kwh'],overhead_s=query['overhead_s'],consumption_kwh_per_m=query['consumption_kwh_per_m'],energy_floor_kwh=query['minimum_energy_kwh'],terminal_reserve_kwh=query['reserve_kwh'],stop_penalty_s=query['lambda_stop_s'],initial_soc='2/5',charging_primitive=dict(energy_breakpoints_kwh=['0','5'],slopes_s_per_kwh=['1'],intercepts_s=['0']),schedule=None)
        self.manifest=dict(selection_certificate_sha256=self.selection_hash,hierarchy_sha256=tree_hash,status='export_complete_preparation_only',no_optimization=True,tables={'p':self.table_spec},restrictions={'p':self.r_spec})
        self.refresh()

    def write(self,path,value):
        data=value if isinstance(value,bytes) else blob(value)
        (self.root/path).write_bytes(data);return digest(data)

    def refresh(self,states=None):
        self.manifest['query_states_resolved_sha256']=self.write('query_states_resolved.json',[self.state] if states is None else states)
        self.manifest_hash=self.write('export_manifest.json',self.manifest)

    def load(self):
        return load_exported_case(self.root,'mock',self.manifest_hash,selection_path=self.root/'selection.json',expected_selection_sha256=self.selection_hash,original_hierarchy_path=self.root/'tree.json')

    def test_readonly_translation_without_optimization_or_graph(self):
        with patch('timecut5.bounded.Problem.__init__',side_effect=RuntimeError('graph constructor')):
            prepared=self.load()
        self.assertEqual(prepared.query['initial_energy_kwh'],2)
        self.assertEqual(prepared.query['charging_segments'],[['0','5','1','0']])
        self.assertEqual(len(prepared.restriction.regions),3)

    def test_hash_mismatch(self):
        (self.root/'table.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'hash mismatch'):self.load()

    def test_path_escape(self):
        self.table_spec['path']='../table.json';self.refresh()
        with self.assertRaisesRegex(ValueError,'escapes'):self.load()

    def test_duplicate_state_and_json_keys(self):
        self.refresh([self.state,self.state])
        with self.assertRaisesRegex(ValueError,'Duplicate state'):self.load()
        data=b'{"a":1,"a":2}'
        self.manifest_hash=self.write('export_manifest.json',data)
        with self.assertRaisesRegex(ValueError,'Duplicate JSON'):self.load()

    def test_original_restriction_rows_are_recomputed(self):
        value=json.loads((self.root/'restriction.json').read_text());value['regions'][0]['site_ids']=[]
        self.r_spec['sha256']=self.write('restriction.json',value);self.refresh()
        with self.assertRaisesRegex(ValueError,'restriction mismatch'):self.load()

    def test_soc_and_baseline_cannot_drift(self):
        self.state['initial_soc']='1/2';self.refresh()
        with self.assertRaisesRegex(ValueError,'SOC/energy'):self.load()
        self.state['initial_soc']='2/5';self.state['accepted_baseline_time_s']=encode_binary64(3.);self.refresh()
        with self.assertRaisesRegex(ValueError,'baseline mismatch'):self.load()

    def test_table_binding_and_mode_cannot_drift(self):
        self.state['immutable_direct_leg_table']=dict(self.table_spec,sha256='0'*64);self.refresh()
        with self.assertRaisesRegex(ValueError,'State/table'):self.load()
        self.state['immutable_direct_leg_table']=self.table_spec;self.state['mode']='unexpected';self.refresh()
        with self.assertRaisesRegex(ValueError,'State/pool'):self.load()

    def test_wrong_original_tree_fails_before_restriction(self):
        self.write('tree.json',{})
        with self.assertRaisesRegex(ValueError,'hash mismatch'):self.load()


if __name__=='__main__':unittest.main()
