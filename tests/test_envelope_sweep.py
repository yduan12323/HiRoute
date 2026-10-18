"""Exact old-loop differential, endpoint events and provenance guard tests."""
import asyncio
from dataclasses import FrozenInstanceError, replace
from fractions import Fraction as R
from itertools import product
import random
import unittest
from unittest.mock import patch

from timecut5 import envelope_sweep as sweep, provenance as prov
from timecut5.bounded import replay_witness, solve_bounded
from timecut5.envelope_sweep import EnvelopeSweep
from timecut5.hierarchy import solve_hierarchical
from timecut5.probe import Cut, Event, Interval, State, Witness
from timecut5.pwa import (CutPiece, ProjectionSupportPrefilter, _arrangement,
                         _point, _same_family, lower_envelope)
from validation.family5 import independent_oracle_v2 as oracle


def piece(domain, slope=0, intercept=0, chi=True, tag="a"):
    state = State("x", 0, 0)
    def at(energy):
        if not domain.contains(energy):
            raise AssertionError("Inherited witness escaped its original energy support")
        time = slope*energy+intercept
        def approach(epsilon):
            actual = time if chi else time+epsilon/2
            return Witness(actual, energy, 0, (), state,
                (Event("analytic", tag, actual, actual, energy, energy),))
        return Cut(time, chi, energy, 0, (), state, approach)
    return CutPiece(domain, slope, intercept, chi, 0, (), state, at)


def historical(pieces):
    """Frozen historical cell-selection loop, with no optimized helper calls."""
    pieces = tuple(pieces)
    _same_family(pieces)
    result = []
    for cell in _arrangement(pieces):
        e = _point(cell)
        candidates = [p for p in pieces if p.domain.contains(e)]
        if not candidates:
            continue
        minimum = min(p.slope*e+p.intercept for p in candidates)
        tied = [p for p in candidates if p.slope*e+p.intercept == minimum]
        chosen = next((p for p in tied if p.chi), tied[0])
        result.append(prov.select(chosen, pieces, cell,
            next(i for i, p in enumerate(pieces) if p is chosen), "union"))
    prov.batch("union", pieces, result)
    return tuple(result)


def signature(pieces):
    return [(prov.signature(p), tuple(prov.witness_dict(
        p.at((p.domain.lo+p.domain.hi)/2).approach(epsilon))
        for epsilon in (R(1), R(1, 10**30)))) for p in pieces]


