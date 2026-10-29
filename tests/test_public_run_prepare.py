import hashlib, importlib.util, json, os, sys
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
def _load_tool(name):
    spec=importlib.util.spec_from_file_location(name, ROOT/'tools'/f'{name}.py')
    module=importlib.util.module_from_spec(spec); sys.modules[name]=module; spec.loader.exec_module(module)
    return module
prepare_tool=_load_tool('prepare_run')
run_tool=_load_tool('run_admitted')
make_admission,prepare,system_mem_available_bytes=(prepare_tool.make_admission,prepare_tool.prepare,prepare_tool.system_mem_available_bytes)
run_admitted=run_tool.run_admitted

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def inputs(tmp_path):
    raw=ROOT/'tests/data/tiny-shandong.osm.pbf'
    boundary=ROOT/'tests/data/tiny-shandong-relation.osm'
    routing=ROOT/'configs/shandong-routing.json'
    parameters={
        'RAW_PBF_PATH':str(raw),'RAW_PBF_SHA256':sha(raw),
        'BOUNDARY_PATH':str(boundary),'BOUNDARY_SHA256':sha(boundary),
        'ROUTING_CONFIG_PATH':str(routing),'ROUTING_CONFIG_SHA256':sha(routing),
        'H_REF':3,'CAPACITY_KWH':'90','INITIAL_ENERGY_KWH':'60','MINIMUM_ENERGY_KWH':'0',
        'CONSUMPTION_KWH_PER_M':'1/10000','CHARGING_SEGMENTS':[['0','0'],['90','3600']],
        'CASE_ID':'synthetic-smoke','ORIGIN_OSM_ID':'1','ORIGIN_LON':'117.0000','ORIGIN_LAT':'35.0000',
        'DESTINATION_OSM_ID':'3','DESTINATION_LON':'117.0020','DESTINATION_LAT':'35.0020',
        'CANDIDATE_SITE_IDS':['101','102'],'INITIAL_REMAINING_SCHEDULE':0,
        'WALL_LIMIT_SECONDS':20,'CPU_LIMIT_SECONDS':10,'MEMORY_LIMIT_BYTES':64*1024*1024,
        'HOST_HEADROOM_BYTES':0,'GROWTH_MARGIN_BYTES':0,
    }
    request_template=json.loads((ROOT/'configs/shandong-query.example.json').read_text())
    profile_template=json.loads((ROOT/'configs/resource-profile.example.json').read_text())
    return request_template,profile_template,parameters

