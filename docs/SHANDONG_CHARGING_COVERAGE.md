# Shandong charging coverage: bounded audit and supplemented static inputs

The authorized provincial audit is complete; it does **not** complete the
original research taskbook. The supplemented catalog has172 distinct qualified
C road anchors, up from168. Energy N256 is still globally unavailable, short by
at least84 before OD exclusion/reachability. No new planning solve, timing row,
main experiment, four-charge demonstration or holdout was run.

## Provenance and historical extraction uncertainty

Base main is `9f53054ac14b6156831ff200b304b50c4460d3e4` (PR30), whose
[push CI passed](https://github.com/yduan12323/HiRoute/actions/runs/41294416733).
The existing public processed graph was copied inbound from its authorized
archive and streamed locally. Its3,320,685,254 bytes and SHA-256
`49c2f9fc5edf2e8c3da08198c4a1e03a796f72197003145b80d343abc7cfd3a3`
match the old producer manifest. No graph, road metric, battery, consumption,
selected-leg rule, seed or solver kernel was changed.

The historical2026-10-16 PBF is absent from the inspected local/server paths;
other retained PBF candidates were374-byte fixtures. The old dated public URL
returned404. Therefore exact raw-to-extraction loss parity for that historical
file cannot be established. The source request/manifest were read only as data
provenance; no old admission/evidence chain was restored or executed.

The lawful fallback is the dated
[Geofabrik Shandong-only extract](https://download.geofabrik.de/asia/china/shandong.html),
`shandong-261031.osm.pbf`:71,913,523 bytes, SHA-256
`408677f47a78230fb14678a716c1dee999f3acff39589b922d847f12026e5c95`,
header replication timestamp2026-10-31T21:23:06Z. Two180s download attempts timed
out; ETag-checked HTTP206 Range continuation finished the same object in a final
bounded45s attempt. Failed attempts and headers remain in the external input
directory. The retrieved17,871-byte boundary exactly matches the old boundary
SHA-256 `cbba0cf1e5fe764bde8614477e9c027d7a7ace1e564b6bd3e42e7d32d1eb9166`.
Temporal differences are not labeled extraction fixes. Geofabrik's OSM-derived
data is [ODbL1.0](https://www.geofabrik.de/data/download.html); attribution is
OpenStreetMap contributors / Geofabrik, with the
[OSM license notice](https://www.openstreetmap.org/copyright) retained.

Raw and generated catalogs are versioned **outside Git** at
`charging-coverage-artifacts-v1/inputs` and `charging-coverage-artifacts-v1/audit-v1`
next to the checkout. Historical inputs/results remain unchanged. The committed
small result artifact records their input/output hashes and resource receipts;
it does not contain the raw or supplemented catalog.

## Observed funnel and actual limitations

| Step | Historical material | New provincial audit / supplemented version |
| --- | ---: | ---: |
| Source objects with charging signals | unavailable historical raw |266 |
| Canonical charging-station tags | historical raw count unverified |244 |
| Explicit private/no access excluded | unverified historical raw |17 |
| Eligible station records under declared static policy |223 extracted C Sites |227 |
| Individual charge-point objects, not counted as stations | not separately recorded |22 |
| Geometry errors / containment aliases in current source | not separately recorded |0 /0 |
| Additional source station IDs |—|4 |
| Attached C Sites |171 |175 |
| Distinct C road anchors |168 |172 |
| Unattached C Sites under unchanged policy |52 |52 |

All223 historical C identities are present and positively classified in the
current tagged-object audit; there were no explicit current contradictions.
The additional four source IDs and evidence are recorded in the external
catalog/provenance. All four attach, each to a new distinct anchor. This small
increase does not establish whether the old reader missed anything in its
unavailable raw input. It supplies no evidence for a large hidden extraction
loss or that another corridor could make N256 possible. Even227 raw eligible
station records are below256 before any attachment/deduplication loss.

The52 old failures reproduce exactly: under the existing four-candidate
prefilter/geodesic rule their selected eligible anchor lies outside250m. This is
failure of the frozen attachment contract, not proof that the physical station
is unusable or that moving the threshold is safe. No threshold, class exclusion,
boundary or anchor rule was relaxed to fill N.

Station capability is **source-tag evidence for the static research model**,
not verification of present operational availability. The four added records
do not establish connector compatibility, measured power or a charging curve.
The common historical charging curve remains a disclosed modeled default.
New stations are C-only; no S/CS support was invented. The old service-support
inventory remains dated historical material. No live occupancy, queueing,
opening-hours guarantee, physical entrance access, or province-wide ground-truth
coverage is claimed.

## Extraction and bounded attachment correctness

`tools/audit_shandong_charging.py` uses three bounded Pyosmium passes, retaining
tagged objects and needed way/relation members/node positions only. It handles
nodes, closed/open ways and multipolygon relations; incomplete/invalid geometry
is reported, not replaced by fabricated coordinates. Admission requires the
unchanged frozen boundary. Tags, geometry method, identity and unknown fields
remain in source evidence. Individual charge points/lifecycle objects are
audited separately. Explicit access/vehicle/lifecycle/conditional-access,
swap-only and zero-capacity contradictions are excluded. These checks are
new-catalog policy, not retroactive changes to historical evidence.

Station/child aliases use stable identity and same/contained geometry, with
historical identity preference and no automatic merge of conflicting known
operators. Such deduplication remains a declared workload rule, not a safe
full-province optimization reduction. Cross-source coordinate proximity alone
would not establish that two records are the same station. Multiple sockets or
EVSEs never become multiple station candidates merely to increase N. All
candidate counts additionally deduplicate usable road anchors.

The new data-only `AttachmentIndex` preserves the existing contract: permitted
road-class incoming AND outgoing edges; four unit-sphere squared-chord nearest
candidates, numeric/lexical ID tie, then WGS84 geodesic distance/ID tie, threshold
equality retained. An exact-eps KD query plus outward64-epsilon distance margin
collects the conservative boundary ball; original Python keys are recomputed
before selecting the prefix. Colocated ties have no hidden truncation. This
accelerates preparation without changing planning/routing or claiming globally
nearest ellipsoidal distance beyond the legacy prefix.

All **4,725 historical Sites**, including all unattached cases, reproduce their
recorded road anchors/statuses exactly. The eligible graph-node count is the
same2,710,931. Eight fresh-data-environment tests now pass: evidence/unknown semantics,
restrictions, independent random/tied prefix parity, geodesic threshold equality,
input legality, and actual native XML node/way/relation/missing-geometry handling.
The additional clean data CI requires Pyosmium/Shapely/Pyproj and runs those
fixtures normally and with `-OO`; the unchanged full M5 workflow also runs.

The first full M5 run41296196700 at head312de2f failed before independent REF
collection because the two new test modules were not registered in the existing
test-cohort manifest. This integration omission is diagnosed by its exact
`Unclassified test module` error. Both are now registered as isolated code gates,
the dependency-light coverage tests are staged into installed-wheel regressions,
and an explicit collection regression protects the registration. No existing
assertion or resource limit was relaxed, and the real data audit is not rerun.
The independent native-data CI41296196750 had already passed six tests normally
and six with `-OO` on that head. Final-head CI is reported with delivery.
The next M5 run41296733553 at6cf2023 exposed a fixture error in that new
collection regression: it assumed the optional native test file was staged
inside the installed-wheel cohort. The assertion remains unchanged; the test
now creates its own registered-path files under a temporary root, so collection
semantics do not depend on the cohort's staging layout. The second native-data
CI41296733380 passed. Both failures and their distinct diagnosed causes remain
recorded; neither is attributed to solver mathematics or hidden by a data rerun.

### Relation linework correction after review

Review of head`ee8aaa5f` identified a real parser defect: `polygonize` can discard
incomplete outer/inner linework and silently accept the remaining polygon.
The relation branch now calls `polygonize_full` separately on **original** outer
and inner lines, before any union/noding that could repair or hide invalid
rings. Nonempty cut edges, dangles or invalid rings are reported and rejected;
inner polygons outside the outer area are rejected as well. Complete fragmented
rings still work and retain their hole. Native source fixtures cover a closed
outer plus open inner, closed outer plus dangling outer, outer cut edges,
invalid inner/outer rings, outside inner rings, and a valid fragmented
outer/inner control. The original incomplete-inner fixture is demonstrably
accepted by the pre-fix implementation and rejected by the corrected branch.

Impact was assessed from the already saved source evidence, whose SHA-256 still
matches the original result artifact: all266 source objects contain **zero
relation IDs**, both among geometry records and geometry errors; all four
additions are nodes. Therefore the corrected relation-only branch was unused
by the completed real audit. Node/way processing is unchanged. Saved catalog,
binding and matrix identities remain unchanged. The small
`shandong_relation_geometry_review.json` records this evidence. No raw data was
downloaded again, no real-data extraction/attachment recount was necessary, and
no solver ran. Existing preparation and solve/verification ledgers are retained;
the wider matrix remains unlaunched. This correction does not retroactively
attribute any measured coverage increase to a historical extraction fix.

Preparation guard: one worker/thread,1.5GiB RSS,2GiB host headroom,8GiB disk
headroom,900 CPU/1,800 wall seconds overall, no reset after failures. Setup,
acquisition, dependency/test/documentation work is conservatively precharged600
CPU seconds; the processing reservation is300. The completed processing worker
used49.222366 CPU /49.253350 wall seconds; supervisor CPU peak49.223551 plus1s
margin gives50.223551 charged processing seconds. Conservative preparation
charge is **650.223551 /900 CPU seconds**, separately reported from research
solve accounting. Peak sampled RSS772,292,608 bytes; minimum host available
3,246,555,136 bytes. Disk preflight had49GiB free; after acquisition about45GiB
remained. No guard fired or new compute/resource purchase was made.

## Other lawful source options and required admission fields

The [OCM API](https://www.openchargemap.org/develop/api) has mixed provider
licenses and requires a key; no account or key was created. Its public
[per-POI export](https://github.com/openchargemap/ocm-export) permits targeted
provincial-record inspection without downloading a national POI corpus. One
specifically located
[Jinan record](https://github.com/openchargemap/ocm-export/blob/8e3bedca48ca94807d96b2f5e7ee02cffe63ae54/data/CN/OCM-54989.json)
was inspected with pinned provider-reference metadata: provider1 is marked
CC-BY4.0/open licensed, but that record was last verified in2016 and has unknown
operational status. It stays a separately retained source option, **not merged
into this frozen OSM-tag catalog**. Targeted keyword searches are not proof of
complete OCM provincial coverage. Open licensing alone supplies neither present
quality nor automatic cross-source equivalence; provider-specific attribution
and database-combination terms must remain explicit.

A government/operator dataset is a further option only when a concrete
station-level file/API and its dataset-specific reusable license/provenance are
verified. Public aggregate charger totals or an interactive commercial map are
not a reusable station catalog. No verified downloadable provincial operator
catalog was established here; no new account, agreement, purchase or contact
was attempted. No arbitrary commercial-map copying is proposed.

Required fields for another source: namespaced stable station/EVSE identities
and parent relationships; publisher/version/extraction time/license/attribution;
coordinate CRS, geometry/entrance and precision; observed vehicle/connector,
access, lifecycle/operational status and verification date; observed power and
unknown flags. WGS84 compatibility must be established rather than silently
mixing GCJ/BD coordinates with OSM. Model C/S/CS, default curve, overhead and
availability assumptions stay separately derived. Duplicates, colocated
operators, opposite carriageways, barriers and250m snap errors need explicit
handling. Preserve the old/new version boundary and compare fair methods on the
same frozen new domains; do not relabel old changed-domain runtimes.

## Frozen staged wider DEV design, not launched

`configs/charging_coverage_dev_matrix.json` freezes the prior12 OD targets,
18/48kWh initial energies, energy/schedule recipes,60km policy, supplemented
catalog/binding hashes, current complete shared profile, exact candidate-domain
fingerprints and all144 query-N cells. The four new station records did not
authorize corridor widening, battery/consumption changes or new ODs. Directed
reachability, feasible seeds, actual charge counts and performance are untested
on the new cells. All these recipes are DEV, not independent holdout groups.

| Stage | Available query cells /48 | Input-unavailable cells | Two-method cells |
| --- | ---: | ---: | ---: |
| N64, energy and schedule |44 |4 |88 available |
| N128 |24 schedule |24 energy |48 available |
| N256 |22 schedule |24 energy +2 schedule |44 available |

Thus90/144 input cells support the requested N;54 remain explicit unavailable.
Both current D01 energy64 rows have identical new fingerprints and are reusable;
the old D03 schedule128 fingerprint changes and its timing cannot be relabeled.
There are178 fresh available method cells after the two valid reuses. Complete
declared-corridor supplements are frozen independently by min/max pool count:
WD09 energy39,WD04 energy108,WD09 schedule207,WD04 schedule966, initial18 and both
methods (at most eight more rows). None supplies a province-optimal safe-filter
claim, and none has been solved.

No execution allocation is authorized here. The concrete **proposed** first
DEV stage cap is12,000 CPU seconds, within the original remaining envelope;
keep1 worker/thread,120s loaded query cap/60s target,180s cold allowance,
8GiB process/query guard and2GiB host reserve. Deterministic order is query ID,
initial18 then48, energy then schedule, Strong then Scale. Before a fresh pair,
reserve600 CPU seconds from both the eventual approved stage cap and the
original ledger. If insufficient, preserve both as `not_run_cpu_budget`; never
drop unavailable, timeout, infeasible, unattained or unrun cells from reporting.
This cap does not guarantee completion of all44 supported first-stage cells:
86 fresh workers could reserve25,800s at their worst limits. Do not infer
completion from the earlier9–10s cold observations.

Research solve/limited-REF carry is5166.078454329s; mandatory clean-CI tiny-REF/
regression verification is conservatively precharged60s, giving
**5226.078454329 /28800 CPU seconds**, with **23573.921545671s remaining**.
Preparation remains separate. The full178-fresh-row available matrix alone has
21,360 query-slot seconds at120s, plus cold costs, before complete-domain,
external-comparison, trip-value or holdout work. Their budget/priority and the
acceptance treatment of missing energyN256 require a concrete next decision;
neither a budget extension nor full matrix launch is assumed. Passing this data
audit is not population95%/median10s acceptance. Retain D04's valid60s misses,
and freeze algorithms/sampling/statistics before any future>=8new-OD holdout.
