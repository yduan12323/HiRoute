import hashlib
import importlib.util
from pathlib import Path
import sys

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'experiments/m5e2e_v1'

# Load the report-only source files explicitly; the test process also has the
# frozen 966912 wheel installed, which is intentionally not the module under test.
common_name = 'experiments.m5e2e_v1.common'
common_spec = importlib.util.spec_from_file_location(common_name, PACKAGE / 'common.py')
common = importlib.util.module_from_spec(common_spec)
sys.modules[common_name] = common
common_spec.loader.exec_module(common)

reproduction_name = 'experiments.m5e2e_v1.reproduction'
reproduction_spec = importlib.util.spec_from_file_location(
    reproduction_name, PACKAGE / 'reproduction.py')
reproduction = importlib.util.module_from_spec(reproduction_spec)
sys.modules[reproduction_name] = reproduction
reproduction_spec.loader.exec_module(reproduction)

CANONICALIZATION_SCHEMA = reproduction.CANONICALIZATION_SCHEMA
_value = reproduction._value
canonical_parquet = reproduction.canonical_parquet
canonical = common.canonical


def test_canonicalization_schema_is_versioned():
    assert CANONICALIZATION_SCHEMA == 'hiroute.report_canonicalization.v2'


def test_empty_and_non_utf8_bytes_use_exact_hex_tag():
    assert _value(b'') == {'binary_bytes_hex': ''}
    assert _value(b'\x00\xff') == {'binary_bytes_hex': '00ff'}


def test_native_mapping_cannot_collide_with_generated_byte_tag():
    native = {'binary_bytes_hex': '00ff'}
    assert _value(native) == {'mapping': native}
    assert _value(b'\x00\xff') != _value(native)


def test_tuple_is_tagged_separately_from_list():
    assert _value((b'\x80',)) == {'tuple': [{'binary_bytes_hex': '80'}]}
    assert _value([b'\x80']) == [{'binary_bytes_hex': '80'}]
    assert _value((b'\x80',)) != _value([b'\x80'])


def test_geometry_wkb_parquet_hash_is_stable_and_byte_sensitive(tmp_path):
    first = tmp_path / 'first.parquet'
    same = tmp_path / 'same.parquet'
    different = tmp_path / 'different.parquet'
    pq.write_table(pa.table({'geometry_wkb': [b'\x01\x00\xff']}), first)
    pq.write_table(pa.table({'geometry_wkb': [b'\x01\x00\xff']}), same)
    pq.write_table(pa.table({'geometry_wkb': [b'\x01\x00\xfe']}), different)

    first_hash = canonical_parquet(first)
    assert first_hash == canonical_parquet(same)
    assert first_hash != canonical_parquet(different)
    assert hashlib.sha256(canonical(_value(b'\x01\x00\xff'))).digest() != \
        hashlib.sha256(canonical(_value(b'\x01\x00\xfe'))).digest()

def _slots(missing=(), differing=()):
    rows = []
    for case_id in ('E01', 'E02', 'E03'):
        for method in ('REF', 'FLAT', 'HIER'):
            key = (case_id, method)
            if key in missing:
                rows.append({'case_id': case_id, 'method': method,
                             'operation_status': 'TIMEOUT'})
            else:
                value = 2 if key in differing else 1
                rows.append({'case_id': case_id, 'method': method,
                             'operation_status': 'SUCCESS',
                             'outcome': {'charge': value}})
    return rows


def _preflight(executable, source_path):
    return ({'environment': {'executable': executable},
             'installation': {'source': 'same', 'deps': 'same'},
             'source': {'path': source_path}},
            {'nodes': 'same', 'edges': 'same', 'cases': []},
            _slots(missing={('E02', 'REF'), ('E03', 'REF')}))

def test_timeouts_are_incomplete_when_shared_successful_results_match(tmp_path, monkeypatch):
    a = tmp_path / 'run-a'
    b = tmp_path / 'run-b'
    a.mkdir()
    b.mkdir()
    snapshots = {a.resolve(): _preflight('/env/a/bin/python', '/src/a'),
                 b.resolve(): _preflight('/env/b/bin/python', '/src/b')}
    monkeypatch.setattr(reproduction, '_snapshot', lambda path: snapshots[path.resolve()])

    result = reproduction.compare_builds(a, b)
    assert result['status'] == 'INCOMPLETE'
    assert result['model_equal'] is True
    assert result['mathematical_outcomes_equal'] is True
    assert result['complete_mathematical_results'] is False
    assert result['comparable_successful_result_count'] == 7


def test_conflicting_completed_outcome_is_correctness_failure(tmp_path, monkeypatch):
    a = tmp_path / 'run-a'
    b = tmp_path / 'run-b'
    a.mkdir()
    b.mkdir()
    pa, ma, oa = _preflight('/env/a/bin/python', '/src/a')
    pb, mb, ob = _preflight('/env/b/bin/python', '/src/b')
    oa = _slots()
    ob = _slots(differing={('E01', 'REF')})
    snapshots = {a.resolve(): (pa, ma, oa), b.resolve(): (pb, mb, ob)}
    monkeypatch.setattr(reproduction, '_snapshot', lambda path: snapshots[path.resolve()])

    result = reproduction.compare_builds(a, b)
    assert result['status'] == 'CORRECTNESS_FAILED'
    assert result['model_equal'] is True
    assert result['mathematical_outcomes_equal'] is False
    assert result['complete_mathematical_results'] is True
    assert result['outcome_conflicts'][0]['case_id'] == 'E01'


def test_model_difference_remains_reproduction_mismatch(tmp_path, monkeypatch):
    a = tmp_path / 'run-a'
    b = tmp_path / 'run-b'
    a.mkdir()
    b.mkdir()
    pa, ma, oa = _preflight('/env/a/bin/python', '/src/a')
    pb, mb, ob = _preflight('/env/b/bin/python', '/src/b')
    mb = {'nodes': 'different', 'edges': 'same', 'cases': []}
    snapshots = {a.resolve(): (pa, ma, oa), b.resolve(): (pb, mb, ob)}
    monkeypatch.setattr(reproduction, '_snapshot', lambda path: snapshots[path.resolve()])

    result = reproduction.compare_builds(a, b)
    assert result['status'] == 'REPRODUCTION_MISMATCH'
    assert result['model_equal'] is False
