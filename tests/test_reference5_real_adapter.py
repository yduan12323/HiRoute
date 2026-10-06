"""Independent immutable-real REF mocks: no native routing or real C32 solve."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
from fractions import Fraction as R
import hashlib
import json
from pathlib import Path

import pytest

from validation.reference5.model import InvalidInput
from validation.reference5.real_input import IndependentLegTable, decode_binary64, verify_source_files
from validation.reference5.real_solver import (estimate_real_regimes, prepare_real_case,
                                               replay_real_witness, solve_real_case)


def encoded(value):
    numerator, denominator = value.as_integer_ratio()
    return dict(hex=value.hex(), ratio=[str(numerator), str(denominator)])


def payload():
    anchors = ["o", "x", "z"]
    p = dict(schema="hiroute.immutable_selected_legs.v1", numerical_contract="binary64_totals_as_exact_rationals_v1",
             anchors=anchors, origin_anchor="o", destination_anchor="z",
             sites=[dict(site_id="A", anchor_id="x", effects=["C"]), dict(site_id="B", anchor_id="x", effects=["S"])],
             backend=dict(name="independent mock native export", tie_policy="min_time_then_actual_length_then_first_discovery",
                          direction_policy="forward_per_source_v1", source_sha256={"router.cpp": hashlib.sha256(b"router").hexdigest()}),
             source_sha256={"graph.bin": hashlib.sha256(b"graph").hexdigest()},
             selection_certificate_sha256="1"*64, hierarchy_sha256="2"*64,
             legs=[dict(source_anchor=a, target_anchor=b, reachable=True,
                        time_s=encoded(0.0 if a == b else 10.0), actual_length_m=encoded(0.0 if a == b else 10.0),
                        label_direction="identity" if a == b else "forward_from_source") for a in anchors for b in anchors])
    for a, b, t, length in (("o","x",1.0,1.0),("x","z",1.0,4.0),("o","z",1.0,20.0)):
        pair(p,a,b).update(time_s=encoded(t), actual_length_m=encoded(length))
    return p


def pair(p,a,b):
    return next(row for row in p["legs"] if (row["source_anchor"],row["target_anchor"]) == (a,b))


def load(p):
    raw=json.dumps(p,sort_keys=True,separators=(",",":")).encode()
    return IndependentLegTable.from_bytes(raw,hashlib.sha256(raw).hexdigest())


def query():
    return dict(case_id="independent_colocation_mock",H_ref=2,origin="o",destination="z",start_time_s=0,
                initial_energy_kwh=2,capacity_kwh=10,minimum_energy_kwh=0,reserve_kwh=0,
                consumption_kwh_per_m=1,overhead_s=1,lambda_stop_s=0,
                charging_segments=[[0,10,1,0]],schedule=dict(a=0,b=100,D=2))


def test_lossless_binary64_and_signed_zero():
    for value in (0.0,-0.0,0.1,0.1+0.2,float.fromhex("0x0.0000000000001p-1022"),1e200):
        exact, retained=decode_binary64(encoded(value))
        assert exact == R(*value.as_integer_ratio()) and retained == value.hex()
    assert decode_binary64(encoded(0.1))[0] != R(1,10)
    p=payload();pair(p,"x","x")["time_s"]=encoded(-0.0)
    assert load(p).pair("x","x").time_hex == (-0.0).hex()


@pytest.mark.parametrize("edit",[
    lambda p: p.update(edges=[]),
    lambda p: p.update(anchors="oxz"),
    lambda p: p.update(origin_anchor=[]),
    lambda p: p["sites"][0].update(anchor_id=[]),
    lambda p: p["sites"][0].update(effects="CS"),
    lambda p: p["legs"].append(deepcopy(p["legs"][0])),
    lambda p: p["legs"].pop(),
    lambda p: pair(p,"o","x").update(reachable=1),
    lambda p: pair(p,"o","x").update(time_s=encoded(0.0)),
    lambda p: pair(p,"o","x").update(label_direction="reverse_from_target"),
    lambda p: pair(p,"o","x")["time_s"].update(ratio=["1","10"]),
    lambda p: pair(p,"o","x")["time_s"].update(ratio=[True,"1"]),
    lambda p: p["backend"].update(tie_policy="time_then_node_path"),
    lambda p: p.update(selection_certificate_sha256="bad"),
    lambda p: pair(p,"o","z").update(reachable=False,time_s=None,actual_length_m=None),
])
def test_independent_parser_rejects_bad_contract(edit):
    p=payload();edit(p)
    with pytest.raises(InvalidInput):load(p)


def test_payload_hash_duplicate_keys_and_deep_immutability():
    p=payload();raw=json.dumps(p).encode()
    with pytest.raises(InvalidInput,match="SHA256"):
        IndependentLegTable.from_bytes(raw,"0"*64)
    raw=raw.replace(b'"origin_anchor": "o"',b'"origin_anchor": "x", "origin_anchor": "o"')
    with pytest.raises(InvalidInput,match="Duplicate"):
        IndependentLegTable.from_bytes(raw,hashlib.sha256(raw).hexdigest())
    table=load(p)
    with pytest.raises(TypeError):table.sites["extra"]=table.sites["A"]
    with pytest.raises(FrozenInstanceError):table.sites["A"].anchor_id="z"


def test_coattached_site_actions_and_zero_drive_remain_distinct():
    result=solve_real_case(query(),load(payload()))
    assert result["all_regimes_certified"]
    winner=result["result"]
    assert winner["lex_key"] == (R(9),R(3),2,(("A","C"),("B","S")))
    assert winner["route_legs"][1].time == winner["route_legs"][1].energy == 0
    assert winner["route_legs"][1].source_road_anchor == winner["route_legs"][1].target_road_anchor == "x"
    assert winner["route_legs"][1].label_direction == "identity"
    assert [event["site"] for event in winner["events"]] == ["A","B"]
    assert replay_real_witness(query(),load(payload()),winner["site_action_tuple"],winner["charges"])["lex_key"] == winner["lex_key"]
    assert result["tree_independent"]


def test_unequal_length_equal_time_table_choice_is_never_rerouted():
    p=payload();p["sites"]=[]
    pair(p,"o","z").update(time_s=encoded(2.0),actual_length_m=encoded(9.0))
    pair(p,"x","z")["actual_length_m"]=encoded(1.0)
    q=query();q.update(H_ref=0,schedule=None,charging_segments=[])
    table=load(p)
    assert table.pair("o","z").time == table.pair("o","x").time+table.pair("x","z").time
    assert table.pair("o","z").actual_length == 9
    assert solve_real_case(q,table)["result"]["status"] == "infeasible_within_H_ref"
    with pytest.raises(InvalidInput,match="terminal reserve"):replay_real_witness(q,table,(),())


def test_rounded_nonmetric_totals_and_explicit_direction_are_retained():
    p=payload()
    for a,b,t in (("o","x",0.1),("x","z",0.2),("o","z",0.1+0.2)):
        pair(p,a,b)["time_s"]=encoded(t)
    p["backend"]["direction_policy"]="explicit_per_leg_v1"
    pair(p,"o","x")["label_direction"]="reverse_from_target"
    table=load(p)
    assert table.pair("o","z").time > table.pair("o","x").time+table.pair("x","z").time
    assert table.pair("o","x").label_direction == "reverse_from_target"


def test_terminal_rule_uses_road_anchor_not_site_text():
    p=payload();p["sites"]=[dict(site_id="at_z",anchor_id="z",effects=["S"]),dict(site_id="z",anchor_id="x",effects=["S"])]
    pair(p,"x","z")["actual_length_m"]=encoded(1.0)
    q=query();q["charging_segments"]=[]
    table=load(p);result=solve_real_case(q,table)
    assert result["result"]["site_action_tuple"] == (("z","S"),)
    assert result["result"]["J"] == 5
    assert result["preflight"]["terminal_excluded_sites"] == ("at_z",)
    with pytest.raises(InvalidInput):replay_real_witness(q,table,(("at_z","S"),),())
    p["origin_anchor"]="z";q["origin"]="z"
    assert solve_real_case(q,load(p))["result"]["status"] == "infeasible_within_H_ref"
    q["schedule"]=None
    assert solve_real_case(q,load(p))["result"]["lex_key"] == (0,0,0,())


def test_explicit_unreachable_pair_and_boolean_transitivity():
    p=payload()
    for a,b in (("x","o"),("z","o"),("z","x")):
        pair(p,a,b).update(reachable=False,time_s=None,actual_length_m=None)
    table=load(p)
    assert not table.pair("z","o").reachable and table.pair("z","o").time is None
    assert solve_real_case(query(),table)["result"]["lex_key"] == (9,3,2,(("A","C"),("B","S")))


def test_terminal_energy_exclusion_does_not_delete_feasible_charging_subtree():
    p=payload();q=query();q["schedule"]=None
    table=load(p);preflight=estimate_real_regimes(q,table)
    assert any(e["reason"]=="terminal_consumption_exceeds_reserve_budget" and not e["subtree_excluded"] for e in preflight["exclusions"])
    result=solve_real_case(q,table)
    assert result["result"]["lex_key"] == (6,3,1,(("A","C"),))


def test_origin_and_interstop_energy_exclusions_are_exact():
    p=payload();q=query()
    pair(p,"o","x")["actual_length_m"]=encoded(3.0)
    preflight=estimate_real_regimes(q,load(p))
    reasons=preflight["counts"]["exclusions_by_reason"]
    assert reasons["origin_consumption_exceeds_initial_budget"] == 2
    assert preflight["counts"]["continuous_regimes"] == 0
    for e in preflight["exclusions"]:
        if "exact_strict_excess" in e:assert e["exact_strict_excess"] > 0


def test_real_ref_has_no_tree_or_production_dependency():
    p=payload();a=solve_real_case(query(),load(p))["result"]["lex_key"]
    p["hierarchy_sha256"]="3"*64
    b=solve_real_case(query(),load(p))["result"]["lex_key"]
    assert a == b
    import ast
    package=Path(__file__).resolve().parents[1]/"validation/reference5"
    for file in package.glob("*.py"):
        for node in ast.walk(ast.parse(file.read_text())):
            if isinstance(node,ast.ImportFrom):assert not (node.module or "").startswith(("timecut5","stopplan4r"))
            if isinstance(node,ast.Import):assert all(not item.name.startswith(("timecut5","stopplan4r")) for item in node.names)


def test_explicit_resource_budget_blocks_before_lp(monkeypatch):
    import validation.reference5.solver as kernel
    monkeypatch.setattr(kernel,"exact_lp",lambda *a,**k: (_ for _ in ()).throw(AssertionError("LP must not run")))
    result=solve_real_case(query(),load(payload()),regime_limit=0)
    assert result["result"]["status"] == "unresolved" and not result["optimization_started"]


def test_source_claims_require_explicit_local_verification(tmp_path):
    table=load(payload());assert not verify_source_files(table,{})["complete"]
    graph,router=tmp_path/"graph",tmp_path/"router"
    graph.write_bytes(b"graph");router.write_bytes(b"router")
    assert verify_source_files(table,{"graph.bin":graph,"router.cpp":router})["complete"]
    router.write_bytes(b"modified")
    assert verify_source_files(table,{"graph.bin":graph,"router.cpp":router})["mismatched"] == ["router.cpp"]


def test_interstop_capacity_and_unreachable_subtree_certificates():
    p=payload();p["anchors"].append("y")
    p["sites"].append(dict(site_id="D",anchor_id="y",effects=["C"]))
    for a in p["anchors"]:
        for b in p["anchors"]:
            if "y" not in (a,b):continue
            p["legs"].append(dict(source_anchor=a,target_anchor=b,reachable=True,
                                  time_s=encoded(0.0 if a==b else 1.0),
                                  actual_length_m=encoded(0.0 if a==b else 11.0),
                                  label_direction="identity" if a==b else "forward_from_source"))
    preflight=estimate_real_regimes(query(),load(p))
    assert preflight["counts"]["exclusions_by_reason"]["inter_stop_consumption_exceeds_capacity_budget"] > 0
    certificate=next(e for e in preflight["exclusions"] if e["reason"]=="inter_stop_consumption_exceeds_capacity_budget")
    assert certificate["consumption_kwh"] == 11 and certificate["capacity_limit_kwh"] == 10
    assert certificate["subtree_excluded"]
    p=payload()
    for a in ("o","z"):
        pair(p,a,"x").update(reachable=False,time_s=None,actual_length_m=None)
    preflight=estimate_real_regimes(query(),load(p))
    assert preflight["counts"]["exclusions_by_reason"]["road_inbound_unreachable"] == 2
    assert preflight["counts"]["continuous_regimes"] == 0


def test_exact_energy_boundary_is_not_excluded():
    p=payload();pair(p,"o","x")["actual_length_m"]=encoded(2.0)
    result=solve_real_case(query(),load(p))
    assert result["result"]["lex_key"] == (10,4,2,(("A","C"),("B","S")))
    assert "origin_consumption_exceeds_initial_budget" not in result["preflight"]["counts"]["exclusions_by_reason"]


def test_resolved_state_mapping_verifies_binary64_baseline_soc_and_windows():
    from validation.reference5.real_solver import query_from_resolved_state
    p=payload();mapping={"o":"road:1","x":"road:2","z":"road:3"}
    p["anchors"]=[mapping[a] for a in p["anchors"]]
    p["origin_anchor"],p["destination_anchor"]="road:1","road:3"
    for site in p["sites"]:site["anchor_id"]=mapping[site["anchor_id"]]
    for row in p["legs"]:
        row["source_anchor"],row["target_anchor"]=mapping[row["source_anchor"]],mapping[row["target_anchor"]]
    table=load(p)
    state=dict(state_id="mock_C",pool_id="mock_pool",H_ref=2,origin_road_anchor=1,destination_road_anchor=3,
               immutable_direct_leg_table=dict(sha256=table.payload_sha256),accepted_baseline_time_s=encoded(1.0),
               accepted_baseline_actual_length_m=encoded(20.0),mode="energy_only",schedule=None,
               initial_energy_kwh="2",initial_soc="1/5",capacity_kwh="10",energy_floor_kwh="0",
               terminal_reserve_kwh="0",consumption_kwh_per_m="1",overhead_s="1",stop_penalty_s="0",start_time_s="0",
               charging_primitive=dict(energy_breakpoints_kwh=["0","10"],slopes_s_per_kwh=["1"],intercepts_s=["0"]))
    q=query_from_resolved_state(state,table)
    assert q["origin"]=="road:1" and q["initial_energy_kwh"]==2 and q["schedule"] is None
    state["mode"]="energy_and_scheduled"
    state["schedule"]=dict(baseline_binary64=encoded(1.0),baseline_time_s="1",window_start_s="2/5",window_end_s="7/10",duration_s="2")
    q=query_from_resolved_state(state,table)
    assert q["schedule"]==dict(a=R(2,5),b=R(7,10),D="2")
    state["schedule"]["window_start_s"]="1/2"
    with pytest.raises(InvalidInput,match="window arithmetic"):query_from_resolved_state(state,table)
    state["schedule"]["window_start_s"]="2/5";state["initial_soc"]="1/4"
    with pytest.raises(InvalidInput,match="SOC"):query_from_resolved_state(state,table)
