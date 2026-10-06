These independent review files are copied byte-for-byte from the review
workspace. Source fingerprints in review_summary.json identify the tested
snapshot. The archived reproducers contain original workspace paths; point
those constants at the local checkout and independent REF checkout before
rerunning. Do not treat those paths as downloadable dependencies. Portable
unit regressions live under tests/test_real_solver_adapter.py,
tests/test_real_export_input.py and tests/test_time_cut_optimized_replay.py.
No actual real query optimization appears in these results.
