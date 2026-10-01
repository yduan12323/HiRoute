"""Static diagnostics only: full-node spatial aggregation and all-OD growth."""
from __future__ import annotations

import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pyproj import Transformer
import shapely

from _common import ROOT, load_graph, sha256
from _envelope_common import envelope_config, envelope_run
from envelope import NumericalTolerance, build_envelope_from_precomputed, precompute_detour_distances
from envelope.boundary import read_poly


def save(fig,path):
    fig.savefig(path.with_suffix(".svg"),bbox_inches="tight")
    fig.savefig(path.with_suffix(".pdf"),bbox_inches="tight")
    fig.savefig(path.with_suffix(".png"),dpi=300,bbox_inches="tight")
    plt.close(fig)


def main():
    config = envelope_config()
    data,routing,_ = envelope_run("plot_envelopes",config)
    directory = ROOT/config["results_dir"]
    figure_dir = directory/"figures"
    figure_dir.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({"font.family":"sans-serif","font.sans-serif":["DejaVu Sans"],
        "font.size":7,"svg.fonttype":"none","pdf.fonttype":42,
        "axes.spines.top":False,"axes.spines.right":False,"legend.frameon":False})
    stats = pd.read_parquet(directory/"envelope_stats.parquet")
    # Every OD is drawn; median and min/max are descriptive, not uncertainty CIs.
    fig,axes = plt.subplots(1,2,figsize=(7.2,2.8),layout="constrained")
    for axis,column,label,panel in zip(axes,["node_percent","edge_percent"],["Graph nodes (%)","Graph edges (%)"],["a","b"]):
        for _,group in stats.groupby("instance_id"):
            axis.plot(group.ratio,group[column],color="#bbbbbb",linewidth=.5,zorder=1)
        grouped = stats.groupby("ratio")[column]
        median = grouped.median()
        axis.plot(median.index,median.values,color="#287c9e",marker="o",markersize=3,label="Median, 30 ODs",zorder=3)
        axis.set(xlabel="Detour budget ratio",ylabel=label,xlim=(1,2),ylim=(0,100))
        axis.text(-.12,1.02,panel,transform=axis.transAxes,fontweight="bold",fontsize=8)
    axes[0].legend(fontsize=7,loc="upper left")
    save(fig,figure_dir/"envelope_growth")
    stats.to_csv(figure_dir/"envelope_growth_source.csv",index=False)
    graph = load_graph(data,routing)
    instances = pd.read_parquet(ROOT/data["instances_path"])
    boundary_path = ROOT/config["boundary"]["path"]
    if sha256(boundary_path) != config["boundary"]["sha256"]:
        raise ValueError("Boundary checksum mismatch")
    transform = Transformer.from_crs("EPSG:4326",config["boundary"]["projection"],always_xy=True)
    x,y = map(np.asarray,transform.transform(graph.nodes.lon,graph.nodes.lat))
    polygon = shapely.transform(read_poly(boundary_path),transform.transform,interleaved=False)
    x0,y0 = x.min(),y.min()
    step = config["diagnostics"]["map_grid_m"]
    xb = np.arange(x0,x.max()+2*step,step)
    yb = np.arange(y0,y.max()+2*step,step)
    tolerance = NumericalTolerance(**config["numerical_tolerance"])
    audit = []
    for od in config["diagnostics"]["figure_od_ids"]:
        row = instances.loc[instances.instance_id.eq(od)].iloc[0]
        distances = precompute_detour_distances(graph,int(row.origin_node),int(row.destination_node),config["cost"])
        baseline = graph.shortest_path(int(row.origin_node),int(row.destination_node),config["cost"])
        route_nodes = list(baseline.nodes)
        fig,axes = plt.subplots(1,3,figsize=(7.2,3.0),layout="constrained")
        sources = {"x_edges_m":xb,"y_edges_m":yb,"baseline_x_m":x[route_nodes],"baseline_y_m":y[route_nodes]}
        for axis,ratio in zip(axes,config["diagnostics"]["figure_ratios"]):
            envelope = build_envelope_from_precomputed(distances,ratio*distances.baseline_cost,tolerance)
            counts,_,_ = np.histogram2d(x[envelope.node_mask],y[envelope.node_mask],bins=[xb,yb])
            if int(counts.sum()) != int(envelope.node_mask.sum()):
                raise RuntimeError("Spatial aggregation dropped envelope nodes")
            sources[f"counts_ratio_{ratio:g}"] = counts.astype(np.int32)
            # Binary occupancy supports a common scale across all ratios.
            occupancy = np.ma.masked_where(counts.T==0,np.ones_like(counts.T))
            axis.pcolormesh((xb-x0)/1000,(yb-y0)/1000,occupancy,cmap="Blues",vmin=0,vmax=2,
                            shading="flat",rasterized=True,zorder=1)
            for part in shapely.get_parts(polygon):
                ring = np.asarray(part.exterior.coords)
                axis.plot((ring[:,0]-x0)/1000,(ring[:,1]-y0)/1000,color="#aaaaaa",linewidth=.5,zorder=2)
            axis.plot((x[route_nodes]-x0)/1000,(y[route_nodes]-y0)/1000,color="#333333",linewidth=.7,zorder=3)
            axis.scatter((x[row.origin_node]-x0)/1000,(y[row.origin_node]-y0)/1000,
                         marker="o",s=20,facecolors="white",edgecolors="black",zorder=4)
            axis.scatter((x[row.destination_node]-x0)/1000,(y[row.destination_node]-y0)/1000,
                         marker="^",s=20,color="black",zorder=4)
            axis.set(title=f"B = {ratio:g} C*\n{int(envelope.node_mask.sum()):,} nodes",xlabel="East (km)",aspect="equal")
            axis.set_xlim(0,(xb[-1]-x0)/1000)
            axis.set_ylim(0,(yb[-1]-y0)/1000)
            audit.append({"instance_id":od,"ratio":ratio,"source_nodes":int(envelope.node_mask.sum()),
                          "aggregated_nodes":int(counts.sum()),"grid_m":step,"excluded_nodes":0})
        axes[0].set_ylabel("North (km)")
        fig.suptitle(f"OD {od}: {row.origin_city.replace('_',' ')} → {row.destination_city.replace('_',' ')}\n"
                     "Circle: origin; triangle: destination; line: baseline; blue: occupied envelope cells",fontsize=8)
        save(fig,figure_dir/f"od_{od:02d}_envelopes")
        np.savez_compressed(figure_dir/f"od_{od:02d}_source.npz",**sources)
    (figure_dir/"qa.json").write_text(json.dumps({"backend":"Python/matplotlib","maps":audit,
        "source":"Frozen graph and envelope_stats.parquet; all 30 ODs in growth panels.",
        "contract":"Quantitative grid plus diagnostic maps: larger budgets expand membership; visual appearance is not proof.",
        "aggregation":"All retained nodes assigned to configured metric grid cells; occupancy displayed, counts preserved in NPZ.",
        "coordinates":"EPSG:3035 with fixed full-graph local origin, equal aspect.",
        "exports":"Editable SVG/PDF text and PNG previews at 300 dpi; diagnostic figures, no publication target.",
        "statistics":"Individual ODs and descriptive median; no significance tests or confidence intervals."},indent=2)+"\n")
    print(f"Saved growth figure and {len(config['diagnostics']['figure_od_ids'])} OD diagnostics")


if __name__ == "__main__":
    main()
