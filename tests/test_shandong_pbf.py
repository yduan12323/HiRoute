from __future__ import annotations
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from hiroute.data.shandong import read_shandong_pbf, _posted_speed
ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "data" / "tiny-shandong.osm.pbf"
ROUTING = json.loads((ROOT / "configs" / "shandong-routing.json").read_text())
class ShandongPbfTests(unittest.TestCase):
    def test_real_pbf_parser_is_explicitly_single_process(self):
        from pyrosm import OSM as RealOSM
        calls=[]
        def serial_osm(*args, **kwargs):
            calls.append(kwargs.copy())
            return RealOSM(*args, **kwargs)
        with patch("pyrosm.OSM", side_effect=serial_osm):
            read_shandong_pbf(FIXTURE, ROUTING)
        self.assertEqual(calls, [{"engine": "out_of_core", "workers": 1}])

    def test_out_of_core_matches_full_ordered_network_rows_and_direction(self):
        a=read_shandong_pbf(FIXTURE,ROUTING,reader_engine="in_memory")
        b=read_shandong_pbf(FIXTURE,ROUTING,reader_engine="out_of_core")
        self.assertEqual(a.nodes,b.nodes)
        self.assertEqual(a.edges,b.edges)
        self.assertEqual({k:v for k,v in a.audit.items() if k != "raw_way_policy_scan_milliseconds"},
                         {k:v for k,v in b.audit.items() if k != "raw_way_policy_scan_milliseconds"})
        self.assertEqual(a.policy_id,b.policy_id)

    def test_real_pbf_network_tags_lengths_and_direction_are_ingested(self):
        g = read_shandong_pbf(FIXTURE, ROUTING, expected_sha256="a79190e0b9bd4dc36dfa8bd99258d2f76bacb5826e3265eee1daa31d64555857")
        self.assertEqual(g.source_bytes, 294)
        self.assertEqual((len(g.nodes), g.audit["parsed_segments"], len(g.edges)), (3, 3, 5))
        edges = {(e["osm_way_id"], e["source"], e["target"]): e for e in g.edges}
        self.assertIn(("10", "1", "2"), edges)
        self.assertIn(("10", "2", "1"), edges)
        self.assertIn(("11", "1", "3"), edges)
        self.assertNotIn(("11", "3", "1"), edges)
        self.assertEqual(edges[("10", "1", "2")]["time_s"], "25611/1000")
        self.assertEqual(len(g.policy_id), 64)
    def test_hash_mismatch_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            read_shandong_pbf(FIXTURE, ROUTING, expected_sha256="0"*64)
    def test_speed_parser_and_policy_validation(self):
        self.assertEqual(str(_posted_speed("30 mph; 60 km/h", ROUTING["speed_model"])), "48.280320")
        with self.assertRaises(ValueError):
            read_shandong_pbf(FIXTURE, {**ROUTING, "simplify": True})

def _Point(x=117.0,y=35.0):
    from shapely.geometry import Point
    return Point(x,y)

