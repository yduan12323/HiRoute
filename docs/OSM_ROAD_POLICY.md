# OSM road admission policy

This package's Shandong road normalizer applies a fail-closed classification policy. Supported highway values must have an explicit speed rule or exclusion rule. Unknown or unproven classes stop graph construction; access tags do not silently turn an unknown road class into an admitted class.

The narrow exclusions are:

- `highway=street_lamp` is excluded as a non-road feature.
- `highway=yes` is excluded only when verified original-way evidence shows the exact tags `building=yes` and `amenity=shelter`, and the original ordered node-reference sequence is closed. Other `highway=yes` ways remain errors.

The closed-contour rule uses source tags and original node references, not a geometric guess from a segmented line. Missing or ambiguous evidence does not qualify. Audit counts distinguish excluded parsed segments from original ways. This rule does not alter routing speed assumptions, direction handling, sample selection, or solver mathematics.
