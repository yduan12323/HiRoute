"""Capture and independently replay one pinned case; no suffix optimizer."""
from collections import Counter
import hashlib,json,os,resource,time
from pathlib import Path
from types import MappingProxyType
from .plan import canonical,digest,inside,pin,load,require,result_key

REPRESENTATION='exact-adjacent-cut-coalescing-v1'
DERIVED={'ancestry_nodes','ancestry_node_ids','trusted_case','cuts','real_input'}

def chunks(value):
 encoder=json.JSONEncoder(sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)
 for text in encoder.iterencode(value):
  for offset in range(0,len(text),65536):yield text[offset:offset+65536].encode('ascii')
 yield b'\n'

def array_document(metadata,key,rows):
 from validation.capture5.containers import canonical_chunks
 yield b'{'
 for i,name in enumerate(sorted((*metadata,key))):
  if i:yield b','
  yield canonical(name)+b':'
  if name!=key:
   yield from canonical_chunks(metadata[name]);continue
  yield b'['
  for j,row in enumerate(rows):
   if j:yield b','
   yield from canonical_chunks(row)
  yield b']'
 yield b'}\n'

def variant(plan):
 return {key:plan[key] for key in ('state_id','pool_id','H_ref','sites','regions','dominance','representation','external_incumbent')}

def input_bytes(root,plan,role):
 spec=plan['inputs'][role];path=inside(root,spec['path'])
 require(pin(path)=={k:spec[k] for k in ('sha256','size_bytes')},'input changed: '+role)
 return path.read_bytes()

def stage(writer,name,**observations):
 value=dict(schema='hiroute-recorded-stage-v1',stage=name,monotonic=time.monotonic(),pid=os.getpid(),
     kernel_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
     observational_only=True,**observations)
 writer.write('stage-'+name+'.json',chunks(value))

def comparison(plan,canonical_result):
 expected=plan['reference']
 if expected['status']=='historical_reference_missing':return dict(status='pending_missing_historical_reference',raw_certificates_replayed=False)
 actual=result_key(canonical_result['result'])
 return dict(status='matches_historical_result' if actual==expected['expected_key'] else 'historical_result_mismatch',
             expected_key=expected['expected_key'],actual_key=actual,raw_certificates_replayed=False)

def capture(plan,root,writer,plan_sha,before=lambda:None):
 from timecut5.real_legs import ImmutableLegTable,restrict_frozen_tree
 from timecut5.coalesced_solver import solve_hierarchical_real_coalesced
 from timecut5.provenance import Recorder,primitive
 from timecut5.invocation_trace import InvocationTrace
 table=ImmutableLegTable.from_bytes(input_bytes(root,plan,'table'),plan['inputs']['table']['sha256'])
 restriction=restrict_frozen_tree(input_bytes(root,plan,'original_tree'),plan['inputs']['original_tree']['sha256'],list(table.sites))
 require((len(table.sites),len(restriction.regions))==(plan['sites'],plan['regions']),'physical population differs from plan')
 before();stage(writer,'before-search')
 with Recorder() as recorder,InvocationTrace(recorder,representation=REPRESENTATION) as trace:
  result=solve_hierarchical_real_coalesced(plan['query'],table,restriction,dominance=plan['dominance'],record_lineage=True)
 storage=dict(nodes=len(recorder.nodes),batches=len(recorder.batches),events=len(trace.events),callbacks=len(recorder.witness_requests),
     encoded_bytes=dict(nodes=sum(len(x.payload) for x in recorder.nodes.values()),batches=sum(map(len,recorder.batches)),
                        events=sum(map(len,trace.events)),callbacks=sum(map(len,recorder.witness_requests))),
     registered_parent_slots=sum(len(x.parents) for x in recorder.nodes.values()))
 before();stage(writer,'after-search',storage=storage)
 wire,bundle=trace.export(),recorder.export();bundle['roots']=wire['events'][-1]['payload']['terminal_families']
 payload=dict(schema='hiroute-recorded-real-capture-v1',source_plan_sha256=plan_sha,
     source_sha256=plan['source_sha256'],input_sha256=plan['input_sha256'],query_sha256=plan['query_sha256'],
     variant=variant(plan),query=plan['query'],canonical=primitive(result.inner.canonical()),
     bundle=bundle,trace=wire,callback_requests=recorder.export_witness_requests(),suffix_optimizer_calls=0)
 before();stage(writer,'before-publication',storage=storage)
 commitment=writer.write('capture.json',chunks(payload));before()
 relation=comparison(plan,payload['canonical']) # Only after unseeded search and publication.
 summary=dict(schema='hiroute-recorded-capture-summary-v1',capture=commitment,variant=variant(plan),
     source_plan_sha256=plan_sha,source_sha256=plan['source_sha256'],input_sha256=plan['input_sha256'],
     storage=storage,canonical=payload['canonical'],reference_comparison=relation,
     independent_replay_completed=False,literal_G8_closed=False,suffix_optimizer_calls=0)
 writer.write('capture-summary.json',chunks(summary));stage(writer,'after-publication')
 require(relation['status']!='historical_result_mismatch','unseeded capture differs from historical result')
 return summary

