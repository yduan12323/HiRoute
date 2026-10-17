# OD02 recovery gate — 2026-10-17

Engineering gate: **completed**, five of five stages accounted for. This is one fixed OD02 case and one indexed/recompute pair, not the full experiment batch.

Source: [`d2474ec6795c7be67509a727517b3ad04b19b93e`](https://github.com/yduan12323/HiRoute/commit/d2474ec6795c7be67509a727517b3ad04b19b93e); [source CI passed](https://github.com/yduan12323/HiRoute/actions/runs/38999025954). Exact identities, inputs, costs and complete rational solution keys are in [results.json](results.json).

| Stage | Outcome | Worker wall seconds |
|---|---|---:|
| Common prepare | SUCCESS | 29.646561877 |
| Indexed search | TIMEOUT, external phase_timeout at 120 s search budget | 148.351523153 |
| Fresh indexed verification | SUCCESS | 16.391308827 |
| Recompute search | TIMEOUT, external phase_timeout at 120 s search budget | 148.368192422 |
| Fresh recompute verification | SUCCESS | 15.835792940 |

Both timeout incumbents independently replayed successfully, with identical complete lexicographic keys. The first key component improved **12.981068813%** over the common feasible seed. Both results are `timeout_feasible_only`, with `optimality_claim=false`. This establishes feasible improvement, **not optimality, index/ALT advantage, speedup, or a multi-case scientific conclusion**. End-to-end arm wall time includes setup beyond the 120-second search phase. Every stage reports verified cleanup.

Summed worker-stage wall time is **358.593379219 s**. Supervisor/parent CPU is **13.567987405 s**; it is not total worker CPU, which was not measured here. Memory limits are per-process virtual-address-space limits, with sampled process-tree RSS; there is no aggregate cgroup memory hard limit. See exact fields in results.json.

## Repair history and retained failures

The earlier v1 gate remains **UNKNOWN: 1 not admitted, 4 not run**, after its prepare control receipt exceeded 64 KiB; cleanup was verified. It is not relabeled as a pass or pooled with this v2 gate. An earlier 128 MiB source cache was too small to retain even one source; the repaired, manifest-bound policy is 1 GiB / at most 2 sources. These are repair diagnostics, not accepted experimental results. The v2 receipt repair stores large results as hash-bound artifacts and keeps control receipts compact.

## Evidence and replay boundaries

[evidence.json](evidence.json) records SHA-256 and byte size for the original frozen summary, receipts, ledger, prepared common artifact, search-entry bindings and witnesses. Original execution evidence remains retained separately; environment-specific paths and process identities are omitted from this publication. Hashes alone are provenance commitments, not substitutes for the underlying evidence.

[witness-00.json](witness-00.json) and [witness-01.json](witness-01.json) preserve the original hash-bound feasible witnesses. [verification.json](verification.json) is byte-identical for the two separate fresh verifier outputs. Replaying routing feasibility requires the hash-matching source, graph inputs and admitted common/manifest artifacts listed in the evidence; this compact report is not a standalone graph bundle. No graph was loaded for publication. Gate observations remain separate from any later full-batch run.
