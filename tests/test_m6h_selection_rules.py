"""Synthetic-only tests: never open an actual new OD/catalog/graph."""
import copy
import importlib.util
from pathlib import Path
import random

import pytest

SPEC = importlib.util.spec_from_file_location("m6h_selection_rules", Path(__file__).resolve().parents[1] /
    "experiments/m6h_selection_v1/rules.py")
rules = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rules)


def site(i, lat=0.1, lon=0.1, charge=True, meal=1, node=None):
    return dict(site_id=f"s{i:04}", access_node=i if node is None else node,
                lat=lat, lon=lon, transport_capabilities=["charge"] if charge else [], meal_count=meal)


def registry():
    return dict(schema="hiroute.m6h.exposure_registry.v1", coverage=dict(status="complete",
        scope="recovered_project_development_artifacts", known_missing_artifacts=[],
        reviewer="synthetic-test", included_categories=["all_geographic_screens", "all_route_screen_pairs",
        "all_dev_queries", "all_diagnostics", "all_candidate_selection"]),
        sources=[dict(source_id="synthetic", sha256="0"*64)],
        records=[dict(source_id="synthetic", reason="DEV", origin=site(9998, -40, -40),
                      destination=site(9999, -30, -30))], inspected_endpoints=[])


def select(rows, exposure=None):
    return rules.select_od_slate(rows, registry() if exposure is None else exposure,
                                 site_catalog_sha256="a"*64)


def test_selection_is_order_invariant_and_six_groups():
    rows = [site(i, lon=i*2+0.1) for i in range(16)]
    first = select(rows)
    random.Random(17).shuffle(rows)
    assert first == select(rows)
    assert first["status"] == "SELECTED"
    assert len(first["od"]) == 6
    assert not first["statistical_independence_claim"]
    assert [x["od_id"] for x in first["od"]] == [f"HOD{i:02}" for i in range(6)]
    assert len({n for x in first["od"] for n in (x["origin_anchor"],x["destination_anchor"])}) == 12


def test_reversed_and_neighbor_exposures_excluded():
    rows = [site(i, lon=i*2+0.1) for i in range(16)]
    first = select(rows)["od"][0]
    exposure = registry()
    exposure["records"].append(dict(source_id="synthetic", reason="route screened", origin=
        site(8001, lat=first["destination"]["lat"]+0.5, lon=first["destination"]["lon"]),
        destination=site(8002, lat=first["origin"]["lat"]+0.5, lon=first["origin"]["lon"])))
    selected = select(rows, exposure)
    assert all(not rules.groups_near(rules.group(x["origin"],x["destination"]),
        rules.group(exposure["records"][-1]["origin"],exposure["records"][-1]["destination"])) for x in selected["od"])


def test_no_representative_replacement_after_exposure():
    rows = [site(1),site(2),site(3,lon=3)]
    exposure = registry()
    exposure["inspected_endpoints"].append(dict(source_id="synthetic", reason="geographic screen", endpoint=site(1)))
    got = select(rows, exposure)
    assert got["status"] == "DATA_LIMITED" and got["od"] == []


@pytest.mark.parametrize("field,value", [("known_missing_artifacts",["missing.json"]), ("status","partial"),
    ("scope","all_external_history")])
def test_incomplete_registry_blocks(field,value):
    exposure=registry();exposure["coverage"][field]=value
    with pytest.raises(rules.InvalidInput): select([],exposure)


def test_duplicate_null_anchor_identity_and_invalid_numeric_fail_closed():
    a=site(1); a["access_node"]=None
    with pytest.raises(rules.InvalidInput): select([a,a])
    for value in [float("nan"),float("inf"),True]:
        a=site(1);a["lat"]=value
        with pytest.raises(rules.InvalidInput):select([a])
    assert select([dict(site(1),access_node=None)])["selected_group_count"] == 0


