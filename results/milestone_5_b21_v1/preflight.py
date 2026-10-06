"""Read-only preservation audit. Outputs exclusively in this run's namespace."""
import hashlib
import json
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write(name, value):
    with (OUT / name).open('x') as stream:
        stream.write(json.dumps(value, indent=2, allow_nan=False) + '\n')


def counts(path):
    suites = list(ET.parse(path).getroot().iter('testsuite'))
    result = {k: sum(int(s.attrib.get(k, 0)) for s in suites)
              for k in ['tests', 'failures', 'errors', 'skipped']}
    result['passed'] = result['tests'] - sum(result[k] for k in ['failures', 'errors', 'skipped'])
    return result


def main():
    started = time.perf_counter()
    initial = json.loads((OUT / 'git_before.json').read_text())
    refs, manifests = [], []
    directories = ['milestone_4r', 'milestone_4b', 'milestone_4r_b1',
                   'milestone_4r_b1d', 'milestone_4r_b1e', 'milestone_4r_b1d2',
                   'milestone_4r_b2_b21']
    names = ['preservation_before.json', 'preservation_checkpoint.json',
             'resume_preservation_before.json', 'acceptance.json',
             'frozen_input_hash_manifest.json', 'query_preregistration.json',
             'boundary_manifest.json', 'landmark_manifest.json',
             'experiment_protocol.json', 'hierarchy_preregistration.json',
             'prior_attempt_hash_manifest.json', 'probe_freeze_manifest.json']
    for directory in directories:
        base = ROOT / 'results' / directory
        for name in names:
            p = base / name
            if not p.is_file():
                continue
            data = json.loads(p.read_text())
            manifests.append(str(p.relative_to(ROOT)))
            groups = [('files', data)] if name in [
                'frozen_input_hash_manifest.json', 'prior_attempt_hash_manifest.json',
                'probe_freeze_manifest.json'] else [
                (k, data.get(k, {})) for k in [
                    'files', 'source_sha256', 'archive_sha256', 'archived_hashes',
                    'artifact_sha256', 'final_source_sha256', 'evidence_sha256',
                    'extraction_code_sha256', 'graph_sha256',
                    'implementation_sha256', 'input_sha256', 'inputs']]
            for group_name, group in groups:
                for filename, record in group.items():
                    expected = record.get('sha256') if isinstance(record, dict) else record
                    if not isinstance(expected, str) or len(expected) != 64:
                        continue
                    target = ROOT / filename
                    if group_name == 'graph_sha256' and name == 'boundary_manifest.json':
                        target = ROOT / 'data/processed/graphs/slovenia_extended' / filename
                    elif not target.is_file() and (base / filename).is_file():
                        target = base / filename
                    refs.append(dict(manifest=str(p.relative_to(ROOT)),
                                     path=str(target.relative_to(ROOT)), expected_sha256=expected))
            if data.get('report_sha256'):
                report = ROOT / 'docs' / (directory.upper() + '_REPORT.md')
                refs.append(dict(manifest=str(p.relative_to(ROOT)),
                                 path=str(report.relative_to(ROOT)), expected_sha256=data['report_sha256']))
    paths = {r['path'] for r in refs} | set(manifests)
    paths.update(subprocess.check_output(['git', 'ls-files'], cwd=ROOT, text=True).splitlines())
    for base in [ROOT / 'src', ROOT / 'scripts', ROOT / 'tests', ROOT / 'docs']:
        paths.update(str(p.relative_to(ROOT)) for p in base.rglob('*')
                     if p.is_file() and '__pycache__' not in p.parts)
    for directory in directories:
        paths.update(str(p.relative_to(ROOT)) for p in (ROOT / 'results' / directory).rglob('*')
                     if p.is_file() and '__pycache__' not in p.parts)
    paths.update(str(p.relative_to(ROOT)) for p in ROOT.glob('MILESTONE_*.md'))
    historical_paths = sorted(str(p.relative_to(ROOT)) for p in
        (ROOT / 'results/milestone_4r_b2_b21').rglob('*') if p.is_file())
    paths.update(historical_paths)
    hashes = {name: digest(ROOT / name) if (ROOT / name).is_file() else None
              for name in sorted(paths)}
    violations = [r | {'actual_sha256': hashes[r['path']]} for r in refs
                  if hashes[r['path']] != r['expected_sha256']]
    write('frozen_input_hash_manifest.json', hashes)
    write('historical_b21_v0_hash_manifest.json',
          {n: hashes[n] for n in historical_paths} |
          {'docs/MILESTONE_4R_B2_B21_REPORT.md': hashes['docs/MILESTONE_4R_B2_B21_REPORT.md']})
    write('predecessor_manifest_audit.json', dict(manifests=manifests, records=refs, violations=violations))
    authority_names = {
        'MILESTONE_5_MULTISTOP_CORE_THEORY_V1.md': 'dbe44ff83b4d98f2d06b090f7cd44bd40b0a4e21cc8eb439eee991ff2c73ccb2',
        'MILESTONE_5_MULTISTOP_CORE_THEORY_AUDIT_V1.md': '02a1c417614852daec17a46be66f8930aa8de626128344122136617d5077b4c7',
        'MILESTONE_5_B21_EXACT_VALIDATION_PROTOCOL_V1.md': '013c039b0c4d71f61fc43002ae05f63d33073293f7e0a709fc2e8b5bbe1e537f'}
    authorities = []
    for name, expected in authority_names.items():
        actual = digest(ROOT / name)
        authorities.append(dict(requested_path='docs/' + name, resolved_path=name,
            requested_path_exists=(ROOT / 'docs' / name).exists(),
            expected_sha256=expected, actual_sha256=actual, verified=actual == expected,
            path_resolution='Supplied byte-identical artifact present at repository root; no reconstruction'))
        (OUT / name).write_bytes((ROOT / name).read_bytes())
    write('authority_manifest.json', dict(ordered_read_completed=True,
        research_spec_sha256=digest(ROOT / 'RESEARCH_SPEC_v0.2.md'), authorities=authorities))
    (OUT / 'protocol_snapshot.md').write_bytes((ROOT / list(authority_names)[-1]).read_bytes())
    before = dict(**initial, files_verified=len(hashes), expected_hash_records_verified=len(refs),
        historical_files_archived=len(historical_paths) + 1, hash_violations=violations,
        authority_passed=all(a['verified'] for a in authorities),
        preservation_passed=not violations and not initial['tracked_diff'].strip(),
        seconds=time.perf_counter() - started, implementation_started=False)
    write('preservation_before.json', before)
    print(json.dumps({k:v for k,v in before.items() if k not in ['git_status']}), flush=True)
    command = [sys.executable, '-m', 'pytest', '-vv', '--require-real-data',
               '--require-envelope-results', '--require-regional-results',
               '--require-opportunity-results', '--require-microplan-results',
               '--junitxml=' + str(OUT / 'preexisting_tests.xml')]
    start = time.perf_counter()
    with (OUT / 'preexisting_tests.log').open('x') as log:
        code = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT).returncode
    summary = dict(command=command, exit_code=code, seconds=time.perf_counter() - start,
                   **counts(OUT / 'preexisting_tests.xml'))
    write('pretest_summary.json', summary)
    print(json.dumps(summary), flush=True)
    if code or violations or not before['authority_passed'] or not before['preservation_passed']:
        sys.exit(1)


if __name__ == '__main__':
    main()
