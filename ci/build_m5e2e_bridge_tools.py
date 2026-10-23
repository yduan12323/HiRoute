"""Build an isolated bridge wheel plus an editable namespace overlay for the pinned source tree."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
WRAPPER_FILES = ("m5e2e_original_bridge.py", "m5e2e_original_bridge_worker.py")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path,
                        help="the exact trusted M6 source checkout named by the recovery configuration")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if not args.source_root.is_absolute() or args.source_root.is_symlink():
        raise ValueError("trusted source root must be absolute and not a symlink")
    source_root = args.source_root.resolve(strict=True)
    if not source_root.is_dir() or source_root == ROOT.resolve():
        raise ValueError("trusted source root must be a separate directory from the bridge checkout")
    bridge_revision = git(ROOT, "rev-parse", "HEAD")
    source_revision = git(source_root, "rev-parse", "HEAD")
    if git(ROOT, "status", "--porcelain") or git(source_root, "status", "--porcelain"):
        raise ValueError("bridge and original source checkouts must both be clean")
    args.out = args.out.expanduser().resolve()
    args.out.mkdir(parents=True, exist_ok=False)
    overlay = args.out / "original-source-overlay"
    overlay.mkdir()
    setup_text = (
        "from setuptools import setup, find_namespace_packages\n"
        "from pathlib import Path\n"
        f"SOURCE_ROOT = Path({str(source_root)!r}).resolve(strict=True)\n"
        "packages = find_namespace_packages(where=str(SOURCE_ROOT), include=['experiments', 'experiments.*', 'validation', 'validation.*', 'scripts', 'scripts.*'])\n"
        "if not packages: raise RuntimeError('no experiments namespace packages found')\n"
        "setup(name='hiroute-original-m6-source-overlay', version='0.1.0', packages=packages, package_dir={'': str(SOURCE_ROOT)})\n"
    )
    (overlay / "setup.py").write_text(setup_text, encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="hiroute-bridge-wheel-") as temporary:
        stage = Path(temporary)
        package = stage / "ci"
        package.mkdir()
        (package / "__init__.py").write_text('"""Installed original-bridge tools."""\n', encoding="utf-8")
        for name in WRAPPER_FILES:
            shutil.copyfile(ROOT / "ci" / name, package / name)
        shutil.copyfile(ROOT / "ci" / Path(__file__).name, package / Path(__file__).name)
        identity = {
            "schema": "hiroute.m5e2e.original_bridge_wrapper.v2",
            "bridge_source_revision": bridge_revision,
            "original_source_revision": source_revision,
            "build_script_sha256": digest(__file__),
            "modules": {name: digest(package / name) for name in WRAPPER_FILES},
        }
        (package / "original_bridge_identity.json").write_text(
            json.dumps(identity, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        (stage / "setup.py").write_text(
            "from setuptools import setup\n"
            "setup(name='hiroute-m5e2e-original-bridge', version='0.1.0', packages=['ci'], package_data={'ci': ['original_bridge_identity.json', 'build_m5e2e_bridge_tools.py']})\n",
            encoding="utf-8")
        wheelhouse = args.out / "wheelhouse"
        wheelhouse.mkdir()
        subprocess.run([sys.executable, "-m", "build", "--wheel", "--no-isolation",
                        "--outdir", str(wheelhouse)], cwd=stage, check=True)
        wheels = sorted(wheelhouse.glob("*.whl"))
        if len(wheels) != 1:
            raise RuntimeError("expected exactly one bridge wheel")
        print(json.dumps({
            "schema": "hiroute.m5e2e.bridge_build_receipt.v1",
            "bridge_source_revision": bridge_revision,
            "original_source_revision": source_revision,
            "wrapper_identity": identity,
            "wheel": str(wheels[0]),
            "wheel_sha256": digest(wheels[0]),
            "source_overlay": str(overlay),
            "source_overlay_setup_sha256": digest(overlay / "setup.py"),
        }, sort_keys=True))


if __name__ == "__main__":
    main()
