"""Tiny-only primary bound decision, not a replacement lexicographic optimizer."""
import time
import os
import tempfile
from pathlib import Path
from fractions import Fraction
from .exact_physical_adapter import Encoding,Engine,Unknown,q,real,relevant_depth,table_relevant_depth,atomic
from .incumbent_model_certificate import certify


def decide(table,parameters,witness,bound,audit_dir,time_limit_s=8):
    if type(time_limit_s) not in (int,float) or not 0<time_limit_s<=8:
        raise ValueError('tiny-only <=8 second deadline')
    if audit_dir is None:raise ValueError('persistent complete audit required')
    if type(bound) not in (int,Fraction):raise TypeError('exact int/Fraction bound required')
    return _decide(table,parameters,witness,bound,audit_dir,time.monotonic()+time_limit_s,False)


def preflight_audit(audit_dir,check):
    """Fresh output path, durable parent probe; never remove existing evidence."""
    if audit_dir is None:raise ValueError('persistent audit directory required')
    path=Path(audit_dir)
    check()
    if path.exists() or path.is_symlink():raise ValueError('audit output already exists')
    if not path.parent.is_dir():raise ValueError('persistent audit parent missing')
    fd,name=tempfile.mkstemp(prefix='.bound-audit-probe-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(b'bound-audit-probe\n');stream.flush();os.fsync(stream.fileno())
        check()
    finally:Path(name).unlink()
    return path


def decide_real(load_inputs,bound,audit_dir,deadline,extract_witness=False):
    """Admitted-worker API, not an experiment launcher.

    Caller must retain the external 120 CPU/120 wall process-tree envelope,
    resource guards, immutable admission and cumulative accounting. Deadline is
    the caller's absolute end-to-end monotonic deadline, including prior setup.
    The callback loads and verifies inputs and returns table, physics, witness.
    No saved certificate accepted. No runtime or budget admission is bypassed.
    """
    start=time.monotonic()
    metadata=dict(bound=str(bound),checks=[],phases=[],secondary_certified=False,full_key_certified=False)
    try:
        if type(deadline) not in (int,float) or not start<deadline<=start+120:
            raise ValueError('remaining end-to-end deadline must be positive and <=120s')
        if type(bound) not in (int,Fraction):raise TypeError('exact int/Fraction bound required')
        def check():
            if time.monotonic()>=deadline:raise Unknown('end-to-end deadline')
        directory=preflight_audit(audit_dir,check)
        load_start=time.monotonic()
        table,parameters,witness=load_inputs(check)
        check()
        load_elapsed=time.monotonic()-load_start
        result=_decide(table,parameters,witness,bound,directory,deadline,True,extract_witness)
        check()
        result.update(load_wall_s=load_elapsed,end_to_end_wall_s=time.monotonic()-start)
        return result
    except (Unknown,ValueError,TypeError,KeyError,OSError) as exc:
        return dict(status='unknown',reason=str(exc),**metadata)


def _decide(table,parameters,witness,bound,audit_dir,deadline,complete_depth,extract_witness=False):
    metadata=dict(bound=str(bound),checks=[],phases=[],secondary_certified=False,full_key_certified=False)
    try:
        engine=Engine(deadline,audit_dir,120000 if complete_depth else 2000,dag_audit=True)
        metadata.update(checks=engine.audit,phases=engine.phases,complete_depth=complete_depth)
        engine.remaining()
        with engine.phase('bound-model-construction'):
            depth,seed=(table_relevant_depth if complete_depth else relevant_depth)(table,parameters,witness)
            metadata['derived_depth']=depth
            if extract_witness and q(bound)!=seed['key'][0]:raise ValueError('extraction bound must equal freshly replayed incumbent')
            m=Encoding(table,parameters,depth,seed['key'][0],engine.remaining,finite_lookup=True)
            x,y=m.state_copy(engine.remaining),m.state_copy(engine.remaining)
            base=m.G+x['P']+y['P']+y['strict']
        with engine.phase('bound-fresh-certificate'):
            certificate=certify(m,x,y,table,parameters,witness,base,engine.remaining)
            atomic(engine.directory/'incumbent-certificate.json',certificate)
        # Exactly one decision, no Optimize, no bisection, no incumbent fixing.
        model=engine.feasible([*base,x['J']<real(bound)],'strict-primary-bound')
        engine.remaining()
        if model is not None:
            if extract_witness:
                from .strict_bound_witness import extract,publish_verified_result
                roots=[*base,x['J']<real(bound)]
                with engine.phase('strict-bound-witness-extraction'):
                    verified=extract(m,x,y,table,parameters,bound,roots,model,
                                     engine.directory/'candidate.unverified.json',engine.remaining)
                with engine.phase('strict-bound-verified-publication'):
                    receipt=publish_verified_result(engine.directory/'witness.verified.json',verified,engine.remaining)
                engine.remaining()
                return dict(status='attained_improvement',attained_improvement_certified=True,
                            witness=verified['witness'],primary_value=verified['primary_value'],
                            verified_witness_receipt=receipt,optimality_certified=False,**metadata)
            return dict(status='sat_supported_below_bound',attained_improvement_certified=False,**metadata)
        # Original closure plus strict support can prove a lower bound, but
        # equality to the independently replayed attained witness is essential.
        return dict(status=('primary_optimal_only' if q(bound)==seed['key'][0]
                            else 'unsat_below_bound'),
                    primary_certified=q(bound)==seed['key'][0],**metadata)
    except (Unknown,ValueError,TypeError,KeyError,OSError) as exc:
        return dict(status='unknown',reason=str(exc),**metadata)
