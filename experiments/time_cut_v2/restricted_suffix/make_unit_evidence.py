"""Materialize only the named tiny unit cases, never the frozen TRACE01 pilot."""
import hashlib,json,sys
from fractions import Fraction as F
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'));sys.path.insert(0,str(ROOT/'src'))
from test_restricted_suffix_v1 import tiny_case,initial_context,inherited_context,foreign_context
from validation.suffix5.solver import solve_model,solution_point,SolveBudget
from validation.suffix5.model import build_model,plain
from validation.suffix5.checker import check_regime
from validation.suffix5.witness import lift_point,result_contract
from validation.suffix5.evidence import check_result_witness
from validation.family5.checker import require


def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True);items=[];contexts=[]
    def add(name,ctx,ident,effect):
        require(ctx._physics.case['case_id'].startswith('UNIT_SUFFIX_'),'protected/non-unit population forbidden')
        items.append(dict(name=name,case=plain(ctx._physics.case),bundle=ctx.snapshot(),family_id=ident,word=[['c',effect]]));contexts.append(ctx)
    for name,effect in [('attained','C'),('primary_open','C'),('secondary_open','CS'),('closed_empty','C'),('strict_empty','C'),('graph_empty','C'),('inverted_window','S')]:
        ctx,ident=initial_context(tiny_case(name));add(name,ctx,ident,effect)
    for name,effect in [('energy_open','S'),('time_open','C')]:
        ctx,ident=inherited_context(name);add('inherited_'+name,ctx,ident,effect)
    ctx,ids=foreign_context()
    for label,ident in zip(('A','B'),ids):add('foreign_'+label,ctx,ident,'C')
    inputs=a.output/'INPUTS.json';inputs.write_text(json.dumps(items,sort_keys=True,indent=2)+'\n')
    input_sha=hashlib.sha256(inputs.read_bytes()).hexdigest()
    (a.output/'INPUT_FREEZE.json').write_text(json.dumps(dict(schema='suffix5-tiny-unit-input-freeze-v1',input_sha256=input_sha,cases=[x['name'] for x in items],frozen_TRACE01_population=False),sort_keys=True,indent=2)+'\n')
    budget=SolveBudget(max_passes=100,wall_seconds=60,rss_mib=256);epsilon=F(1,10**40);summary=[]
    with (a.output/'RECORDS.jsonl').open('w') as stream:
        for index,(item,ctx) in enumerate(zip(items,contexts)):
            before=budget.passes;model=build_model(ctx,item['family_id'],item['word']);record=solve_model(model,budget)
            independent=check_regime(ctx,record,with_audit=True)
            result=record['result'];evidence=contract=audit=None
            if result['status'] in ('attained_optimum','primary_unattained','secondary_unattained'):
                evidence=lift_point(ctx,model,solution_point(record,epsilon));contract=result_contract(result,epsilon)
                audit=check_result_witness(ctx,record,evidence,contract)
            row=dict(input_index=index,name=item['name'],input_sha256=input_sha,record=record,evidence=evidence,contract=contract)
            stream.write(json.dumps(row,sort_keys=True,separators=(',',':'))+'\n');stream.flush()
            summary.append(dict(name=item['name'],result=independent['result'],candidate_passes=budget.passes-before,physical_witness_verified=audit is not None))
    result=dict(schema='suffix5-tiny-unit-evidence-v1',input_sha256=input_sha,records_sha256=hashlib.sha256((a.output/'RECORDS.jsonl').read_bytes()).hexdigest(),cases=summary,total_candidate_passes=budget.passes,frozen_TRACE01_queries_run=False,literal_G8_closed=False)
    (a.output/'SUMMARY.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