class ShandongSiteTests(unittest.TestCase):
    def test_colocated_meal_support_creates_c_s_cs_from_distinct_osm_identities(self):
        from hiroute.data.shandong import normalize_site_records, rank_query_candidates
        rows=[
          {"id":22,"osm_type":"node","amenity":"charging_station","access":"yes","geometry":_Point()},
          {"id":23,"osm_type":"node","amenity":"restaurant","access":"yes","geometry":_Point()},
          {"id":24,"osm_type":"node","amenity":"cafe","access":"private","geometry":_Point()},
          {"id":25,"osm_type":"node","amenity":"school","access":"yes","geometry":_Point()},
        ]
        sites=normalize_site_records(rows,ROUTING["site_policy"],"a"*64)
        self.assertEqual([(x.site_id,x.capabilities,x.transport_classes,x.meal_count_500m) for x in sites],
                         [("node/22",("C","S","CS"),("charge",),1)])
        chosen=rank_query_candidates(sites,"origin","destination",{"node/22":"3/2"},limit=4)
        self.assertEqual([x.site_id for x in chosen],["node/22"])

    def test_candidate_policy_stably_ranks_supported_action_classes_and_ties(self):
        from hiroute.data.shandong import RawSite,rank_query_candidates
        def site(i,caps): return RawSite(f"node/{i}",117,35,"fixture",caps,"b"*64)
        rows=[site(31,("C",)),site(32,("C","S","CS")),site(33,("C","S","CS")),site(34,("S",))]
        scores={"node/31":"3","node/32":"1","node/33":"1","node/34":"2"}
        self.assertEqual([x.site_id for x in rank_query_candidates(rows,"o","d",scores,limit=4)],
                         ["node/31","node/34","node/32","node/33"])
        self.assertEqual([x.site_id for x in rank_query_candidates(rows,"o","d",scores,limit=4)],
                         [x.site_id for x in rank_query_candidates(reversed(rows),"o","d",scores,limit=4)])

    def test_point_line_polygon_representatives_and_same_identity_priority(self):
        from shapely.geometry import LineString,Polygon,MultiPolygon
        from hiroute.data.shandong import normalize_site_records
        policy=ROUTING["site_policy"]
        rows=[
          {"id":41,"osm_type":"way","amenity":"charging_station","geometry":_Point(117.0,35.0)},
          {"id":42,"osm_type":"way","amenity":"charging_station","geometry":LineString([(117.0,35.0),(117.002,35.0)])},
          {"id":43,"osm_type":"relation","amenity":"charging_station","geometry":Polygon([(117,35),(117.004,35),(117.004,35.004),(117,35.004)])},
          {"id":44,"osm_type":"relation","amenity":"charging_station","geometry":MultiPolygon([Polygon([(117,35),(117.002,35),(117.002,35.002),(117,35.002)])])},
        ]
        sites=normalize_site_records(rows,policy,"c"*64)
        self.assertEqual([x.site_id for x in sites],["relation/43","relation/44","way/41","way/42"])
        methods={x.site_id:x.geometry_method for x in sites}
        self.assertEqual(methods["way/41"],"point_unchanged_v1")
        self.assertEqual(methods["way/42"],"epsg3035_normalized_line_midpoint_v1")
        self.assertEqual(methods["relation/43"],"epsg3035_point_on_surface_v1")
        self.assertTrue(117.0 <= next(x.lon for x in sites if x.site_id=="way/42") <=117.002)
        duplicated=[
          {"id":45,"osm_type":"way","amenity":"charging_station","geometry":_Point(117,35)},
          {"id":45,"osm_type":"way","amenity":"charging_station","geometry":Polygon([(117,35),(117.002,35),(117.002,35.002),(117,35.002)])},
        ]
        chosen=normalize_site_records(duplicated,policy,"e"*64)
        self.assertEqual(len(chosen),1)
        self.assertEqual(chosen[0].geometry_method,"epsg3035_point_on_surface_v1")

    def test_500m_support_closed_boundary_and_outside(self):
        from hiroute.data.shandong import normalize_site_records
        # Construct longitude offsets from the exact legacy spherical chord formula.
        import math
        chord=2*math.sin(500/(2*6371008.8))
        offsets=[math.degrees(2*math.asin((r/500)*chord/2)) for r in (499,500,501)]
        rows=[]
        for i,lon in enumerate(offsets,51):
            rows.extend([
              {"id":i,"osm_type":"node","amenity":"charging_station","geometry":_Point(0,0)},
              {"id":i+100,"osm_type":"node","amenity":"restaurant","geometry":_Point(lon,0)},
            ])
        sites=normalize_site_records(rows,ROUTING["site_policy"],"d"*64)
        self.assertEqual([(x.site_id,x.meal_count_500m,x.capabilities) for x in sites],
                         [("node/51",2,("C","S","CS")),("node/52",2,("C","S","CS")),("node/53",2,("C","S","CS"))])

    def test_frozen_candidate_source_ids_preserve_order_and_reject_substitution(self):
        from hiroute.data.shandong import read_shandong_pbf, extract_shandong_sites, build_snapshot_from_shandong_components
        p=ROOT/"tests/data/tiny-shandong-sites.osm.pbf"
        graph=read_shandong_pbf(p,ROUTING); sites=extract_shandong_sites(p,ROUTING["site_policy"])
        q={"origin":"1","destination":"3","departure_time_s":"0","initial_energy_kwh":"18","capacity_kwh":"60",
          "minimum_energy_kwh":"0","destination_reserve_kwh":"6","stop_overhead_s":"300","stop_penalty_s":"600",
          "consumption_kwh_per_m":"1/6250","charging_curve":[["0","30","36","0"],["30","48","60","-720"],["48","60","120","-3600"]],
          "schedule":None,"initial_remaining_schedule":0,"H_ref":1,"diagnostic_depth_limit":1}
        result=build_snapshot_from_shandong_components(graph,sites,q,site_access_nodes={"node/101":"2"},
            detour_scores={"node/101":"1"},candidate_site_ids=["4r:node/101"])
        self.assertEqual(result.snapshot.candidate_order,("2",))
        self.assertEqual(result.manifest["candidate_selection"],"frozen-source-identities-order-v1")
        self.assertEqual(result.manifest["candidate_source_ids"],["4r:node/101"])
        with self.assertRaisesRegex(ValueError,"absent from raw POIs"):
            build_snapshot_from_shandong_components(graph,sites,q,site_access_nodes={"node/102":"2"},
                detour_scores={"node/102":"1"},candidate_site_ids=["node/102"])
        with self.assertRaisesRegex(ValueError,"duplicate raw POIs"):
            build_snapshot_from_shandong_components(graph,sites,q,site_access_nodes={"node/101":"2"},
                detour_scores={"node/101":"1"},candidate_site_ids=["4r:node/101","node/101"])
        with self.assertRaisesRegex(ValueError,"distinct source identities"):
            build_snapshot_from_shandong_components(graph,sites,q,site_access_nodes={"node/101":"2"},
                detour_scores={"node/101":"1"},candidate_site_ids=["node/101","node/101"])

    def test_real_poi_parser_is_explicitly_single_process(self):
        from pyrosm import OSM as RealOSM
        from hiroute.data.shandong import extract_shandong_sites
        calls=[]
        def serial_osm(*args, **kwargs):
            calls.append(kwargs.copy())
            return RealOSM(*args, **kwargs)
        with patch("pyrosm.OSM", side_effect=serial_osm):
            extract_shandong_sites(ROOT / "tests/data/tiny-shandong-sites.osm.pbf", ROUTING["site_policy"])
        self.assertEqual(calls, [{"engine": "out_of_core", "workers": 1}])

    def test_out_of_core_matches_ordered_poi_sites_and_selected_legs(self):
        from hiroute.data.shandong import extract_shandong_sites, build_snapshot_from_shandong_components
        p=ROOT/"tests/data/tiny-shandong-sites.osm.pbf"
        ga=read_shandong_pbf(p,ROUTING,reader_engine="in_memory")
        gb=read_shandong_pbf(p,ROUTING,reader_engine="out_of_core")
        sa=extract_shandong_sites(p,ROUTING["site_policy"],reader_engine="in_memory")
        sb=extract_shandong_sites(p,ROUTING["site_policy"],reader_engine="out_of_core")
        self.assertEqual(ga.nodes,gb.nodes); self.assertEqual(ga.edges,gb.edges); self.assertEqual(sa,sb)
        q={"origin":"1","destination":"3","departure_time_s":"0","initial_energy_kwh":"18","capacity_kwh":"60","minimum_energy_kwh":"0","destination_reserve_kwh":"6","stop_overhead_s":"300","stop_penalty_s":"600","consumption_kwh_per_m":"1/6250","charging_curve":[["0","30","36","0"],["30","48","60","-720"],["48","60","120","-3600"]],"schedule":None,"initial_remaining_schedule":0,"H_ref":1,"diagnostic_depth_limit":1}
        a=build_snapshot_from_shandong_components(ga,sa,q,site_access_nodes={"node/101":"2"},detour_scores={"node/101":"1"})
        b=build_snapshot_from_shandong_components(gb,sb,q,site_access_nodes={"node/101":"2"},detour_scores={"node/101":"1"})
        self.assertEqual(a.selected_legs,b.selected_legs)
        self.assertEqual(a.snapshot.candidate_order,b.snapshot.candidate_order)

    def test_real_pbf_pois_are_extracted_with_frozen_capability_and_access_rules(self):
        from hiroute.data.shandong import extract_shandong_sites
        p=ROOT/"tests"/"data"/"tiny-shandong-sites.osm.pbf"
        sites=extract_shandong_sites(p,ROUTING["site_policy"])
        self.assertEqual([(x.site_id,x.capabilities,x.meal_count_500m) for x in sites],[("node/101",("C","S","CS"),1)])
        self.assertEqual({x.source_sha256 for x in sites},{__import__("hashlib").sha256(p.read_bytes()).hexdigest()})

    def test_fixture_scope_uses_generic_pbf_size_cap(self):
        from hiroute.data.shandong import produce_shandong_snapshot
        with tempfile.TemporaryDirectory() as directory:
            raw = Path(directory) / "oversized-synthetic.pbf"
            raw.write_bytes(b"x" * (4 * 1024 * 1024 + 1))
            with self.assertRaisesRegex(PermissionError, "at most 4 MiB"):
                produce_shandong_snapshot(raw, "unused-boundary", ROUTING, {},
                    execution_scope="fixture", expected_raw_sha256="0" * 64,
                    expected_boundary_sha256="0" * 64, projection="EPSG:3035",
                    max_distance_m=250)

    def test_real_pbf_graph_to_selected_legs_and_snapshot_dag(self):
        from hiroute.data.shandong import read_shandong_pbf,extract_shandong_sites,build_snapshot_from_shandong_components
        p=ROOT/"tests"/"data"/"tiny-shandong-sites.osm.pbf"
        g=read_shandong_pbf(p,ROUTING); sites=extract_shandong_sites(p,ROUTING["site_policy"])
        q={"origin":"1","destination":"3","departure_time_s":"0","initial_energy_kwh":"18","capacity_kwh":"60","minimum_energy_kwh":"0","destination_reserve_kwh":"6","stop_overhead_s":"300","stop_penalty_s":"600","consumption_kwh_per_m":"1/6250","charging_curve":[["0","30","36","0"],["30","48","60","-720"],["48","60","120","-3600"]],"schedule":None,"initial_remaining_schedule":0,"H_ref":1,"diagnostic_depth_limit":1}
        result=build_snapshot_from_shandong_components(g,sites,q,site_access_nodes={"node/101":"2"},detour_scores={"node/101":"1"})
        self.assertEqual(result.snapshot.candidate_order,("2",))
        self.assertEqual([x["stage"] for x in result.manifest["stages"]],["raw","graph","stop_sites","query_candidates","selected_legs","snapshot"])
        self.assertEqual([(x["source"],x["target"]) for x in result.selected_legs],[("1","2"),("2","3")])
        self.assertEqual([x["edge_ids"] for x in result.selected_legs],[["way:10:1>2"],["way:10:2>1","way:11:1>3"]])


    def test_real_pbf_pois_are_extracted_with_frozen_capability_and_access_rules(self):
        from hiroute.data.shandong import extract_shandong_sites
        p=ROOT/"tests"/"data"/"tiny-shandong-sites.osm.pbf"
        g=extract_shandong_sites(p,ROUTING["site_policy"])
        self.assertEqual([(x.site_id,x.capabilities,x.meal_count_500m) for x in g],[("node/101",("C","S","CS"),1)])
        self.assertEqual({x.source_sha256 for x in g},{__import__("hashlib").sha256(p.read_bytes()).hexdigest()})

    def test_real_pbf_graph_to_selected_legs_and_snapshot_dag(self):
        from hiroute.data.shandong import read_shandong_pbf, extract_shandong_sites, build_snapshot_from_shandong_components
        p=ROOT/"tests"/"data"/"tiny-shandong-sites.osm.pbf"
        g=read_shandong_pbf(p,ROUTING)
        sites=extract_shandong_sites(p,ROUTING["site_policy"])
        q={"origin":"1","destination":"3","departure_time_s":"0","initial_energy_kwh":"18","capacity_kwh":"60",
          "minimum_energy_kwh":"0","destination_reserve_kwh":"6","stop_overhead_s":"300","stop_penalty_s":"600",
          "consumption_kwh_per_m":"1/6250","charging_curve":[["0","30","36","0"],["30","48","60","-720"],["48","60","120","-3600"]],
          "schedule":None,"initial_remaining_schedule":0,"H_ref":1,"diagnostic_depth_limit":1}
        result=build_snapshot_from_shandong_components(g,sites,q,site_access_nodes={"node/101":"2"},detour_scores={"node/101":"1"})
        self.assertEqual(result.snapshot.candidate_order,("2",))
        self.assertEqual([x["stage"] for x in result.manifest["stages"]],["raw","graph","stop_sites","query_candidates","selected_legs","snapshot"])
        self.assertEqual([(x["source"],x["target"]) for x in result.selected_legs],[("1","2"),("2","3")])
        self.assertEqual([x["edge_ids"] for x in result.selected_legs],[["way:10:1>2"],["way:10:2>1","way:11:1>3"]])


    def test_hash_bound_raw_boundary_to_snapshot_producer(self):
        import hashlib,tempfile
        from pathlib import Path
        from hiroute.data.shandong import produce_shandong_snapshot
        poly="""tiny
outer
117.0000 34.9990
117.0020 34.9990
117.0020 35.0020
117.0000 35.0020
117.0000 34.9990
END
END
"""
        raw=ROOT/"tests/data/tiny-shandong-sites.osm.pbf"
        q={"origin":"1","destination":"3","departure_time_s":"0","initial_energy_kwh":"18","capacity_kwh":"60","minimum_energy_kwh":"0","destination_reserve_kwh":"6","stop_overhead_s":"300","stop_penalty_s":"600","consumption_kwh_per_m":"1/6250","charging_curve":[["0","30","36","0"],["30","48","60","-720"],["48","60","120","-3600"]],"schedule":None,"initial_remaining_schedule":0,"H_ref":1,"diagnostic_depth_limit":1}
        with tempfile.TemporaryDirectory() as tmp:
            boundary=Path(tmp)/"tiny.poly"; boundary.write_text(poly)
            result=produce_shandong_snapshot(raw,boundary,ROUTING,q,execution_scope="fixture",
                expected_raw_sha256=hashlib.sha256(raw.read_bytes()).hexdigest(),
                expected_boundary_sha256=hashlib.sha256(boundary.read_bytes()).hexdigest(),
                projection="+proj=lcc +lat_1=35 +lat_2=38 +lat_0=36.5 +lon_0=118.5 +datum=WGS84 +units=m +no_defs +type=crs",
                endpoint_sources={"origin":{"identity":"4r:node/1","coordinates":[117.0,35.0]},
                                  "destination":{"identity":"4r:node/3","coordinates":[117.002,35.0]}},
                max_distance_m=250)
        produced=result["produced"]
        self.assertEqual(produced.snapshot.candidate_order,("2",))
        self.assertEqual(result["sites"][0].capabilities,("C","S","CS"))
        self.assertEqual(result["sites"][0].meal_count_500m,1)
        self.assertEqual(result["endpoint_bindings"]["origin"]["graph_node_id"],"1")
        self.assertEqual(result["endpoint_bindings"]["destination"]["graph_node_id"],"3")
        self.assertEqual(produced.manifest["endpoint_bindings"],result["endpoint_bindings"])
        self.assertEqual(len(produced.manifest["endpoint_binding_policy_id"]),64)
        self.assertEqual([s["stage"] for s in produced.manifest["stages"]],["raw","graph","stop_sites","query_candidates","selected_legs","snapshot"])


    def test_diagnostic_depth_is_explicit_independent_of_candidate_count(self):
        from hiroute.data.shandong import RawRoadGraph, RawSite, build_snapshot_from_shandong_components
        nodes=tuple({"node_id":str(i),"lat":35.0,"lon":117.0+i*0.001} for i in range(1,7))
        edges=tuple({"edge_id":f"e{i}","source":str(i),"target":str(i+1),"length_m":"100","time_s":"10"} for i in range(1,6))
        graph=RawRoadGraph("a"*64,1,nodes,edges,"policy",{"nodes":6,"directed_edges":5})
        sites=tuple(RawSite(f"node/{100+i}",117.0+i*0.001,35.0,"charging_station",("C",),"a"*64) for i in range(1,5))
        base={"origin":"1","destination":"6","departure_time_s":"0","initial_energy_kwh":"18","capacity_kwh":"60",
          "minimum_energy_kwh":"0","destination_reserve_kwh":"6","stop_overhead_s":"300","stop_penalty_s":"600",
          "consumption_kwh_per_m":"1/6250","charging_curve":[["0","30","36","0"],["30","48","60","-720"],["48","60","120","-3600"]],
          "schedule":None,"initial_remaining_schedule":0,"H_ref":3,"diagnostic_depth_limit":3}
        access={f"node/{100+i}":str(i+1) for i in range(1,5)}
        scores={sid:str(i) for i,sid in enumerate(access,1)}
        ids=list(access)
        result=build_snapshot_from_shandong_components(graph,sites,base,site_access_nodes=access,detour_scores=scores,candidate_site_ids=ids)
        self.assertEqual(len(result.snapshot.candidate_order),4)
        self.assertEqual(result.snapshot.depth_mode,"diagnostic_cap")
        self.assertEqual(result.snapshot.depth_limit,3)
        other={**base,"H_ref":2,"diagnostic_depth_limit":2}
        result2=build_snapshot_from_shandong_components(graph,sites,other,site_access_nodes=access,detour_scores=scores,candidate_site_ids=ids)
        self.assertEqual(result2.snapshot.depth_limit,2)
        with self.assertRaisesRegex(ValueError,"conflicts"):
            build_snapshot_from_shandong_components(graph,sites,{**base,"diagnostic_depth_limit":2},site_access_nodes=access,detour_scores=scores,candidate_site_ids=ids)
        with self.assertRaisesRegex(ValueError,"frozen query fields"):
            build_snapshot_from_shandong_components(graph,sites,{k:v for k,v in base.items() if k!="H_ref"},site_access_nodes=access,detour_scores=scores,candidate_site_ids=ids)
        with self.assertRaisesRegex(ValueError,"supported range"):
            build_snapshot_from_shandong_components(graph,sites,{**base,"H_ref":6,"diagnostic_depth_limit":6},site_access_nodes=access,detour_scores=scores,candidate_site_ids=ids)