class EnvelopeSweepTests(unittest.TestCase):
    def parity(self, pieces, *, formula=False):
        expected = historical(pieces)
        with EnvelopeSweep(enabled=True) as policy:
            actual = lower_envelope(pieces)
        self.assertEqual(signature(actual), signature(expected))
        self.assertEqual([id(p._point) for p in actual], [id(p._point) for p in expected])
        if formula:
            oracle.exact_family_equal([oracle.load(prov.signature(p)) for p in pieces],
                                     [oracle.load(prov.signature(p)) for p in actual])
        return actual, policy.snapshot()

    def test_all_endpoint_flags_singletons_gaps_and_zero(self):
        for flags in product((False, True), repeat=4):
            values = (piece(Interval(0, 1, *flags[:2]), 1, 0, False, "left"),
                      piece(Interval(1, 2, *flags[2:]), -1, 2, True, "right"),
                      piece(Interval(1, 1), 0, 1, False, "point"),
                      piece(Interval(4, 5, False, False), 0, 0, True, "gap"))
            self.parity(values, formula=True)
        self.parity((piece(Interval(0, 0)),), formula=True)
        result, stats = self.parity(())
        self.assertEqual(result, ())
        self.assertEqual((stats.calls, stats.pair_tests, stats.event_updates), (1, 0, 0))

    def test_simultaneous_crossings_attainment_and_original_order(self):
        for attained in (False, True):
            values = (piece(Interval(0, 2), 2, 0, False, "slope2"),
                      piece(Interval(0, 2), 0, 2, attained, "flat"),
                      piece(Interval(0, 2), -2, 4, True, "slope-2"),
                      piece(Interval(1, 1), 0, 2, True, "singleton"))
            result, _ = self.parity(values, formula=True)
            point = next(p for p in result if p.domain == Interval(1, 1))
            self.assertIs(point._point, values[1 if attained else 2]._point)
        # A root at two excluded endpoints remains a historical arrangement
        # knot, but neither parent is a supported candidate at that singleton.
        result, _ = self.parity((piece(Interval(0, 1, True, False), 1),
                                piece(Interval(1, 2, False, True), -1, 2)))
        self.assertFalse(any(p.domain == Interval(1, 1) for p in result))

    def test_identical_lines_and_repeated_parent_identity(self):
        a = piece(Interval(0, 2), 1, 0, False, "first")
        b = piece(Interval(0, 2), 1, 0, True, "attained")
        parents = (a, b, a, b)
        original = prov.select_many
        seen = []
        def capture(parents, choices, mode):
            choices = tuple(choices)
            seen.extend(index for index, _ in choices)
            return original(parents, choices, mode)
        with patch.object(prov, "select_many", side_effect=capture):
            self.parity(parents)
        self.assertTrue(seen)
        self.assertEqual(set(seen), {1})
        self.parity((a, a, replace(a, _point=piece(a.domain, 1, 0, False, "other")._point)))

    def test_seeded_rational_differential_and_complete_formula(self):
        rng = random.Random(202610171448)
        for trial in range(120):
            parents = []
            for index in range(rng.randrange(1, 11)):
                if parents and rng.randrange(7) == 0:
                    parents.append(rng.choice(parents))
                    continue
                lo, hi = sorted(R(rng.randrange(-5, 7), rng.randrange(1, 4)) for _ in range(2))
                lc, rc = ((True, True) if lo == hi else
                          (bool(rng.randrange(2)), bool(rng.randrange(2))))
                parents.append(piece(Interval(lo, hi, lc, rc),
                    R(rng.randrange(-4, 5), rng.randrange(1, 4)),
                    R(rng.randrange(-5, 6), rng.randrange(1, 4)),
                    bool(rng.randrange(2)), str(index)))
            with self.subTest(trial=trial):
                self.parity(tuple(parents), formula=True)

    def test_no_point_callback_added_and_same_family_guard_unchanged(self):
        bad = piece(Interval(0, 2))
        bad = replace(bad, _point=lambda e: (_ for _ in ()).throw(AssertionError("callback")))
        with EnvelopeSweep(enabled=True):
            result = lower_envelope((bad,))
        self.assertTrue(result)
        for values in ((bad, replace(bad, rho=1)),
                       (bad, replace(bad, state=State("other", 0, 0)))):
            with EnvelopeSweep(enabled=True), self.assertRaises(ValueError):
                lower_envelope(values)

    def test_event_work_bound_replaces_per_cell_parent_rescans(self):
        n = 24
        parents = tuple(piece(Interval(-1, 0), i**3, i**2, bool(i % 2), str(i))
                        for i in range(1, n+1))
        with EnvelopeSweep(enabled=False) as off:
            expected = lower_envelope(parents)
        with EnvelopeSweep(enabled=True) as on:
            actual = lower_envelope(parents)
        self.assertEqual(signature(actual), signature(expected))
        a, b = on.snapshot(), off.snapshot()
        self.assertEqual(a.pair_tests, n*(n-1)//2)
        self.assertEqual(a.event_updates, 2*(n+a.relation_intervals))
        self.assertLessEqual(a.event_updates, 2*n+2*n*(n-1))
        self.assertLessEqual(a.heap_pushes, a.event_updates)
        self.assertLessEqual(a.heap_pops, a.heap_pushes)
        self.assertEqual(a.baseline_parent_visits, 0)
        self.assertEqual(b.baseline_parent_visits, n*b.arrangement_cells)
        self.assertGreater(b.baseline_parent_visits, 5*a.event_updates)
        self.assertEqual(a.selected_cells, b.selected_cells)

    def test_absent_and_disabled_do_not_enter_sweep_or_batch_helper(self):
        parents = (piece(Interval(0, 1)),)
        with patch.object(sweep, "select_envelope", side_effect=AssertionError("sweep")), \
             patch.object(prov, "select_many", side_effect=AssertionError("new helper")):
            expected = lower_envelope(parents)
            with EnvelopeSweep(enabled=False) as policy:
                actual = lower_envelope(parents)
        self.assertEqual(signature(actual), signature(expected))
        self.assertEqual(policy.snapshot().baseline_parent_visits, 3)

    def test_symmetric_entry_and_completion_counts_after_arrangement(self):
        parents = (piece(Interval(0, 1)),)
        for enabled in (False, True):
            with EnvelopeSweep(enabled=enabled) as policy:
                target = (patch.object(sweep, "select_envelope", side_effect=RuntimeError("stop"))
                          if enabled else patch.object(prov, "select", side_effect=RuntimeError("stop")))
                with target, self.assertRaises(RuntimeError):
                    lower_envelope(parents)
            snapshot = policy.snapshot()
            self.assertEqual((snapshot.calls, snapshot.completed_calls,
                              snapshot.input_pieces, snapshot.arrangement_cells), (1, 0, 1, 3))
        with EnvelopeSweep(enabled=True) as policy:
            with patch("timecut5.pwa._arrangement", side_effect=RuntimeError("arrangement")):
                with self.assertRaises(RuntimeError):
                    lower_envelope(parents)
        self.assertEqual(policy.snapshot().calls, 0)

    def test_exact_bool_detached_snapshots_and_context_restoration(self):
        for value in (None, 0, 1, R(1), 1.0, "true"):
            with self.assertRaises(ValueError):
                EnvelopeSweep(enabled=value)
        context = EnvelopeSweep(enabled=True)
        before = context.snapshot()
        parents = (piece(Interval(0, 1)),)
        with context:
            lower_envelope(parents)
            with self.assertRaisesRegex(RuntimeError, "inner"):
                with EnvelopeSweep(enabled=False) as inner:
                    lower_envelope(parents)
                    raise RuntimeError("inner")
            lower_envelope(parents)
            with self.assertRaises(ValueError):
                with context:
                    pass
        saved = context.snapshot()
        lower_envelope(parents)
        self.assertEqual(context.snapshot(), saved)
        self.assertEqual((before.calls, saved.calls, inner.snapshot().calls), (0, 2, 1))
        with self.assertRaises(FrozenInstanceError):
            before.calls = 2
        with self.assertRaises(AttributeError):
            context.enabled = False
        with self.assertRaises(ValueError):
            with context:
                pass

    def test_interleaved_async_contexts_are_separate(self):
        async def work(enabled):
            with EnvelopeSweep(enabled=enabled) as context:
                await asyncio.sleep(0)
                lower_envelope((piece(Interval(0, 1)),))
                await asyncio.sleep(0)
                lower_envelope((piece(Interval(0, 1)),))
            return context.snapshot()
        async def both():
            return await asyncio.gather(work(True), work(False))
        on, off = asyncio.run(both())
        self.assertEqual((on.calls, off.calls), (2, 2))
        self.assertEqual((on.baseline_parent_visits, off.baseline_parent_visits), (0, 6))

    def test_recorded_mode_uses_historical_loop_and_identical_payloads(self):
        def run(enabled):
            with prov.Recorder() as recorder, EnvelopeSweep(enabled=enabled) as policy:
                a = prov.bind(piece(Interval(0, 2), 1, tag="a"), "analytic", tag="a")
                b = prov.bind(piece(Interval(0, 2), -1, 2, tag="b"), "analytic", tag="b")
                with patch.object(sweep, "select_envelope", side_effect=AssertionError("recorded sweep")):
                    result = lower_envelope((a, b, a))
                values = signature(result)
                return recorder.export(result), recorder.export_witness_requests(), values, policy.snapshot()
        off, on = run(False), run(True)
        self.assertEqual(off[:3], on[:3])
        self.assertEqual(on[3].recorded_fallback_calls, 1)
        self.assertEqual(on[3].pair_tests, 0)

    def test_batch_helper_known_parent_guard_and_recorded_exact_parity(self):
        a, b = piece(Interval(0, 1)), piece(Interval(0, 1), intercept=5)
        object.__setattr__(b, "_family", object())
        with patch.object(prov, "replace", side_effect=AssertionError("output before guard")):
            with self.assertRaisesRegex(ValueError, "Recorder context"):
                prov.select_many((a, b), ((0, Interval(0, 0)),), "union")
            self.assertEqual(prov.select_many((a, b), (), "union"), ())
        with EnvelopeSweep(enabled=True), self.assertRaisesRegex(ValueError, "Recorder context"):
            lower_envelope((a, b))
        for index in (True, -1, 2):
            with self.assertRaises(ValueError):
                prov.select_many((a, b), ((index, Interval(0, 0)),), "union")
        def recorded(batch):
            with prov.Recorder() as recorder:
                a = prov.bind(piece(Interval(0, 1)), "analytic")
                choices = ((0, Interval(0, 0)), (0, Interval(0, 1, False, False)))
                result = (prov.select_many((a,), choices, "union") if batch else
                          tuple(prov.select(a, (a,), domain, i, "union") for i, domain in choices))
                return recorder.export(result)
        self.assertEqual(recorded(False), recorded(True))

    def test_tiny_solvers_with_prefilter_keep_keys_and_replay(self):
        query = dict(case_id="envelope-tiny", H_ref=2, origin="o", destination="z",
            start_time_s="0", initial_energy_kwh="2", capacity_kwh="4",
            minimum_energy_kwh="0", reserve_kwh="1", overhead_s="1",
            lambda_stop_s="1", consumption_kwh_per_m="1",
            charging_segments=[["0", "2", "1", "0"], ["2", "4", "2", "-2"]],
            sites={"c": ["C", "S", "CS"]}, schedule=dict(a="0", b="20", D="2"),
            edges=[dict(source=a, target=b, time_s="1", length_m="1")
                   for a, b in (("o", "c"), ("c", "z"))])
        for solver, dominance in product((solve_bounded, solve_hierarchical), (False, True)):
            expected = solver(query, dominance=dominance)
            with EnvelopeSweep(enabled=True), ProjectionSupportPrefilter(enabled=True):
                actual = solver(query, dominance=dominance)
            self.assertEqual(actual.canonical(), expected.canonical())
            bounded = actual.bounded if hasattr(actual, "bounded") else actual
            if bounded.result.witness is not None:
                self.assertEqual(replay_witness(query, bounded.result.witness), bounded.result.key)


if __name__ == "__main__":
    unittest.main()
