"""Persist named tiny v2 proofs. No file/input-driven acceptance solves exist."""
import argparse
import hashlib
import json
from fractions import Fraction as F
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT/'src'), str(ROOT/'tests')]
from test_restricted_suffix_v2 import unit_inputs
from validation.family5.checker import require
from validation.suffix5.model import plain
from validation.suffix5.convex_model import build_models
from validation.suffix5.solver import solve_model, solution_point, SolveBudget
from validation.suffix5.convex_checker import check_regime
from validation.suffix5.convex_witness import lift_point, result_contract
from validation.suffix5.convex_evidence import check_result_witness


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    require(not any(args.output.iterdir()), 'unit evidence output must be new and empty')
    fixtures = unit_inputs()
    inputs = []
    for name, ctx, ident, word in fixtures:
        require(ctx._physics.case['case_id'].startswith('UNIT_CONVEX_SUFFIX_'),
                'only named tiny unit physical inputs are admitted')
        inputs.append(dict(name=name, case=plain(ctx._physics.case), bundle=ctx.snapshot(),
                           family_id=ident, word=word))
    input_path = args.output/'INPUTS.json'
    input_path.write_text(json.dumps(inputs, sort_keys=True, indent=2)+'\n')
    input_sha = hashlib.sha256(input_path.read_bytes()).hexdigest()
    budget = SolveBudget(max_passes=500, wall_seconds=60, rss_mib=256)
    epsilon, summary = F(1, 10**40), []
    with (args.output/'RECORDS.jsonl').open('w') as output:
        for index, (name, ctx, ident, word) in enumerate(fixtures):
            for slot, model in enumerate(build_models(ctx, ident, word)):
                before = budget.passes
                record = solve_model(model, budget)
                result = check_regime(ctx, record)
                evidence = contract = None
                if result['status'] in ('attained_optimum', 'primary_unattained', 'secondary_unattained'):
                    evidence = lift_point(ctx, model, solution_point(record, epsilon))
                    contract = result_contract(result, epsilon)
                    check_result_witness(ctx, record, evidence, contract)
                row = dict(input_index=index, regime_index=slot, name=name, input_sha256=input_sha,
                           record=record, evidence=evidence, contract=contract)
                output.write(json.dumps(row, sort_keys=True, separators=(',', ':'))+'\n')
                output.flush()
                summary.append(dict(name=name, regime_index=slot, arrival_bands=model['arrival_bands'],
                                    result=result, candidate_passes=budget.passes-before,
                                    physical_witness_verified=evidence is not None))
    result = dict(schema='suffix5-convex-tiny-unit-evidence-v2', input_sha256=input_sha,
                  records_sha256=hashlib.sha256((args.output/'RECORDS.jsonl').read_bytes()).hexdigest(),
                  input_count=len(inputs), regime_count=len(summary), regimes=summary,
                  total_candidate_passes=budget.passes, frozen_queries_run=False,
                  source_model_review_pending=True, literal_G8_closed=False)
    (args.output/'SUMMARY.json').write_text(json.dumps(result, sort_keys=True, indent=2)+'\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'regimes'}, sort_keys=True))


if __name__ == '__main__':
    main()
