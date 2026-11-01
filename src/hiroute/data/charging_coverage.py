"""Data-only charging evidence and bounded legacy-compatible road attachment.

This module never routes or invokes a numerical planning solver. Station tags
are source evidence; operational status, connector compatibility and the common
research charging curve are different facts and must not be inferred from them.
"""
from __future__ import annotations

from math import cos, isfinite, radians, sin, nextafter, inf


def charging_evidence(tags):
    tags = {str(k): str(v) for k, v in tags.items()}
    station = tags.get('amenity') == 'charging_station'
    point = tags.get('man_made') == 'charge_point'
    lifecycle = [prefix for prefix in ('disused', 'abandoned', 'demolished',
        'removed', 'proposed', 'construction')
        if tags.get(prefix+':amenity') == 'charging_station'
        or tags.get(prefix+':man_made') == 'charge_point'
        or ((station or point) and tags.get(prefix) == 'yes')]
    signals = station or point or bool(lifecycle) or tags.get('charging') == 'yes'
    reasons = []
    if not station:
        reasons.append('not_a_station_tag')
    if lifecycle:
        reasons.append('explicit_lifecycle_exclusion')
    if tags.get('access') in ('private', 'no'):
        reasons.append('explicit_access_exclusion')
    # Observe explicit restrictions without claiming compatibility from absence.
    if any(tags.get(k) == 'no' for k in ('motorcar', 'motor_vehicle', 'vehicle')):
        reasons.append('explicit_vehicle_exclusion')
    if tags.get('access:conditional'):
        reasons.append('conditional_access_not_modeled')
    if tags.get('charging_station:battery_swapping') == 'only':
        reasons.append('battery_swapping_only_not_charging')
    if tags.get('capacity') == '0':
        reasons.append('explicit_zero_vehicle_capacity')
    observed = {k: v for k, v in tags.items() if k in (
        'amenity', 'man_made', 'name', 'operator', 'brand', 'ref', 'access',
        'access:conditional', 'motorcar', 'motor_vehicle', 'vehicle',
        'opening_hours', 'capacity', 'charging_station:output',
        'charging_station:battery_swapping', 'charging') or k.startswith('socket:')}
    return dict(charging_signal=bool(signals), station_tag=station,
        charge_point_tag=point, lifecycle=lifecycle, exclusion_reasons=reasons,
        modeled_C_eligible=not reasons, observed=observed,
        operational_availability='unknown',
        connector_compatibility='not_verified', charging_curve='modeled_default_not_observed')


def node_tie(value):
    value = str(value)
    return (0, int(value)) if value.isdigit() else (1, value)


def sphere(lon, lat):
    lon, lat = float(lon), float(lat)
    if not (isfinite(lon) and isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90):
        raise ValueError('finite WGS84 coordinates required')
    a, b = radians(lat), radians(lon)
    return cos(a)*cos(b), cos(a)*sin(b), sin(a)


class AttachmentIndex:
    """Recover the exact four-candidate legacy ordering without all-N scans.

    KD queries use eps=0. An outward 64-epsilon absolute distance margin covers
    rounding of the three unit-coordinate differences, squares, sum and sqrt.
    Recompute the original Python squared-chord key and stable ID tie for every
    member of that conservative ball before retaining its prefix. The ball may
    contain all colocated nodes; no hidden tie/candidate truncation is allowed.
    WGS84 Geod.inv refinement remains exactly the existing attachment contract,
    not a claim of globally nearest ellipsoidal distance beyond its prefix.
    """
    def __init__(self, node_ids, lon_lat):
        import numpy as np
        from scipy.spatial import cKDTree
        if len(node_ids) != len(lon_lat) or not len(node_ids):
            raise ValueError('nonempty matching node coordinates required')
        self.ids = tuple(map(str, node_ids))
        if len(set(self.ids)) != len(self.ids):
            raise ValueError('duplicate road node identity')
        self.coordinates = np.asarray(lon_lat, dtype=np.float64)
        if self.coordinates.shape != (len(self.ids), 2):
            raise ValueError('lon/lat coordinate pairs required')
        self.xyz = np.empty((len(self.ids),3),dtype=np.float64)
        for i,xy in enumerate(self.coordinates):self.xyz[i]=sphere(*xy)
        self.tree = cKDTree(self.xyz, copy_data=False)

    def prefix(self, lon, lat, count=4):
        import numpy as np
        if type(count) is not int or count < 1:
            raise ValueError('positive candidate count required')
        center = sphere(lon, lat)
        count = min(count, len(self.ids))
        distances, _ = self.tree.query(center, k=count, eps=0, workers=1)
        distance = float(np.max(np.atleast_1d(distances)))
        radius = nextafter(distance + 64*np.finfo(float).eps, inf)
        candidates = self.tree.query_ball_point(center, radius, eps=0, workers=1)
        def key(i):
            return (sum((a-float(b))**2 for a, b in zip(center, self.xyz[i])),
                    node_tie(self.ids[i]), i)
        return sorted(candidates, key=key)[:count]

    def attach(self, site, geod, threshold_m=250, count=4):
        if not isfinite(threshold_m) or threshold_m < 0:
            raise ValueError('finite nonnegative attachment threshold required')
        choices = []
        for i in self.prefix(site['lon'], site['lat'], count):
            lon, lat = self.coordinates[i]
            _, _, distance = geod.inv(site['lon'], site['lat'], float(lon), float(lat))
            if not isfinite(distance) or distance < 0:
                raise ValueError('invalid geodesic distance')
            choices.append((distance, node_tie(self.ids[i]), self.ids[i]))
        distance, _, node = min(choices)
        return None if distance > threshold_m else dict(node_id=node, distance_m=distance)
