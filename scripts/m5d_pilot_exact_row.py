"""One supervised exact FLAT or HIER search on a fixed qualified Pilot row."""
from __future__ import annotations
import hashlib
import json
import os
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
from timecut5.deployable import (DomainBinding, QueryDomain, RegionBoundProvider,
    construct_verified_seed, _outcome_from_terminal, _independent_attained_replay)
from timecut5.real_adapter import RealProblem, original_region_view
from timecut5.real_legs import restrict_frozen_tree, NUMERICS
from timecut5.bounded import _solve_problem
from timecut5.hierarchy import _solve_hierarchical_problem
from scripts.m5d_one_query_runner import verifier_hashes


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canon(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),allow_nan=False).encode()


def encode(value):
    if isinstance(value,Fraction):return str(value)
    if isinstance(value,dict):return {k:encode(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)):return [encode(v) for v in value]
    return value


def binary(value):
    a,b=value.as_integer_ratio()
    return {"hex":value.hex(),"ratio":[str(a),str(b)]}


def run(root, graph_dir, out, certificate, od_id, prefix_count, mode, solver):
    if solver not in ("flat","hier"):
        raise ValueError("FLAT or HIER required")
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
    anchors=list(dict.fromkeys([f"road:{pool['origin_anchor']}"]+
        [item["anchor_id"] for item in sites]+[f"road:{pool['destination_anchor']}"]))
    if anchors[0]!=f"road:{pool['origin_anchor']}" or anchors[-1]!=f"road:{pool['destination_anchor']}":
        raise ValueError("Endpoint and candidate anchors overlap")
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
    if not accepted:
        raise ValueError("Fixed row has no independently replayed seed")
    hierarchy_bytes=(root/"results/milestone_4r_b1/hierarchy.json").read_bytes()
    graph_bytes=canon({"nodes_sha256":cert["graph_nodes_sha256"],
        "edges_sha256":cert["graph_edges_sha256"],"metadata_sha256":metadata_sha})
    query_bytes=canon(encode(query));candidate_bytes=canon(sorted(deployable_table.sites))
    source_bytes={"graph_sha256":graph_bytes,"site_catalog_sha256":canon(selected["sites"]),
        "population_sha256":pool_file.read_bytes(),"hierarchy_sha256":hierarchy_bytes,
        "landmark_sha256":certificate.read_bytes(),
        "selected_leg_contract_sha256":canon(backend),
        "candidate_set_sha256":candidate_bytes,"query_sha256":query_bytes,
        "mobility_budget_sha256":b"unrestricted",
        "depth_policy_sha256":b"positive_overhead_verified_seed_v1",
        "numeric_contract_sha256":NUMERICS.encode()}
    binding=DomainBinding.from_verified_bytes({k:(v,hashlib.sha256(v).hexdigest())
        for k,v in source_bytes.items()})
    domain=QueryDomain(binding,query_bytes,candidate_bytes,table_bytes,table_sha)
    seed=construct_verified_seed(domain,verifier_hashes())
    if not hasattr(seed,"max_depth"):
        raise ValueError("Verified same-domain seed reconstruction failed")
    restriction=restrict_frozen_tree(hierarchy_bytes,selected["hierarchy_sha256"],
        list(deployable_table.sites))
    root_region=original_region_view(deployable_table,restriction)
    provider=RegionBoundProvider(domain,root_region)
    marker={"schema":"hiroute.m5d.pilot_search_started.v1","row_id":row_id,
        "method":solver,"seed_j":str(seed.seed.primary_j),
        "certified_max_depth":seed.max_depth,"table_sha256":table_sha,
        "setup_elapsed_ns":time.monotonic_ns()-start}
    with (out/"search_started.json").open("x") as f:
        json.dump(marker,f,sort_keys=True);f.write("\n");f.flush();os.fsync(f.fileno())
    problem=RealProblem(dict(query,H_ref=seed.max_depth),deployable_table)
    if solver=="flat":
        solved=_solve_problem(problem,verified_primary_upper=seed.seed.primary_j,
            singleton_bound=provider.singleton_bound)
        bounded=solved;metrics={"attempted_extensions":solved.attempted_extensions}
    else:
        solved=_solve_hierarchical_problem(problem,True,root_region,
            verified_primary_upper=seed.seed.primary_j,bound_provider=provider)
        bounded=solved.bounded;metrics={"leaf_actions":solved.leaf_actions,
            "bound_member_scans":solved.bound_member_scans}
    outcome=_outcome_from_terminal(binding,bounded)
    _independent_attained_replay(domain,bounded,outcome,seed.max_depth)
    output={"schema":"hiroute.m5d.od00_development_ref_replay.v1",
        "scope":"fixed_pilot_warm_complete_leg_table_diagnostic",
        "row_id":row_id,"od_id":od_id,"mode":mode,"candidate_prefix_count":prefix_count,
        "method":solver,"seed_j":str(seed.seed.primary_j),
        "certified_max_depth":seed.max_depth,
        "solver_status":bounded.result.status,"solver_metrics":metrics,
        "exact_outcome_status":outcome.status.value,
        "exact_key":({"J":str(outcome.j),"Q":str(outcome.q),
            "H":outcome.h,"Pi":outcome.pi} if outcome.j is not None else None),
        "terminal_witness_independently_replayed":True,
        "provider_queries":provider.online_queries,
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
    run(*(Path(arg) for arg in sys.argv[1:5]),sys.argv[5],int(sys.argv[6]),sys.argv[7],sys.argv[8])
