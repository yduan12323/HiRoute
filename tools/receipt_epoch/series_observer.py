"""Run the independently approved saved argv exactly once; observe only."""
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time

ROOT = Path('/home/dy/HiRoute/project')


def exact_json(path, expected_sha, expected_size, limit):
    """Parse only bytes from one bounded, identity-stable, independently pinned fd."""
    path=Path(os.path.abspath(path))
    if type(expected_sha) is not str or len(expected_sha)!=64 or type(expected_size) is not int or \
       not 0 <= expected_size <= limit:
        raise ValueError('observer exact input pin required')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        first=os.fstat(fd)
        if not stat.S_ISREG(first.st_mode) or first.st_nlink!=1 or first.st_size!=expected_size:
            raise ValueError('observer input alias or size changed')
        chunks=[];count=0;digest=hashlib.sha256()
        while True:
            raw=os.read(fd,65536)
            if not raw: break
            count+=len(raw)
            if count>limit: raise ValueError('observer input byte cap')
            digest.update(raw);chunks.append(raw)
        def identity(value):
            return (value.st_dev,value.st_ino,value.st_mode,value.st_uid,value.st_nlink,
                    value.st_size,value.st_mtime_ns,value.st_ctime_ns)
        if count!=expected_size or digest.hexdigest()!=expected_sha or \
           identity(first)!=identity(os.fstat(fd)) or identity(first)!=identity(os.lstat(path)):
            raise ValueError('observer pinned input changed during read')
        def pairs(items):
            result={}
            for key,value in items:
                if key in result: raise ValueError('observer duplicate JSON key')
                result[key]=value
            return result
        return json.loads(b''.join(chunks),object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError('observer nonfinite JSON')))
    finally:
        os.close(fd)


if len(sys.argv)!=4:
    raise ValueError('observer requires independently pinned prepared path, SHA and size')
PREPARED = exact_json(sys.argv[1],sys.argv[2],int(sys.argv[3]),4*1024**2)
D = Path(PREPARED['output_dir'])
LABEL = PREPARED['label']
OBS = D/(LABEL+'.observation.001')
HEAD = '3ad6e385903b631579df059b48d9ea6037728da7'
SOURCE = '9b3f2a1b1c2a3b36533ea42e744b94e33f5929730ec7cfe11aa0f2e586caf5ad'
COMMAND_SHA = PREPARED['command']['sha256']
POLICY_SHA = '3de130328d7a488fd5551f67fae570a274b8003fa6b5fa0b92f04381559b2493'
WINDOW = PREPARED['window_id']
os.chdir(ROOT)
sys.path[:0] = [str(ROOT/'src'), str(ROOT)]
from experiments.time_cut_v2.recorded_real import suffix_census, plan as binding


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def pin(path):
    path = Path(path)
    return dict(path=str(path), **binding.pin(path))


def load(path):
    return binding.load(path)


def publish(name, value):
    with (OBS/name).open('xb') as stream:
        stream.write(binding.canonical(value)+b'\n')


def state(value):
    temporary = OBS/'state.partial'
    with temporary.open('wb') as stream:
        stream.write(binding.canonical(value)+b'\n')
    os.replace(temporary, OBS/'state.json')


def process_rows():
    rows = {}
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():
            continue
        try:
            if path.stat().st_uid != os.getuid():
                continue
            status = (path/'stat').read_text().rsplit(')', 1)[1].split()
            rows[int(path.name)] = dict(ppid=int(status[1]), pgid=int(status[2]),
                start_ticks=int(status[19]), rss_bytes=int(status[21])*os.sysconf('SC_PAGE_SIZE'),
                user_cpu_seconds=int(status[11])/os.sysconf('SC_CLK_TCK'),system_cpu_seconds=int(status[12])/os.sysconf('SC_CLK_TCK'))
        except (OSError, ValueError, IndexError):
            pass
    return rows


def active_recorded():
    result = []
    for pid in process_rows():
        try:
            argv = (Path('/proc')/str(pid)/'cmdline').read_bytes().split(b'\0')
            if b'-m' in argv and any(x.startswith(b'experiments.time_cut_v2.recorded_real.') for x in argv):
                result.append(pid)
        except OSError:
            pass
    return result


