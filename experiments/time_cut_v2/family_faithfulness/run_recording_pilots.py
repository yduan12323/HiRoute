"""Output-equivalence/recording pilot only. No independent acceptance claim."""
import argparse, hashlib, json, time, resource
from fractions import Fraction as R
from pathlib import Path
from timecut5.bounded import solve_bounded
from timecut5.provenance import Recorder, primitive, witness_dict


def main():
    p=argparse.ArgumentParser();p.add_argument('--case-files',nargs='+',required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--probe-all-pieces',action='store_true');args=p.parse_args()
    chosen=[]
    for path in args.case_files:
        for case in json.loads(Path(path).read_text()):
            if case['case_id'].startswith(('A13_','A15_','SUP_A06_')):
                chosen.append(case)
    args.output.mkdir(parents=True,exist_ok=True);rows=[]
    for case in chosen:
        start=time.perf_counter();baseline=solve_bounded(case,True)
        baseline_seconds=time.perf_counter()-start
        start=time.perf_counter()
        probe_count=0
        with Recorder(capture_pieces=args.probe_all_pieces) as recorder:
            recorded=solve_bounded(case,True)
            for piece in tuple(recorder.recorded_pieces.values()):
                energies={(piece.domain.lo+piece.domain.hi)/2}
                if piece.domain.left_closed:energies.add(piece.domain.lo)
                if piece.domain.right_closed:energies.add(piece.domain.hi)
                for energy in sorted(energies):
                    piece.at(energy).approach(R(1,10**60));probe_count+=1
            bundle=recorder.export()
        elapsed=time.perf_counter()-start
        if baseline.canonical()!=recorded.canonical():
            raise ValueError('recording changes canonical answer: '+case['case_id'])
        bundle['roots']=[k for k,n in bundle['nodes'].items()
                         if n['output']['state'][0]==case['destination'] and n['output']['state'][1]==0]
        payload=dict(case=case,bundle=bundle,callback_requests=recorder.export_witness_requests(),canonical=primitive(recorded.canonical()),
                     witness=witness_dict(recorded.result.witness) if recorded.result.witness else None)
        path=args.output/(case['case_id']+'.json')
        path.write_text(json.dumps(payload,sort_keys=True,indent=2)+'\n')
        row=dict(case_id=case['case_id'],H_ref=case['H_ref'],dominance=True,
                 nodes=len(bundle['nodes']),batches=len(bundle['batches']),roots=len(bundle['roots']),
                 callback_requests=len(recorder.witness_requests),production_callback_probe_count=probe_count,
                 output_equivalence=True,status=recorded.result.status,
                 baseline_seconds=baseline_seconds,recording_seconds=elapsed,
                 process_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                 sha256=hashlib.sha256(path.read_bytes()).hexdigest(),bytes=path.stat().st_size)
        rows.append(row);print(json.dumps(row),flush=True)
    (args.output/'summary.json').write_text(json.dumps(rows,sort_keys=True,indent=2)+'\n')

if __name__=='__main__':main()
