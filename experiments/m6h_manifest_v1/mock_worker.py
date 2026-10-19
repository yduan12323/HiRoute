"""Only a built-in synthetic fixture; never imports solver or reads datasets."""
import json
import os
from pathlib import Path
import sys
import time
from .contract import BoundSyntheticInput, canonical, digest, identity


def result(bound, operation, method, common, scenario):
    value = dict(identity=identity(bound, operation, method), evidence='MOCK_ONLY')
    if operation == 'prepare':
        if scenario == 'no_seed':
            return dict(value, outcome='seed_exhausted_unknown', stream_exhausted=True,
                        proposals=2, rejections=2, feasibility='unknown')
        return dict(value, outcome='common_feasible_seed', seed='builtin-mock-seed-v1',
                    key=['12','0',0,[]], hmax=4, fresh_replays=2)
    value.update(outcome='exact_attained', common_sha256=digest(common),
        key=['12','0',0,[]], hmax=4, attained=True)
    if operation == 'replay': value['fresh_process_replay'] = True
    if operation == 'ref': value['implementation'] = 'independent_mock_ref_no_physical_claim'
    if scenario == 'drift': value['identity']['runtime'] = 'drift'
    if scenario == 'wrong_key': value['key'][0] = '13'
    return value


def main():
    request = json.loads(sys.argv[1])
    bound = BoundSyntheticInput.fixture(request['domain'])
    scenario = request['scenario']
    # Synthetic startup/phase boundary proof; never used by physical workers.
    if scenario == 'startup_delay':time.sleep(.75)
    if request['operation'] == 'search':
        from experiments.mechanism_recovery_v1.supervisor import publish_phase_entry
        publish_phase_entry()
    if scenario == 'timeout': time.sleep(30)
    if scenario == 'crash': raise RuntimeError('Deliberate synthetic failure')
    value = result(bound, request['operation'], request['method'], request['common'], scenario)
    Path(os.environ['HIROUTE_WORKER_RECEIPT']).write_bytes(canonical(dict(status='SUCCESS', result=value)))


if __name__ == '__main__': main()