class ShandongTopologyClipTests(unittest.TestCase):
    def test_polygon_clipping_is_topological_directional_and_identity_stable(self):
        import hashlib, tempfile
        from pathlib import Path
        from hiroute.data.shandong import read_shandong_pbf
        poly = """tiny
outer
117.0002 34.9999
117.0010 34.9999
117.0010 35.0010
117.0002 35.0010
117.0002 34.9999
END
END
"""
        with tempfile.TemporaryDirectory() as tmp:
            boundary = Path(tmp) / "tiny.poly"
            raw = poly.encode()
            boundary.write_bytes(raw)
            digest = hashlib.sha256(raw).hexdigest()
            kwargs = dict(boundary_path=boundary, expected_boundary_sha256=digest,
                          projection="+proj=lcc +lat_1=35 +lat_2=38 +lat_0=36.5 +lon_0=118.5 +datum=WGS84 +units=m +no_defs +type=crs")
            pbf=ROOT/"tests/data/tiny-shandong-sites.osm.pbf"
            a = read_shandong_pbf(pbf, ROUTING, **kwargs)
            b = read_shandong_pbf(pbf, ROUTING, **kwargs)
        self.assertEqual(a.nodes, b.nodes)
        self.assertEqual(a.edges, b.edges)
        self.assertEqual(a.policy_id, b.policy_id)
        nodes = {n["node_id"] for n in a.nodes}
        self.assertIn("2", nodes)
        clip_nodes = sorted(n for n in nodes if n.startswith("clip:"))
        self.assertGreaterEqual(len(clip_nodes), 3)
        way10 = [e for e in a.edges if e["osm_way_id"] == "10"]
        way11 = [e for e in a.edges if e["osm_way_id"] == "11"]
        self.assertEqual({e["direction"] for e in way10}, {-1, 1})
        self.assertEqual({e["direction"] for e in way11}, {1})
        self.assertFalse(any(e["source"] == e["target"] for e in a.edges))
        self.assertTrue(all(e["original_source"] and e["original_target"] for e in a.edges))
        self.assertTrue(all(e["boundary_sha256"] == digest for e in a.edges))
        self.assertTrue(all(e["source"].startswith("clip:11:") or e["target"].startswith("clip:11:") for e in way11))
        self.assertFalse(any(e["source"].startswith("clip:11:") and e["target"].startswith("clip:10:") for e in a.edges))
        self.assertEqual(a.audit["clipped_segments"], 2)
        self.assertEqual(a.audit["clip_nodes"], len(clip_nodes))
        full=read_shandong_pbf(ROOT/"tests/data/tiny-shandong-sites.osm.pbf", ROUTING)
        from fractions import Fraction
        full10=sum((Fraction(e["length_m"]) for e in full.edges if e["osm_way_id"]=="10" and e["direction"]==1),Fraction(0))
        clipped10=sum((Fraction(e["length_m"]) for e in way10 if e["direction"]==1),Fraction(0))
        self.assertGreater(clipped10/full10,0.79)
        self.assertLess(clipped10/full10,0.81)

    def test_boundary_is_required_and_wholly_outside_graph_fails_closed(self):
        import hashlib, tempfile
        from pathlib import Path
        from hiroute.data.shandong import read_shandong_pbf
        poly = "tiny\nouter\n117.01 35.01\n117.02 35.01\n117.02 35.02\n117.01 35.02\n117.01 35.01\nEND\nEND\n"
        with tempfile.TemporaryDirectory() as tmp:
            boundary=Path(tmp)/"outside.poly"; raw=poly.encode(); boundary.write_bytes(raw)
            digest=hashlib.sha256(raw).hexdigest()
            pbf=ROOT/"tests/data/tiny-shandong.osm.pbf"
            with self.assertRaisesRegex(ValueError,"frozen SHA-256"):
                read_shandong_pbf(pbf, ROUTING, boundary_path=boundary, projection="EPSG:3857")
            with self.assertRaisesRegex(ValueError,"no supported edges"):
                read_shandong_pbf(pbf, ROUTING, boundary_path=boundary,
                    expected_boundary_sha256=digest, projection="EPSG:3857")


    def test_extracted_pois_snap_to_bidirectional_pbf_graph_and_form_snapshot(self):
        from hiroute.data.shandong import (
            read_shandong_pbf, extract_shandong_sites,
            snap_and_score_shandong_sites, build_snapshot_from_shandong_components,
        )
        p=ROOT/"tests/data/tiny-shandong-sites.osm.pbf"
        graph=read_shandong_pbf(p,ROUTING)
        sites=extract_shandong_sites(p,ROUTING["site_policy"])
        charging=[site for site in sites if "C" in site.capabilities]
        attached=snap_and_score_shandong_sites(graph,charging,origin_node_id="1",
                                                destination_node_id="3",max_distance_m=250)
        self.assertEqual(attached["site_access_nodes"],{"node/101":"2"})
        self.assertEqual(attached["audit"]["unattached_site_ids"],[])
        from dataclasses import replace
        displaced=[replace(charging[0],lon=charging[0].lon+0.01)]
        too_far=snap_and_score_shandong_sites(graph,displaced,origin_node_id="1",
                                               destination_node_id="3",max_distance_m=1)
        self.assertEqual(too_far["site_access_nodes"],{})
        self.assertEqual(set(attached["detour_scores"]),{"node/101"})
        query={"origin":"1","destination":"3","departure_time_s":"0","initial_energy_kwh":"18","capacity_kwh":"60",
          "minimum_energy_kwh":"0","destination_reserve_kwh":"6","stop_overhead_s":"300","stop_penalty_s":"600",
          "consumption_kwh_per_m":"1/6250","charging_curve":[["0","30","36","0"],["30","48","60","-720"],["48","60","120","-3600"]],
          "schedule":None,"initial_remaining_schedule":0,"H_ref":1,"diagnostic_depth_limit":1}
        result=build_snapshot_from_shandong_components(graph,charging,query,
            site_access_nodes=attached["site_access_nodes"],detour_scores=attached["detour_scores"])
        self.assertEqual(result.snapshot.candidate_order,("2",))
        self.assertEqual([(x["source"],x["target"]) for x in result.selected_legs],[("1","2"),("2","3")])


