# Time-cut v2 foundation checks

This directory supports the [foundation report](../../docs/MILESTONE_5_TIME_CUT_FOUNDATION_REPORT_V2.md) and [versioned contract](../../docs/MILESTONE_5_TIME_CUT_CONTRACT_V2.md). It is not a production solver.

From the repository root, using the project's Python 3.11 environment:

```sh
# New probes need only the standard library; no road datasets required.
PYTHONPATH=src python -m unittest discover -s tests -p test_time_cut_v2.py -v

# Held-out exact checks, seed 63119, independently authored.
PYTHONPATH=src python experiments/time_cut_v2/independent_review_checks.py

# If repository pytest dependencies are installed:
python -m pytest tests/test_time_cut_v2.py -q

# Historical v1 contract probe still has its ordinary ALG-4 failure.
python -m pytest results/milestone_5_b21_v1/test_closure_contract.py -q
```

The archived XML/outputs are the actual 2026-10-06 Python 3.12.14 runs. The project-declared Python 3.11 environment and full historical data/tool acceptance remain to be validated. The expected old v1 failure is evidence of that frozen contract's defect, not an xfail or a new acceptance criterion.
