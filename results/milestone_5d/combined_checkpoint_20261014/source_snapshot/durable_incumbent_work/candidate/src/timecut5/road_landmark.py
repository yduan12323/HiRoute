"""Certify directed ALT potentials on conservative integer road seconds."""
from __future__ import annotations

import hashlib
import json
import math
from types import SimpleNamespace

import numpy as np

from .deployable import LandmarkDistances


def certify_integer_landmark(graph, anchor_nodes: dict[str, int], root_anchor: str,
                             router_factory, *, graph_nodes_sha256: str,
                             graph_edges_sha256: str):
    """Return anchor labels and byte-stable edge-inequality certificate.

    Every conservative edge weight is an integer no greater than its frozen
    binary64 travel time. Forward and reverse potentials are checked against
    every original directed edge, so ALT differences lower-bound actual paths.
    """
    if root_anchor not in anchor_nodes or not anchor_nodes or any(
            type(node) is not int or not 0 <= node < graph.node_count
            for node in anchor_nodes.values()):
        raise ValueError("Invalid bound landmark anchor")
    times = graph.weights["travel_time"]
    if (len(times) != graph.edge_count or not np.isfinite(times).all() or
            (times <= 0).any()):
        raise ValueError("Invalid road-time weights")
    weights = np.ascontiguousarray(np.maximum(0, np.floor(np.nextafter(times, -np.inf))))
    if (weights >= 2**53).any() or (weights != np.floor(weights)).any():
        raise ValueError("Conservative integer edge weights exceed exact domain")
    conservative = SimpleNamespace(node_count=graph.node_count, edge_count=graph.edge_count,
        source=graph.source, target=graph.target,
        weights={"travel_time": weights, "distance": weights})
    router = router_factory(conservative)
    try:
        root = anchor_nodes[root_anchor]
        forward, _, _ = router.full(root)
        backward, _, _ = router.full(root, reverse=True)
        if forward[root] != 0 or backward[root] != 0:
            raise ValueError("Landmark root label is not zero")
        checked = []
        for labels, reverse in ((forward, False), (backward, True)):
            finite = np.isfinite(labels)
            if (not finite[root] or (labels[finite] < 0).any() or
                    (labels[finite] != np.floor(labels[finite])).any() or
                    labels[finite].max() + weights.max() >= 2**53):
                raise ValueError("Landmark labels leave exact integer domain")
            count = 0
            for start in range(0, graph.edge_count, 500000):
                stop = min(start + 500000, graph.edge_count)
                u, v = graph.source[start:stop], graph.target[start:stop]
                left, right = (v, u) if reverse else (u, v)
                reached = finite[left]
                if (not finite[right[reached]].all() or
                        (labels[right[reached]] > labels[left[reached]] +
                         weights[start:stop][reached]).any()):
                    raise ValueError("Directed landmark potential violates an edge")
                count += int(reached.sum())
            checked.append(dict(direction="to_landmark" if reverse else "from_landmark",
                reached_nodes=int(finite.sum()), checked_edges=count,
                label_sha256=hashlib.sha256(labels.tobytes()).hexdigest()))
        def anchors(labels):
            return {name: (int(labels[node]) if math.isfinite(float(labels[node])) else math.inf)
                    for name, node in sorted(anchor_nodes.items())}
        distances = LandmarkDistances(anchors(forward), anchors(backward))
        payload = dict(schema="hiroute.m5d.integer_second_landmark.v1",
            graph_nodes_sha256=graph_nodes_sha256, graph_edges_sha256=graph_edges_sha256,
            router_source_sha256=router.provenance["source_sha256"],
            root_anchor=root_anchor, root_node=root,
            edge_weight_policy="floor(nextafter(frozen_binary64_time,-infinity))",
            exact_integer_limit=2**53, audited=checked,
            anchor_labels={name: [None if math.isinf(distances.from_landmark[name]) else
                                 distances.from_landmark[name],
                                 None if math.isinf(distances.to_landmark[name]) else
                                 distances.to_landmark[name]] for name in sorted(anchor_nodes)})
        data = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                          allow_nan=False).encode()
        return distances, data
    finally:
        router.close()
