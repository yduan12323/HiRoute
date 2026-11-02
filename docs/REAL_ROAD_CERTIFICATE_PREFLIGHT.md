# Complete frozen N64 road certificate preflight

## Bounded outcome

**NO-GO for the current JSON/Python-object graph loader on this host.** The
preflight completed once, with no resource termination, but did not release
source work. No road tree, selected-leg table or EV optimization was generated.
All **65 sources and 4225 directed pairs** remain explicitly
`unrun_preflight_blocked`; the whole table is uncertified. This is a memory/input
readiness result, not physical infeasibility or a solver timeout.

The actual producer is `415d8cddbc8fbb8c403bd6624af36364c436e04f`, based on
verified merged main `f67555cc8dbda9a90aa6f26841ef8390661f8aaf`. Later delivery
changes add an allocation regression and this report; the real scan was not
repeated. [Machine-readable evidence](real_road_certificate_preflight_results.json)
retains that distinction and hashes the external full raw result.

## Frozen denominator and inputs

The prospectively selected query is **WD01 / E18 / schedule / N64**, exactly the
single query proposed in PR44 before this admission. WD01 is the first original
query and E18 the lowest original energy; schedule preserves service actions.
Its DEV history was already known. This selection is not a new holdout,
performance-blind sample, candidate reduction or full-provincial optimum.

The domain digest is
`2a8f28645f781049a73619eb8222dd730261b58318d1f73f295edf08dad4dc64`.
The frozen manifest preserves all64 literal Sites/capabilities, original
endpoints and physical parameters. It has65 physical sources,65targets,
64alias-zero pairs and4225 directed pairs. The full union of source/target
anchors has66 nodes. No easier replacement query or Site was introduced.

Verified identities:

| Existing input | SHA256 |
| --- | --- |
| Full road TSV | `8076e850b096c5cf74f307ae7ad34c2aebd1f1e53c3c4d092234d40078a4c54d` |
| Site bindings | `c981bbf5d529f61e0385b4424b5145c44b6afd7dbb35b90fd625792b1e28bf42` |
| Site catalog | `a71e0a645fd21a2f415b4b079033cfe631dfb2292a1a41ce43b439304805a1a9` |
| Original E18 config | `062fc4fb50c6bb92d4a8827351e2cd9b41a29b6d5e679265453bd54fe9d0248f` |
| Original E18 domain manifest | `f05ab33291f3ed8889aad3be0fade330ad35bf82afa9b190e6ad3b1df0cc016a` |

The frozen full-domain artifact itself hashes to
`250ff5d84aed3e6fbf86e371f0cabbf135c4cc89034f9ce27fbc5f0bb411db7a`.
Config/manifest contents are joined back to the actual64-Site domain and
unchanged physical model, rather than trusting declared denominator fields.

## Observed input facts

The single streaming scan reads all530374281bytes and **5900232 edge rows**.
Every row has five fields, valid literal identifiers and positive exact integer
or numerator/denominator time and length. No float conversion, integer rounding,
zero-edge deletion, graph reduction or routing occurs. Every one of the66
required physical anchors appears in the graph endpoints.

Maximum numerator/denominator bit widths are78/84for time and75/77for length.
These are individual input components; they do not bound a global common
denominator, distances or accumulated integer sizes. A compact bridge cannot
silently substitute64-bit weights or binary64 arithmetic.

The complete file hash agrees with the frozen original input, so this was not
a corridor subgraph or prefix substituted for it. This scan does **not** count
distinct graph nodes, independently verify global edge-ID uniqueness, certify
the original extraction's real-world completeness, or establish shortest paths.
Those obligations remain open; no source work was released on the strength of
a schema flag or matching hash. Historical node counts are not promoted to new
observations.

## Current-loader memory obstruction

At admission the host reports4599775232available bytes. Retaining the original
2GiB headroom leaves **2452291584bytes** for additional residency, below the
nominal8GiB extra cap. Existing graph/index residency is not treated as free.

The current `ExactRoadGraph.from_bytes` decodes a whole JSON edge list, retains
its row dictionaries and value strings during construction, and creates an
ordinary `Edge` and two `Fraction` objects per edge. The64-bit CPython audit
uses these conservative disjoint live-storage units:

| Counted per edge | Bytes |
| --- | ---: |
| Five-field JSON row dictionary |184|
| Input list pointer slot |8|
| Edge object |56|
| Only five pointer-sized Edge dictionary values |40|
| Two Fraction object bodies |96|
| Three noninterned multi-character identity strings |49+character count each|

