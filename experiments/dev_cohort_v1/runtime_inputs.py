"""Hash-only publication bindings; generated pools stay in runtime input storage.

No import-time data reads, automatic downloads, or source-tree data caches.
Canonical digests retain ordering, unlike the separate sorted candidate digest.
"""
from pathlib import Path

from experiments.mechanism_recovery_v1 import run as base


def compact_binding(binding):
    """Commit an actual generated binding without publishing its candidate array."""
    value = dict(binding)
    value['candidate_site_ids_sha256'] = base.digest(value.pop('candidate_site_ids'))
    return value


def ordered_candidates_match(sites, spec):
    return base.digest(list(sites)) == spec['original_binding']['candidate_site_ids_sha256']


def require_prefix(prefix, spec):
    if (len(prefix) != spec['candidate_count'] or
            base.digest(prefix) != spec['original_pool_prefix_sha256'] or
            not ordered_candidates_match((site['site_id'] for site in prefix), spec)):
        raise ValueError('Original ordered generated pool prefix differs from published commitment')


def require_generated_inputs(directory, names):
    """Fail with actionable setup instructions before any experiment preparation."""
    missing = [name for name in names if not (Path(directory) / name).is_file()]
    if missing:
        raise FileNotFoundError(
            'Missing generated experiment inputs: ' + ', '.join(missing) +
            '. Generate or restore the exact hash-bound inputs in an external input directory '
            'and pass that directory to the experiment. See docs/REPRODUCING.md. '
            'Source checkout contains recipes and hashes, not generated pools; '
            'no synthetic fallback or implicit download is performed.')
