"""Public research boundary regressions using synthetic inputs and receipts."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import pytest

from hiroute.data.artifacts import digest, verify_manifest
from hiroute.execution import cohort
from hiroute.execution.config import load_config, n64_cells, N64_PROFILE
from hiroute.evaluation.cohort import summarize_rows
from hiroute.evaluation.report import summarize

ROOT = Path(__file__).resolve().parents[2]


def manifest(root):
    files = []
    for name in ('graph', 'catalog', 'bindings'):
        p = root / name
        p.write_bytes(name.encode())
        files.append(dict(role=name, path=name, bytes=p.stat().st_size, sha256=digest(p)))
    return dict(schema='hiroute.artifact_manifest.v1', files=files)


def test_manifest_reports_all_missing_corrupt_and_unsafe_inputs(tmp_path):
    m = manifest(tmp_path)
    assert verify_manifest(tmp_path, m)['verified']
    (tmp_path / 'graph').unlink()
    (tmp_path / 'catalog').write_bytes(b'bad')
    m['files'][2]['path'] = '../bindings'
    report = verify_manifest(tmp_path, m)
    assert [r['status'] for r in report['errors']] == ['missing', 'integrity_mismatch', 'unsafe_path']
    with pytest.raises(ValueError, match='duplicate'):
        verify_manifest(tmp_path, dict(m, files=[m['files'][0], m['files'][0]]))


def test_exact_legacy_profile_selection_and_complete_denominator():
    loaded = load_config(ROOT / 'configs/research/n64.json')
    matrix = loaded['matrix']
    assert len(n64_cells(matrix)) == 48
    for energy, cfg in loaded['configs'].items():
        assert cfg['model'] == {**matrix['model'], 'initial_energy_kwh': energy}
        assert cfg['selection'] == {**matrix['endpoint_and_selection_policy'], 'candidate_counts': [64]}
        assert cfg['implementation'] == N64_PROFILE
        assert cfg['resources']['numeric_workers'] == cfg['resources']['numeric_threads'] == 1
        assert [r['query_ids'][0] for r in cfg['pilot_matrix']] == [c['query_id'] for c in n64_cells(matrix) if c['initial_energy_kwh'] == energy]
    from hiroute.contracts import SolverConfig
    raw = json.loads((ROOT / 'configs/rebuild/r1_flat.json').read_text())
    with pytest.raises(ValueError):
        SolverConfig.from_dict(dict(raw, implementation=N64_PROFILE))


def test_prepare_missing_input_records_findings_without_solver(tmp_path):
    m = manifest(tmp_path)
    (tmp_path / 'graph').unlink()
    p = tmp_path / 'manifest.json'; p.write_text(json.dumps(m))
    out = tmp_path / 'check'
    with patch('hiroute.execution.pilot.worker', side_effect=AssertionError('must not solve')):
        with pytest.raises(ValueError, match='input closure incomplete'):
            cohort.prepare(ROOT / 'configs/research/n64.json', tmp_path, p, out)
    assert not (out / 'prepared.json').exists()
    assert json.loads((out / 'input-verification.json').read_text())['errors'][0]['role'] == 'graph'
    with pytest.raises(FileExistsError):
        cohort.prepare(ROOT / 'configs/research/n64.json', tmp_path, p, out)


def prepared_fixture(tmp_path, cap=12000):
    loaded = load_config(ROOT / 'configs/research/n64.json')
    loaded['config']['resources']['stage_cpu_s'] = cap
    prepared = dict(schema='hiroute.prepared_research.v1', run_id='synthetic-test', source={},
                    matrix=loaded['matrix'], config=loaded['config'])
    directory = tmp_path / 'prepared'; directory.mkdir()
    cohort.write_new(directory / 'prepared.json', prepared)
    cohort.write_new(directory / 'preparation.receipt.json', dict(prepared_sha256=digest(directory / 'prepared.json')))
    return directory, prepared


def timed_out(_directory, _prepared, _out, cell, method, charged, guard):
    assert guard(0)
    return dict(cell, method=method, status='time_limit', mathematical_status='unknown',
                query_loaded_total_s=120, worker_cpu_s=0.01, supervisor_cpu_s=0.01,
                execution='new', seed_key=['1', '0', 0, []])


def test_fresh_run_keeps_96_slots_and_never_reuses_or_restarts(tmp_path):
    directory, prepared = prepared_fixture(tmp_path)
    out = tmp_path / 'run'
    with patch.object(cohort, 'validate_prepared'), patch.object(cohort, 'run_slot', side_effect=timed_out) as run:
        assert cohort.benchmark(directory, out)['slots'] == 96
        assert run.call_count == 88
        with pytest.raises(FileExistsError):
            cohort.benchmark(directory, out)
        assert run.call_count == 88
    report = summarize(out)
    assert report['common_exact_pairs'] == 0
    for summary in report['summary'].values():
        assert summary['full_query_cells'] == 48 and summary['supported_query_cells'] == 44
        assert summary['statuses'] == {'time_limit': 44, 'input_domain_unavailable': 4}
        assert summary['executions'] == {'new': 44, 'not_attempted': 4}
    assert report['accounting']['historical_carried_cpu_s'] == 0
    receipt = next((out / 'rows').glob('*.json')); receipt.write_text('{}')
    with pytest.raises(ValueError, match='slot receipt mismatch'):
        summarize(out)


def test_budget_stop_reserves_complete_pairs_and_preserves_denominator(tmp_path):
    directory, prepared = prepared_fixture(tmp_path, cap=1000)
    out = tmp_path / 'run'
    with patch.object(cohort, 'validate_prepared'), patch.object(cohort, 'run_slot', side_effect=AssertionError('no reservation')):
        result = cohort.benchmark(directory, out)
    assert result['state'] == 'budget_stopped'
    assert summarize(out)['summary']['scale']['statuses'] == {'not_run_cpu_budget': 44, 'input_domain_unavailable': 4}


def test_unknown_failure_has_terminal_evidence_and_cannot_restart(tmp_path):
    directory, prepared = prepared_fixture(tmp_path)
    out = tmp_path / 'run'
    with patch.object(cohort, 'validate_prepared'), patch.object(cohort, 'run_slot', side_effect=RuntimeError('uncertain child')):
        with pytest.raises(RuntimeError, match='uncertain child'):
            cohort.benchmark(directory, out)
    terminal = json.loads((out / 'terminal.json').read_text())
    assert terminal['state'] == 'failed'
    assert summarize(out)['summary']['scale']['full_query_cells'] == 48


def test_statistics_preserves_reuse_and_rejects_duplicate_or_foreign_rows():
    cells = n64_cells(load_config(ROOT / 'configs/research/n64.json')['matrix'])
    row = dict(cells[0], method='scale', status='time_limit', mathematical_status='unknown', execution='reused')
    summary = summarize_rows(cells, [row])
    assert summary['summary']['scale']['executions']['reused'] == 1
    with pytest.raises(ValueError, match='duplicate or foreign'):
        summarize_rows(cells, [row, row])
    with pytest.raises(ValueError, match='duplicate or foreign'):
        summarize_rows(cells, [dict(row, query_id='foreign')])


def test_summary_cli_does_not_import_numerical_or_process_modules():
    script = '''import sys
from hiroute.cli import parser
from hiroute.evaluation.report import summarize
parser().parse_args(['summarize','--input','unused','--output','unused'])
assert 'hiroute.exact.search' not in sys.modules
assert 'hiroute.exact.scale' not in sys.modules
assert 'hiroute.execution.pilot' not in sys.modules
'''
    subprocess.run([sys.executable, '-c', script], check=True)


def test_result_validation_retains_unknown_and_rejects_false_completion():
    cohort.validate_result(dict(status='memory_limit', mathematical_status='unknown'))
    with pytest.raises(ValueError):
        cohort.validate_result(dict(status='memory_limit', mathematical_status='attained_optimum'))
    with pytest.raises(ValueError):
        cohort.validate_result(dict(status='attained_optimum', mathematical_status='attained_optimum', key=['1','0',0,[]]))
    with pytest.raises(ValueError, match='paired seed'):
        cohort.compare_pair([dict(method=m,status='time_limit',seed_key=[i]) for i,m in enumerate(('flat_bb_strong','scale'))])
