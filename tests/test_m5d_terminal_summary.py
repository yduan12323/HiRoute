import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import hashlib
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('summary', ROOT / 'scripts/summarize_m5d_terminal_state.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class TerminalSummaryTests(unittest.TestCase):
    def setUp(self):
        self.m, self.mh = module.load(ROOT / 'results/milestone_5d/terminal_state_audit_20261014/inputs/frozen_main_phase_v3_20261011.json')
        self.s, _, _ = module.load_projection(ROOT / 'results/milestone_5d/terminal_state_audit_20261014/inputs/main_state.public.json', 'main')
        self.p, _, _ = module.load_projection(ROOT / 'results/milestone_5d/terminal_state_audit_20261014/inputs/parallel_state.public.json', 'parallel')

    def run_summary(self):
        return module.summarize(self.m, self.s, self.p, self.mh)

    def test_projection_generator_is_deterministic_and_strips_tokens(self):
        raw = copy.deepcopy(self.p)
        raw['completed'][raw['launch_order'][0]]['claim_token'] = 'PRIVATE_TEST_TOKEN'
        raw['host_path'] = '/home/private/test'
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'raw.json';path.write_text(json.dumps(raw))
            outputs=[]
            for n in (1,2):
                out=Path(d)/('public'+str(n)+'.json')
                subprocess.run([sys.executable, str(ROOT/'scripts/project_m5d_state.py'),
                                '--raw-input', str(path), '--kind', 'parallel', '--output', str(out)],check=True)
                payload, _, source_hash = module.load_projection(out,'parallel')
                self.assertEqual(source_hash,hashlib.sha256(path.read_bytes()).hexdigest())
                self.assertEqual(payload,self.p)
                outputs.append(out.read_bytes())
            self.assertEqual(*outputs)
            self.assertNotIn(b'PRIVATE_TEST_TOKEN',outputs[0])
            self.assertNotIn(b'/home/private',outputs[0])

    def test_projection_payload_tamper_rejected(self):
        wrapper = json.loads((ROOT / 'results/milestone_5d/terminal_state_audit_20261014/inputs/main_state.public.json').read_text())
        wrapper['payload']['charged_cpu_ns'] += 1
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'bad.json'; path.write_text(json.dumps(wrapper))
            with self.assertRaisesRegex(module.EvidenceError, 'payload hash'):
                module.load_projection(path, 'main')

    def test_projection_kind_rejected(self):
        with self.assertRaisesRegex(module.EvidenceError, 'projection kind'):
            module.load_projection(ROOT / 'results/milestone_5d/terminal_state_audit_20261014/inputs/main_state.public.json', 'parallel')

    def test_raw_state_not_accepted_as_projection(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'raw.json';path.write_text(json.dumps(self.s))
            with self.assertRaisesRegex(module.EvidenceError,'projection schema'):
                module.load_projection(path,'main')

    def test_public_projection_has_no_private_scheduler_fields(self):
        for name in ('main_state.public.json','parallel_state.public.json'):
            text=(ROOT / 'results/milestone_5d/terminal_state_audit_20261014/inputs'/name).read_text()
            for prohibited in ('claim_token','receipt_path','/home/','control_group','memory_current_path'):
                self.assertNotIn(prohibited,text)

    def test_terminal_counts_and_denominator(self):
        r, rows = self.run_summary()
        self.assertEqual((r['denominator'], len(rows), r['exact_rows']), (192,192,0))
        self.assertEqual(r['status_counts'], {'time_limit':148,'incumbent_search_failed':44})
        self.assertFalse(r['acceptance']['m5d_complete'])

    def test_phase_unknown_preserved(self):
        r,_ = self.run_summary()
        self.assertEqual(r['observed_phase_counts'], {'unknown':93,'seed_started':73,'seed_failed':26})

    def test_no_success_pair_means_na_not_one(self):
        r,_ = self.run_summary()
        self.assertEqual(r['paired_bindings'],96)
        self.assertEqual(r['paired_exact_bindings'],0)
        self.assertIsNone(r['paired_end_to_end_speedup'])
        self.assertEqual(r['paired_speedup_display'],'NA')

    def test_missing_measurements_stay_null(self):
        _, rows = self.run_summary()
        self.assertIsNone(rows[0]['wall_elapsed_ns'])
        self.assertIsNone(rows[0]['cgroup_memory_peak_bytes'])
        self.assertGreater(rows[93]['wall_elapsed_ns'], 0)
        self.assertGreater(rows[93]['cgroup_memory_peak_bytes'], 0)

    def test_cpu_not_double_counted(self):
        r,_ = self.run_summary()
        c = r['cpu_accounting']
        self.assertEqual(c['row_cgroup_ns'],99559649486000)
        self.assertEqual(c['serial_row_cgroup_ns'],48608328801000)
        self.assertEqual(c['parallel_row_cgroup_ns'],50951320685000)
        self.assertEqual(c['parallel_host_cumulative_ns'],4265765481000)
        self.assertEqual(c['main_rows_plus_parallel_host_known_subtotal_ns'],103825414967000)
        self.assertFalse(c['original_48_cpu_hour_ledger_complete'])

    def test_missing_row_rejected(self):
        del self.s['rows'][next(iter(self.s['rows']))]
        with self.assertRaisesRegex(module.EvidenceError,'row IDs'): self.run_summary()

    def test_duplicate_manifest_id_rejected(self):
        self.m['rows'][1] = self.m['rows'][0]
        with self.assertRaisesRegex(module.EvidenceError,'duplicate'): self.run_summary()

    def test_duplicate_json_id_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bad.json';p.write_text('{"row": 1, "row": 2}')
            with self.assertRaisesRegex(module.EvidenceError,'duplicate'): module.load(p)

    def test_duplicate_launch_rejected(self):
        self.p['launch_order'][1]=self.p['launch_order'][0]
        with self.assertRaisesRegex(module.EvidenceError,'launch'): self.run_summary()

    def test_foreign_manifest_rejected(self):
        self.s['phase_sha256']='wrong'
        with self.assertRaisesRegex(module.EvidenceError,'binding'): self.run_summary()

    def test_nonterminal_rejected(self):
        self.p['inflight']={'still_running':{}}
        with self.assertRaisesRegex(module.EvidenceError,'unfinished'): self.run_summary()

    def test_cpu_mismatch_rejected(self):
        self.s['charged_cpu_ns']+=1
        with self.assertRaisesRegex(module.EvidenceError,'CPU'): self.run_summary()

    def test_denominator_exclusion_rejected(self):
        self.s['rows'][next(iter(self.s['rows']))]['denominator_included']=False
        with self.assertRaisesRegex(module.EvidenceError,'denominator'): self.run_summary()

    def test_exact_claim_needs_separate_audit(self):
        self.s['rows'][next(iter(self.s['rows']))]['status']='exact'
        with self.assertRaisesRegex(module.EvidenceError,'proof-aware'): self.run_summary()

    def test_state_disagreement_rejected(self):
        rid=self.p['launch_order'][0]
        self.p['completed'][rid]['row_result']['wall_elapsed_ns']+=1
        with self.assertRaisesRegex(module.EvidenceError,'disagree'): self.run_summary()

    def test_host_snapshot_above_total_rejected(self):
        row=self.s['rows'][self.m['rows'][0]['row_id']]
        row['batch_and_waited_child_cpu_ns']=self.p['host_cpu_ns']+1
        with self.assertRaisesRegex(module.EvidenceError,'host total'): self.run_summary()

    def test_boolean_cpu_rejected(self):
        self.s['rows'][self.m['rows'][0]['row_id']]['cgroup_cpu_usage_ns']=True
        with self.assertRaisesRegex(module.EvidenceError,'integer'): self.run_summary()

if __name__=='__main__': unittest.main()
