import json
from pathlib import Path
from unittest.mock import patch
import pytest
from experiments.m5e2e_v1.common import environment_admission, load, write_new, GIB
from experiments.m5e2e_v1.budget import totals
from experiments.m5e2e_v1.cli import plan


def test_insufficient_headroom_fails_without_lowering_guard():
    report=environment_admission(require_installed=False,available=9*GIB)
    assert report['status']=='BLOCKED_INPUT_OR_ENVIRONMENT'
    assert 'insufficient_10GiB_host_reserve' in report['reasons']
    assert report['host_reserve_bytes']==10*GIB
    assert report['aggregate_memory_hard_limit'] is False


def test_immutable_receipts_and_duplicate_keys(tmp_path):
    p=tmp_path/'receipt.json';write_new(p,dict(x=1))
    with pytest.raises(FileExistsError):write_new(p,dict(x=2))
    assert load(p)==dict(x=1)
    p.write_text('{"x":1,"x":2}')
    with pytest.raises(ValueError):load(p)


def test_unsettled_invocation_stops_continuation():
    with pytest.raises(RuntimeError):totals([dict(kind='start',invocation_id='a')])
    assert totals([dict(kind='start',invocation_id='a'),dict(kind='end',invocation_id='a',cpu_seconds=2,wall_seconds=3,cleanup_verified=True)])==(2,3)


def test_plan_never_opens_holdout_or_merges():
    p=plan()
    assert p['case_ids']==['E01','E02','E03']
    assert p['H_ref']==3 and p['max_candidates']==4
    assert p['holdout'] is False and p['merge'] is False
    assert p['automatic_retries'] is False


def test_uncertain_cleanup_prevents_next_worker():
    with pytest.raises(RuntimeError):
        totals([dict(kind="start",invocation_id="a"),dict(kind="end",invocation_id="a",cleanup_verified=False,cpu_seconds=0,wall_seconds=0)])
