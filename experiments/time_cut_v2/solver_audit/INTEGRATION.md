# Independent solver audit integration

The files in this directory are copied unchanged from the independent audit's
final snapshot. `REPORT.md` and `final_revision_summary.json` state the tested
source hashes and exact scope. Historical absolute workspace paths in its
scripts identify the original run, not required installation locations.

The six targeted fixtures are also executable permanent regressions in
`tests/test_time_cut_hierarchy_v2.py`, including own-search versus explicitly
supplied verified incumbents, both dominance modes, and global primary/secondary
nonattainment. Run them portably from the repository root:

```sh
PYTHONPATH=src python -m unittest discover -s tests -p test_time_cut_hierarchy_v2.py -v
```

To reproduce the 100-case independent audit in a different checkout, point the
copied script's `ROOT` at this directory, `PROD` at that checkout's
`src/timecut5`, and `REF` at its `validation/reference5`; use a fresh output
directory/file because the script deliberately refuses to overwrite its result
JSONL. Add the checkout and its `src` to `PYTHONPATH`. The shared physical
fixtures are already frozen here, and all expected outcomes come from the
independent REF rather than production propagation.

The audit identified and rechecked three fixes: destination-stop semantics,
witness stop-bound enforcement, and rejection of consecutive-drive route
shaping in an incumbent. These are post-discovery regressions, not holdout
performance or full real-network acceptance.
