"""Small variant/population boundary tests; no real capture or numerical work."""
from copy import deepcopy
import unittest

from experiments.time_cut_v2.recorded_real import plan, replay_plan, variant_scope as scope


class VariantScopeTests(unittest.TestCase):
    def physical(self, d0=False):
        value = dict(schema=scope.D0_PLAN_SCHEMA if d0 else scope.D1_PLAN_SCHEMA,
            state_id='C01', pool_id='OD00_energy_only', H_ref=4, sites=8, regions=2047,
            dominance=not d0, representation=scope.REPRESENTATION, external_incumbent=None)
        if d0:
            value['variant_id'] = scope.D0
        return value

    def test_v1_is_unchanged_d1_and_v2_is_explicit_d0(self):
        self.assertFalse(scope.physical_scope(self.physical()))
        self.assertTrue(scope.physical_scope(self.physical(True)))

    def test_boolean_aliases_and_implicit_or_foreign_d0_reject(self):
        for d0 in (False, True):
            for field, value in [('dominance', 0), ('dominance', 1), ('dominance', 'off'),
                                 ('dominance', None), ('representation', 'other'), ('external_incumbent', [])]:
                bad = self.physical(d0); bad[field] = value
                with self.subTest(d0=d0, field=field, value=value), self.assertRaises(ValueError):
                    scope.validate_variant(bad)
        for change in ({'dominance': False}, {'variant_id': scope.D0}):
            bad = self.physical(); bad.update(change)
            with self.assertRaises(ValueError): scope.validate_variant(bad)
        for field, value in [('variant_id', 'C02::HIER::D-off'), ('state_id', 'C02'),
                             ('dominance', True), ('schema', 'unknown')]:
            bad = self.physical(True); bad[field] = value
            with self.assertRaises(ValueError): scope.validate_variant(bad)

    def test_physical_scope_cannot_change_original_shape_or_integer_types(self):
        for field, value in [('H_ref', True), ('sites', 8.0), ('regions', 2047.0),
                             ('H_ref', 3), ('sites', 7), ('regions', 2046), ('pool_id', 'OD01_energy_only')]:
            bad = self.physical(True); bad[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): scope.physical_scope(bad)

    def test_source_renewal_cannot_turn_d1_into_d0_even_with_new_hash(self):
        old = self.physical(); old.update(source_commit='a'*40, source_files={}, source_sha256='b'*64)
        new = self.physical(True); new.update(source_commit='c'*40, source_files={}, source_sha256='d'*64)
        with self.assertRaisesRegex(ValueError, 'capture scope'):
            replay_plan.same_capture_scope(old, new)

    def test_legacy_commitment_bytes_stay_identical(self):
        old = dict(completed_replay={}, unique_logical_models=9)
        raw = plan.canonical(old)
        self.assertEqual(plan.canonical(scope.with_variant(old, {})), raw)
        self.assertFalse(scope.is_d0_population(old))

    def frozen(self):
        catalogue = dict(block_size=256, total_models=513, blocks=[0, 1, 2])
        anchors = dict(variant_id=scope.D0, dominance=False, representation=scope.REPRESENTATION)
        value = dict(completed_replay=anchors, block_plan_sha256=plan.digest(catalogue),
            unique_logical_models=513, queries=17, original_model_occurrences=1027, empty_action_queries=5)
        return catalogue, scope.with_variant(value, anchors)

    def test_d0_counts_have_their_own_independent_freeze(self):
        catalogue, value = self.frozen()
        self.assertTrue(scope.population_scope(catalogue, value))
        self.assertEqual(value['queries']+value['empty_action_queries'], 22)

    def test_changed_freeze_alias_count_and_catalogue_reject(self):
        catalogue, value = self.frozen()
        for field, changed in [('unique_logical_models', 514), ('queries', 18),
                               ('dominance', 0), ('variant_id', 'C01::HIER::D-on')]:
            bad = deepcopy(value); bad[field] = changed
            with self.subTest(field=field), self.assertRaises(ValueError): scope.population_scope(catalogue, bad)
        for alias in (True, 17.0):
            bad = deepcopy(value); bad['queries'] = alias
            bad['population_freeze_sha256'] = plan.digest({k:v for k,v in bad.items() if k!='population_freeze_sha256'})
            with self.assertRaises(ValueError): scope.population_scope(catalogue, bad)
        bad_catalogue = deepcopy(catalogue); bad_catalogue['blocks'].append(3)
        with self.assertRaises(ValueError): scope.population_scope(bad_catalogue, value)

    def test_partial_variant_or_changed_replay_anchor_reject(self):
        _, value = self.frozen()
        for field in ('variant_id', 'population_freeze_sha256'):
            bad = deepcopy(value); bad.pop(field)
            with self.assertRaises(ValueError): scope.is_d0_population(bad)
        bad = deepcopy(value); bad['completed_replay']['dominance'] = True
        bad['population_freeze_sha256'] = plan.digest({k:v for k,v in bad.items() if k!='population_freeze_sha256'})
        with self.assertRaises(ValueError): scope.is_d0_population(bad)


if __name__ == '__main__':
    unittest.main()
