"""Optimizer/candidate-disabled complete raw convex tiny-evidence replay."""
import argparse
import hashlib
import importlib.abc
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
BLOCKED = ('scipy', 'numpy', 'timecut5', 'reference5', 'validation.suffix5.model',
           'validation.suffix5.solver', 'validation.suffix5.vendor_lp', 'validation.suffix5.witness',
           'validation.suffix5.query', 'validation.suffix5.convex_model',
           'validation.suffix5.convex_witness', 'validation.suffix5.convex_query')


class NoCandidate(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == name or fullname.startswith(name+'.') for name in BLOCKED):
            raise RuntimeError('Candidate/optimizer import during independent replay: '+fullname)


sys.meta_path.insert(0, NoCandidate())
from validation.family5 import verify_bundle
from validation.family5.checker import require, wire_equal
from validation.suffix5.independent_convex_model import build_models
from validation.suffix5.convex_checker import check_regime
from validation.suffix5.convex_evidence import check_result_witness


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input-root', type=Path, required=True)
    parser.add_argument('--input-sha', required=True)
    parser.add_argument('--records-sha', required=True)
    args = parser.parse_args()
    inp, raw = args.input_root/'INPUTS.json', args.input_root/'RECORDS.jsonl'
    require(hashlib.sha256(inp.read_bytes()).hexdigest() == args.input_sha, 'unit input anchor mismatch')
    require(hashlib.sha256(raw.read_bytes()).hexdigest() == args.records_sha, 'unit certificate anchor mismatch')
    items = json.loads(inp.read_text())
    expected = []
    for index, item in enumerate(items):
        require(item['case']['case_id'].startswith('UNIT_CONVEX_SUFFIX_'), 'non-unit input forbidden')
        ctx = verify_bundle(item['bundle'], item['case'])
        for slot, model in enumerate(build_models(ctx, item['family_id'], item['word'])):
            expected.append((index, slot, item, ctx, model))
    rows = raw.read_text().splitlines()
    require(len(rows) == len(expected), 'incomplete original input/band regime coverage')
    witnesses, statuses = 0, {}
    for line, (index, slot, item, ctx, model) in zip(rows, expected):
        row = json.loads(line)
        require(type(row['input_index']) is int and row['input_index'] == index,
                'input occurrence mismatch')
        require(type(row['regime_index']) is int and row['regime_index'] == slot,
                'regime occurrence mismatch')
        require(row['name'] == item['name'] and row['input_sha256'] == args.input_sha,
                'foreign unit input')
        require(wire_equal(row['record']['model'], model), 'foreign original family/word/band model')
        result = check_regime(ctx, row['record'])
        statuses[result['status']] = statuses.get(result['status'], 0)+1
        if result['status'] in ('attained_optimum', 'primary_unattained', 'secondary_unattained'):
            check_result_witness(ctx, row['record'], row['evidence'], row['contract'])
            witnesses += 1
        else:
            require(row['evidence'] is None and row['contract'] is None, 'empty regime claims witness')
    for name in sys.modules:
        require(not any(name == blocked or name.startswith(blocked+'.') for blocked in BLOCKED),
                'blocked module already loaded')
    print(json.dumps(dict(unit_inputs=len(items), unit_regimes=len(rows), physical_witnesses=witnesses,
                         statuses=statuses, optimization_level=sys.flags.optimize,
                         optimizer_imports_blocked=True, frozen_queries_run=False), sort_keys=True))


if __name__ == '__main__':
    main()