def test_fixed_enumeration_bound():
    rows=[site(i,lat=-70+(i//100),lon=-150+(i%100)) for i in range(513)]
    with pytest.raises(rules.InvalidInput,match="512"):select(rows)


def pool_rows():
    return [site(i+10,lat=0,lon=(i+1)/140,charge=i%2==0,meal=0 if i%2==0 else 1) for i in range(128)]


def pool(rows):
    return rules.build_capability_pool(site(1,lat=0,lon=0),site(2,lat=0,lon=1),rows,od_id="HOD00")


def test_pool_recipe_matches_literal_original_rank():
    rows=pool_rows();got=pool(rows)
    assert got["prefix_sizes"] == [8,32,128]
    assert len(got["sites"]) == 128
    used=set()
    # For this equatorial straight-line fixture progress is exactly the original
    # expression, rather than assuming algebraically equivalent lon arithmetic.
    for ordinal,out in enumerate(got["sites"],1):
        capability="C" if ordinal%2 else "S"
        available=[r for r in rows if r["site_id"] not in used and
                   ((capability=="C" and "charge" in r["transport_capabilities"]) or
                    (capability=="S" and r["meal_count"]>=1))]
        expected=min(available,key=lambda r:(abs((r["lon"]*111320*111320)/(111320*111320)-rules.vdc(ordinal)),0,r["site_id"]))
        assert out["site_id"] == expected["site_id"]
        used.add(out["site_id"])
    assert got == pool(list(reversed(rows)))


def test_first_radius_no_capability_repair_and_toilet_not_meal():
    rows=[site(i+10,lat=0,lon=(i+1)/140,meal=0) for i in range(128)]
    rows += [site(i+500,lat=.3,lon=(i+1)/70,charge=False,meal=1) for i in range(64)]
    with pytest.raises(rules.PoolFailure,match="FIRST_RADIUS"):pool(rows)
    rows=pool_rows()
    for r in rows:r["meal_count"]=0;r["toilet_count"]=1
    with pytest.raises(rules.PoolFailure):pool(rows)


def test_cs_same_anchor_sites_and_endpoint_anchor_exclusion():
    rows=[site(i+10,lat=0,lon=(i+1)/140,node=500,meal=1) for i in range(128)]
    got=pool(rows)
    assert all(x["effects"]==["C","S","CS"] for x in got["sites"])
    rows[0]["access_node"]=1
    with pytest.raises(rules.PoolFailure,match="INSUFFICIENT_CAPABLE"):pool(rows)


def test_pool_failure_cannot_change_preselected_slate():
    slate=select([site(i,lon=i*2+.1) for i in range(16)])
    before=copy.deepcopy(slate)
    for od in slate["od"]:
        with pytest.raises(rules.PoolFailure):rules.build_capability_pool(od["origin"],od["destination"],[],od_id=od["od_id"])
    assert slate == before


def test_neighbor_hash_lookup_matches_pairwise_definition():
    known={((0,0),(3,4)),((5,6),(1,2))}
    known={tuple(sorted(x)) for x in known}
    for a in range(-2,8):
        for b in range(-2,8):
            g=tuple(sorted(((a,b),(4,5))))
            assert rules._has_near_group(g,known) == any(rules.groups_near(g,k) for k in known)


def test_exact_equality_to_original_formal_generator(tmp_path, monkeypatch):
    """Execute original source only against synthetic local parquet/JSON."""
    import hashlib
    import json
    import sys
    import pandas as pd
    root=Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(root/'scripts'))
    original_spec=importlib.util.spec_from_file_location('original_formal',root/'scripts/m5d_formal_site_pools.py')
    original=importlib.util.module_from_spec(original_spec);original_spec.loader.exec_module(original)
    rows=pool_rows()+[site(700+i,lat=.03,lon=(i+1)/140,meal=1) for i in range(128)]
    sites=tmp_path/'sites.parquet';pd.DataFrame(rows).to_parquet(sites)
    origin,destination=site(1,lat=0,lon=0),site(2,lat=0,lon=1)
    slate=tmp_path/'slate.json';geo=tmp_path/'geo.json';out=tmp_path/'pool.json'
    slate.write_text(json.dumps(dict(schema='hiroute.m5d.fixed_12od_candidate_slate.v1',od=[dict(
        od_id='HOD00',origin_site=origin['site_id'],destination_site=destination['site_id'],origin_anchor=1,destination_anchor=2)])))
    geo.write_text(json.dumps(dict(schema='hiroute.m5d.geographic_screen.v1',sites_sha256=hashlib.sha256(sites.read_bytes()).hexdigest(),fixed_grid_candidates=[origin,destination])))
    original.run(slate,geo,sites,out)
    old=json.loads(out.read_text())['pools'][0];new=pool(rows)
    for field in ['od_id','origin_anchor','destination_anchor','radius_m','eligible_capable_site_count','sites']:
        assert old[field] == new[field]
