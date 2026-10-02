"""4R-only provenance, guards, and result IO; frozen inputs are read-only."""
import json
from pathlib import Path
import resource

from _common import ROOT, read_config, sha256


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def peak_rss_mib():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def memory_guard(config, projected_additional_gib=0):
    info = {line.split(':')[0]: int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines() if line.split()[1].isdigit()}
    available_gib = info['MemAvailable'] / 1024**2
    rss_gib = peak_rss_mib() / 1024
    if rss_gib + projected_additional_gib > config['maximum_rss_gib'] or available_gib - projected_additional_gib < config['minimum_available_gib']:
        raise MemoryError(f'4R memory guard: RSS={rss_gib:.3f}, available={available_gib:.3f}, projected additional={projected_additional_gib:.3f} GiB')
    return {'peak_rss_gib': rss_gib, 'available_gib': available_gib,
            'projected_additional_gib': projected_additional_gib}


def verify_protected():
    before = json.loads((ROOT / 'results/milestone_4r/preservation_before.json').read_text())
    changes = [p for p, record in before['files'].items()
               if not (ROOT / p).is_file() or (ROOT / p).stat().st_size != record['size_bytes'] or sha256(ROOT / p) != record['sha256']]
    accepted = json.loads((ROOT / 'results/milestone_4b/acceptance.json').read_text())['final_source_sha256']
    source_changes = [p for p, digest in accepted.items()
                      if not (ROOT / p).is_file() or sha256(ROOT / p) != digest]
    return {'passed': not changes and not source_changes, 'verified_files': len(before['files']),
            'changed_files': changes, 'verified_accepted_source_files': len(accepted),
            'changed_accepted_source_files': source_changes,
            'accepted_source_manifest': 'results/milestone_4b/acceptance.json'}
