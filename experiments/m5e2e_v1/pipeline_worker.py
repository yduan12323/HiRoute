"""Supervised fresh build workers; inputs are raw/config or this build's stages."""
import argparse
import os
from pathlib import Path
from .common import load, write_new, file_hash


def main():
    p=argparse.ArgumentParser()
    p.add_argument('stage',choices=('prepare','freeze'))
    for name in ('source','config','raw-cache','run-root'):
        p.add_argument('--'+name,required=True,type=Path)
    p.add_argument('--osmium',type=Path); p.add_argument('--compiler',type=Path)
    args=p.parse_args(); out=Path(os.environ['HIROUTE_OUTPUT_DIR']); config=load(args.config)
    if args.stage=='prepare':
        if not args.osmium or not args.compiler:
            raise ValueError('Pinned osmium and compiler executable paths are required')
        from .prepare import prepare_inputs
        result=prepare_inputs(config,args.raw_cache,out/'prepared',osmium=str(args.osmium),
                              compiler=str(args.compiler),config_root=args.source)
        write_new(out/'prepared.json',result)
    else:
        from .selection import freeze_cases
        prepared=load(args.run_root/'prepare-invocation/artifacts/prepared.json')
        result=freeze_cases(prepared,out/'frozen',config,compiler=str(args.compiler) if args.compiler else None)
        write_new(out/'cases.json',load(result['cases_path']))
        write_new(out/'freeze.json',result)
    write_new(os.environ['HIROUTE_WORKER_RECEIPT'],dict(status='COMPLETED',stage=args.stage))


if __name__=='__main__':
    main()
