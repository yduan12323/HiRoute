# Narrow road-admission amendment

## Status and scope

This is an explicit change to the previously frozen data/model admission policy,
not a performance-only parser change. It applies to graph builds made with the
amended `configs/routing.yaml`. Historical graphs and their configuration hashes
remain historical; this source patch does not certify or regenerate them.

Only these additions are admitted:

1. Exclude the exact highway class `street_lamp`.
2. Exclude a way whose **original raw tags** contain exactly `highway=yes`,
   `building=yes`, and `amenity=shelter`, and whose **original node-reference
   sequence** is closed (at least two references, first reference equals last).

`yes` is not added to the speed table or the generic highway exclusion list.
All other unknown highway classes, including unmatched `highway=yes`, remain
fatal even if access restrictions would otherwise discard them. No case folding,
whitespace trimming, Boolean aliases, geometry matching, or inferred closure is
allowed as evidence for the new exception. Duplicate raw tag keys or missing
original-way evidence do not qualify. Identical endpoint coordinates with
different original node IDs are not closure. This is a topological closure test,
not a claim to validate polygon geometry or building semantics.

Speed assumptions, routing/solver algorithms, OD/selection rules, sample sizes,
budgets, supported-road access rules and direction expansion are unchanged.

## Evidence before segmentation

`graph.raw_way_policy.read_raw_way_policy` reads the checksum-verified snapshot
before Pyrosm constructs segments. It uses the Python `osmium` reader without
node-location indexing and copies complete, unmodified tags and ordered node
references for exact `highway=yes` candidates. Callback-backed objects are never
retained. Candidate duplicate way IDs fail, rather than choosing one version.
This scanner expects snapshot input, not a history PBF. It neither edits the
source PBF nor exports raw evidence as a public artifact.

`normalize_network(..., raw_way_policy=records)` uses the evidence keyed by way
ID. A closed original contour can generate several open segments; it is excluded
once at way-policy evaluation and all its segments are removed. Segment geometry
is never used to reconstruct the original topology. Calls without evidence still
work for known classes, but unknown `yes` remains fatal. The config flag
`access.exclude_closed_shelter_contour` must also be enabled.

`build_graph.py` performs this prepass before parsing and records its duration
and the raw candidate count in graph metadata. Other callers must pass evidence
from the same verified source if they use the amendment. Filters upstream of the
normalizer must not silently remove these classes and erase exclusion accounting.

## Audit units

On a successful normalization, the audit always contains:

- `excluded_street_lamp`: removed parsed segments
- `excluded_street_lamp_ways`: removed original way IDs present in parsed input
- `excluded_closed_shelter_contour`: removed parsed segments
- `excluded_closed_shelter_contour_ways`: removed original way IDs present in parsed input

These are pre-direction-expansion counts, not directed-edge counts. Existing
exclusion reasons also gain an explicitly named `_ways` companion. The raw
`highway=yes` candidate total includes unmatched candidates and must not be
presented as the excluded count. If all edges are excluded, normalization still
fails as an empty driving graph. If any unknown remains, no graph is accepted.

## Dependencies and focused reproduction

Python `osmium>=4,<5` is declared in `pyproject.toml` (`pyosmium` in the Conda
manifest). Existing historical explicit Conda lock files are unchanged and do
not include this new dependency: install the declared dependency before using
the amended graph builder, or generate and validate a new environment lock.
The focused rehearsal used `osmium==4.3.2`; this is independent of the native
`osmium-tool` used by other preparation scripts.

Run in a disposable Python 3.11 environment with NumPy, pandas, SciPy, Shapely,
igraph, PyArrow, PyYAML, pytest, and osmium installed:

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests/test_road_policy_amendment.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -OO -m pytest -q tests/test_road_policy_amendment.py
```

The existing required installed-wheel CI also runs dependency-light near-miss
and mocked-decoder checks in `tests/test_raw_way_policy_logic.py`, in both modes.
Its dependency lock is unchanged; it does not substitute for geospatial checks.

The separately selected geospatial code-only gate includes hand-authored graph segments,
a synthetic PBF raw-way round trip, precise rejection cases, and audit checks.
It is not the private six-way reproduction, a full graph/OD rebuild, a solver
run, a performance benchmark, or acceptance of the previous frozen population.
No private dataset, result archive, approval identifier, or manifest is included.


## Separate pre-OD access-token correction

Before any new OD sampling, `configs/routing.yaml` now quotes the OSM access
values `"yes"` and `"no"`. PyYAML's YAML 1.1 loader otherwise loads those bare
words as `True` and `False`; normalized OSM tags remain strings. The old allowed
list therefore wrongly rejected legitimate explicit `access=yes` (and higher
priority `vehicle`, `motor_vehicle`, or `motorcar` yes) roads. Quoting `no` also
restores the documented excluded-list token type; the existing allowlist still
rejects no and other restricted/unknown values.

This is a correctness change to graph admission, separate from both the narrow
road amendment above and any semantics-preserving way partitioning. It is not
claimed to preserve the old buggy graph. The changed config and source hashes
invalidate old graph artifacts for a new corrected freeze: regenerate graphs,
freeze their new provenance, and only then generate new ODs. Historical graph
and OD artifacts must not be relabeled or reused as corrected results.

The normalizer now validates that `allowed`, `excluded`, `hierarchy`, and
`excluded_highway` are lists containing only strings before touching graph data.
Malformed tokens (including YAML booleans) fail explicitly, without coercion.
Access hierarchy, no-tag behavior, speed assumptions, other road policy,
direction expansion, solver, and backend mode are unchanged. In particular,
Pyrosm driving-mode service-road exclusion is not changed by this correction.
The dependency-light CI tests cover malformed token types; the geospatial
synthetic tests load the actual YAML and cover yes admission, no rejection,
and higher-priority access tags in both directions. These tests do not parse
a real map, generate ODs, or certify a rebuilt graph.
