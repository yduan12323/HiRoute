"""Optional dyadic ALT: exact unit conversion and tiny native certificates."""
from fractions import Fraction as F
import hashlib
import json
import math
import sys
import unittest
from unittest.mock import patch

import numpy as np

from . import test_energy as fixture
from . import test_combined_target_energy as combined_fixture
from timecut5.bounded import _solve_problem
from timecut5.hierarchy import build_regions, _solve_hierarchical_problem
from timecut5.real_adapter import site_catalog_digest
from timecut5.real_legs import RealSite
from timecut5.remaining_charge_runtime import admit_remaining_charge_runtime
from timecut5.road_landmark import certify_integer_landmark
from timecut5.road_provider import TableFreeRegionBoundProvider
from timecut5.routing_config import RoutingConfig


class DyadicTimeALTTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.EnergyTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        fixture.EnergyTests.tearDownClass.__func__(cls)

    directory = fixture.EnergyTests.directory
    context = combined_fixture.CombinedTargetEnergyTests.context
    problem = fixture.EnergyTests.problem

    def landmark_router(self, graph):
        graph.weights['travel_time'].flags.writeable = False
        return RoutingConfig().create_router(graph,self.config,self.directory(),
            role='landmark',artifact=self.router_artifact)

    def certify(self, graph, *, q=None, factory=None):
        options = {} if q is None else dict(time_quantum_exponent=q)
        return certify_integer_landmark(graph,{str(i):i for i in range(graph.node_count)},
            '0',factory or self.landmark_router,graph_nodes_sha256='a'*64,
            graph_edges_sha256='b'*64,**options)

    def make(self, *, q=10, strategy='indexed', onward=True, mode='full', graph=None,
             anchors=None, provider_class=TableFreeRegionBoundProvider, unsupported='reject'):
        graph = graph or fixture.graph(4,[(a,b,.5,1.) for a,b in
            ((0,1),(1,0),(1,2),(2,1),(2,3),(3,2))])
        context = self.context(mode=mode,g=graph,anchors=anchors,unsupported=unsupported)
        p = self.problem(context)
        sites = dict(s=RealSite('s','B',('C',)),t=RealSite('t','X',('C',)))
        root = build_regions(sites,leaf_size=1)
        bound = provider_class(context.provider,sites,root,
            destination_anchor='D',landmark_anchor='A',site_catalog_sha256=site_catalog_digest(sites),
            router_factory=self.landmark_router,alt_strategy=strategy,onward_alt=onward,
            time_quantum_exponent=q)
        return context,p,bound,root

    def test_default_and_explicit_zero_have_identical_v1_certificate_bytes(self):
        graph = fixture.graph(3,[(0,1,.5,1),(1,2,1.25,1),(2,0,2.,1)])
        default, data = self.certify(graph)
        explicit, data0 = self.certify(graph,q=0)
        self.assertEqual(data,data0)
        self.assertEqual(default,explicit)
        receipt = json.loads(data)
        self.assertEqual(receipt['schema'],'hiroute.m5d.integer_second_landmark.v1')
        self.assertEqual(receipt['edge_weight_policy'],'floor(nextafter(frozen_binary64_time,-infinity))')
        self.assertNotIn('time_quantum_exponent',receipt)
        self.assertNotIn('time_units_per_second',receipt)
        # The pre-option v1 payload, independently specified for this graph.
        audited = [dict(direction=direction,reached_nodes=3,checked_edges=3,
            label_sha256=hashlib.sha256(np.array(values,dtype=np.float64).tobytes()).hexdigest())
            for direction,values in (('from_landmark',[0.,0.,1.]),('to_landmark',[0.,2.,1.]))]
        legacy = dict(schema='hiroute.m5d.integer_second_landmark.v1',
            graph_nodes_sha256='a'*64,graph_edges_sha256='b'*64,
            router_source_sha256=self.router_artifact.receipt['source_sha256'],
            root_anchor='0',root_node=0,edge_weight_policy='floor(nextafter(frozen_binary64_time,-infinity))',
            exact_integer_limit=2**53,audited=audited,
            anchor_labels={'0':[0,0],'1':[0,2],'2':[1,1]})
        self.assertEqual(data,json.dumps(legacy,sort_keys=True,separators=(',',':'),allow_nan=False).encode())

    def test_dyadic_boundaries_are_exact_conservative_integer_units(self):
        quantum = 1/1024
        times = [math.ulp(0.),math.nextafter(quantum,0.),quantum,
                 math.nextafter(quantum,math.inf),.5,1.,math.nextafter(1.,math.inf)]
        rows = [(0,i+1,t,1.) for i,t in enumerate(times)]
        rows += [(i+1,0,t,1.) for i,t in enumerate(times)]
        graph = fixture.graph(len(times)+1,rows)
        captured = []
        def factory(g):
            captured.extend(g.weights['travel_time'].tolist())
            return self.landmark_router(g)
        labels,data = self.certify(graph,q=10,factory=factory)
        expected = [max(0,math.ceil(F.from_float(t)*1024)-1) for t in times]
        self.assertEqual(captured,expected+expected)
        for i,(t,units) in enumerate(zip(times,expected)):
            self.assertEqual(labels.from_landmark[str(i+1)],units)
            self.assertEqual(labels.to_landmark[str(i+1)],units)
            self.assertLessEqual(F(units,1024),F.from_float(t))
        receipt = json.loads(data)
        self.assertEqual(receipt['schema'],'hiroute.m5d.dyadic_second_landmark.v2')
        self.assertEqual((receipt['time_quantum_exponent'],receipt['time_units_per_second']),(10,1024))
        self.assertEqual([row['checked_edges'] for row in receipt['audited']],[len(rows)]*2)

    def test_invalid_quantum_and_weights_fail_before_router_construction(self):
        def forbidden(_):
            self.fail('Invalid policy or edge reached routing')
        graph = fixture.graph(2,[(0,1,1.,1.)])
        for q in (True,False,10.,F(10),-1,1,11,1024,'10'):
            with self.subTest(q=q),self.assertRaises(ValueError):
                self.certify(graph,q=q,factory=forbidden)
        for time in (0.,-1.,math.nan,math.inf,sys.float_info.max,(2**53+2)/1024):
            with self.subTest(time=time),self.assertRaises(ValueError):
                self.certify(fixture.graph(2,[(0,1,time,1.)]),q=10,factory=forbidden)

    def test_exact_label_plus_edge_guard_and_both_edge_audits_are_retained(self):
        # An individual integer edge below 2^53 is insufficient: the retained
        # finite-label + max-edge check must still reject this graph.
        with self.assertRaisesRegex(ValueError,'exact integer domain'):
            self.certify(fixture.graph(2,[(0,1,2**43,1.)]),q=10)
        labels,_ = self.certify(fixture.graph(2,[(0,1,2**42,1.)]),q=10)
        self.assertEqual(labels.from_landmark['1'],2**52-1)
        graph = fixture.graph(3,[(a,b,.5,1.) for a in range(3) for b in range(3) if a!=b])
        for bad_reverse in (False,True):
            def factory(g):
                native = self.landmark_router(g)
                class Corrupt:
                    provenance = native.provenance
                    def full(self,root,reverse=False):
                        values = native.full(root,reverse=reverse)
                        if reverse == bad_reverse:
                            values[0][1] = 1024.
                        return values
                    def close(self): native.close()
                return Corrupt()
            with self.subTest(reverse=bad_reverse),self.assertRaisesRegex(ValueError,'violates an edge'):
                self.certify(graph,q=10,factory=factory)

    def test_all_region_singleton_onward_and_runtime_outputs_use_exact_seconds(self):
        for q in (0,10):
            step = F(0) if q==0 else F(511,1024)
            outcomes=[]
            for strategy in ('indexed','recompute'):
                for onward in (False,True):
                    _,p,bound,root = self.make(q=q,strategy=strategy,onward=onward)
                    initial=(p.initial_piece(),)
                    self.assertEqual((bound.time_quantum_exponent,bound.time_units_per_second),(q,1<<q))
                    self.assertEqual(bound._incoming('A',root),step)
                    if onward: self.assertEqual(bound._outgoing(root),step)
                    region=bound.bound(p,initial,root,'C')[0]
                    expected=p.overhead+p.penalty+step*(2 if onward else 1)
                    self.assertEqual(region,expected)
                    for site,steps in (('s',1),('t',2)):
                        value=bound.singleton_bound(p,initial,site,'C')
                        self.assertEqual(value,p.overhead+p.penalty+step*(3 if onward else steps))
                    self.assertEqual(bound.certified_suffix_time_v1(p,'A').lower_bound,3*step)
                    runtime=admit_remaining_charge_runtime(p,
                        energy_screen=p._terminal_energy_screen,travel_provider=bound)
                    zero=admit_remaining_charge_runtime(p,energy_screen=p._terminal_energy_screen)
                    self.assertEqual(runtime.evaluate_group(initial).primary_lower_bound,
                                     zero.evaluate_group(initial).primary_lower_bound+3*step)
                    self.assertEqual(runtime.original_hmax,p.bound)
                    outcomes.append((onward,region))
            self.assertEqual(outcomes[:2],outcomes[2:])

    def test_full_target_selected_legs_and_exact_results_are_unchanged(self):
        outputs=[]
        for mode in ('full','destination_target'):
            for q in (0,10):
                context,p,bound,root=self.make(q=q,mode=mode)
                direct=context.provider.leg('A','D',target_only=mode=='destination_target')
                selected=(direct,context.provider.edge_witnesses['A','D'])
                flat=_solve_problem(p,verified_primary_upper=F(100),singleton_bound=bound.singleton_bound)
                hier=_solve_hierarchical_problem(p,True,root,
                    verified_primary_upper=F(100),bound_provider=bound).bounded
                self.assertEqual(flat.result.key,hier.result.key)
                self.assertIsNotNone(flat.result.key)
                outputs.append((selected,flat.result.status,flat.result.key))
        self.assertTrue(all(value==outputs[0] for value in outputs))

    def test_missing_terms_and_quantized_zero_cycles_do_not_mean_unreachable(self):
        graph=fixture.graph(5,[(0,1,.0001,1.),(1,0,.0001,1.),(1,2,.5,1.),(2,3,.5,1.)])
        for mode in ('full','destination_target'):
            context,p,bound,root=self.make(mode=mode,graph=graph,anchors=dict(A=0,B=1,X=2,D=3,Y=4))
            self.assertEqual(bound.landmarks[0].from_landmark['B'],0)
            self.assertEqual(bound.certified_suffix_time_v1(p,'Y').lower_bound,F(0))
            self.assertEqual(bound._incoming('Y',root),F(0))
            self.assertTrue(context.provider.leg('A','D',target_only=mode=='destination_target').reachable)
            self.assertFalse(context.provider.leg('Y','D',target_only=mode=='destination_target').reachable)
            self.assertEqual(bound.certified_suffix_time_v1(p,'Y').status,'active')

    def test_native_rounding_and_multiple_leg_label_resets(self):
        graph=fixture.graph(4,[(0,1,2**41,1.),(1,2,2**-12,1.),(2,3,2**-12,1.)])
        for mode in ('full','destination_target'):
            context,p,bound,_=self.make(mode=mode,graph=graph)
            direct=context.provider.leg('A','D',target_only=mode=='destination_target')
            split=context.provider.leg('A','B').time+context.provider.leg(
                'B','D',target_only=mode=='destination_target').time
            self.assertEqual(direct.time,F(2**41))
            self.assertEqual(split,F(2**41)+F(1,2048))
            lower=bound.certified_suffix_time_v1(p,'A').lower_bound
            self.assertEqual(lower,F(2**41)-F(1,1024))
            self.assertLessEqual(lower,direct.time)
            self.assertLessEqual(lower,split)

    def test_quantum_and_certificate_drift_cannot_reinterpret_suffix_units(self):
        _,p,bound,root=self.make()
        runtime=admit_remaining_charge_runtime(p,energy_screen=p._terminal_energy_screen,travel_provider=bound)
        for field,value in (('time_quantum_exponent',0),('time_units_per_second',1)):
            with self.assertRaises(AttributeError): setattr(bound,field,value)
        old=bound._time_quantum_policy
        bound._time_quantum_policy=(0,1)
        for call in (lambda:bound._incoming('A',root), lambda:bound._incoming_recomputed('A',root),
                     lambda:bound._outgoing(root), lambda:bound._outgoing_recomputed(root),
                     lambda:bound.singleton_bound(p,(p.initial_piece(),),'s','C')):
            with self.assertRaises(ValueError): call()
        with self.assertRaises(ValueError): bound.certified_suffix_time_v1(p,'A')
        with self.assertRaises(ValueError): runtime.evaluate_group((p.initial_piece(),))
        bound._time_quantum_policy=old
        old=bound.landmark_certificate
        receipt=json.loads(old);receipt['time_units_per_second']=1
        bound.landmark_certificate=json.dumps(receipt).encode()
        with self.assertRaises(ValueError): bound.certified_suffix_time_v1(p,'A')
        bound.landmark_certificate=old
        self.assertEqual(runtime.evaluate_group((p.initial_piece(),)).status,'active')

    def test_legacy_member_scan_subclass_also_converts_units(self):
        from scripts.m5d_supplement_alt import SameALTMemberScan
        _,p,bound,root=self.make(provider_class=SameALTMemberScan)
        self.assertEqual(bound._incoming('A',root),F(511,1024))
        self.assertEqual(bound.bound(p,(p.initial_piece(),),root,'C')[0],
                         p.overhead+p.penalty+F(1022,1024))
        bound._time_quantum_policy=(0,1)
        with self.assertRaises(ValueError): bound._incoming('A',root)

    def test_disabled_zero_does_not_hide_invalid_quantum_types(self):
        _,p,bound,_=self.make(unsupported='zero')
        runtime=admit_remaining_charge_runtime(p,energy_screen=p._terminal_energy_screen,travel_provider=bound)
        original=bound._time_quantum_policy
        with patch.object(p._terminal_energy_screen.kernel,'supported',return_value=False):
            bound._time_quantum_policy=(10,1024.)
            with self.assertRaises(ValueError): bound.certified_suffix_time_v1(p,'A')
            with self.assertRaises(ValueError): runtime.evaluate_group((p.initial_piece(),))
            bound._time_quantum_policy=original
            self.assertEqual(bound.certified_suffix_time_v1(p,'A').status,'disabled_unsupported')
        bound._time_quantum_policy=(10.,1024)
        with self.assertRaises(ValueError): bound.certified_suffix_time_v1(p,'A')
        with self.assertRaises(ValueError): runtime.evaluate_group((p.initial_piece(),))
        bound._time_quantum_policy=original


if __name__=='__main__':
    unittest.main()
