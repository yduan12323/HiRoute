"""Invocation-local reuse of exact Shandong site attachments."""
from __future__ import annotations


class RunScopedSiteAttachmentCache:
    """Reuse all-site attachments within one producer invocation."""

    def __init__(
        self, graph, sites, *, max_distance_m, candidate_count=4,
        excluded_highway=("motorway", "motorway_link", "trunk", "trunk_link"),
        attachment_workers=1,
        max_attachment_group_rss_bytes=24 * 1024**3,
        attachment_memory_margin_bytes=2 * 1024**3,
    ):
        self._graph = graph
        self._sites = sites
        self._nodes = graph.nodes
        self._edges = graph.edges
        self._site_signature = tuple(
            (x.site_id, x.lon, x.lat, x.amenity, tuple(x.capabilities),
             x.source_sha256, tuple(x.transport_classes),
             x.meal_count_500m, x.geometry_method)
            for x in sites
        )
        self._config = (max_distance_m, candidate_count, tuple(excluded_highway))
        self._worker_config = (
            attachment_workers, max_attachment_group_rss_bytes,
            attachment_memory_margin_bytes,
        )
        self._resource_record = {}
        self._cached = None
        self.snap_passes = 0
        self.reuse_hits = 0

    def _check_identity(self, graph, sites, max_distance_m,
                        candidate_count, excluded_highway):
        signature = tuple(
            (x.site_id, x.lon, x.lat, x.amenity, tuple(x.capabilities),
             x.source_sha256, tuple(x.transport_classes),
             x.meal_count_500m, x.geometry_method)
            for x in sites
        )
        if (
            graph is not self._graph
            or graph.nodes is not self._nodes
            or graph.edges is not self._edges
            or sites is not self._sites
            or signature != self._site_signature
            or (max_distance_m, candidate_count, tuple(excluded_highway))
               != self._config
        ):
            raise ValueError("attachment cache identity/configuration mismatch")

    def snap_and_score(
        self, graph, sites, *, origin_node_id, destination_node_id,
        max_distance_m, candidate_count=4,
        excluded_highway=("motorway", "motorway_link", "trunk", "trunk_link"),
    ):
        self._check_identity(
            graph, sites, max_distance_m, candidate_count, excluded_highway
        )
        nodes = {n["node_id"]: n for n in graph.nodes}
        if origin_node_id not in nodes or destination_node_id not in nodes:
            raise ValueError("query endpoint absent from graph")

        if self._cached is None:
            from hiroute.data.shandong import snap_and_score_shandong_sites
            result = snap_and_score_shandong_sites(
                graph, sites,
                origin_node_id=origin_node_id,
                destination_node_id=destination_node_id,
                max_distance_m=max_distance_m,
                candidate_count=candidate_count,
                excluded_highway=excluded_highway,
                attachment_workers=self._worker_config[0],
                max_attachment_group_rss_bytes=self._worker_config[1],
                attachment_memory_margin_bytes=self._worker_config[2],
                attachment_resource_record=self._resource_record,
            )
            from copy import deepcopy
            self._cached = {
                "site_access_nodes": deepcopy(result["site_access_nodes"]),
                "audit": deepcopy(result["audit"]),
            }
            self.snap_passes += 1
            return result

        from hiroute.data.shandong_spatial import geodesic_detour_scores_wgs84
        scores = geodesic_detour_scores_wgs84(
            sites,
            (nodes[origin_node_id]["lon"], nodes[origin_node_id]["lat"]),
            (nodes[destination_node_id]["lon"],
             nodes[destination_node_id]["lat"]),
        )
        from copy import deepcopy
        access = deepcopy(self._cached["site_access_nodes"])
        scores = {sid: value for sid, value in scores.items() if sid in access}
        self.reuse_hits += 1
        return {
            "site_access_nodes": access,
            "detour_scores": scores,
            "audit": deepcopy(self._cached["audit"]),
        }

    def summary(self):
        return {
            "scope": "single_producer_invocation",
            "snap_passes": self.snap_passes,
            "reuse_hits": self.reuse_hits,
            "site_count": len(self._site_signature),
            "max_distance_m": self._config[0],
            "candidate_count": self._config[1],
            "excluded_highway": list(self._config[2]),
            "attachment_workers": self._worker_config[0],
            "max_attachment_group_rss_bytes": self._worker_config[1],
            "attachment_memory_margin_bytes": self._worker_config[2],
            "resource_record": self._resource_record,
        }