def test_parameterized_templates_render_hash_bound_request_and_admission(tmp_path):
    rt,pt,params=inputs(tmp_path)
    request,profile,admission=prepare(rt,pt,params,ROOT,512*1024*1024)
    assert admission['status']=='admitted'
    assert admission['request_sha256']==hashlib.sha256(json.dumps(request,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    assert request['queries'][0]['candidate_site_ids']==['101','102']
    assert request['queries'][0]['initial_remaining_schedule']==0
    assert '${' not in json.dumps([request,profile])

def test_parameterized_template_rejects_changed_source_bytes_and_unknown_placeholders(tmp_path):
    rt,pt,params=inputs(tmp_path); params['RAW_PBF_SHA256']='0'*64
    with pytest.raises(ValueError,match='checksum mismatch'):
        prepare(rt,pt,params,ROOT,512*1024*1024)
    rt,pt,params=inputs(tmp_path); del params['H_REF']
    with pytest.raises(ValueError,match='missing parameter H_REF'):
        prepare(rt,pt,params,ROOT,512*1024*1024)

def test_admission_preflight_fails_closed_when_headroom_is_insufficient():
    profile={'schema':'hiroute.resource_profile.v1','wall_limit_seconds':20,'cpu_limit_seconds':10,
             'memory_limit_bytes':100,'host_headroom_bytes':50,'growth_margin_bytes':25}
    admission=make_admission({'schema':'hiroute.run_request.v1'},profile,174)
    assert admission['status']=='insufficient_headroom'
    assert admission['required_mem_available_bytes']==175

def test_admitted_runner_executes_only_hash_bound_smoke_command(tmp_path):
    rt,pt,params=inputs(tmp_path)
    request,profile,admission=prepare(rt,pt,params,ROOT,system_mem_available_bytes())
    rp=tmp_path/'request.json'; pp=tmp_path/'profile.json'; ap=tmp_path/'admission.json'
    rp.write_text(json.dumps(request,sort_keys=True,separators=(',',':'),ensure_ascii=False))
    pp.write_text(json.dumps(profile,sort_keys=True,separators=(',',':'),ensure_ascii=False))
    ap.write_text(json.dumps(admission,sort_keys=True,separators=(',',':'),ensure_ascii=False))
    receipt=tmp_path/'receipt.json'; stdout=tmp_path/'stdout'; stderr=tmp_path/'stderr'
    rc=run_admitted(rp,pp,ap,receipt,stdout,stderr,[sys.executable,'-c','print("admission-smoke-ok")'],cwd=str(tmp_path))
    assert rc==0 and stdout.read_text().strip()=='admission-smoke-ok'
    assert receipt.is_file()
    with pytest.raises(FileExistsError,match='overwrite'):
        run_admitted(rp,pp,ap,receipt,stdout,stderr,[sys.executable,'-c','raise SystemExit(99)'],cwd=str(tmp_path))
    changed=json.loads(pp.read_text()); changed['memory_limit_bytes']+=1
    pp.write_text(json.dumps(changed,sort_keys=True,separators=(',',':'),ensure_ascii=False))
    with pytest.raises(ValueError,match='profile no longer matches'):
        run_admitted(rp,pp,ap,tmp_path/'second.json',stdout,stderr,[sys.executable,'-c','raise SystemExit(99)'],cwd=str(tmp_path))


def test_documented_cli_flow_renders_request_and_runs_supervised_smoke(tmp_path, monkeypatch):
    rt,pt,params=inputs(tmp_path)
    param_path=tmp_path/'parameters.json'; param_path.write_text(json.dumps(params))
    out=tmp_path/'prepared'
    monkeypatch.setattr(prepare_tool,'system_mem_available_bytes',lambda:512*1024*1024)
    rc=prepare_tool.main(['--request-template',str(ROOT/'configs/shandong-query.example.json'),
        '--profile-template',str(ROOT/'configs/resource-profile.example.json'),
        '--parameters',str(param_path),'--root',str(ROOT),'--output-dir',str(out)])
    assert rc==0
    request=json.loads((out/'request.json').read_text())
    profile=json.loads((out/'resource-profile.json').read_text())
    admission=json.loads((out/'admission.json').read_text())
    assert request['raw_source']['sha256']==params['RAW_PBF_SHA256']
    assert request['queries'][0]['initial_remaining_schedule']==0
    assert admission['status']=='admitted'
    receipt=tmp_path/'cli-receipt.json'; stdout=tmp_path/'cli-stdout'; stderr=tmp_path/'cli-stderr'
    rc=run_tool.main(['--request',str(out/'request.json'),'--profile',str(out/'resource-profile.json'),
        '--admission',str(out/'admission.json'),'--receipt',str(receipt),'--stdout',str(stdout),
        '--stderr',str(stderr),'--',sys.executable,'-c','print("documented-flow-ok")'])
    assert rc==0 and stdout.read_text().strip()=='documented-flow-ok' and receipt.is_file()


def test_admitted_runner_rejects_source_changed_after_admission(tmp_path):
    rt,pt,params=inputs(tmp_path)
    raw_copy=tmp_path/'raw-copy.pbf'; raw_copy.write_bytes(Path(params['RAW_PBF_PATH']).read_bytes())
    params['RAW_PBF_PATH']=str(raw_copy); params['RAW_PBF_SHA256']=sha(raw_copy)
    request,profile,admission=prepare(rt,pt,params,ROOT,system_mem_available_bytes())
    rp=tmp_path/'request.json'; pp=tmp_path/'profile.json'; ap=tmp_path/'admission.json'
    rp.write_text(json.dumps(request,sort_keys=True,separators=(',',':'),ensure_ascii=False))
    pp.write_text(json.dumps(profile,sort_keys=True,separators=(',',':'),ensure_ascii=False))
    ap.write_text(json.dumps(admission,sort_keys=True,separators=(',',':'),ensure_ascii=False))
    raw_copy.write_bytes(raw_copy.read_bytes()+b'changed')
    with pytest.raises(ValueError,match='checksum mismatch'):
        run_admitted(rp,pp,ap,tmp_path/'receipt',tmp_path/'stdout',tmp_path/'stderr',
                     [sys.executable,'-c','raise SystemExit(99)'],cwd=str(tmp_path))
