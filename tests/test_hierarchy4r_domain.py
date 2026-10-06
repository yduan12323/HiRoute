from dataclasses import replace, asdict
from types import SimpleNamespace
import json
import pytest
from hierarchy4r.domain import effects, flat_actions, equal_value, require_h0, ROLES, ENERGY_TOL
from stopplan4r.models import (StopSite, LocalSupport, EVModel, PiecewiseChargingCurve,
                              PlannerConfig, ScheduledStop, Trip, TravelLeg)


def fixture(energy=45.6, schedule=None, charger=True):
    site = StopSite('4r:node/1', 'node', 1, 0, 0, 1,
                    frozenset({'charge'} if charger else {'parking'}), LocalSupport(meal_count=1))
    class Travel:
        def leg(self, a, b):
            return TravelLeg(100 if (a,b) != (0,2) else 200, 10000 if (a,b) != (0,2) else 20000)
    trip = Trip(0, 2, energy, mobility_budget_s=300)
    args = (trip, [site], Travel(), EVModel(), PiecewiseChargingCurve(), schedule, PlannerConfig())
    legacy, plans = flat_actions(*args)
    return site, legacy, plans, args


@pytest.mark.parametrize('energy,scheduled,expected', [(45.6,False,''),(8,False,'C'),(45.6,True,'S'),(8,True,'CS')])
def test_actual_effect_roles(energy, scheduled, expected):
    schedule = ScheduledStop(0, 1000) if scheduled else None
    site, _, plans, _ = fixture(energy, schedule)
    assert effects(plans[site.site_id], site, schedule) == expected


def test_zero_is_separate_and_effect_free_noncharger_excluded():
    site, legacy, plans, _ = fixture(charger=False)
    assert set(plans) == {'zero', site.site_id}
    assert legacy is plans['zero']
    assert not effects(plans[site.site_id], site, None)
    assert not plans['zero'].stops and len(plans[site.site_id].stops) == 1


def test_capabilities_do_not_assign_cs_or_mutate_static_site():
    site, _, plans, _ = fixture(8)
    before = repr(asdict(site))
    role = effects(plans[site.site_id], site, None)
    assert role == 'C' and sum(role == x for x in ROLES) == 1
    assert repr(asdict(site)) == before
    assert set(ROLES) == {'C','S','CS'}


@pytest.mark.parametrize('charge,expected', [(0,''),(ENERGY_TOL,''),(ENERGY_TOL*1.001,'C')])
def test_charge_effect_boundary(charge, expected):
    site, _, plans, _ = fixture()
    p = plans[site.site_id]
    p = replace(p, stops=(replace(p.stops[0], charged_kwh=charge),))
    assert effects(p,site,None) == expected


def test_value_gate_ignores_identity_only_ties_and_detects_strict_gap():
    site, _, plans, _ = fixture()
    p = plans[site.site_id]
    tie = replace(p, stops=(replace(p.stops[0],site_id='4r:node/2'),))
    assert equal_value(p,tie)
    assert equal_value(p,replace(tie,generalized_cost_s=p.generalized_cost_s+1e-9))
    assert not equal_value(p,replace(tie,generalized_cost_s=p.generalized_cost_s+1e-5))
    assert not equal_value(p,None)


@pytest.mark.parametrize('summary',[{}, {'cases_evaluated':480,'cost_mismatches':1,'passed':False},
                                    {'cases_evaluated':479,'cost_mismatches':0,'passed':True}])
def test_h0_failure_blocks_construction(summary):
    with pytest.raises(RuntimeError,match='construction prohibited'):
        require_h0(summary)


def test_full_h0_is_required():
    require_h0({'cases_evaluated':480,'cost_mismatches':0,'passed':True})
