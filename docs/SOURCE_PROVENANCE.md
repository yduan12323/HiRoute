# Source provenance and code evolution

HiRoute run records may include the current commit, executable-source closure, installed package identity, and dependency information. These values document the code and environment used for that run. A new source revision is not rejected merely because its digest or file count differs from an older revision.

Before combining stages or comparing results, verify that they share the source and environment identities required by their experiment contract. Different source identities do not establish scientific equivalence; behavior and reproduction checks remain necessary.

Integrity checks remain required for raw and downloaded inputs, frozen queries and configurations, generated outputs, manifests, receipts, and historical experiment evidence. These checks protect the identity and readability of scientific evidence and are distinct from a fixed source-code allowlist.
