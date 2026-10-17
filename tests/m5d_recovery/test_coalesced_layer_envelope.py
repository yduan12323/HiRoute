"""Completed-layer recovery only, with fresh-process native tiny-road providers."""
from fractions import Fraction as R
from itertools import product
import json
import subprocess
import sys

import timecut5
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_layer_envelope import case, binding
import test_table_free_coalesced_solver as road_fixture
from timecut5.bounded import Problem, _replay_problem
from timecut5.coalesced_solver import table_free_problem
from timecut5.coalesce import VERSION
from timecut5.durable_incumbent import load_verified
from timecut5.hierarchy import build_regions
from timecut5.layer_envelope import run_layer_envelope, LayerEnvelopeStop, _bytes
from timecut5.provenance import primitive, witness_dict
from timecut5.real_legs import RealSite


class Fixture:
    def __init__(self):
        self.road = road_fixture.TestTableFreeCoalescing()
        self.road.setUp()
        self.c = case()
        self.c.update(origin="O", reserve_kwh=2, H_ref=2)
        self.c["edges"][0]["source"] = "O"
        self.road.query = {k:v for k,v in self.c.items()
                           if k not in ('origin','destination','sites','edges')}
        self.road.sites = {'s': RealSite('s', 'A', ('CS',))}
        self.providers = []
        self.problems = []

    def problem(self, coalescing=False):
        provider = self.road.provider()
        if provider.legs:
            raise RuntimeError('Provider must be cold')
        self.providers.append(provider)
        problem = table_free_problem(self.road.query, self.road.sites, provider,
                                     **self.road.binding(), coalescing=coalescing)
        self.problems.append(problem)
        return problem

    def binding(self):
        return binding(dict(case=self.c, road=self.road.binding(),
            nodes=self.road.nodes.read_bytes().hex(), edges=self.road.edges.read_bytes().hex()))

    def seed(self):
        problem = self.problem()
        pieces = problem.finish(problem.advance((problem.initial_piece(),), "s", "CS"))
        piece = next(p for p in pieces if p.domain.contains(R(5)))
        return piece.at(R(5)).approach(R(1))

    def run(self, path, method, coalescing=False, **kwargs):
        options = dict(problem_factory=lambda:self.problem(coalescing),
            verifier_factory=self.problem, binding_supplier=self.binding,
            initial_witness=self.seed(), method=method, output_path=path,
            root=build_regions(self.road.sites) if method=='hier' else None,
            bound_policy_sha256='a'*64, coalescing=coalescing)
        options.update(kwargs)
        return run_layer_envelope(**options)

    def close(self):
        self.road.doCleanups()


