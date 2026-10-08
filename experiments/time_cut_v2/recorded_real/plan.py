"""Read-only source/input plan preparation. This grants no execution authority."""
import argparse
from dataclasses import asdict
from fractions import Fraction
import hashlib,json,subprocess,time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
SOURCE_DIRS=('src/timecut5','validation/family5','validation/trace5','validation/real5_v2',
             'validation/capture5','experiments/time_cut_v2/recorded_real')
MODEL_FIELDS=('H_ref','origin','destination','start_time_s','initial_energy_kwh','capacity_kwh',
              'minimum_energy_kwh','reserve_kwh','consumption_kwh_per_m','overhead_s',
              'lambda_stop_s','charging_segments','schedule')

def require(ok,why):
 if not ok:raise ValueError(why)

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
def digest(value):return hashlib.sha256(canonical(value)).hexdigest()
def load(path):
 def pairs(rows):
  result={}
  for key,value in rows:
   require(key not in result,'duplicate JSON key');result[key]=value
  return result
 return json.loads(Path(path).read_bytes(),object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('nonfinite JSON')))
def pin(path):
 path=Path(path);require(path.is_file() and not path.is_symlink(),'regular nonsymlink input required')
 before=path.stat();h=hashlib.sha256()
 with path.open('rb') as f:
  while chunk:=f.read(65536):h.update(chunk)
 after=path.stat();require((before.st_ino,before.st_size,before.st_mtime_ns)==(after.st_ino,after.st_size,after.st_mtime_ns),'file changed during hash')
 return dict(sha256=h.hexdigest(),size_bytes=after.st_size)
def inside(root,name):
 require(type(name) is str and name and not Path(name).is_absolute() and '..' not in Path(name).parts,'relative repository path required')
 path=root/name;require(path.resolve().is_relative_to(root.resolve()) and not path.is_symlink(),'path escapes repository or is symlink');return path
def source_inventory(root):
 paths={Path('validation/__init__.py')}
 for folder in SOURCE_DIRS:
  paths.update(p.relative_to(root) for p in (root/folder).rglob('*.py'))
 return {p.as_posix():pin(inside(root,p.as_posix())) for p in sorted(paths)}
def source_commit(root):return subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
def assert_committed_sources(root,sources,commit):
 for name,spec in sources.items():
  require('\n' not in name and '\x00' not in name,'invalid source path')
  try:data=subprocess.check_output(['git','--no-pager','show',commit+':'+name],cwd=root,stderr=subprocess.DEVNULL)
  except subprocess.CalledProcessError as error:raise ValueError('source is not committed: '+name) from error
  require(len(data)==spec['size_bytes'] and hashlib.sha256(data).hexdigest()==spec['sha256'],'uncommitted source bytes: '+name)

def result_key(result):
 require(type(result) is dict and result.get('status')=='attained_optimum','fixed C01 comparison requires attained optimum')
 require(type(result['H']) is int and result['H']>=0,'invalid reference stop count')
 pi=result['site_action_tuple'];require(type(pi) in (list,tuple) and len(pi)==result['H'],'invalid reference prefix')
 require(all(type(value) in (str,int) for value in (result['J'],result['Q_total'])),'reference key must use exact numbers')
 require(all(type(item) in (list,tuple) and len(item)==2 and all(type(x) is str for x in item) and item[1] in ('C','S','CS') for item in pi),'invalid reference action tuple')
 return [str(Fraction(result['J'])),str(Fraction(result['Q_total'])),result['H'],[list(x) for x in pi]]
def model_equal(a,b):
 for name in MODEL_FIELDS:
  if name in ('origin','destination','schedule','charging_segments','H_ref'):
   require(canonical(a[name])==canonical(b[name]),'reference model mismatch: '+name)
  else:
   require(type(a[name]) in (str,int) and type(b[name]) in (str,int),'reference model numbers must be exact')
   require(Fraction(a[name])==Fraction(b[name]),'reference model mismatch: '+name)

