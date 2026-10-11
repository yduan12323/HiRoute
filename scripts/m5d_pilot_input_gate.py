"""One bounded independent REF seed attempt for a fixed Pilot input row."""
from __future__ import annotations
import hashlib
import json
from fractions import Fraction
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from microplan.routing import ExactRouter
from scripts.m5d_one_query_runner import load_graph
from validation.reference5.real_solver import query_from_resolved_state, replay_real_witness_bytes
from validation.reference5.real_input import IndependentLegTable
from timecut5.deployable import constructive_seed_candidates


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canon(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),allow_nan=False).encode()


def binary(value):
    a,b=value.as_integer_ratio()
    return {"hex":value.hex(),"ratio":[str(a),str(b)]}


def run(root, graph_dir, out, certificate, od_id, prefix_count, mode):
    start=time.monotonic_ns()
    source=root/"results/milestone_5d/continuation_20261011"
    pool_file=root/"formal_pools_20261011_v2/pools.json"
    slate_file=source/"fixed_12od_candidate_slate.json"
    pools=json.loads(pool_file.read_text());slate=json.loads(slate_file.read_text())
    pool=next(row for row in pools["pools"] if row["od_id"]==od_id)
    if (pools["slate_sha256"]!=sha(slate_file) or
        prefix_count not in (8,16,32) or mode not in ("energy_only","energy_and_scheduled")):
        raise ValueError("Frozen OD00 source binding failed")
    legacy=root/"results/milestone_5_real_export"
    states=json.loads((legacy/"query_states_resolved.json").read_text())
    template=next(row for row in states if row.get("state_id")==
        ("C01" if mode=="energy_only" else "C02"))
    old=json.loads((legacy/template["immutable_direct_leg_table"]["path"]).read_text())
    cert=json.loads(certificate.read_text())
    graph,metadata_sha=load_graph(graph_dir,cert["graph_nodes_sha256"],cert["graph_edges_sha256"])
    sites=pool["sites"][:prefix_count]
    anchors=[f"road:{pool['origin_anchor']}"]+[item["anchor_id"] for item in sites]+[f"road:{pool['destination_anchor']}"]
    if len(set(anchors))!=prefix_count+2:
        raise ValueError("Duplicate candidate anchor")
    nodes=[int(a.removeprefix("road:")) for a in anchors]
    router=ExactRouter(graph,{"compiler":"g++","compiler_flags":["-O3","-std=c++17"]},out/"native")
    legs=[]
    for i,source_node in enumerate(nodes):
        times,lengths,parents,edges=router.full_edges(source_node)
        for j,target_node in enumerate(nodes):
            t,d=float(times[target_node]),float(lengths[target_node])
            reachable=t<float("inf") and d<float("inf")
            row={"source_anchor":anchors[i],"target_anchor":anchors[j],
                 "reachable":reachable,"label_direction":"identity" if i==j else "forward_from_source",
                 "time_s":binary(t) if reachable else None,
                 "actual_length_m":binary(d) if reachable else None}
            legs.append(row)
    backend=dict(old["backend"])
    backend["binary_sha256"]=sha(out/"native/routing.so")
    backend["compiler_provenance"]=router.provenance
    backend["source_sha256"]={
        "configs/microplan.yaml":sha(root/"configs/microplan.yaml"),
        "src/microplan/routing.cpp":sha(root/"src/microplan/routing.cpp"),
        "src/microplan/routing.py":sha(root/"src/microplan/routing.py")}
    source_hashes={"data/processed/graphs/slovenia_extended/nodes.parquet":cert["graph_nodes_sha256"],
        "data/processed/graphs/slovenia_extended/edges.parquet":cert["graph_edges_sha256"],
        "data/processed/graphs/slovenia_extended/metadata.json":metadata_sha,
        "results/milestone_4r/stop_sites.parquet":pools["site_catalog_sha256"],
        "results/milestone_4r_b1/hierarchy.json":old["hierarchy_sha256"],
        "results/milestone_5d/continuation_20261011/fixed_12od_candidate_slate.json":sha(slate_file),
        "formal_pools_20261011_v2/pools.json":sha(pool_file),
        **backend["source_sha256"]}
    router.close()
    selected={"schema":old["schema"],"numerical_contract":old["numerical_contract"],
        "anchors":anchors,"origin_anchor":anchors[0],"destination_anchor":anchors[-1],
        "sites":[{"site_id":s["site_id"],"anchor_id":s["anchor_id"],"effects":s["effects"]} for s in sites],
        "legs":legs,"source_sha256":source_hashes,"backend":backend,
        "selection_certificate_sha256":sha(pool_file),"hierarchy_sha256":old["hierarchy_sha256"]}
    table_bytes=canon(selected);table_sha=hashlib.sha256(table_bytes).hexdigest()
    table=IndependentLegTable.from_bytes(table_bytes,table_sha)
    direct=next(row for row in legs if row["source_anchor"]==anchors[0] and row["target_anchor"]==anchors[-1])
    baseline=Fraction(*float.fromhex(direct["time_s"]["hex"]).as_integer_ratio())
    schedule=(dict(template["schedule"],baseline_binary64=direct["time_s"],
        baseline_time_s=str(baseline),window_start_s=str(2*baseline/5),
        window_end_s=str(7*baseline/10)) if mode=="energy_and_scheduled" else None)
    row_id=f"{od_id}_{mode}_soc3_10_n{prefix_count}"
    state=dict(template,state_id=row_id,pool_id=f"{od_id}_first{prefix_count}_{mode}",
        origin_road_anchor=nodes[0],destination_road_anchor=nodes[-1],
        accepted_baseline_time_s=direct["time_s"],
        accepted_baseline_actual_length_m=direct["actual_length_m"],
        immutable_direct_leg_table={"sha256":table_sha},schedule=schedule,H_ref=4)
    query=query_from_resolved_state(state,table)
    query.update(leg_payload_sha256=table_sha,
        selection_certificate_sha256=selected["selection_certificate_sha256"],
        hierarchy_sha256=selected["hierarchy_sha256"])
    from timecut5.real_legs import ImmutableLegTable
    deployable_table=ImmutableLegTable.from_bytes(table_bytes,table_sha)
    proposals=constructive_seed_candidates(query,deployable_table)
    accepted=None;attempted=0
    for sequence,charges in proposals:
        attempted+=1
        try:
            result=replay_real_witness_bytes(query,table_bytes,table_sha,sequence,charges)
            if result.get("witness_replayed") is True and len(sequence)>=2:
                accepted=(sequence,charges,result)
                break
        except (ValueError,AssertionError):
            pass
    if accepted:
        sequence,charges,result=accepted
    else:
        sequence,charges,result=(),(),{}
    output={"schema":"hiroute.m5d.od00_development_ref_replay.v1",
        "scope":"fixed_pilot_input_qualification_not_formal_search",
        "row_id":row_id,"od_id":od_id,"mode":mode,"candidate_prefix_count":prefix_count,
        "pool_sha256":sha(pool_file),"table_sha256":table_sha,
        "graph_metadata_sha256":metadata_sha,"source_route_runs":len(nodes),
        "sequence":sequence,"charges":[str(x) for x in charges],
        "proposal_count":len(proposals),"attempted_count":attempted,
        "qualification":"independently_replayed_multi_stop_seed" if accepted else "incumbent_search_failed_in_bounded_deterministic_proposals",
        "witness_replayed":result.get("witness_replayed") is True,
        "H":result.get("H"),"J":str(result.get("J")),
        "elapsed_ns":time.monotonic_ns()-start}
    with (out/"replay.json").open("x") as f:
        json.dump(output,f,sort_keys=True,indent=2);f.write("\n")
    print(json.dumps(output))

if __name__=="__main__":
    run(*(Path(arg) for arg in sys.argv[1:5]),sys.argv[5],int(sys.argv[6]),sys.argv[7])