def process_run(path, report, method, coalescing, checkpoint=None, stop=None):
    fixture = Fixture()
    try:
        try:
            result = fixture.run(path, method, coalescing,
                previous_checkpoint=checkpoint, stop_after_depth=stop)
            witness, key = load_verified(str(path)+'.incumbent',
                problem_factory=fixture.problem, binding_supplier=fixture.binding)
            output = dict(result=result.canonical(), key=primitive(key),
                witness=witness_dict(witness), stopped=False,
                solution_key=primitive(_replay_problem(fixture.problem(), result.result.witness)),
                solution_witness=witness_dict(result.result.witness))
        except LayerEnvelopeStop:
            output = dict(stopped=True)
        output.update(pid=os.getpid(), providers=len(fixture.providers),
            source_runs=sum(p.source_run_count for p in fixture.providers),
            coalescing_calls=sum(p.statistics().calls for p in fixture.problems
                                 if hasattr(p, "statistics")))
        Path(report).write_text(json.dumps(primitive(output)))
    finally:
        fixture.close()


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.serial = 0
        self.fixture = Fixture()
        self.addCleanup(self.fixture.close)

    def path(self):
        self.serial += 1
        return self.base / str(self.serial)

    def checkpoint(self, method, coalescing):
        with self.assertRaises(LayerEnvelopeStop) as stopped:
            self.fixture.run(self.path(), method, coalescing, stop_after_depth=1)
        return stopped.exception.checkpoint_bytes

    def subprocess(self, method, coalescing, **kwargs):
        path = self.path()
        report = str(path)+'.report'
        # Preserve the parent's production import selection (including installed
        # wheel CI); add only fixture imports, never an implicit src fallback.
        arguments = dict(path=str(path), report=report, method=method,
                         coalescing=coalescing, **kwargs)
        if arguments.get('checkpoint') is not None:
            arguments['checkpoint'] = arguments['checkpoint'].hex()
        code = """
import json, sys
from pathlib import Path
import timecut5
if Path(timecut5.__file__).resolve() != Path(sys.argv[1]).resolve():
    raise RuntimeError('Child production package provenance differs')
sys.path.insert(0, sys.argv[2])
from test_coalesced_layer_envelope import process_run
arguments = json.loads(sys.argv[3])
if arguments.get('checkpoint') is not None:
    arguments['checkpoint'] = bytes.fromhex(arguments['checkpoint'])
process_run(**arguments)
"""
        command = [sys.executable]
        if sys.flags.optimize:
            command.append('-' + 'O' * sys.flags.optimize)
        command += ['-c', code, str(Path(timecut5.__file__).resolve()),
                    str(Path(__file__).resolve().parent), json.dumps(arguments)]
        # run() reaps this child, also killing/waiting on its own child on
        # timeout. No multiprocessing resource tracker or unrelated kill.
        environment = dict(os.environ, PYTHONPATH=str(Path(timecut5.__file__).resolve().parent.parent))
        worker = subprocess.run(command, env=environment, timeout=30, capture_output=True, text=True)
        self.assertEqual(worker.returncode, 0, worker.stdout + worker.stderr)
        return json.loads(Path(report).read_text()), path.read_bytes()

    def test_fresh_process_completed_layer_reconstruction_matrix(self):
        keys, witnesses, lowers = [], [], []
        for method, coalescing in product(('flat','hier'), (False, True)):
            with self.subTest(method=method, coalescing=coalescing):
                plain, _ = self.subprocess(method, coalescing)
                stopped, data = self.subprocess(method, coalescing, stop=1)
                restored, final = self.subprocess(method, coalescing, checkpoint=data)
                self.assertEqual(len({plain['pid'],stopped['pid'],restored['pid']}), 3)
                self.assertTrue(stopped['stopped'])
                self.assertFalse(restored['stopped'])
                self.assertGreater(restored['providers'], 1)
                self.assertGreater(restored['source_runs'], 0)
                self.assertEqual(plain['source_runs'], restored['source_runs'])
                self.assertEqual(restored['coalescing_calls'] > 0, coalescing)
                self.assertEqual(plain['coalescing_calls'], restored['coalescing_calls'])
                for field in ('result','key','witness','solution_key','solution_witness'):
                    self.assertEqual(plain[field], restored[field])
                row = json.loads(data); end = json.loads(final)
                self.assertEqual(row['state']['depth'], 1)
                self.assertEqual(end['history'][:len(row['history'])], row['history'])
                self.assertFalse(row['header']['complete'])
                self.assertEqual(row['header']['reconstruction'],
                                 'original_seed_same_source_full_replay_charged')
                config = row['header']['config']
                self.assertIs(config['coalescing'], coalescing)
                self.assertEqual(config['representation_version'], VERSION if coalescing else None)
                self.assertEqual(restored['result']['result']['lex_key'], restored['solution_key'])
                self.assertEqual(restored['solution_key'], ['12', '2', 1, [['s', 'CS']]])
                self.assertEqual(restored['key'], ['12', '5', 1, [['s', 'CS']]])
                lower = row['state']['lower_bounds']['bounded_domain_conservative_primary']
                self.assertEqual(lower, '11')
                self.assertLessEqual(R(lower), R(restored['key'][0]))
                keys.append(restored['solution_key']); witnesses.append(restored['solution_witness']); lowers.append(lower)
        self.assertTrue(all(k==keys[0] for k in keys))
        self.assertTrue(all(w==witnesses[0] for w in witnesses))
        self.assertTrue(all(v==lowers[0] for v in lowers))

    def test_config_tampering_old_schema_and_cross_mode_fail_closed(self):
        for method, enabled in product(('flat','hier'), (False, True)):
            data = self.checkpoint(method, enabled)
            for field, value in (('coalescing',not enabled),('coalescing',int(enabled)),
                    ('representation_version','unknown'),('bound_policy_sha256','b'*64)):
                row = json.loads(data); row['header']['config'][field] = value
                path = self.path()
                with self.subTest(method=method,enabled=enabled,field=field), self.assertRaises(ValueError):
                    self.fixture.run(path,method,enabled,previous_checkpoint=_bytes(row))
                self.assertFalse(path.exists())
            with self.assertRaises(ValueError):
                self.fixture.run(self.path(),method,not enabled,previous_checkpoint=data)
            row = json.loads(data); row['header']['schema']='hiroute.completed_layer_envelope.v1'
            del row['header']['config']['coalescing']; del row['header']['config']['representation_version']
            with self.assertRaises(ValueError):
                self.fixture.run(self.path(),method,enabled,previous_checkpoint=_bytes(row))
            with self.assertRaisesRegex(ValueError,'Cannot stop'):
                self.fixture.run(self.path(),method,enabled,previous_checkpoint=data,stop_after_depth=0)

    def test_adapter_flag_version_and_reducer_are_explicit(self):
        for value in (1,None,'true'):
            with self.assertRaises(ValueError):
                self.fixture.run(self.path(),'flat',value)
        for enabled, factory in ((True,lambda:self.fixture.problem(False)),
                (False,lambda:self.fixture.problem(True)),(True,lambda:Problem(self.fixture.c))):
            with self.assertRaises(ValueError):
                self.fixture.run(self.path(),'flat',enabled,problem_factory=factory)
        problem=self.fixture.problem(True); problem.reduce=lambda pieces:pieces
        with self.assertRaises(ValueError):
            self.fixture.run(self.path(),'flat',True,problem_factory=lambda:problem)
        for module in ('coalesce','coalesced_solver'):
            with patch('timecut5.'+module+'.VERSION','unsupported'), self.assertRaises(ValueError):
                self.fixture.run(self.path(),'flat',True)
        problem=self.fixture.problem(True); problem._record_lineage=True
        with self.assertRaises(ValueError):
            self.fixture.run(self.path(),'flat',True,problem_factory=lambda:problem)
        for method in ('flat','hier'):
            problem=self.fixture.problem(True)
            original=problem.reduce
            with patch('timecut5.layer_envelope.'+('_solve_problem' if method=='flat' else '_solve_hierarchical_problem')) as solve:
                self.fixture.run(self.path(),method,True,problem_factory=lambda:problem)
                self.assertEqual(solve.call_args.kwargs['reducer'], original)
            with patch('timecut5.coalesced_solver.coalesce_pieces',side_effect=AssertionError('default enabled')):
                self.fixture.run(self.path(),method)


if __name__=='__main__':
    unittest.main()
