"""One persistent, resource-bounded candidate interpreter; no numerical cache."""
import argparse
import os
import resource
import sys
import time

from .candidate_memory import peak_rss_bytes
from .lp_jobs import (CHILD_AS_BYTES, SOFT_RSS_MIB, STDOUT_BYTES, THREAD_ENV,
                      LP_SECONDS, canonical, decode, require)
from .lp_stream_jobs import (LPStreamJob, BoundJob, FRAME_SCHEMA, REQUEST_SCHEMA,
                             INPUT_FRAME_BYTES)
from .lp_worker import CandidateFence, execute_candidate


def serve(generation, *, source=None, output=None, solve=None, budget_factory=None, versions=None):
    """Test seam uses only hand certificates; CLI exposes no solver injection."""
    source = sys.stdin.buffer if source is None else source
    output = sys.stdout.buffer if output is None else output
    previous = -1
    while True:
        raw = source.readline(INPUT_FRAME_BYTES + 1)
        if not raw:
            return 0
        require(len(raw) <= INPUT_FRAME_BYTES and raw.endswith(b'\n'), 'candidate input frame byte cap')
        request = decode(raw)
        require(type(request) is dict and set(request) ==
                {'schema', 'generation', 'job', 'deadline_monotonic'} and
                request['schema'] == REQUEST_SCHEMA and request['generation'] == generation,
                'candidate request generation/schema')
        deadline = request['deadline_monotonic']
        require(type(deadline) in (float, int) and time.monotonic() < deadline <=
                time.monotonic() + LP_SECONDS, 'candidate absolute deadline')
        job = LPStreamJob.from_dict(request['job'])
        require(job.model_ordinal > previous, 'worker model ordinals must increase')
        previous = job.model_ordinal
        bound = BoundJob(job, generation)
        used = 0

        def emit(frame):
            nonlocal used
            require(time.monotonic() < deadline, 'candidate serialization deadline exhausted')
            require(peak_rss_bytes() <= SOFT_RSS_MIB * 1024**2, 'candidate retained RSS cap')
            wire = canonical(dict(frame, schema=FRAME_SCHEMA)) + b'\n'
            require(used + len(wire) <= STDOUT_BYTES, 'candidate output byte cap exhausted')
            used += len(wire)
            output.write(wire)
            output.flush()

        def load(_):
            require(peak_rss_bytes() <= SOFT_RSS_MIB * 1024**2, 'candidate retained RSS cap')
            return job.model

        execute_candidate(bound, deadline_monotonic=deadline, emit=emit, solve=solve,
            budget_factory=budget_factory, versions=versions, model_loader=load)
        emit(dict(job=bound.to_dict(), kind='done'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cpu', type=int, required=True)
    parser.add_argument('--generation', required=True)
    args = parser.parse_args()
    require(args.cpu in os.sched_getaffinity(0), 'candidate CPU outside inherited allowed mask')
    os.sched_setaffinity(0, {args.cpu})
    resource.setrlimit(resource.RLIMIT_AS, (CHILD_AS_BYTES, CHILD_AS_BYTES))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    require(all(os.environ.get(name) == '1' for name in THREAD_ENV),
            'single-thread BLAS environment required')
    require(not any(name == 'timecut5' or name.startswith(('timecut5.', 'validation.reference5'))
                    for name in sys.modules), 'forbidden module imported before candidate fence')
    sys.meta_path.insert(0, CandidateFence())
    return serve(args.generation)


if __name__ == '__main__':
    raise SystemExit(main())
