"""Tiny native runtime-admission tests; no search integration or road runs."""
from dataclasses import replace
from fractions import Fraction as F
import json
from types import MappingProxyType
import unittest
from unittest.mock import patch

from . import test_energy as fixture
from . import test_combined_target_energy as combined_fixture
from timecut5.bounded import _evaluate_sequence_problem
from timecut5.hierarchy import build_regions
from timecut5.probe import ChargingCurve, Interval, State
from timecut5.real_adapter import site_catalog_digest
from timecut5.real_legs import RealSite
from timecut5.remaining_charge_bound import remaining_charge_primary_lower_bound
from timecut5.remaining_charge_runtime import (admit_remaining_charge_runtime,
    RemainingChargeRuntimeV1, RemainingChargeBoundResultV1, SuffixPotentialV1)
from timecut5.road_provider import TableFreeRegionBoundProvider
from timecut5.routing_config import RoutingConfig, TerminalEnergyConfig
from timecut5.terminal_energy import canonical, UnsupportedEnvironment


class RemainingChargeRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.EnergyTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        fixture.EnergyTests.tearDownClass.__func__(cls)

    directory = fixture.EnergyTests.directory
    context = combined_fixture.CombinedTargetEnergyTests.context

    def make(self, *, mode='full', travel=True, unsupported='reject', no_curve=False, graph=None, **changes):
        graph = graph or fixture.graph(4, [(a,b,3.25*abs(a-b),abs(a-b))
                                for a in range(4) for b in range(4) if a != b])
        context = self.context(mode=mode, g=graph, unsupported=unsupported)
        query = dict(origin='A', destination='D', H_ref=3, start_time_s=7,
            initial_energy_kwh=2, capacity_kwh=20, minimum_energy_kwh=0,
            reserve_kwh=1, consumption_kwh_per_m=1, overhead_s=2,
            lambda_stop_s=1, charging_segments=[[0,5,3,0],[5,20,1,10]], schedule=None)
        if no_curve:
            query.update(charging_segments=[], schedule=dict(a=0,b=100,D=1))
        query.update(changes)
        sites = {name: RealSite(name, anchor, ('S',) if no_curve else ('C',))
                 for name, anchor in (('s','B'), ('t','X'))}
        problem = context.problem(query, sites, origin_anchor='A', destination_anchor='D',
            site_catalog_sha256=site_catalog_digest(sites))
        bound = None
        if travel:
            def router_factory(graph):
                graph.weights['travel_time'].flags.writeable = False
                return RoutingConfig().create_router(graph, self.config, self.directory(),
                    role='landmark', artifact=self.router_artifact)
            bound = TableFreeRegionBoundProvider(context.provider, sites, build_regions(sites),
                destination_anchor='D', landmark_anchor='A',
                site_catalog_sha256=site_catalog_digest(sites), router_factory=router_factory)
        runtime = admit_remaining_charge_runtime(problem,
            energy_screen=problem._terminal_energy_screen, travel_provider=bound)
        return context, problem, bound, runtime

    def test_full_target_physical_multileg_bounds_and_declared_hmax(self):
        values = []
        for mode in ('full', 'destination_target'):
            context, p, bound, runtime = self.make(mode=mode)
            initial = (p.initial_piece(),)
            before = (context.provider.source_run_count, context.provider.target_run_count)
            actual = runtime.evaluate_group(initial)
            self.assertEqual(actual.status, 'active')
            self.assertEqual(runtime.binding['global_min_charge_seconds_per_kwh'], '1')
            self.assertEqual(runtime.binding['routing_mode'], mode)
            self.assertEqual(before, (context.provider.source_run_count, context.provider.target_run_count))
            e = p._terminal_energy_screen.certified_suffix_energy_v1(p, 'A').lower_bound
            t = bound.certified_suffix_time_v1(p, 'A').lower_bound
            self.assertEqual(t, F(9))
            expected = remaining_charge_primary_lower_bound(initial, remaining_energy_lower=e,
                remaining_time_lower=t, terminal_reserve=p.reserve,
                min_charge_seconds_per_kwh=F(1), start_time=p.start, stop_penalty=p.penalty)
            self.assertEqual(actual.primary_lower_bound, expected)
            sequence = (('s','C'), ('t','C'))
            terminal = _evaluate_sequence_problem(p, sequence)
            self.assertIsNotNone(terminal.key)
            self.assertLessEqual(actual.primary_lower_bound, terminal.key[0])
            pieces = initial
            for site, effect in sequence:
                pieces = p.advance(pieces, site, effect)
                self.assertLessEqual(runtime.evaluate_group(pieces).primary_lower_bound, terminal.key[0])
            whole = runtime.whole_route_lower_bound(2)
            self.assertLessEqual(whole.primary_lower_bound, terminal.key[0])
            self.assertEqual(whole.primary_lower_bound, expected + 2*(p.overhead+p.penalty))
            self.assertEqual((p.bound, runtime.original_hmax, p.case['H_ref']), (3,3,3))
            values.append((actual.primary_lower_bound, whole.primary_lower_bound, terminal.key))
        self.assertEqual(values[0], values[1])

    def test_zero_travel_and_detached_typed_receipts(self):
        _, p, _, runtime = self.make(travel=False)
        result = runtime.evaluate_group((p.initial_piece(),))
        self.assertIsInstance(result, RemainingChargeBoundResultV1)
        self.assertEqual(runtime.binding['travel_relaxation'], 'explicit_zero')
        receipt = runtime.binding
        receipt['original_hmax'] = -1
        self.assertEqual(runtime.binding['original_hmax'], 3)
        self.assertIn('not_authenticated_by_CutPiece', runtime.binding['frontier_contract'])
        with self.assertRaises(ValueError):
            RemainingChargeRuntimeV1(None, p, p._terminal_energy_screen, None)
        with self.assertRaises(TypeError):
            SuffixPotentialV1('time', 'active', 0, runtime.binding_sha256)
        with self.assertRaises(ValueError):
            RemainingChargeBoundResultV1('disabled_unsupported', F(0), runtime.binding_sha256)

    def test_signed_potentials_bound_native_cyclic_and_reset_suffixes(self):
        # Binary64 0.1/0.2/0.3 length accumulation restarts on every selected
        # leg. A cycle can include negative signed potential differences;
        # only the telescoped total is claimed to be nonnegative.
        graph = fixture.graph(4, [(0,1,1.1,.1),(1,0,1.1,.1),(1,2,1.2,.2),
                                  (2,1,1.2,.2),(2,3,1.3,.3),(0,3,20.,9.)])
        for mode in ('full','destination_target'):
            context, p, bound, runtime = self.make(mode=mode,graph=graph)
            screen = p._terminal_energy_screen
            for path in (('A','B','X','D'),('A','B','A','X','D'),('X','B','X','D')):
                energy = travel = F(0)
                for source,target in zip(path,path[1:]):
                    leg = context.provider.leg(source,target,
                        target_only=mode=='destination_target' and target=='D')
                    energy += leg.energy(p.rate); travel += leg.time
                self.assertLessEqual(screen.certified_suffix_energy_v1(p,path[0]).lower_bound,energy)
                self.assertLessEqual(bound.certified_suffix_time_v1(p,path[0]).lower_bound,travel)
            self.assertEqual(runtime.evaluate_group((p.initial_piece(),)).status,'active')
            self.assertEqual(screen.certified_suffix_energy_v1(p,'D').lower_bound,F(0))
            self.assertEqual(bound.certified_suffix_time_v1(p,'D').lower_bound,F(0))

    def test_large_small_native_rounding_and_label_resets_need_common_beta(self):
        graph = fixture.graph(4, [(0,1,1.,2**53),(1,2,1.,1.),(2,3,1.,1.)])
        anchors = dict(A=0,B=1,X=2,D=3)
        for mode in ('full','destination_target'):
            context = RoutingConfig(mode,TerminalEnergyConfig(quantum_exponent=0)).create_context(
                graph,self.config,self.directory(),role='search',artifact=self.router_artifact,
                energy_artifact=self.energy_artifact,anchor_nodes=anchors,
                nodes_sha256=fixture.digest(graph.node_count),edges_sha256=fixture.digest('rounding edges'),
                anchor_catalog_sha256=fixture.digest(anchors))
            self.addCleanup(context.close)
            p = fixture.EnergyTests.problem(self,context,consumption_kwh_per_m='1/9007199254740992')
            screen = p._terminal_energy_screen
            runtime = admit_remaining_charge_runtime(p,energy_screen=screen)
            full = context.provider.leg('A','D',target_only=mode=='destination_target')
            self.assertEqual(full.actual_length,F(2**53))  # both +1 additions round away
            split = context.provider.leg('A','B').energy(p.rate) + context.provider.leg(
                'B','D',target_only=mode=='destination_target').energy(p.rate)
            self.assertEqual(split,F(1)+F(2,2**53))  # second label starts again at zero
            potential = screen.receipt['anchor_potentials']['A']
            naive_unscaled = p.rate*potential
            self.assertGreater(naive_unscaled,full.energy(p.rate))
            guarded = screen.certified_suffix_energy_v1(p,'A').lower_bound
            self.assertLessEqual(guarded,full.energy(p.rate))
            self.assertLessEqual(guarded,split)
            self.assertEqual(guarded,p.rate*F(screen.receipt['beta'])*potential)
            self.assertEqual(runtime.evaluate_group((p.initial_piece(),)).status,'active')

    def test_zero_consumption_rate_preserves_travel_relaxation(self):
        for mode in ('full','destination_target'):
            _,p,bound,runtime = self.make(mode=mode,consumption_kwh_per_m=0)
            screen = p._terminal_energy_screen
            self.assertTrue(all(screen.certified_suffix_energy_v1(p,a).lower_bound==0
                                for a in p.provider.anchor_nodes))
            self.assertEqual(runtime.evaluate_group((p.initial_piece(),)).primary_lower_bound,
                             bound.certified_suffix_time_v1(p,'A').lower_bound)

    def test_accessors_ignore_private_immediate_lower_but_authenticate_certificates(self):
        _, p, bound, runtime = self.make()
        screen = p._terminal_energy_screen
        initial = (p.initial_piece(),)
        expected = runtime.evaluate_group(initial)
        lower = screen._lower
        screen._lower = MappingProxyType({anchor:F(10**20) for anchor in lower})
        self.assertEqual(runtime.evaluate_group(initial), expected)
        screen._lower = lower
        old = screen._receipt_bytes
        receipt = json.loads(old); receipt['anchor_potentials']['A'] += 1
        screen._receipt_bytes = canonical(receipt)
        with self.assertRaisesRegex(ValueError, 'certificate changed'):
            runtime.evaluate_group(initial)
        screen._receipt_bytes = old
        old = bound.landmarks[0].from_landmark['A']
        bound.landmarks[0].from_landmark['A'] = old+1
        with self.assertRaisesRegex(ValueError, 'labels changed'):
            runtime.evaluate_group(initial)
        bound.landmarks[0].from_landmark['A'] = old
        old = bound.landmark_certificate
        bound.landmark_certificate = old+b' '
        with self.assertRaises(ValueError):
            runtime.evaluate_group(initial)
        bound.landmark_certificate = old
        self.assertEqual(runtime.evaluate_group(initial), expected)

    def test_case_and_actual_runtime_mutations_fail_closed(self):
        _, p, _, runtime = self.make()
        initial = (p.initial_piece(),)
        for field in ('start','initial','capacity','floor','reserve','overhead','penalty','rate',
                      'bound','initial_remaining','origin','destination','schedule','sites','site_anchors'):
            with self.subTest(field=field):
                old = getattr(p,field)
                if field in ('origin','destination'): new = 'B'
                elif field == 'schedule': new = (F(0),F(1),F(1))
                elif field == 'sites': new = dict(s=('S',),t=('C',))
                elif field == 'site_anchors': new = dict(s='X',t='B')
                else: new = old+1
                setattr(p,field,new)
                try:
                    with self.assertRaises((ValueError,TypeError)):
                        runtime.evaluate_group(initial)
                finally:
                    setattr(p,field,old)
        old = p.curve
        # Even an equal replacement curve has a different live owner.
        p.curve = ChargingCurve(old.segments)
        with self.assertRaises(ValueError): runtime.evaluate_group(initial)
        p.curve = old
        # Coordinated case+field mutation is still a different admitted query.
        old_start = p.start
        p.case['start_time_s'] += 1; p.start += 1
        with self.assertRaises(ValueError): runtime.evaluate_group(initial)
        p.case['start_time_s'] -= 1; p.start = old_start
        # Admission itself rejects actual/case mismatch, including shared curve.
        p.curve = ChargingCurve(((0,20,1,0),))
        with self.assertRaises(ValueError):
            admit_remaining_charge_runtime(p, energy_screen=p._terminal_energy_screen)
        p.curve = old
        self.assertEqual(runtime.evaluate_group(initial).status, 'active')

    def test_native_graph_cache_policy_and_history_integrity(self):
        context, p, _, runtime = self.make()
        initial = (p.initial_piece(),)
        provider = context.provider
        old = provider.source_cache_max_sources
        provider.source_cache_max_sources += 1
        with self.assertRaises(ValueError): runtime.evaluate_group(initial)
        provider.source_cache_max_sources = old
        old = provider.source_sha256['router']
        provider.source_sha256['router'] = 'f'*64
        with self.assertRaises(ValueError): runtime.evaluate_group(initial)
        provider.source_sha256['router'] = old
        old = provider.graph
        provider.graph = object()
        with self.assertRaises(ValueError): runtime.evaluate_group(initial)
        provider.graph = old
        old = provider.router._mode
        provider.router._mode = 'destination_target'
        with self.assertRaises(ValueError): runtime.evaluate_group(initial)
        provider.router._mode = old
        history = provider._terminal_energy_route_guard
        history.pending = 1
        with self.assertRaises(ValueError): runtime.evaluate_group(initial)
        history.pending = 0
        history.status = 'invalid'
        with self.assertRaises(ValueError): runtime.evaluate_group(initial)
        history.status = 'guarded'
        self.assertEqual(runtime.evaluate_group(initial).status, 'active')

    def test_public_accessors_check_the_actual_leg_adapter(self):
        context,p,bound,runtime = self.make()
        initial = (p.initial_piece(),)
        screen = p._terminal_energy_screen
        for field,value in (('rate',F(0)),('provider',object())):
            old = getattr(p.legs,field)
            setattr(p.legs,field,value)
            try:
                with self.assertRaises(ValueError): screen.certified_suffix_energy_v1(p,'A')
                if field == 'provider':
                    with self.assertRaises(ValueError): bound.certified_suffix_time_v1(p,'A')
                with self.assertRaises(ValueError): runtime.evaluate_group(initial)
            finally:
                setattr(p.legs,field,old)
        self.assertEqual(runtime.evaluate_group(initial).status,'active')

    def test_explicit_unsupported_zero_is_none_and_sticky_integrity_still_raises(self):
        _, p, bound, runtime = self.make(unsupported='zero')
        initial = (p.initial_piece(),)
        screen = p._terminal_energy_screen
        with patch.object(screen.kernel, 'supported', return_value=False):
            result = runtime.evaluate_group(initial)
            self.assertEqual((result.status,result.primary_lower_bound), ('disabled_unsupported',None))
        self.assertIsNone(runtime.whole_route_lower_bound(1).primary_lower_bound)
        self.assertEqual(runtime.evaluate_group(initial).status, 'disabled_unsupported')
        bound.landmarks[0].from_landmark['B'] += 1
        with self.assertRaises(ValueError): runtime.evaluate_group(initial)
        with self.assertRaises(ValueError):
            runtime.evaluate_group((replace(initial[0],state=State('unknown',0,0)),))

    def test_unsupported_reject_does_not_become_zero(self):
        _, p, _, runtime = self.make(unsupported='reject')
        with patch.object(p._terminal_energy_screen.kernel, 'supported', return_value=False):
            with self.assertRaises(UnsupportedEnvironment):
                runtime.evaluate_group((p.initial_piece(),))

    def test_no_curve_is_explicitly_inactive_but_integrity_and_anchor_checks_apply(self):
        _, p, _, runtime = self.make(no_curve=True)
        initial = (p.initial_piece(),)
        result = runtime.evaluate_group(initial)
        self.assertEqual((result.status,result.primary_lower_bound), ('inactive_no_charging_curve',None))
        self.assertIsNone(runtime.whole_route_lower_bound(1).primary_lower_bound)
        with self.assertRaises(ValueError):
            runtime.evaluate_group((replace(initial[0],state=State('unknown',1,0)),))
        p.penalty += 1
        with self.assertRaises(ValueError): runtime.evaluate_group(initial)

    def test_unsupported_at_activation_disables_without_certificate_adoption(self):
        from timecut5.terminal_energy import Kernel
        # No fake certificate is constructed when activation is unsupported.
        with patch.object(Kernel,'supported',return_value=False):
            _, p, _, runtime = self.make(unsupported='zero',travel=False)
            self.assertFalse(p._terminal_energy_screen.receipt['certificate_validated'])
            result = runtime.evaluate_group((p.initial_piece(),))
            self.assertEqual((result.status,result.primary_lower_bound),('disabled_unsupported',None))
        self.assertEqual(runtime.evaluate_group((p.initial_piece(),)).status,'disabled_unsupported')

    def test_frontier_syntax_state_and_hmax_are_not_silently_relaxed(self):
        _, p, _, runtime = self.make()
        piece = p.initial_piece()
        bad = [(), (replace(piece,state=State('unknown',0,0)),),
            (piece,replace(piece,state=State('A',0,1),pi=(('s','C'),))),
            (replace(piece,state=State('A',1,0)),),
            (replace(piece,state=State('A',0,4),pi=(('s','C'),)*4),),
            (replace(piece,domain=Interval(-1,2)),),
            (replace(piece,domain=Interval(2,21)),)]
        for pieces in bad:
            with self.subTest(pieces=pieces):
                with self.assertRaises((ValueError,TypeError)): runtime.evaluate_group(pieces)
        for stops in (-1,4,True,F(1)):
            with self.assertRaises(ValueError): runtime.whole_route_lower_bound(stops)
        self.assertEqual(p.bound,3)

    def test_foreign_problem_or_nonsearch_context_cannot_be_adopted(self):
        _, p, bound, runtime = self.make()
        _, other, _, _ = self.make()
        with self.assertRaises(ValueError):
            admit_remaining_charge_runtime(other, energy_screen=p._terminal_energy_screen, travel_provider=bound)
        p.routing_role = 'verification'
        with self.assertRaises(ValueError): runtime.evaluate_group((p.initial_piece(),))


if __name__ == '__main__':
    unittest.main()
