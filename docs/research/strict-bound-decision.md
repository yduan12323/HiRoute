# Tiny strict-bound decision

Development-only API, maximum eight seconds per call. Uses the original supported-disjunction roots and one exact J < b constraint, with fresh exact incumbent certification and independent replay. No optimizer, bisection, fixed incumbent assignment, or reuse of solver results. Each decision has a complete verified DAG audit.

UNSAT proves no supported value below b. Only when b equals the independently attained witness's primary value is primary optimality certified. No secondary, H, action-order or full-key certificate is returned. SAT does not certify an attained improvement: a closure point need not satisfy strict charge constraints. UNKNOWN establishes no new bound. Subsequent optimization/support/attainment routines remain unchanged.

Phase start/end process RSS samples are observational, not peak or tree memory. Missing psutil produces null samples. External process-tree guards remain authoritative; no inference of native allocation cause is supported.

This stage does not authorize full-size trials or establish a lower-memory improvement. Any future extension must preserve complete depth and all subsequent proof duties.

## Separately admitted complete-depth profile

`decide_real` is a development API, not a launcher or admission. An admitted consumer must supply its original absolute monotonic deadline (at most120seconds remaining), with unchanged external120CPU/120wall tree guards and accounting. The callback loads and validates immutable inputs inside that deadline. Parent-directory write/fsync probe and fresh output-path checks precede loading; existing evidence is never removed. Engine initialization and deadline failures yield UNKNOWN. Final post-result deadline check prevents a late SAT/UNSAT from becoming a certificate.

The profile uses table_relevant_depth's complete triangle-bound depth, with no site/slot cap. It retains original physical equations, support copy, exact incumbent certificate, J<b query and restricted primary-only conclusions. No full-size use has been tested or authorized in this stage.
