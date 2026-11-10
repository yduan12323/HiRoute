"""Separate verification of a sealed candidate; never solve or revise old status."""
import hashlib,json,re
from pathlib import Path
from fractions import Fraction as F
import z3
from .exact_physical_adapter import real,replay,validate
from .strict_bound_witness import constants,certificate,publish_verified_result
from .dag_formula_export import export_dag,verify_export
from .provenance import source


def file_hash(path,check):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):check();h.update(block)
    check();return h.hexdigest()


def strict_json(path,expected,check):
    path=Path(path)
    if path.stat().st_size>1024*1024:raise ValueError('metadata quota')
    raw=path.read_bytes();check()
    if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('sealed file changed')
    def unique(pairs):
        result={}
        for k,v in pairs:
            if k in result:raise ValueError('duplicate JSON field')
            result[k]=v
        return result
    return json.loads(raw,object_pairs_hook=unique)


def groups(rows):
    result={}
    for name,sort,value in rows:
        match=re.fullmatch(r'(.+)!([0-9]+)',name)
        if match is None:raise ValueError('unsupported symbol spelling')
        result.setdefault((match[1],sort),[]).append((int(match[2]),value))
    return {k:[v for _,v in sorted(vs)] for k,vs in result.items()}


def verify_candidate(origin,expected,out,m,x,y,table,parameters,incumbent,check=lambda:None):
    """Expected hashes/source identities come from a separately sealed admission.

    Symbol pairing is only a proposal: exact regenerated audit equality after
    renaming is mandatory. No parser, solver, alpha-equivalence assumption or
    silent compatibility fallback is used.
    """
    origin,out=Path(origin),Path(out);check()
    if source()!=expected['verifier_source'] or expected['verifier_source'].get('dirty') is not False:raise ValueError('verifier source changed')
    if out.exists():raise ValueError('fresh verification output required')
    out.mkdir()
    ad=strict_json(origin/'consumer-admission.json',expected['admission_sha256'],check)
    if ad['consumer_source']!=expected['original_source'] or ad['producer_files']!=expected['producer_files']:raise ValueError('original source/input provenance changed')
    audit=origin/'audit-root/SMT/0001.dag.smt2'
    verified=verify_export(audit,check)
    if verified['payload_sha256']!=expected['audit_payload_sha256'] or file_hash(audit,check)!=expected['audit_sha256']:raise ValueError('original formula changed')
    raw=strict_json(origin/'audit-root/SMT/candidate.unverified.json',expected['candidate_sha256'],check)
    if set(raw)!={'status','payload','payload_sha256'} or raw['status']!='UNVERIFIED_CANDIDATE':raise ValueError('unverified candidate contract')
    p=raw['payload'];encoded=json.dumps(p,sort_keys=True,separators=(',',':')).encode()
    if hashlib.sha256(encoded).hexdigest()!=raw['payload_sha256']:raise ValueError('candidate payload changed')
    if set(p)!={'bound','table_sha256','physics_sha256','assignment'}:raise ValueError('candidate fields')
    physics=validate(table,parameters)
    upper=replay(table,parameters,incumbent['plan'],incumbent['charges'],incumbent.get('initial_wait',0))['key'][0]
    if p['bound']!=ad['bound'] or F(p['bound'])!=upper or upper!=m.upper:raise ValueError('original attained upper changed')
    if p['table_sha256']!=table.payload_sha256 or p['physics_sha256']!=physics.sha256:raise ValueError('input/physics changed')
    roots=m.G+x['P']+y['P']+y['strict']+[x['J']<real(upper)]
    symbols=constants(roots,check);current=groups([(str(s.decl().name()),str(s.sort()),s) for s in symbols])
    rows=p['assignment'];seen=set();parsed=[]
    if type(rows) is not list:raise ValueError('assignment list')
    for row in rows:
        check()
        if type(row) is not dict or set(row)!={'name','sort','value'} or any(type(row[k]) is not str for k in row):raise ValueError('typed assignment row')
        name,sort,value=row['name'],row['sort'],row['value']
        if name in seen:raise ValueError('duplicate symbol')
        seen.add(name)
        if sort=='Int' and re.fullmatch(r'-?(0|[1-9][0-9]*)',value):v=int(value)
        elif sort=='Real' and re.fullmatch(r'-?(0|[1-9][0-9]*)(/[1-9][0-9]*)?',value):v=F(value)
        elif sort=='Bool' and value in ('True','False'):v=value=='True'
        else:raise ValueError('noncanonical typed value')
        parsed.append((name,sort,(name,v)))
    old=groups(parsed)
    if set(old)!=set(current) or any(len(old[k])!=len(current[k]) for k in current):raise ValueError('missing/foreign/ill-typed binding')
    rename=[];bindings=[]
    for key in current:
        for s,(name,value) in zip(current[key],old[key]):
            rename.append((s,z3.Const(name,s.sort())));bindings.append((s,value))
    renamed=[z3.substitute(root,*rename) for root in roots];check()
    rebuilt=out/'reconstructed.dag.smt2';metadata=export_dag(renamed,rebuilt,check)
    if metadata['payload_sha256']!=expected['audit_payload_sha256'] or file_hash(rebuilt,check)!=expected['audit_sha256']:raise ValueError('reconstructed original formula mismatch')
    result=certificate(m,x,y,table,parameters,upper,roots,bindings,check)
    check();result.update(verification_scope='SEPARATE_POST_RUN_VERIFICATION',original_run_status='UNKNOWN',original_run_completed_in_budget=False,
                          original_source=expected['original_source'],verifier_source=expected['verifier_source'],candidate_sha256=expected['candidate_sha256'],audit_sha256=expected['audit_sha256'])
    receipt=publish_verified_result(out/'separate-witness.verified.json',result,check)
    check();return dict(result=result,receipt=receipt)
