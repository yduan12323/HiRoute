"""All-OD absolute and marginal growth; data extent is not decision value."""
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from _common import ROOT


def main():
    directory = ROOT/'results/milestone_3a'
    output = directory/'figures'
    output.mkdir(parents=True,exist_ok=True)
    table = pd.read_parquet(directory/'envelope_stats.parquet')
    comparison = pd.read_parquet(directory/'envelope_comparison.parquet')
    assert len(table)==210 and table.instance_id.nunique()==30
    table.to_csv(output/'growth_source_data.csv',index=False)
    plt.rcParams.update({'font.family':'sans-serif','font.sans-serif':['DejaVu Sans'],
        'font.size':7,'axes.spines.right':False,'axes.spines.top':False,
        'svg.fonttype':'none','pdf.fonttype':42,'axes.linewidth':0.8,'legend.frameon':False})
    ratios=sorted(table.ratio.unique())
    fig,axes=plt.subplots(2,2,figsize=(7.205,5.315),layout='constrained')
    for ax,column,title in [(axes[0,0],'nodes','Envelope vertices'),(axes[0,1],'edges','Envelope directed edges')]:
        for _,od in table.groupby('instance_id'):
            od=od.sort_values('ratio');ax.plot(od.ratio,od[column]/1e6,color='#8AB0C2',alpha=0.3,lw=0.6)
        med=table.groupby('ratio')[column].median()/1e6
        si=comparison.groupby('ratio')['si_'+column].median()/1e6
        ax.plot(ratios,med,color='#245B78',marker='o',ms=3,label='Extended median')
        ax.plot(ratios,si,color='#777777',ls='--',label='Slovenia median')
        ax.set_ylabel(title+' (millions)');ax.legend(fontsize=6)
    for ax,column,title in [(axes[1,0],'delta_nodes','Added vertices'),(axes[1,1],'delta_edges','Added directed edges')]:
        data=table.loc[table.marginal_from_previous]
        for _,od in data.groupby('instance_id'):
            od=od.sort_values('ratio');ax.plot(od.ratio,od[column]/1e6,color='#8AB0C2',alpha=0.3,lw=0.6)
        ax.plot(ratios[1:],data.groupby('ratio')[column].median()/1e6,color='#245B78',marker='o',ms=3)
        ax.set_ylabel(title+' (millions)')
    for label,ax in zip('abcd',axes.flat):
        ax.set_xlabel('Budget ratio α (B = αC*)')
        ax.set_xticks(ratios,[f'{r:.2f}' for r in ratios],rotation=40)
        ax.text(-0.14,1.06,label,transform=ax.transAxes,fontweight='bold',fontsize=8)
    fig.savefig(output/'absolute_marginal_growth.svg')
    fig.savefig(output/'absolute_marginal_growth.pdf')
    fig.savefig(output/'absolute_marginal_growth.png',dpi=600)
    plt.close(fig)
    growth=pd.read_csv(directory/'envelope_growth.csv')
    fig,ax=plt.subplots(figsize=(3.504,2.756),layout='constrained')
    ax.plot(growth.ratio,growth.si_boundary_risk_ods,color='#777777',ls='--',marker='s',ms=3,label='Slovenia')
    ax.plot(growth.ratio,growth.boundary_risk_ods,color='#245B78',marker='o',ms=3,label='Extended')
    ax.set(xlabel='Budget ratio α',ylabel='ODs with boundary risk (of 30)',ylim=(-1,31))
    ax.set_xticks(ratios,[f'{r:.2f}' for r in ratios],rotation=40);ax.legend(fontsize=6)
    fig.savefig(output/'boundary_risk.svg')
    fig.savefig(output/'boundary_risk.pdf')
    fig.savefig(output/'boundary_risk.png',dpi=600)
    plt.close(fig)
    (output/'QA.md').write_text('''# Figure contract and QA

Conclusion: geographic expansion changes the computational size and boundary risk
of Slovenia-centered bounded-detour envelopes; the measured direction and magnitude
are shown without inferring decision value.

Quantitative grid, Python/matplotlib; 183 × 135 mm growth figure and 89 × 70 mm
boundary figure. SVG/PDF retain editable text; PNG previews at 600 dpi.
All 30 frozen ODs and all seven ratios are included (210 rows). Thin lines are
individual ODs; heavy lines are medians, not uncertainty intervals. No inferential
test or independent-repeat claim is made. Marginal panels omit ratio 1.00 because
it has no previous configured budget; they show raw consecutive differences,
with unequal ratio intervals explicitly labelled. Both datasets use their own C*.
Slovenia curves are read from frozen Milestone 2 outputs. Source data are
growth_source_data.csv, envelope_comparison.csv and envelope_growth.csv.

Boundary risk is the same projected 1 km inward-buffer proximity diagnostic;
no global completeness certificate is implied. Area panels are not included in
these figures; CSV tables supply occupied-cell and bounding-box areas.
Graph-size saturation is not decision-value saturation.
''')


if __name__=='__main__':main()
