"""Candidate snapping to locally routable non-expressway nodes; access approximation."""
from dataclasses import replace
import numpy as np
from scipy.spatial import cKDTree
from pyproj import Geod
from graph.road_graph import unit_sphere


def attach_opportunities(opportunities, graph, road_classes, config):
    if config['default_threshold_m'] <= 0 or config['candidate_count'] < 1:
        raise ValueError('Invalid attachment configuration')
    allowed = ~np.isin(road_classes, config['excluded_highway'])
    outgoing = np.zeros(graph.node_count, dtype=bool)
    incoming = outgoing.copy()
    outgoing[graph.source[allowed]] = True
    incoming[graph.target[allowed]] = True
    routable = outgoing & incoming if config['require_in_and_out_edges'] else outgoing | incoming
    nodes = np.flatnonzero(routable)
    if not len(nodes):
        return [replace(o, attachment_status='no_candidate') for o in opportunities]
    tree = cKDTree(unit_sphere(graph.nodes.iloc[nodes].lat, graph.nodes.iloc[nodes].lon))
    _, nearest = tree.query(unit_sphere([o.lat for o in opportunities], [o.lon for o in opportunities]),
                            k=min(config['candidate_count'], len(nodes)))
    nearest = np.asarray(nearest).reshape(len(opportunities), -1)
    geod = Geod(ellps='WGS84')
    result = []
    for o, candidates in zip(opportunities, nearest, strict=True):
        candidates = nodes[candidates]
        coordinates = graph.nodes.iloc[candidates]
        distances = geod.inv(np.full(len(candidates), o.lon), np.full(len(candidates), o.lat),
                             coordinates.lon.to_numpy(), coordinates.lat.to_numpy())[2]
        # Geodesic distance then graph identity supplies deterministic tie breaking.
        best = np.lexsort((candidates, distances))[0]
        node, distance = int(candidates[best]), float(distances[best])
        result.append(replace(o, access_node=node, access_osm_node_id=int(graph.nodes.iloc[node].osm_node_id),
                              access_distance_m=distance,
                              attachment_status='attached' if distance <= config['default_threshold_m'] else 'excessive_snap'))
    return result
