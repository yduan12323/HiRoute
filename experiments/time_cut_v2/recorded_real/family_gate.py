"""Shared genuine real-family gate used by bounded numerical preparations."""
from unittest.mock import patch
from . import plan as binding

def verify_families(bundle,trusted,pool):
 from validation.real5_v2 import family
 from validation.family5.independent_oracle_v3 import MemoizedOracle
 from validation.family5.checker import VerificationError
 binding.require(pool.kernel=='interval-join-v1','reviewed endpoint-join family kernel required')
 native=family._verify_bundle;memo=MemoizedOracle();calls=0
 def delegated(*a,**kw):
  nonlocal calls
  binding.require(calls==0 and 'batch_executor' not in kw,'unexpected family invocation');calls+=1
  return native(*a,**kw,batch_executor=pool)
 def exact(a,b,reason):
  try:return memo.exact_family_equal(a,b)
  except AssertionError as error:raise VerificationError(f'{reason}: {error}') from error
 with patch.object(family,'oracle',memo),patch.object(family,'_exact',exact),patch.object(family,'_verify_bundle',delegated):
  checked=family.verify_bundle(bundle,trusted)
 ledger=pool.snapshot();binding.require(calls==1 and ledger['complete'] is True,'incomplete family batch join')
 return checked,ledger
