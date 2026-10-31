"""Scale correctness on common finite domains and explicit resource boundaries."""
import itertools
from dataclasses import replace
import json
from pathlib import Path
import random
import unittest
from unittest.mock import Mock, patch

from hiroute.contracts import ProblemSnapshot, SolverConfig
from hiroute.exact import scale
from hiroute.exact.road_index import RoadIndex
from hiroute.exact.search import solve_snapshot
from hiroute.exact.scale_replay import verify_scale_witness
from hiroute.exact.scale_bounds import SiteFeatures
from hiroute.exact.terminal import TerminalResult
from hiroute_ref.cli import snapshot_case
from hiroute_ref.model import normalize_case, replay_witness
from hiroute_ref.solver import solve_case

ROOT = Path(__file__).resolve().parents[1]
METHODS = ("flat_bb_strong", "scale")


def raw(**changes):
    source = json.loads((ROOT/"tests/r0/c01_zero_stop_snapshot.json").read_text())
    source.update(changes)
    return source


def edge(source, target, time=1, length=1):
    return dict(source=source, target=target, time_s=str(time), length_m=str(length),
                edge_id=source+">"+target)


def old_config():
    return SolverConfig("flat", "none", "bounded_time_cut_v2", "none", "none", "none",
                        "full_lexicographic_J_Q_H_Pi")


def frozen_snapshot(case):
    schedule = case.get("schedule")
    return raw(origin=case["origin"], destination=case["destination"],
               departure_time_s=str(case["start_time_s"]),
               initial_energy_kwh=str(case["initial_energy_kwh"]),
               capacity_kwh=str(case["capacity_kwh"]),
               minimum_energy_kwh=str(case["minimum_energy_kwh"]),
               destination_reserve_kwh=str(case["reserve_kwh"]),
               stop_overhead_s=str(case["overhead_s"]),
               stop_penalty_s=str(case["lambda_stop_s"]),
               consumption_kwh_per_m=str(case["consumption_kwh_per_m"]),
               schedule=None if schedule is None else {k:str(v) for k,v in schedule.items()},
               initial_remaining_schedule=0 if schedule is None else 1,
               candidate_order=list(case["sites"]), site_capabilities=case["sites"],
               charging_curve=[[str(v) for v in row] for row in case.get("charging_segments", [])],
               directed_edges=[{**e, "time_s":str(e["time_s"]), "length_m":str(e["length_m"]),
                                "edge_id":e.get("edge_id", str(i))}
                               for i,e in enumerate(case["edges"])], depth_limit=case["H_ref"])


def semantics(result):
    return tuple(result.get(field) for field in (
        "status", "key", "primary_infimum", "primary_value", "secondary_infimum"))


