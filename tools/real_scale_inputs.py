"""Prepare declared real DEV domains without running a numeric solver.

The source graph is reused, not rebuilt. The TSV exporter streams the existing
pretty JSON in bounded memory. It copies exact metrics, never selected legs as
an ordinary graph. Candidate selection is a declared experimental restriction,
not an admissible full-domain filter. No solve results enter selection.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import replace
from fractions import Fraction
import json
import math
from pathlib import Path
import resource
import time


def write_new(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def pretty_array(path, key):
    """Stream one top-level object array in the existing producer pretty JSON.

    Reject unexpected indentation/schema rather than guessing another JSON
    representation. This format-specific reader avoids a multi-GB JSON heap.
    """
    active = False
    record = None
    with Path(path).open(encoding="utf-8") as stream:
        for line in stream:
            if not active:
                if line.rstrip() == f'  "{key}": [':
                    active = True
                continue
            if line.rstrip() in ("  ],", "  ]"):
                if record is not None:
                    raise ValueError("unterminated array record")
                return
            if line.rstrip() == "    {":
                if record is not None:
                    raise ValueError("nested or malformed array record")
                record = [line]
            elif record is not None:
                record.append(line)
                if line.rstrip() in ("    },", "    }"):
                    yield json.loads("".join(record).rstrip().rstrip(","))
                    record = None
            else:
                raise ValueError("unexpected array formatting")
    raise ValueError(f"missing or unterminated top-level array: {key}")


def export_edges(source, destination):
    started, cpu = time.monotonic(), time.process_time()
    count = 0
    with Path(destination).open("x", encoding="utf-8") as stream:
        for edge in pretty_array(source, "directed_edges"):
            row = [edge[k] for k in ("source", "target", "edge_id", "time_s", "length_m")]
            if any(not isinstance(x, str) or not x or any(c in x for c in "\t\r\n") for x in row):
                raise ValueError("invalid edge TSV field")
            if Fraction(row[3]) <= 0 or Fraction(row[4]) <= 0:
                raise ValueError("positive road metrics required")
            stream.write("\t".join(row) + "\n")
            count += 1
    return {"stage": "existing_processed_graph_tsv_export", "edges": count,
            "source": str(source), "source_bytes": Path(source).stat().st_size,
            "output": str(destination), "output_bytes": Path(destination).stat().st_size,
            "wall_s": time.monotonic()-started, "cpu_s": time.process_time()-cpu,
            "peak_rss_platform_units": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}


def great_circle(a, b):
    lat1, lat2 = math.radians(a["lat"]), math.radians(b["lat"])
    dlat, dlon = lat2-lat1, math.radians(b["lon"]-a["lon"])
    h = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 6371008.8 * 2 * math.asin(min(1, math.sqrt(h)))


def segment_features(site, origin, destination):
    lat = math.radians((origin["lat"] + destination["lat"])/2)
    scale = 6371008.8 * math.pi/180
    dx = (destination["lon"]-origin["lon"])*math.cos(lat)*scale
    dy = (destination["lat"]-origin["lat"])*scale
    sx = (site["lon"]-origin["lon"])*math.cos(lat)*scale
    sy = (site["lat"]-origin["lat"])*scale
    length2 = dx*dx+dy*dy
    if not length2:
        raise ValueError("identical OD coordinates")
    progress = (sx*dx+sy*dy)/length2
    clipped = min(1, max(0, progress))
    cross = math.hypot(sx-clipped*dx, sy-clipped*dy)
    detour = great_circle(origin, site) + great_circle(site, destination) - great_circle(origin, destination)
    return progress, cross, max(0, detour)


def select_domains(config, sites, attachments):
    """Return the frozen four OD domains; no road search/solver is called."""
    rules = config["selection"]
    access = attachments["site_access_nodes"]
    attached = [s for s in sites if s["site_id"] in access]
    if not attached:
        raise ValueError("no already attached real Sites")
    queries = []
    for od in rules["ods"]:
        endpoints = {}
        for which in ("origin", "destination"):
            target = od[which]
            site = min(attached, key=lambda s: (great_circle(target, s), s["site_id"]))
            endpoints[which] = {"target": target, "site_id": site["site_id"],
                                "access_node": access[site["site_id"]],
                                "lon": site["lon"], "lat": site["lat"],
                                "displacement_m": great_circle(target, site)}
        if endpoints["origin"]["access_node"] == endpoints["destination"]["access_node"]:
            raise ValueError("OD endpoints bind to the same road anchor")
        endpoint_anchors = {x["access_node"] for x in endpoints.values()}
        by_anchor = {}
        eligible_count = 0
        for site in attached:
            caps = set(site["capabilities"])
            anchor = access[site["site_id"]]
            if not caps or anchor in endpoint_anchors:
                continue
            progress, cross, detour = segment_features(site, endpoints["origin"], endpoints["destination"])
            if cross > rules["corridor_km"]*1000:
                continue
            eligible_count += 1
            row = {**site, "access_node": anchor, "progress": progress,
                   "corridor_distance_m": cross, "geometric_detour_m": detour}
            preference = (0 if "CS" in caps else 1 if "C" in caps else 2, site["site_id"])
            if anchor not in by_anchor or preference < by_anchor[anchor][0]:
                by_anchor[anchor] = (preference, row)
        pools = []
        strata = rules["progress_strata"]
        for bucket in range(strata):
            rows = [x[1] for x in by_anchor.values()
                    if min(strata-1, max(0, int(x[1]["progress"]*strata))) == bucket]
            for effect in ("C", "S"):
                pools.append(sorted((r for r in rows if effect in r["capabilities"]),
                                    key=lambda r: (r["geometric_detour_m"], r["site_id"])))
        ordered, chosen = [], set()
        positions = [0]*len(pools)
        while True:
            added = False
            for i, pool in enumerate(pools):
                while positions[i] < len(pool) and pool[positions[i]]["site_id"] in chosen:
                    positions[i] += 1
                if positions[i] < len(pool):
                    row = pool[positions[i]]
                    positions[i] += 1
                    ordered.append(row)
                    chosen.add(row["site_id"])
                    added = True
            if not added:
                break
        counts = rules["candidate_counts"]
        # Preserve the original mixed order for historical ingress and the
        # scheduled scenario. Energy-only has no legal S-only action; its N
        # therefore counts C-capable Sites from the *full* frozen order.
        scenario_pools = {"energy_only": [r for r in ordered if "C" in r["capabilities"]],
                          "schedule": ordered}
        scenario_domains = {scenario: {str(n): rows[:n] for n in counts}
                            for scenario, rows in scenario_pools.items()}
        queries.append({"query_id": od["query_id"], "endpoints": endpoints,
                        "great_circle_m": great_circle(endpoints["origin"], endpoints["destination"]),
                        "eligible_sites_before_anchor_dedup": eligible_count,
                        "eligible_unique_anchors": len(ordered),
                        "candidate_domains": {str(n): ordered[:n] for n in counts},
                        "domain_sizes": {str(n): min(n, len(ordered)) for n in counts},
                        "scenario_candidate_domains": scenario_domains,
                        "scenario_eligible_counts": {scenario: len(rows)
                                                     for scenario, rows in scenario_pools.items()},
                        "scenario_domain_status": {
                            scenario: {str(n): "available" if len(rows) >= n
                                      else "input_domain_unavailable" for n in counts}
                            for scenario, rows in scenario_pools.items()},
                        "domain_claim": rules["domain_claim"]})
    return {"schema": "hiroute.real_scale_preflight.v1", "config": config,
            "source_sites": len(sites), "source_attached_sites": len(attached),
            "source_capabilities": {','.join(k): v for k, v in Counter(tuple(s["capabilities"]) for s in sites).items()},
            "queries": queries, "selection_uses_solver_results": False}


class InputDomainUnavailable(ValueError):
    """A declared N exceeds the frozen scenario's actual qualified Sites."""
    def __init__(self, requested, available, scenario):
        self.requested = requested
        self.available = available
        self.scenario = scenario
        super().__init__(f"input_domain_unavailable: scenario={scenario}, "
                         f"requested={requested}, available={available}")


