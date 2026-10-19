import copy
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from experiments.m6h_manifest_v1 import continuation as c
from experiments.m6h_manifest_v1.contract import canonical

class ReceiptContinuationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.parent=dict(schema='hiroute.m6h.disclosed_waited_round.v1',status='FAILED',cleanup_verified=True,
            accounting='authoritative_outer_self_plus_waited_children_once_no_nested_sum',
            protocol=dict(cpu_limit_seconds=144000,absolute_deadline_utc=c.DEADLINE),
            cumulative_measured_plus_conservative_carry=dict(cpu_seconds=1250.25,wall_seconds=20))
        self.owner=dict(schema='hiroute.mechanism_recovery.supervisor.v1',status='FAILED',complete=True,
            cleanup_verified=True,reason='sampled_tree_rss_limit',accounted_owned_cpu_seconds=30)
        self.a=dict(schema=c.SCHEMA,parent_waited_receipt=self.write('waited_round_receipt.json',self.parent),
            parent_owner_receipt=self.write('owner/receipt.json',self.owner),
            parent_graph_progress=self.write('owner/artifacts/round/preprocessing/graph/artifacts/graph_progress.json',
                dict(schema='hiroute.graph_progress.v1',stage='parser_started')),
            active_since_utc='2026-10-19T12:00:00Z',cpu_capacity=9,observed_numerical_slots=0,
            od_selection_started=False,failure_scope='preselection_graph_infrastructure')
    def tearDown(self):self.temp.cleanup()
    def write(self,name,value):
        p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);raw=canonical(value);p.write_bytes(raw)
        return dict(path=str(p),sha256=hashlib.sha256(raw).hexdigest())
    def verify(self,a=None):
        b=self.write('admission.json',a or self.a)
        return c.verify(b,expected_admission_sha256=b['sha256'])
    def test_exact_parent_cumulative_not_nested_sum_or_initial_epoch(self):
        lineage=self.verify();self.assertEqual(lineage['carried_cpu_seconds'],1250.25)
        self.assertEqual(c.debit_at(lineage,'2026-10-19T12:01:00Z'),1790.25)
        with patch.object(c,'ContinuationBudget') as b:
            c.budget(lineage,transition_utc='2026-10-19T12:01:00Z')
        self.assertEqual(b.call_args.kwargs['carried_cpu_seconds'],1790.25)
        self.assertEqual(b.call_args.kwargs['deadline_utc'],c.DEADLINE)
    def test_missing_root_pin_before_io(self):
        with patch.object(Path,'read_bytes',side_effect=AssertionError('read')):
            with self.assertRaises(PermissionError):c.verify({},expected_admission_sha256=None)
    def test_forged_or_mutated_parent_rejected(self):
        Path(self.a['parent_waited_receipt']['path']).write_bytes(b'{}')
        with self.assertRaises(ValueError):self.verify()
    def test_cleanup_cap_deadline_status_and_total_fail_closed(self):
        for field,value in [('cleanup_verified',False),('status','SUCCESS'),
                            ('protocol',dict(cpu_limit_seconds=144001,absolute_deadline_utc=c.DEADLINE)),
                            ('protocol',dict(cpu_limit_seconds=144000,absolute_deadline_utc='2027-01-01T00:00:00Z')),
                            ('cumulative_measured_plus_conservative_carry',dict(cpu_seconds=-1))]:
            with self.subTest(field=field,value=value):
                p=copy.deepcopy(self.parent);p[field]=value;a=copy.deepcopy(self.a)
                a['parent_waited_receipt']=self.write('waited_round_receipt.json',p)
                with self.assertRaises(ValueError):self.verify(a)
    def test_numeric_or_selection_attempt_cannot_restart(self):
        for field,value in [('observed_numerical_slots',1),('observed_numerical_slots',False),
                            ('od_selection_started',True),('cpu_capacity',8),('carried_cpu_seconds',0)]:
            a=copy.deepcopy(self.a);a[field]=value
            with self.subTest(field=field):
                with self.assertRaises(ValueError):self.verify(a)
        p=self.root/'owner/artifacts/round/generation';p.mkdir()
        with self.assertRaises(ValueError):self.verify()
    def test_wrong_owner_and_incomplete_cleanup_rejected(self):
        a=copy.deepcopy(self.a);a['parent_owner_receipt']=self.write('another/receipt.json',self.owner)
        with self.assertRaises(ValueError):self.verify(a)
        owner=dict(self.owner,cleanup_verified=False)
        a['parent_owner_receipt']=self.write('owner/receipt.json',owner)
        with self.assertRaises(ValueError):self.verify(a)

if __name__=='__main__':unittest.main()
