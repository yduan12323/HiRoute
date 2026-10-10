# C01 HIER D-off final collector acceptance

Accepted on 2026-10-09 UTC for **C01::HIER::D-off** on the frozen production source `3ad6e385903b631579df059b48d9ea6037728da7`. The collector reports `single_C01_case_accepted=true` and `single_C01_case_bound_valid=true`; its bound status is `satisfied`. This is one C01 identity. The receipts explicitly leave the full population, full C32, whole M5, and literal G8 incomplete.

The machine-readable [receipt capsule](MILESTONE_5_C01_D0_FINAL_COLLECTOR_RECEIPT.json) records the full command and environment, measured resources, evidence pins, and archive. The [D1 report](MILESTONE_5_C01_FINAL_COLLECTOR_REPORT.md) remains a separate source and identity.

## Source, population, and exact command

The production verifier remained at `3ad6e385903b631579df059b48d9ea6037728da7`, with 119-file source inventory SHA-256 `9b3f2a1b1c2a3b36533ea42e744b94e33f5929730ec7cfe11aa0f2e586caf5ad`. The D0 population freeze SHA-256 is `f2f5d282b226b69a686d694663089594b7db613436bd266cddea219d91f80b07`. The final reconciled registry is 105 entries, 3,299 complete blocks, and 844,440 unique logical models. Its SHA-256 is `171c5ecff4258cb72ee013c4d1cd441d814b4e35c4e50bc4aca733ca92a81abf`.

The approved launch plan SHA-256 is `3880a9bbc4529185a2209cd5a3fb0fedaf5fa4b2b92944e4d253bb067247c257`; canonical command argv SHA-256 is `54fed4c106716da35fe811d8830231b473e183d9fa5edaaa276890cd235df946`. The exact argv array is in the receipt capsule. It binds the historical and replay plans, capture, query index, logical return, source policy (`3de130328d7a488fd5551f67fae570a274b8003fa6b5fa0b92f04381559b2493`), and final registry/registration return (`12131f5373dba908bbe46d38cfe9765f7419104d45dd543c3eeecc8a05b5e715`). The final window runtime return SHA-256 is `9999de9a3b5d91d390aa5a60b8890ead0d30f339a4719530826d3cae1f147b9a`.

## Measured acceptance and resources

| Measure | Observed |
| --- | ---: |
| Original query events | 35,685 |
| Nonempty attained optima | 19,890 |
| Empty restricted families, counted as vacuous | 15,795 |
| Bound-valid queries | 35,685 |
| Missing bounds / bound counterexamples | 0 / 0 |
| Physical witnesses | 2,925 |
| Original model occurrences | 9,288,840 |
| Complete blocks / unique models / registry entries | 3,299 / 844,440 / 105 |
| Phase wall time | 1,408.2119749269914 seconds |
| Sampled worker group RSS peak | 4,173,930,496 bytes |
| Worker evidence charge | 418,267,942 bytes |

The run completed within its fixed 3,600-second deadline, 1 GiB evidence charge, 16 GiB coordinator address-space cap, and 20 GiB sampled group RSS cap. It used four family workers, supervisor CPU 0, workers on CPUs 1–5, and zero numerical solver calls. The runtime return reports worker exit 0 and all descendants reaped. The sampled group peak can double-count shared pages; it is a monitoring measure rather than exact aggregate resident memory.

## Evidence and independent verification

Server receipt stem: `/home/dy/HiRoute/project/results/milestone_5_recorded_remote/C01.HIER.D0.final_collector.001.3ad6e38`. The acceptance JSON SHA-256 is `c8222f32096e0d0968ae282e97ad70e9fd5341f6837ce28f88bf33e8112031d0`, runtime return `f372edff079dca82d500fff3e9a3eb1b4610644978cbbe2f6a8c82752b65098d`, controller return `4831c03228eaeb81d5994b8322efcaeba2a2e10a88fa0910b5835b6fb4703191`, and 11-file evidence manifest `65da492c5ebd5ea47c4129fbad5249a25b8f4fc74a6f4a2c8e911583acd17f62`.

