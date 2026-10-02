"""Static facts and separate trip/action types; all times are seconds, energy kWh."""
from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Protocol

TRANSPORT = frozenset({'charge', 'parking', 'rest', 'services'})


@dataclass(frozen=True)
class LocalSupport:
    radius_m: float = 500.0
    meal_count: int = 0
    nearest_meal_m: float | None = None
    toilet_count: int = 0
    nearest_toilet_m: float | None = None
    lodging_count: int = 0
    nearest_lodging_m: float | None = None
    method: str = 'spherical_geographic_distance_proxy'


@dataclass(frozen=True)
class StopSite:
    site_id: str
    osm_type: str
    osm_id: int
    lat: float
    lon: float
    access_node: int | None
    transport_capabilities: frozenset[str]
    support: LocalSupport = field(default_factory=LocalSupport)
    # Raw evidence only: no inferred power, operational availability or legal access.
    original_tags: str = '{}'
    access_osm_node_id: int | None = None
    access_distance_m: float | None = None
    attachment_status: str = 'attached'
    geometry_type: str = 'Point'
    geometry_method: str = 'OSM node'
    source_datasets: tuple[str, ...] = ()
    snapshot_timestamp: str = ''

    def __post_init__(self):
        from opportunity.models import OpportunityId
        identity = OpportunityId(self.osm_type, self.osm_id)
        if self.site_id != f'4r:{identity}':
            raise ValueError('Site identity must be the typed source OSM identity')
        caps = frozenset(self.transport_capabilities)
        if not caps or not caps <= TRANSPORT:
            raise ValueError('Only existing transportation capabilities define anchors')
        if not isfinite(self.lat) or not isfinite(self.lon) or not -90 <= self.lat <= 90 or not -180 <= self.lon <= 180:
            raise ValueError('Invalid coordinates')
        if self.access_node is not None and self.access_node < 0:
            raise ValueError('Invalid road node')
        object.__setattr__(self, 'transport_capabilities', caps)


@dataclass(frozen=True)
class EVModel:
    capacity_kwh: float = 60.0
    consumption_kwh_km: float = 0.16
    reserve_fraction: float = 0.10
    robust_margin_kwh: float = 0.0
    minimum_energy_kwh: float = 0.0

    def __post_init__(self):
        if not all(isfinite(x) for x in vars(self).values()) or self.capacity_kwh <= 0 or self.consumption_kwh_km < 0 or not 0 <= self.reserve_fraction <= 1 or self.robust_margin_kwh < 0 or not 0 <= self.minimum_energy_kwh <= self.capacity_kwh:
            raise ValueError('Invalid EV model')
        if self.terminal_floor > self.capacity_kwh:
            raise ValueError('Terminal reserve exceeds capacity')

    @property
    def terminal_floor(self):
        return max(self.minimum_energy_kwh, self.capacity_kwh * self.reserve_fraction + self.robust_margin_kwh)

    def drive_energy(self, distance_m):
        return distance_m / 1000 * self.consumption_kwh_km


class ChargingCurve(Protocol):
    def duration_s(self, arrival_kwh: float, departure_kwh: float, capacity_kwh: float) -> float: ...


@dataclass(frozen=True)
class PiecewiseChargingCurve:
    """Synthetic piecewise-constant power by SOC, with exact integral duration.

    Each (upper SOC fraction, kW) defines the interval from the previous upper
    bound. This permits nonlinear taper; it is not measured station/vehicle data.
    """
    bands: tuple[tuple[float, float], ...] = ((0.5, 100.0), (0.8, 60.0), (1.0, 30.0))

    def __post_init__(self):
        bands = tuple(tuple(map(float, b)) for b in self.bands)
        last = 0.0
        for upper, power in bands:
            if not isfinite(upper) or not isfinite(power) or not last < upper <= 1 or power <= 0:
                raise ValueError('Invalid charging bands')
            last = upper
        if last != 1.0:
            raise ValueError('Charging curve must cover full capacity')
        object.__setattr__(self, 'bands', bands)

    def segments(self, capacity):
        low, cumulative = 0.0, 0.0
        result = []
        for fraction, power in self.bands:
            high, slope = fraction * capacity, 3600 / power
            result.append((low, high, slope, cumulative - slope * low))
            cumulative += slope * (high - low)
            low = high
        return result

    def cumulative_s(self, energy, capacity):
        if not isfinite(energy) or not 0 <= energy <= capacity:
            raise ValueError('Energy outside charging domain')
        for low, high, slope, intercept in self.segments(capacity):
            if energy <= high:
                return slope * energy + intercept
        raise AssertionError('Uncovered charging domain')

    def duration_s(self, arrival_kwh, departure_kwh, capacity_kwh):
        if departure_kwh < arrival_kwh:
            raise ValueError('Charging cannot discharge')
        return self.cumulative_s(departure_kwh, capacity_kwh) - self.cumulative_s(arrival_kwh, capacity_kwh)


@dataclass(frozen=True)
class ScheduledStop:
    window_start_s: float
    window_end_s: float
    duration_s: float = 2700.0
    meal_threshold: int = 1
    hard: bool = True
    miss_penalty_s: float = 7200.0
    time_penalty_per_s: float = 2.0
    compatible_with_charging: bool = True

    def __post_init__(self):
        numbers = (self.window_start_s, self.window_end_s, self.duration_s, self.miss_penalty_s, self.time_penalty_per_s)
        if not all(isfinite(x) and x >= 0 for x in numbers) or self.window_start_s > self.window_end_s or self.meal_threshold < 1:
            raise ValueError('Invalid scheduled requirement')

    def supports(self, site):
        return site.support.meal_count >= self.meal_threshold


@dataclass(frozen=True)
class PlannerConfig:
    overhead_s: float = 300.0
    lambda_stop_s: float = 600.0
    distance_penalty_s_per_km: float = 0.0
    maximum_stops: int = 2

    def __post_init__(self):
        if not all(isfinite(x) and x >= 0 for x in (self.overhead_s, self.lambda_stop_s, self.distance_penalty_s_per_km)) or self.maximum_stops < 0:
            raise ValueError('Invalid planner configuration')


@dataclass(frozen=True)
class Trip:
    origin: int
    destination: int
    initial_energy_kwh: float
    start_time_s: float = 0.0
    mobility_budget_s: float | None = None


@dataclass(frozen=True)
class TravelLeg:
    time_s: float
    distance_m: float

    def __post_init__(self):
        if not all(isfinite(x) and x >= 0 for x in (self.time_s, self.distance_m)):
            raise ValueError('Invalid travel leg')


@dataclass(frozen=True)
class StopEvent:
    site_id: str
    access_node: int
    arrival_time_s: float
    arrival_energy_kwh: float
    departure_time_s: float
    departure_energy_kwh: float
    charged_kwh: float
    charging_duration_s: float
    scheduled_start_s: float | None

    @property
    def duration_s(self):
        return self.departure_time_s - self.arrival_time_s


@dataclass(frozen=True)
class SearchLabel:
    anchor: int
    elapsed_s: float
    energy_kwh: float
    scheduled_satisfied: bool
    stop_count: int
    generalized_cost_s: float


@dataclass(frozen=True)
class Plan:
    stops: tuple[StopEvent, ...]
    clock_s: float
    drive_s: float
    distance_m: float
    terminal_energy_kwh: float
    requirement_penalty_s: float
    generalized_cost_s: float
    labels: tuple[SearchLabel, ...]

    @property
    def stop_count(self):
        return len(self.stops)
