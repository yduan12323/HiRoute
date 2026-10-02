"""Exhaustive bounded stop-order search with continuous, globally coupled energy.

For every order and assignment of the independent scheduled requirement, enumerate
the arrival/departure intervals of each piecewise charging curve. Within a cell,
the charging integral is affine, so an LP gives the global continuous optimum.
No greedy prefix energy is frozen: extensions reoptimize the entire prefix.
This expensive reference search is for small worlds, not continental scaling.
"""
from itertools import permutations, product
import math

import numpy as np
from scipy.optimize import linprog

from .evaluation import assemble_plan, best_one_stop, plan_key, validate_trip
from .models import EVModel, PiecewiseChargingCurve, PlannerConfig


class FlatStopPlanner:
    def __init__(self, travel, ev=EVModel(), curve=PiecewiseChargingCurve(), config=PlannerConfig(), site_curves=None):
        self.travel, self.ev, self.curve, self.config = travel, ev, curve, config
        self.site_curves = dict(site_curves or {})
        self.stats = {}

    def solve(self, trip, sites, schedule=None, region_labels=None):
        """Exact for <= maximum_stops distinct anchors on the supplied road legs.

        Region labels are intentionally ignored. Arbitrary road path alternatives,
        revisiting the same anchor, and more stops are outside this reference domain.
        Exactness is conditional on this explicit domain, never full EV routing.
        """
        validate_trip(trip, self.ev)
        sites = tuple(sorted(sites, key=lambda s: s.site_id))
        if len({s.site_id for s in sites}) != len(sites):
            raise ValueError('Duplicate Site')
        sites = tuple(s for s in sites if s.access_node is not None and s.attachment_status == 'attached')
        self.stats = {'orders_evaluated': 0, 'linear_programs': 0, 'domain': 'bounded distinct-anchor orders; time-optimal road legs; continuous charging'}
        if self.config.maximum_stops <= 1 and not self.site_curves:
            return best_one_stop(trip, sites if self.config.maximum_stops else (), self.travel,
                                 self.ev, self.curve, schedule, self.config)
        best = self.optimize_order(trip, (), schedule)
        for count in range(1, min(self.config.maximum_stops, len(sites)) + 1):
            for order in permutations(sites, count):
                plan = self.optimize_order(trip, order, schedule)
                if plan is not None and (best is None or plan_key(plan) < plan_key(best)):
                    best = plan
        return best

    def optimize_order(self, trip, order, schedule=None):
        """Continuous optimum for a fixed vehicle-stop order; useful as an oracle."""
        validate_trip(trip, self.ev)
        self.stats['orders_evaluated'] = self.stats.get('orders_evaluated', 0) + 1
        nodes = [trip.origin, *(s.access_node for s in order), trip.destination]
        legs = [self.travel.leg(a, b) for a, b in zip(nodes, nodes[1:])]
        if any(leg is None for leg in legs):
            return None
        if trip.mobility_budget_s is not None and sum(l.time_s for l in legs) > trip.mobility_budget_s + 1e-7:
            return None
        if not order:
            if trip.initial_energy_kwh - self.ev.drive_energy(legs[0].distance_m) < self.ev.terminal_floor - 1e-8 or (schedule and schedule.hard):
                return None
            return assemble_plan(trip, (), legs, [], [], [], [], [], None, None,
                                 schedule.miss_penalty_s if schedule else 0, self.ev, self.config)
        assignments = [None] if schedule is None or not schedule.hard else []
        if schedule is not None:
            assignments.extend(i for i, site in enumerate(order) if schedule.supports(site))
        cells = []
        for site in order:
            if 'charge' in site.transport_capabilities:
                curve = self.site_curves.get(site.site_id, self.curve)
                if not isinstance(curve, PiecewiseChargingCurve):
                    raise TypeError('Exact LP optimizer requires a piecewise charging integral')
                segments = curve.segments(self.ev.capacity_kwh)
                cells.append([(a, b) for a in segments for b in segments if b[1] >= a[0]])
            else:
                cells.append([None])
        best = None
        for assignment in assignments:
            for cell in product(*cells):
                plan = self._solve_cell(trip, order, legs, cell, schedule, assignment)
                if plan is not None and (best is None or plan_key(plan) < plan_key(best)):
                    best = plan
        return best

    def _solve_cell(self, trip, order, legs, cell, schedule, scheduled_index):
        k, ev, cfg = len(order), self.ev, self.config
        # Per stop: arrival energy, departure energy, arrival clock, departure
        # clock, charge duration. Last two variables: schedule start and deviation.
        n = 5 * k + 2
        ae, de, at, dt, ct = ([5 * i + j for i in range(k)] for j in range(5))
        activity, deviation = n - 2, n - 1
        bounds = [(0, None)] * n
        equalities, rhs_eq, inequalities, rhs_ub = [], [], [], []
        def eq(values, rhs):
            row = np.zeros(n)
            for index, v in values.items():
                row[index] = v
            equalities.append(row); rhs_eq.append(rhs)
        def le(values, rhs):
            row = np.zeros(n)
            for index, v in values.items():
                row[index] = v
            inequalities.append(row); rhs_ub.append(rhs)
        for i, segments in enumerate(cell):
            bounds[ae[i]] = bounds[de[i]] = (ev.minimum_energy_kwh, ev.capacity_kwh)
            if segments is None:
                eq({de[i]: 1, ae[i]: -1}, 0)
                bounds[ct[i]] = (0, 0)
            else:
                arr, dep = segments
                bounds[ae[i]] = (max(arr[0], ev.minimum_energy_kwh), arr[1])
                bounds[de[i]] = (max(dep[0], ev.minimum_energy_kwh), dep[1])
                eq({ct[i]: 1, de[i]: -dep[2], ae[i]: arr[2]}, dep[3] - arr[3])
            le({ae[i]: 1, de[i]: -1}, 0)
            if i == 0:
                eq({ae[i]: 1}, trip.initial_energy_kwh - ev.drive_energy(legs[i].distance_m))
                eq({at[i]: 1}, legs[i].time_s)
            else:
                eq({ae[i]: 1, de[i - 1]: -1}, -ev.drive_energy(legs[i].distance_m))
                eq({at[i]: 1, dt[i - 1]: -1}, legs[i].time_s)
            le({at[i]: 1, ct[i]: 1, dt[i]: -1}, -cfg.overhead_s)
        le({de[-1]: -1}, -ev.drive_energy(legs[-1].distance_m) - ev.terminal_floor)
        penalty = 0.0 if schedule is None or scheduled_index is not None else schedule.miss_penalty_s
        objective = np.zeros(n); objective[dt[-1]] = 1
        if scheduled_index is None:
            bounds[activity] = bounds[deviation] = (0, 0)
        else:
            i = scheduled_index
            # Scheduled activity starts after overhead; charging starts at the
            # same instant if compatible, otherwise the activity follows charging.
            values = {at[i]: 1, activity: -1}
            if not schedule.compatible_with_charging:
                values[ct[i]] = 1
            le(values, -cfg.overhead_s)
            le({activity: 1, dt[i]: -1}, -schedule.duration_s)
            lo, hi = schedule.window_start_s - trip.start_time_s, schedule.window_end_s - trip.start_time_s
            le({activity: -1, deviation: -1}, -lo)
            le({activity: 1, deviation: -1}, hi)
            if schedule.hard:
                bounds[deviation] = (0, 0)
            objective[deviation] = schedule.time_penalty_per_s
        self.stats['linear_programs'] = self.stats.get('linear_programs', 0) + 1
        options = {'primal_feasibility_tolerance': 1e-8, 'dual_feasibility_tolerance': 1e-8}
        args = dict(A_ub=np.array(inequalities), b_ub=np.array(rhs_ub),
                    A_eq=np.array(equalities), b_eq=np.array(rhs_eq), bounds=bounds, method='highs', options=options)
        result = linprog(objective, **args)
        if result.status == 2:
            return None
        if not result.success:
            raise RuntimeError(f'LP optimization failed: {result.message}')
        # Secondary minimization removes surplus energy hidden by scheduled dwell.
        secondary = np.zeros(n)
        for a, d in zip(ae, de):
            secondary[d] += 1; secondary[a] -= 1
        args['A_ub'] = np.vstack([args['A_ub'], objective])
        args['b_ub'] = np.append(args['b_ub'], result.fun + 1e-8)
        tied = linprog(secondary, **args)
        if not tied.success:
            raise RuntimeError(f'LP tie-break failed: {tied.message}')
        x = tied.x
        charge_times = [max(0.0, x[j]) for j in ct]
        schedule_penalty = 0 if scheduled_index is None else x[deviation] * schedule.time_penalty_per_s
        plan = assemble_plan(trip, order, legs, x[ae], x[de], x[at], x[dt], charge_times,
                             scheduled_index, None if scheduled_index is None else x[activity], penalty + schedule_penalty, ev, cfg)
        # Check returned continuous resource state rather than trusting solver status.
        if plan.terminal_energy_kwh < ev.terminal_floor - 1e-6 or any(e.arrival_energy_kwh < ev.minimum_energy_kwh - 1e-6 for e in plan.stops):
            raise RuntimeError('LP output violates energy feasibility')
        return plan
