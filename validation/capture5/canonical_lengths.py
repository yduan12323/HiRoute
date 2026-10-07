"""Exact canonical byte lengths over an already-owned immutable JSON DAG."""
import json
from types import MappingProxyType

SCALAR_ENTRIES=100000

def query_lengths(queries):
 if type(queries) is not tuple:raise ValueError('owned immutable query tuple required')
 containers={};scalars={};active=set()
 def scalar(value):
  kind=type(value)
  if kind not in (str,int,bool,float,type(None)):raise ValueError('non-JSON scalar')
  # Do not equate +0.0 and -0.0, which have different canonical lengths.
  key=None if kind is float else (kind,value)
  if key is not None and key in scalars:return scalars[key]
  result=len(json.dumps(value,ensure_ascii=True,allow_nan=False,separators=(',',':')).encode('ascii'))
  if key is not None and len(scalars)<SCALAR_ENTRIES:scalars[key]=result
  return result
 def size(value):
  kind=type(value)
  if kind not in (MappingProxyType,tuple):return scalar(value)
  ident=id(value)
  if ident in active:raise ValueError('cyclic immutable JSON')
  if ident in containers:return containers[ident]
  active.add(ident)
  if kind is MappingProxyType:
   if any(type(k) is not str for k in value):raise ValueError('non-string JSON key')
   result=2+max(0,len(value)-1)+sum(scalar(k)+1+size(v) for k,v in value.items())
  else:result=2+max(0,len(value)-1)+sum(size(v) for v in value)
  active.remove(ident);containers[ident]=result;return result
 lengths=[];prefix=[1]
 for i,query in enumerate(queries):
  value=size(query);lengths.append(value);prefix.append(prefix[-1]+value+int(i>0))
 return dict(query_bytes=tuple(lengths),prefix_bytes=tuple(prefix),total_bytes=prefix[-1]+1,
  largest_query_bytes=max(lengths,default=0),unique_containers=len(containers),scalar_cache_entries=len(scalars))
