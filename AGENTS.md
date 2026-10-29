# Repository development rules

- Do not add source-code hash locks, fixed source-file-count gates, frozen source-file manifests, or tamper-rejection checks that prevent normal code evolution. Validate code changes with behavior regressions, interface contracts, and the reproduction checks needed for the change.
- Keep source identity as per-run provenance where useful, and keep consistency checks that ensure stages within one run use the same recorded code and environment. Such records describe which code produced an outcome; they must not be mistaken for a rule that source updates are forbidden or that results from different code versions are scientifically comparable.
- Keep integrity checks for downloaded inputs, raw data, frozen query/configuration identities, generated artifacts, receipts, and historical experiment records. Do not remove scientific input validation, output verification, or historical provenance while simplifying source-code maintenance gates.