def domain_rows(query, candidate_count, scenario, require_full=True):
    """Read a declared scenario domain, failing before routing if N is absent.

    The old mixed domain remains readable for scheduled historical ingress.
    Energy-only fallback removes S-only Sites instead of counting them as N;
    full original order is available only in newly prepared scenario domains.
    ``require_full=False`` exposes a short pool for reporting, never upgrades
    it into the requested N domain.
    """
    if type(candidate_count) is not int or candidate_count < 0:
        raise ValueError("candidate_count must be a nonnegative integer")
    if scenario not in ("energy_only", "schedule"):
        raise ValueError("undeclared scenario")
    if "scenario_candidate_domains" in query:
        rows = query["scenario_candidate_domains"][scenario][str(candidate_count)]
    else:
        rows = query["candidate_domains"][str(candidate_count)]
        if scenario == "energy_only":
            rows = [r for r in rows if "C" in r["capabilities"]]
    if require_full and len(rows) < candidate_count:
        raise InputDomainUnavailable(candidate_count, len(rows), scenario)
    return rows


class SiteAliasedProvider:
    """Keep Site identities distinct from road-anchor routing identities."""
    def __init__(self, provider, aliases):
        self.provider = provider
        self.aliases = dict(aliases)
        self.nodes = tuple(self.aliases)

    @property
    def check(self):
        return self.provider.check

    @check.setter
    def check(self, value):
        self.provider.check = value

    def _call(self, method, anchor, *args):
        if self.check is not None:
            self.check()
        return getattr(self.provider, method)(self.aliases[anchor], *args)

    def selected_leg(self, source, target):
        if self.check is not None:
            self.check()
        leg = self.provider.selected_leg(self.aliases[source], self.aliases[target])
        return None if leg is None else replace(leg, source=source, target=target)

    def distances_from(self, source, weight="time_s"):
        distances = self._call("distances_from", source, weight)
        return {site: distances[anchor] for site, anchor in self.aliases.items() if anchor in distances}

    def distances_to(self, target, weight="time_s"):
        distances = self._call("distances_to", target, weight)
        return {site: distances[anchor] for site, anchor in self.aliases.items() if anchor in distances}

    def metrics(self):
        return self.provider.metrics()

    def lower_bound(self, source, target, weight="time_s"):
        return self.distances_to(target, weight).get(source)


