# C01 HIER D0 infrastructure, first stage

This is code and tiny/mock regression coverage. It does not admit a real D0
capture, population, numerical result, or research milestone. The accepted
C01 HIER D1 result and its historical evidence remain separate.

The default recorded-real plan stays `hiroute-recorded-real-plan-v1`, with
exact boolean `dominance: true`. Preparing a plan with `--dominance off`
requires C01 and emits v2 with explicit `C01::HIER::D-off`. Both variants
retain H=4, eight sites, 2047 original regions, OD00 energy-only, no external
incumbent, and exact adjacent-cut coalescing. Capture and structural replay
use the existing D0-capable solver and checker. Renewing a source checkpoint
cannot turn a D1 capture into D0.

## Independent D0 population admission

`python -B -m experiments.time_cut_v2.recorded_real.population_bootstrap --help`
lists the metadata preparation inputs. Supply independently pinned original
and replay plans, capture, actual replay return and attempt, query index,
actual count return and attempt, count report, reviewed source policy, and a
fresh output path. Preparation launches no capture, worker, matrix or LP.
It authenticates successful retained replay/count returns and manifests,
requires the reviewed `parallel_replay` and `suffix_census` worker modules,
recomputes counts independently, and retains the complete input/proof graph.
Count admission also authenticates the actual request's entry/deadline against
the cold successful return, requires an at-most-180-second requested budget,
and binds the worker's single exact `--deadline` value to that request.
Duplicate, attached and abbreviated deadline options are rejected. The outer
REPLAY profile's 1800-second ceiling and a report describing 180 seconds do
not authorize a longer count request.
The initial bootstrap requires one reviewed source checkpoint shared by the
original plan, replay plan and count. Later windows may use subsequently
reviewed checkpoints without changing that population.

The first D0 window uses `suffix_window --bootstrap PATH --bootstrap-sha SHA`
alongside its usual common pinned inputs and reviewed source policy, with all
seed/registry options absent. Controller, fresh worker and cold receipt
admission each authenticate the bootstrap again. It supplies an empty typed
scheduling registry, with no completed numerical authority. The live worker
independently checks genuine families and compares the whole catalogue and
population commitment before constructing a matrix. Later windows use the
existing registered-ledger inputs. The historical D1 seed is forbidden for D0.

D0 freezes its own unique models, original query occurrences, nonempty/empty
query counts, block catalogue and replay anchors. A repaired outer JSON hash
cannot replace authenticated replay/count evidence. Registry and collector
admission bind the explicit variant and population freeze. Collector completion
requires all original canonical blocks and the entire original query partition;
the acceptance records carry the D0 identity. Literal G8 and global milestone
authority flags remain false.

## Compatibility and limits

D1 keeps its existing population constants (695712 unique models, 2718 blocks,
12172 nonempty and 9666 empty queries, 7652832 original model occurrences).
Its command/context serialization excludes absent new bootstrap options, and
its original seed and source-policy checks remain in place.

Existing execution limits are unchanged: 256 models per block, at most 32 blocks
or 8192 models per window, 900 seconds, 512 MiB charged evidence/archive limit,
four numerical workers with the existing AS/RSS/model ceilings, and the existing
host/disk reserves. Replay/count/capture/collector profiles are unchanged.
Bootstrap preparation retains the count phase's 2 GiB AS ceiling, cooperative
180-second deadline and a 32 MiB metadata cap; it is metadata preparation, not
a successful guarded-phase receipt. Outputs use exclusive publication and do
not replace historical files. Exceeding an input, resource or proof bound must
stop; it does not authorize raising caps or dropping query events.

Calibration, fixed preview/pilot, resume and recovery entrypoints remain scoped
to their existing D1 workflows. This stage does not add a CLI test mode, an
admission bypass, a numerical cache, or alternate Library materialization.

## Focused verification

The new unit modules are `tests.test_c01_variant_scope` and
`tests.test_c01_d0_bootstrap`; D0 collector protocol boundaries are also tested
in `tests.test_suffix_final_collector`. The D0 mathematical fixtures use genuine
tiny checked families and original query occurrences. Guard execution envelopes
are explicitly mocked and cannot be accepted by the unmocked runtime reader.
These tests establish code behavior, not production execution authority.

Run the selected modules and relevant existing D1 recorded-real regressions
under Linux Python 3.11, normal and `-OO`, with one-thread BLAS/OpenMP/MKL.
The existing installed-wheel CI remains its separate explicit 31-module
synthetic gate; it does not run these recorded-real orchestration modules.
