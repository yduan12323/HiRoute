"""Prespecified original-domain Tranche B: synthetic and tiny-native tests only."""
import copy
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

_TESTS = Path(__file__).resolve().parents[1]
for _path in (_TESTS, _TESTS / 'm5d_recovery'):
    if str(_path) not in sys.path:
        sys.path.append(str(_path))

from experiments.dev_coverage_tranche_v1 import bindings
from experiments.dev_coverage_tranche_v1 import domain as adapter
from experiments.dev_coverage_tranche_v1 import lifecycle
from experiments.dev_coverage_tranche_v1 import run as gate
from experiments.dev_cohort_v1 import run as cohort
from experiments.mechanism_recovery_v1 import run as base
from test_projection_support_gate import tiny_domain as support_domain
from synthetic_runtime_inputs import synthetic_tranche, toy_prefix, toy_binding


A_CASES = tuple('OD' + n + '_energy_and_scheduled_soc19_25' for n in ('01', '03', '04', '05'))
B_CASES = ('OD08_energy_and_scheduled_soc19_25', 'OD09_energy_and_scheduled_soc19_25',
           'OD06_energy_and_scheduled_soc3_10', 'OD07_energy_and_scheduled_soc3_10')
QUEUE = tuple((case, n) for n in (32, 128) for case in B_CASES if (case,n)!=(B_CASES[2],128))


def original_common(manifest):
    """Metadata-only common receipt, with a fresh seed-derived non-placeholder Hmax."""
    spec = gate.spec_for(manifest, manifest['case_id'])
    binding = toy_binding(spec)
    query = copy.deepcopy(binding['query'])
    query['sparse_domain_sha256'] = 'a' * 64
    unit = F(query['overhead_s']) + F(query['lambda_stop_s'])
    key = [str(unit * 7 + F(1, 2)), '1', 1, [[binding['candidate_site_ids'][0], 'CS']]]
    tree_sha = base.digest(['synthetic original topology'])
    return dict(schema=gate.SCHEMA, status='common_feasible_seed', case_id=manifest['case_id'],
                candidate_count=manifest['candidate_count'], case_binding_sha256=base.digest(spec), query=query,
                historical_query_sha256=binding['query_sha256'], runtime_rebinding_fields=['sparse_domain_sha256'],
                sites=toy_prefix(spec), tree_sha256=tree_sha,
                seed=dict(max_depth=7, key_bytes=base.canonical(key).decode(), query_sha256=base.digest(query),
                          site_sha256=binding['site_catalog_sha256'], tree_sha256=tree_sha),
                source=manifest['source'], inputs=manifest['inputs'], cache_policy=manifest['cache_policy'])


def tiny_domain(root, arm, *, required_hmax=None):
    from timecut5.real_legs import RealSite
    original = support_domain(root / 'original', 'support_on')
    query = json.loads(original.query_bytes)
    query['schedule'] = dict(a=2, b=30, D=1)
    # H_ref is only a proposal placeholder. The frozen witness supplies Hmax.
    query['H_ref'] = 4
    sites = {sid: RealSite(site.site_id, site.anchor_id, ('C', 'S', 'CS'))
             for sid, site in original.sites.items()}
    return adapter.ScheduledMethodDomain(arm=arm, required_hmax=required_hmax,
        case_binding={'case_id': 'tiny-original', 'candidate_count': len(sites)},
        manifest_binding=base.digest('tiny original-domain coverage'), graph_factory=original.graph_factory,
        query=query, sites=sites, tree=original.tree, source_hashes=original.source_hashes,
        cache=root / 'method', compiler=original.compiler['compiler'])


