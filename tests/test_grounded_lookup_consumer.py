import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch,Mock

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'comparison')]
import run_grounded_lookup_consumer as c


def budget():
    return dict(state='development_only',cap_CPU_s=600,original_cap_CPU_s=28800,
        carried_research_CPU_s='18229.782734743',allocations_CPU_s=dict(development=180,validation=60,optimization=180,close=30,reserve=150),
        fixed_precharge_CPU_s=10,fixed_precharge_phase='close',phase_charged_CPU_s=dict(development=42,validation=0,optimization=0,close=0,reserve=0),
        records=[],active=None,allowed_real_attempts=dict(optimization=1),
        real_query_gate='BLOCKED until passing tiny tests and independent review')


def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data))


def producer(root):
    src=dict(commit=c.PRODUCER,dirty=False)
    old=dict(source=src,pair_denominator=4225,site_denominator=64,actions=78,holdout=False,road_selection_certified=False)
    write(root/'admission.json',old);write(root/'config.json',{});write(root/'physics.json',{})
    write(root/'split-table/manifest.json',{})
    freeze=dict(source=src,mode='freeze',status='COMPLETE',admission_sha256=c.sha(root/'admission.json'))
    gen=dict(source=src,mode='generation',status='COMPLETE',completed_pairs=4225,table_sha256=c.sha(root/'split-table/manifest.json'))
    val=dict(source=src,mode='validation',status='COMPLETE',table_sha256=gen['table_sha256'],physics_sha256=c.sha(root/'physics.json'),derived_complete_H=20,upper_replay=dict(key=['1','0',1,[]]))
    records=[]
    for name,row in [('freeze',freeze),('generation',gen),('validation',val)]:
        write(root/(name+'.result.json'),row)
        records.append(dict(phase=name,actual_child_returncode=0,guard_reason=None,terminal_sha256=c.sha(root/(name+'.result.json'))))
    write(root/'budget.json',dict(records=records))
    pins={name:c.sha(root/name) for name in c.PINNED}
    return old,val,pins


