# M5-E2E A/B result and accounting addendum — 2026-10-23

## Acceptance and source identities

- Numeric source evaluated by both runs: `966912f7f552816bf2cf810fe24b624a8dcf1342`.
- Report-only source used to produce the acceptances: `04cb5fcacb86edca552b3f2cb9e58783b728bdf2`, canonicalization schema `hiroute.report_canonicalization.v2`.
- A and B acceptance files each have 2,099 bytes and SHA256 `00eef126d1e276cdde6d47b264adc0beaa60e547776b6a61c91799e8d1092d45`.
- Both report `delivery_status=PARTIAL`, `clean_e2e_status=PARTIAL`, `original_shandong_ref_status=UNKNOWN`, bridge `NOT_RUN_DEPENDENCY`.
- Model hashes match: `b1b190b606a7b604abe12862b74d3d6f0edaea95a1516a08c09047bcb33b956d`. Seven paired successful outcomes agree with no conflicts. E02/REF and E03/REF timed out in both runs; overall reproduction is `INCOMPLETE`. Each run has seven successful and two timed-out method slots; no timeout was retried.
- E01 alone is certified: REF attained optimum and certified 6174/6174 regimes; independent graph replay and cold check are VERIFIED; one positive charge was observed.

## A/B installed packages

Both environments used Python 3.11.15 on Linux x86_64, numeric source `966912...`, the same 87 production modules, same dependency versions, and tools manifest SHA256 `f2e08eeb4eb1af812fcd6fdc346eba5a5de69d2a3e0645b67e8b62fe33c61451`.

| Distribution | Version | Wheel SHA256 A | Wheel SHA256 B | Installed RECORD SHA256 A | Installed RECORD SHA256 B |
|---|---:|---|---|---|---|
| `hiroute` | 0.1.0 | `23e140f0913302afbde676756bdcc78a43e729d3b9cd82900974f565dc50d909` | `d07226c88fbb41ad772865fa01e6e056ba532b20eb106b91dcc9cb30681bbf1e` | `d7ee995bb886531fd28312c2d3b08b73e4ddb472be7a020bb72c9d96213bff43` | `5f18364b81111c9c08c04d66d03eb7484817e6031ba818b8d473b6f2ad7f1f45` |
| `hiroute-e2e-tools` | 0.1.0 | `35b8d270b25e3ff853528a089b126acb0a0f36731f07b4b560c560e1e00890fa` | `4cff7b4be70e71a3d8534523cea1a80f81b542239dfe6d1c8c86be00518c8be5` | `675f09fe4654caf3d1cf1c016681a443ef80e15fd44685cfb43c6f0ca5dc45c5` | `195951894e63ed3e9f50e8c4ca3e24a165dcf1c96e34c0edbeb058d0ecec70d7` |

Dependency names and versions match. Wheel hashes and installed RECORD hashes differ, but a comparison excluding `*.dist-info/RECORD` found identical wheel payloads: 90 core files and 373 tools files. Acceptance conservatively compares RECORDs byte-for-byte, so `installed_sources_and_dependencies_equal=false` and `environment_identity_ok=false` remain. This is packaging/RECORD identity uncertainty, not a model or paired-output conflict. Original records are preserved.

## Accounting correction

Global caps remain 28,800 CPU seconds and 43,200 external wall seconds; no budget was reset.

- `budget-repair-1` carry: 1,723.030921903 CPU / 14,144.361995148 wall seconds.
- Six conservative delta rows add 117 CPU / 1,840 wall seconds. The failed wrapper prepare adds 0.334404 measured CPU / 0.263243 measured wall seconds. The next epoch's carry is therefore 1,840.365325903 CPU / 15,984.625238190 wall seconds.
- `budget-continue-2` has 31 paired unique start/end IDs: one non-worker carry transfer and 30 measured worker invocations. Measured work totals 2,638.134405 CPU / 1,602.090951 wall seconds. Carry plus measured work equals 4,478.499730903 CPU / 17,586.716189 wall seconds. Carry is not worker execution; nested inclusive receipts are not added again.
- A previous report listed carry as 1,760.030921903 / 14,424.361995148. This differs from the repair manifest by 37 CPU / 280 wall seconds. No matching row was found in the retained ledgers/manifests. The discrepancy remains unresolved; do not treat it as reconciled.
- For a provisional master-budget view only, reserve that 37 CPU / 280 wall difference as an extra conservative charge (not measured work and not written into either original ledger). With known post-snapshot work deducted, the provisional remaining upper bound is 23,583.775982 CPU / 24,630.660349 wall seconds before subtracting unknown costs.
- The outer-accounting remaining snapshot 24,303.465982 CPU / 25,588.210349 wall seconds predates report-v2 work. Known measured work after that snapshot: focused test invocations 6.37 / 2.63; B report-wheel build 0.71 / 0.72; successful A+B summary scans 675.61 / 674.20 CPU/wall seconds. A report-wheel build and package installation costs are unknown. The failed A+B summaries (30.94 / 33.10) were already present in the snapshot's event list. Therefore remaining is at most 23,620.775982 CPU / 24,910.660349 wall seconds before subtracting unknown costs. Original ledgers were not edited.
- `budget-continue-2/phase_ledger.jsonl` SHA256: `ba453f3fcdc72ef5c5b8a0418164672dcaa0446210e74035d46d76140360645f`.

## Original Shandong bridge

Original Shandong binding remains UNKNOWN and bridge remains NOT_RUN_DEPENDENCY pending inspection of the approved historical checkpoint. The original 37 CPU / 280 wall discrepancy remains unresolved and reserved, not measured.
