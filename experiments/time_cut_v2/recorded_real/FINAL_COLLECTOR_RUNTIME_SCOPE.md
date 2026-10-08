# Final collector runtime scope

Source preparation only. `final-collector-v1` is a separate fixed profile for a
fresh family check followed by cold receipt, query, and selected witness
collection. It does not authorize a run, numerical LP children, publication, or
access to real archives. Root approval of exact source/input/plan hashes is still
required. CAPTURE, REPLAY, BATCH_REPLAY, and TINY_TEST limits remain unchanged.

The profile has a 3,600 s absolute entry-to-return deadline, 1 GiB total charged
evidence including a 16 MiB supervisor reserve, 16 GiB coordinator AS, 20 GiB
sampled worker-group RSS, a 16 GiB live host-memory floor, the existing 20 GiB
disk floor, and 512 MiB supervisor AS. Six explicit distinct CPUs cover one
supervisor, one coordinator, and four fresh family workers. The trusted
coordinator owns the latter partition and permits no numerical LP children.
The generic guard enforces process-group/resource bounds, not child semantics.
The existing per-UID group lock, conservative twice-payload accounting, cold
verification, final-decision checks, and separately retained actual successful
return requirements all remain in force.

`BoundedEvidenceWriter.write_from_callback(path, producer, expected_bytes=None)`
calls `producer(emit)` synchronously. Each immutable byte chunk enters the same
64 KiB framing, reservation, journal, partial-file, and atomic-publication path
as `write(iterable)`. No thread, spool, or full collection is introduced. A
producer may retain its own verifier result in a closure; its return value is
ignored. A sink is valid only during its producer call. A failed producer or
sink poisons completion even if the producer catches the sink exception;
reservations are never refunded and partials stay available. Nested callback
and generator writes preserve separate sinks, partials, and publication order.
Finalizing during an active write rejects completion. Calling a stale sink
rejects without appending any bytes, including after writer closure.

Validation uses synthetic callback streams, fabricated historical control
records, mocked group processes/resource readings, and a TINY_TEST callback
phase. No real final-collector group, LP solve, server operation, or archive
collection is part of these tests.