class ConsumerTests(unittest.TestCase):
    def test_pinned_producer_chain_and_every_identity_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);old,val,pins=producer(root)
            with patch.object(c,'PINNED',pins):
                self.assertEqual(c.producer_chain(root),(old,val))
                for name in pins:
                    raw=(root/name).read_bytes();(root/name).write_bytes(raw+b' ')
                    with self.subTest(name=name),self.assertRaisesRegex(ValueError,'producer identity changed'):c.producer_chain(root)
                    (root/name).write_bytes(raw)

    def test_receipt_controller_binding_is_required_even_with_matching_file_hashes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);_,_,pins=producer(root)
            b=c.load(root/'budget.json');b['records'][1]['guard_reason']='wall_guard';write(root/'budget.json',b)
            pins['budget.json']=c.sha(root/'budget.json')
            with patch.object(c,'PINNED',pins),self.assertRaisesRegex(ValueError,'controller terminal'):c.producer_chain(root)

    def test_changed_consumer_source_or_environment_rejected(self):
        ad=dict(consumer_source=dict(commit='reviewed',dirty=False),consumer_environment={'v':1})
        for src,env in [(dict(commit='new',dirty=False),{'v':1}),(dict(commit='reviewed',dirty=True),{'v':1}),(ad['consumer_source'],{'v':2})]:
            with patch.object(c,'source',return_value=src),patch.object(c,'environment',return_value=env),self.assertRaises(ValueError):c.verify_identity(ad)

    def test_budget_exhaustion_prior_attempt_and_pending_work_rejected(self):
        c.validate_budget(budget())
        for mode in ('exhausted','attempt','active','global','closed','gate'):
            b=budget()
            if mode=='exhausted':b['phase_charged_CPU_s']['development']=500
            if mode=='attempt':b['records']=[dict(phase='optimization')]
            if mode=='active':b['active']={'pid':1}
            if mode=='global':b['carried_research_CPU_s']='28700'
            if mode=='closed':b['state']='closed'
            if mode=='gate':b['real_query_gate']='unreviewed'
            with self.subTest(mode=mode),self.assertRaises(ValueError):c.validate_budget(b)

    def test_preparation_forks_charges_once_and_preserves_producer(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'producer';p.mkdir();old,val,pins=producer(p)
            ledger=root/'stage/budget.json';write(ledger,budget());original=ledger.read_bytes();out=root/'consumer'
            src=dict(commit='reviewed',dirty=False)
            with patch.object(c,'PINNED',pins),patch.object(c,'source',return_value=src),patch.object(c,'environment',return_value={'v':1}):
                ad=c.prepare(p,ledger,out,'reviewed')
                self.assertEqual((out/'parent-budget.json').read_bytes(),original)
                self.assertEqual(c.load(out/'budget.json')['phase_charged_CPU_s'],budget()['phase_charged_CPU_s'])
                self.assertEqual(c.load(ledger)['state'],'closed_delegated_to_consumer')
                self.assertEqual(c.producer_chain(p),(old,val))
                with self.assertRaises(ValueError):c.prepare(p,ledger,out,'reviewed')
                with self.assertRaises(ValueError):c.prepare(p,ledger,root/'second','reviewed')
                self.assertEqual(ad['consumer_source'],src)

    def test_controller_identity_inherited_charges_and_threads(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);p=root/'producer';p.mkdir();_,_,pins=producer(p)
            ledger=root/'stage/budget.json';write(ledger,budget());out=root/'consumer'
            src=dict(commit='reviewed',dirty=False)
            with patch.object(c,'PINNED',pins),patch.object(c,'source',return_value=src),patch.object(c,'environment',return_value={'v':1}):
                ad=c.prepare(p,ledger,out,'reviewed')
            d=c.load(out/'budget.json')
            d['active']=dict(phase='optimization',child_CPU_limit=120,wall_limit=120,reserved_CPU_s=180,
                pid=os.getpid(),controller_pid=os.getppid(),controller_sha256=c.sha(ROOT/'tools/shared_pilot_budget.py'))
            write(out/'budget.json',d)
            with patch.dict(os.environ,{key:'1' for key in c.THREAD_VARS}):
                self.assertEqual(c.verify_controller(out,ad),d)
                for mode in ('pid','parent_pid','controller_hash','charges','cpu','wall','reserve','missing_active','threads'):
                    altered=copy.deepcopy(d)
                    if mode=='pid':altered['active']['pid']+=1
                    if mode=='parent_pid':altered['active']['controller_pid']+=1
                    if mode=='controller_hash':altered['active']['controller_sha256']='changed'
                    if mode=='charges':altered['phase_charged_CPU_s']['development']=0
                    if mode=='cpu':altered['active']['child_CPU_limit']=121
                    if mode=='wall':altered['active']['wall_limit']=121
                    if mode=='reserve':altered['active']['reserved_CPU_s']=181
                    if mode=='missing_active':altered['active']=None
                    write(out/'budget.json',altered)
                    with patch.dict(os.environ,{'OMP_NUM_THREADS':'2' if mode=='threads' else '1'}):
                        with self.subTest(mode=mode),self.assertRaises(ValueError):c.verify_controller(out,ad)
                write(out/'budget.json',d)
                original=ledger.read_bytes();ledger.write_bytes(original+b' ')
                with self.assertRaisesRegex(ValueError,'delegated parent changed'):c.verify_controller(out,ad)

    def test_bare_execution_rejected_and_attempt_marker_never_reused(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)
            self.assertEqual(c.run(out),75)
            self.assertTrue((out/'optimization.started.json').exists())
            with self.assertRaises(FileExistsError):c.run(out)

    def test_deadline_prevents_phase_entry_and_records_interruption(self):
        with tempfile.TemporaryDirectory() as d:
            clock=c.Clock(Path(d))
            with patch.object(c.time,'monotonic',return_value=clock.start+120),self.assertRaises(TimeoutError):clock.remaining()
            with self.assertRaises(TimeoutError):
                with clock.phase('load'):
                    clock.start-=121
            self.assertEqual(clock.phases[-1]['status'],'interrupted')

    def test_loader_rejects_changed_header_dimensions_physics_and_depth(self):
        old=dict(source={'commit':'old'},config_sha256='cfg',graph_sha256='graph',candidate_domain_sha256='domain',header={'h':1},model={},schedule_recipe={},upper_witness={})
        provenance={k:old[k] for k in ('source','config_sha256','graph_sha256','candidate_domain_sha256')}
        for mode in ('header','dimensions','physics','depth','table'):
            store=SimpleNamespace(manifest={'provenance':provenance},numeric={'h':1,'pairs':[]})
            table=SimpleNamespace(_path_store=store,candidate_order=list(range(64)),actions=list(range(78)),pairs=list(range(4225)),sources=list(range(65)),targets=list(range(65)),payload_sha256='table')
            if mode=='header':store.numeric['h']=2
            if mode=='dimensions':table.actions.pop()
            if mode=='table':table.payload_sha256='changed'
            with patch('split_leg_table.read',return_value=table) as reader,patch('split_leg_table.close') as close,patch.object(c,'physical',return_value={'p':1}),patch.object(c,'load',return_value={'p':2} if mode=='physics' else {'p':1}),patch('exact_physical_adapter.table_relevant_depth',return_value=(19,{'key':[]})):
                with self.subTest(mode=mode),self.assertRaises(ValueError):c.load_verified_table(Path('/unused'),old,{'table_sha256':'table','upper_replay':{'key':[]}},lambda:None)
                reader.assert_called_once();close.assert_called_once_with(table)

    def test_environment_fingerprint_contains_real_runtime_identity(self):
        value=c.environment()
        self.assertEqual(value['z3'],'4.13.4')
        for key in ('executable_sha256','z3_module_sha256','z3_library_sha256'):self.assertEqual(len(value[key]),64)
