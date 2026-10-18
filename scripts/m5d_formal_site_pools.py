"""Select nested capability-typed Site pools for all frozen ODs before solving."""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
import pandas as pd

from m5d_fixed_od_pool import vdc


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(slate_path, geo_path, sites_path, output):
    slate=json.loads(slate_path.read_text());geo=json.loads(geo_path.read_text())
    if (slate["schema"]!="hiroute.m5d.fixed_12od_candidate_slate.v1" or
        geo["schema"]!="hiroute.m5d.geographic_screen.v1" or
        sha(sites_path)!=geo["sites_sha256"]):
        raise ValueError("Frozen Site/OD source mismatch")
    locations={row["site_id"]:row for row in geo["fixed_grid_candidates"]}
    frame=pd.read_parquet(sites_path,columns=["site_id","access_node","lat","lon",
        "transport_capabilities","meal_count"])
    all_sites=[]
    for row in frame.itertuples(index=False):
        if pd.isna(row.access_node):continue
        charge=isinstance(row.transport_capabilities,(list,tuple,np.ndarray)) and "charge" in row.transport_capabilities
        meal=pd.notna(row.meal_count) and row.meal_count>=1
        if not charge and not meal:continue
        effects=(["C"] if charge else [])+(["S"] if meal else [])+(["CS"] if charge and meal else [])
        all_sites.append((str(row.site_id),int(row.access_node),float(row.lat),float(row.lon),effects))
    pools=[]
    for od in slate["od"]:
        origin,dest=locations[od["origin_site"]],locations[od["destination_site"]]
        lat0=(float(origin["lat"])+float(dest["lat"]))/2
        sx=111320*math.cos(math.radians(lat0));sy=111320
        dx=(float(dest["lon"])-float(origin["lon"]))*sx
        dy=(float(dest["lat"])-float(origin["lat"]))*sy
        squared=dx*dx+dy*dy;segment=math.sqrt(squared)
        if squared<=0:raise ValueError("Zero OD chord")
        choices=[]
        for site_id,node,lat,lon,effects in all_sites:
            if site_id in (od["origin_site"],od["destination_site"]) or node in (od["origin_anchor"],od["destination_anchor"]):continue
            x=(lon-float(origin["lon"]))*sx;y=(lat-float(origin["lat"]))*sy
            progress=(x*dx+y*dy)/squared
            if not 0<progress<1:continue
            perpendicular=abs(x*dy-y*dx)/segment
            choices.append((site_id,node,progress,perpendicular,effects))
        radius=next((r for r in (25000,50000,100000,200000) if sum(row[3]<=r for row in choices)>=128),None)
        if radius is None:raise ValueError(f"{od['od_id']} lacks 128 capable Sites")
        eligible=[row for row in choices if row[3]<=radius]
        chosen=[];used=set()
        if (sum("C" in row[4] for row in eligible)<64 or
            sum("S" in row[4] for row in eligible)<64):
            raise ValueError(f"{od['od_id']} lacks 64 Sites per capability")
        for ordinal in range(1,129):
            target=vdc(ordinal)
            # Uniform capability balance for each nested prefix. CS qualifies
            # in either slot, and identities are never duplicated.
            required="C" if ordinal%2 else "S"
            row=min((r for r in eligible if r[0] not in used and required in r[4]),
                key=lambda r:(abs(r[2]-target)+r[3]/segment,r[3],r[0]))
            used.add(row[0]);chosen.append({"site_id":row[0],"anchor_id":f"road:{row[1]}",
                "access_node":row[1],"effects":row[4],"progress":row[2],"perpendicular_m":row[3]})
        pools.append({"od_id":od["od_id"],"origin_anchor":od["origin_anchor"],
            "destination_anchor":od["destination_anchor"],"radius_m":radius,
            "eligible_capable_site_count":len(eligible),"sites":chosen,
            "prefix_sizes":[8,16,32,128],
            "first32_charge_count":sum("C" in s["effects"] for s in chosen[:32]),
            "first32_meal_count":sum("S" in s["effects"] for s in chosen[:32])})
    result={"schema":"hiroute.m5d.formal_capability_pools.v1",
        "status":"preregistration_input_candidate_no_route_or_solver_outputs",
        "slate_sha256":sha(slate_path),"geographic_sha256":sha(geo_path),
        "site_catalog_sha256":sha(sites_path),
        "selection_rule":"odd_ordinal_C_even_ordinal_S_then_uniform_vdc_progress_plus_perpendicular_and_site_id_tie;CS_eligible_both;distinct_identity",
        "meal_rule":"meal_count_at_least_1;toilet_count_not_meal",
        "pools":pools}
    with output.open("x") as f:
        json.dump(result,f,sort_keys=True,indent=2,allow_nan=False);f.write("\n")
    print(json.dumps({"pool_count":len(pools),"first32_counts":[(p["od_id"],p["first32_charge_count"],p["first32_meal_count"]) for p in pools]}))


if __name__=="__main__":
    run(*(Path(x) for x in sys.argv[1:5]))
