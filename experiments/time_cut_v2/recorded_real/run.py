"""Explicit phase launcher; reviewed plan/profile required separately."""
import time
ENTRY=time.monotonic()
import argparse,json,resource,sys
from pathlib import Path
from .plan import ROOT,verify_plan,require
from .runtime import CAPTURE,REPLAY,PlanContext,run_phase


def main():
 parser=argparse.ArgumentParser();parser.add_argument('--phase',choices=('capture','replay'),required=True)
 parser.add_argument('--plan',type=Path,required=True);parser.add_argument('--plan-sha',required=True)
 parser.add_argument('--attempt-dir',type=Path,required=True);parser.add_argument('--cpu',type=int,required=True)
 parser.add_argument('--capture-attempt',type=Path);parser.add_argument('--capture-manifest-sha');parser.add_argument('--capture-result-sha');parser.add_argument('--capture-decision-sha');parser.add_argument('--capture-return',type=Path);parser.add_argument('--capture-return-sha')
 args=parser.parse_args();profile=CAPTURE if args.phase=='capture' else REPLAY
 deadline=ENTRY+profile.wall_seconds
 soft,hard=resource.getrlimit(resource.RLIMIT_AS)
 require(hard==resource.RLIM_INFINITY or hard>=profile.child_as_bytes,'inherited hard AS limit is too small')
 resource.setrlimit(resource.RLIMIT_AS,(min(512*1024**2,soft) if soft!=resource.RLIM_INFINITY else 512*1024**2,hard))
 plan=verify_plan(ROOT,args.plan,args.plan_sha,deadline)
 argv=[sys.executable,'-B','-m','experiments.time_cut_v2.recorded_real.worker','--phase',args.phase,
       '--plan',str(args.plan.resolve()),'--plan-sha',args.plan_sha,'--deadline',repr(deadline)]
 if args.phase=='replay':
  require(args.capture_attempt is not None and args.capture_manifest_sha and args.capture_result_sha and args.capture_decision_sha and args.capture_return is not None and args.capture_return_sha,'capture commitments required')
  argv += ['--capture-attempt',str(args.capture_attempt.resolve()),'--capture-manifest-sha',args.capture_manifest_sha,'--capture-result-sha',args.capture_result_sha,'--capture-decision-sha',args.capture_decision_sha,'--capture-return',str(args.capture_return.resolve()),'--capture-return-sha',args.capture_return_sha]
 context=PlanContext(args.plan_sha,plan['source_sha256'],plan['input_sha256'],profile.name)
 result=run_phase(argv,attempt_dir=args.attempt_dir,profile=profile,cpu=args.cpu,context=context,
      entry_monotonic=float(ENTRY),deadline_monotonic=float(deadline))
 print(json.dumps(result,sort_keys=True));return 0 if result['status']=='completed' else 1
if __name__=='__main__':raise SystemExit(main())
