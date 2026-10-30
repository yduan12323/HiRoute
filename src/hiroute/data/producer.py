"""Synthetic OSM XML producer contract; not yet the Shandong PBF reader."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from xml.etree import ElementTree as ET
from hiroute.contracts import ProblemSnapshot, canonical_json
from hiroute.exact.search import selected_leg

@dataclass(frozen=True)
class ProducedSnapshot:
    """Snapshot plus producer diagnostics.

    selected_legs covers ONLY consecutive pairs in [origin, *candidate_order,
    destination], including explicit unreachable rows. It is neither an itinerary
    nor a complete routing table: unlisted pairs have not been queried. The
    snapshot's directed graph remains authoritative for every solver transfer.
    """
    snapshot: ProblemSnapshot
    manifest: dict
    graph: dict
    selected_legs: tuple[dict, ...]

def _id(value):
    return sha256(canonical_json(value)).hexdigest()

def _stage(name, inputs, parents, output):
    return {"stage":name,"inputs":inputs,"parents":parents,"output_id":_id(output)}

def build_snapshot_from_osm_xml(raw: bytes, query: dict) -> ProducedSnapshot:
    """Build snapshot from synthetic OSM XML carrying exact per-segment metrics.

    The exact hiroute:time_s/length_m tags exist only in this test adapter.
    Real OSM PBF geometry/speed conversion and E01/E02/E03 bindings remain
    explicitly unimplemented.
    """
    required={"origin","destination","initial_energy_kwh","capacity_kwh",
      "minimum_energy_kwh","destination_reserve_kwh","consumption_kwh_per_m",
      "charging_curve"}
    if type(raw) is not bytes or not raw or type(query) is not dict or set(query)!=required:
        raise ValueError("raw bytes or frozen query fields invalid")
    root=ET.fromstring(raw)
    if root.tag!="osm": raise ValueError("expected OSM XML root")
    nodes={}; sites={}
    for n in root.findall("node"):
        i=n.attrib.get("id")
        if not i: raise ValueError("OSM node missing id")
        nodes[i]=(n.attrib.get("lat"),n.attrib.get("lon"))
        tags={t.attrib.get("k"):t.attrib.get("v") for t in n.findall("tag")}
        if tags.get("amenity")=="charging_station":
            effects=tuple(sorted(set(tags.get("hiroute:capabilities","C").split(","))))
            if not effects or not set(effects)<={"C","S","CS"}: raise ValueError("unsupported Site capability")
            sites[i]=effects
    edges=[]; ways=[]
    for w in root.findall("way"):
        refs=[n.attrib.get("ref") for n in w.findall("nd")]
        tags={t.attrib.get("k"):t.attrib.get("v") for t in w.findall("tag")}
        if not tags.get("highway") or tags.get("access")=="private" or len(refs)<2: continue
        if "hiroute:time_s" not in tags or "hiroute:length_m" not in tags:
            raise ValueError("synthetic highway requires exact time/length tags")
        times=tags["hiroute:time_s"].split(","); lengths=tags["hiroute:length_m"].split(",")
        if len(times)!=len(refs)-1 or len(lengths)!=len(refs)-1:
            raise ValueError("segment metric count differs from way geometry")
        pairs=list(zip(refs,refs[1:]))
        directed=pairs if tags.get("oneway")=="yes" else pairs+[(b,a) for a,b in pairs]
        for j,(a,b) in enumerate(directed):
            k=j if j<len(pairs) else 2*len(pairs)-1-j
            if a not in nodes or b not in nodes: raise ValueError("way references absent node")
            if not times[k].isdecimal() or not lengths[k].isdecimal() or int(times[k])<1 or int(lengths[k])<1:
                raise ValueError("edge metrics must be positive integer rationals")
            edges.append({"source":a,"target":b,"time_s":times[k],"length_m":lengths[k],
              "edge_id":f"way:{w.attrib.get('id')}:{a}>{b}"})
        ways.append(w.attrib.get("id"))
    if not edges: raise ValueError("raw source produced no routable edges")
    raw_sha=sha256(raw).hexdigest()
    graph={"nodes":sorted(nodes),"edges":edges,"source_way_ids":ways}; gid=_id(graph); qid=_id(query)
    adj={}; rev={}
    for e in edges: adj.setdefault(e["source"],set()).add(e["target"]); rev.setdefault(e["target"],set()).add(e["source"])
    def reach(start, graph):
        seen={start}; todo=[start]
        while todo:
            for nxt in graph.get(todo.pop(),()):
                if nxt not in seen: seen.add(nxt); todo.append(nxt)
        return seen
    candidates=sorted(s for s in sites if s in reach(query["origin"],adj) and s in reach(query["destination"],rev))
    stages=[]
    stages.append(_stage("raw",{"sha256":raw_sha,"bytes":len(raw)},[],{"sha256":raw_sha}))
    stages.append(_stage("graph",{"raw_id":stages[-1]["output_id"]},[stages[-1]["output_id"]],graph))
    parent=[stages[-1]["output_id"]]
    stages.append(_stage("stop_sites",{"graph_id":gid},parent,{k:list(sites[k]) for k in sorted(sites)})); parent=[stages[-1]["output_id"]]
    stages.append(_stage("hierarchy_summaries",{"graph_id":gid},parent,{"node_order":sorted(nodes)})); parent=[stages[-1]["output_id"]]
    stages.append(_stage("query_candidates",{"query_id":qid},parent,{"origin":query["origin"],"destination":query["destination"],"candidate_order":candidates})); parent=[stages[-1]["output_id"]]
    obj={"schema":"hiroute.problem_snapshot.v1","model_contract_id":"hiroute.time_cut_v2.bounded",
      "numerical_contract_id":"exact_rational_inputs_v1","origin":query["origin"],"destination":query["destination"],
      "departure_time_s":"0","initial_energy_kwh":query["initial_energy_kwh"],"capacity_kwh":query["capacity_kwh"],
      "minimum_energy_kwh":query["minimum_energy_kwh"],"destination_reserve_kwh":query["destination_reserve_kwh"],
      "stop_overhead_s":"1","stop_penalty_s":"0","consumption_kwh_per_m":query["consumption_kwh_per_m"],
      "schedule":None,"initial_remaining_schedule":0,"candidate_order":candidates,
      "site_capabilities":{k:list(sites[k]) for k in candidates},"charging_curve":query["charging_curve"],
      "directed_edges":edges,"selected_leg_contract":"positive_time_node_path_edge_path_tie_v1",
      "graph_or_leg_identity":"synthetic-osm-v1:"+gid,"depth_mode":"diagnostic_cap",
      "depth_limit":min(5,len(candidates)),"depth_certificate_reference":None}
    snap=ProblemSnapshot.from_dict(obj)
    legs=diagnostic_selected_legs(snap)
    stages.append(_stage("selected_legs",{"semantic_problem_id":snap.semantic_problem_id},parent,legs)); parent=[stages[-1]["output_id"]]
    stages.append(_stage("snapshot",{"semantic_problem_id":snap.semantic_problem_id,"graph_id":gid},parent,snap.to_dict()))
    manifest={"schema":"hiroute.producer_dag.v1","raw_sha256":raw_sha,"raw_bytes":len(raw),
      "graph_id":gid,"query_id":qid,"semantic_problem_id":snap.semantic_problem_id,
      "stages":stages,"execution_scope":"synthetic_osm_xml_contract_test"}
    return ProducedSnapshot(snap,manifest,graph,tuple(legs))


def diagnostic_selected_legs(snapshot):
    """O(N) diagnostic pairs only; absence of a route is valid problem data."""
    legs = []
    for source, target in zip((snapshot.origin, *snapshot.candidate_order),
                              (*snapshot.candidate_order, snapshot.destination)):
        leg = selected_leg(snapshot, source, target)
        legs.append({"source": source, "target": target, "reachable": leg is not None,
                     "time_s": None if leg is None else str(leg.time_s),
                     "length_m": None if leg is None else str(leg.length_m),
                     "edge_ids": None if leg is None else [e["edge_id"] for e in leg.edges]})
    return legs
