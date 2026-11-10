"""A tiny physical query through the installed worker subprocess, never real N64."""
import json
from pathlib import Path
import os
from types import SimpleNamespace

import pytest


def test_installed_worker_roundtrip_with_full_n64_profile(tmp_path):
    if os.environ.get('HIROUTE_REQUIRE_NATIVE_ROADS') != '1':
        pytest.skip('native tier supplies the mandatory compiler and Boost dependency')
    from hiroute.execution import pilot
    from hiroute.execution.config import N64_PROFILE
    from hiroute.data.queries import select_domains
    root = Path(__file__).resolve().parents[2]
    cfg = json.loads((root / 'configs/real_scale_dev.json').read_text())
    cfg['selection']['ods'] = [dict(query_id='tiny', origin=dict(lon=0,lat=0), destination=dict(lon=1,lat=0))]
    cfg['selection']['candidate_counts'] = [1]
    cfg['selection']['scenarios'] = ['energy_only']
    cfg['pilot_matrix'] = [dict(N=1,query_ids=['tiny'],scenarios=['energy_only'])]
    cfg['resources']['host_headroom_bytes'] = 1
    cfg['implementation'] = N64_PROFILE
    sites = [dict(site_id='o',lon=0,lat=0,capabilities=[]), dict(site_id='z',lon=1,lat=0,capabilities=[]),
             dict(site_id='c',lon=.5,lat=0,capabilities=['C'])]
    bindings = dict(site_access_nodes={s['site_id']:'road-'+s['site_id'] for s in sites})
    manifest = select_domains(cfg,sites,bindings)
    cp, pp, graph = tmp_path/'config.json', tmp_path/'preflight.json', tmp_path/'graph.tsv'
    cp.write_text(json.dumps(cfg)); pp.write_text(json.dumps(manifest))
    graph.write_text('road-o\troad-c\toc\t1\t1\nroad-c\troad-z\tcz\t1\t1\nroad-o\troad-z\toz\t3\t1\n')
    receipts = tmp_path/'receipts'; receipts.mkdir()
    args = SimpleNamespace(config=cp,preflight=pp,graph_tsv=graph,native_cache=tmp_path/'native',output=tmp_path/'rows.jsonl',
        preflight_only=False,domains='1',queries='tiny',scenarios='energy_only',methods=None,
        diagnostic=False,ablation=False,no_bound=False,solve_limit_seconds=120,development_cpu_s=0,
        cold_load_allowance_s=180,process_memory_gib=8,receipt_directory=str(receipts))
    pilot.main(args)
    rows = [json.loads(line) for line in args.output.read_text().splitlines()]
    assert len(rows)==2
    assert rows[0]['key']==rows[1]['key']==['2','0',0,[]]
    assert rows[0]['seed_key']==rows[1]['seed_key']
    for row in rows:
        assert row['status']=='attained_optimum'
        assert row['implementation']==N64_PROFILE
        assert row['depth_contract']['mode']=='unrestricted'
        assert row['witness']['physical_verified'] is True
        assert row['witness']['independent_key']==row['key']
    assert len(list(receipts.glob('*.supervisor.json')))==2
