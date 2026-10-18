"""Finite installed-wheel energy tests; all graphs are tiny synthetic arrays."""
import ctypes
from dataclasses import replace
from fractions import Fraction as F
import hashlib
from importlib import resources
import json
import os
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
from microplan.native_artifact import build_artifact as build_router
from timecut5.routing_config import RoutingConfig,TerminalEnergyConfig
from timecut5.terminal_energy_artifact import build_artifact as build_energy
from timecut5 import terminal_energy as energy
from timecut5 import energy_observation as observation
from timecut5.real_adapter import site_catalog_digest
from timecut5.real_legs import RealSite
from timecut5.bounded import _solve_problem
from timecut5.hierarchy import _solve_hierarchical_problem,build_regions
from timecut5.probe import Interval

HERE=Path(__file__).resolve().parent


def graph(n,rows):
    arrays=[np.ascontiguousarray([r[i] for r in rows],dtype=np.int64 if i<2 else np.float64) for i in range(4)]
    for array in arrays:array.flags.writeable=False
    return SimpleNamespace(node_count=n,edge_count=len(rows),source=arrays[0],target=arrays[1],
        weights=dict(travel_time=arrays[2],distance=arrays[3]))


def digest(value):return hashlib.sha256(energy.canonical(value)).hexdigest()


def limits():resource.setrlimit(resource.RLIMIT_CPU,(15,18))


class EnergyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name)
        cls.compiler=str(Path(shutil.which('g++')).resolve())
        cls.config=dict(compiler=cls.compiler,compiler_flags=['-O3','-std=c++17'])
        cls.router_artifact=build_router(cls.config,cls.root/'build')
        cls.energy_artifact=build_energy(dict(compiler=cls.compiler,
            compiler_flags=['-O3','-std=c++17','-fno-fast-math','-frounding-math']),cls.root/'build')
        helper=cls.root/'flags.so'
        subprocess.run([cls.compiler,'-O2','-shared','-fPIC',str(HERE/'floating_flags.cpp'),'-o',str(helper)],
            check=True,timeout=30,preexec_fn=limits)
        cls.flags=ctypes.CDLL(str(helper));cls.count=0
        if os.environ.get('ENERGY_EVIDENCE'):
            evidence_root=Path(os.environ['ENERGY_EVIDENCE']).with_suffix('')
            evidence_root.mkdir(exist_ok=True)
            for name,artifact in (('router',cls.router_artifact),('energy',cls.energy_artifact)):
                shutil.copy2(artifact.binary_path,evidence_root/(name+'.so'))
            Path(os.environ['ENERGY_EVIDENCE']).write_bytes(energy.canonical(dict(python=sys.version,
                supported=sys.version_info[:2]==(3,11),module=energy.__file__,router=cls.router_artifact.receipt,
                energy=cls.energy_artifact.receipt,real_graph=False)))

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def directory(self):
        type(self).count+=1;return self.root/str(self.count)

    def context(self,*,enabled=True,role='search',g=None,anchors=None,obs=None,unsupported='reject'):
        g=g or graph(4,[(a,b,abs(a-b),abs(a-b)) for a in range(4) for b in range(4) if a!=b])
        anchors=anchors or dict(A=0,B=1,D=3,X=2)
        c=RoutingConfig(terminal_energy=TerminalEnergyConfig(unsupported=unsupported) if enabled else None).create_context(
            g,self.config,self.directory(),role=role,artifact=self.router_artifact,
            energy_artifact=self.energy_artifact if enabled else None,observation=obs,
            anchor_nodes=anchors,nodes_sha256=digest(g.node_count),edges_sha256=digest('synthetic edges'),
            anchor_catalog_sha256=digest(anchors),source_cache_max_bytes=1000000)
        self.addCleanup(c.close);return c

    def problem(self,c,**changes):
        q=dict(origin='A',destination='D',H_ref=1,start_time_s=0,initial_energy_kwh=2,
            capacity_kwh=20,minimum_energy_kwh=0,reserve_kwh=1,consumption_kwh_per_m=1,
            overhead_s=2,lambda_stop_s=1,charging_segments=[[0,20,1,0]],schedule=None)
        q.update(changes)
        sites=dict(s=RealSite('s','B',('C',)),t=RealSite('t','X',('C',)))
        return c.problem(q,sites,origin_anchor='A',destination_anchor='D',site_catalog_sha256=site_catalog_digest(sites))

    def observer(self,**kwargs):
        return observation.EnergyObservation(self.directory(),run_identity={'run':'tiny','domain':digest('tiny')},interval=.01,**kwargs)

    def test_installed_resource_and_same_build_defaults(self):
        # CI explicitly requires installed-wheel origin; ordinary pytest uses src.
        expected = (Path(sys.prefix) if os.environ.get('HIROUTE_REQUIRE_INSTALLED_WHEEL') == '1'
                    else Path(__file__).resolve().parents[2] / 'src')
        self.assertTrue(Path(energy.__file__).resolve().is_relative_to(expected.resolve()))
        raw=resources.files('timecut5').joinpath('terminal_energy_native.cpp').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),self.energy_artifact.receipt['source_sha256'])
        self.assertIsNone(RoutingConfig().terminal_energy)
        self.assertEqual(TerminalEnergyConfig().quantum_exponent,20)
        combined=RoutingConfig('destination_target',TerminalEnergyConfig())
        self.assertEqual(combined.effective_mode('search'),'destination_target')
        self.assertEqual(combined.effective_mode('verification'),'full')
        self.assertEqual(RoutingConfig().search_mode,'full')
        a,b=self.context(enabled=False),self.context()
        self.assertEqual(a.router.artifact['artifact_identity_sha256'],b.router.artifact['artifact_identity_sha256'])
        self.assertEqual(a.provider.leg('A','D'),b.provider.leg('A','D'))
        self.assertEqual(a.provider.edge_witnesses,b.provider.edge_witnesses)
        self.assertIsNone(self.problem(a)._terminal_energy_screen)

    def test_both_solvers_parity_future_charge_and_fresh_replay(self):
        from timecut5.durable_incumbent import _independent_replay
        from timecut5.exact_progress import ExactSearchProgress
        for method in ('flat','hier'):
            results=[]
            for enabled in (False,True):
                c=self.context(enabled=enabled);p=self.problem(c);calls=[];original=p.advance
                def record(pieces,site,effect):
                    calls.append((pieces[0].state.anchor,site,effect));return original(pieces,site,effect)
                p.advance=record
                obs=ExactSearchProgress(self.directory(),query_sha256=digest(p.case),domain_sha256=digest('tiny'),
                    source_sha256={'test':digest('source')},provider=c.provider,interval=.01)
                r=(_solve_problem(p,progress_hook=obs) if method=='flat' else
                    _solve_hierarchical_problem(p,True,build_regions(p.sites),progress_hook=obs))
                result=r.result if method=='flat' else r.bounded.result
                self.assertIsNotNone(result.witness);self.assertTrue(result.witness.pi)
                v=self.context(enabled=enabled,role='durable_verification');vp=self.problem(v)
                class Throwing:
                    def reject(self,*args):raise AssertionError('Verifier called screen')
                vp._terminal_energy_screen=Throwing()
                self.assertEqual(_independent_replay(lambda:vp,result.witness),result.key)
                self.assertEqual(c.provider.source_sha256,v.provider.source_sha256)
                self.assertFalse(hasattr(v.provider,'_terminal_energy_route_guard'))
                self.assertEqual(v.router.target_calls,0)
                results.append((result.key,result.witness.pi,calls))
            self.assertEqual(results[0],results[1])

    def test_endpoint_zero_unreachable_and_native_binary64_bound(self):
        c=self.context();p=self.problem(c);screen=p._terminal_energy_screen
        piece=p.initial_piece();threshold=p.reserve+screen._lower['A']
        self.assertFalse(screen.reject(p,(replace(piece,domain=Interval(threshold,threshold)),)))
        self.assertTrue(screen.reject(p,(replace(piece,domain=Interval(F(0),threshold,True,False)),)))
        for rows in ([(0,1,0.,0.),(1,2,0.,0.),(2,3,0.,0.)],
                     [(0,1,1.,2**53),(1,2,1.,1.5),(2,3,1.,1.5)],
                     [(0,1,1.,float.fromhex('0x0.0000000000001p-1022'))]):
            ctx=self.context(g=graph(4,rows));problem=self.problem(ctx)
            screen=problem._terminal_energy_screen
            for anchor in ctx.provider.anchor_nodes:
                leg=ctx.provider.leg(anchor,'D')
                if leg.reachable:self.assertLessEqual(screen._lower[anchor],leg.energy(problem.rate))
            self.assertEqual(screen.receipt['checked_edges'],len(rows))
            self.assertEqual(screen.receipt['full_edge_validation_passes'],2)
            self.assertEqual(screen.receipt['anchor_potentials']['D'],0)

    def test_zero_rate_and_constructor_failure_do_not_fake_activation(self):
        c=self.context();p=self.problem(c,consumption_kwh_per_m=0,reserve_kwh=0)
        self.assertTrue(all(v==0 for v in p._terminal_energy_screen._lower.values()))
        self.assertFalse(p._terminal_energy_screen.reject(p,(p.initial_piece(),)))
        with self.assertRaises(ValueError):self.context(g=graph(4,[(0,1,-1,1)]))
        with self.assertRaises(ValueError):self.context(g=graph(4,[(0,1,1,float('inf'))]))
        with self.assertRaises(ValueError):TerminalEnergyConfig(cap=0)

    def test_guard_before_seed_cache_and_anchor_poison_rejected(self):
        c=self.context();guard=c.provider._terminal_energy_route_guard
        c.provider.leg('A','B');self.assertGreater(guard.completed,0)
        old=c.provider.anchor_nodes['A'];c.provider.anchor_nodes['A']=2
        try:
            with self.assertRaises(ValueError):c.provider.leg('A','D')
        finally:c.provider.anchor_nodes['A']=old
        self.problem(c)
        old_round=self.flags.test_get_round()
        try:
            self.flags.test_set_round(self.flags.test_downward())
            with self.assertRaises(energy.UnsupportedEnvironment):c.provider.leg('A','D')
        finally:self.flags.test_set_round(old_round)
        self.assertNotIn(('A','D'),c.provider.legs)
        c.provider.leg('A','D')

    def test_owned_metadata_query_policy_and_native_replacement_reject(self):
        c=self.context();p=self.problem(c);piece=p.initial_piece();array=c.provider.graph.source
        dtype=array.dtype;array.dtype=np.uint64
        try:
            with self.assertRaises(ValueError):p.finish((piece,))
        finally:array.dtype=dtype
        c.provider.anchor_nodes['A']=2
        try:
            with self.assertRaises(ValueError):p.finish((piece,))
        finally:c.provider.anchor_nodes['A']=0
        p.reserve+=1
        with self.assertRaises(ValueError):p.finish((piece,))
        p.reserve-=1
        lib=c.router.lib;c.router.lib=object()
        try:
            with self.assertRaises(ValueError):p.finish((piece,))
        finally:c.router.lib=lib
        config=c.config;c.config=RoutingConfig()
        try:
            with self.assertRaises(ValueError):p.finish((piece,))
        finally:c.config=config
        policy=c.energy_policy;c.energy_policy={}
        try:
            with self.assertRaises(ValueError):self.problem(c)
        finally:c.energy_policy=policy

    def test_float_flags_zero_fallback_and_unguarded_cache_rejection(self):
        c=self.context(unsupported='zero');p=self.problem(c);screen=p._terminal_energy_screen
        csr=self.flags.test_get_mxcsr()
        try:
            self.flags.test_set_mxcsr(csr|(1<<15))
            self.assertFalse(screen.reject(p,(p.initial_piece(),)))
        finally:self.flags.test_set_mxcsr(csr)
        self.assertEqual(screen.status,'disabled_unsupported')
        self.assertFalse(screen._lower)
        strict=self.context();sp=self.problem(strict)
        csr=self.flags.test_get_mxcsr();control=self.flags.test_get_x87()
        try:
            for bit in (1<<6,1<<15):
                self.flags.test_set_mxcsr(csr|bit)
                with self.assertRaises(energy.UnsupportedEnvironment):sp.finish((sp.initial_piece(),))
                self.flags.test_set_mxcsr(csr)
            self.flags.test_set_x87(control & ~(1<<4))
            with self.assertRaises(energy.UnsupportedEnvironment):sp.finish((sp.initial_piece(),))
        finally:
            self.flags.test_set_x87(control);self.flags.test_set_mxcsr(csr)
        raw=self.context();raw.provider.leg('A','B');del raw.provider._terminal_energy_route_guard
        with self.assertRaises(ValueError):energy.RoutingHistoryGuard(raw.provider,raw._energy_kernel,'reject')

    def test_verifier_inactive_policy_and_artifact_tampering(self):
        for role in ('verification','recovery','durable_verification'):
            obs=self.observer();c=self.context(role=role,obs=obs);self.problem(c)
            self.assertIsNone(c._energy_kernel);self.assertIsNone(obs.certificate)
            c.close();pin=obs.complete(c)
            got=observation.read_status(pin['path'],expected_sha256=pin['sha256'],run_identity=json.loads(obs.binding),now_ns=time.monotonic_ns(),terminated=False)
            self.assertEqual(got['sample']['lifecycle'],'inactive')
            self.assertEqual(got['sample']['counters']['calls_started'],0)
        copied=self.directory();shutil.copytree(self.energy_artifact.directory,copied)
        bad=replace(self.energy_artifact,directory=copied);binary=bad.binary_path;binary.chmod(0o600)
        binary.write_bytes(binary.read_bytes()+b'bad')
        with self.assertRaises(ValueError):energy.policy_binding(TerminalEnergyConfig(),bad)
        with self.assertRaises(ValueError):energy.policy_binding(TerminalEnergyConfig(),SimpleNamespace(authenticate=lambda:{}))

    def test_activation_publication_failure_never_attaches(self):
        obs=self.observer();c=self.context(obs=obs);original=observation._publish
        def fail(path,*args,**kw):
            original(path,*args,**kw)
            if kw.get('immutable'):raise OSError('after certificate directory fsync')
        with patch.object(observation,'_publish',fail):
            with self.assertRaises(observation.ObservationError):self.problem(c)
        self.assertIsNotNone(obs.error)
        c.close()
        with self.assertRaises(observation.ObservationError):obs.complete(c)

    def test_callback_failure_latches_and_refuses_complete(self):
        noticed=threading.Event()
        def callback(error):noticed.set();raise RuntimeError('callback broken')
        obs=self.observer(on_async_error=callback);c=self.context(obs=obs);self.problem(c)
        errors=[]
        def worker():
            try:obs.sample(force=True)
            except observation.ObservationError as error:errors.append(str(error))
        with patch.object(observation,'_publish',side_effect=OSError('sink failed')):
            t=threading.Thread(target=worker);t.start();t.join(5)
        self.assertTrue(noticed.is_set());self.assertTrue(errors);self.assertIsNotNone(obs.callback_error)
        c.close()
        with self.assertRaises(observation.ObservationError):obs.complete(c)
        self.assertFalse(obs.final_complete)
        other=self.observer()
        with self.assertRaises(ValueError):observation.EnergyProgress(self.directory(),energy_observation=other)

    def test_status_final_commit_corruption_clock_and_censoring(self):
        obs=self.observer();c=self.context(obs=obs);p=self.problem(c);p.finish((p.initial_piece(),));c.close()
        pin=obs.complete(c);args=dict(expected_sha256=pin['sha256'],run_identity=json.loads(obs.binding),now_ns=time.monotonic_ns())
        self.assertFalse(observation.read_status(pin['path'],terminated=False,clean_outcome_authenticated=True,**args)['censored'])
        self.assertEqual(observation.read_status(pin['path'],terminated=True,**args)['final_health'],'unknown')
        self.assertTrue(observation.read_status(pin['path'],terminated=False,**args)['censored'])
        with self.assertRaises(ValueError):observation.read_status(pin['path'],terminated=True,**dict(args,now_ns=0))
        commit=obs.output/'complete.json';commit.write_text('{}')
        with self.assertRaises(ValueError):observation.read_status(pin['path'],terminated=False,**args)
        other=self.observer();ctx=self.context(obs=other);self.problem(ctx);ctx.close()
        original=observation._publish
        def failure(path,*a,**kw):
            original(path,*a,**kw)
            if path.name=='status.json':raise OSError('post status link')
        with patch.object(observation,'_publish',failure):
            with self.assertRaises(observation.ObservationError):other.complete(ctx)
        self.assertFalse((other.output/'complete.json').exists())
        raw=(other.output/'status.json').read_bytes()
        result=observation.read_status(other.output/'status.json',expected_sha256=hashlib.sha256(raw).hexdigest(),
            run_identity=json.loads(other.binding),now_ns=time.monotonic_ns(),terminated=True)
        self.assertTrue(result['censored']);self.assertFalse(result['completion_committed'])

    def test_contained_kill_and_explicit_async_error_channel(self):
        # Actual native/solver/ordinary observer in a child; no production data.
        for behavior in ('kill','fail'):
            out=self.directory();out.mkdir();env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
            env['ENERGY_EVIDENCE']=str(out/'child_artifacts.json')
            flags=['-OO'] if sys.flags.optimize==2 else ['-O'] if sys.flags.optimize else []
            proc=subprocess.Popen([sys.executable,*flags,'-B',str(HERE/'worker.py'),str(out),behavior],
                env=env,start_new_session=True,stdout=(out/'stdout').open('w'),stderr=(out/'stderr').open('w'))
            try:
                deadline=time.monotonic()+30
                signal_file=out/('failed' if behavior=='fail' else 'ready')
                while not signal_file.exists() and proc.poll() is None and time.monotonic()<deadline:time.sleep(.02)
                self.assertTrue(signal_file.exists(),(out/'stderr').read_text())
                os.killpg(proc.pid,9);proc.wait(timeout=5)
                with self.assertRaises(ProcessLookupError):os.killpg(proc.pid,0)
                status=out/'evidence/status.json';raw=status.read_bytes()
                got=observation.read_status(status,expected_sha256=hashlib.sha256(raw).hexdigest(),
                    run_identity={'run':'contained'},now_ns=time.monotonic_ns(),terminated=True)
                self.assertTrue(got['censored']);self.assertEqual(got['final_health'],'unknown')
                self.assertGreaterEqual(got['sample']['counters']['calls_started'],1)
                (out/'cleanup.json').write_bytes(energy.canonical(dict(returncode=proc.returncode,process_group_absent=True,censored=True,final_health='unknown')))
                if os.environ.get('ENERGY_EVIDENCE'):
                    shutil.copytree(out,Path(os.environ['ENERGY_EVIDENCE']).with_suffix('')/('contained_'+behavior))
            finally:
                if proc.poll() is None:os.killpg(proc.pid,9);proc.wait(timeout=5)


    def test_actual_sparse_recovery_stable_policy_domain(self):
        from timecut5.sparse_seed import SparseSeedCatalog,replay_sparse_seed
        from timecut5.streaming_seed_diagnostic import StreamingSeedObserver
        from timecut5.feasible_incumbent import recover_feasible_incumbent,verifier_sources
        import microplan.routing
        directory=self.directory();directory.mkdir()
        nodes,edges=directory/'nodes.json',directory/'edges.json'
        nodes.write_bytes(energy.canonical(4));edges.write_bytes(energy.canonical('synthetic edges'))
        def setup(role):
            ctx=self.context(role=role);p=self.problem(ctx)
            sites=dict(s=RealSite('s','B',('C',)),t=RealSite('t','X',('C',)))
            cat=SparseSeedCatalog(ctx.provider,sites,origin_anchor='A',destination_anchor='D',
                nodes_path=nodes,edges_path=edges,site_catalog_sha256=site_catalog_digest(sites),
                hierarchy_sha256=digest('tree'),candidate_sha256=digest(sorted(sites)))
            query=dict(p.case);query.pop('sites')
            query.update(hierarchy_sha256=digest('tree'),sparse_domain_sha256=cat.domain_sha256)
            return ctx,query,cat
        search,q,cat=setup('search');fresh=replay_sparse_seed(q,cat,[('s','C')],[3])
        output=self.directory();observer=StreamingSeedObserver(q,cat,output_dir=output,provenance={'synthetic':True})
        observer('incumbent',sequence=[('s','C')],charges=[3],lex_key=fresh['lex_key'],
            edge_witnesses=fresh['edge_witnesses'],status='replayed_feasible_incumbent')
        observer.journal.close();snapshot=output/'snapshot.json'
        verifier,qv,cv=setup('recovery')
        self.assertEqual(q,qv);self.assertEqual(cat.domain_sha256,cv.domain_sha256)
        receipt=recover_feasible_incumbent(snapshot,expected_checkpoint_sha256=hashlib.sha256(snapshot.read_bytes()).hexdigest(),
            query_bytes=energy.canonical(q),catalog=cv,nodes_path=nodes,edges_path=edges,
            router_source_path=Path(microplan.routing.__file__).with_suffix('.cpp'),approved_verifier_sha256=verifier_sources())
        self.assertEqual(receipt.primary_upper,fresh['lex_key'][0])
        self.assertIsNone(verifier._energy_kernel)
        self.assertGreater(search.provider._terminal_energy_route_guard.completed,0)