class ShandongOutOfCoreRelationParityTests(unittest.TestCase):
    def test_relation_poi_support_and_selected_legs_match_in_memory_order(self):
        from hiroute.data.shandong import (
            read_shandong_pbf, extract_shandong_sites, snap_and_score_shandong_sites,
            build_snapshot_from_shandong_components,
        )
        pbf = ROOT / "tests/data/tiny-shandong-relation.osm.pbf"
        graph_memory = read_shandong_pbf(pbf, ROUTING, reader_engine="in_memory")
        graph_stream = read_shandong_pbf(pbf, ROUTING, reader_engine="out_of_core")
        self.assertEqual(graph_memory.nodes, graph_stream.nodes)
        self.assertEqual(graph_memory.edges, graph_stream.edges)
        self.assertEqual(
            {k:v for k,v in graph_memory.audit.items() if k != "raw_way_policy_scan_milliseconds"},
            {k:v for k,v in graph_stream.audit.items() if k != "raw_way_policy_scan_milliseconds"},
        )
        self.assertEqual(graph_memory.policy_id, graph_stream.policy_id)
        sites_memory = extract_shandong_sites(pbf, ROUTING["site_policy"], reader_engine="in_memory")
        sites_stream = extract_shandong_sites(pbf, ROUTING["site_policy"], reader_engine="out_of_core")
        self.assertEqual(sites_memory, sites_stream)
        self.assertEqual(len(sites_stream), 1)
        self.assertEqual(sites_stream[0].site_id, "node/101")
        # The relation multipolygon is the only meal support in this fixture.
        self.assertEqual(sites_stream[0].capabilities, ("C", "S", "CS"))
        query = {
            "origin":"1", "destination":"3", "departure_time_s":"0",
            "initial_energy_kwh":"18", "capacity_kwh":"60", "minimum_energy_kwh":"0",
            "destination_reserve_kwh":"6", "stop_overhead_s":"300", "stop_penalty_s":"600",
            "consumption_kwh_per_m":"1/6250",
            "charging_curve":[["0","30","36","0"],["30","48","60","-720"],["48","60","120","-3600"]],
            "schedule":None, "initial_remaining_schedule":0, "H_ref":1,
            "diagnostic_depth_limit":1,
        }
        def build(graph, sites):
            charging = [site for site in sites if "C" in site.capabilities]
            attached = snap_and_score_shandong_sites(graph, charging, origin_node_id="1",
                destination_node_id="3", max_distance_m=250)
            return build_snapshot_from_shandong_components(graph, charging, query,
                site_access_nodes=attached["site_access_nodes"], detour_scores=attached["detour_scores"])
        result_memory = build(graph_memory, sites_memory)
        result_stream = build(graph_stream, sites_stream)
        self.assertEqual(result_memory.snapshot.to_dict(), result_stream.snapshot.to_dict())
        self.assertEqual(result_memory.selected_legs, result_stream.selected_legs)




