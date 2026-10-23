"""Build a separate source-bound tools wheel; never add validators to core wheel.

Invoke with the same locked build environment as ci/run_m5_code_only.py.
Only Python/native source is included: no experiment inputs, outputs or fixtures.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    source = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    modules = {}
    with tempfile.TemporaryDirectory(prefix='hiroute-tools-build-') as temporary:
        stage = Path(temporary)
        packages = set()
        for top in ('experiments', 'validation', 'scripts', 'ci'):
            for path in sorted((ROOT / top).rglob('*')):
                if not path.is_file() or path.suffix not in ('.py', '.cpp') and path.name not in ('installed.txt','requirements-hashed.txt'):
                    continue
                if path.name.startswith('test_') or '__pycache__' in path.parts:
                    continue
                if path.is_symlink():
                    raise ValueError('Source symlink not permitted: ' + str(path))
                relative = path.relative_to(ROOT)
                destination = stage / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, destination)
                modules[str(relative)] = hashlib.sha256(path.read_bytes()).hexdigest()
                parent = relative.parent
                while parent.parts:
                    packages.add('.'.join(parent.parts))
                    parent = parent.parent
        bridge_dir = stage / 'ci'
        bridge_dir.mkdir(parents=True, exist_ok=True)
        bridge_identity = {
            'schema': 'hiroute.m5e2e.original_bridge_wrapper.v1',
            'modules': {
                name: hashlib.sha256((bridge_dir / name).read_bytes()).hexdigest()
                for name in ('m5e2e_original_bridge.py', 'm5e2e_original_bridge_worker.py')
            },
        }
        (bridge_dir / 'original_bridge_identity.json').write_text(
            json.dumps(bridge_identity, sort_keys=True, separators=(',', ':')))

        # Existing NativeDomain imports the frozen DEV cohort metadata at import
        # time. Ship its exact source-bound resource, never processed map inputs.
        relative=Path('docs/dev_cohort_v1_bindings.json')
        (stage/relative).parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/relative,stage/relative)
        modules[str(relative)]=hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()
        packages.add('docs')
        for package in packages:
            init = stage.joinpath(*package.split('.'), '__init__.py')
            if not init.exists():
                init.write_text('"""Installed HiRoute validation tools namespace."""\n')
        (stage/'setup.py').write_text(
            'from setuptools import setup\nsetup(name="hiroute-e2e-tools", version="0.1.0", '
            'python_requires=">=3.11,<3.12", packages=' + repr(sorted(packages)) + ', '
            'package_data={"": ["*.cpp", "*.txt", "source_identity.json", "dev_cohort_v1_bindings.json"], '
            '"ci": ["original_bridge_identity.json"]})\n')
        production = {str(p.relative_to(ROOT/'src')):hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in sorted((ROOT/'src').rglob('*'))
                      if p.is_file() and p.suffix in ('.py','.cpp') and '__pycache__' not in p.parts
                      and p.relative_to(ROOT/'src').parts[0] in ('graph','envelope','opportunity','microplan','stopplan4r','hierarchy4r','timecut5')}
        dirty = bool(subprocess.check_output(['git','-C',str(ROOT),'status','--porcelain'],text=True).strip())
        identity = dict(production_modules=production, source_dirty=dirty, schema='hiroute.m5e2e.tools_source.v1', source_sha=source, modules=modules)
        (stage/'experiments/m5e2e_v1/source_identity.json').write_text(json.dumps(identity,sort_keys=True))
        subprocess.run([sys.executable, '-m', 'build', '--wheel', '--no-isolation',
                        '--outdir', str(args.out.resolve())], cwd=stage, check=True)
    print(json.dumps(identity, sort_keys=True))


if __name__ == '__main__':
    main()
