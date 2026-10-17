"""Same-ALT member-scan diagnostic; never substitutes selected-leg minima."""
from __future__ import annotations

from fractions import Fraction
import math

from timecut5.deployable import RegionLandmarkSummary, directed_alt_region_bound
from timecut5.road_provider import TableFreeRegionBoundProvider


class SameALTMemberScan(TableFreeRegionBoundProvider):
    """Scan the same complete Region members for each online ALT/mask lookup.

    The indexed summary and mask remain independent parity gates.
    Every differing summary or action mask fails the row closed.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.member_scan_reads = 0
        self.member_scan_summary_queries = 0
        self.member_scan_mask_queries = 0

    def _incoming(self, source, region):
        self._check_region(region)
        self.member_scan_summary_queries += 1
        self.member_scan_reads += 2 * len(region.members)
        distances = self.landmarks[0]
        scanned = RegionLandmarkSummary(self._member_hash[region.identifier],
            self.graph_sha256, self.landmark_sha256,
            (min(distances.from_landmark[self.sites[s].anchor_id]
                 for s in region.members),),
            (max(distances.to_landmark[self.sites[s].anchor_id]
                 for s in region.members),))
        if scanned != self._summary[region.identifier]:
            raise ValueError("Member-scan directed ALT summary parity failed")
        value = directed_alt_region_bound(source, self.landmarks, scanned,
            graph_sha256=self.graph_sha256, landmark_sha256=self.landmark_sha256,
            member_set_sha256=self._member_hash[region.identifier])
        return Fraction(math.floor(value))

    def action_mask(self, region, effect, remaining):
        self._check_region(region)
        self.member_scan_mask_queries += 1
        scanned = 0
        if not (effect in ("S", "CS") and not remaining):
            for site in region.members:
                self.member_scan_reads += 1
                scanned |= self._action_bits.get((site, effect), 0)
        if scanned != self._action_masks[region.identifier, effect, remaining]:
            raise ValueError("Member-scan action mask parity failed")
        self.online_mask_word_work += max(1, (scanned.bit_length() + 63) // 64)
        return scanned
