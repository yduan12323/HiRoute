"""One construction or independent representation-only check; no source search."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from external_packed_graph import build,validate
from preflight_real_road_certificate import validate_domain
from streaming_road_graph import sha,flush_file,ResourceStop


def save(path,value):
    path=Path(path);tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,indent=2)+'\n');flush_file(tmp);tmp.replace(path)


def main():
    a=argparse.ArgumentParser();a.add_argument('--mode',choices=('build','validate'),required=True)
    a.add_argument('--config',required=True);a.add_argument('--frozen-domain',required=True)
    a.add_argument('--source-db',required=True);a.add_argument('--packed',required=True);a.add_argument('--output',required=True)
    a=a.parse_args();start=time.process_time();wall=time.monotonic();out=Path(a.output);out.mkdir(exist_ok=False)
    state=dict(mode=a.mode,decision='STARTED_UNCERTIFIED',source_search=False,EV_solve=False,holdout=False,
        real_source_status_counts={'UNKNOWN':1,'UNRUN':64,'independently_certified':0},pair_denominator=4225)
    save(out/'started.json',dict(state,started_at=time.time()))
    try:
        config=json.loads(Path(a.config).read_text());frozen=json.loads(Path(a.frozen_domain).read_text())
        if sha(a.frozen_domain)!=config['frozen_domain_sha256']:raise ValueError('frozen full query bytes changed')
        S,T=validate_domain(frozen)
        if (len(S),len(T),config['nodes'],config['edges'],config['sources'],config['targets'],config['pairs'])!=(65,65,2986695,5900232,65,65,4225):raise ValueError('complete admitted shape changed')
        if any(config[k] is not False for k in ('source_search','EV_solve','holdout')):raise ValueError('unadmitted work requested')
        if frozen['candidate_domain_sha256']!=config['candidate_domain_sha256'] or frozen['expected_input_sha256']['graph']!=config['raw_sha256']:raise ValueError('original candidate/raw provenance mismatch')
        for name in ('config','preflight'):
            if sha(frozen[name+'_path'])!=frozen[name+'_sha256']:raise ValueError('original configuration changed')
        for name,path in frozen['input_paths'].items():
            if name!='graph' and sha(path)!=frozen['expected_input_sha256'][name]:raise ValueError('physical input changed')
        state['source_commit']=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
        state['source_dirty']=bool(subprocess.check_output(['git','status','--porcelain'],text=True).strip())
        state['config_sha256']=sha(a.config);state['frozen_domain_sha256']=sha(a.frozen_domain)
        save(out/'started.json',dict(state,started_at=time.time()))
        progress=lambda v:save(out/'progress.json',dict(v,CPU_s=time.process_time()-start,wall_s=time.monotonic()-wall))
        if a.mode=='build':
            result=build(a.source_db,Path(a.packed).parent,expected_db_sha=config['source_DB_sha256'],
                expected_identity=config['graph_identity'],expected_N=config['nodes'],expected_E=config['edges'],
                max_db_bytes=config['SQLite_file_bytes_cap'],max_packed_bytes=config['packed_bytes_cap'],progress=progress)
        else:
            result=validate(frozen['input_paths']['graph'],a.packed,out/'independent',expected_raw_sha=config['raw_sha256'],
                expected_N=config['nodes'],expected_E=config['edges'],anchors=set(S)|set(T),max_db_bytes=config['SQLite_file_bytes_cap'],progress=progress)
        state.update(result);state['whole_road_table_certified']=False
    except BaseException as exc:
        state.update(decision='RESOURCE_STOP_UNCERTIFIED' if isinstance(exc,ResourceStop) else 'ERROR_UNCERTIFIED',error=repr(exc));raise
    finally:
        state.update(body_CPU_s=time.process_time()-start,body_wall_s=time.monotonic()-wall)
        save(out/'results.json',state);print(json.dumps(state,sort_keys=True))


if __name__=='__main__':main()