def main():
    publish('observer-entry.json', dict(utc=utc(),observer_pid=os.getpid(),
        permission='one authorized ordinary window within unique remaining D0 series; fail stop; no retry or cap increase'))
    state(dict(stage='prechecking', utc=utc(), observer_pid=os.getpid(), controller_started=False))
    command_path = D/(LABEL+'.command.json')
    policy_path = Path('/home/dy/HiRoute/project/results/milestone_5_validation/C01.D0.executor_review.3ad6e38.20261008T171537Z/source-policy.REVIEW-CANDIDATE.json')
    handoff_path = D/'preparation.json'
    binding.require(pin(command_path)['sha256'] == COMMAND_SHA and command_path.stat().st_size == PREPARED['command']['size_bytes'],
                    'approved command bytes changed')
    binding.require(pin(policy_path)['sha256'] == POLICY_SHA and policy_path.stat().st_size == 989,
                    'approved policy bytes changed')
    binding.require(pin(handoff_path)['sha256'] ==
        PREPARED['preparation']['sha256'], 'handoff changed')
    if PREPARED['command']['path']!=str(command_path) or PREPARED['preparation']['path']!=str(handoff_path):
        raise ValueError('observer prepared paths differ from fixed output layout')
    command=exact_json(command_path,PREPARED['command']['sha256'],PREPARED['command']['size_bytes'],4*1024**2)
    handoff=exact_json(handoff_path,PREPARED['preparation']['sha256'],PREPARED['preparation']['size_bytes'],4*1024**2)
    sources = suffix_census.check_sources(ROOT, HEAD, SOURCE)
    binding.require(len(sources) == 119, 'source inventory count changed')
    binding.require(not subprocess.check_output(['git','diff','--name-only'],text=True).strip() and
                    not subprocess.check_output(['git','diff','--cached','--name-only'],text=True).strip(),
                    'tracked checkout not clean')
    historical = []
    checked = set()
    def verify(path, expected, size=None):
        path = Path(path); actual = pin(path)
        binding.require(actual['sha256'] == expected and
                        (size is None or actual['size_bytes'] == size), 'historical pin changed: '+str(path))
        if str(path) not in checked:
            historical.append(actual); checked.add(str(path))
    for row in handoff['historical_and_policy_pins']+handoff['actual_previous_returns']:
        verify(row['path'],row['sha256'],row['size_bytes'])
    argv = command['argv']; values = {}; position = 4
    while position < len(argv):
        key=argv[position]; width=5 if key=='--worker-cpus' else 1
        binding.require(key not in values, 'duplicate approved option')
        values[key]=argv[position+1:position+1+width] if width==5 else argv[position+1]
        position += width+1
    binding.require(command['cwd']==str(ROOT) and '--maximum-blocks' not in values and
        values['--source-commit']==HEAD and values['--source-sha']==SOURCE and
        command['window_plan']['window_id']==WINDOW and
        command['window_plan']['block_ids']==PREPARED['block_ids'] and
        command['window_plan']['expected_ordinal_ranges']==handoff['window_plan']['expected_ordinal_ranges'] and
        command['window_plan']['expected_model_count']==PREPARED['expected_models'] and
        not any(key.startswith('--seed-') or key in ('--bootstrap','--bootstrap-sha','--old-archive','--old-summary','--old-selection') for key in values), 'approved ordinary window scope changed')
    for key in ('--historical-plan','--replay-plan','--replay-return','--logical-return',
                '--source-policy','--registry','--registry-return'):
        verify(values[key],values[key+'-sha'])
    verify(values['--capture'],handoff['population']['completed_replay']['capture_sha256'])
    replay_attempt=Path(values['--replay-attempt']); logical_attempt=Path(values['--logical-attempt'])
    for attempt in (replay_attempt,logical_attempt):
        manifest=load(attempt/'evidence/__manifest.json')
        for row in manifest['files']:
            relative=Path(row['path'])
            binding.require(not relative.is_absolute() and '..' not in relative.parts, 'foreign manifest file')
            verify(attempt/'evidence'/relative,row['sha256'],row['size_bytes'])
    query=handoff['population']['completed_replay']['query_index']
    # The replay manifest above contains and pins the actual query index.
    binding.require(any(row['sha256']==values['--query-index-sha'] for row in historical),
                    'actual query-index pin missing')
    from experiments.time_cut_v2.recorded_real import suffix_window
    args=suffix_window.parser().parse_args(argv[4:])
    outputs=[args.attempt_dir,args.registry_output,args.registration_return_output,
             suffix_window.runtime_return_path(args)]
    binding.require(all(not path.exists() and not path.is_symlink() and
        not path.with_name(path.name+'.partial').exists() for path in outputs), 'pilot outputs not fresh')
    jobs=active_recorded();binding.require(not jobs,'active recorded job exists')
    lock_path=Path('/tmp')/f'hiroute-recorded-phase-{os.getuid()}.lock'
    if lock_path.exists():
        lock_fd=os.open(lock_path,os.O_RDONLY|os.O_NOFOLLOW)
        try:
            fcntl.flock(lock_fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            fcntl.flock(lock_fd,fcntl.LOCK_UN)
        finally:
            os.close(lock_fd)
    # This is an observation precheck, never a substitute for the controller's
    # own actual 512 MiB address-space fence or standard runtime admission.
    suffix_census.check_sources(ROOT,HEAD,SOURCE)
    publish('precheck.json',dict(utc=utc(),source_commit=HEAD,source_sha256=SOURCE,source_files=119,
        command=pin(command_path),source_policy=pin(policy_path),historical_pins=historical,
        outputs=[str(path) for path in outputs],outputs_fresh=True,active_recorded_jobs=jobs,
        window_id=WINDOW,resource_plan=command['resource_plan'],controller_limit_unproven=True))
    env=dict(os.environ,**command['environment'])
    start=time.monotonic();started_utc=utc()
    stdout=OBS/'controller.stdout.json';stderr=OBS/'controller.stderr.txt'
    with stdout.open('xb') as out, stderr.open('xb') as err, (OBS/'samples.jsonl').open('xb') as samples:
        child=subprocess.Popen(argv,cwd=command['cwd'],env=env,stdout=out,stderr=err,start_new_session=True)
        publish('launch.json',dict(utc=started_utc,pid=child.pid,argv=argv,environment=command['environment'],
            cwd=command['cwd'],source_commit=HEAD,maximum_launches=1,
            standard_controller_preflight_required=True,controller_nominal_as_bytes=536870912))
        peak=0;controller_peak=0;limit_samples=set();seen=set();count=0;milestones={};per_pid={}
        state(dict(stage='controller-running',utc=utc(),pid=child.pid,observer_pid=os.getpid(),
                   controller_started=True,elapsed_seconds=0))
        print('CONTROLLER_STARTED pid='+str(child.pid)+' observation='+str(OBS),flush=True)
        while True:
            rows=process_rows();descendants={child.pid}
            for _ in range(len(rows)+1):
                more={pid for pid,row in rows.items() if row['ppid'] in descendants}
                if more<=descendants:break
                descendants|=more
            observed={pid:row for pid,row in rows.items() if pid in descendants}
            rss=sum(row['rss_bytes'] for row in observed.values());peak=max(peak,rss)
            controller_rss=rows.get(child.pid,{}).get('rss_bytes',0);controller_peak=max(controller_peak,controller_rss)
            limits=[]
            try:
                limits=[line for line in (Path('/proc')/str(child.pid)/'limits').read_text().splitlines()
                        if line.startswith('Max address space')]
                limit_samples.update(limits)
            except OSError:pass
            seen.update(observed)
            for pid,item in observed.items():
                previous=per_pid.get(str(pid),{})
                if not previous:
                    try:
                        cmd=(Path('/proc')/str(pid)/'cmdline').read_bytes().split(b'\0')
                        previous['command_prefix']=[v.decode(errors='replace') for v in cmd[:6]]
                    except OSError:pass
                previous.update(user_cpu_seconds=item['user_cpu_seconds'],system_cpu_seconds=item['system_cpu_seconds'],
                    peak_rss_bytes=max(previous.get('peak_rss_bytes',0),item['rss_bytes']),ppid=item['ppid'],start_ticks=item['start_ticks'])
                per_pid[str(pid)]=previous
            paths={'raw_attempt':args.attempt_dir,'request':args.attempt_dir/'request.json',
                'worker':args.attempt_dir/'worker.json','family_summary':args.attempt_dir/'evidence/family-summary.json',
                'window_selection':args.attempt_dir/'evidence/window-selection.json',
                'proof_archive':args.attempt_dir/'evidence/model-proofs.jsonl.gz',
                'window_summary':args.attempt_dir/'evidence/window-summary.json',
                'manifest':args.attempt_dir/'evidence/__manifest.json',
                'runtime_result':args.attempt_dir/'result.json','runtime_decision':args.attempt_dir/'decision.json',
                'runtime_return':suffix_window.runtime_return_path(args),
                'registry':args.registry_output,'registration_return':args.registration_return_output}
            for name,path in paths.items():
                if name not in milestones and path.exists():
                    milestones[name]=dict(elapsed_seconds=time.monotonic()-start,utc=utc(),observed_subtree_rss_bytes=rss,
                        controller_rss_bytes=controller_rss,observation_period_seconds=0.2)
            row=dict(elapsed_seconds=time.monotonic()-start,pids=sorted(observed),
                     observed_subtree_rss_bytes=rss,controller_rss_bytes=controller_rss,address_space=limits)
            samples.write(binding.canonical(row)+b'\n');samples.flush();count+=1
            waited,status,usage=os.wait4(child.pid,os.WNOHANG)
            if waited:
                code=os.waitstatus_to_exitcode(status);child.returncode=code
                break
            if count%10==0:
                state(dict(stage='controller-running',utc=utc(),pid=child.pid,observer_pid=os.getpid(),
                    controller_started=True,elapsed_seconds=time.monotonic()-start,
                    sampled_subtree_peak_rss_bytes=peak,sampled_controller_peak_rss_bytes=controller_peak,
                    raw_attempt_exists=args.attempt_dir.exists(),samples=count,milestones=milestones))
            time.sleep(0.2)
    result=dict(schema='hiroute-observed-single-window-controller-v1',utc=utc(),started_utc=started_utc,
        controller_pid=child.pid,argv=argv,exit_code=code,wall_seconds=time.monotonic()-start,
        sampled_subtree_peak_rss_bytes=peak,sampled_controller_peak_rss_bytes=controller_peak,
        kernel_wait4_ru_maxrss_bytes=usage.ru_maxrss*1024,controller_user_cpu_seconds=usage.ru_utime,
        controller_system_cpu_seconds=usage.ru_stime,address_space_samples=sorted(limit_samples),
        seen_pids=sorted(seen),milestones=milestones,observed_process_resources=per_pid,samples=count,observation_period_seconds=0.2,
        observation_scope='informational process subtree samples; actual runtime guards remain authoritative',
        stdout=pin(stdout),stderr=pin(stderr),raw_attempt_exists=args.attempt_dir.exists(),
        output_state=[dict(path=str(path),exists=path.exists()) for path in outputs],
        launches=1,automatic_retry=False,source_commit=HEAD,source_sha256=SOURCE,
        active_recorded_jobs_after_controller=active_recorded())
    if stdout.stat().st_size:
        try:result['controller_return']=load(stdout)
        except (ValueError,UnicodeError):result['controller_return_decode_failed']=True
    publish('controller-observation.json',result)
    suffix_census.check_sources(ROOT,HEAD,SOURCE)
    for row in historical:verify(row['path'],row['sha256'],row['size_bytes'])
    publish('postcheck.json',dict(utc=utc(),source_commit=HEAD,source_sha256=SOURCE,
        historical_pins_unchanged=True,active_recorded_jobs=active_recorded(),
        controller_exit_code=code,next_window_started=False))
    state(dict(stage='controller-ended',utc=utc(),controller_started=True,exit_code=code,
        wall_seconds=result['wall_seconds'],raw_attempt_exists=args.attempt_dir.exists()))
    print(json.dumps(result),flush=True)


if __name__=='__main__':
    try:
        main()
    except BaseException as error:
        failure=dict(utc=utc(),error_type=type(error).__name__,message=str(error),
            launch_record_exists=(OBS/'launch.json').exists(),automatic_retry=False)
        publish('observer-failure.json',failure)
        state(dict(stage='observer-failed',**failure))
        raise
