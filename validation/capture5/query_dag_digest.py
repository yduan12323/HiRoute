"""The legacy flat query hash, encoded from an owned immutable shared DAG.

This is a serialization optimization only. It never establishes family validity.
The unchanged containers.query_digest remains the byte-level reference.
"""
import hashlib,sys
from types import MappingProxyType
from .containers import canonical_chunks,freeze_shared

CACHE_BYTES=512*1024**2
ENTRY_BYTES=4*1024**2
KEY_BYTES=32*1024**2
CHUNK_BYTES=65536

class QueryDagEncoder:
 def __init__(self,queries,*,cache_bytes=CACHE_BYTES,entry_bytes=ENTRY_BYTES,key_bytes=KEY_BYTES):
  if type(queries) not in (list,tuple):raise ValueError('completed query sequence required')
  for value,limit in ((cache_bytes,CACHE_BYTES),(entry_bytes,ENTRY_BYTES),(key_bytes,KEY_BYTES)):
   if type(value) is not int or not 0<=value<=limit:raise ValueError('canonical cache limit')
  self._queries=freeze_shared(queries) # Copy external mappings; no borrowed mutable cache keys.
  self.cache_bytes=cache_bytes;self.entry_bytes=entry_bytes;self.key_bytes=key_bytes
  self.cache={};self.keys={};self.reserved_bytes=0;self.reserved_key_bytes=0
  self.stats=dict(cache_bytes=0,key_tuple_bytes=0,cache_hits=0,cache_misses=0,cache_entries=0,
   oversized_entries=0,budget_skips=0,ancestry_occurrences=0,distinct_ancestries=0,
   query_count=len(self.queries),queries_started=0,queries_completed=0,
   emitted_bytes=0,emitted_chunks=0,encoded_chunks=0,encoded_bytes=0,cached_bytes_emitted=0)
 @property
 def queries(self):return self._queries
 def snapshot(self):
  return dict(self.stats,cache_bytes=sum(map(len,self.cache.values())),cache_entries=len(self.cache),
   key_tuple_bytes=sum(map(sys.getsizeof,self.keys.values())),reserved_cache_bytes=self.reserved_bytes,
   reserved_key_tuple_bytes=self.reserved_key_bytes,logical_query_bytes=self.stats['emitted_bytes'])
 def encoded(self,value):
  for chunk in canonical_chunks(value):
   self.stats['encoded_chunks']+=1;self.stats['encoded_bytes']+=len(chunk)
   yield chunk
 def cached(self,value):
  key=id(value)
  if key in self.cache:
   self.stats['cache_hits']+=1;raw=self.cache[key]
   for offset in range(0,len(raw),CHUNK_BYTES):
    chunk=raw[offset:offset+CHUNK_BYTES];self.stats['cached_bytes_emitted']+=len(chunk);yield chunk
   return
  self.stats['cache_misses']+=1
  room=min(self.entry_bytes,self.cache_bytes-self.reserved_bytes);parts=[];size=0;admit=room>0
  for chunk in self.encoded(value):
   if admit:
    size+=len(chunk)
    if size<=room:parts.append(chunk)
    else:
     parts.clear();admit=False
     self.stats['oversized_entries' if size>self.entry_bytes else 'budget_skips']+=1
   yield chunk
  if admit and key not in self.cache:
   raw=b''.join(parts)
   # Yielding a stream permits interleaved consumption; recheck current admission.
   if self.reserved_bytes+len(raw)<=self.cache_bytes:
    # Reserve first: interruption may waste budget, but cannot admit uncharged bytes.
    self.reserved_bytes+=len(raw);self.cache[key]=raw
   else:self.stats['budget_skips']+=1
  elif room==0:self.stats['budget_skips']+=1
 def ordered_keys(self,value):
  key=id(value)
  if key in self.keys:return self.keys[key]
  keys=tuple(sorted(value));size=sys.getsizeof(keys)
  if self.reserved_key_bytes+size<=self.key_bytes:
   self.reserved_key_bytes+=size;self.keys[key]=keys
  return keys
 def ancestry(self,value):
  self.stats['ancestry_occurrences']+=1
  yield b'{'
  for i,key in enumerate(self.ordered_keys(value)):
   if i:yield b','
   yield from self.encoded(key);yield b':'
   yield from self.cached(value[key])
  yield b'}'
 def query(self,value):
  if type(value) is not MappingProxyType:
   yield from self.encoded(value);return
  yield b'{'
  for i,key in enumerate(sorted(value)):
   if i:yield b','
   yield from self.encoded(key);yield b':'
   if key=='ancestry_nodes' and type(value[key]) is MappingProxyType:yield from self.ancestry(value[key])
   elif key in ('ancestry_node_ids','trusted_case'):yield from self.cached(value[key])
   else:yield from self.encoded(value[key])
  yield b'}'
 def chunks(self):
  seen=set()
  def body():
   yield b'['
   for i,query in enumerate(self.queries):
    if i:yield b','
    self.stats['queries_started']+=1
    if type(query) is MappingProxyType and type(query.get('ancestry_nodes')) is MappingProxyType:seen.add(id(query['ancestry_nodes']))
    self.stats['distinct_ancestries']=len(seen)
    yield from self.query(query)
    self.stats['queries_completed']+=1
   yield b']'
  for chunk in body():
   if len(chunk)>CHUNK_BYTES:raise ValueError('canonical chunk limit')
   self.stats['emitted_bytes']+=len(chunk);self.stats['emitted_chunks']+=1
   yield chunk
  self.stats['distinct_ancestries']=len(seen)
 def digest(self):
  h=hashlib.sha256()
  for chunk in self.chunks():h.update(chunk)
  return h.hexdigest()

def freeze_query_digest(queries,**limits):
 encoder=QueryDagEncoder(queries,**limits)
 return encoder.queries,encoder.digest(),encoder.snapshot()
