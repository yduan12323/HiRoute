"""Dedicated deterministic-fixture route; never an admission route for real data.

The normal physical/reference entrypoints remain hard-blocked. This module may
enter their implementation only after the source-owned generator independently
regenerates and authenticates the entire known synthetic fixture. A marker or a
caller-supplied hash is not sufficient provenance.
"""
import argparse
from contextlib import contextmanager
from pathlib import Path
import sys
import threading

from . import physical, physical_inputs, physical_queue_adapter

_LOCK = threading.RLock()


def _verify(binding):
    from .generation import verify_synthetic_fixture
    if type(binding) is not dict or set(binding) != {'path', 'sha256'}:
        raise ValueError('Exact synthetic manifest binding required')
    verify_synthetic_fixture(binding['path'], binding['sha256'])


@contextmanager
def _verified_scope(bindings):
    """Private, serialized, exception-safe admission of independently proved bytes."""
    if threading.current_thread() is not threading.main_thread() or threading.active_count()!=1:
        raise ValueError('Synthetic fixture admission requires a dedicated single-threaded process')
    with _LOCK:
        if not bindings:
            raise ValueError('No synthetic fixture bindings')
        for binding in bindings:
            _verify(binding)
        modules = (physical, physical_inputs, physical_queue_adapter)
        original = [module.require_root_freeze for module in modules]
        try:
            # Scope is entered only after deterministic verification. No public
            # flag or environment variable changes the real root freeze gate.
            for module in modules:
                module.require_root_freeze = lambda: None
            yield
        finally:
            for module, gate in zip(modules, original):
                module.require_root_freeze = gate


class SyntheticQueueAdapter(physical_queue_adapter.PhysicalQueueAdapter):
    """Same queue/worker/admission behavior, with fixture-only command dispatch."""
    def __init__(self, declaration, bindings, *, selection_binding):
        with _verified_scope(list(bindings.values())):
            super().__init__(declaration, bindings, selection_binding=selection_binding)

    def preflight(self, domain, context):
        with _verified_scope([self.bindings[domain['id']]]):
            return super().preflight(domain, context)

    def command(self, domain, row, context):
        with _verified_scope([self.bindings[domain['id']]]):
            command = super().command(domain, row, context)
        argv = command['argv']
        if argv[:2] != [sys.executable, '-m']:
            raise ValueError('Unexpected physical worker command')
        module = argv[2]
        if module == 'experiments.m6h_manifest_v1.reference':
            argv[3:3] = ['--worker', 'ref']
        elif module != 'experiments.m6h_manifest_v1.physical':
            raise ValueError('Unexpected physical worker module')
        argv[2] = 'experiments.m6h_manifest_v1.synthetic_worker'
        return command

    def admit(self, domain, row, context, receipt, directory):
        with _verified_scope([self.bindings[domain['id']]]):
            return super().admit(domain, row, context, receipt, directory)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', required=True, choices=('prepare', 'arm', 'verify', 'ref'))
    for name in ('manifest', 'manifest-sha256', 'case', 'strategy', 'common', 'common-sha256',
                 'search-directory', 'search-receipt-sha256'):
        parser.add_argument('--' + name, required=name in ('manifest', 'manifest-sha256', 'case'))
    args = parser.parse_args()
    binding = dict(path=args.manifest, sha256=args.manifest_sha256)
    with _verified_scope([binding]):
        if args.worker == 'ref':
            if args.strategy is not None or args.search_directory is not None or args.search_receipt_sha256 is not None:
                raise ValueError('REF fixture worker does not accept method/replay arguments')
            from . import reference
            reference.worker(args.manifest, args.manifest_sha256, args.case, args.common, args.common_sha256)
        else:
            physical.worker(args.worker, args.manifest, args.manifest_sha256, args.case,
                strategy=args.strategy, common_path=args.common, common_sha256=args.common_sha256,
                search_directory=args.search_directory, search_receipt_sha256=args.search_receipt_sha256)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
