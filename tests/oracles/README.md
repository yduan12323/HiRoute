# Historical differential oracle

The six modules under `timecut5` were copied unchanged from snapshot `679239d`.
They provide the minimal import closure used by exact-pipeline and terminal
differential tests. They are not distributed with `hiroute`. Future source
changes are validated by behavior, not a source digest or file-count gate.

The original historical package remains in `src/timecut5` while its archived
callers and unavailable input chains are being resolved; it is outside the
default CI and the production wheel. Do not delete historical inputs or receipts.
