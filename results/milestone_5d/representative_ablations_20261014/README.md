# Representative synthetic ablation evidence

This is a separate, bounded supplement to the historical 192-row main matrix.
It does not replace failed rows, establish production performance, or close M5-D.

## Results and limitations

- 64 correctness cells cover eight predefined semantic cases, two methods, and
  four reduction/coalescing configurations. All matched frozen independent
  expected outcomes; attained witnesses were physically replayed.
- 192 fresh-process timing rows repeat those cells three times. These tiny
  timings are descriptive. The solver timer includes Problem construction and
  routing; it is not a pure propagation timer. No new REF solve was performed.
- 36 exploratory cold/warm rows used a synthetic four-node Python router.
  Independent review occurred after that batch; the sequence deviation remains
  disclosed in PLAN.md. A separate, prospectively reviewed 36-row confirmation
  followed the same frozen protocol and passed.
- Nine confirmation groups retained equal initial incumbent/depth/policies and
  equal full terminal keys. Cold selected-leg source calls were 3/7/1 for the
  three fixtures; warm calls were zero. This demonstrates fixture cache reuse,
  not a long-haul runtime benefit.
- Additional verified tightening and production table-free coalescing remain
  unsupported. The fixed 24-row production supplement is a different experiment
  and is not completed by these synthetic cells.

## Preserved evidence

DELIVERY_MANIFEST.json is the original reviewed delivery manifest, SHA-256
3d98871f656f283acbf59f2dcf559236b83abffd718e451762121210b176c8a1.
Its listed files remain byte-identical. Frozen plans contain historical stage
statuses; consult the result summaries and PLAN.md completion notes for outcomes.

The initial correctness harness attempt recorded eight passes and 56 reporting
serialization failures. All 64 identities are preserved in
attempt1_serialization_failure/CORRECTNESS_RESULTS.public.jsonl. Only private-path
tracebacks were replaced by digest and explanatory text; PROJECTION.json binds
the original raw records. This repaired attempt is separate from the final
64-cell correctness denominator and is not a set of solver failures.

The confirmation ledger's review_path and output_paths are original relative
workspace labels, not live repository paths. REVIEW.md and
CONFIRMATION_ACCEPTANCE.md preserve the associated review records. No earlier
records are retroactively marked prospectively approved.

## Source reconstruction without duplicated runtime code

SOURCE_MAP.json maps every omitted runtime module and fixture to immutable
repository commit 1a6bd82b4b96df04c6e849525cdb30f39ba79d55, its Git blob SHA, and
the exact experiment SHA-256. Extract each repository_path with git show from
that commit into its workspace_path in a separate working copy of this evidence
folder. Apply only the specified append_lf_bytes transformation, then verify
workspace_sha256. Three imported text files had one extra trailing LF in the
experiment; that provenance difference is explicit and must not be silently
normalized. Apply the same source map inside confirmation_20261014T040625Z.

The original runners, analyzers, plans and results are included without source
rewrites. Their result-overwrite guards are intentional. For a genuinely new
run, use a new experiment directory and identity, preserve the old artifacts,
and account for the new run separately. Do not rerun against current HEAD while
claiming the pinned experiment identity. Source-map reconstruction is a recipe;
no new numerical experiment was run while packaging this evidence.
