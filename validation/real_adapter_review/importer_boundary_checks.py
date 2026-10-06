"""Adversarial mock-only importer boundary checks. No graph or search."""
from pathlib import Path
import json,sys,tempfile
from unittest.mock import patch
sys.path[:0]=['/workspace/shared/navigation_audit/worktrees/HiRoute-m5-time-cut/src',
             '/workspace/shared/navigation_audit/worktrees/HiRoute-m5-time-cut/tests']
from test_real_export_input import TestRealExportInput,blob
results=[]
def run(name,edit,error='escapes'):
    f=TestRealExportInput();f.setUp()
    try:
        with tempfile.TemporaryDirectory() as external:
            edit(f,Path(external))
            with patch('timecut5.bounded.Problem.__init__',side_effect=RuntimeError('graph invoked')):
                try:f.load()
                except (ValueError,TypeError,KeyError) as e:
                    if error and error not in str(e):raise
                    results.append(dict(name=name,status='rejected',exception=type(e).__name__,message=str(e)))
                else:raise AssertionError(f'{name}: accepted invalid bundle')
    finally:f.doCleanups()
def symlink(f,external,name):
    p=f.root/name;other=external/name;other.write_bytes(p.read_bytes());p.unlink();p.symlink_to(other)
for name in ['export_manifest.json','query_states_resolved.json','table.json','restriction.json']:
    run('symlink_escape_'+name,lambda f,e,name=name:symlink(f,e,name))
for value in ['/tmp/not_the_table.json','../table.json','nested/../../table.json','']:
    def edit(f,e,value=value):f.table_spec['path']=value;f.refresh()
    run('path_'+repr(value),edit,error='Relative' if value.startswith('/') or value=='' else 'escapes')
def duplicate_state_object(f,e):
    data=blob([f.state]);needle=b'"state_id": "mock"';assert needle in data
    data=data.replace(needle,b'"state_id": "fake", "state_id": "mock"')
    f.manifest['query_states_resolved_sha256']=f.write('query_states_resolved.json',data)
    f.manifest_hash=f.write('export_manifest.json',f.manifest)
run('duplicate_state_object_key',duplicate_state_object,error='Duplicate JSON')
def duplicate_selection_object(f,e):
    data=(f.root/'selection.json').read_bytes();data=data.replace(b'"original_hierarchy_sha256":',b'"original_hierarchy_sha256":"bad", "original_hierarchy_sha256":')
    f.selection_hash=f.write('selection.json',data)
run('duplicate_selection_object_key',duplicate_selection_object,error='Duplicate JSON')
Path(__file__).with_name('importer_boundary_results.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results,indent=2))
