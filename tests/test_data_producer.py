import hashlib, unittest
from hiroute.data.producer import build_snapshot_from_osm_xml

RAW=b"""<osm><node id="o" lat="0" lon="0"/><node id="c" lat="0" lon="1"><tag k="amenity" v="charging_station"/><tag k="hiroute:capabilities" v="C,CS"/></node><node id="z" lat="0" lon="2"/><way id="10"><nd ref="o"/><nd ref="c"/><nd ref="z"/><tag k="highway" v="residential"/><tag k="oneway" v="yes"/><tag k="hiroute:time_s" v="2,3"/><tag k="hiroute:length_m" v="4,5"/></way></osm>"""
class ProducerTests(unittest.TestCase):
 def query(self):
  return {"origin":"o","destination":"z","initial_energy_kwh":"5","capacity_kwh":"10","minimum_energy_kwh":"0","destination_reserve_kwh":"0","consumption_kwh_per_m":"0","charging_curve":[["0","10","1","0"]]}
 def test_synthetic_raw_to_snapshot_dag_identity_and_legs(self):
  a=build_snapshot_from_osm_xml(RAW,self.query()); b=build_snapshot_from_osm_xml(RAW,self.query())
  self.assertEqual(a.snapshot.candidate_order,("c",)); self.assertEqual(a.manifest,b.manifest)
  self.assertEqual(a.manifest["raw_sha256"],hashlib.sha256(RAW).hexdigest())
  names=[x["stage"] for x in a.manifest["stages"]]
  self.assertEqual(names,["raw","graph","stop_sites","hierarchy_summaries","query_candidates","selected_legs","snapshot"])
  self.assertEqual(a.manifest["stages"][-1]["parents"],[a.manifest["stages"][-2]["output_id"]])
  self.assertEqual(a.selected_legs[0]["edge_ids"],["way:10:o>c"])
  self.assertEqual(a.selected_legs[1]["edge_ids"],["way:10:c>z"])
 def test_unreachable_site_excluded_and_missing_metrics_rejected(self):
  raw=RAW.replace(b"</osm>",b'<node id="u" lat="1" lon="1"><tag k="amenity" v="charging_station"/></node></osm>')
  self.assertEqual(build_snapshot_from_osm_xml(raw,self.query()).snapshot.candidate_order,("c",))
  with self.assertRaisesRegex(ValueError,"exact time/length"):
   build_snapshot_from_osm_xml(RAW.replace(b"hiroute:time_s",b"missing:time_s"),self.query())
 def test_query_identity_changes_with_capacity(self):
  q=self.query(); a=build_snapshot_from_osm_xml(RAW,q); q["capacity_kwh"]="11"; b=build_snapshot_from_osm_xml(RAW,q)
  self.assertNotEqual(a.manifest["query_id"],b.manifest["query_id"])
  self.assertNotEqual(a.snapshot.semantic_problem_id,b.snapshot.semantic_problem_id)
