"""Installed comparator boundary, including successful supervised finalization."""
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from unittest.mock import patch

import pytest
from hiroute_compare.io import sha
from hiroute_compare.verify import verify_bundle

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from tests import test_import_strict_candidate as import_tests
from exact_physical_fixtures import case, tiny_table


def bundle_fixture(root):
    args = import_tests.ImportTests().setup_case(root)
    _, expected, model, _, _, table, parameters, upper = args
    (root / 'table.json').write_bytes(tiny_table(case('empty_prefix_terminal'))[1])
    (root / 'physics.json').write_text(json.dumps(parameters))
    (root / 'upper.json').write_text(json.dumps(upper))
    with sqlite3.connect(root / 'roads.sqlite') as db:
        db.execute('CREATE TABLE edges(eid TEXT PRIMARY KEY,u TEXT,v TEXT,t TEXT,l TEXT)')
        db.execute('INSERT INTO edges VALUES(?,?,?,?,?)', ('o>z', 'o', 'z', '2', '2'))
    expected.pop('verifier_source')
    names = ['table.json', 'physics.json', 'upper.json', 'roads.sqlite', 'origin/consumer-admission.json',
             'origin/audit-root/SMT/0001.dag.smt2', 'origin/audit-root/SMT/candidate.unverified.json']
    bundle = dict(schema='hiroute.compare_bundle.v1', files=[dict(path=n,bytes=(root/n).stat().st_size,sha256=sha(root/n)) for n in names],
                  table=dict(format='json',path='table.json'), parameters='physics.json', incumbent='upper.json',
                  graph_db='roads.sqlite', origin='origin', depth=len(model.choices), expected=expected)
    path = root / 'bundle.json'; path.write_text(json.dumps(bundle))
    return path, bundle


def test_bundle_verification_never_imports_production_solver(tmp_path):
    path, bundle = bundle_fixture(tmp_path)
    out = tmp_path / 'out'; out.mkdir()
    import builtins
    original = builtins.__import__
    def importing(name, *args, **kwargs):
        if name.split('.')[0] in ('hiroute', 'hiroute_ref', 'timecut5'):
            raise AssertionError('production dependency')
        return original(name, *args, **kwargs)
    with patch('builtins.__import__', side_effect=importing):
        result = verify_bundle(path, tmp_path, out)
    assert result['status'] == 'COMPLETE'
    assert result['original_run_status'] == 'UNKNOWN'
    assert result['optimality_certified'] is False
    assert result['comparison']['primary_value'] == '2'
    assert result['output_path_checks'][0]['status'] == 'exact_path_replay_pass'


def test_resealed_wrong_path_still_fails_exact_raw_replay(tmp_path):
    path, bundle = bundle_fixture(tmp_path)
    with sqlite3.connect(tmp_path / 'roads.sqlite') as db:
        db.execute("UPDATE edges SET t='9'")
    row = next(r for r in bundle['files'] if r['path'] == 'roads.sqlite')
    row['sha256'] = sha(tmp_path / 'roads.sqlite')
    path.write_text(json.dumps(bundle))
    out = tmp_path / 'out'; out.mkdir()
    with pytest.raises(ValueError, match='raw selected path totals'):
        verify_bundle(path, tmp_path, out)


def test_cli_requires_successful_new_terminal_and_retains_historical_unknown(tmp_path):
    path, bundle = bundle_fixture(tmp_path)
    out = tmp_path / 'run'
    command = [sys.executable, '-m', 'hiroute_compare.cli', 'verify', '--bundle', str(path),
               '--artifact-root', str(tmp_path), '--output', str(out), '--host-headroom-bytes', '0']
    result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    terminal = json.loads((out / 'terminal.json').read_text())
    assert terminal['status'] == 'COMPLETE' and terminal['original_run_status'] == 'UNKNOWN'
    assert terminal['body_sha256'] == sha(out / 'body-result.json')
    assert subprocess.run(command, cwd=tmp_path, capture_output=True).returncode != 0
    command[command.index(str(out))] = str(tmp_path / 'timeout')
    result = subprocess.run(command + ['--wall-s', '0.001'], cwd=tmp_path, capture_output=True, timeout=10)
    assert result.returncode == 75
    terminal = json.loads((tmp_path / 'timeout/terminal.json').read_text())
    assert terminal['status'] == 'UNKNOWN' and terminal['reason'] == 'time_limit'
    command[command.index(str(tmp_path / 'timeout'))] = str(tmp_path / 'cpu-limit')
    result = subprocess.run(command + ['--cpu-s', '0.001'], cwd=tmp_path, capture_output=True, timeout=10)
    assert result.returncode == 75
    terminal = json.loads((tmp_path / 'cpu-limit/terminal.json').read_text())
    assert terminal['status'] == 'UNKNOWN' and terminal['reason'] == 'cpu_limit'


def test_unsealed_required_file_and_truncated_assignment_are_rejected(tmp_path):
    path, bundle = bundle_fixture(tmp_path)
    bundle['files'] = [r for r in bundle['files'] if r['path'] != 'physics.json']
    path.write_text(json.dumps(bundle))
    with pytest.raises(ValueError, match='unsealed required'):
        verify_bundle(path, tmp_path, tmp_path / 'unsealed')
    # Exact assertion/missing-assignment tests are also retained from the old importer.
