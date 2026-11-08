# Separate verification final acceptance

The historical outside-source consumer rejected tuple/list-equivalent content after JSON round trip. Both historical UNKNOWN runs remain unchanged. Future runs use version-controlled run_separate_candidate_verification.py and finalize_candidate_verification.py.

Canonical sorted compact JSON with allow_nan=false compares in-memory and persisted content and binds payload hashes. Matching serialization alone is not acceptance: required fields, outcome restrictions, original/new source and input provenance, table/physics/upper identities, exact physical replay, strict improvement, raw-path checks and final immutable input/source checks must all succeed. Only then is COMPLETE returned, with another deadline check. The caller must still publish its successful terminal under the original external guards. An isolated witness file cannot establish acceptance or change the earlier UNKNOWN.

Development tests are solver-free and use tiny synthetic inputs only. They cover tuple/list round trips, missing fields, hash and semantic tampering, stale provenance, deadline failures and raw-path failure. No historical candidate is evaluated in this stage.