Key evidence pins: summary `b3003eb739906a8370010936f010f8c355cca14a1e3ef7c4d85253640ef8e36b`; query rows `51a754618e670fc4724b45b6c5e3fc895128efa561659502c301542c2ccbab57`; physical witnesses `505e363358a392ad5aa2b760c2ad3460e2c01b6cacfc8b3d4da4524cac890493`; reconciled registry `171c5ecff4258cb72ee013c4d1cd441d814b4e35c4e50bc4aca733ca92a81abf`.

An independent read-only verifier checked every manifest member byte, streamed all 35,685 query rows and 2,925 physical witnesses, checked bound statuses and physical bindings, and confirmed the original processes had exited. The Mac evidence archive at `/Users/dy/Documents/Codex/2026-10-07/task/HiRoute-D0-archive-20261009-8818aa9/C01-HIER-D0-final-collector-3ad6e38-20261009T165839Z/C01.HIER.D0.final_collector.001.3ad6e38.closed-evidence.tar.gz` is 18,675,739 bytes, SHA-256 `69b013d4b21cb69dd53ca7a4617763561636056be1e541be68a90d37dc4e07be`. Its standalone manifest SHA-256 is `85ae4a6b31dede224a5c2ef9bd1638b1012eab8e60de201a82f728e8c2460083`; all 35 original files were checked against their source hashes. Server originals remain intact.

## Acceptance boundary

The successful C01 HIER D-off result cannot be transferred to another case, FLAT search, or literal inherited-family G8. The D1 result is separately accepted on source `052a157b745cdaee463579bf8478d1f78d44838b`. The [coverage audit](MILESTONE_5_V_COVERAGE_AUDIT.md) tracks the remaining original identity and gate obligations. No D0 models need to be rerun to establish this accepted C01 result.

## Full original-node domain audit (.001)

On 2026-10-10, isolated checker commit `6a91a6b18a858a10b5206cad17402db72d5972a8` completed one supervised, read-only audit at `/home/dy/HiRoute/g8_batch_d0_6a91a6b/g8-batch-full-d0.001`. The accepted historical C01-HIER-D0 numerical and physical evidence was reauthenticated; no LP model was rerun. The actual caller return was `completed` (SHA-256 `bdba8a00817963523037b46b77e636d838ffd81dedb404a43c7b6d151d8961c9`), all descendants were reaped, and an independent cold read verified the 43-file manifest (SHA-256 `301fce572a3cc9acc7fa737ab6d30ec8de3829ab0960e6156aa5af697eaf5fe9`).

The original-node domain check covered 19,890 nonempty queries, 15,795 empty-action events, 35,685 total query events, 844,440 unique logical models, 9,288,840 model occurrences and 3,299 blocks across 105 retained registry entries. The ordered domain SHA-256 is `5daba98afcc11c7864fa84148993a3f71119e8685a6dbab04966b6ea8a692990`. Fresh LP calls and newly rechecked numerical certificates were both zero. The domain report SHA-256 is `d7d72f677ed6a09e2f7a4c602277ee6fbd70d704d396c96be0da4e06f48ff006`.

Wall time was 2,659.02 seconds, peak sampled worker-group RSS 5,710,467,072 bytes, and charged evidence 2,577,334,424 bytes. This fit the separate fixed D0 profile: 3,600 seconds, 16 GiB child AS, 20 GiB sampled group RSS and 4 GiB total charged evidence including the supervisor reserve. The D1 profile remains 2 GiB. The exact D0 live plan SHA-256 was `5f16bdb23fcebfe49c02a90197eda5d929a092260829968fef0153d44ec45b97`; checker source inventory SHA-256 was `f47a4e248751f7593c2efafdb25cbac156243e42feda78fec856106a48c4635a`. The production verifier remained at `3ad6e385903b631579df059b48d9ea6037728da7`.

This closes the scoped C01-HIER-D0 original-node domain check using prior numerical and physical authority. The domain artifact records `supervisor_acceptance=false`; it does not promote this check to a new final collector acceptance. Literal inherited-family G8, C01 FLAT, other C32 identities and whole M5-V remain open. The Mac archive is `/Users/dy/Documents/Codex/2026-10-07/task/g8-batch-full-d0.002.success.tar.gz`, 43,888,420 bytes, SHA-256 `a458382f4b7bf3476b427c5d48572bf75f213b0f1c55ccc97ad287fda13d3cdb`; server originals remain intact.
