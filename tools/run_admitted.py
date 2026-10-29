"""Run one explicitly admitted command under the installed HiRoute supervisor."""
from __future__ import annotations
import argparse, hashlib, json, os, sys
from pathlib import Path
from hiroute.runtime import run_formal_supervised
from prepare_run import canonical, digest, system_mem_available_bytes, validate_profile, validate_request


def sha_file(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    return h.hexdigest()


def write_new_bytes(path, body):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as f:
        f.write(body); f.flush(); os.fsync(f.fileno())


def run_admitted(request_path, profile_path, admission_path, receipt_path, stdout_path, stderr_path, argv, cwd=None):
    request_path, profile_path, admission_path = map(Path,(request_path,profile_path,admission_path))
    request=json.loads(request_path.read_text()); profile=json.loads(profile_path.read_text()); admission=json.loads(admission_path.read_text())
    validate_profile(profile)
    if admission.get('schema')!='hiroute.run_admission.v1' or admission.get('status')!='admitted':
        raise ValueError('run has no successful admission record')
    if digest(canonical(request))!=admission.get('request_sha256') or digest(canonical(profile))!=admission.get('profile_sha256'):
        raise ValueError('request or profile no longer matches its admission record')
    validate_request(request, Path('/'))
    input_paths={p.resolve() for p in (request_path,profile_path,admission_path)}
    output_paths=[Path(p).resolve() for p in (receipt_path,stdout_path,stderr_path)]
    if len(set(output_paths))!=len(output_paths) or any(p in input_paths for p in output_paths):
        raise ValueError('output paths must be distinct from each other and from input records')
    if any(p.exists() for p in output_paths):
        raise FileExistsError('refusing to overwrite an existing run output')
    for p in output_paths: p.parent.mkdir(parents=True,exist_ok=True)
    needed=profile['memory_limit_bytes']+profile['host_headroom_bytes']+profile['growth_margin_bytes']
    if system_mem_available_bytes()<needed:
        raise RuntimeError('host MemAvailable fell below the admitted threshold before launch')
    source_sha=sha_file(Path(__file__))
    profile_sha=admission['profile_sha256']
    result=run_formal_supervised(
        argv, wall_limit_s=profile['wall_limit_seconds'], cpu_limit_s=profile['cpu_limit_seconds'],
        memory_limit_bytes=profile['memory_limit_bytes'], receipt_path=receipt_path,
        run_identity={'source_sha256':source_sha,'input_sha256':admission['request_sha256'],
                      'config_sha256':profile_sha,'budget_id':profile_sha},
        cwd=cwd or os.getcwd(), env=os.environ.copy())
    write_new_bytes(stdout_path,result.stdout); write_new_bytes(stderr_path,result.stderr)
    if result.returncode!=0 or result.timed_out or result.memory_limited or result.cpu_limited:
        return 124 if result.timed_out else 125 if result.memory_limited else 126 if result.cpu_limited else result.returncode
    return 0


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--request',required=True); p.add_argument('--profile',required=True)
    p.add_argument('--admission',required=True); p.add_argument('--receipt',required=True)
    p.add_argument('--stdout',required=True); p.add_argument('--stderr',required=True)
    p.add_argument('command',nargs=argparse.REMAINDER)
    a=p.parse_args(argv); command=a.command[1:] if a.command[:1]==['--'] else a.command
    if not command: p.error('provide a command after --')
    return run_admitted(a.request,a.profile,a.admission,a.receipt,a.stdout,a.stderr,command)


if __name__=='__main__':
    raise SystemExit(main())