def trusted_case(plan,root):
 from validation.real5_v2 import prepare_real_case
 return prepare_real_case(plan['query'],plan['query_sha256'],input_bytes(root,plan,'table'),plan['inputs']['table']['sha256'],
                          input_bytes(root,plan,'original_tree'),plan['inputs']['original_tree']['sha256'])

def receipt_rows(checked,requests,before):
 from validation.family5.checker import check_witness,check_receipt
 from validation.capture5.containers import stream_digest
 # The whole immutable CheckedBundle already passed the real physical-phase gate.
 for i,request in enumerate(requests):
  before();receipt=check_witness(checked.bundle,request['node_id'],request['witness'],request['contract'])
  check_receipt(checked.bundle,request['node_id'],request['witness'],request['contract'],receipt)
  yield dict(index=i,request_sha256=stream_digest(request),receipt=receipt)

def thin_queries(checked,before):
 for query in checked.queries:
  before();yield {key:value for key,value in query.items() if key not in DERIVED}

def _expand_query(row,checked):
 """Deterministically restore one exact query from the verified shared registry."""
 from validation.capture5.containers import detach_json,stream_digest
 from validation.trace5.checker import CheckedTrace
 require(type(checked) is CheckedTrace and checked.summary['verified'] is True,'checked trace required')
 nodes=checked.bundle._data['nodes'];roots=row['family_ids'];reachable=set()
 def visit(ident):
  require(ident in nodes,'missing query ancestor')
  if ident in reachable:return
  reachable.add(ident)
  for parent in nodes[ident]['parents']:visit(parent)
 for ident in roots:visit(ident)
 ancestry={ident:nodes[ident] for ident in sorted(reachable)}
 require(stream_digest(dict(schema='family5-transitive-ancestry-v1',roots=roots,nodes=ancestry))==row['ancestry_bundle_sha256'],'query closure commitment mismatch')
 value=dict(row,ancestry_nodes=ancestry,ancestry_node_ids=sorted(reachable),trusted_case=checked.bundle._physics.case,
            cuts=[dict(family_id=ident,cut=nodes[ident]['output']) for ident in roots],real_input=checked.summary['real_input'])
 return detach_json(value)

class QueryExpander:
 """Validate occurrence identity once; retain O(1) lookup without full expansion."""
 def __init__(self,checked):
  from validation.trace5.checker import CheckedTrace
  from validation.capture5.containers import stream_digest
  require(type(checked) is CheckedTrace and checked.summary['verified'] is True,'checked trace required')
  self.checked=checked;identities={}
  for query in checked.queries:
   seq=query['query_seq'];require(type(seq) is int and seq>=0 and seq not in identities,'duplicate/invalid query occurrence')
   thin={key:value for key,value in query.items() if key not in DERIVED}
   identities[seq]=stream_digest(thin)
  self.identities=MappingProxyType(identities)
 def expand(self,row):
  from validation.capture5.containers import stream_digest
  require(type(row) is dict and not DERIVED.intersection(row),'unexpected derived query fields')
  seq=row.get('query_seq');require(type(seq) is int and seq in self.identities,'unknown query occurrence')
  require(stream_digest(row)==self.identities[seq],'query occurrence differs from checked trace')
  return _expand_query(row,self.checked)


