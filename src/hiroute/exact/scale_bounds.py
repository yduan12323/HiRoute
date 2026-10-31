"""Conservative completion relaxations and static next-action summaries.

The landmark features below are distances in the *underlying directed road
graph*, once with time and once with length weights.  They are not the lengths
of selected fastest legs: those lengths need not satisfy a triangle inequality.
Tree construction scans candidates once per level; a summary query reads only
six extrema and never materializes or scans a node's members.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from types import MappingProxyType
from typing import Mapping

from .scalar import exact


def completion_bound(pieces, *, start_time, travel_time, drive_energy, reserve,
                     overhead, stop_penalty, charge_slope, service_duration=0):
    """Infimal primary cost of a relaxation requiring at least one next stop.

    For each represented physical post-stop piece, minimize

      tau(E)-t0 + T + h + max(mu*max(0,reserve+e-E), rD) + lambda*(k+1).

    ``service_duration`` is the duration still required when the piece's
    remaining-schedule flag is one (zero otherwise). Charging and service may
    overlap; driving cannot.  Each term is a lower bound on the corresponding
    remaining cost.  Additional stops, waits and route restrictions are relaxed.
    On an affine piece this function is piecewise affine, so its infimum occurs
    at an endpoint or the charge/service kink. Open endpoints are deliberately
    evaluated as limits: this function never supplies an executable incumbent.
    ``None`` means the physical prefix family is empty, not a finite bound.
    """
    start_time, travel_time, drive_energy, reserve, overhead, stop_penalty, mu, duration = (
        exact(v) for v in (start_time, travel_time, drive_energy, reserve,
                          overhead, stop_penalty, charge_slope, service_duration))
    if min(travel_time, drive_energy, reserve, overhead, stop_penalty, mu, duration) < 0:
        raise ValueError("completion relaxation costs must be nonnegative")
    best = None
    needed = reserve + drive_energy
    for piece in pieces:
        if len(piece.state_key) != 3:
            raise ValueError("completion bound requires physical state keys")
        _, remaining, stops = piece.state_key
        if remaining not in (0, 1) or type(stops) is not int or stops < 0:
            raise ValueError("invalid physical state in completion bound")
        service = duration if remaining else Fraction(0)
        points = [piece.domain.lo, piece.domain.hi]
        if mu:
            kink = needed - service / mu
            if piece.domain.lo <= kink <= piece.domain.hi:
                points.append(kink)
        fixed = travel_time + overhead + stop_penalty * (stops + 1) - start_time
        for energy in points:
            value = (piece.slope * energy + piece.intercept + fixed
                     + max(mu * max(Fraction(0), needed-energy), service))
            if best is None or value < best:
                best = value
    return best


@dataclass(frozen=True)
class SiteFeatures:
    """Exact nonnegative directed landmark distances for one physical anchor."""
    from_origin_time: Fraction
    to_destination_time: Fraction
    from_origin_distance: Fraction
    to_destination_distance: Fraction

    def __post_init__(self):
        for name in self.__dataclass_fields__:
            value = exact(getattr(self, name))
            if value < 0:
                raise ValueError("landmark distances must be nonnegative")
            object.__setattr__(self, name, value)


@dataclass(frozen=True)
class MetricSummary:
    count: int
    min_from_origin_time: Fraction
    min_to_destination_time: Fraction
    max_to_destination_time: Fraction
    min_from_origin_distance: Fraction
    min_to_destination_distance: Fraction
    max_to_destination_distance: Fraction


@dataclass(frozen=True)
class SummaryRegion:
    identifier: int
    site: str | None
    children: tuple["SummaryRegion", ...]
    summaries: Mapping[str, MetricSummary]
    # Static bitsets are an optional coverage/debug aid, never rebuilt per prefix.
    effect_masks: Mapping[str, int]


def _summarize(rows):
    return MetricSummary(
        len(rows), min(r.from_origin_time for r in rows),
        min(r.to_destination_time for r in rows),
        max(r.to_destination_time for r in rows),
        min(r.from_origin_distance for r in rows),
        min(r.to_destination_distance for r in rows),
        max(r.to_destination_distance for r in rows))


def build_region_tree(candidate_order, capabilities, features):
    """Build disjoint binary regions ordered by actual directed road progress.

    Every supplied candidate must have a feature record; missing data never
    silently deletes a Site. Proven unreachable candidates can be excluded by
    the caller, with that exclusion reported as input preparation. For providers
    lacking landmark information, all-zero features are a safe weaker choice.
    Site IDs only break ties between equal road-progress features.
    """
    sites = tuple(candidate_order)
    if len(set(sites)) != len(sites) or set(sites) != set(capabilities):
        raise ValueError("candidate identities and capabilities must match uniquely")
    if any(site not in features for site in sites):
        raise ValueError("every candidate requires explicit landmark features")
    if any(not isinstance(features[s], SiteFeatures) for s in sites):
        raise TypeError("features must be SiteFeatures")
    for site in sites:
        effects = tuple(capabilities[site])
        if not effects or len(set(effects)) != len(effects) or not set(effects) <= {"C", "S", "CS"}:
            raise ValueError("invalid Site capability set")
    bit = {site: 1 << i for i, site in enumerate(sites)}
    ordered = sorted(sites, key=lambda s: (
        features[s].from_origin_time, features[s].to_destination_time,
        features[s].from_origin_distance, features[s].to_destination_distance, s))

    def build(items, identifier):
        summaries, masks = {}, {}
        for effect in ("C", "S", "CS"):
            eligible = [s for s in items if effect in capabilities[s]]
            if eligible:
                summaries[effect] = _summarize([features[s] for s in eligible])
                mask = 0
                for site in eligible:
                    mask |= bit[site]
                masks[effect] = mask
        if len(items) == 1:
            return SummaryRegion(identifier, items[0], (),
                                 MappingProxyType(summaries), MappingProxyType(masks))
        middle = len(items) // 2
        children = (build(items[:middle], identifier*2+1),
                    build(items[middle:], identifier*2+2))
        return SummaryRegion(identifier, None, children,
                             MappingProxyType(summaries), MappingProxyType(masks))
    return build(ordered, 0) if ordered else None


def region_travel_lower_bounds(region, effect, anchor_features):
    """Return (remaining time, remaining length) lower bounds in constant time.

    Triangle inequalities for a directed shortest-distance metric give
    d(a,s)>=d(o,s)-d(o,a) and d(a,s)>=d(a,z)-d(s,z).
    For any first Site s in this Region, its entire continuation has cost at
    least d(a,s)+d(s,z). Independent extrema weaken that bound safely. This
    statement permits arbitrarily many later stops and repeated Sites.
    """
    summary = region.summaries.get(effect)
    if summary is None:
        return None
    a = anchor_features
    inbound_time = max(Fraction(0),
                       summary.min_from_origin_time-a.from_origin_time,
                       a.to_destination_time-summary.max_to_destination_time)
    inbound_distance = max(Fraction(0),
                           summary.min_from_origin_distance-a.from_origin_distance,
                           a.to_destination_distance-summary.max_to_destination_distance)
    return (inbound_time+summary.min_to_destination_time,
            inbound_distance+summary.min_to_destination_distance)


def singleton_region(site, capabilities, features, identifier=0):
    """The same static information exposed to the strong singleton baseline."""
    region = build_region_tree((site,), {site: capabilities}, {site: features})
    return SummaryRegion(identifier, region.site, region.children,
                         region.summaries, region.effect_masks)
