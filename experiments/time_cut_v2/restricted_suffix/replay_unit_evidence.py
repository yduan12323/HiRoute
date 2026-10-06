"""Optimizer/production-disabled independent tiny certificate and witness replay."""
import argparse,hashlib,importlib.abc,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
BLOCKED=('scipy','numpy','timecut5','reference5','validation.suffix5.model','validation.suffix5.solver','validation.suffix5.vendor_lp','validation.suffix5.witness','validation.suffix5.query')
class NoCandidate(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if any(fullname==name or fullname.startswith(name+'.') for name in BLOCKED):raise RuntimeError('Candidate/optimizer import during independent replay: '+fullname)
sys.meta_path.insert(0,NoCandidate())
from validation.family5 import verify_bundle
from validation.family5.checker import require,wire_equal
from validation.suffix5.checker import check_regime
from validation.suffix5.evidence import check_result_witness


def main():
    p=argparse.ArgumentParser();p.add_argument('--input-root',type=Path,required=True);p.add_argument('--input-sha',required=True);p.add_argument('--records-sha',required=True);a=p.parse_args()
    inp=a.input_root/'INPUTS.json';raw=a.input_root/'RECORDS.jsonl'
    require(hashlib.sha256(inp.read_bytes()).hexdigest()==a.input_sha,'unit input anchor mismatch')
    require(hashlib.sha256(raw.read_bytes()).hexdigest()==a.records_sha,'unit certificate anchor mismatch')
    items=json.loads(inp.read_text());seen=0;witnesses=0
    for index,line in enumerate(raw.read_text().splitlines()):
        require(index<len(items),'extra unit record');row=json.loads(line);item=items[index]
        require(type(row['input_index']) is int and row['input_index']==index and row['name']==item['name'],'unit occurrence mismatch')
        require(row['input_sha256']==a.input_sha,'foreign unit input')
        ctx=verify_bundle(item['bundle'],item['case'])
        require(row['record']['model']['family_id']==item['family_id'] and wire_equal(row['record']['model']['word'],item['word']),'foreign original family/word')
        result=check_regime(ctx,row['record'])
        if result['status'] in ('attained_optimum','primary_unattained','secondary_unattained'):
            check_result_witness(ctx,row['record'],row['evidence'],row['contract']);witnesses+=1
        else:require(row['evidence'] is None and row['contract'] is None,'empty regime claims witness')
        seen+=1
    require(seen==len(items),'missing unit records')
    for name in sys.modules:require(not any(name==x or name.startswith(x+'.') for x in BLOCKED),'blocked module already loaded')
    print(json.dumps(dict(unit_records=seen,physical_witnesses=witnesses,optimization_level=sys.flags.optimize,optimizer_imports_blocked=True,frozen_TRACE01_queries_run=False)))

if __name__=='__main__':main()