def bind_snapshot(config, query, candidate_count, scenario, provider):
    """Freeze a small metadata snapshot over an external real road provider.

    Provider metadata, source graph and index are kept separate from the input
    snapshot, so millions of road edges are never copied per query.
    """
    from hiroute.contracts import ProblemSnapshot
    rows = domain_rows(query, candidate_count, scenario)
    origin, destination = (query["endpoints"][w]["site_id"] for w in ("origin", "destination"))
    if scenario not in config["selection"]["scenarios"]:
        raise ValueError("undeclared scenario")
    schedule = None
    if scenario == "schedule":
        leg = provider.selected_leg(origin, destination)
        if leg is None:
            raise ValueError("directed OD unreachable; scheduled direct-time recipe unavailable")
        recipe = config["selection"]["schedule_recipe"]
        schedule = {"a": str(leg.time_s*Fraction(recipe["a_fraction_direct_time"])),
                    "b": str(leg.time_s*Fraction(recipe["b_fraction_direct_time"])),
                    "D": recipe["duration_s"]}
    model = {k: v for k, v in config["model"].items() if k != "provenance"}
    return ProblemSnapshot.from_dict({**model, "schema": "hiroute.problem_snapshot.v1",
        "model_contract_id": "hiroute.time_cut_v2.bounded", "numerical_contract_id": "exact_rational_inputs_v1",
        "origin": origin, "destination": destination, "schedule": schedule,
        "initial_remaining_schedule": int(schedule is not None),
        "candidate_order": [r["site_id"] for r in rows],
        "site_capabilities": {r["site_id"]: r["capabilities"] for r in rows},
        "directed_edges": [], "selected_leg_contract": "positive_time_node_path_edge_path_tie_v1",
        "graph_or_leg_identity": "Shandong-20261016-existing-directed-road-provider",
        "depth_mode": "unrestricted", "depth_limit": 0, "depth_certificate_reference": None})


def minimum_required_charges(shortest_road_distance, model):
    """Capacity-only necessary count, independent of the planner's winner.

    Any route consumes at least c*d_shortest. Each positive charge adds at most
    capacity-floor, even if its exact site or schedule is relaxed. This is only
    a necessary energy bound; it does not establish charging connectivity.
    """
    consumption = Fraction(model["consumption_kwh_per_m"])
    required = (consumption*Fraction(shortest_road_distance)
                + Fraction(model["destination_reserve_kwh"])
                - Fraction(model["initial_energy_kwh"]))
    span = Fraction(model["capacity_kwh"])-Fraction(model["minimum_energy_kwh"])
    if span <= 0 or consumption < 0:
        raise ValueError("invalid energy model")
    return max(0, math.ceil(required/span))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export-edges")
    export.add_argument("--graph", required=True)
    export.add_argument("--output", required=True)
    export.add_argument("--record", required=True)
    preflight = sub.add_parser("preflight")
    preflight.add_argument("--config", required=True)
    preflight.add_argument("--sites", required=True)
    preflight.add_argument("--bindings", required=True)
    preflight.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.command == "export-edges":
        record = export_edges(args.graph, args.output)
        write_new(args.record, record)
        print(json.dumps(record, sort_keys=True))
    else:
        started, cpu = time.monotonic(), time.process_time()
        config, sites, bindings = (json.loads(Path(p).read_text()) for p in (args.config, args.sites, args.bindings))
        result = select_domains(config, sites, bindings)
        result["preparation_wall_s"] = time.monotonic()-started
        result["preparation_cpu_s"] = time.process_time()-cpu
        write_new(args.output, result)
        print(json.dumps({"queries": [{k: q[k] for k in ("query_id", "endpoints", "great_circle_m", "eligible_unique_anchors", "domain_sizes")} for q in result["queries"]]}, indent=2))


if __name__ == "__main__":
    main()
