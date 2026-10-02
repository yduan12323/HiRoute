"""Static measured compression/regret curves and recorded decision diagnostics."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from pyproj import Transformer
from _common import ROOT,read_config,configs,load_graph
from _microplan_common import identity_keys

mpl.rcParams.update({'font.family':'sans-serif','font.sans-serif':['DejaVu Sans'],
    'font.size':7,'svg.fonttype':'none','pdf.fonttype':42,'axes.spines.top':False,
    'axes.spines.right':False,'axes.linewidth':.8,'legend.frameon':False})
WIDTH=183/25.4
COLORS={'proposed':'#43758B','geographic':'#9A8065','random':'#A57483','flat':'#777777'}


def save(fig,path,dpi):
    fig.savefig(path.with_suffix('.svg'),bbox_inches='tight')
    fig.savefig(path.with_suffix('.pdf'),bbox_inches='tight')
    fig.savefig(path.with_suffix('.png'),dpi=dpi,bbox_inches='tight')
    plt.close(fig)


def main():
    cfg=read_config('configs/microplan.yaml');root=ROOT/cfg['results_dir'];out=root/'figures';out.mkdir(exist_ok=True)
    columns=['instance_id','ratio','task','primary_task','access_scenario','dwell_scenario','method','theta_id',
             'absolute_regret','flat_count','retained_count','oracle_first_index','oracle_second_index',
             'selected_first_index','selected_second_index','boundary_risk']
    raw=pd.read_parquet(root/'abstraction_regret.parquet',columns=columns)
    data=raw[raw.primary_task&raw.ratio.isin([1.05,1.1,1.2,1.4])&
             (raw.access_scenario=='all_attached')&(raw.dwell_scenario=='without_dwell')].copy()
    data['compression']=np.where(data.flat_count>0,1-data.retained_count/data.flat_count,np.nan)
    rows=[]
    for method,t in data.groupby('method'):
        valid=t.absolute_regret.notna();finite=np.isfinite(t.absolute_regret)
        values=t.loc[finite,'absolute_regret']
        rows.append({'method':method,'evaluations':int(valid.sum()),'no_flat_oracle':int((~valid).sum()),
            'infinite_losses':int(np.isinf(t.absolute_regret).sum()),'median_compression':float(t.compression.median()),
            'median_retained':float(t.retained_count.median()),'median_regret_finite':float(values.median()),
            'p95_regret_finite':float(values.quantile(.95)),
            'coverage_001':float(np.mean(t.loc[valid,'absolute_regret']<=.01+1e-10)),
            'coverage_005':float(np.mean(t.loc[valid,'absolute_regret']<=.05+1e-10))})
    curve=pd.DataFrame(rows).set_index('method');curve.reset_index().to_csv(out/'compression_regret_source.csv',index=False)
    proposed=['flat','decision','exact_pareto',*['epsilon_'+n for n in cfg['epsilon_covers']]]
    random=['random_'+n for n in cfg['epsilon_covers']]
    fig,axes=plt.subplots(1,2,figsize=(WIDTH,2.8),layout='constrained')
    for ax,column,title in zip(axes,['median_regret_finite','p95_regret_finite'],['a  Median finite loss','b  p95 finite loss']):
        for methods,color,label in [(proposed,COLORS['proposed'],'Decision → Pareto → ε'),(random,COLORS['random'],'Matched random')]:
            t=curve.loc[methods]
            ax.plot(100*t.median_compression,t[column],'-o',color=color,lw=1,ms=3,label=label)
        t=curve.loc['geographic'];ax.scatter(100*t.median_compression,t[column],marker='s',color=COLORS['geographic'],label='Geographic restriction',s=20)
        ax.set(xlabel='Candidate reduction (%)',ylabel='Absolute normalized-cost loss',title=title,xlim=(-3,103))
        ax.set_yscale('symlog',linthresh=.001);ax.set_ylim(bottom=0);ax.grid(alpha=.15)
    axes[0].legend(fontsize=6,loc='upper left')
    axes[1].annotate('Region restriction',(100*curve.loc['decision','median_compression'],curve.loc['decision','p95_regret_finite']),xytext=(-10,12),textcoords='offset points',ha='center',fontsize=6)
    axes[1].annotate('Pareto / ε covers',(100*curve.loc['exact_pareto','median_compression'],curve.loc['exact_pareto','p95_regret_finite']),xytext=(-45,-20),textcoords='offset points',ha='center',fontsize=6)
    missing=int(data[data.method=='flat'].absolute_regret.isna().sum())
    infinite=int(np.isinf(data[data.method=='epsilon_medium'].absolute_regret).sum())
    fig.supxlabel(f'Equal OD × task × budget × θ observations; absent flat oracle: {missing}; medium-cover infinite loss: {infinite}',fontsize=6)
    save(fig,out/'compression_vs_regret',cfg['diagnostics']['dpi'])
    fig,axes=plt.subplots(1,2,figsize=(WIDTH,2.7),layout='constrained')
    for ax,column,title in zip(axes,['coverage_001','coverage_005'],['a  Loss tolerance 0.01','b  Loss tolerance 0.05']):
        for methods,color,label in [(proposed,COLORS['proposed'],'Decision/Pareto/ε'),(random,COLORS['random'],'Matched random')]:
            t=curve.loc[methods];ax.plot(t.median_retained,t[column],'-o',color=color,lw=1,ms=3,label=label)
        t=curve.loc['geographic'];ax.scatter(t.median_retained,t[column],marker='s',color=COLORS['geographic'],label='Geographic',s=20)
        ax.set(xlabel='Median retained candidates',ylabel='ε-optimal coverage',title=title,ylim=(-.02,1.02))
        if (curve.median_retained>0).all():
            ax.set_xscale('log');ax.set_xlim(left=max(1,float(curve.median_retained.min())/1.5))
        else:
            ax.set_xscale('linear');ax.set_xlim(left=0)
        ax.grid(alpha=.15)
    axes[0].legend(fontsize=6)
    fig.supxlabel('K=1, 3, 5 coincide: ranking and evaluation use the same known scalar objective.',fontsize=6)
    save(fig,out/'retained_vs_topk_coverage',cfg['diagnostics']['dpi'])
    # All task/utility/budget observations are retained in a task source table.
    strat=data.groupby(['task','method']).agg(median_compression=('compression','median'),
        median_regret=('absolute_regret','median'),p95_regret=('absolute_regret',lambda s:s.quantile(.95)),
        infinite_losses=('absolute_regret',lambda s:np.isinf(s).sum()))
    strat.to_csv(out/'task_source.csv')
    fig,ax=plt.subplots(figsize=(WIDTH,3.0),layout='constrained')
    for task in cfg['tasks']:
        if not cfg['tasks'][task]['primary']:continue
        t=strat.loc[(task,'epsilon_medium')]
        ax.scatter(100*t.median_compression,t.p95_regret,color=COLORS['proposed'],s=24)
        offset=(-6,10) if task=='charge' else (-8,4) if '_' in task else (6,10)
        alignment='right' if task=='charge' or '_' in task else 'left'
        ax.annotate(task.replace('_',' + '),(100*t.median_compression,t.p95_regret),xytext=offset,ha=alignment,textcoords='offset points',fontsize=6)
    ax.set(xlabel='Median candidate reduction (%)',ylabel='p95 absolute regret',title='Task-stratified medium cover')
    ax.set_yscale('symlog',linthresh=.001);ax.set_ylim(bottom=0);ax.grid(alpha=.15)
    save(fig,out/'task_compression_regret',cfg['diagnostics']['dpi'])
    medium=data[data.method=='epsilon_medium']
    available=medium[medium.absolute_regret.notna()]
    near=available[(available.absolute_regret<=1e-10)&(available.flat_count>=100)].sort_values('compression',ascending=False).iloc[0]
    worst=available.sort_values('absolute_regret',ascending=False).iloc[0]
    early=available[available.instance_id.isin(cfg['diagnostics']['early_unstable_od_ids'])&(available.ratio==1.05)].sort_values('absolute_regret',ascending=False).iloc[0]
    cases=[('High compression, zero loss',near),('Worst medium-cover loss',worst),('Early expansion diagnostic',early)]
    catalogue=pd.read_parquet(root/'opportunity_index.parquet');old=ROOT/cfg['frozen_region_dir']
    odtable=pd.read_parquet(ROOT/'results/milestone_3a/od_remapping.parquet').set_index('instance_id')
    data_cfg,routing=configs(cfg['graph_data_config']);graph=load_graph(data_cfg,routing)
    transformer=Transformer.from_crs(4326,3035,always_xy=True)
    xy=np.column_stack(transformer.transform(catalogue.lon.to_numpy(),catalogue.lat.to_numpy()))
    figure_cases=[];diagnostic_router=None;fig,axes=plt.subplots(3,2,figsize=(WIDTH,7.2),layout='constrained')
    key=pd.Index(identity_keys(catalogue.osm_type,catalogue.osm_id))
    for row_index,(label,case) in enumerate(cases):
        instance=int(case.instance_id);ratio=float(case.ratio);task=case.task
        membership=pd.read_parquet(old/'region_membership.parquet',filters=[('instance_id','==',instance),('ratio','==',ratio),('method','==','decision-aware')])
        ids=key.get_indexer(identity_keys(membership.osm_type,membership.osm_id));assert(ids>=0).all()
        selected=[int(case.oracle_first_index),int(case.oracle_second_index),int(case.selected_first_index),int(case.selected_second_index)]
        selected=[i for i in selected if i>=0]
        region_ids=set(membership.loc[np.isin(ids,selected),'region_id'])
        gateways=pd.read_parquet(root/'gateways.parquet',filters=[('instance_id','==',instance),('ratio','==',ratio)])
        gateways=gateways[gateways.region_id.isin(region_ids)]
        baseline=odtable.loc[instance].path_nodes.astype(np.int64)
        bx,by=transformer.transform(graph.nodes.iloc[baseline].lon,graph.nodes.iloc[baseline].lat)
        center=xy[int(case.oracle_first_index)];radius=cfg['diagnostics']['map_radius_m']
        bounds=(center[0]-radius,center[0]+radius,center[1]-radius,center[1]+radius)
        relevant=np.array([bool(set(caps)&set(cfg['tasks'][task]['required_capabilities'])) for caps in catalogue.capabilities])
        visible=ids[relevant[ids]]
        # Macro view shows every eligible task-relevant opportunity, no sampling.
        for ax in axes[row_index]:
            ax.scatter(xy[visible,0]/1000,xy[visible,1]/1000,s=2,color='#D5D5D5',rasterized=True)
            ax.plot(np.asarray(bx)/1000,np.asarray(by)/1000,color='#777777',lw=.7,label='Baseline')
            for region_id in region_ids:
                members=ids[membership.region_id.to_numpy()==region_id]
                lo=xy[members].min(axis=0);hi=xy[members].max(axis=0)
                ax.add_patch(mpl.patches.Rectangle(lo/1000,(hi[0]-lo[0])/1000,(hi[1]-lo[1])/1000,
                    fill=False,edgecolor=COLORS['proposed'],lw=.8,linestyle=':'))
            if len(gateways):
                coords=graph.nodes.iloc[gateways.gateway_node.to_numpy()]
                gx,gy=transformer.transform(coords.lon,coords.lat)
                ax.scatter(np.asarray(gx)/1000,np.asarray(gy)/1000,s=12,marker='^',color=COLORS['geographic'],label='Topology interfaces',rasterized=True)
            ax.set_aspect('equal',adjustable='datalim');ax.set_xlabel('EPSG:3035 x (km)');ax.set_ylabel('y (km)')
        selected_routes=[]
        for name,first,second,color in [('Flat best',int(case.oracle_first_index),int(case.oracle_second_index),COLORS['proposed']),
                                      ('Cover best',int(case.selected_first_index),int(case.selected_second_index),COLORS['random'])]:
            if first<0:continue
            visits=[int(catalogue.iloc[first].access_node)]
            if second>=0:visits.append(int(catalogue.iloc[second].access_node))
            endpoints=[int(odtable.loc[instance].origin_node),*visits,int(odtable.loc[instance].destination_node)]
            sequence=[];total_time=0.;total_distance=0.
            for a,b in zip(endpoints[:-1],endpoints[1:]):
                route=graph.shortest_path(a,b);sequence.extend(route.nodes[:-1]);total_time+=route.travel_time_s;total_distance+=route.distance_m
            sequence.append(endpoints[-1])
            stored=pd.read_parquet(root/'microplans_flat'/f'od_{instance:02d}_{task}.parquet')
            target=stored[(stored.first_index==first)&(stored.second_index==second)].iloc[0]
            if abs(total_distance-target.total_route_distance_m)>1e-5:
                from microplan.routing import ExactRouter
                if diagnostic_router is None:diagnostic_router=ExactRouter(graph,cfg,ROOT/cfg['cache_dir']/'figure_routing')
                sequence=[];total_time=0.;total_distance=0.
                for a,b in zip(endpoints[:-1],endpoints[1:]):
                    costs,lengths,parents=diagnostic_router.full(a)
                    path=[b]
                    while path[-1]!=a:
                        parent=int(parents[path[-1]])
                        if parent<0:raise ValueError('Unreachable diagnostic visit')
                        path.append(parent)
                    sequence.extend(list(reversed(path))[:-1]);total_time+=costs[b];total_distance+=lengths[b]
                sequence.append(endpoints[-1])
            if abs(total_time-target.total_route_time_s)>1e-6 or abs(total_distance-target.total_route_distance_m)>1e-5:
                raise ValueError('Reconstructed diagnostic route differs from recorded exact plan')
            coords=graph.nodes.iloc[sequence]
            x,y=transformer.transform(coords.lon,coords.lat)
            for ax in axes[row_index]:
                ax.plot(np.asarray(x)/1000,np.asarray(y)/1000,color=color,lw=1,label=name,alpha=.9)
                ax.scatter(xy[[first]+([second] if second>=0 else []),0]/1000,xy[[first]+([second] if second>=0 else []),1]/1000,
                           s=30,marker='o' if name=='Flat best' else 'x',color=color,zorder=5)
            selected_routes.append({'name':name,'time_s':total_time,'length_m':total_distance,'first_index':first,'second_index':second})
        axes[row_index,1].set_xlim(bounds[0]/1000,bounds[1]/1000);axes[row_index,1].set_ylim(bounds[2]/1000,bounds[3]/1000)
        axes[row_index,1].set_aspect('equal',adjustable='box')
        axes[row_index,0].set_title(f'{label}: OD {instance}, {ratio:.2f}, {task}',fontsize=7)
        axes[row_index,1].set_title(f'Local view; absolute regret {case.absolute_regret:.5g}',fontsize=7)
        figure_cases.append({'label':label,'instance_id':instance,'ratio':ratio,'task':task,'theta_id':case.theta_id,
            'absolute_regret':float(case.absolute_regret) if np.isfinite(case.absolute_regret) else None,
            'infinite_loss':bool(np.isinf(case.absolute_regret)),'compression':float(case.compression),
            'eligible_task_objects_plotted':len(visible),'gateway_interfaces_plotted':len(gateways),'routes':selected_routes,
            'local_zoom_radius_m':radius})
    axes[0,0].legend(fontsize=5,loc='lower left')
    save(fig,out/'microplan_diagnostics',cfg['diagnostics']['dpi'])
    if diagnostic_router is not None:diagnostic_router.close()
    (out/'cases.json').write_text(json.dumps(figure_cases,indent=2)+'\n')
    qa=f'''# Figure QA\n\nPython-only quantitative grids and recorded local route diagnostics.\nAll {len(data):,} primary evaluations enter source summaries. Absent flat-oracle\nevaluations: {missing}; medium-cover infinite losses: {infinite}. Finite median/p95\npanels label this conditioning explicitly. Task plots retain missing/infinite\ncounts in their source CSV. No statistical population claims.\n\nSVG/PDF retain editable text; PNGs are 300 dpi diagnostic previews. TIFF and\n600 dpi raster submission requirements do not apply to this diagnostic bundle.\nSymlog axes retain exact zero values. Maps show all eligible task-relevant\nobjects and relevant region interfaces, with an explicit 6 km local zoom.\nFull-route polylines use frozen road node coordinates and exact directed\nfastest routes; off-road access/entrance geometry is not asserted.\nTopK coverage overlaps for K=1,3,5 by the fixed scalar ranking definition.\nCase identities and plotted counts are in cases.json. Source tables and scripts\nare retained; no arbitrary sampling or invented observations.\n'''
    (out/'QA_NOTES.md').write_text(qa)

if __name__=='__main__':main()
