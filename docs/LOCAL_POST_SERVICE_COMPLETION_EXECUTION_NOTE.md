# Separate 600-second treatment-only diagnostic

This is an unpublished local continuation after the d7a38c02 240-second pair.
The prior pair's timeouts and first-layer observations remain unchanged in its
report. This new run asks whether the fixed treatment can complete with a
separately declared 600-second exact phase; it is not a matched performance
comparison and cannot retroactively satisfy the earlier 240-second budget.

Original OD02 N128 / Hmax33, HIER, analytic C ON, post-service reduction ON and
all other controls remain fixed. Only the experiment lifecycle and budget are
new. Three slots are declared: preparation, search, fresh full-routing replay.
The search worker has 900-second CPU/wall caps and the same per-process 8 GiB
address-space limit. No automatic retry or holdout is enabled.

The 95 production src entries match d7a38c02 exactly. Only generated metadata
under src/hiroute.egg-info/ is excluded from that algorithm equality assertion;
the full execution closure still binds every present source/metadata entry.
The separate optional convex-count runtime is not present or imported here.
Prior core installed-wheel evidence is reused only through unchanged production
bytes; the new final gate is separately tested against that installed source.

The manifest records the new exact local commit and source closure. Public
publication remains independently pending, with no main merge or claim of
whole-project completion.
