"""Selection is explicit; missing research data and fixtures cannot pass silently."""
from pathlib import Path
from types import SimpleNamespace
import importlib.util

import pytest


def policy():
    spec = importlib.util.spec_from_file_location('hiroute_collection_policy', Path(__file__).with_name('conftest.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_allowlist_includes_synthetic_but_not_archived_summary():
    module = policy()
    assert module._code_only_path(module.ROOT / 'tests/test_time_cut_v2.py')
    assert module._code_only_path(module.ROOT / 'tests/terminal_energy/test_energy.py')
    assert not module._code_only_path(module.ROOT / 'tests/test_m5d_terminal_summary.py')
    assert not module._code_only_path(module.ROOT / 'tests/test_unknown_new_module.py')


def test_artifact_opt_in_requires_research_outputs(tmp_path):
    module = policy()
    module.ROOT = tmp_path
    config = SimpleNamespace(getoption=lambda name: True)
    with pytest.raises(pytest.UsageError, match='generated research inputs'):
        module.pytest_configure(config)
    (tmp_path / 'results').mkdir()
    with pytest.raises(pytest.UsageError, match='generated research inputs'):
        module.pytest_configure(config)


def test_explicit_excluded_module_has_actionable_error(tmp_path):
    module = policy()
    module.ROOT = tmp_path
    path = tmp_path / 'tests/test_archived.py'
    path.parent.mkdir()
    path.write_text('raise RuntimeError("must not import")')
    config = SimpleNamespace(getoption=lambda name: False, args=[str(path)])
    with pytest.raises(pytest.UsageError, match='--include-artifact-tests'):
        module.pytest_configure(config)


def test_missing_required_fixture_is_not_ignored(tmp_path):
    module = policy()
    missing = module.ROOT / 'tests/test_time_cut_v2.py'
    assert module.pytest_ignore_collect(missing, SimpleNamespace(getoption=lambda name: False, args=[str(missing)])) is False
    # Selection does not check whether test inputs exist; loading missing inputs
    # remains an ordinary hard failure, rather than an automatic skip.
    with pytest.raises(FileNotFoundError):
        (tmp_path / 'missing_required_fixture.json').read_text()


def test_root_discovery_excludes_extended_code_gate():
    module = policy()
    config = SimpleNamespace(getoption=lambda name: False, args=[str(module.ROOT / 'tests')])
    assert module.pytest_ignore_collect(module.ROOT / 'tests/terminal_energy', config) is True
    assert module.pytest_ignore_collect(module.ROOT / 'tests/test_c01_d0_bootstrap.py', config) is True
    assert module.pytest_ignore_collect(module.ROOT / 'tests/test_time_cut_v2.py', config) is False


def test_explicit_known_code_gate_directory_is_collected():
    module = policy()
    directory = module.ROOT / 'tests/terminal_energy'
    config = SimpleNamespace(getoption=lambda name: False, args=[str(directory)])
    assert module.pytest_ignore_collect(directory / 'test_energy.py', config) is False


def test_artifact_collection_switch_is_independent():
    module = policy()
    config = SimpleNamespace(getoption=lambda name: True, args=[str(module.ROOT / 'tests')])
    assert module.pytest_ignore_collect(module.ROOT / 'tests/test_m5d_terminal_summary.py', config) is None


def test_new_unclassified_module_is_a_hard_collection_error(tmp_path):
    module = policy()
    module.ROOT = tmp_path
    path = tmp_path / 'tests/test_new_unclassified.py'
    path.parent.mkdir()
    path.write_text('raise RuntimeError("must not import")')
    for artifact_opt_in in (False, True):
        config = SimpleNamespace(getoption=lambda name: artifact_opt_in, args=[str(tmp_path / 'tests')])
        with pytest.raises(pytest.UsageError, match='Unclassified test module.*Register it'):
            module.pytest_ignore_collect(path, config)


def publication_tool(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parents[1] / 'tools' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_publication_preflight_needs_only_git_index(tmp_path, monkeypatch):
    module = publication_tool('check_code_publication')
    module.ROOT = tmp_path
    # A clean checkout has no archive manifest or historical output inventory.
    def git_output(command, cwd):
        assert cwd == tmp_path
        if command[1] == 'ls-files':
            return b'100644 abc 0\tsrc/example.py\0'
        assert command == ['git', 'cat-file', '-s', 'abc']
        return b'10'
    monkeypatch.setattr(module.subprocess, 'check_output', git_output)
    assert module.main() == 0


def test_publication_preflight_rejects_archive_inventory(tmp_path, monkeypatch):
    module = publication_tool('check_code_publication')
    module.ROOT = tmp_path
    monkeypatch.setattr(module.subprocess, 'check_output', lambda command, cwd:
                        b'100644 abc 0\tartifacts/index.json\0' if command[1] == 'ls-files' else b'10')
    assert module.main() == 1


def test_archive_verification_requires_explicit_external_index(tmp_path):
    module = publication_tool('verify_artifacts')
    with pytest.raises(SystemExit) as error:
        module.main(['--root', str(tmp_path), '--prefix', 'sample/'])
    assert error.value.code == 2


def test_external_archive_verification_checks_hash_and_missing_files(tmp_path):
    import hashlib
    import json
    module = publication_tool('verify_artifacts')
    root = tmp_path / 'archive'
    (root / 'sample').mkdir(parents=True)
    payload = root / 'sample' / 'tiny.txt'
    payload.write_bytes(b'tiny synthetic test input')
    index = tmp_path / 'external-manifest.json'
    index.write_text(json.dumps({'files': [{'path': 'sample/tiny.txt', 'bytes': payload.stat().st_size,
                                           'sha256': hashlib.sha256(payload.read_bytes()).hexdigest()}]}))
    args = ['--index', str(index), '--root', str(root), '--prefix', 'sample/']
    assert module.main(args) == 0
    payload.write_bytes(b'changed')
    assert module.main(args) == 1
    payload.unlink()
    assert module.main(args) == 1
