# Remaining-charge v1 code and mathematical checks

This bundle preserves independent exact-relaxation checks, helper/runtime/gate
reviews, source-tree test commands, and installed-wheel CI logs. Earlier test
harness failures and the pre-hardening gate log are retained. The broad recovery
CI began before the final receipt-hardening edit; the final focused gate was
rerun normally and with -OO against the final code. Installed core passed
482 tests/817 subtests per mode, target 17, energy 39, and broad recovery
255/163. Final focused gate passed 8 per mode. These are finite correctness and
integration checks, not real-road completion or performance evidence.

Each file is preserved byte-for-byte as UTF-8 with size and SHA256. Historical
independent scripts retain their original workspace paths; portable project
tests are under tests/test_remaining_charge_bound.py, tests/terminal_energy,
and tests/m5d_recovery/test_remaining_charge_gate.py. The public mathematical
contract is docs/REMAINING_CHARGE_BOUND_PROOF_V1.md.
