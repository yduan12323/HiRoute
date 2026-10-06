"""Observe the unchanged accepted evaluator; never duplicate its objective."""
from unittest.mock import patch
from stopplan4r import evaluation

ENERGY_TOL = 1e-8
TIME_TOL = 1e-8
ROLES = ('C', 'S', 'CS')


def effects(plan, site, schedule):
    if plan is None or not plan.stops:
        return ''
    if len(plan.stops) != 1 or plan.stops[0].site_id != site.site_id:
        raise ValueError('Expected one concrete Site action')
    event = plan.stops[0]
    charge = event.charged_kwh > ENERGY_TOL
    scheduled = (schedule is not None and event.scheduled_start_s is not None
                 and schedule.supports(site)
                 and schedule.window_start_s - TIME_TOL <= event.scheduled_start_s
                 <= schedule.window_end_s + TIME_TOL)
    return ('C' if charge else '') + ('S' if scheduled else '')


def flat_actions(trip, sites, travel, ev, curve, schedule, config):
    """Record the accepted routine's best plan per Site, including zero-stop.

    Serial instrumentation only: wrapper returns each original object unchanged.
    Keeping the first equal key preserves accepted stable schedule-start ties.
    The accepted best_one_stop still computes the overall legacy argmin itself.
    """
    recorded = {}
    original = evaluation.assemble_plan

    def observe(*args, **kwargs):
        plan = original(*args, **kwargs)
        key = plan.stops[0].site_id if plan.stops else 'zero'
        if key not in recorded or evaluation.plan_key(plan) < evaluation.plan_key(recorded[key]):
            recorded[key] = plan
        return plan

    with patch.object(evaluation, 'assemble_plan', observe):
        legacy = evaluation.best_one_stop(trip, sites, travel, ev, curve, schedule, config)
    return legacy, recorded


def best(plans):
    return min(plans, key=evaluation.plan_key, default=None)


def action_id(plan):
    return None if plan is None else plan.stops[0].site_id if plan.stops else 'zero'


def equal_value(a, b):
    if a is None or b is None:
        return a is b
    return round(a.generalized_cost_s, 7) == round(b.generalized_cost_s, 7)


def require_h0(summary):
    if (summary.get('cases_evaluated') != 480 or summary.get('cost_mismatches') != 0
            or not summary.get('passed')):
        raise RuntimeError('H0 failed/incomplete; hierarchy construction prohibited')