The string count is a lower bound even for wider Unicode representations.
Single-character values are omitted to avoid shared-string assumptions. The
audit explicitly supports only64-bit CPython and tests the current decoder's
multi-character value ownership. A1000-edge construction through the existing
loader additionally verifies that its traced allocation peak exceeds this
floor. That fixture is not a real graph load or RSS benchmark.

Summing the floor over all actual rows gives **3512791054bytes**, exceeding the
admitted2452291584bytes. This already omits raw JSON bytes, the node array,
numeric strings/integers, graph maps, adjacency, sorting, table paths, and every
source's labels/masks/certificate input. Those extra allocations cannot close
the gap. It is not necessary or safe to attempt the full object load to
demonstrate this obstruction.

This is a representation-specific storage lower bound compared with this run's
measured admission allowance. It is **not** a measured real-loader peak, an
implementation-independent memory impossibility, or proof that every compact
exact implementation fails. If a floor were below the allowance, this tool
would still return NO-GO until a safe complete compact bridge and upper peak
bound were established. It never grants source admission by itself.

## Cost, durability and verification

The admission was at most3600CPU seconds:240preflight,3120source work and
240independent upper-witness replay/cleanup. Only preflight was released. Its
full120development/controller/report precharge is retained, with a120metered
command envelope. Five completed commands charge **20.228686CPU seconds**,
rounded upward per command. Stage total is **140.228686/240preflight**, also
**140.228686/3600overall**. Unreleased source/replay work costs zero; prior
charges are not refunded. No historical feasible seed was consumed as a free
oracle or independently replayed in this blocked stage.

Cumulative conservative research charge is **16016.600202741/28800**, remaining
**12783.399797259**. Preprocessing stays652.040677976/900. Ordinary software CI
is separately reserved before invocation:9000capacity-CPU full M5 and120dedicated
stdlib CI. Those capacities are not measured whole-job CPU or research refunds.

The real scan reserves84CPU seconds with80CPU/120wall limits, one worker/thread,
1GiB preflight-process RSS,3GiB start and2GiB runtime host availability guards.
It completes with no guard or retry. Its body takes13.204434CPU/13.413496wall
seconds; the whole cold-worker/controller/tail charge rounds up to15.604983.
Sampled process-group peak RSS is31064064bytes, post-exit native peak31965184,
and minimum host availability4421124096. These are **streaming-scan** costs,
not current-loader, source-tree or solver measurements.

All five recorded worker PIDs are terminal, with no uncertain active command.
The before-launch domain, raw4225pair statuses, source statuses, incremental
scan progress, complete result, controller source, resource receipts and logs
remain outside Git in `real-road-certificate-artifacts-v1`. Bulk graph and old
datasets/results remain untouched. Twenty-four local regressions pass normally
and under-OO, including8new input/memory cases. Clean CI runs the same small
suite without a real input scan. Failed, missing or incomplete sources are not
silently removed from the denominator.

```sh
python tools/preflight_real_road_certificate.py \
  --frozen-domain /path/to/frozen-domain.json \
  --host-available-bytes <prospectively-measured-value> --output /fresh/preflight
python -m unittest discover -s tests -p 'test_*road_certificate*.py'
python -OO -m unittest discover -s tests -p 'test_*road_certificate*.py'
```

Real reproduction requires the declared external resource supervisor and budget
admission, not an unguarded shell run. Inspect started/PID/terminal receipts
after a disconnect; the once-completed scan must not be repeated for status.
Producer source is per-run provenance, not a source hash/file-count lock.

## Next safe action, not admitted

Stop real source construction. A bounded **<=900CPU-second representation-only
gate** would have higher value than another real routing attempt: design an
independent compact/streamed TSV graph and one-source certificate bridge, retain
the same Bellman/cut/DAG/canonical-path equations, and verify it first on tiny
adversarial graphs plus complete-width construction shapes. This changes input
representation, not the EV model, search architecture or objective.

Its memory plan must include graph/node/edge-ID storage, global uniqueness and
full endpoint validation, exact arbitrary-precision weights, all transient
parsing/sorting work, source labels/masks, output paths and independent checking.
It must establish a conservative peak upper bound under actual headroom, not
assume the nominal8GiB cap is available. Dense64-bit arithmetic or a smaller
graph is not a substitute. A memory-mapped/streamed authoritative edge input and
bounded source arrays are possible design directions, not measured solutions.

No real source generation, table certification, real EV comparison or holdout
belongs in that proposed gate. Re-admitting the same complete real table needs
the bridge/completeness proof and prospective costs first. The65source/4225pair
denominator and independent physical upper-witness verification remain required;
complete relevant depth cannot be inferred from an unverified historical key.
Overall taskbook completion and the original performance/research goals remain
unmet.
