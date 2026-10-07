# Complete parallel replay of an existing recorded capture

This opt-in runner consumes the original completed capture. It does not rerun
search or numerical suffix optimization. The serial replay remains the reference.
The four scalar workers use `interval-sweep-v1`; the coordinator uses the reviewed
bounded `v3-cached` exact node oracle. Every node, physical transition, ordered
invocation, compact occurrence, Region query, supplied callback and terminal
witness retains the existing checker obligation.

## Two source plans and one immutable physical population

`recorded_real.replay_plan` reads the original plan through an exact bounded-byte
hash check, verifies its committed historical source manifest and input/export
chain, and writes a new plan without changing the original. Only `source_commit`,
`source_files` and `source_sha256` may differ. The entire remaining plan, including
query, inputs, reference status, representation and existing profile values,
must compare canonically equal. Current-plan admission retains the fixed C01,
H4, eight-Site and original 2,047-Region checks.

The new runner additionally requires the original capture's separately pinned
resource report, final decision, artifact manifest and observed successful
launcher return. The existing `prior_capture` verifier checks all these and the
complete original output coverage before the workers start. The bytes actually
decoded for replay are hashed against that authenticated capture commitment.
No historical result is used as an incumbent. An absent historical reference
remains `pending_missing_historical_reference` after structural replay.

## Execution and evidence

Use the existing `batch-replay-v1` profile: one 16 GiB-AS coordinator, four fresh
1 GiB-AS children, sampled 20 GiB group RSS, 16 GiB available-host reserve,
20 GiB disk floor, eight GiB charged evidence and 1,800 seconds from launcher
entry. The six CPU IDs must be distinct: one supervisor and an ordered list of
five worker CPUs. All four scalar children start with the full inherited mask
before capture decoding; the coordinator then narrows to the first worker CPU.
There is no whole-registry copy in a scalar worker and at most four jobs in flight.

The existing complete `domain.replay` supplies the trace, receipt and query
outputs. The runner injects only the batch executor and reviewed node memo.
The complete identity-keyed selection ledger is published before the family
validator returns, hence before the structural summary. Original expected IDs,
job hashes, kernel identity, certificate hashes and EOF joins are mandatory.
The parallel summary binds that ledger and the existing structural, callback and
query artifacts to both plans. Exact output coverage and current source/input
pins are rechecked before final publication. The runtime's observed successful
return must still be retained and pinned; files alone do not establish success.

Stage markers before/after family validation distinguish this phase from ordered
trace work. Failure may preserve a partial batch ledger, when the evidence writer
still permits it. Such partial bytes never constitute a completed replay. A cap,
worker failure, missing result or timeout remains incomplete. No limit is raised
automatically. Structural verification does not close literal G8 or its numerical
suffix proof gate.

## Commands after reviewed-source publication

Run the focused tests before any separately admitted real run:

```sh
PYTHONPATH=src:tests python -B -m unittest -q test_parallel_replay_plan test_complete_parallel_replay
PYTHONPATH=src:tests python -B -OO -m unittest -q test_parallel_replay_plan test_complete_parallel_replay
```

Prepare a fresh source plan from the preserved original, without starting replay:

```sh
python -B -m experiments.time_cut_v2.recorded_real.replay_plan \
  --historical-plan "$ORIGINAL_PLAN" --historical-plan-sha "$ORIGINAL_PLAN_SHA" \
  --output "$CURRENT_PLAN"
```

Pin the returned plan SHA. The separately admitted launch uses the original
capture receipt paths and hashes; use a fresh attempt directory and retain the
launcher's exact successful JSON return outside that directory:

```sh
python -B -m experiments.time_cut_v2.recorded_real.parallel_replay \
  --plan "$CURRENT_PLAN" --plan-sha "$CURRENT_PLAN_SHA" \
  --historical-plan "$ORIGINAL_PLAN" --historical-plan-sha "$ORIGINAL_PLAN_SHA" \
  --capture-attempt "$CAPTURE_ATTEMPT" \
  --capture-manifest-sha "$CAPTURE_MANIFEST_SHA" \
  --capture-result-sha "$CAPTURE_RESULT_SHA" \
  --capture-decision-sha "$CAPTURE_DECISION_SHA" \
  --capture-return "$CAPTURE_RETURN" --capture-return-sha "$CAPTURE_RETURN_SHA" \
  --cpu 0 --worker-cpus 1 2 3 4 5 --attempt-dir "$FRESH_REPLAY_ATTEMPT"
```

These commands are reproducibility instructions, not execution authorization.
Tiny tests compare all five immutable real mocks in both dominance modes against
serial replay, including exact callback-receipt and query-index bytes, complete
summaries apart from elapsed time, malformed inputs and incomplete joins. A fresh
producer-blocked process checks the four-child protocol and complete output set.
No full real capture was used in those tests.
