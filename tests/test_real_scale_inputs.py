"""Input preparation keeps physical road anchors and declared domains explicit."""
import json
from pathlib import Path
import tempfile
import unittest

from hiroute.exact.road_index import RoadIndex
from tools.real_scale_inputs import (InputDomainUnavailable, SiteAliasedProvider,
                                     bind_snapshot, domain_rows, export_edges, minimum_required_charges,
                                     select_domains)


class RealScaleInputTests(unittest.TestCase):
    def test_streaming_export_preserves_exact_metrics(self):
        graph = {"audit": {}, "directed_edges": [{
            "source": "a", "target": "b", "edge_id": "ab",
            "time_s": "50980751195449719357/34375000000000000000",
            "length_m": "5664527910605524373/125000000000000000"}],
            "nodes": [{"node_id": "a", "lat": 0, "lon": 0}]}
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory)/"graph.json", Path(directory)/"edges.tsv"
            source.write_text(json.dumps(graph, indent=2) + "\n")
            record = export_edges(source, target)
            self.assertEqual(record["edges"], 1)
            self.assertIn(graph["directed_edges"][0]["time_s"], target.read_text())
            with self.assertRaises(FileExistsError):
                export_edges(source, target)

    def test_domains_are_nested_unique_and_outcome_independent(self):
        config = json.loads(Path("configs/real_scale_dev.json").read_text())
        config["selection"]["ods"] = [{"query_id": "x", "origin": {"lon": 0, "lat": 0},
                                      "destination": {"lon": 1, "lat": 0}}]
        config["selection"]["candidate_counts"] = [2, 4]
        sites = [{"site_id": "o", "lon": 0, "lat": 0, "capabilities": []},
                 {"site_id": "z", "lon": 1, "lat": 0, "capabilities": []}]
        sites += [{"site_id": str(i), "lon": (i+1)/10, "lat": 0,
                   "capabilities": ["C"]} for i in range(8)]
        sites.append({"site_id": "alias", "lon": .1, "lat": 0,
                      "capabilities": ["C", "S", "CS"]})
        bindings = {"site_access_nodes": {s["site_id"]: s["site_id"] for s in sites}}
        bindings["site_access_nodes"]["alias"] = "0"
        a = select_domains(config, sites, bindings)
        b = select_domains(config, list(reversed(sites)), bindings)
        self.assertEqual(a, b)
        query = a["queries"][0]
        small, large = (query["candidate_domains"][n] for n in ("2", "4"))
        self.assertEqual(small, large[:2])
        self.assertEqual(len({r["access_node"] for r in large}), len(large))
        self.assertFalse(a["selection_uses_solver_results"])

    def test_site_aliases_preserve_road_path_and_schedule_recipe(self):
        config = json.loads(Path("configs/real_scale_dev.json").read_text())
        base = RoadIndex([{"source": "road-o", "target": "road-z", "edge_id": "oz",
                           "time_s": "100", "length_m": "1000"}])
        provider = SiteAliasedProvider(base, {"site-o": "road-o", "site-z": "road-z"})
        query = {"endpoints": {"origin": {"site_id": "site-o"},
                               "destination": {"site_id": "site-z"}},
                 "candidate_domains": {"0": []}}
        snapshot = bind_snapshot(config, query, 0, "schedule", provider)
        self.assertEqual(dict(snapshot.schedule), {"a": "40", "b": "70", "D": "2700"})
        self.assertEqual(snapshot.depth_mode, "unrestricted")
        self.assertEqual(snapshot.directed_edges, ())
        leg = provider.selected_leg(snapshot.origin, snapshot.destination)
        self.assertEqual((leg.source, leg.target), ("site-o", "site-z"))
        self.assertEqual(leg.edges[0]["source"], "road-o")
        self.assertEqual(provider.distances_to("site-z")["site-o"], 100)
        calls = []
        provider.check = lambda: calls.append(1)
        provider.selected_leg("site-o", "site-z")
        self.assertGreater(len(calls), 0)

    def test_energy_domains_exclude_service_only_and_report_shortage(self):
        config = json.loads(Path("configs/real_scale_dev.json").read_text())
        config["selection"]["ods"] = [{"query_id": "x", "origin": {"lon": 0, "lat": 0},
                                      "destination": {"lon": 1, "lat": 0}}]
        config["selection"]["candidate_counts"] = [1, 2, 4]
        sites = [{"site_id": "o", "lon": 0, "lat": 0, "capabilities": []},
                 {"site_id": "z", "lon": 1, "lat": 0, "capabilities": []},
                 {"site_id": "charge", "lon": .2, "lat": 0, "capabilities": ["C"]},
                 {"site_id": "both", "lon": .5, "lat": 0, "capabilities": ["C", "S", "CS"]},
                 {"site_id": "service", "lon": .8, "lat": 0, "capabilities": ["S"]}]
        bindings = {"site_access_nodes": {s["site_id"]: s["site_id"] for s in sites}}
        query = select_domains(config, sites, bindings)["queries"][0]
        self.assertEqual(query["scenario_eligible_counts"], {"energy_only": 2, "schedule": 3})
        self.assertEqual(domain_rows(query, 2, "energy_only"),
                         [r for r in query["candidate_domains"]["4"] if "C" in r["capabilities"]])
        self.assertEqual(domain_rows(query, 2, "schedule"), query["candidate_domains"]["2"])
        self.assertNotIn("service", {r["site_id"] for r in domain_rows(query, 2, "energy_only")})
        self.assertEqual(query["scenario_domain_status"]["energy_only"]["4"], "input_domain_unavailable")
        with self.assertRaises(InputDomainUnavailable) as caught:
            domain_rows(query, 4, "energy_only")
        self.assertEqual((caught.exception.requested, caught.exception.available,
                          caught.exception.scenario), (4, 2, "energy_only"))
        self.assertEqual(len(domain_rows(query, 4, "energy_only", require_full=False)), 2)
        # Binding rejects the unavailable domain before invoking any provider.
        with self.assertRaises(InputDomainUnavailable):
            bind_snapshot(config, query, 4, "energy_only", object())

    def test_necessary_charge_count_uses_road_distance_and_capacity(self):
        model = json.loads(Path("configs/real_scale_dev.json").read_text())["model"]
        self.assertEqual(minimum_required_charges(450000, model), 1)
        self.assertEqual(minimum_required_charges(450001, model), 2)
        self.assertEqual(minimum_required_charges(600000, model), 2)


if __name__ == "__main__":
    unittest.main()
