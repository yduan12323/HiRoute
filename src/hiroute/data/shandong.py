"""Shandong raw-PBF road ingestion primitives.
Optional runtime dependencies: pyrosm, pandas, and osmium for raw-way policy.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from hashlib import sha256
from pathlib import Path
from typing import Any
from time import perf_counter
import json, re
from .raw_way_policy import RawWay, read_raw_way_policy
@dataclass(frozen=True)
class RawRoadGraph:
    source_sha256: str
    source_bytes: int
    nodes: tuple[dict[str, Any], ...]
    edges: tuple[dict[str, Any], ...]
    policy_id: str
    audit: dict[str, int]
def _canonical_id(value):
    raw=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    return sha256(raw).hexdigest()
def _tag(value):
    if value is None or (isinstance(value,float) and value!=value): return None
    if isinstance(value,(list,tuple,dict)): raise ValueError("ambiguous raw OSM tag")
    s=str(value).strip()
    return s or None
def _posted_speed(value,model):
    if value is None: return None
    if value in model.get("symbolic_maxspeed_kph",{}): return Decimal(str(model["symbolic_maxspeed_kph"][value]))
    vals=[]
    for part in value.split(";"):
        m=re.fullmatch(r"(\d+(?:\.\d+)?)\s*(mph|km/h|kmh|kph)?",part.strip(),re.I)
        if not m: return None
        speed=Decimal(m.group(1))
        if m.group(2) and m.group(2).lower()=="mph": speed*=Decimal(str(model["mph_to_kph"]))
        if speed<=0 or speed>300: return None
        vals.append(speed)
    return min(vals) if vals else None

def _highway_exclusion_reason(raw_highway, way_id, routing, raw_way_policy):
    """Apply the approved exact highway policy before access or direction handling."""
    highway = _tag(raw_highway)
    if highway is None or raw_highway != highway:
        raise ValueError(f"unsupported/unproven highway class {raw_highway!r}")
    model, policy = routing["speed_model"], routing["access"]
    # highway=yes is never generic: require exact raw tags, original refs, and
    # the exact Pyrosm segment way ID, or fail closed.
    if highway == "yes":
        evidence = (raw_way_policy or {}).get(int(way_id))
        if (policy.get("exclude_closed_shelter_contour") is True
                and isinstance(evidence, RawWay)
                and evidence.is_closed_shelter_contour()):
            return "closed_shelter_contour"
        raise ValueError(f"unsupported/unproven highway class {highway!r}")
    if highway in set(policy["excluded_highway"]):
        return "street_lamp" if highway == "street_lamp" else "excluded_highway"
    if highway not in model["class_kph"]:
        raise ValueError(f"unsupported/unproven highway class {highway!r}")
    return None

def read_shandong_pbf(path,routing,*,expected_sha256=None,boundary_path=None,expected_boundary_sha256=None,projection=None,reader_engine="out_of_core"):
    """Hash raw bytes, then parse unsimplified driving edges under frozen policy."""
    p=Path(path)
    if not p.is_file(): raise FileNotFoundError(p)
    digest,size=sha256(),0
    with p.open("rb") as f:
        for block in iter(lambda:f.read(1048576),b""): digest.update(block); size+=len(block)
    source_hash=digest.hexdigest()
    if expected_sha256 and source_hash!=expected_sha256: raise ValueError("raw PBF SHA-256 mismatch")
    if routing.get("network_type")!="driving" or routing.get("simplify") is not False or routing.get("retain_all_components") is not True:
        raise ValueError("requires unsimplified driving and all components")
    if reader_engine not in ("in_memory","out_of_core"): raise ValueError("unsupported Pyrosm reader engine")
    policy = routing["access"]
    raw_policy_started = perf_counter()
    if policy.get("exclude_closed_shelter_contour") is True:
        try:
            raw_way_policy = read_raw_way_policy(p)
        except ImportError as exc:
            raise RuntimeError("osmium is required for the approved raw-way policy") from exc
    else:
        raw_way_policy = {}
    raw_policy_scan_ms = int(round((perf_counter() - raw_policy_started) * 1000))
    try: from pyrosm import OSM
    except ImportError as exc: raise RuntimeError("pyrosm is required") from exc
    attrs=["maxspeed:forward","maxspeed:backward","oneway:motorcar","oneway:motor_vehicle","motorcar","motor_vehicle","vehicle","access","access:conditional","vehicle:conditional","motor_vehicle:conditional","motorcar:conditional","oneway:conditional","junction"]
    nodes_df,edges_df=OSM(str(p), engine=reader_engine, workers=1).get_network(network_type="driving",nodes=True,extra_attributes=attrs)
    model,policy=routing["speed_model"],routing["access"]
    classes,allowed=model["class_kph"],set(policy["allowed"])
    audit={"parsed_segments":int(len(edges_df)),"excluded_policy":0,"excluded_street_lamp":0,
           "excluded_street_lamp_ways":0,"excluded_closed_shelter_contour":0,
           "excluded_closed_shelter_contour_ways":0,"raw_highway_yes_candidate_ways":len(raw_way_policy),
           "raw_way_policy_scan_milliseconds":raw_policy_scan_ms,"directed_edges":0,"nodes":0}
    excluded_lamp_way_ids=set()
    excluded_shelter_way_ids=set()
    node_rows=[]
    for values in nodes_df.itertuples(index=False, name=None):
        row=dict(zip(nodes_df.columns, values))
        geom=row["geometry"]
        node_rows.append({"node_id":str(int(row["id"])),"lat":float(geom.y),"lon":float(geom.x)})
    node_coordinates={n["node_id"]:(n["lon"],n["lat"]) for n in node_rows}
    boundary=None
    boundary_hash=None
    if boundary_path is not None:
        if not expected_boundary_sha256 or not projection:
            raise ValueError("boundary clipping requires a frozen SHA-256 and projection")
        from hiroute.data.shandong_spatial import read_osm_poly
        boundary=read_osm_poly(boundary_path,expected_sha256=expected_boundary_sha256)
        boundary_hash=expected_boundary_sha256
    elif expected_boundary_sha256 is not None or projection is not None:
        raise ValueError("boundary path, digest and projection must be supplied together")
    clip_context = None
    clip_line_segments_fn = None
    make_clip_context_fn = None
    audit["clipped_segments"]=0
    audit["clip_nodes"]=0
    audit["outside_segments"]=0
    edge_rows=[]
    for values in edges_df.itertuples(index=False, name=None):
        row=dict(zip(edges_df.columns, values))
        way_id=int(row["id"])
        highway=_tag(row.get("highway"))
        exclusion_reason=_highway_exclusion_reason(row.get("highway"),way_id,routing,raw_way_policy)
        if exclusion_reason is not None:
            audit["excluded_policy"]+=1
            if exclusion_reason=="closed_shelter_contour":
                audit["excluded_closed_shelter_contour"]+=1
                excluded_shelter_way_ids.add(way_id)
            elif exclusion_reason=="street_lamp":
                audit["excluded_street_lamp"]+=1
                excluded_lamp_way_ids.add(way_id)
            continue
        vals={k:_tag(row.get(k)) for k in attrs}
        access=next((vals[k] for k in ("motorcar","motor_vehicle","vehicle","access") if vals[k]),None)
        if access and access not in allowed: audit["excluded_policy"]+=1; continue
        if policy.get("exclude_conditional_access") and any(vals[k] for k in attrs if k.endswith(":conditional") and k!="oneway:conditional"):
            audit["excluded_policy"]+=1; continue
        if policy.get("exclude_conditional_oneway") and vals["oneway:conditional"]: audit["excluded_policy"]+=1; continue
        oneway=vals["oneway:motorcar"] or vals["oneway:motor_vehicle"] or _tag(row.get("oneway"))
        if oneway is None: oneway="yes" if vals["junction"]=="roundabout" or highway=="motorway" else "no"
        if oneway in ("yes","true","1"): directions=(1,)
        elif oneway in ("-1","reverse"): directions=(-1,)
        elif oneway in ("no","false","0"): directions=(1,-1)
        else: audit["excluded_policy"]+=1; continue
        length=Decimal(str(row["length"]))
        if not length.is_finite() or length<=0: audit["excluded_policy"]+=1; continue
        u,v=str(int(row["u"])),str(int(row["v"]))
        if boundary is None:
            segments=({"segment_index":0,"source":u,"target":v,"length_m":Fraction(length),"fraction":Fraction(1)},)
        else:
            if clip_line_segments_fn is None:
                from hiroute.data.shandong_spatial import (
                    clip_line_segments as clip_line_segments_fn,
                    make_line_clip_context as make_clip_context_fn,
                )
            if clip_context is None:
                clip_context = make_clip_context_fn(boundary, projection)
            segments,new_nodes=clip_line_segments_fn(row["geometry"],boundary,projection,
                osm_way_id=str(int(row["id"])),source_node_id=u,target_node_id=v,
                node_coordinates=node_coordinates,full_length_m=length,context=clip_context)
            node_rows.extend(n for n in new_nodes if n["node_id"] not in node_coordinates)
            node_coordinates.update({n["node_id"]:(n["lon"],n["lat"]) for n in new_nodes})
            audit["clip_nodes"]+=len(new_nodes)
            audit["clipped_segments"]+=len(segments)
            if not segments: audit["outside_segments"]+=1
        for direction in directions:
            reverse=direction<0
            speed_tag=vals["maxspeed:backward" if reverse else "maxspeed:forward"] or _tag(row.get("maxspeed"))
            posted=_posted_speed(speed_tag,model)
            speed=min(Decimal(str(classes[highway])),posted) if posted is not None else Decimal(str(classes[highway]))
            speed=min(Decimal(str(model["max_kph"])),max(Decimal(str(model["min_kph"])),speed))
            for segment in segments:
                src,dst=(segment["target"],segment["source"]) if reverse else (segment["source"],segment["target"])
                segment_length=Fraction(segment["length_m"])
                travel=segment_length*Fraction(Decimal("3.6"))/Fraction(speed)
                clip_suffix=f":clip:{segment['segment_index']}" if boundary is not None else ""
                edge_rows.append({"edge_id":f"way:{int(row['id'])}:{src}>{dst}{clip_suffix}","source":src,"target":dst,"length_m":str(segment_length),"time_s":str(travel),"osm_way_id":str(int(row["id"])),"direction":direction,"highway":highway,"speed_kph":str(speed),"original_source":u,"original_target":v,"clipped_fraction":str(segment["fraction"]),"boundary_sha256":boundary_hash})
    audit["excluded_street_lamp_ways"]=len(excluded_lamp_way_ids)
    audit["excluded_closed_shelter_contour_ways"]=len(excluded_shelter_way_ids)
    used={e["source"] for e in edge_rows}|{e["target"] for e in edge_rows}
    def node_key(node):
        value=node["node_id"]
        return (0,int(value)) if str(value).isdigit() else (1,str(value))
    nodes=tuple(sorted((n for n in node_rows if n["node_id"] in used),key=node_key))
    audit["nodes"],audit["directed_edges"]=len(nodes),len(edge_rows)
    if not edge_rows: raise ValueError("raw PBF produced no supported edges")
    policy_id=_canonical_id({"routing":routing,"reader":"pyrosm-network-v1","geometry":"pyrosm-length-v1","road_admission":"approved-closed-shelter-contour-v1","raw_way_evidence":"original-tags-and-ordered-node-refs-v1","boundary_sha256":boundary_hash,"projection":projection if boundary is not None else None})
    return RawRoadGraph(source_hash,size,nodes,tuple(edge_rows),policy_id,audit)

@dataclass(frozen=True)
class RawSite:
    site_id: str
    lon: float
    lat: float
    amenity: str
    capabilities: tuple[str,...]
    source_sha256: str
    transport_classes: tuple[str,...]=()
    meal_count_500m: int=0
    geometry_method: str="point_unchanged_v1"


def _representative_wgs84(geom):
    if geom is None or getattr(geom,"is_empty",True): raise ValueError("empty POI geometry")
    kind=geom.geom_type
    if kind in ("Point","MultiPoint"):
        point=geom if kind=="Point" else geom.representative_point()
        method="point_unchanged_v1" if kind=="Point" else "multipoint_representative_v1"
    elif kind in ("LineString","MultiLineString","Polygon","MultiPolygon"):
        from pyproj import Transformer
        from shapely.ops import transform
        project=Transformer.from_crs("EPSG:4326","EPSG:3035",always_xy=True).transform
        back=Transformer.from_crs("EPSG:3035","EPSG:4326",always_xy=True).transform
        projected=transform(project,geom)
        if "Line" in kind:
            point=transform(back,projected.interpolate(0.5,normalized=True)); method="epsg3035_normalized_line_midpoint_v1"
        else:
            point=transform(back,projected.representative_point()); method="epsg3035_point_on_surface_v1"
    else: raise ValueError(f"unsupported POI geometry type: {kind}")
    return float(point.x),float(point.y),method


def _classify_site_record(row,policy):
    tax=policy.get("taxonomy"); tags=row.get("tags")
    if not isinstance(tags,dict): tags={}
    tags={**tags,**{k:row.get(k) for k in ("amenity","tourism","shop","highway","capacity","access") if _tag(row.get(k))}}
    if _tag(tags.get("access")) in set(policy.get("excluded_access",policy.get("exclude_access",["private","no"]))): return (),(),None
    if tax is None:
        amenity=_tag(tags.get("amenity")); caps=tuple(sorted(set(policy.get("amenity_capabilities",{}).get(amenity,()))))
        return caps,(),amenity
    classes=set(); subtypes=[]
    for key,mapping in tax.items():
        val=_tag(tags.get(key))
        if val not in mapping: continue
        if key=="amenity" and val=="parking":
            capacity=_tag(tags.get("capacity"))
            if capacity and capacity.isdigit() and int(capacity)<int(policy.get("parking_min_explicit_capacity",3)): continue
        classes.update(mapping[val]); subtypes.append(f"{key}={val}")
    return tuple(sorted(classes)),tuple(sorted(subtypes)),_tag(tags.get("amenity")) or (subtypes[0] if subtypes else None)


def _action_caps(classes,meal_count):
    out=[]
    if "charge" in classes: out.append("C")
    if meal_count: out.append("S")
    if {"C","S"}<=set(out): out.append("CS")
    return tuple(out)


def _xyz(lon,lat):
    import math
    lon,lat=math.radians(lon),math.radians(lat)
    return math.cos(lat)*math.cos(lon),math.cos(lat)*math.sin(lon),math.sin(lat)


def _meal_support_counts(anchors,meals,radius_m):
    import math
    if not anchors or not meals: return [0]*len(anchors)
    chord=2*math.sin(float(radius_m)/(2*6371008.8))
    cells={}
    for lon,lat in meals:
        q=_xyz(lon,lat); key=tuple(math.floor(x/chord) for x in q); cells.setdefault(key,[]).append(q)
    out=[]
    for lon,lat in anchors:
        q=_xyz(lon,lat); k=tuple(math.floor(x/chord) for x in q)
        nearby=(v for dx in (-2,-1,0,1,2) for dy in (-2,-1,0,1,2) for dz in (-2,-1,0,1,2) for v in cells.get((k[0]+dx,k[1]+dy,k[2]+dz),()))
        out.append(sum(sum((x-y)**2 for x,y in zip(q,v))<=chord*chord+1e-15 for v in nearby))
    return out


def normalize_site_records(records,site_policy,source_sha256,*,boundary=None):
    if not isinstance(source_sha256,str) or not re.fullmatch(r"[0-9a-f]{64}",source_sha256): raise ValueError("invalid source SHA-256")
    from shapely.geometry import Point
    objects={}
    for row in records:
        classes,subtypes,label=_classify_site_record(row,site_policy)
        if not classes and not subtypes: continue
        kind=_tag(row.get("osm_type")) or "node"; oid=_tag(row.get("id"))
        if kind not in ("node","way","relation") or not oid: raise ValueError("POI lacks stable OSM type/id")
        geom=row.get("geometry"); lon,lat,method=_representative_wgs84(geom)
        if boundary is not None and not boundary.covers(geom if geom.geom_type=="Point" else Point(lon,lat)): continue
        rank={"Point":1,"MultiPoint":1,"LineString":2,"MultiLineString":2,"Polygon":3,"MultiPolygon":3}.get(geom.geom_type,0)
        ident=f"{kind}/{oid}"; value=(rank,classes,subtypes,lon,lat,method,label)
        old=objects.get(ident)
        if old is None or rank>old[0]: objects[ident]=value
        elif value[1:3]!=old[1:3]: raise ValueError(f"conflicting OSM tags for identity {ident}")
    rows=[{"id":k,**dict(zip(("rank","classes","subtypes","lon","lat","method","label"),v))} for k,v in sorted(objects.items())]
    meals=[(r["lon"],r["lat"]) for r in rows if "meal" in r["classes"]]
    anchors=[r for r in rows if set(r["classes"]) & {"charge","parking","rest","services"}]
    counts=_meal_support_counts([(r["lon"],r["lat"]) for r in anchors],meals,float(site_policy.get("support_radius_m",500)))
    return tuple(RawSite(r["id"],r["lon"],r["lat"],r["label"] or "transport",_action_caps(r["classes"],n),
        source_sha256,tuple(r["classes"]),n,r["method"]) for r,n in zip(anchors,counts))


def extract_shandong_sites(path,site_policy,*,expected_sha256=None,boundary=None,reader_engine="out_of_core"):
    p=Path(path)
    h=sha256()
    with p.open("rb") as stream:
        for block in iter(lambda: stream.read(1024*1024), b""):
            h.update(block)
    digest=h.hexdigest()
    if expected_sha256 and digest!=expected_sha256: raise ValueError("raw PBF SHA-256 mismatch")
    try: from pyrosm import OSM
    except ImportError as exc: raise RuntimeError("pyrosm is required") from exc
    if reader_engine not in ("in_memory","out_of_core"): raise ValueError("unsupported Pyrosm reader engine")
    tax=site_policy.get("taxonomy")
    filters={k:sorted(v) for k,v in tax.items()} if tax else {"amenity":sorted(site_policy["amenity_capabilities"])}
    osm = OSM(str(p), engine=reader_engine, workers=1)
    extra = ["access", "access:conditional", "capacity", "tourism", "shop", "highway"]
    if reader_engine == "out_of_core":
        # get_pois retains an arbitrary JSON `tags` payload. In Pyrosm 0.13.1 that
        # column can be a struct in point/way chunks and a string in relation chunks,
        # so GeoParquet cannot unify the schemas. This public OSM method keeps the
        # exact policy/filter columns while omitting only tags the classifier never reads.
        frame = osm.get_data_by_custom_criteria(
            custom_filter=filters, filter_type="keep",
            tags_as_columns=sorted(set(tax) | set(extra)),
            keep_nodes=True, keep_ways=True, keep_relations=True,
            keep_other_tags=False,
        )
    else:
        frame = osm.get_pois(custom_filter=filters, extra_attributes=extra)
    if frame is None: return ()
    rows=(dict(zip(frame.columns,values)) for values in frame.itertuples(index=False, name=None))
    if site_policy.get("exclude_conditional_access"): rows=(r for r in rows if not _tag(r.get("access:conditional")))
    return normalize_site_records(rows,site_policy,digest,boundary=boundary)



def bind_source_endpoint(graph, source_identity, coordinates, *, max_distance_m):
    """Bind one exposed OSM identity/coordinate to this raw graph."""
    from pyproj import Geod
    if not isinstance(source_identity, str):
        raise ValueError("source identity must be a string")
    match = re.fullmatch(r"4r:(node|way)/(\d+)", source_identity)
    if not match:
        raise ValueError("unsupported exposed OSM identity")
    if (not isinstance(coordinates, (list, tuple)) or len(coordinates) != 2
            or any(type(v) not in (int, float) for v in coordinates)):
        raise ValueError("endpoint coordinates must be numeric lon/lat")
    lon, lat = map(float, coordinates)
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise ValueError("endpoint coordinates outside WGS84")
    if type(max_distance_m) not in (int, float) or max_distance_m < 0:
        raise ValueError("max_distance_m must be a frozen nonnegative value")
    nodes = {str(n["node_id"]): n for n in graph.nodes}
    kind, source_id = match.groups()
    if kind == "node" and source_id in nodes:
        candidate_ids = [source_id]
        method = "exact_osm_node_id_v1"
    elif kind == "way":
        candidate_ids = sorted({str(e[k]) for e in graph.edges
                                if str(e.get("osm_way_id")) == source_id
                                for k in ("source", "target")},
                               key=lambda x: (0, int(x)) if x.isdigit() else (1, x))
        method = "source_way_endpoint_geodesic_v1"
    else:
        candidate_ids = list(nodes)
        method = "global_graph_node_geodesic_fallback_v1"
    if not candidate_ids:
        raise ValueError("source identity has no graph binding candidates")
    geod = Geod(ellps="WGS84")
    ranked = []
    for node_id in candidate_ids:
        node = nodes.get(node_id)
        if node is None:
            continue
        _, _, distance = geod.inv(lon, lat, float(node["lon"]), float(node["lat"]))
        tie = (0, int(node_id)) if node_id.isdigit() else (1, node_id)
        ranked.append((abs(distance), tie, node_id, node))
    if not ranked:
        raise ValueError("source identity has no graph binding candidates")
    distance, _, node_id, node = min(ranked)
    if distance > max_distance_m:
        raise ValueError("endpoint exceeds frozen WGS84 snap radius")
    return {"source_identity": source_identity, "source_coordinates": [lon, lat],
            "graph_node_id": node_id, "graph_coordinates": [float(node["lon"]), float(node["lat"])],
            "geodesic_distance_m": distance, "binding_method": method,
            "max_distance_m": max_distance_m, "metric": "WGS84_ellipsoidal_Geod.inv"}




def snap_and_score_shandong_sites(graph, sites, *, origin_node_id, destination_node_id,
                                  max_distance_m, candidate_count=4,
                                  excluded_highway=("motorway","motorway_link","trunk","trunk_link"),
                                  attachment_workers=1,
                                  max_attachment_group_rss_bytes=24*1024**3,
                                  attachment_memory_margin_bytes=2*1024**3,
                                  attachment_resource_record=None):
    """Connect extracted POIs to bidirectionally usable graph nodes.

    The 250 m value is not defaulted here: callers must pass a value bound by a
    DEV contract. Eligibility follows the disclosed in-and-out edge rule.
    Geographic detour uses the existing WGS84 Geod.inv metric.
    """
    from hiroute.data.shandong_spatial import (
        snap_sites_wgs84, snap_sites_wgs84_parallel, geodesic_detour_scores_wgs84)
    nodes={n["node_id"]:n for n in graph.nodes}
    if origin_node_id not in nodes or destination_node_id not in nodes:
        raise ValueError("query endpoint absent from graph")
    excluded=set(excluded_highway)
    allowed_edges=[e for e in graph.edges if e["highway"] not in excluded]
    incoming={e["target"] for e in allowed_edges}
    outgoing={e["source"] for e in allowed_edges}
    eligible=[n for n in graph.nodes if n["node_id"] in incoming and n["node_id"] in outgoing]
    if attachment_workers == 1:
        attachments=snap_sites_wgs84(
            sites,eligible,max_distance_m=max_distance_m,candidate_count=candidate_count)
        if attachment_resource_record is not None:
            attachment_resource_record.clear()
            attachment_resource_record.update({"requested_workers":1,"effective_workers":1,"mode":"serial"})
    else:
        profile=[]
        attachments=snap_sites_wgs84_parallel(
            sites,eligible,max_distance_m=max_distance_m,candidate_count=candidate_count,
            workers=attachment_workers,max_group_rss_bytes=max_attachment_group_rss_bytes,
            memory_margin_bytes=attachment_memory_margin_bytes,_profile=profile)
        if attachment_resource_record is not None:
            attachment_resource_record.clear()
            attachment_resource_record.update({"profile":profile})
    access={sid:row["node_id"] for sid,row in attachments.items()}
    origin=nodes[origin_node_id]
    destination=nodes[destination_node_id]
    scores=geodesic_detour_scores_wgs84(
        sites,(origin["lon"],origin["lat"]),(destination["lon"],destination["lat"]))
    scores={sid:value for sid,value in scores.items() if sid in access}
    return {"site_access_nodes":access,"detour_scores":scores,
            "audit":{"eligible_bidirectional_nodes":len(eligible),
                     "candidate_prefilter_count":candidate_count,
                     "excluded_highway":sorted(excluded),
                     "attached_sites":len(access),
                     "unattached_site_ids":sorted(s.site_id for s in sites if s.site_id not in access),
                     "max_distance_m":max_distance_m}}


def _python_package_tree_sha256():
    root=Path(__file__).resolve().parents[1]
    digest=sha256()
    for path in sorted(root.rglob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode()+b"\\0")
        digest.update(sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def _formal_r4_request_sha256(*,expected_raw_sha256,expected_boundary_sha256,
        routing,query,projection,origin_node_id,destination_node_id,
        endpoint_sources,max_distance_m,candidate_count,candidate_site_ids):
    request={"raw_sha256":expected_raw_sha256,
        "boundary_sha256":expected_boundary_sha256,"routing":routing,"query":query,
        "projection":projection,"origin_node_id":origin_node_id,
        "destination_node_id":destination_node_id,"endpoint_sources":endpoint_sources,
        "max_distance_m":str(max_distance_m),"candidate_count":candidate_count,
        "candidate_site_ids":candidate_site_ids}
    canonical=json.dumps(request,sort_keys=True,separators=(",",":"),ensure_ascii=False,
                         allow_nan=False).encode()
    return sha256(canonical).hexdigest()


def _require_formal_r4_admission(receipt_path, *, request_sha256):
    if not receipt_path:
        raise PermissionError("formal Shandong raw run blocked: R0-R3 admission receipt is required")
    try:
        receipt=json.loads(Path(receipt_path).read_text(encoding="utf-8"))
    except (OSError,UnicodeError,json.JSONDecodeError) as exc:
        raise PermissionError("formal Shandong raw run blocked: admission receipt is unreadable") from exc
    if not isinstance(receipt,dict) or receipt.get("schema")!="hiroute.r4_formal_admission.v1":
        raise PermissionError("formal Shandong raw run blocked: admission receipt schema is invalid")
    if receipt.get("status")!="PASS":
        raise PermissionError("formal Shandong raw run blocked: admission receipt is not PASS")
    if receipt.get("request_sha256")!=request_sha256:
        raise PermissionError("formal Shandong raw run blocked: frozen request identity differs")
    if receipt.get("package_python_tree_sha256")!=_python_package_tree_sha256():
        raise PermissionError("formal Shandong raw run blocked: installed/source package tree differs from reviewed tree")
    stages=receipt.get("stages")
    if not isinstance(stages,dict) or set(stages)!={"R0","R1","R2","R3"}:
        raise PermissionError("formal Shandong raw run blocked: R0-R3 stage matrix is incomplete")
    for name,row in stages.items():
        if not isinstance(row,dict) or row.get("status")!="PASS":
            raise PermissionError(f"formal Shandong raw run blocked: {name} is not PASS")
    cases=receipt.get("cases")
    required_cases={f"C{i:02d}" for i in range(1,25)}
    if not isinstance(cases,dict) or set(cases)!=required_cases:
        raise PermissionError("formal Shandong raw run blocked: C01-C24 matrix is incomplete")
    for name,row in cases.items():
        if not isinstance(row,dict) or row.get("status")!="PASS":
            raise PermissionError(f"formal Shandong raw run blocked: {name} is not PASS")
    evidence=receipt.get("evidence")
    if not isinstance(evidence,list) or not evidence:
        raise PermissionError("formal Shandong raw run blocked: hashed gate evidence is required")
    for item in evidence:
        if not isinstance(item,dict) or set(item)!={"path","sha256"}:
            raise PermissionError("formal Shandong raw run blocked: malformed evidence reference")
        path=Path(item["path"])
        if not path.is_file() or sha256(path.read_bytes()).hexdigest()!=item["sha256"]:
            raise PermissionError("formal Shandong raw run blocked: gate evidence missing or hash mismatch")


def produce_shandong_snapshot(raw_pbf,boundary_path,routing,query,*,execution_scope,
        formal_admission_receipt=None,expected_raw_sha256,expected_boundary_sha256,
        projection,origin_node_id=None,destination_node_id=None,endpoint_sources=None,
        max_distance_m,candidate_count=4,candidate_site_ids=None):
    """Build a hash-bound snapshot; formal raw scope requires a reviewed R0-R3 receipt."""
    if execution_scope not in {"fixture","formal"}:
        raise ValueError("execution_scope must be fixture or formal")
    if execution_scope=="fixture":
        if Path(raw_pbf).stat().st_size>4*1024*1024:
            raise PermissionError("fixture scope is limited to PBF inputs at most 4 MiB")
    else:
        request_sha256=_formal_r4_request_sha256(
            expected_raw_sha256=expected_raw_sha256,
            expected_boundary_sha256=expected_boundary_sha256,routing=routing,query=query,
            projection=projection,origin_node_id=origin_node_id,
            destination_node_id=destination_node_id,endpoint_sources=endpoint_sources,
            max_distance_m=max_distance_m,candidate_count=candidate_count,
            candidate_site_ids=candidate_site_ids)
        _require_formal_r4_admission(formal_admission_receipt,
                                     request_sha256=request_sha256)
    from hiroute.data.shandong_spatial import read_osm_poly
    boundary=read_osm_poly(boundary_path,expected_sha256=expected_boundary_sha256)
    graph=read_shandong_pbf(raw_pbf,routing,expected_sha256=expected_raw_sha256,
        boundary_path=boundary_path,expected_boundary_sha256=expected_boundary_sha256,projection=projection)
    sites=extract_shandong_sites(raw_pbf,routing["site_policy"],expected_sha256=expected_raw_sha256,boundary=boundary)
    endpoint_bindings=None
    if endpoint_sources is not None:
        if (type(endpoint_sources) is not dict or set(endpoint_sources)!={"origin","destination"}
                or origin_node_id is not None or destination_node_id is not None):
            raise ValueError("provide exactly two endpoint source records or explicit graph IDs")
        if any(type(value) is not dict or set(value)!={"identity","coordinates"}
               for value in endpoint_sources.values()):
            raise ValueError("endpoint source records must contain identity and coordinates")
        endpoint_bindings={key:bind_source_endpoint(graph,value["identity"],value["coordinates"],
                           max_distance_m=max_distance_m)
                           for key,value in endpoint_sources.items()}
        query=dict(query)
        query["origin"]=endpoint_bindings["origin"]["graph_node_id"]
        query["destination"]=endpoint_bindings["destination"]["graph_node_id"]
        origin_node_id=query["origin"]; destination_node_id=query["destination"]
    elif not isinstance(origin_node_id,str) or not isinstance(destination_node_id,str):
        raise ValueError("explicit graph endpoint IDs or endpoint source records required")
    attachments=snap_and_score_shandong_sites(graph,sites,origin_node_id=origin_node_id,
        destination_node_id=destination_node_id,max_distance_m=max_distance_m,
        candidate_count=candidate_count,excluded_highway=tuple(routing["attachment"]["excluded_highway"]))
    built=build_snapshot_from_shandong_components(graph,sites,query,
        site_access_nodes=attachments["site_access_nodes"],detour_scores=attachments["detour_scores"],
        candidate_site_ids=candidate_site_ids)
    if endpoint_bindings is not None:
        from hiroute.contracts import canonical_json
        endpoint_policy={"rule":"exact-node-or-way-scoped-WGS84-nearest-v1",
                         "fallback":"node-identity-nearest-graph-node",
                         "way_candidates":"endpoints-of-matching-osm-way-only",
                         "tie":"numeric-node-id-then-lexical",
                         "metric":"WGS84_ellipsoidal_Geod.inv",
                         "max_distance_m":max_distance_m}
        built.manifest["endpoint_bindings"]=endpoint_bindings
        built.manifest["endpoint_binding_policy"]=endpoint_policy
        built.manifest["endpoint_binding_policy_id"]=sha256(canonical_json(endpoint_policy)).hexdigest()
    return {"produced":built,"graph":graph,"sites":sites,"attachments":attachments,
        "endpoint_bindings":endpoint_bindings,
        "boundary_sha256":expected_boundary_sha256,"projection":projection}

def rank_query_candidates(sites, origin_id, destination_id, detour_scores, *, limit=4):
    """Stable exposed-query candidate ordering from precomputed exact metric scores.

    detour_scores maps site id to a nonnegative exact rational/decimal score;
    geometry attachment and score production are intentionally separate gates.
    """
    from fractions import Fraction
    if type(limit) is not int or limit<0: raise ValueError("invalid candidate limit")
    rows=[]
    for site in sites:
        if site.site_id in (origin_id,destination_id): continue
        if not site.capabilities: continue
        if site.site_id not in detour_scores: continue
        score=Fraction(str(detour_scores[site.site_id]))
        if score<0: raise ValueError("negative detour score")
        rows.append((score,site.site_id,site))
    rows.sort(key=lambda x:(x[0],x[1]))
    # Frozen DEV rule: one representative of each capability class, then
    # geographic-detour/site-ID fill. Keep C/S/CS distinct from raw tags.
    def klass(site):
        caps=set(site.capabilities)
        if caps=={"C"}: return "C"
        if caps=={"S"}: return "S"
        if caps in ({"C","S"},{"CS"},{"C","S","CS"}): return "CS"
        raise ValueError(f"unsupported site capability combination: {sorted(caps)}")
    chosen=[]
    for category in ("C","S","CS"):
        item=next((row[2] for row in rows if klass(row[2])==category),None)
        if item is not None: chosen.append(item)
    chosen_ids={item.site_id for item in chosen}
    for _,_,item in rows:
        if len(chosen)>=limit: break
        if item.site_id not in chosen_ids:
            chosen.append(item); chosen_ids.add(item.site_id)
    return tuple(chosen[:limit])


def resolve_shandong_candidate_site_ids(candidate_site_ids, site_ids):
    """Resolve frozen source IDs and the sole documented 4r: alias in stable order."""
    if (type(candidate_site_ids) not in (list, tuple) or len(candidate_site_ids)>4
            or any(type(x) is not str or not x for x in candidate_site_ids)
            or len(set(candidate_site_ids)) != len(candidate_site_ids)):
        raise ValueError("candidate_site_ids must be up to four distinct source identities")
    source_to_site={}
    for site_id in site_ids:
        if type(site_id) is not str or not site_id:
            raise ValueError("raw site identity must be a nonempty string")
        for source_id in (site_id,"4r:"+site_id):
            previous=source_to_site.get(source_id)
            if previous is not None and previous!=site_id:
                raise ValueError("ambiguous frozen candidate alias: "+source_id)
            source_to_site[source_id]=site_id
    missing=[sid for sid in candidate_site_ids if sid not in source_to_site]
    if missing:
        raise ValueError(f"frozen candidate source identities absent from raw POIs: {missing}")
    resolved=tuple(source_to_site[sid] for sid in candidate_site_ids)
    if len(set(resolved))!=len(resolved):
        raise ValueError("frozen candidate identities resolve to duplicate raw POIs")
    return resolved


def build_snapshot_from_shandong_components(graph, sites, query, *, site_access_nodes, detour_scores, candidate_site_ids=None):
    """Bind parsed Shandong graph/sites to a snapshot using explicit frozen inputs.

    Spatial attachment and score production are deliberately inputs: this
    function will not guess projection, snapping radius, or selection semantics.
    It does construct selected directed legs, the exact snapshot, and a stage
    DAG from this PBF-derived graph.
    """
    from hiroute.contracts import ProblemSnapshot, canonical_json
    from hiroute.exact.search import selected_leg
    from hiroute.data.producer import ProducedSnapshot
    required={"origin","destination","departure_time_s","initial_energy_kwh","capacity_kwh","minimum_energy_kwh",
      "destination_reserve_kwh","stop_overhead_s","stop_penalty_s","consumption_kwh_per_m",
      "charging_curve","schedule","initial_remaining_schedule","H_ref","diagnostic_depth_limit"}
    if type(query) is not dict or set(query)!=required: raise ValueError("frozen query fields invalid")
    h_ref=query["H_ref"]
    depth_limit=query["diagnostic_depth_limit"]
    if type(h_ref) is not int or type(depth_limit) is not int:
        raise ValueError("H_ref and diagnostic_depth_limit must be explicit integers")
    if h_ref!=depth_limit:
        raise ValueError("H_ref conflicts with diagnostic_depth_limit")
    if not 0<=depth_limit<=5:
        raise ValueError("diagnostic_depth_limit outside supported range 0..5")
    if type(site_access_nodes) is not dict: raise ValueError("explicit Site attachment map required")
    if candidate_site_ids is None:
        ranked=rank_query_candidates(sites,query["origin"],query["destination"],detour_scores,limit=4)
        candidate_selection="frozen-policy-ranking-v1"
    else:
        resolved_ids=resolve_shandong_candidate_site_ids(candidate_site_ids,[site.site_id for site in sites])
        site_index={site.site_id:site for site in sites}
        ranked=tuple(site_index[sid] for sid in resolved_ids)
        candidate_selection="frozen-source-identities-order-v1"
    candidates=[]; capabilities={}; access_seen=set()
    site_by_id={s.site_id:s for s in sites}
    for site in ranked:
        access=site_access_nodes.get(site.site_id)
        if not isinstance(access,str) or not access: raise ValueError("candidate lacks explicit access node")
        if access in (query["origin"],query["destination"]): continue
        if access not in {n["node_id"] for n in graph.nodes}: raise ValueError("Site access node absent from graph")
        if access in access_seen: raise ValueError("multiple selected sites share one access node")
        access_seen.add(access); candidates.append(access); capabilities[access]=site.capabilities
    if query["origin"] not in {n["node_id"] for n in graph.nodes} or query["destination"] not in {n["node_id"] for n in graph.nodes}:
        raise ValueError("query endpoint absent from graph")
    graph_obj={"nodes":[dict(n) for n in graph.nodes],"edges":[dict(e) for e in graph.edges]}
    graph_id=sha256(canonical_json(graph_obj)).hexdigest()
    snapshot_edges=[{k:e[k] for k in ("source","target","time_s","length_m","edge_id")} for e in graph_obj["edges"]]
    obj={"schema":"hiroute.problem_snapshot.v1","model_contract_id":"hiroute.time_cut_v2.bounded",
      "numerical_contract_id":"exact_rational_inputs_v1","origin":query["origin"],"destination":query["destination"],
      "departure_time_s":query["departure_time_s"],"initial_energy_kwh":query["initial_energy_kwh"],"capacity_kwh":query["capacity_kwh"],
      "minimum_energy_kwh":query["minimum_energy_kwh"],"destination_reserve_kwh":query["destination_reserve_kwh"],
      "stop_overhead_s":query["stop_overhead_s"],"stop_penalty_s":query["stop_penalty_s"],
      "consumption_kwh_per_m":query["consumption_kwh_per_m"],
      "schedule":query["schedule"],"initial_remaining_schedule":query["initial_remaining_schedule"],"candidate_order":candidates,"site_capabilities":capabilities,
      "charging_curve":query["charging_curve"],"directed_edges":snapshot_edges,
      "selected_leg_contract":"positive_time_node_path_edge_path_tie_v1","graph_or_leg_identity":"shandong-pbf-v1:"+graph_id,
      "depth_mode":"diagnostic_cap","depth_limit":depth_limit,"depth_certificate_reference":None}
    snap=ProblemSnapshot.from_dict(obj)
    legs=[]
    for a,b in zip([snap.origin,*snap.candidate_order],[*snap.candidate_order,snap.destination]):
        leg=selected_leg(snap,a,b)
        if leg is None: raise ValueError(f"unreachable selected leg {a}->{b}")
        legs.append({"source":a,"target":b,"time_s":str(leg.time_s),"length_m":str(leg.length_m),
          "edge_ids":[e["edge_id"] for e in leg.edges],"site_source_id":next((sid for sid,node in site_access_nodes.items() if node==a),None)})
    raw_stage={"sha256":graph.source_sha256,"bytes":graph.source_bytes}
    site_output=[{"site_id":s.site_id,"amenity":s.amenity,"capabilities":list(s.capabilities),"transport_classes":list(s.transport_classes),"meal_count_500m":s.meal_count_500m,"geometry_method":s.geometry_method,"access_node":site_access_nodes.get(s.site_id)} for s in sorted(sites,key=lambda x:x.site_id)]
    stages=[]; parent=[]
    for name,inputs,out in [("raw",{},raw_stage),("graph",{"raw_sha256":graph.source_sha256},graph_obj),
      ("stop_sites",{"graph_id":graph_id},site_output),("query_candidates",{"score_ids":sorted(detour_scores)},candidates),
      ("selected_legs",{"semantic_problem_id":snap.semantic_problem_id},legs),("snapshot",{"semantic_problem_id":snap.semantic_problem_id},snap.to_dict())]:
        oid=sha256(canonical_json(out)).hexdigest(); stages.append({"stage":name,"inputs":inputs,"parents":parent,"output_id":oid}); parent=[oid]
    manifest={"schema":"hiroute.producer_dag.v1","raw_sha256":graph.source_sha256,"raw_bytes":graph.source_bytes,
      "candidate_selection":candidate_selection,"candidate_source_ids":list(candidate_site_ids) if candidate_site_ids is not None else [s.site_id for s in ranked],
      "graph_id":graph_id,"semantic_problem_id":snap.semantic_problem_id,"stages":stages,
      "execution_scope":"bounded_shandong_dev_producer_slice","attachments_and_candidate_scores":"explicit_inputs_not_independently_generated"}
    return ProducedSnapshot(snap,manifest,graph_obj,tuple(legs))
