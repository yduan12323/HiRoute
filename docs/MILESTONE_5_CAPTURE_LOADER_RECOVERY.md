# Immutable capture loader recovery

This code-only milestone restores the surviving standalone `capture5` candidate.
Its reader and tests are byte-identical to the recovered candidate, with SHA-256
`b39d12f2f480102fcdaf896b23d442dd1a01da8899e006a9e84d2115ff70219a`
and `ea32d4f0d459d95bb3e7f945621684ac0916b600cd398594936087108de244a6`.
It is not a restoration or acceptance of the missing full real checker pipeline.

`load_capture(path, expected_sha256, expected_size_bytes, limits=CaptureLimits())`
checks the entire original file and freezes its JSON values as immutable mappings
and tuples. Equal 64-character hexadecimal IDs share immutable strings; all
values, parent order, guards, events and callbacks remain present. The reader
retains no full encoded input string or second mutable document. Its diagnostics
are storage observations, not mathematical evidence.

Explicit resource limits fail with `CaptureResourceError`, never an infeasibility
result. Duplicate keys, nonfinite values, changed pins, truncated input, trailing
content and changed file identity reject. Source opening is nonblocking and does
not follow a final-component symlink; platforms without `O_NOFOLLOW` and
`O_NONBLOCK` are unsupported. Ancestor-directory symlinks are not prohibited.

Fresh Python 3.11.16 validation: 20 tests pass in normal, `-O`, and `-OO` modes,
with each complete test process capped at 512 MiB address space. Tests include
source races, FIFO rejection, Unicode/chunk boundaries and a 37,937,243-byte
structural specimen retaining 524,288 ordered parent occurrences. These synthetic
checks do not establish real-C01 peak memory, full physical replay or M5-V closure.

Reproduce from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 python -B -m unittest -q tests/test_capture5_reader.py
PYTHONDONTWRITEBYTECODE=1 python -B -OO -m unittest -q tests/test_capture5_reader.py
```

The published family/trace/suffix checkers and production operators are unchanged.
Further reconstructed adapters require new source review and reference-equivalence
checks before any real capture or replay run.