class ShandongEndpointBindingTests(unittest.TestCase):
    def test_source_way_binding_is_way_scoped_and_records_identity_difference(self):
        from hiroute.data.shandong import read_shandong_pbf, bind_source_endpoint
        graph = read_shandong_pbf(ROOT/"tests/data/tiny-shandong-sites.osm.pbf", ROUTING)
        result = bind_source_endpoint(graph, "4r:way/10", [117.001, 35.0], max_distance_m=250)
        self.assertIn(result["graph_node_id"], {"1", "2"})
        self.assertEqual(result["source_identity"], "4r:way/10")
        self.assertEqual(result["binding_method"], "source_way_endpoint_geodesic_v1")
        self.assertEqual(result["metric"], "WGS84_ellipsoidal_Geod.inv")
        with self.assertRaisesRegex(ValueError, "no graph binding candidates"):
            bind_source_endpoint(graph, "4r:way/999", [117.001, 35.0], max_distance_m=250)
        with self.assertRaisesRegex(ValueError, "snap radius"):
            bind_source_endpoint(graph, "4r:way/10", [117.001, 35.0], max_distance_m=1)

    def test_exact_node_and_node_coordinate_fallback_are_deterministic(self):
        from hiroute.data.shandong import read_shandong_pbf, bind_source_endpoint
        graph = read_shandong_pbf(ROOT/"tests/data/tiny-shandong-sites.osm.pbf", ROUTING)
        exact = bind_source_endpoint(graph, "4r:node/1", [117.0, 35.0], max_distance_m=1)
        self.assertEqual((exact["graph_node_id"], exact["binding_method"]),
                         ("1", "exact_osm_node_id_v1"))
        a = bind_source_endpoint(graph, "4r:node/999", [117.001, 35.0], max_distance_m=250)
        b = bind_source_endpoint(graph, "4r:node/999", [117.001, 35.0], max_distance_m=250)
        self.assertEqual(a, b)
        self.assertEqual(a["binding_method"], "global_graph_node_geodesic_fallback_v1")


