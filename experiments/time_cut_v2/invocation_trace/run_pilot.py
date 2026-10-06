"""Frozen tiny-HIER trace pilot; no numerical suffix oracle."""
import argparse,hashlib,json,resource,time
from pathlib import Path
from timecut5.hierarchy import solve_hierarchical
from timecut5.invocation_trace import InvocationTrace
from timecut5.provenance import Recorder,primitive


def main():
    p=argparse.ArgumentParser();p.add_argument('--case',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    case=json.loads(a.case.read_text());a.output.mkdir(parents=True,exist_ok=True)
    for dominance in (False,True):
        baseline=solve_hierarchical(case,dominance=dominance)
        start=time.perf_counter()
        with Recorder() as recorder,InvocationTrace(recorder) as trace:
            result=solve_hierarchical(case,dominance=dominance)
        if result.canonical()!=baseline.canonical():raise ValueError('Trace changes canonical solver answer')
        events=trace.export();bundle=recorder.export()
        bundle['roots']=events['events'][-1]['payload']['terminal_families']
        value=dict(case=case,trace=events,bundle=bundle,callback_requests=recorder.export_witness_requests(),
                   canonical=primitive(result.canonical()),source_case_sha256=hashlib.sha256(a.case.read_bytes()).hexdigest(),
                   output_equivalence=True,elapsed_s=time.perf_counter()-start,
                   peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                   numeric_suffix_optimization_run=False)
        path=a.output/('D1.json' if dominance else 'D0.json');path.write_text(json.dumps(value,sort_keys=True,indent=2)+'\n')
        print(json.dumps(dict(path=str(path),events=len(events['events']),families=len(bundle['nodes']),
                             batches=len(bundle['batches']),callbacks=len(value['callback_requests']),
                             canonical=value['canonical'])),flush=True)

if __name__=='__main__':main()
