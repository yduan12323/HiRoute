"""Supervised worker wrapper; activates only a fully validated recovery binding."""
import argparse
from ci.m5e2e_original_bridge import _verify_wrapper_identity
from experiments.m6h_manifest_v1 import recovery_runtime


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--configuration', required=True)
    p.add_argument('--configuration-sha256', required=True)
    p.add_argument('--manifest', required=True)
    p.add_argument('--manifest-sha256', required=True)
    p.add_argument('--common', required=True)
    p.add_argument('--common-sha256', required=True)
    p.add_argument('--wrapper-identity-sha256', required=True)
    a = p.parse_args(argv)
    if _verify_wrapper_identity() != a.wrapper_identity_sha256:
        raise RuntimeError('installed bridge wrapper identity changed after parent admission')
    recovery_runtime.activate({'path': a.configuration, 'sha256': a.configuration_sha256})
    # The existing worker and reference.run_reference repeat require_root_freeze.
    from experiments.m6h_manifest_v1 import reference
    reference.worker(a.manifest, a.manifest_sha256, 'N8', a.common, a.common_sha256)


if __name__ == '__main__':
    raise SystemExit(main())
