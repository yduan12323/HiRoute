"""Verify protection and record the 4R-A gate; never writes prior milestones."""
import argparse
import importlib.metadata
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

from _stopplan4r_common import ROOT, sha256, verify_protected, write_json


def capture(out):
    files = []
    for base in ['data/raw', 'data/processed', 'results/milestone_1', 'results/milestone_2',
                 'results/milestone_3a', 'results/milestone_4a', 'results/milestone_4b',
                 'src/graph', 'src/envelope', 'src/opportunity', 'src/microplan']:
        files.extend(p for p in (ROOT / base).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    files.extend(p for p in (ROOT / 'tests').glob('*.py') if 'stopplan4r' not in p.name)
    files.extend(p for p in (ROOT / 'configs').glob('*.yaml') if p.name != 'stopplan_4r.yaml')
    files.extend(p for p in (ROOT / 'docs').glob('*.md') if p.name != 'MILESTONE_4R_REPORT.md')
    files.extend(ROOT / p for p in ['RESEARCH_SPEC.md', 'RESEARCH_SPEC_v0.2.md', 'MILESTONE_4R_CODEX_PROMPT.md',
        'MILESTONE_4R_IMPLEMENTATION_PLAN.md', 'environment.yml', 'environment-resolved.yml',
        'environment-linux-64.lock', 'environment-osmium-linux-64.lock', '.env.example'])
    record = {'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        'git_status': subprocess.check_output(['git', 'status', '--porcelain'], text=True),
        'files': {str(p.relative_to(ROOT)): {'sha256': sha256(p), 'size_bytes': p.stat().st_size} for p in sorted(set(files))},
        'environment': environment()}
    with (out / 'preservation_before.json').open('x') as stream:
        json.dump(record, stream, indent=2)
    print(f'Captured {len(record["files"])} protected files')


def environment():
    return {'python': sys.version, 'executable': sys.executable, 'platform': platform.platform(),
            'packages': {d.metadata['Name']: d.version for d in importlib.metadata.distributions()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', action='store_true', help='Fresh checkout only: refuses to overwrite a previous protection manifest')
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    out = ROOT / 'results/milestone_4r'; out.mkdir(parents=True, exist_ok=True)
    if args.capture:
        capture(out); return
    preserve = verify_protected()
    preserve['timestamp_utc'] = datetime.now(timezone.utc).isoformat()
    write_json(out / 'preservation_after.json', preserve)
    if not preserve['passed']:
        raise ValueError(f'Protected files changed: {preserve["changed_files"]}')
    if args.verify_only:
        print(json.dumps(preserve, indent=2)); return
    def counts(name):
        suites = list(ET.parse(out / name).getroot().iter('testsuite'))
        return {k: sum(int(s.attrib.get(k, 0)) for s in suites) for k in ['tests', 'failures', 'errors', 'skipped']}
    tests, previous, semantic = counts('tests.xml'), counts('preexisting_tests.xml'), counts('semantic_tests.xml')
    build = json.loads((out / 'site_build.json').read_text())
    diagnostic = json.loads((out / 'diagnostic.json').read_text())
    report = ROOT / 'docs/MILESTONE_4R_REPORT.md'
    checks = {
        'preexisting_tests': previous['tests'] >= 84 and not any(previous[k] for k in ['failures', 'errors', 'skipped']),
        'semantic_regressions': semantic['tests'] >= 29 and not any(semantic[k] for k in ['failures', 'errors', 'skipped']),
        'complete_final_suite': tests['tests'] >= previous['tests'] + semantic['tests'] + 3 and not any(tests[k] for k in ['failures', 'errors', 'skipped']),
        'protected_unchanged': preserve['passed'],
        'accepted_source_unchanged': preserve['verified_accepted_source_files'] == 56,
        'static_schema_and_reproducibility': build['byte_identical_reordered_rebuild'],
        'all_30_development_ods': diagnostic['development_od_count'] == 30 and diagnostic['case_count'] == 480,
        'independent_directed_route_checks': len(diagnostic['independent_route_checks']) == 18 and all(x['passed'] for x in diagnostic['independent_route_checks']),
        'report_and_go1_boundary': report.exists() and 'revised Go-1 has not yet been established' in report.read_text(),
    }
    for metadata in [build, diagnostic]:
        for name, digest in metadata['outputs'].items():
            if sha256(out / name) != digest:
                raise ValueError(f'4R evidence checksum mismatch: {name}')
        for name, digest in metadata['inputs'].items():
            if sha256(ROOT / name) != digest:
                raise ValueError(f'4R input checksum mismatch: {name}')
    tracked_diff = subprocess.check_output(['git', 'diff', '--stat'], text=True)
    (out / 'git_diff_stat.txt').write_text(tracked_diff)
    record = {'timestamp_utc': datetime.now(timezone.utc).isoformat(), 'passed': all(checks.values()),
        'checks': checks, 'tests': tests, 'preexisting_tests': previous, 'semantic_tests': semantic,
        'preservation': preserve, 'environment': environment(), 'report_sha256': sha256(report),
        'scope': '4R-A semantic substrate and bounded flat deterministic baseline only; revised Go-1 not established',
        'git_branch': subprocess.check_output(['git', 'branch', '--show-current'], text=True).strip(),
        'git_status': subprocess.check_output(['git', 'status', '--porcelain'], text=True),
        'git_diff_stat_includes_preexisting_changes': tracked_diff,
        'final_source_sha256': {str(p.relative_to(ROOT)): sha256(p) for base in ['src/stopplan4r', 'scripts', 'tests']
            for p in (ROOT / base).rglob('*.py') if base == 'src/stopplan4r' or 'stopplan4r' in p.name or 'stopplan_4r' in p.name or p.name == 'build_stop_sites_4r.py'},
        'config_sha256': sha256(ROOT / 'configs/stopplan_4r.yaml')}
    write_json(out / 'acceptance.json', record)
    print(json.dumps({'passed': record['passed'], 'checks': checks, 'tests': tests,
                      'protected_files': preserve['verified_files'], 'git_diff_stat': tracked_diff}, indent=2))
    if not record['passed']:
        raise ValueError('4R-A acceptance gate incomplete')


if __name__ == '__main__':
    main()
