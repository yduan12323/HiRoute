"""Acceptance checks on the complete 4R static/30-OD development evidence."""
import json

import numpy as np
import pandas as pd

from _common import ROOT, sha256
from stopplan4r.models import EVModel
from stopplan4r.sites import validate_static_table

OUT = ROOT / 'results/milestone_4r'


def test_4r_static_artifacts_reproducibility_and_provenance():
    metadata = json.loads((OUT / 'site_build.json').read_text())
    sites = pd.read_parquet(OUT / 'stop_sites.parquet')
    support = pd.read_parquet(OUT / 'local_support.parquet')
    validate_static_table(sites)
    assert len(sites) == metadata['site_count']
    assert sites.site_id.nunique() == len(sites)
    assert metadata['byte_identical_reordered_rebuild']
    for artifact in ['stop_sites', 'local_support']:
        assert sha256(OUT / (artifact + '.parquet')) == sha256(OUT / (artifact + '_rebuild.parquet'))
    assert set(support.radius_m) == {250, 500, 750}
    assert len(support) == 3 * len(sites)
    for name, digest in metadata['inputs'].items():
        assert sha256(ROOT / name) == digest
    for name, digest in metadata['outputs'].items():
        assert sha256(OUT / name) == digest


def test_4r_all_development_cases_energy_cost_and_vehicle_anchors():
    metadata = json.loads((OUT / 'diagnostic.json').read_text())
    cfg = metadata['configuration']
    ev = EVModel(**cfg['ev'])
    plans = pd.read_parquet(OUT / 'one_stop_diagnostics.parquet')
    sites = pd.read_parquet(OUT / 'stop_sites.parquet').set_index('site_id')
    envelopes = pd.read_parquet(OUT / 'envelope_site_counts.parquet')
    assert metadata['development_od_count'] == 30
    assert len(plans) == 30 * 4 * 2 * 2
    assert set(plans.instance_id) == set(range(30))
    assert len(envelopes) == 30 * 4
    assert plans.groupby(['instance_id', 'ratio', 'initial_soc', 'scenario']).size().eq(1).all()
    feasible = plans[plans.feasible]
    assert feasible.stop_count.isin([0, 1]).all()
    assert (feasible.terminal_energy_kwh >= ev.terminal_floor - 1e-6).all()
    expected = feasible.clock_s + cfg['planner']['lambda_stop_s'] * feasible.stop_count + feasible.requirement_penalty_s
    expected += cfg['planner']['distance_penalty_s_per_km'] * feasible.distance_m / 1000
    assert np.allclose(feasible.generalized_cost_s, expected)
    scheduled = feasible[feasible.scenario.eq('energy_and_scheduled')]
    assert scheduled.stop_count.eq(1).all()
    assert (scheduled.scheduled_activity_start_s >= scheduled.window_start_s - 1e-6).all()
    assert (scheduled.scheduled_activity_start_s <= scheduled.window_end_s + 1e-6).all()
    for p in feasible[feasible.stop_count.eq(1)].itertuples():
        s = sites.loc[p.site_id]
        assert s.attachment_status == 'attached'
        assert set(s.transport_capabilities) & {'charge', 'parking', 'rest', 'services'}
        if p.charged_kwh > 1e-8:
            assert 'charge' in s.transport_capabilities
            assert p.terminal_energy_kwh == __import__('pytest').approx(ev.terminal_floor, abs=1e-6)
        if p.scenario == 'energy_and_scheduled':
            assert s.meal_count >= cfg['support']['meal_threshold']
    for name, digest in metadata['inputs'].items():
        assert sha256(ROOT / name) == digest
    for name, digest in metadata['outputs'].items():
        assert sha256(OUT / name) == digest
    assert all(c['passed'] for c in metadata['independent_route_checks'])
    for _, group in envelopes.groupby('instance_id'):
        assert group.sort_values('ratio').site_count.diff().dropna().ge(0).all()


def test_4r_all_protected_files_unchanged():
    before = json.loads((OUT / 'preservation_before.json').read_text())
    for name, record in before['files'].items():
        assert (ROOT / name).stat().st_size == record['size_bytes']
        assert sha256(ROOT / name) == record['sha256'], name