class ShandongPolylineClipRatioTests(unittest.TestCase):
    def test_bent_polyline_fraction_uses_whole_projected_arclength(self):
        from fractions import Fraction
        from shapely.geometry import LineString, box
        from pyproj import Transformer
        from shapely.ops import transform
        from hiroute.data.shandong_spatial import clip_line_segments
        projection = "+proj=lcc +lat_1=35 +lat_2=38 +lat_0=36.5 +lon_0=118.5 +datum=WGS84 +units=m +no_defs +type=crs"
        line = LineString([(117.0000,35.0000),(117.0005,35.0007),(117.0010,35.0000),(117.0015,35.0006)])
        boundary = box(117.00025,34.9998,117.00125,35.0010)
        forward = Transformer.from_crs("EPSG:4326", projection, always_xy=True).transform
        projected_line = transform(forward, line)
        projected_boundary = transform(forward, boundary)
        clipped_length = projected_line.intersection(projected_boundary).length
        expected = clipped_length / projected_line.length
        endpoint_chord = LineString([projected_line.coords[0], projected_line.coords[-1]])
        chord_fraction = clipped_length / endpoint_chord.length
        self.assertGreater(abs(expected-chord_fraction), 1e-3)
        segments, _ = clip_line_segments(line, boundary, projection, osm_way_id="77",
                    source_node_id="1", target_node_id="4", node_coordinates={}, full_length_m=1000)
        actual = sum((Fraction(x["fraction"]) for x in segments), Fraction(0))
        self.assertAlmostEqual(float(actual), expected, places=12)
        self.assertGreater(len(segments), 0)
        self.assertLess(float(actual), 1)



    def test_formal_raw_producer_fails_closed_before_open_without_admission(self):
        from hiroute.data.shandong import produce_shandong_snapshot
        with tempfile.TemporaryDirectory() as tmp:
            missing=Path(tmp)/"not-opened.osm.pbf"
            with self.assertRaisesRegex(PermissionError,"R0-R3 admission receipt is required"):
                produce_shandong_snapshot(missing,missing,{}, {},execution_scope="formal",
                    expected_raw_sha256="0"*64,expected_boundary_sha256="1"*64,
                    projection="EPSG:4326",max_distance_m=1)

    def test_large_pbf_cannot_use_fixture_scope(self):
        from hiroute.data.shandong import produce_shandong_snapshot
        with tempfile.TemporaryDirectory() as tmp:
            large=Path(tmp)/"large.osm.pbf"
            with large.open("wb") as stream:
                stream.truncate(4*1024*1024+1)
            with self.assertRaisesRegex(PermissionError,"fixture scope is limited"):
                produce_shandong_snapshot(large,large,{}, {},execution_scope="fixture",
                    expected_raw_sha256="0"*64,expected_boundary_sha256="1"*64,
                    projection="EPSG:4326",max_distance_m=1)


if __name__ == "__main__":
    unittest.main()