class ScaleSearchTests(unittest.TestCase):
    def test_invalid_resource_limits_are_rejected_before_index_construction(self):
        snapshot = ProblemSnapshot.from_dict(raw())
        invalid_times = (None, True, False, 0, -1, float('nan'), float('inf'),
                         -float('inf'), '120', object(), 10**1000)
        invalid_memory = (None, True, False, 0, -1, 1.5, 1024.0, float('nan'),
                          float('inf'), '1024')
        with patch('hiroute.exact.road_index.RoadIndex',
                   side_effect=AssertionError('invalid limits constructed an index')) as index:
            for value in invalid_times:
                with self.subTest(time=value), self.assertRaisesRegex(ValueError, 'time_limit_s'):
                    scale.solve_scale(snapshot,time_limit_s=value)
            for value in invalid_memory:
                with self.subTest(memory=value), self.assertRaisesRegex(ValueError, 'memory_limit_bytes'):
                    scale.solve_scale(snapshot,memory_limit_bytes=value)
            index.assert_not_called()

    def test_missing_scalar_exposure_is_invalid_input_not_proven_unreachable(self):
        snapshot = ProblemSnapshot.from_dict(raw(candidate_order=['u'],
            site_capabilities={'u':['C']},charging_curve=[['0','10','1','0']],depth_limit=1))
        provider = Mock(spec=('exposed_nodes','distances_from','distances_to','metrics'))
        provider.exposed_nodes = ('o','z')
        for method in METHODS:
            with self.subTest(method=method), self.assertRaisesRegex(ValueError, 'expose every query anchor: u'):
                scale.solve_scale(snapshot,method=method,provider=provider)
        provider.distances_from.assert_not_called()
        provider.distances_to.assert_not_called()

        class CompleteRestrictedProvider(RoadIndex):
            def __init__(self):
                super().__init__(snapshot.directed_edges)
                # u was explicitly requested from the full graph, whose
                # absent scalar entry now genuinely proves unreachability.
                self.exposed_nodes = ('o','z','u')

        for method in METHODS:
            result = scale.solve_scale(snapshot,method=method,provider=CompleteRestrictedProvider())
            self.assertEqual(result['status'], 'attained_optimum')
            self.assertEqual(result['key'], (1,0,0,()))
            self.assertEqual(result['metrics']['safe_unreachable_sites'], 1)

    def parity(self, source, *, compare_old=True, replay=True):
        snapshot = ProblemSnapshot.from_dict(source)
        old = solve_snapshot(snapshot, old_config()) if compare_old else None
        results = []
        for method in METHODS:
            with self.subTest(method=method):
                result = scale.solve_scale(snapshot, method=method, time_limit_s=10)
                self.assertNotIn(result["status"], ("time_limit", "memory_limit"), result)
                if old is not None:
                    self.assertEqual(semantics(result), semantics(old))
                if replay and result["status"] == "attained_optimum":
                    self.assertEqual(result["replay"]["key"], result["key"])
                    charges = [oe-ie for effect,_,ie,_,oe,_ in result["replay"]["trace"]
                               if effect in {"C", "CS"}]
                    independent_source = dict(source, depth_mode="diagnostic_cap",
                                              depth_limit=max(len(result["plan"]), source["depth_limit"]))
                    independent, _ = snapshot_case(independent_source)
                    checked = replay_witness(normalize_case(independent), result["plan"], charges)
                    self.assertEqual(checked["lex_key"], result["key"])
                results.append(result)
        self.assertEqual(semantics(results[0]), semantics(results[1]))
        return results

    def test_zero_stop_and_proven_unreachable_site(self):
        rows = self.parity(raw(candidate_order=["unreachable"],
                               site_capabilities={"unreachable":["C"]},
                               charging_curve=[["0", "10", "1", "0"]], depth_limit=1))
        for result in rows:
            self.assertEqual(result["key"], (1,0,0,()))
            self.assertEqual(result["metrics"]["safe_unreachable_sites"], 1)

    def test_terminal_infeasibility_does_not_destroy_poststop_family(self):
        source = raw(initial_energy_kwh="2", capacity_kwh="2", depth_limit=2,
                     candidate_order=["a", "b", "u"],
                     site_capabilities={s:["C"] for s in ("a", "b", "u")},
                     charging_curve=[["0", "2", "1", "0"]],
                     directed_edges=[edge("o","a",length=2), edge("a","b",length=2),
                                     edge("b","z",length=2), edge("o","u",length=3),
                                     edge("u","z",length=3)])
        rows = self.parity(source)
        for result in rows:
            self.assertEqual(result["plan"], (("a","C"),("b","C")))
            self.assertGreater(result["metrics"]["terminal_infeasible_prefixes"], 0)
            self.assertGreater(result["metrics"]["empty_prefixes"], 0)

    def test_seed_skips_static_illegal_and_provably_energy_empty_routes(self):
        # The service-only Site is physically reachable but has no legal
        # pending=0 action. The distant charger has a strictly excessive
        # directed-distance lower bound. Neither requires an exact leg query.
        source = raw(initial_energy_kwh="2",capacity_kwh="2",depth_limit=2,
                     candidate_order=["a","b","distant","service-only"],
                     site_capabilities={"a":["C"],"b":["C"],"distant":["C"],
                                        "service-only":["S"]},
                     charging_curve=[["0","2","1","0"]],
                     directed_edges=[edge("o","a",length=2),edge("a","b",length=2),
                                     edge("b","z",length=2),edge("o","distant",length=10),
                                     edge("distant","z"),edge("o","service-only"),
                                     edge("service-only","z",time=100,length=100)])
        snapshot = ProblemSnapshot.from_dict(source)

        class TracingProvider(RoadIndex):
            def __init__(self, edges):
                super().__init__(edges)
                self.requests = []

            def selected_leg(self, source, target):
                self.requests.append((source,target))
                return super().selected_leg(source,target)

        provider = TracingProvider(snapshot.directed_edges)
        ot = provider.distances_from("o", "time_s")
        od = provider.distances_from("o", "length_m")
        zt = provider.distances_to("z", "time_s")
        zd = provider.distances_to("z", "length_m")
        features = {s:SiteFeatures(ot[s],zt[s],od[s],zd[s]) for s in snapshot.candidate_order}
        root = scale.PrefixState((scale.initial_piece(scale.Interval(2,2),anchor="o",
            remaining_schedule=0,rho=-2),), "o")
        seed, _ = scale.deterministic_seed(snapshot,root,provider,features,lambda:None,max_depth=2)
        self.assertIsNotNone(seed)
        self.assertEqual(seed["key"], (11,4,2,(("a","C"),("b","C"))))
        self.assertEqual(seed["key"], solve_snapshot(snapshot,old_config())["key"])
        self.assertFalse(any(target in {"service-only","distant"}
                             for _,target in provider.requests))
        self.assertNotIn(("o","b"),provider.requests)
        # Equality at a full battery is feasible, so the > guard must keep it.
        self.assertIn(("a","b"),provider.requests)
        verified = verify_scale_witness(snapshot,seed)
        self.assertEqual(verified["positive_charge_count"], 2)

    def test_frozen_primary_secondary_unattainment_and_full_tuple_tie(self):
        cases = json.loads((ROOT/"tests/fixtures/milestone_5_reference/frozen_cases_v2.json").read_text())
        for index in (5, 6, 7, 8, 14):
            case = cases[index]
            with self.subTest(case=case["case_id"]):
                rows = self.parity(frozen_snapshot(case))
                self.assertEqual(rows[0]["status"], case["independent_expected"]["status"])
                if rows[0]["status"] == "primary_unattained":
                    self.assertNotIn("key", rows[0])
                    self.assertIsNotNone(rows[0]["incumbent"])
                elif rows[0]["status"] == "secondary_unattained":
                    self.assertNotIn("key", rows[0])
                    self.assertEqual(rows[0]["secondary_infimum"], 0)

    def test_streaming_face_preserves_attainment_independently_of_visit_order(self):
        primary_open = TerminalResult("primary_unattained", primary_infimum=5)
        secondary_open = TerminalResult("secondary_unattained", primary_value=5,
                                        primary_infimum=5, secondary_infimum=2)
        attained_larger_q = TerminalResult("attained_optimum", primary_value=5,
                                           key=(5,3,1,(("a","C"),)))
        attained_equal_q = TerminalResult("attained_optimum", primary_value=5,
                                          key=(5,2,1,(("b","C"),)))
        for terminal_set, expected_key in (
                ((primary_open, secondary_open, attained_larger_q), None),
                ((primary_open, secondary_open, attained_larger_q, attained_equal_q), attained_equal_q.key)):
            for ordering in itertools.permutations(terminal_set):
                face = scale.OptimalFace()
                for terminal in ordering:
                    face.add(terminal, None, None)
                self.assertEqual(face.j, 5)
                self.assertTrue(face.primary_attained)
                self.assertEqual(face.q, 2)
                self.assertEqual(None if face.best is None else face.best[0].key, expected_key)
                # A better open primary face supersedes every attained route.
                face.add(TerminalResult("primary_unattained", primary_infimum=4), None, None)
                self.assertEqual(face.j, 4)
                self.assertFalse(face.primary_attained)
                self.assertIsNone(face.best)

    def test_state_aware_equality_keeps_better_secondary_value(self):
        source = raw(initial_energy_kwh="1", capacity_kwh="5", stop_penalty_s="0",
                     candidate_order=["a","b"], site_capabilities={"a":["C"],"b":["C"]},
                     depth_limit=1, charging_curve=[["0","5","1","0"]],
                     directed_edges=[edge("o","a"),edge("a","z",length=3),
                                     edge("o","b",time=2),edge("b","z",time=2)])
        for result in self.parity(source):
            self.assertEqual(result["key"], (6,1,1,(("b","C"),)))
            self.assertGreater(result["metrics"]["equality_retained"], 0)

    def test_schedule_translation_and_fixed_random_dag_parity(self):
        source = raw(initial_energy_kwh="1", capacity_kwh="5", stop_penalty_s="0",
                     candidate_order=["a"],site_capabilities={"a":["C","S","CS"]},
                     charging_curve=[["0","5","1","0"]],depth_limit=1,
                     schedule={"a":"10","b":"20","D":"3"},initial_remaining_schedule=1,
                     directed_edges=[edge("o","a"),edge("a","z")])
        for shift in (-50, 0, 100):
            rows = self.parity(dict(source, departure_time_s=str(shift),
                                    schedule={"a":str(10+shift),"b":str(20+shift),"D":"3"}))
            self.assertEqual(rows[0]["key"], (14,1,1,(("a","CS"),)))
        rng = random.Random(7613)
        nodes = ("o","a","b","z")
        for _ in range(4):
            edges = [edge(a,b,time=rng.randint(1,5),length=rng.randint(1,4))
                     for i,a in enumerate(nodes) for b in nodes[i+1:]]
            self.parity(raw(initial_energy_kwh=str(rng.randint(1,5)),capacity_kwh="6",
                            candidate_order=["a","b"],site_capabilities={"a":["C"],"b":["C"]},
                            charging_curve=[["0","6","2","0"]],depth_limit=2,
                            directed_edges=edges))

    def test_complete_independent_ref_on_one_tiny_common_domain(self):
        source = raw(initial_energy_kwh="2",capacity_kwh="5",depth_limit=1,
                     candidate_order=["a","b"],site_capabilities={"a":["C"],"b":["C"]},
                     charging_curve=[["0","5","1","0"]],
                     directed_edges=[edge("o","a"),edge("a","z",time=3,length=3),
                                     edge("o","b",time=2),edge("b","z",time=2,length=2)])
        independent, _ = snapshot_case(source)
        ref = solve_case(independent, keep_evidence=False)["result"]
        self.assertEqual(ref["status"], "attained_optimum")
        for row in self.parity(source):
            self.assertEqual(row["key"], ref["lex_key"])

    def test_no_hidden_candidate_cap_and_no_arbitrary_depth_cap(self):
        sites = [f"c{i:02}" for i in range(64)]
        source = raw(candidate_order=sites,site_capabilities={s:["C"] for s in sites},
                     charging_curve=[["0","10","1","0"]],depth_mode="unrestricted",
                     depth_limit=0,directed_edges=[edge("o","z")]+[
                         e for site in sites for e in (edge("o",site,time=100),edge(site,"z",time=100))])
        for row in self.parity(source, compare_old=False):
            self.assertEqual(row["active_candidates"], 64)
            self.assertEqual(row["key"], (1,0,0,()))
            self.assertEqual(row["depth_contract"]["mode"], "unrestricted")
        # A directed chain has six physically necessary positive charges.
        # This verifies the API can exceed diagnostic depth five; it is a
        # synthetic correctness fixture, never evidence for the real pilot.
        sites = [f"c{i}" for i in range(6)]
        nodes = ["o"]+sites+["z"]
        source = raw(initial_energy_kwh="2",capacity_kwh="2",stop_overhead_s="10",
                     stop_penalty_s="10",candidate_order=sites,
                     site_capabilities={s:["C"] for s in sites},charging_curve=[["0","2","1","0"]],
                     depth_mode="unrestricted",depth_limit=0,
                     directed_edges=[edge(a,b,length=2) for a,b in zip(nodes,nodes[1:])])
        for row in self.parity(source, compare_old=False):
            self.assertEqual(row["key"][:3], (139,12,6))
            self.assertIsNone(row["depth_contract"]["declared_limit"])
            self.assertGreaterEqual(row["metrics"]["max_depth"], 6)

    def test_resource_stop_is_unknown_and_preserves_executable_seed(self):
        snapshot = ProblemSnapshot.from_dict(raw())
        for method in METHODS:
            clock = {"time":0}
            result = scale.solve_scale(snapshot,method=method,time_limit_s=1,
                _clock=lambda:clock["time"],
                on_incumbent=lambda record:clock.update(time=2))
            self.assertEqual(result["status"], "time_limit")
            self.assertEqual(result["mathematical_status"], "unknown")
            self.assertEqual(result["incumbent"]["replay"]["key"], (1,0,0,()))
            self.assertNotIn("key", result)
        with patch.object(scale, "_resident_bytes", side_effect=itertools.count(0,100)):
            result = scale.solve_scale(snapshot,memory_limit_bytes=1,time_limit_s=10)
        self.assertEqual(result["status"], "memory_limit")
        self.assertEqual(result["mathematical_status"], "unknown")
        self.assertNotIn("key", result)


