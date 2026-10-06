# Immutable real-leg adapter: infrastructure checkpoint

2026-10-06. Branch: `codex/m5-real-leg-contract`, based on delivered checkpoint `579c6db`. No push, PR, real graph load or Stage C optimization was performed.

## Delivered

- [Draft contract and API](MILESTONE_5_IMMUTABLE_REAL_LEG_CONTRACT.md).
- `src/timecut5/real_legs.py`: immutable, hash-bound real-leg loading; lossless binary64-to-rational conversion; separate Site/road-anchor identities; topology-preserving frozen Region restriction; deliberately weak non-metric action bounds; explicit declared-source verification.
- `tests/test_real_leg_contract.py`: 20 mocked regressions. The utility is not imported by the existing production or REF optimizers.
- `experiments/time_cut_v2/check_native_pair_contract.py`: a tiny calibration against the unchanged accepted native router, with no real input data.
- REF certificate recovery `d91c148` integrated as local commit `14d8ced`; its unchanged exact verifier still rejects invalid certificates. The ten recovery regressions pass.

## Validation

- Python 3.11 focused command: `python -m pytest tests/test_real_leg_contract.py tests/test_reference5_certificate_recovery.py -q`: **30 passed**.
- Independent review: **20/20 permanent mocks**, 500 binary64 trials, 1,800 C/S/CS weak-bound cases, and a read-only restriction of the actual frozen 2,047-Region tree passed.
- The review caught malformed-container acceptance (`effects: "CS"`, `anchors: "oxz"`) and duplicate JSON keys. All now reject, with permanent regressions. Tested source hashes and reproducible independent checks are preserved under `results/milestone_5_real_leg_contract/independent_review/`.
- Native calibration: **41 ordered pairs on two tiny graphs** match forward `full` results bit-for-bit for time and actual length. The finite cutoff is the maximum representable binary64 value, not a shortened query budget. The accepted compiler/flags and source hashes are recorded in `results/milestone_5_real_leg_contract/native_pair_mock_check.json`.
- A synthetic large-magnitude chain demonstrates different forward/reverse binary64 accumulation. Direction provenance is therefore mandatory; the forward-pair check does not establish reverse equivalence or real-data readiness.

## Safety boundaries retained

The loader never constructs a graph or reroutes a leg table. Equal-time alternatives do not replace its selected length. It preserves co-attached Site action identities and exact zero same-anchor movement. Destination terminality is checked by physical road anchor rather than Site text.

Topological reachability must be transitively consistent; numeric triangle inequalities are not assumed. The initial action bound adds only an exact immediate inbound minimum, proved mandatory overhead/service cost and next-stop penalty. Its onward travel lower bound is zero. An energy-infeasible direct destination leg does not delete a viable charging continuation.

Source-hash declarations and a verified payload hash establish identity, not selection validity or shortest-route certification. The source-verifier's `complete` result refers only to the explicitly declared source set. It is not permission to run a real acceptance suite.

## Still gated

- Verify the complete accepted real input set, including edges, and pass a graph/native-index memory preflight.
- Freeze candidate selection and routing direction/numeric policies; stream one source at a time and retain only needed pairs.
- On a small real subset, compare the accepted pair/full APIs before any compact export is used; never reduce cutoff or change tie rules to save memory.
- Add independently reviewed production and REF physical-query adapters, including co-location, witness provenance and exact actual-tree action coverage.
- Distinguish superset bound certificates from exact inherited-mask/node-constrained REF optimization.
- Complete the formal A20/B64/C32 and later real-hierarchy/deployment gates. These mocked utilities do not complete any of them.

The delivered `579c6db` branch and ZIP are unchanged. This is a separate infrastructure/recovery checkpoint.