def resolved_query(state,inputs):
 # Independent declarative translation from pinned state scalars; no producer import.
 query={k:state[k] for k in ('H_ref','start_time_s','initial_energy_kwh','capacity_kwh','overhead_s','consumption_kwh_per_m')}
 query.update(origin='road:'+str(state['origin_road_anchor']),destination='road:'+str(state['destination_road_anchor']),
  minimum_energy_kwh=state['energy_floor_kwh'],reserve_kwh=state['terminal_reserve_kwh'],lambda_stop_s=state['stop_penalty_s'],
  leg_payload_sha256=inputs['table']['sha256'],selection_certificate_sha256=inputs['selection']['sha256'],
  hierarchy_sha256=inputs['original_tree']['sha256'])
 curve=state['charging_primitive'];e,m,b=(curve[k] for k in ('energy_breakpoints_kwh','slopes_s_per_kwh','intercepts_s'))
 require(len(e)==len(m)+1==len(b)+1,'invalid resolved charging curve')
 query['charging_segments']=[[e[i],e[i+1],m[i],b[i]] for i in range(len(m))]
 if state['mode']=='energy_only':
  require(state['schedule'] is None,'energy-only schedule changed');query['schedule']=None
 else:
  require(state['mode']=='energy_and_scheduled','unsupported resolved mode');q=state['schedule']
  require(q['hard'] is True and q['compatible_with_charging'] is True,'unsupported resolved schedule')
  query['schedule']=dict(a=q['window_start_s'],b=q['window_end_s'],D=q['duration_s'])
 return query

def prepare_plan(root,export_dir,manifest_sha,selection,selection_sha,tree,*,reference=None,state_id='C01',dominance=True):
 # This preparation uses the published input translator only; it never searches.
 from timecut5.real_export_input import load_exported_case
 from .runtime import CAPTURE,REPLAY
 root=Path(root).resolve();export=inside(root,export_dir)
 prepared=load_exported_case(export,state_id,manifest_sha,selection_path=inside(root,selection),
     expected_selection_sha256=selection_sha,original_hierarchy_path=inside(root,tree))
 manifest=load(export/'export_manifest.json');states=load(export/'query_states_resolved.json')
 state=next(row for row in states if row['state_id']==state_id);pool=state['pool_id']
 names=dict(export_manifest=export_dir+'/export_manifest.json',resolved_states=export_dir+'/query_states_resolved.json',
     selection=selection,original_tree=tree,table=export_dir+'/'+manifest['tables'][pool]['path'],
     restriction=export_dir+'/'+manifest['restrictions'][pool]['path'])
 comparison=dict(status='historical_reference_missing',raw_certificates_replayed=False)
 if reference is not None:
  names['reference']=reference;ref=load(inside(root,reference))
  require(ref['state_id']==state_id and ref['pool_id']==pool and ref['table_sha256']==prepared.table.payload_sha256,'reference source context mismatch')
  model_equal(ref['query'],prepared.query)
  comparison=dict(status='historical_result_available',expected_key=result_key(ref['result']),raw_certificates_replayed=False)
 inputs={role:dict(path=name,**pin(inside(root,name))) for role,name in names.items()}
 sources=source_inventory(root);commit=source_commit(root);assert_committed_sources(root,sources,commit)
 require(type(dominance) is bool,'exact boolean dominance required')
 require(dominance or state_id=='C01','D0 is restricted to C01')
 result=dict(schema='hiroute-recorded-real-plan-v1' if dominance else 'hiroute-recorded-real-plan-v2',state_id=state_id,pool_id=pool,dominance=dominance,
     representation='exact-adjacent-cut-coalescing-v1',external_incumbent=None,
     H_ref=prepared.query['H_ref'],sites=len(prepared.table.sites),regions=len(prepared.restriction.regions),
     query=prepared.query,query_sha256=digest(prepared.query),source_commit=commit,
     source_files=sources,source_sha256=digest(sources),inputs=inputs,input_sha256=digest(inputs),
     profiles={p.name:asdict(p) for p in (CAPTURE,REPLAY)},reference=comparison,
     source_provenance_scope='pins verify current consumption chain; selection-generation sources and historical certificates are not rerun',
      numerical_suffix_optimization=False,literal_G8_closed=False)
 if not dominance:
  from .variant_scope import D0
  result['variant_id']=D0
 return result