def expand_query(row,checked):
 """Convenience for one query; use QueryExpander once for a whole population."""
 return QueryExpander(checked).expand(row)

def replay(plan,root,writer,plan_sha,capture_path,expected_capture_sha,before=lambda:None,*,on_checked_trace=None):
 from validation.real5_v2.shared_replay import verify_coalesced_trace
 from validation.family5.checker import wire_equal,_plain
 from validation.capture5.containers import stream_digest
 before();require(pin(capture_path)['sha256']==expected_capture_sha,'capture byte commitment changed')
 stage(writer,'before-decode',input_bytes=Path(capture_path).stat().st_size)
 payload=load(capture_path);stage(writer,'after-decode')
 require(payload['schema']=='hiroute-recorded-real-capture-v1','unsupported capture schema')
 for key in ('source_sha256','input_sha256','query_sha256'):
  require(payload[key]==plan[key],'capture context changed: '+key)
 require(payload['source_plan_sha256']==plan_sha and wire_equal(payload['variant'],variant(plan)) and
         wire_equal(payload['query'],plan['query']) and type(payload['suffix_optimizer_calls']) is int and payload['suffix_optimizer_calls']==0,'capture scope mismatch')
 trusted=trusted_case(plan,root);before()
 checked=verify_coalesced_trace(payload['trace'],payload['bundle'],trusted)
 require(wire_equal(payload['canonical'],_plain(checked.summary['canonical'])),'outer canonical result differs from checked trace')
 if on_checked_trace is not None:
  require(callable(on_checked_trace),'checked trace callback required')
  before();on_checked_trace(checked);before()
 before();stage(writer,'after-trace',events=checked.summary['events'],queries=len(checked.queries))
 receipt=writer.write('callback-receipts.json',array_document({},'receipts',receipt_rows(checked,payload['callback_requests'],before)))
 before();stage(writer,'after-callbacks',callbacks=len(payload['callback_requests']))
 index_metadata=dict(schema='hiroute-recorded-query-index-v1',capture_sha256=expected_capture_sha,
     source_plan_sha256=plan_sha,bundle_sha256=checked.summary['bundle_sha256'],trace_sha256=checked.summary['trace_sha256'],
     query_freeze_sha256=checked.summary['query_freeze_sha256'],case_sha256=checked.summary['case_sha256'],
     derived_fields=sorted(DERIVED),reconstruction='QueryExpander.expand with independently verified capture registry',
     exact_queries=len(checked.queries),empty_action_queries=len(checked.empty_action_queries),
     empty_action_sha256=stream_digest(checked.empty_action_queries),real_input=_plain(checked.summary['real_input']))
 index=writer.write('query-index.json',array_document(index_metadata,'queries',thin_queries(checked,before)))
 before();stage(writer,'after-query-index',queries=len(checked.queries))
 kinds=Counter(event['kind'] for event in payload['trace']['events'])
 relation=comparison(plan,payload['canonical'])
 summary=dict(schema='hiroute-recorded-structural-summary-v1',source_plan_sha256=plan_sha,
     source_sha256=plan['source_sha256'],input_sha256=plan['input_sha256'],variant=variant(plan),
     capture_sha256=expected_capture_sha,checked=_plain(checked.summary),event_kinds=dict(sorted(kinds.items())),
     callbacks_checked=len(payload['callback_requests']),callback_receipts=receipt,query_index=index,
     callback_scope='all supplied producer-observed requests; required candidate and terminal witnesses are checked by complete trace grammar',
     reference_comparison=relation,structural_verified=True,literal_G8_closed=False,suffix_optimizer_calls=0)
 writer.write('structural-summary.json',chunks(summary));before()
 require(relation['status']!='historical_result_mismatch','checked result differs from historical reference')
 return summary
