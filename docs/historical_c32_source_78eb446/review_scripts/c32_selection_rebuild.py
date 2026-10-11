"""Read-only independent reconstruction of Stage C32 deterministic site selection."""
from pathlib import Path
import hashlib,json,math,resource,signal,struct,time
import pyarrow as pa
import pyarrow.parquet as pq
pa.set_cpu_count(1)
pa.set_io_thread_count(1)
BASE=Path('/home/dy/HiRoute/project')
OUT=Path('/home/dy/HiRoute/c32_selection_review_20261011')
OUT.mkdir(exist_ok=True)
def sha(p):
 d=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(8<<20):d.update(b)
 return d.hexdigest()
def limit(*_):raise TimeoutError('180-second selection review cap')
signal.signal(signal.SIGALRM,limit);signal.alarm(180);resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
start=time.monotonic();manifest_path=BASE/'results/milestone_5_real_export/selection_manifest.json';m=json.loads(manifest_path.read_text());src=[]
for x in m['sources']:
 p=BASE/x['repository_target_path'];h=sha(p);assert p.stat().st_size==x['size_bytes'] and h==x['sha256'];src.append({'name':x['name'],'sha256':h})
od=pq.read_table(BASE/'results/milestone_3a/od_remapping.parquet',columns=['instance_id','destination_node'],use_threads=False).to_pylist();dest={x['instance_id']:x['destination_node'] for x in od};assert all(i in dest for i in range(8))
static=pq.read_table(BASE/'results/milestone_4r/stop_sites.parquet',columns=['site_id','attachment_status','transport_capabilities','meal_count','support_radius_m','access_node','osm_type','osm_id'],use_threads=False).to_pylist()
static=[x for x in static if x['attachment_status']=='attached'];assert len(static)==60498
features={i:{} for i in range(8)};dupes=0;missing_progress=0
pf=pq.ParquetFile(BASE/'results/milestone_4a/od_features.parquet')
for batch in pf.iter_batches(batch_size=32768,columns=['instance_id','osm_type','osm_id','progress'],use_threads=False):
 for x in batch.to_pylist():
  i=x['instance_id']
  if i not in features:continue
  key=(x['osm_type'],x['osm_id']);v=x['progress'];bits=None if v is None else struct.pack('!d',v)
  old=features[i].get(key,'ABSENT')
  if old!='ABSENT':
   dupes+=1
   if old!=bits:raise ValueError('contradictory accepted progress row')
  else:features[i][key]=bits
pools={x['pool_id']:x for x in m['pools']};rows=[];errors=[]
for i in range(8):
 for mode in ('energy_only','energy_and_scheduled'):
  pid=f'OD{i:02}_{mode}';original=pools[pid];pool=[]
  for x in static:
   if x['access_node']==dest[i]:continue
   C='charge' in x['transport_capabilities']
   S=x['meal_count']>=1 and x['support_radius_m']==500
   actions=['C'] if C else []
   if mode=='energy_and_scheduled':
    if S:actions.append('S')
    if C and S:actions.append('CS')
   if not actions:continue
   bits=features[i].get((x['osm_type'],x['osm_id']))
   value=struct.unpack('!d',bits)[0] if bits is not None else None
   if value is not None and not math.isfinite(value):value=None
   pool.append((x['site_id'],'/'.join(actions),value))
  pool.sort(key=lambda r:(r[2] is None,0 if r[2] is None else r[2],r[0]))
  reps={}
  for rank,(site,signature,progress) in enumerate(pool):reps.setdefault(signature,(rank,site))
  selected={x[1] for x in reps.values()}
  for site,signature,progress in pool:
   if len(selected)>=8:break
   selected.add(site)
  chosen=[(rank,site,signature) for rank,(site,signature,progress) in enumerate(pool) if site in selected]
  expected=[(x['rank'],x['site_id'],x['class_signature']) for x in original['chosen']]
  signature_counts={sig:sum(item[1]==sig for item in pool) for sig in reps}
  saved_reps={x['class_signature']:(x['representative_rank'],x['representative_site_id'],x['class_member_count']) for x in original['class_representatives']}
  rep_match={sig:(rank,site,signature_counts[sig]) for sig,(rank,site) in reps.items()}==saved_reps
  selected_values_match=True
  for entry in original['chosen']:
   rank=entry['rank'];site,sig,progress=pool[rank]
   bits=None if progress is None else struct.pack('!d',progress).hex()
   reason=('earliest_ranked_representative_of_eligible_action_signature' if reps[sig][1]==site else 'fill8_in_full_pool_order_after_class_representatives')
   selected_values_match &= (entry['site_id']==site and entry['progress_missing']==(progress is None) and entry['progress_float64_bits_hex']==bits and entry['selection_reason']==reason)
  match=len(pool)==original['full_ordered_pool_count'] and chosen==expected and [x[1] for x in chosen]==original['selected_site_ids'] and rep_match and selected_values_match
  if not match:errors.append({'pool_id':pid,'computed_count':len(pool),'stored_count':original['full_ordered_pool_count'],'computed_selected':chosen,'stored_selected':expected})
  rows.append({'pool_id':pid,'count':len(pool),'selected':chosen,'representatives':reps,'match':match})
assert not errors,errors[:2]
state_ids=[f'C{i:02}' for i in range(1,33)];states=json.loads((BASE/'results/milestone_5_real_export/query_states_resolved.json').read_text());actual=[(x['state_id'],x['instance_id'],x['initial_soc'],x['mode']) for x in states];expected=[(state_ids[k],i,s,mode) for k,(i,s,mode) in enumerate((i,s,mode) for i in range(8) for s in ('3/10','19/25') for mode in ('energy_only','energy_and_scheduled'))]
assert actual==expected
out={'schema':'c32-independent-deterministic-selection-rebuild-v1','status':'passed','selection_manifest_sha256':sha(manifest_path),'source_hashes':src,'static_attached_count':len(static),'progress_duplicate_agreeing_rows':dupes,'pools':rows,'pool_count':len(rows),'states_match':True,'elapsed_seconds':time.monotonic()-start,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'method':'Stage C v2.1 rule reconstructed from six unchanged base inputs; no original intermediate pool/query-state file assumed'}
with (OUT/'selection_rebuild_result.json').open('x') as f:json.dump(out,f,indent=2,sort_keys=True);f.write('\n')
print(json.dumps({k:out[k] for k in ['status','pool_count','states_match','elapsed_seconds','peak_rss_kib','progress_duplicate_agreeing_rows']},sort_keys=True))