def verify_export_chain(root,plan):
 # Recheck the manifest links independently on every admission, including replay.
 # Re-pinning a derived state cannot sever it from the separately approved export.
 from validation.real5_v2.input import prepare_real_case,decode_binary64
 inputs=plan['inputs'];pool_id=plan['pool_id']
 require(set(inputs)=={'export_manifest','resolved_states','selection','original_tree','table','restriction'} |
         ({'reference'} if 'reference' in inputs else set()),'unexpected input roles')
 manifest_path=inside(root,inputs['export_manifest']['path']);export=manifest_path.parent
 manifest=load(manifest_path);selection=load(inside(root,inputs['selection']['path']))
 require(manifest['status']=='export_complete_preparation_only' and manifest['no_optimization'] is True,'unsupported export status')
 require(manifest['query_states_resolved_sha256']==inputs['resolved_states']['sha256'],'export manifest resolved-state link changed')
 require(inside(root,inputs['resolved_states']['path']).resolve()==(export/'query_states_resolved.json').resolve(),'resolved-state path changed')
 require(manifest['selection_certificate_sha256']==inputs['selection']['sha256'],'export selection link changed')
 require(manifest['hierarchy_sha256']==selection['original_hierarchy_sha256']==inputs['original_tree']['sha256'],'export original-tree link changed')
 states=load(inside(root,inputs['resolved_states']['path']))
 require(type(states) is list and all(type(row) is dict and type(row.get('state_id')) is str for row in states),'invalid resolved states')
 ids=[row['state_id'] for row in states];require(len(ids)==len(set(ids)),'duplicate resolved state ID')
 matching=[row for row in states if row['state_id']==plan['state_id']]
 require(len(matching)==1 and matching[0]['pool_id']==pool_id,'frozen state identity changed');state=matching[0]
 for role,group,state_field in (('table','tables','immutable_direct_leg_table'),('restriction','restrictions','original_tree_restriction')):
  spec=manifest[group][pool_id]
  require(type(spec) is dict and spec['sha256']==inputs[role]['sha256'],'export '+role+' hash link changed')
  require(inside(export,spec['path']).resolve()==inside(root,inputs[role]['path']).resolve(),'export '+role+' path link changed')
  require(canonical(state[state_field])==canonical(spec),'resolved '+role+' manifest link changed')
 require(canonical(resolved_query(state,inputs))==canonical(plan['query']),'query differs from frozen resolved state')
 pools=[row for row in selection['pools'] if row['pool_id']==pool_id]
 require(len(pools)==1,'unknown or duplicate selected pool');pool=pools[0]
 require(canonical([state['mode'],state['instance_id']])==canonical([pool['mode'],pool['instance_id']]),'state/pool identity mismatch')
 trusted=prepare_real_case(plan['query'],plan['query_sha256'],inside(root,inputs['table']['path']).read_bytes(),
  inputs['table']['sha256'],inside(root,inputs['original_tree']['path']).read_bytes(),inputs['original_tree']['sha256'])
 table=trusted.table
 require(table.selection_certificate_sha256==inputs['selection']['sha256'] and table.hierarchy_sha256==inputs['original_tree']['sha256'],'table source link changed')
 chosen=pool['chosen'];selected=pool['selected_site_ids']
 require(type(chosen) is list and type(selected) is list and all(type(s) is str for s in selected),'invalid selected pool')
 chosen_ids=[row['site_id'] for row in chosen]
 require(len(chosen_ids)==len(set(chosen_ids))==len(selected)==len(set(selected))==len(table.sites) and
         set(chosen_ids)==set(selected)==set(table.sites),'selected Site universe changed')
 for row in chosen:
  site=table.sites[row['site_id']]
  require(site.anchor_id=='road:'+str(row['access_node']) and canonical(list(site.effects))==canonical(row['eligible_actions']),'selected physical anchor or capabilities changed')
 rows={}
 def visit(region,parent):
  rows[region['id']]=dict(region_id=region['id'],parent_id=parent,child_ids=[c['id'] for c in region['children']],site_ids=list(region['members']))
  for child in region['children']:visit(child,region['id'])
 visit(trusted.regions,-1)
 restriction=load(inside(root,inputs['restriction']['path']))
 expected=dict(schema='hiroute.original_tree_restriction.v1',original_sha256=inputs['original_tree']['sha256'],
  selection_certificate_sha256=inputs['selection']['sha256'],pool_id=pool_id,
  selected_site_ids=[sid for sid in load(inside(root,inputs['original_tree']['path']))['site_ids'] if sid in table.sites],
  regions=[rows[i] for i in range(len(rows))])
 require(canonical({k:restriction[k] for k in expected})==canonical(expected),'original tree restriction changed')
 require(type(plan['H_ref']) is int and type(plan['sites']) is int and type(plan['regions']) is int and
         (plan['H_ref'],plan['sites'],plan['regions'])==(trusted.physics.bound,len(table.sites),len(rows)),'plan physical population changed')
 baseline=table.pairs[(table.origin_anchor,table.destination_anchor)]
 require(baseline.reachable and decode_binary64(state['accepted_baseline_time_s'])[0]==baseline.time and
         decode_binary64(state['accepted_baseline_actual_length_m'])[0]==baseline.actual_length,'resolved baseline changed')
 def exact(value):
  require(type(value) in (str,int),'exact resolved scalar required');return Fraction(value)
 require(exact(state['initial_soc'])*exact(state['capacity_kwh'])==exact(state['initial_energy_kwh']),'resolved SOC/energy changed')
 if state['mode']=='energy_and_scheduled':
  q=state['schedule']
  require(decode_binary64(q['baseline_binary64'])[0]==baseline.time and exact(q['baseline_time_s'])==baseline.time and
          exact(q['window_start_s'])==Fraction(2,5)*baseline.time and exact(q['window_end_s'])==Fraction(7,10)*baseline.time,'resolved schedule arithmetic changed')
 return state