def terminal_fixture(arm, hmax=7, status='attained_optimum', key=None):
    key = key or ['8', '1', 1, [['s', 'CS']]]
    payload = dict(status='attained_optimum', J=key[0], Q_total=key[1], H=key[2],
                   site_action_tuple=key[3], lex_key=key)
    if status == 'infimum_unattained':
        payload = dict(status='primary_unattained', primary_infimum='7')
    common = dict(status=status, method=arm, strategy=arm, pending_window_arm=arm,
        accepted_key=key, pending_window_schema=gate.SCHEMA,
        pending_window_configuration=gate.CONFIGS[arm], post_service_policy=gate.POST_SERVICE_POLICY,
        pending_window_policy=gate.PENDING_WINDOW_POLICY, completion_policy=gate.COMPLETION_POLICY,
        analytic_charge_policy=gate.ANALYTIC_POLICY)
    return (dict(common, Hmax=hmax, seed_key=key, result=dict(H_ref=hmax, result=payload)),
            dict(common, search_status='SUCCESS'))


class DevCoverageTrancheTests(unittest.TestCase):
    def test_fixed_B_queue_seven_domains_fourteen_rows_thirtyfive_slots(self):
        self.assertEqual(bindings.A_CASES, A_CASES)
        self.assertEqual(bindings.B_CASES, B_CASES)
        self.assertEqual(bindings.QUEUE, QUEUE)
        self.assertEqual(gate.CASES, B_CASES)
        self.assertEqual(tuple(c['query_id'] for c in bindings.PLAN['cases']), A_CASES + B_CASES)
        self.assertEqual(hashlib.sha256(bindings.PLAN_PATH.read_bytes()).hexdigest(), bindings.PLAN_SHA256)
        stage = bindings.PLAN['execution_stages'][1]
        self.assertEqual(stage['query_ids'], list(B_CASES))
        self.assertEqual(stage['N_order'], [32, 128])
        self.assertEqual((stage['coverage_grid_domains'], stage['new_method_rows'], stage['new_operational_slots']), (8, 14, 35))
        self.assertIs(stage['automatic_start'], False)
        plans = [gate.prospective(case, n) for case, n in QUEUE]
        self.assertEqual(sum(p['denominator']['total_stages'] for p in plans), 35)
        self.assertEqual(sum(len(p['methods']) for p in plans), 14)
        for plan, (case, n) in zip(plans, QUEUE):
            self.assertEqual((plan['case_id'], plan['candidate_count']), (case, n))
            self.assertEqual(plan['order'], [[case, ['flat', 'hier']]])
            self.assertEqual(plan['runnable_tranche'], 'B')
            self.assertEqual(plan['prospective_full_selection'], bindings.PLAN)
            for name in ('launchable', 'tranche_A_launchable', 'automatic_next_run', 'holdout', 'historical_pooling',
                         'require_positive_result', 'outcome_blind', 'same_budget_speedup_comparison',
                         'historical_treatment_completion_is_paired_result'):
                self.assertIs(plan[name], False, name)
        for case in A_CASES + ('OD11_energy_and_scheduled_soc19_25',):
            for n in (32, 128):
                with self.assertRaises(ValueError):
                    gate.prospective(case, n)
        for n in (True, 32.0, '32', 0, 64, None):
            with self.assertRaises(ValueError):
                gate.prospective(B_CASES[0], n)

    def test_original_full_bindings_prefixes_and_exact_case_N_allowlist(self):
        for case in bindings.PLAN['cases']:
            low, high = case['domains']
            self.assertNotIn('original_pool_prefix', low)
            self.assertNotIn('original_pool_prefix', high)
            for spec in (low, high):
                n = spec['candidate_count']
                binding = spec['original_binding']
                self.assertEqual(spec['case_id'], case['query_id'] + '_n' + str(n))
                self.assertEqual(binding['query']['case_id'], case['query_id'])
                self.assertEqual(binding['query']['H_ref'], 4)
                self.assertNotIn('candidate_site_ids', binding)
                self.assertEqual(len(spec['original_pool_prefix_sha256']), 64)
                self.assertEqual(len(binding['candidate_site_ids_sha256']), 64)
                self.assertEqual(base.digest(binding['query']), binding['query_sha256'])
                if (case['query_id'],n) not in QUEUE:
                    with self.assertRaises(ValueError):
                        bindings.spec_for(dict(case_id=case['query_id'], candidate_count=n, case_binding=spec), case['query_id'])
                    continue
                manifest = gate.prospective(case['query_id'], n)
                self.assertEqual(gate.spec_for(manifest, case['query_id']), spec)
                for change in (dict(candidate_count=128 if n == 32 else 32), dict(candidate_count=True),
                               dict(case_id=B_CASES[(B_CASES.index(case['query_id']) + 1) % 4]), dict(case_binding={})):
                    with self.assertRaises(ValueError):
                        gate.spec_for(dict(manifest, **change), case['query_id'])
                bad = copy.deepcopy(manifest)
                bad['case_binding']['original_pool_prefix_sha256'] = '0' * 64
                with self.assertRaises(ValueError):
                    gate.spec_for(bad, case['query_id'])

    def test_selection_digest_and_semantic_binding_tampering_fail_closed(self):
        mutations = (
            lambda p: p['cases'].reverse(),
            lambda p: p['cases'][0]['domains'].reverse(),
            lambda p: p['cases'][0]['domains'][0].update(original_pool_prefix_sha256='invalid'),
            lambda p: p['cases'][0]['domains'][1]['original_binding']['query'].update(H_ref=9),
            lambda p: p['cases'][0]['domains'][1]['original_binding'].update(candidate_site_ids_sha256='invalid'),
        )
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'selection.json'
            for mutate in mutations:
                altered = copy.deepcopy(bindings.PLAN)
                mutate(altered)
                raw = base.canonical(altered)
                path.write_bytes(raw)
                with patch.object(bindings, 'PLAN_PATH', path), patch.object(bindings, 'PLAN_SHA256', hashlib.sha256(raw).hexdigest()):
                    with self.assertRaises(ValueError):
                        bindings.selection()
            path.write_bytes(base.canonical(bindings.PLAN) + b' ')
            with patch.object(bindings, 'PLAN_PATH', path):
                with self.assertRaisesRegex(ValueError, 'selection changed'):
                    bindings.selection()

    def test_both_review_and_current_pair_outcome_guard_freeze_and_consumption(self):
        statuses = (
            ('pending_independent_dev_coverage_tranche_B_review', 'pending_root_tranche_A_terminal_review', 'review is pending'),
            ('pending_independent_dev_coverage_tranche_B_review', 'root_tranche_A_terminal_reviewed', 'review is pending'),
            ('approved_independent_dev_coverage_tranche_B_review', 'pending_root_tranche_A_terminal_review', 'Tranche A terminal outcome is pending'),
        )
        for review, current, message in statuses:
            with self.subTest(review=review, current=current), tempfile.TemporaryDirectory() as temp, \
                    patch.object(gate, 'REVIEW_STATUS', review), patch.object(gate, 'CURRENT_PAIR_STATUS', current):
                with self.assertRaisesRegex(ValueError, message):
                    gate.require_launch_review()
                target = Path(temp) / 'manifest.json'
                with patch.object(sys, 'argv', ['gate', '--freeze', '--case', B_CASES[0], '--candidate-count', '32',
                                               '--input-directory', temp, '--output', str(target)]), \
                        patch.object(gate, 'source_identity') as identity, patch.object(base, 'load_graph') as load:
                    with self.assertRaisesRegex(ValueError, message):
                        gate.main()
                identity.assert_not_called()
                load.assert_not_called()
                self.assertFalse(target.exists())
                plan = gate.prospective(B_CASES[0], 32)
                plan['launchable'] = True
                target.write_bytes(base.canonical(plan))
                with self.assertRaisesRegex(ValueError, message):
                    gate._manifest(target, base.file_hash(target))
        with patch.object(gate, 'REVIEW_STATUS', 'approved_independent_dev_coverage_tranche_B_review'), \
                patch.object(gate, 'CURRENT_PAIR_STATUS', 'root_tranche_A_terminal_reviewed'):
            gate.require_launch_review()

    def test_same_budget_historical_runtime_and_disabled_optional_features(self):
        self.assertEqual(gate.ARMS, ('flat', 'hier'))
        for case, n in QUEUE:
            plan = gate.prospective(case, n)
            self.assertEqual(plan['source_base_commit'], '43e83b57429dc06c18763339f06444bd5b40f44d')
            self.assertEqual(plan['production_source_entries'], 96)
            self.assertEqual(plan['allowed_new_production_modules'], [])
            self.assertEqual(plan['denominator'], dict(common_preparations=1, search_arms=2, independent_replays=2, total_stages=5))
            self.assertEqual((plan['limits']['search_seconds'], plan['limits']['search_worker_wall_seconds'],
                              plan['limits']['search_worker_cpu_seconds']), (1200, 1500, 1500))
            self.assertEqual(plan['execution_policy']['max_heavy_workers'], 1)
            self.assertIs(plan['execution_policy']['automatic_retry'], False)
            self.assertEqual(plan['memory_policy']['required_available_memory_bytes'], 7168 * 1024 ** 2)
            self.assertEqual(plan['shared_configuration'], cohort.shared_configuration(False))
            self.assertIs(plan['same_budget_method_comparison'], True)
            self.assertIn('unchanged_original_seed_to_depth_rule', plan['hmax_policy'])
            for arm in gate.ARMS:
                config = plan['arms'][arm]
                self.assertEqual(config['method'], arm)
                self.assertEqual(config['shared_configuration'], plan['shared_configuration'])
                for name in ('analytic_charge', 'post_service_dominance', 'pending_window_dominance'):
                    self.assertIs(config[name], True)
                for name in ('convex_charge_count_runtime', 'operator_compaction_candidate',
                             'lazy_native_allocation_backend', 'service_deadline_screen'):
                    self.assertIs(config[name], False)
                    self.assertIs(plan['completion_policy'][name], False)
                self.assertIs(config['shared_configuration']['envelope_sweep'], False)
                self.assertIs(config['shared_configuration']['coalescing'], False)
            self.assertEqual(plan['completion_policy']['runtime_variant'], 'historical_remaining_charge_runtime_v1')

    @synthetic_tranche
    def test_extract_exact_original_metadata_without_graph_load_or_candidate_repair(self):
        from timecut5.real_adapter import site_catalog_digest
        for case, n in QUEUE:
            with self.subTest(case=case, n=n), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                manifest = gate.prospective(case, n)
                spec = gate.spec_for(manifest, case)
                row = dict(query_id=case, od_id=case.split('_')[0], bindings={str(n): toy_binding(spec)})
                pool = dict(od_id=row['od_id'], sites=toy_prefix(spec))
                (root / 'queries.json').write_bytes(base.canonical(dict(queries=[row])))
                (root / 'pools.json').write_bytes(base.canonical(dict(pools=[pool])))
                (root / 'hierarchy.json').write_bytes(b'{}')
                for name in ('nodes.parquet', 'edges.parquet', 'metadata.json'):
                    (root/name).write_bytes(b'test-only graph loader placeholder')
                tree = object()
                with patch.object(base, 'verify_inputs') as inputs, patch.object(base, 'original_tree', return_value=tree) as topology, \
                        patch.object(base, 'load_graph') as load:
                    query, sites, returned_tree = gate.extract_case(root, case, manifest['inputs'], manifest)
                    self.assertEqual(query, spec['original_binding']['query'])
                    self.assertEqual(list(sites), toy_binding(spec)['candidate_site_ids'])
                    self.assertEqual(site_catalog_digest(sites), spec['original_binding']['site_catalog_sha256'])
                    self.assertIs(returned_tree, tree)
                    inputs.assert_called_once()
                    self.assertEqual(topology.call_args.args[2], list(sites))
                    load.assert_not_called()
                    pool['sites'] = list(reversed(pool['sites']))
                    (root / 'pools.json').write_bytes(base.canonical(dict(pools=[pool])))
                    with self.assertRaisesRegex(ValueError, 'Original ordered generated pool prefix differs'):
                        gate.extract_case(root, case, manifest['inputs'], manifest)

    @synthetic_tranche
    def test_common_depth_uses_fresh_original_seed_and_keeps_original_hash_distinct(self):
        for case, n in QUEUE:
            with self.subTest(case=case, n=n), tempfile.TemporaryDirectory() as temp:
                manifest = dict(gate.prospective(case, n), input_directory=temp, source={'closure_sha256': 'b' * 64})
                (Path(temp) / 'hierarchy.json').write_bytes(b'{}')
                common = original_common(manifest)
                self.assertEqual(common['query']['H_ref'], 4)
                self.assertEqual(common['seed']['max_depth'], 7)
                self.assertNotEqual(common['historical_query_sha256'], common['seed']['query_sha256'])
                with patch.object(base, 'original_tree', return_value=object()), \
                        patch.object(base, 'tree_value', return_value=['synthetic original topology']), patch.object(base, 'load_graph') as load:
                    gate.validate_common(common, case, manifest)
                    for mutate in (
                        lambda c: c['seed'].update(max_depth=4),
                        lambda c: c['seed'].update(max_depth=True),
                        lambda c: c['seed'].update(key_bytes=base.canonical(['1800', '1', 1, [['s', 'CS']]]).decode()),
                        lambda c: c['query'].update(H_ref=7),
                        lambda c: c['query'].update(overhead_s='301'),
                        lambda c: c.update(historical_query_sha256=c['seed']['query_sha256']),
                        lambda c: c['seed'].update(query_sha256=c['historical_query_sha256']),
                        lambda c: c['sites'].reverse(),
                        lambda c: c.update(tree_sha256='0' * 64),
                        lambda c: c.update(candidate_count=True),
                        lambda c: c.update(source={}),
                    ):
                        bad = copy.deepcopy(common)
                        mutate(bad)
                        with self.assertRaises(ValueError):
                            gate.validate_common(bad, case, manifest)
                    load.assert_not_called()

    @synthetic_tranche
    def test_domain_factory_wires_original_placeholder_then_admitted_seed_depth(self):
        from timecut5.real_legs import RealSite
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'hierarchy.json').write_bytes(b'{}')
            for case, n in QUEUE:
                manifest = dict(gate.prospective(case, n), input_directory=temp, source={'closure_sha256': 'b' * 64},
                                compiler={'path': '/synthetic/compiler'})
                spec = gate.spec_for(manifest, case)
                sites = {s['site_id']: RealSite(s['site_id'], s['anchor_id'], tuple(s['effects']))
                         for s in toy_prefix(spec)}
                for depth in (None, 7):
                    with patch.object(base, 'original_tree', return_value='original tree'), \
                            patch.object(gate, 'ScheduledMethodDomain') as construct, patch.object(base, 'load_graph') as load:
                        gate.domain_factory(manifest, spec['original_binding']['query'], sites, root / 'native',
                                            arm='flat', case_id=case, admitted_hmax=depth)
                        args = construct.call_args.kwargs
                        self.assertEqual(args['required_hmax'], depth)
                        self.assertEqual(args['query']['H_ref'], 4)
                        self.assertEqual(args['case_binding'], spec)
                        self.assertEqual(args['tree'], 'original tree')
                        load.assert_not_called()
                with patch.object(base, 'load_graph') as load:
                    with self.assertRaisesRegex(ValueError, 'candidate order differs'):
                        gate.domain_factory(manifest, spec['original_binding']['query'], dict(reversed(list(sites.items()))),
                                            root / 'bad', arm='flat', case_id=case)
                    load.assert_not_called()

    def test_terminal_full_key_unattained_and_fresh_depth_authentication(self):
        for arm in gate.ARMS:
            completed, replayed = terminal_fixture(arm)
            self.assertEqual(gate.validate_terminal(completed, replayed, arm, 7),
                             dict(status='attained_optimum', lex_key=completed['accepted_key']))
            for depth in (4, True, '7'):
                with self.assertRaises(ValueError):
                    gate.validate_terminal(completed, replayed, arm, depth)
            for key in (['16/2', '1', 1, [['s', 'CS']]], ['8', '1', True, [['s', 'CS']]],
                        ['8', 1, 1, [['s', 'CS']]], ['8', '1', 1, []]):
                bad, full = terminal_fixture(arm, key=key)
                with self.assertRaises(ValueError):
                    gate.validate_terminal(bad, full, arm, 7)
            completed, replayed = terminal_fixture(arm, status='infimum_unattained')
            self.assertEqual(gate.validate_terminal(completed, replayed, arm, 7),
                             dict(status='primary_unattained', primary_infimum='7'))
            for payload in (dict(status='primary_unattained', primary_infimum='14/2'),
                            dict(status='primary_unattained', primary_infimum='-1'),
                            dict(status='primary_unattained', primary_infimum='7', extra='1')):
                bad = copy.deepcopy(completed)
                bad['result']['result'] = payload
                with self.assertRaises(ValueError):
                    gate.validate_terminal(bad, replayed, arm, 7)

    def test_tiny_native_canonical_parity_original_seed_depth_and_fresh_full_replay(self):
        from timecut5.bounded import _solve_problem
        from timecut5 import bounded, hierarchy, pending_window_dominance
        from timecut5.remaining_charge_runtime import RemainingChargeRuntimeV1
        answers, seeds = [], []
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = tiny_domain(root / 'seed', 'flat')
            with adapter.historical_operators(), first.context('verification') as context:
                witness = _solve_problem(first.problem(context), True).result.witness
            for arm in gate.ARMS:
                domain = tiny_domain(root / arm, arm)
                seed = domain.freeze_seed(witness)
                seeds.append(seed)
                self.assertEqual(seed.max_depth, base.depth_bound(json.loads(domain.query_bytes), (F(json.loads(seed.key_bytes)[0]),)))
                self.assertNotEqual(seed.max_depth, json.loads(domain.query_bytes)['H_ref'])
                output = root / ('result-' + arm)
                module = bounded if arm == 'flat' else hierarchy
                entry = '_solve_problem' if arm == 'flat' else '_solve_hierarchical_problem'
                with patch.object(module, entry, wraps=getattr(module, entry)) as engine, \
                        patch.object(pending_window_dominance, 'make_pending_window_reducer',
                                     wraps=pending_window_dominance.make_pending_window_reducer) as reducer:
                    result = domain.run_arm(arm, seed, output, search_seconds=15)
                    engine.assert_called_once()
                    reducer.assert_called_once()
                    self.assertIs(type(reducer.call_args.kwargs['runtime']), RemainingChargeRuntimeV1)
                    for flag in ('enabled', 'post_service_enabled', 'completed_departure_layers'):
                        self.assertIs(reducer.call_args.kwargs[flag], True)
                    self.assertIn('singleton_bound' if arm == 'flat' else 'bound_provider', engine.call_args.kwargs)
                fresh = tiny_domain(root / ('fresh-' + arm), arm, required_hmax=seed.max_depth)
                replayed = fresh.recover_durable(seed, output / 'incumbent.json')
                with fresh.context('verification') as context:
                    self.assertEqual(context.router.mode, 'full')
                self.assertEqual(result['status'], 'attained_optimum')
                self.assertEqual(result['Hmax'], seed.max_depth)
                self.assertEqual(result['seed_key'], json.loads(seed.key_bytes))
                self.assertEqual(result['accepted_key'], replayed['accepted_key'])
                replayed.update(status=result['status'], search_status='SUCCESS')
                answers.append(gate.validate_terminal(result, replayed, arm, seed.max_depth))
                snapshot = json.loads((output / 'progress/progress.json').read_bytes())
                for field in ('pending_window_statistics', 'post_service_statistics', 'analytic_charge_statistics', 'completion_policy'):
                    self.assertEqual(snapshot[field], result[field])
                gate.validate_post_service_statistics(result['post_service_statistics'], arm, completed=True)
                gate.validate_pending_window_statistics(result['pending_window_statistics'], result['post_service_statistics'], arm, completed=True)
                gate.validate_combined_statistics(result['projection_support_statistics'], result['analytic_charge_statistics'], arm, completed=True)
                cohort.validate_singleton_statistics(result['singleton_bound_statistics'], arm, completed=True)
                self.assertIs(result['envelope_sweep_statistics']['enabled'], False)
                self.assertEqual(snapshot['Hmax'], seed.max_depth)
            self.assertEqual(seeds[0], seeds[1])
            self.assertEqual(answers[0], answers[1])


if __name__ == '__main__':
    unittest.main()
