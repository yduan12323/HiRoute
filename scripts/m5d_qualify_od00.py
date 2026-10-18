"""Bounded real-road qualification of the frozen OD00 first 32 Site candidates."""
from __future__ import annotations

from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from microplan.routing import ExactRouter
from scripts.m5d_one_query_runner import load_graph


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(root, graph_dir, output, certificate):
    start = time.monotonic_ns()
    source = root / "results/milestone_5d/continuation_20261011"
    pool_file = source / "pool_od00_20261011_v1/pool.json"
    slate_file = source / "fixed_12od_candidate_slate.json"
    pool, slate = json.loads(pool_file.read_text()), json.loads(slate_file.read_text())
    if (pool["slate_sha256"] != digest(slate_file) or pool["od_id"] != "OD00"
            or len(pool["sites"]) != 128 or slate["od"][0]["od_id"] != "OD00"):
        raise ValueError("Frozen OD00 input binding failed")
    # Graph authority is the already checked native landmark certificate.
    cert = json.loads(certificate.read_text())
    graph, metadata_sha = load_graph(graph_dir, cert["graph_nodes_sha256"], cert["graph_edges_sha256"])
    candidates = pool["sites"][:32]
    nodes = [pool["origin_anchor"]] + [s["access_node"] for s in candidates] + [pool["destination_anchor"]]
    if len(set(nodes)) != len(nodes):
        raise ValueError("Duplicate road anchor in OD00 first 32")
    router = ExactRouter(graph, {"compiler":"g++","compiler_flags":["-O3","-std=c++17"]}, output / "native")
    labels = []
    for node in nodes[:-1]:
        _, length, _, _ = router.full_edges(node)
        labels.append([float(length[target]) for target in nodes])
    # Charge fully at each stop. This is a physical path proposal, not a
    # schedule or objective certificate. Recheck every selected directed leg.
    q = slate["queries"][0]
    initial = Fraction(q["initial_energy_kwh"])
    capacity = Fraction(q["capacity_kwh"])
    reserve = Fraction(q["terminal_reserve_kwh"])
    consumption = Fraction(q["consumption_kwh_per_m"])
    routes = [(0, initial, ())]
    witness = None
    for depth in range(1, 9):
        more = []
        for at, energy, used in routes:
            for j in range(1, 33):
                if j in used or candidates[j-1]["progress"] <= (candidates[at-1]["progress"] if at else 0):
                    continue
                length = labels[at][j]
                if not 0 <= length < float("inf"):
                    continue
                arrival = energy - Fraction(*length.as_integer_ratio()) * consumption
                if arrival < 0:
                    continue
                end_length = labels[j][33]
                if len(used) >= 1 and 0 <= end_length < float("inf") and capacity - Fraction(*end_length.as_integer_ratio()) * consumption >= reserve:
                    witness = used + (j,)
                    break
                more.append((j, capacity, used + (j,)))
            if witness:
                break
        if witness:
            break
        routes = more[:30000]
        if not routes:
            break
    witness_legs = []
    if witness:
        chain = (0,) + witness + (33,)
        energy = initial
        for ordinal, (a, b) in enumerate(zip(chain, chain[1:])):
            times, lengths, parents, parent_edges = router.full_edges(nodes[a])
            back = []
            current = nodes[b]
            while current != nodes[a]:
                edge = int(parent_edges[current]); previous = int(parents[current])
                if (edge < 0 or int(graph.source[edge]) != previous or
                        int(graph.target[edge]) != current or len(back) >= graph.node_count):
                    raise ValueError("Invalid selected predecessor edge")
                back.append(edge);current = previous
            edges = tuple(reversed(back))
            replay_time = replay_length = 0.0
            for edge in edges:
                replay_time += float(graph.weights["travel_time"][edge])
                replay_length += float(graph.weights["distance"][edge])
            if (replay_time, replay_length) != (float(times[nodes[b]]),float(lengths[nodes[b]])):
                raise ValueError("Selected path edge replay differs from native labels")
            arrival = energy - Fraction(*replay_length.as_integer_ratio()) * consumption
            if arrival < 0 or (ordinal == len(chain)-2 and arrival < reserve):
                raise ValueError("Proposed path violates exact battery energy")
            charge = capacity-arrival if b != 33 else Fraction(0)
            witness_legs.append({"from_node":nodes[a],"to_node":nodes[b],
                "selected_edges":list(edges),"travel_time_hex":replay_time.hex(),
                "actual_length_hex":replay_length.hex(),"energy_arrival_kwh":str(arrival),
                "charge_kwh":str(charge)})
            energy = capacity if b != 33 else arrival
    router.close()
    result = {"schema":"hiroute.m5d.od00_road_qualification.v2",
              "role":"directed_real_road_energy_path_proposal_not_schedule_or_exact_seed",
              "pool_sha256":digest(pool_file),"slate_sha256":digest(slate_file),
              "graph_nodes_sha256":cert["graph_nodes_sha256"],
              "graph_edges_sha256":cert["graph_edges_sha256"],
              "graph_metadata_sha256":metadata_sha,
              "candidate_count":32,"source_route_runs":len(labels),
              "route_prefix_site_indices":list(witness) if witness else None,
              "route_prefix_site_ids":[candidates[i-1]["site_id"] for i in witness] if witness else None,
              "witness_legs":witness_legs,
              "qualified_executable_seed":False,
              "qualification":"exact_energy_and_native_edge_replay_passed_activity_contract_pending" if witness else "no_energy_path_found_in_bounded_first32_search",
              "elapsed_ns":time.monotonic_ns()-start}
    with (output / "qualification.json").open("x") as f:
        json.dump(result,f,indent=2,sort_keys=True);f.write("\n")
    print(json.dumps({"qualification":result["qualification"],"witness":result["route_prefix_site_ids"]}))


if __name__ == "__main__":
    run(Path(sys.argv[1]),Path(sys.argv[2]),Path(sys.argv[3]),Path(sys.argv[4]))