def verify_plan(root,path,expected_sha,deadline,*,require_c01=True):
 root=Path(root).resolve();require(time.monotonic()<deadline,'phase deadline before binding')
 require(pin(path)['sha256']==expected_sha,'plan SHA256 mismatch');plan=load(path)
 from .variant_scope import validate_variant
 validate_variant(plan)
 require(plan['source_commit']==source_commit(root),'source commit changed')
 require(digest(plan['source_files'])==plan['source_sha256'] and source_inventory(root)==plan['source_files'],'source closure changed')
 assert_committed_sources(root,plan['source_files'],plan['source_commit'])
 require(digest(plan['inputs'])==plan['input_sha256'],'input manifest changed')
 for spec in plan['inputs'].values():require(pin(inside(root,spec['path']))=={k:spec[k] for k in ('sha256','size_bytes')},'input bytes changed')
 require(digest(plan['query'])==plan['query_sha256'],'query digest changed')
 verify_export_chain(root,plan)
 if 'reference' in plan['inputs']:
  ref=load(inside(root,plan['inputs']['reference']['path']))
  require(ref['state_id']==plan['state_id'] and ref['pool_id']==plan['pool_id'] and ref['table_sha256']==plan['inputs']['table']['sha256'],'reference context changed')
  model_equal(ref['query'],plan['query'])
  expected_reference=dict(status='historical_result_available',expected_key=result_key(ref['result']),raw_certificates_replayed=False)
 else:expected_reference=dict(status='historical_reference_missing',raw_certificates_replayed=False)
 require(canonical(plan['reference'])==canonical(expected_reference),'reference comparison binding changed')
 require(plan['representation']=='exact-adjacent-cut-coalescing-v1','representation changed')
 require(plan['external_incumbent'] is None and plan['numerical_suffix_optimization'] is False and plan['literal_G8_closed'] is False,'unsupported execution scope')
 if require_c01:
  require((plan['state_id'],plan['pool_id'],plan['H_ref'],plan['sites'],plan['regions'])==('C01','OD00_energy_only',4,8,2047),'fixed C01 population changed')
  fixed={'export_manifest':'f846eb37219a34dea74aa9a79e7673b8cdae03ae281de189cb9b602a98ac380d',
         'selection':'0e39ad906c01e05b4a4b764b3270360e309c24d1ae67d7a2e3533b6dca8af06a',
         'original_tree':'4c9cd924c9066630f961302ff249de8e6260ed553f8044f1d2fafe8632127805'}
  require(all(plan['inputs'][k]['sha256']==v for k,v in fixed.items()),'fixed C01 source anchor changed')
 from .runtime import CAPTURE,REPLAY
 require(canonical(plan['profiles'])==canonical({p.name:asdict(p) for p in (CAPTURE,REPLAY)}),'runtime profiles changed')
 require(time.monotonic()<deadline,'phase deadline after binding');return plan

def main():
 p=argparse.ArgumentParser();p.add_argument('--export-dir',required=True);p.add_argument('--manifest-sha',required=True)
 p.add_argument('--selection',required=True);p.add_argument('--selection-sha',required=True);p.add_argument('--tree',required=True)
 p.add_argument('--reference');p.add_argument('--dominance',choices=('on','off'),default='on');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 value=prepare_plan(ROOT,a.export_dir,a.manifest_sha,a.selection,a.selection_sha,a.tree,reference=a.reference,dominance=a.dominance=='on')
 require((value['H_ref'],value['sites'],value['regions'])==(4,8,2047),'fixed C01 population changed')
 with a.output.open('xb') as f:f.write(canonical(value)+b'\n')
 print(json.dumps(dict(plan=str(a.output),**pin(a.output),reference_status=value['reference']['status'],execution_started=False)))
if __name__=='__main__':main()
