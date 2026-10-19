"""Root-pinned, receipt-bound continuation after preselection infrastructure loss.

Per-run totals, timestamps, receipts and admission documents remain external.
Only the authoritative outer cumulative account is carried, never child totals.
"""
import hashlib
import json
import math
from pathlib import Path
from datetime import datetime,timezone
from .contract import canonical
from .resources import ContinuationBudget, conservative_transition_debit
from .recovery_protocol import DEADLINE

SCHEMA='hiroute.m6h.parent_receipt_continuation.v1'


def _stamp(value):
    stamp=datetime.fromisoformat(value.replace('Z','+00:00'))
    if stamp.tzinfo is None or stamp.utcoffset().total_seconds()!=0:
        raise ValueError('Explicit UTC continuation timestamp required')
    return stamp.timestamp()


def _bound(binding,limit=4*2**20):
    if type(binding) is not dict or set(binding)!={'path','sha256'}:
        raise ValueError('Exact receipt byte binding required')
    p=Path(binding['path'])
    if not p.is_absolute() or p.is_symlink() or not p.is_file() or not 0<p.stat().st_size<=limit:
        raise ValueError('Bounded absolute regular receipt required')
    raw=p.read_bytes()
    if len(raw)>limit or hashlib.sha256(raw).hexdigest()!=binding['sha256']:
        raise ValueError('Receipt/admission byte identity differs')
    def unique(pairs):
        obj={}
        for key,value in pairs:
            if key in obj:raise ValueError('Duplicate continuation JSON key')
            obj[key]=value
        return obj
    value=json.loads(raw,object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite continuation JSON')))
    return value,p


def verify(binding, *, expected_admission_sha256):
    if expected_admission_sha256 is None:
        raise PermissionError('Continuation admission awaits root source review')
    if not isinstance(binding,dict) or binding.get('sha256')!=expected_admission_sha256:
        raise ValueError('Continuation admission is not root-pinned')
    a,path=_bound(binding,128*1024)
    if path.read_bytes()!=canonical(a):raise ValueError('Canonical continuation admission required')
    sites_failure=a.get('failure_scope')=='preselection_sites_infrastructure'
    extra={'parent_sites_ledger','parent_completed_receipts'} if sites_failure else set()
    if set(a)!=extra|{'schema','parent_waited_receipt','parent_owner_receipt','parent_graph_progress',
                'active_since_utc','cpu_capacity','observed_numerical_slots','od_selection_started','failure_scope'}:
        raise ValueError('Complete continuation admission required')
    if (a['schema']!=SCHEMA or type(a['cpu_capacity']) is not int or a['cpu_capacity']!=9 or
        type(a['observed_numerical_slots']) is not int or a['observed_numerical_slots']!=0 or
        a['od_selection_started'] is not False or a['failure_scope'] not in ('preselection_graph_infrastructure','preselection_sites_infrastructure')):
        raise ValueError('Continuation cannot replace numerical outcomes or broaden scope')
    start=_stamp(a['active_since_utc'])
    if start>=_stamp(DEADLINE):raise ValueError('Continuation begins after original deadline')
    parent,parent_path=_bound(a['parent_waited_receipt'])
    if (parent.get('schema')!='hiroute.m6h.disclosed_waited_round.v1' or
        parent.get('status')!='FAILED' or parent.get('cleanup_verified') is not True or
        parent.get('accounting')!='authoritative_outer_self_plus_waited_children_once_no_nested_sum'):
        raise ValueError('Authoritative failed cleaned-up outer receipt required')
    protocol=parent.get('protocol',{})
    if protocol.get('cpu_limit_seconds')!=144000 or protocol.get('absolute_deadline_utc')!=DEADLINE:
        raise ValueError('Original global cap/deadline differs')
    used=parent.get('cumulative_measured_plus_conservative_carry',{}).get('cpu_seconds')
    if type(used) not in (int,float) or not math.isfinite(used) or not 0<=used<=144000:
        raise ValueError('Finite cumulative outer CPU debit required')
    owner,owner_path=_bound(a['parent_owner_receipt'])
    root=parent_path.parent
    if owner_path!=root/'owner/receipt.json':raise ValueError('Owner receipt belongs to another round')
    if (owner.get('schema')!='hiroute.mechanism_recovery.supervisor.v1' or
        owner.get('status')!='FAILED' or owner.get('complete') is not True or
        owner.get('cleanup_verified') is not True or owner.get('reason')!='sampled_tree_rss_limit'):
        raise ValueError('Reviewed preselection memory-stop receipt required')
    progress,progress_path=_bound(a['parent_graph_progress'])
    round_root=root/'owner/artifacts/round'
    if progress_path!=round_root/'preprocessing/graph/artifacts/graph_progress.json':
        raise ValueError('Progress belongs to another round/stage')
    if progress.get('schema')!='hiroute.graph_progress.v1' or not isinstance(progress.get('stage'),str):
        raise ValueError('Durable graph-stage evidence required')
    if sites_failure:
        if progress.get('stage')!='graph_files_written':
            raise ValueError('Site continuation requires completed graph evidence')
        completed=a['parent_completed_receipts']
        if type(completed) is not dict or set(completed)!={'source','graph','inventory'}:
            raise ValueError('Exact successful predecessor receipts required')
        for phase,binding in completed.items():
            receipt,receipt_path=_bound(binding)
            if receipt_path!=round_root/'preprocessing'/phase/'receipt.json':
                raise ValueError('Predecessor receipt belongs to another stage')
            result=(receipt.get('worker_receipt') or {}).get('result',{})
            if (receipt.get('schema')!='hiroute.mechanism_recovery.supervisor.v1' or
                receipt.get('status')!='SUCCESS' or receipt.get('complete') is not True or
                receipt.get('cleanup_verified') is not True or receipt.get('reason')!='success' or
                result.get('phase')!=phase or result.get('synthetic') is not False):
                raise ValueError('Successful real predecessor receipt required')
        ledger,ledger_path=_bound(a['parent_sites_ledger'])
        argv=ledger.get('argv',[])
        if (ledger_path!=round_root/'preprocessing/sites/ledger.json' or
            ledger.get('schema')!='hiroute.mechanism_recovery.supervisor.v1' or
            ledger.get('status')!='UNKNOWN' or ledger.get('complete') is not False or
            '--phase' not in argv or argv[argv.index('--phase')+1:argv.index('--phase')+2]!=['sites'] or
            (round_root/'preprocessing/sites/receipt.json').exists()):
            raise ValueError('Interrupted Site stage evidence required')
    if any((round_root/n).exists() for n in ('generation','generation-job.json','queue')):
        raise ValueError('Prior attempt reached selection or numerical generation')
    return dict(schema=SCHEMA,parent_waited_receipt=dict(a['parent_waited_receipt']),
        carried_cpu_seconds=used,active_since_utc=a['active_since_utc'],cpu_capacity=a['cpu_capacity'],
        absolute_deadline_utc=DEADLINE,observed_numerical_slots=0,od_selection_started=False)


def debit_at(lineage,transition_utc):
    return conservative_transition_debit(prior_debit=lineage['carried_cpu_seconds'],
        active_since_utc=lineage['active_since_utc'],transition_utc=transition_utc,
        cpu_capacity=lineage['cpu_capacity'])


def budget(lineage, *, transition_utc):
    return ContinuationBudget(carried_cpu_seconds=debit_at(lineage,transition_utc),
        deadline_utc=DEADLINE,transition_utc=transition_utc,
        transition_cpu_capacity=lineage['cpu_capacity'])
