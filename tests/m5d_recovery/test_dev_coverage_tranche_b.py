"""Reviewed B admission and linked-gate accounting; metadata and mocks only."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from experiments.dev_coverage_tranche_v1 import run as gate, batch, bindings
from experiments.mechanism_recovery_v1 import run as base


class TrancheBReleaseTests(unittest.TestCase):
    def test_exact_queue_excludes_existing_gate_and_all_A_domains(self):
        self.assertEqual(bindings.QUEUE, (
            ('OD08_energy_and_scheduled_soc19_25', 32),
            ('OD09_energy_and_scheduled_soc19_25', 32),
            ('OD06_energy_and_scheduled_soc3_10', 32),
            ('OD07_energy_and_scheduled_soc3_10', 32),
            ('OD08_energy_and_scheduled_soc19_25', 128),
            ('OD09_energy_and_scheduled_soc19_25', 128),
            ('OD07_energy_and_scheduled_soc3_10', 128)))
        for case, n in [bindings.LINKED_GATE_DOMAIN] + [(c, n) for c in bindings.A_CASES for n in (32, 128)]:
            with self.assertRaises(ValueError):
                gate.prospective(case, n)
        plan = batch.prospective()
        self.assertEqual(plan['denominator'], dict(domains=7, method_rows=14,
            common_preparations=7, searches=14, replays=14, operational_slots=35))
        self.assertEqual(plan['full_queue_conservative_CPU_charge_reservation_seconds'], 31680)
        self.assertEqual(plan['combined_A_B_conservative_reservation_seconds'], 67680)
        self.assertLessEqual(plan['combined_A_B_conservative_reservation_seconds'],
                             plan['aggregate_conservative_CPU_charge_ceiling_seconds'])
        link = plan['linked_existing_gate']
        self.assertEqual((link['case_id'], link['candidate_count']), bindings.LINKED_GATE_DOMAIN)
        self.assertEqual((link['expected_hmax'], link['method_rows'], link['operational_slots']), (39, 2, 5))
        self.assertIs(link['rerun'], False)
        self.assertIs(link['included_in_new_denominator'], False)
        self.assertEqual(batch.batch_ledger('f'*64)['linked_existing_gate'], link)

    def test_release_defaults_and_pending_or_old_A_review_cannot_freeze_or_load_B(self):
        self.assertEqual(gate.REVIEW_STATUS, 'approved_independent_dev_coverage_tranche_B_review')
        self.assertEqual(gate.CURRENT_PAIR_STATUS, 'root_tranche_A_terminal_reviewed')
        gate.require_launch_review()
        states = [('pending_independent_dev_coverage_tranche_B_review', 'pending_root_tranche_A_terminal_review'),
            ('pending_independent_dev_coverage_tranche_B_review', gate.CURRENT_PAIR_STATUS),
            (gate.REVIEW_STATUS, 'pending_root_tranche_A_terminal_review'),
            ('approved_independent_dev_coverage_tranche_review', 'root_current_pair_outcome_reviewed'),
            ('approved_independent_dev_coverage_tranche_B_review', 'root_current_pair_outcome_reviewed')]
        for review, current in states:
            with self.subTest(review=review), tempfile.TemporaryDirectory() as temp, \
                    patch.object(gate, 'REVIEW_STATUS', review), patch.object(gate, 'CURRENT_PAIR_STATUS', current), \
                    patch.object(gate, 'source_identity') as source, patch.object(base, 'load_graph') as graph:
                output = Path(temp)/'freeze'
                with self.assertRaises(ValueError):
                    batch.freeze(output, temp)
                self.assertFalse(output.exists())
                forged = copy.deepcopy(batch.prospective())
                forged.update(launchable=True, status='frozen_tranche_B_not_launched')
                manifest = Path(temp)/'batch.json'
                manifest.write_bytes(base.canonical(forged))
                with self.assertRaises(ValueError):
                    batch._manifest(manifest, base.file_hash(manifest))
                source.assert_not_called()
                graph.assert_not_called()