class IndependentPhysicalReplayTests(unittest.TestCase):
    def fixture(self):
        source = raw(initial_energy_kwh="2",capacity_kwh="6",destination_reserve_kwh="1",
                     stop_penalty_s="2",depth_limit=1,candidate_order=["a"],
                     site_capabilities={"a":["C","S","CS"]},
                     charging_curve=[["0","3","2","0"],["3","6","4","-6"]],
                     schedule={"a":"10","b":"50","D":"8"},initial_remaining_schedule=1,
                     directed_edges=[edge("o","a",time=2,length=1),
                                     edge("a","z",time=3,length=4)])
        snapshot = ProblemSnapshot.from_dict(source)
        result = scale.solve_scale(snapshot,time_limit_s=10)
        self.assertEqual(result["status"], "attained_optimum")
        self.assertEqual(result["plan"], (("a","CS"),))
        return snapshot, result

    def test_piecewise_charge_service_overlap_and_wait_are_recomputed(self):
        snapshot, result = self.fixture()
        verified = verify_scale_witness(snapshot, result)
        self.assertEqual(verified["independent_key"], result["key"])
        self.assertEqual(verified["total_distance_m"], 5)
        self.assertEqual(verified["driving_time_s"], 5)
        self.assertEqual(verified["elapsed_time_s"], 21)
        self.assertEqual(verified["charges_kwh"], (4,))
        self.assertEqual(verified["positive_charge_count"], 1)

    def test_alias_headers_are_distinct_from_physical_road_vertices(self):
        snapshot, result = self.fixture()
        names = {"o":"origin-site", "a":"charge-site", "z":"destination-site"}
        source = snapshot.to_dict()
        source.update(origin=names["o"],destination=names["z"],
                      candidate_order=[names["a"]],site_capabilities={names["a"]:["C","S","CS"]})
        aliased_snapshot = ProblemSnapshot.from_dict(source)
        plan = ((names["a"],"CS"),)
        key = result["key"][:3]+(plan,)
        replay = dict(result["replay"], events=plan, key=key,
                      trace=tuple((effect,names[site],ie,it,oe,ot)
                                  for effect,site,ie,it,oe,ot in result["replay"]["trace"]))
        record = dict(key=key,plan=plan,replay=replay,
                      legs=tuple(replace(leg,source=names[leg.source],target=names[leg.target])
                                 for leg in result["legs"]))
        with self.assertRaisesRegex(ValueError, "contiguous|wrong anchor"):
            verify_scale_witness(aliased_snapshot, record)
        verified = verify_scale_witness(aliased_snapshot,record,
                                        {alias:road for road,alias in names.items()})
        self.assertEqual(verified["independent_key"], key)

    def test_tampered_charge_time_edge_path_and_key_are_rejected(self):
        snapshot, result = self.fixture()
        wrong_key = (result["key"][0]+1,)+result["key"][1:]
        with self.assertRaisesRegex(ValueError, "objective key"):
            verify_scale_witness(snapshot,dict(result,key=wrong_key))
        trace = list(result["replay"]["trace"])
        charge = trace[1]
        # A zero-charge CS proposal violates strict positivity before any
        # objective or redundant-summary check can accept it.
        trace[1] = charge[:4]+(charge[2],charge[5])
        with self.assertRaisesRegex(ValueError, "strictly positive"):
            verify_scale_witness(snapshot,dict(result,replay=dict(result["replay"],trace=trace)))
        trace[1] = charge[:5]+(charge[5]+1,)
        with self.assertRaisesRegex(ValueError, "event equation"):
            verify_scale_witness(snapshot,dict(result,replay=dict(result["replay"],trace=trace)))
        first = result["legs"][0]
        edges = tuple(dict(e, source="wrong-road-vertex") for e in first.edges)
        legs = (replace(first,edges=edges),)+result["legs"][1:]
        with self.assertRaisesRegex(ValueError, "not contiguous"):
            verify_scale_witness(snapshot,dict(result,legs=legs))


if __name__ == "__main__":
    unittest.main()
