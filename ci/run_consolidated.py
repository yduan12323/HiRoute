"""Installed-wheel test tiers, staged outside the repository without src on sys.path."""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
GROUPS = {
    'core': ['tests/r0/test_contracts.py', 'tests/r0/test_cli_supported_matrix.py',
             'tests/test_data_producer.py', 'tests/test_c_operator.py',
             'tests/test_exact_search.py', 'tests/test_real_scale_inputs.py', 'tests/test_scale_pilot_control.py',
             'tests/test_n64_coverage_stage.py', 'tests/test_r3_runtime.py', 'tests/test_r3_os_supervisor.py',
             'tests/consolidation/test_research.py'],
    'ref': ['tests/test_c_operator_ref.py', 'tests/r0/test_ref_supported_matrix.py', 'tests/test_semantic_fixes.py', 'tests/test_prefix_reuse.py',
            'tests/test_flat_bb.py', 'tests/test_scale_bounds.py', 'tests/test_scale_search.py',
            'tests/test_inbound_energy_bound.py', 'tests/test_enqueue_pruning.py', 'tests/test_pending_activity_screen.py'],
    'native': ['tests/test_scale_road_index.py', 'tests/test_source_tree_reuse.py', 'tests/test_shared_leg_pilot.py',
               'tests/consolidation/test_worker_installation.py'],
    'geo': ['tests/test_shandong_pbf.py', 'tests/test_shandong_spatial.py', 'tests/test_shandong_spatial_parallel.py',
            'tests/test_charging_coverage.py', 'tests/test_charging_coverage_extract.py'],
    'differential': ['tests/r2/test_exact_cut.py', 'tests/r2/test_interval.py', 'tests/r2/test_pwa_piece.py',
                     'tests/r2/test_strict_projection.py', 'tests/test_exact_pipeline.py', 'tests/test_exact_terminal.py',
                     'tests/test_exact_pwa_migrations.py', 'tests/test_exact_pwa_partition.py',
                     'tests/test_c09_new_kernel_path_parity.py'],
    'comparator': ['tests/test_exact_physical_adapter.py', 'tests/test_finite_leg_lookup.py',
                   'tests/test_exact_leg_table.py', 'tests/test_exact_road_certificate.py',
                   'tests/test_streaming_road_representation.py', 'tests/test_real_road_certificate_preflight.py',
                   'tests/test_dag_formula_export.py', 'tests/test_dag_audit_path.py', 'tests/test_cached_dag_audit.py',
                   'tests/test_incumbent_model_certificate.py', 'tests/test_folded_lookup.py',
                   'tests/test_strict_bound_decision.py', 'tests/test_strict_bound_witness.py',
                   'tests/test_strict_witness_integration.py', 'tests/test_import_strict_candidate.py',
                   'tests/test_candidate_finalization.py', 'tests/test_grounded_lookup_consumer.py',
                   'tests/comparison'],
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--group', choices=[*GROUPS, 'artifact'], required=True)
    parser.add_argument('--artifact-root', type=Path)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--record', type=Path, help='new JSON verification record')
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 11):
        raise RuntimeError('Python 3.11 is required')
    if args.group == 'artifact':
        if args.artifact_root is None or args.manifest is None:
            parser.error('artifact checks require --artifact-root and --manifest; no inferred archive')
        from hiroute.data.artifacts import read_json, verify_manifest
        result = verify_manifest(args.artifact_root, read_json(args.manifest))
        print(json.dumps(result, indent=2))
        return 0 if result['verified'] else 1
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',
               PYTHONNOUSERSITE='1', OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    env.pop('PYTHONPATH', None)
    if args.group == 'native':
        env['HIROUTE_REQUIRE_NATIVE_ROADS'] = '1'
    packages = ['hiroute']
    if args.group in {'ref', 'native'}:
        packages.append('hiroute_ref')
    if args.group == 'comparator':
        packages = ['hiroute_compare']
    with tempfile.TemporaryDirectory(prefix='hiroute-wheel-tests-') as directory:
        staged = Path(directory)
        for name in ('tests', 'configs', 'tools', 'docs'):
            shutil.copytree(ROOT / name, staged / name, ignore=shutil.ignore_patterns('__pycache__', 'conftest.py'))
        (staged / 'comparison').mkdir()
        shutil.copy2(ROOT / 'comparison/tiny_smt.py', staged / 'comparison/tiny_smt.py')
        shutil.copytree(ROOT / 'validation/reference5', staged / 'validation/reference5', ignore=shutil.ignore_patterns('__pycache__'))
        # No implementation checkout is staged. This is an interface check, not a fixed source manifest.
        script = "import importlib,pathlib; modules=" + repr(packages) + "; forbidden=" + repr(str(ROOT)) + "; "
        script += "\nfor name in modules:\n p=pathlib.Path(importlib.import_module(name).__file__).resolve(); print(name,p); assert not p.is_relative_to(forbidden) and 'site-packages' in str(p)\n"
        subprocess.run([sys.executable, '-B', '-c', script], cwd=staged, env=env, check=True)
        runs = []
        for mode in ([], ['-OO']):
            log = staged / ('optimized.log' if mode else 'normal.log')
            with log.open('w') as stream:
                result = subprocess.run([sys.executable, '-B', *mode, '-m', 'pytest', '-p', 'no:cacheprovider',
                    '-q', '--tb=short', *GROUPS[args.group]], cwd=staged, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=180)
            output = log.read_text()
            print(output, end='')
            runs.append(dict(mode='-OO' if mode else 'normal', returncode=result.returncode, output=output))
            if result.returncode:
                break
    record = dict(group=args.group, python=sys.version, runs=runs,
                  dependencies={d.metadata['Name']: d.version for d in importlib.metadata.distributions()})
    if args.record:
        with args.record.open('x') as stream:
            json.dump(record, stream, indent=2)
    return 0 if len(runs) == 2 and all(r['returncode'] == 0 for r in runs) else 1


if __name__ == '__main__':
    raise SystemExit(main())
