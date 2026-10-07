"""Renew only checker source pins while retaining an authenticated capture plan."""
import argparse,copy,time
from pathlib import Path
from . import plan as binding
from .hot_jobs import read_pinned

SOURCE_FIELDS=frozenset(('source_commit','source_files','source_sha256'))
MAX_PLAN_BYTES=4*1024**2

def historical_plan(root,path,expected_sha):
 value=read_pinned(path,expected_sha,MAX_PLAN_BYTES)
 binding.require(type(value) is dict and value.get('schema')=='hiroute-recorded-real-plan-v1','historical plan schema')
 binding.require(binding.digest(value['source_files'])==value['source_sha256'],'historical source inventory changed')
 binding.assert_committed_sources(root,value['source_files'],value['source_commit'])
 binding.require(binding.digest(value['inputs'])==value['input_sha256'] and
  binding.digest(value['query'])==value['query_sha256'],'historical physical digest changed')
 for spec in value['inputs'].values():
  binding.require(binding.pin(binding.inside(root,spec['path']))=={k:spec[k] for k in ('sha256','size_bytes')},'historical input changed')
 binding.verify_export_chain(root,value)
 return value

def same_capture_scope(original,current):
 binding.require(binding.canonical({k:v for k,v in original.items() if k not in SOURCE_FIELDS})==
  binding.canonical({k:v for k,v in current.items() if k not in SOURCE_FIELDS}),
  'source renewal changed capture scope or reference')

def renew(root,path,expected_sha):
 original=historical_plan(root,path,expected_sha);current=copy.deepcopy(original)
 sources=binding.source_inventory(root);commit=binding.source_commit(root)
 binding.assert_committed_sources(root,sources,commit)
 current.update(source_commit=commit,source_files=sources,source_sha256=binding.digest(sources))
 same_capture_scope(original,current)
 return current

def verify(root,current_path,current_sha,original_path,original_sha,deadline,*,require_c01=True):
 binding.require(time.monotonic()<deadline,'renewal deadline')
 current=binding.verify_plan(root,current_path,current_sha,deadline,require_c01=require_c01)
 binding.require(binding.canonical(current)==binding.canonical(read_pinned(current_path,current_sha,MAX_PLAN_BYTES)),
  'consumed current plan changed')
 original=historical_plan(root,original_path,original_sha);same_capture_scope(original,current)
 binding.require(time.monotonic()<deadline,'renewal deadline')
 return original,current

def main():
 p=argparse.ArgumentParser();p.add_argument('--historical-plan',type=Path,required=True)
 p.add_argument('--historical-plan-sha',required=True);p.add_argument('--output',type=Path,required=True)
 a=p.parse_args();value=renew(binding.ROOT,a.historical_plan,a.historical_plan_sha)
 with a.output.open('xb') as f:f.write(binding.canonical(value)+b'\n')
 print(binding.canonical(dict(plan=str(a.output),**binding.pin(a.output),execution_started=False)).decode())
if __name__=='__main__':main()
