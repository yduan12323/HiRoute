# Frozen A28/B64 metadata intake

`timecut5.frozen_ab_registry` restores the exact original physical population as
metadata: 24 h4 inputs, 3 physical supplements, 1 merge supplement, and 64 B cases.
Every case retains its original case ID and integer `H_ref=4`; the registry emits
one HIER/D-off and one HIER/D-on identity for each, totaling 184 variants.

This is not a solver or a current acceptance result. No propagation, graph
construction, LP, witness replay, or population optimization runs. The recorded
capture wrapper was absent from the backup and remains to reconstruct. A04 is
algebra-only, not a 29th physical A case.

## Original source closure

Extract the recovered inputs at their original relative paths. The loader reads
only these six files and pins their raw-byte SHA256 identities in code:

| File under `results/` | SHA256 |
| --- | --- |
| `milestone_5_coalescing_prototype/frozen_A/physical_cases_h4.json` | `3d79795956e63cf5ada6ac4d73a49e5a70598169701447eda4b226d664b614f2` |
| `milestone_5_coalescing_prototype/frozen_A/physical_supplement.json` | `1b09f4895df68dd67e0362f88988c9f05c10e9bbf628ded24807bf577bc43a30` |
| `milestone_5_coalescing_prototype/frozen_A/physical_merge_supplement.json` | `121770eb0bef153d313dea7b02d7ab8156f846b3331cf896676a3cf72b5b6bd4` |
| `milestone_5_acceptance_b64/acceptance_populations/stage_b/cases.json` | `61a1d3f86da1c750ef127f7827f4ef68d2b5aa21babc314691ce095ed498f037` |
| `milestone_5_coalescing_prototype/frozen_A/FINAL_STAGE_A_RESULTS.json` | `163949bdf649412ecdd094b07de5ddbd8a436c7db4ca360851fe98d523de5c5c` |
| `milestone_5_acceptance_b64/acceptance_populations/evaluation_v2/B64_RESULTS.json` | `a45979a2a49909d61b25df46d35237120f85c46c8c266cf13b78c7ed627bb025` |

Historical comparison statuses/keys come from A `case_rows[*].key_or_infimum`
and B `cases[*].status/key`, matching the preserved old parity runner. The
embedded input `independent_expected` metadata is preserved separately and never
substituted for the historical final result. The old runner
`experiments/time_cut_v2/coalescing/run_frozen_differential.py` is historical
reference only (SHA256 `ca4c3205c5ea568891df2ee7c3994b9e58f30c8e59eaa143dcf70926769aef15`);
it is neither imported nor executed.

The recovered archive `HiRoute-frozen-AB92-inputs-a2c4a7f.zip` has SHA256
`7d001b1ce2ec83ac953b1891a93562e3b9060195e9dd5f5bcc6a9687b50e7679`.
It is an external input artifact; this code-only change adds no original case or
result files to the repository. The archive also contains historical references
that the loader does not need to read.

## Usage and verification

From the repository root on Linux with Python 3.11:

```sh
PYTHONPATH=src python -m timecut5.frozen_ab_registry --input-root /path/to/extracted/tree
HIROUTE_FROZEN_AB_ROOT=/path/to/extracted/tree PYTHONPATH=src python -m unittest discover -s tests -p test_frozen_ab_registry.py -v
```

Without `HIROUTE_FROZEN_AB_ROOT`, the tiny validator tests run and the two
original-population tests explicitly skip. Those tiny rows test malformed input,
duplicates, missing fields, type aliases, and file boundaries; they are not
replacement population cases.

Each file read is bounded to 1 MiB, requires a regular file, and refuses symlinks
at every absolute root ancestor and relative path component. The hash is computed on the
same bytes that are decoded. Duplicate JSON keys, nonfinite values (including
overflowing floats), wrong scalar types, boolean/integer aliases, missing or
duplicate cases, and mismatched historical identities fail closed. All source
bytes remain in immutable byte objects; `original_case()` returns a fresh parsed
copy without rewriting inputs. The historical expectations are recursively
immutable. Intake validates metadata shape and identity, not physical feasibility.

The original-population tests verify all 92 IDs against their input rows, exactly
184 distinct HIER variants, unchanged bytes, historical status totals of 72
attained / 18 infeasible / 1 primary-unattained / 1 secondary-unattained, and a
complete load in a fresh process with solver/optimizer imports forbidden.
