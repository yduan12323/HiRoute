"""User-approved B1-O statistical closure only; never reruns the hierarchy."""
import json
import pandas as pd
from _common import ROOT,sha256
from _stopplan4r_common import write_json

out=ROOT/'results/milestone_4r_b1d';old=ROOT/'results/milestone_4r_b1'
m=pd.read_csv(old/'logical_work.csv');m=m[m.epsilon.eq(0)].copy()
defined=m.semantic_flat_sites.gt(0);v=m.loc[defined,'reduction']
median=float(v.median());p50=float(v.ge(.5).mean());p25=float(v.ge(.25).mean())
classification='strong GO' if median>=.7 and p50>=.75 else 'NO-GO' if median<.5 or p25<.75 else 'gray zone'
record=dict(all_cases=len(m),metric_defined_cases=int(defined.sum()),zero_semantic_cases=int((~defined).sum()),
    macro_conditional_median_reduction=median,p_reduction_ge_50=p50,p_reduction_ge_25=p25,
    micro_workload_reduction=float(1-m.logical_site_evaluations.sum()/m.semantic_flat_sites.sum()),
    classification=classification,zero_policy='NA; no_semantic_site_pruning_opportunity',
    authority='User B1-D prompt section 1 and B1-D formal spec sections 27–29',
    inputs_sha256={'logical_work.csv':sha256(old/'logical_work.csv')},hierarchy_rerun=False)
m['metric_status']=defined.map({True:'defined',False:'no_semantic_site_pruning_opportunity'})
m.loc[~defined,'reduction']=float('nan')
m.to_csv(out/'b1_oracle_classification.csv',index=False)
write_json(out/'b1_oracle_classification.json',record)
write_json(old/'zero_denominator_policy.json',{'policy':'defined_cases_only',**record})
write_json(old/'zero_denominator_clarification.json',{'status':'closed',**record})
for name in ['oracle_summary.json','oracle_analysis.json']:
    a=json.loads((old/name).read_text());a.update(classification=classification,median_reduction=median,
        fraction_at_least_50_percent=p50,fraction_at_least_25_percent=p25,statistical_closure=record)
    write_json(old/name,a)
report=ROOT/'docs/MILESTONE_4R_B1_REPORT.md';text=report.read_text()
text=text.replace('B1-O classification unresolved — zero semantic denominator policy required',f'B1-O {classification}')
start=text.index('The amended denominator is zero in **93/480 cases**')
end=text.index('\n\nStrong GO remains',start)
text=text[:start]+f'''The approved B1-D clarification closes this contract: 480 total cases,
387 metric-defined cases, 93 zero-semantic cases recorded as NA and
`no_semantic_site_pruning_opportunity`. All 480 remain in correctness/runtime
reporting. On the 387 defined cases, median reduction is {median:.6%},
P(r>=50%) is {p50:.6%}, and P(r>=25%) is {p25:.6%}. The all-case micro
workload reduction is {record['micro_workload_reduction']:.6%}.
The unchanged thresholds give **B1-O {classification}**. No hierarchy was rerun
or retuned. Closure tables are in `results/milestone_4r_b1d/b1_oracle_classification.*`.
The earlier unresolved state is preserved in the B1-D preservation archive.''' +text[end:]
text=text.replace('The zero-semantic denominator needs an explicit convention\nbefore a 480-case empirical classification can be interpreted.',
    'Zero-semantic cases have NA reduction; macro statistics condition on nonempty cases, while all cases remain in correctness and micro-workload reporting.')
report.write_text(text)
a=json.loads((old/'acceptance.json').read_text());a.update(passed=True,status='completed',B1_O_classification=classification,
    final_gate_statement=f'B1-O {classification}',statistical_closure=record,report_sha256=sha256(report))
write_json(old/'acceptance.json',a)
print(json.dumps(record,indent=2))
