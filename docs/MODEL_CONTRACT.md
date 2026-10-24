# Model Contract Source Map

This is an R0 source map, not a replacement mathematical specification. Migration must preserve accepted time-cut v2 semantics without promoting conditional theory to production acceptance.

## Sources at `c33f621f080eea500dfc9ca32b79e23aa9ae9c6a`

- `docs/MILESTONE_5_TIME_CUT_CONTRACT_V2.md`: bounded contract; distinguishes infima from attained executable values and excludes full production propagation/solver acceptance.
- `docs/MILESTONE_5_TIME_CUT_PWA_DESIGN_V2.md`: proposed PWA API and design constraints conditional on H1–H8; not proof of a complete accepted production implementation.
- `docs/MILESTONE_5_TIME_CUT_THEORY_REVIEW_V2.md`: conditional proof and hypotheses. It preserves strict positive charge, same-state/same-energy/same-depth comparison scope, sequential attainment and witness restrictions.
- `docs/MILESTONE_5_V_R12_FINAL_ACCEPTANCE.md`: scoped M5-V acceptance with explicit historical boundaries and missing artifacts.

## Semantics to map into public objects

The C01–C24 fixture-to-expected-result mapping must be completed against the taskbook and source documents before implementation. The source map identifies these obligations:

- Complete key `K=(J,Q,H,Pi)` and full tuple tie policy.
- Continuous charge and strict `q > 0`; C/S/CS, time windows and parallel makespan.
- Frozen selected-fastest-route time, length and tie policy; exact numerical input interpretation.
- Separate attainment of primary and secondary objectives; undefined coordinates remain undefined.
- Same `(v,E,r,k)` comparison scope and inherited-family witness lifting.
- Exactness limited to the declared candidate, road and depth domain; no implicit truncation or new pruning.

## Open audit

Map each active operator and its conformance coverage; identify the original 76 kWh fixture; inventory refuted B21-v0/v1 rules as failure context; and complete C01–C24 mapping before R1.