class ProgressLifecycleTests(unittest.TestCase):
    def test_failure_restores_active_observer_on_enter_and_exit(self):
        from timecut5 import exact_progress
        with tempfile.TemporaryDirectory() as temp:
            for phase in ('enter','exit'):
                root=Path(temp)/phase
                obs=observation.EnergyObservation(root/'evidence',run_identity={'run':phase},on_async_error=lambda error:None)
                progress=observation.EnergyProgress(root/'progress',energy_observation=obs,
                    query_sha256=digest('q'),domain_sha256=digest('d'),source_sha256={'source':digest('s')})
                try:
                    if phase=='enter':
                        with patch.object(obs,'sample',side_effect=observation.ObservationError('entry sink error')):
                            with self.assertRaises(observation.ObservationError):progress.__enter__()
                    else:
                        progress.__enter__()
                        with patch.object(obs,'sample',side_effect=observation.ObservationError('exit sink error')):
                            with self.assertRaises(observation.ObservationError):progress.__exit__(None,None,None)
                    self.assertIsNone(exact_progress._active.get())
                    self.assertEqual(obs.background_users,0)
                finally:
                    # Preserve isolation even while reproducing the old defect.
                    progress.stop.set()
                    if getattr(progress,'thread_started',False):progress.thread.join()
                    if exact_progress._active.get() is progress:exact_progress._active.reset(progress.token)

    def test_original_solver_error_survives_exit_publication_error(self):
        from timecut5 import exact_progress
        with tempfile.TemporaryDirectory() as temp:
            obs=observation.EnergyObservation(Path(temp)/'evidence',run_identity={'run':'errors'},on_async_error=lambda error:None)
            progress=observation.EnergyProgress(Path(temp)/'progress',energy_observation=obs,
                query_sha256=digest('q'),domain_sha256=digest('d'),source_sha256={'source':digest('s')})
            with self.assertRaisesRegex(ValueError,'original solver error'):
                with progress:
                    def fail(**kwargs):raise observation.ObservationError('exit publication error')
                    obs.sample=fail
                    raise ValueError('original solver error')
            self.assertIsNone(exact_progress._active.get())
            self.assertEqual(obs.background_users,0)
            self.assertIn('exit publication error',obs.error)
