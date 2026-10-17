"""Run one source selection in an isolated interpreter; tiny fixtures only."""
import sys,json,tempfile,time,statistics
from pathlib import Path
from fractions import Fraction as R
ROOT=Path(__file__).resolve().parent
mode=sys.argv[1]
SRC=ROOT/'src' if mode!='original' else ROOT.parent/'sparse_feasible_handoff_work/src'
sys.path[:0]=[str(SRC),str(ROOT.parent/'sparse_feasible_handoff_work'),str(ROOT.parent/'optimized_od06_phase2/runner')]
from timecut5.bounded import _solve_problem
from timecut5.hierarchy import _solve_hierarchical_problem,build_regions
from timecut5.real_adapter import TableFreeRealProblem
from timecut5.road_provider import TableFreeRegionBoundProvider
from timecut5.feasible_incumbent import canonical,sha
from fixture_source import fixture,Router
if mode=='enabled':from timecut5.exact_progress import ExactSearchProgress
results=[];durations=[];cpus=[];io=[]
with tempfile.TemporaryDirectory() as tmp:
 for repeat in range(8):
  for case in ('nonbest','charge_required','equality'):
   for method in ('flat','hier'):
    ident=f'{repeat}-{case}-{method}';q,c,_=fixture(Path(tmp)/ident,case)
    p=TableFreeRealProblem(q,c.sites,c.provider,origin_anchor=q['origin'],destination_anchor=q['destination'],site_catalog_sha256=c.site_catalog_sha256)
    root=build_regions(c.sites)
    b=TableFreeRegionBoundProvider(c.provider,c.sites,root,destination_anchor=c.destination_anchor,landmark_anchor=c.origin_anchor,site_catalog_sha256=c.site_catalog_sha256,router_factory=Router)
    order=[];advance=p.advance
    def record(pieces,site,effect):
     order.append((tuple(x.pi for x in pieces),site,effect));return advance(pieces,site,effect)
    p.advance=record;extra={}
    if mode=='enabled':
     o=ExactSearchProgress(Path(tmp)/(ident+'-progress'),query_sha256=sha(canonical(q)),domain_sha256=c.domain_sha256,source_sha256=c.provider.source_sha256,provider=c.provider)
     extra['progress_hook']=o
    start=time.monotonic_ns();cpu=time.process_time_ns()
    if method=='flat':r=_solve_problem(p,singleton_bound=b.singleton_bound,**extra)
    else:r=_solve_hierarchical_problem(p,True,root,bound_provider=b,**extra).bounded
    durations.append(time.monotonic_ns()-start);cpus.append(time.process_time_ns()-cpu)
    if mode=='enabled':io.append(dict(wall_ns=o.state['observer_io_wall_ns'],cpu_ns=o.state['observer_io_cpu_ns']))
    if repeat==0:results.append(dict(case=case,method=method,canonical=r.canonical(),action_order=order,source_runs=c.provider.source_run_count,selected_pairs=len(c.provider.legs)))
 errors=[]
 for method in ('flat','hier'):
  for invalid in (-1,1.0):
   error_extra={}
   if mode=='enabled':
    eo=ExactSearchProgress(Path(tmp)/f'error-{method}-{invalid}',query_sha256=sha(canonical(q)),domain_sha256=c.domain_sha256,source_sha256=c.provider.source_sha256,provider=c.provider)
    error_extra['progress_hook']=eo
   try:
    if method=='flat':_solve_problem(p,verified_primary_upper=invalid,**error_extra)
    else:_solve_hierarchical_problem(p,True,root,verified_primary_upper=invalid,**error_extra)
   except Exception as e:errors.append(dict(method=method,type=type(e).__name__,message=str(e)))
print(json.dumps(dict(mode=mode,results=results,errors=errors,measurement=dict(runs=len(durations),total_wall_ns=sum(durations),total_process_cpu_ns=sum(cpus),median_wall_ns=statistics.median(durations),median_process_cpu_ns=statistics.median(cpus),observer_io=io)),default=str,sort_keys=True))
