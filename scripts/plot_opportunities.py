"""Static diagnostic maps and measured all-OD compression/coherence, Python only."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from pyproj import Transformer
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from _common import ROOT,read_config

plt.rcParams.update({'font.family':'sans-serif','font.sans-serif':['DejaVu Sans'], 'font.size':7,
    'svg.fonttype':'none','pdf.fonttype':42,'axes.spines.top':False,'axes.spines.right':False,
    'legend.frameon':False,'axes.linewidth':.7})


def save(fig,path):
    fig.savefig(str(path)+'.svg',bbox_inches='tight')
    fig.savefig(str(path)+'.pdf',bbox_inches='tight')
    fig.savefig(str(path)+'.png',dpi=300,bbox_inches='tight')
    plt.close(fig)


def main():
    config=read_config('configs/opportunity.yaml');result=ROOT/config['results_dir'];figdir=result/'figures';figdir.mkdir(exist_ok=True)
    # Figure contract: diagnostic evidence for compression/coherence and spatial
    # structure; quantitative grid, all 30 ODs, no inference about decision utility.
    stats=pd.read_parquet(result/'region_stats.parquet');stats.to_csv(figdir/'region_stats_source.csv',index=False)
    fig,axes=plt.subplots(2,2,figsize=(7.2047244094,155/25.4),layout='constrained')
    fields=[('compression_ratio','Representation compression'),('weighted_progress_variance','Within-region progress variance'),
            ('weighted_detour_variance_s2','Within-region detour variance (s²)'),('singleton_fraction','Singleton region fraction')]
    colors={'geographic baseline':'#667080','decision-aware':'#27868B'}
    for ax,(key,label),panel in zip(axes.flat,fields,'abcd'):
        for method,color in colors.items():
            data=stats[stats.method==method]
            grouped=data.groupby('ratio')[key]
            summary=grouped.agg(['median','min','max'])
            # n=30, median and observed min/max, descriptive, no significance test.
            ax.plot(summary.index,summary['median'],marker='o',ms=3,color=color,label=method)
            ax.fill_between(summary.index,summary['min'],summary['max'],color=color,alpha=.10)
        ax.set(xlabel='Envelope budget / C*',ylabel=label)
        if key in ['weighted_progress_variance','weighted_detour_variance_s2']:
            ax.set_yscale('symlog',linthresh=1e-6 if key=='weighted_progress_variance' else 1)
        ax.text(-.16,1.04,panel,transform=ax.transAxes,fontweight='bold',fontsize=9)
    axes[0,0].legend(fontsize=6)
    save(fig,figdir/'compression_coherence')
    inventory=pd.read_parquet(result/'opportunity_inventory.parquet');attachment=pd.read_parquet(result/'opportunity_attachment.parquet')
    all_opportunities=inventory.merge(attachment,on=['osm_type','osm_id'],validate='one_to_one')
    transform=Transformer.from_crs(4326,3035,always_xy=True)
    all_opportunities['x'],all_opportunities['y']=transform.transform(all_opportunities.lon,all_opportunities.lat)
    fig,axes=plt.subplots(1,3,figsize=(7.2047244094,70/25.4),layout='constrained')
    for ax,area,panel in zip(axes,config['diagnostics']['audit_areas'],'abc'):
        cx,cy=transform.transform(area['lon'],area['lat']);radius=area['radius_m']
        local=all_opportunities[np.hypot(all_opportunities.x-cx,all_opportunities.y-cy)<=radius]
        for status,color,marker in [('attached','#27868B','.'),('excessive_snap','#A8613B','x')]:
            group=local[local.attachment_status==status]
            ax.scatter((group.x-cx)/1000,(group.y-cy)/1000,s=2 if marker=='.' else 9,color=color,marker=marker,label=('Attached' if status=='attached' else f"Rejected (>{config['attachment']['default_threshold_m']} m)"),rasterized=True)
        ax.set(title=f"{area['name']} (n={len(local):,})",xlabel='East (km)',ylabel='North (km)',aspect='equal')
        ax.text(-.18,1.07,panel,transform=ax.transAxes,fontweight='bold',fontsize=9)
    handles,labels=axes[0].get_legend_handles_labels()
    fig.legend(handles,labels,fontsize=6,loc='outside lower center',ncol=2)
    save(fig,figdir/'attachment_audit')
    membership=pd.read_parquet(result/'region_membership.parquet');features=pd.read_parquet(result/'od_features.parquet')
    nodes=pd.read_parquet(ROOT/'data/processed/graphs/slovenia_extended/nodes.parquet',columns=['lat','lon'])
    od=pd.read_parquet(ROOT/'results/milestone_3a/od_remapping.parquet')
    diagnostic_counts=[]
    for oid in config['diagnostics']['figure_od_ids']:
        fig,axes=plt.subplots(2,3,figsize=(7.2047244094,130/25.4),layout='constrained')
        route=od[od.instance_id==oid].iloc[0];route_nodes=nodes.iloc[list(route.path_nodes)]
        rx,ry=transform.transform(route_nodes.lon,route_nodes.lat)
        rx,ry=np.asarray(rx)/1000,np.asarray(ry)/1000
        for col,ratio in enumerate(config['diagnostics']['figure_ratios']):
            for row,method in enumerate(['geographic baseline','decision-aware']):
                members=membership[(membership.instance_id==oid)&(membership.ratio==ratio)&(membership.method==method)]
                points=members.merge(features[features.instance_id==oid],on=['instance_id','osm_type','osm_id'],validate='one_to_one')
                if len(points):
                    # All member points; shared region mean progress supplies a
                    # route-stage encoding, not a quality score or region identity.
                    color=points.groupby('region_id').progress.transform('mean')
                    im=axes[row,col].scatter(points.x_m/1000,points.y_m/1000,c=color,vmin=0,vmax=1,cmap='cividis',s=1,rasterized=True)
                    bounds=points.groupby('region_id').agg(xmin=('x_m','min'),xmax=('x_m','max'),
                        ymin=('y_m','min'),ymax=('y_m','max'),count=('osm_id','size'))
                    rectangles=[np.array([[b.xmin,b.ymin],[b.xmax,b.ymin],[b.xmax,b.ymax],
                        [b.xmin,b.ymax],[b.xmin,b.ymin]])/1000 for b in bounds.itertuples() if b.count>1]
                    axes[row,col].add_collection(LineCollection(rectangles,colors='#333333',linewidths=.25,alpha=.35))
                axes[row,col].plot(rx,ry,color='#B34D42',lw=.7,label='baseline')
                axes[row,col].scatter([rx[0],rx[-1]],[ry[0],ry[-1]],s=9,c=['#222222','#222222'],marker='s')
                axes[row,col].set(title=f"{ratio:.2f}C*\n{len(points):,} POIs / {members.region_id.nunique():,} regions",
                                  xlabel='EPSG:3035 east (km)',ylabel=(method+'\nNorth (km)') if col==0 else 'North (km)',aspect='equal')
                diagnostic_counts.append({'instance_id':oid,'ratio':ratio,'method':method,'plotted_points':len(points),'region_count':members.region_id.nunique()})
        fig.suptitle(f'OD {oid}: baseline and eligible opportunity regions',fontsize=9)
        fig.colorbar(im,ax=axes.ravel().tolist(),label='Region mean route progress',shrink=.5)
        save(fig,figdir/f'od_{oid:02d}_regions')
    pd.DataFrame(diagnostic_counts).to_csv(figdir/'diagnostic_counts.csv',index=False)
    (figdir/'QA.md').write_text('''# Milestone 4A diagnostic figure contract and QA

Python/matplotlib quantitative grids at 183 mm width. Editable SVG/PDF and 300 dpi PNG previews. Core evidence: measured representation compression and within-region decision dispersion; maps locate the same eligible objects for both methods. No decision-optimality or gateway claim.

Compression/coherence panels use all 30 ODs and every configured budget. Lines are medians; shading is observed min–max, not confidence intervals. Variance panels use symmetric-log axes with linear thresholds 1e-6 (progress) and 1 s² (detour), preserving zero values while resolving method differences. No hypothesis test or p value is used. Source: region_stats_source.csv. Zero-opportunity compression/singleton values remain undefined and do not enter descriptive medians.

Audit maps use all opportunities whose representative point is within each configured 7 km area. This is a labelled diagnostic subset, not a clustering input filter. Full inventory and attachment tables remain unchanged. Region maps use every eligible opportunity for ODs 0, 4, 21 at 1.10, 1.40, 2.00; plotted counts are retained in diagnostic_counts.csv. All points are rasterized only for vector-file size. Red lines are frozen baseline paths; squares identify endpoints. Color encodes a region's mean normalized route progress, and is neither a unique region ID nor utility. Thin rectangles outline every non-singleton region's projected bounding box; singleton regions appear as their points. These country-scale maps cannot establish entrance correctness or distinguish every small region; membership/coherence tables provide that evidence. All axes are projected metres converted to km, equal aspect for maps. No online map tiles.

Source preflight passed with two reviewed warnings: PNG previews use 300 dpi and no TIFF is supplied because these are repository diagnostics with editable vector masters, not a submission raster package. Rendered PNGs are visually inspected for legible labels, clipping and colorbar overlap. Table outputs, not visual impressions, supply scientific comparisons. Maximum-budget boundary-risk ODs remain included.
''')

if __name__=='__main__':main()
