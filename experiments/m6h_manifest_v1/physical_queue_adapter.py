"""Trusted physical command/admission callbacks for the fixed 30-domain queue."""
from pathlib import Path
import hashlib
import json
import secrets
import sys
from .contract import canonical, plan
from . import physical
from .physical_inputs import require_root_freeze, validate_manifest_contract, validate_input_failure
from .supervisor import PhaseBudget


def validate_manifest_grid(declaration, manifests, selection=None, *, recovery_admission=None):
    """Pure whole-grid binding including immutable generation failure records."""
    if canonical(declaration)!=canonical(plan(6)):
        raise ValueError('Real M6-H requires the exact frozen six-group declaration')
    if type(manifests) is not dict or set(manifests)!={d['id'] for d in declaration['domains']}:
        raise ValueError('Exactly thirty fixed domain identities required')
    if selection is not None:
        if (type(selection) is not dict or selection.get('schema')!='hiroute.m6h.od_selection.v1' or
            selection.get('status')!='SELECTED' or type(selection.get('selected_group_count')) is not int or
            selection['selected_group_count']!=6 or len(selection.get('od',[]))!=6 or selection.get('no_replacement') is not True):
            raise ValueError('Authenticated selection must contain exactly six fixed groups')
        from experiments.m6h_selection_v1.rules import group,groups_near,endpoint,RULE_VERSION
        if recovery_admission is None:
            if selection.get('rule_version')!=RULE_VERSION:raise ValueError('Frozen strict selection rule version differs')
        else:
            if (selection.get('rule_version')!='hiroute.m6h.selection_rules.disclosed_recovery.v1' or
                selection.get('recovery_admission_sha256')!=physical.base.digest(recovery_admission) or
                selection.get('exposure_registry_sha256')!=recovery_admission.get('registry_sha256') or
                selection.get('strict_independent_holdout_claim') is not False or
                selection.get('exposure_mode')!='disclosed_incomplete_recovery' or
                selection.get('generalization_scope')!='new_map_correctness_and_performance_validation_with_incomplete_history'):
                raise ValueError('Recovered selection admission/scope differs')
        for index,od in enumerate(selection['od']):
            for key in ('origin','destination'):
                normalized=endpoint(od[key])
                if normalized['access_node'] is None or canonical(normalized)!=canonical(od[key]):raise ValueError('Canonical selected endpoint required')
            g=group(od['origin'],od['destination'])
            if max(abs(g[0][0]-g[1][0]),abs(g[0][1]-g[1][1]))<=1:raise ValueError('Selected OD endpoint cells are neighbors')
            if (od.get('od_id')!=f'HOD{index:02d}' or od.get('geographic_group')!=[list(c) for c in group(od['origin'],od['destination'])] or
                od.get('origin_anchor')!=od['origin']['access_node'] or od.get('destination_anchor')!=od['destination']['access_node'] or
                od.get('origin_site')!=od['origin']['site_id'] or od.get('destination_site')!=od['destination']['site_id']):
                raise ValueError('Selection endpoint/group identities differ')
            anchors={od['origin_anchor'],od['destination_anchor']};sites={od['origin_site'],od['destination_site']}
            if len(anchors)!=2 or len(sites)!=2:raise ValueError('Selected OD repeats endpoint anchor or Site')
            for prior in selection['od'][:index]:
                if anchors & {prior['origin_anchor'],prior['destination_anchor']} or sites & {prior['origin_site'],prior['destination_site']}:
                    raise ValueError('Selected OD groups share endpoint anchor or Site')
                if groups_near(group(od['origin'],od['destination']),group(prior['origin'],prior['destination'])):
                    raise ValueError('Selected OD groups overlap under frozen grouping policy')
    common_fields=('selection_sha256','protocol_sha256','source','compiler','inputs','repo','input_directory')
    first=None;groups={};seen=set()
    for ordinal,d in enumerate(declaration['domains']):
        raw=manifests[d['id']];failed=raw.get('status')=='FAILED_INPUT'
        m=validate_input_failure(raw,d,ordinal) if failed else validate_manifest_contract(raw)
        if failed and selection is None:raise ValueError('Input failure requires authenticated selected OD identity')
        if (m['domain_ordinal']!=ordinal or m['candidate_count']!=d['candidate_count'] or m['method_order']!=d['method_order']):
            raise ValueError('Manifest differs from fixed group/SOC/N/ordinal slot')
        if selection is not None:
            if m['selection_sha256']!=physical.base.digest(selection):raise ValueError('Domain selection hash differs from authenticated document')
            od=selection['od'][d['group_slot']]
            if m['case_id']!=od['od_id']+'_energy_and_scheduled_soc'+d['soc'].replace('/','_'):
                raise ValueError('Case differs from authenticated selection slot')
        if not failed:
            q=m['case_binding']['original_binding']['query']
            if q['initial_energy_kwh']!=('18' if d['soc']=='3/10' else '228/5'):
                raise ValueError('Fixed SOC differs')
            if selection is not None and (q['origin']!=f"road:{od['origin_anchor']}" or q['destination']!=f"road:{od['destination_anchor']}"):
                raise ValueError('Query OD differs from authenticated selected OD')
        if first is None:first=m
        if recovery_admission is not None:
            expected_graph={k+'_sha256':m['inputs'][k+'.parquet']['sha256'] for k in ('nodes','edges')}
            if selection is None or selection.get('graph_file_identity')!=expected_graph:
                raise ValueError('Recovered selection graph identity differs')
        if any(canonical(m[k])!=canonical(first[k]) for k in common_fields):
            raise ValueError('Grid source/protocol/selection/runtime/input identity differs')
        groups.setdefault(d['group_slot'],{})[(d['candidate_count'],d['soc'])]=m
    for rows in groups.values():
        pool_reasons={'INSUFFICIENT_CAPABLE_SITES','INSUFFICIENT_CAPABILITY_AT_FIRST_RADIUS','CAPABILITY_EXHAUSTED'}
        failures=[m['reason_code'] for m in rows.values() if m['status']=='FAILED_INPUT' and m['reason_code'] in pool_reasons]
        if failures and any(m['status']!='FAILED_INPUT' or m['reason_code']!=failures[0] for m in rows.values()):
            raise ValueError('A whole-pool failure must retain all five OD domains with the same reason')
        valid={key:m for key,m in rows.items() if m['status']!='FAILED_INPUT'}
        if not valid:continue
        q=next(iter(valid.values()))['case_binding']['original_binding']['query']
        pair=tuple(sorted((q['origin'],q['destination'])))
        if pair in seen:raise ValueError('Repeated/reversed OD is not independent')
        seen.add(pair)
        for (n,soc),m in valid.items():
            other=m['case_binding']['original_binding']['query']
            for key in ('origin','destination','schedule','hierarchy_sha256'):
                if canonical(other[key])!=canonical(q[key]):raise ValueError('OD or physical schedule changed across same group')
            for (other_n,other_soc),peer in valid.items():
                if soc==other_soc and m['case_id']!=peer['case_id']:raise ValueError('Query identity changed across candidate sizes')
                if n<=other_n and canonical(m['case_binding']['original_pool_prefix'])!=canonical(peer['case_binding']['original_pool_prefix'][:n]):
                    raise ValueError('Candidates are not immutable nested original prefixes across N/SOC')
    return manifests


class PhysicalQueueAdapter:
    """Constructor authenticates every manifest before any worker can launch.

    `bindings` maps fixed slot IDs to {path,sha256}. Root-owned freezing must also
    authenticate the selection/exposure registry behind the common selection hash.
    """
    def __init__(self,declaration,bindings,*,selection_binding,recovery_admission=None):
        active=require_root_freeze()
        if active is not None and recovery_admission!=active['recovery_admission']:
            raise ValueError('Queue requires exact active recovery admission')
        if type(bindings) is not dict or set(bindings)!={d['id'] for d in plan(6)['domains']}:
            raise ValueError('Complete fixed manifest bindings required')
        if type(selection_binding) is not dict or set(selection_binding)!={'path','sha256'}:raise ValueError('Bound selection document required')
        selection_raw=Path(selection_binding['path']).read_bytes()
        if hashlib.sha256(selection_raw).hexdigest()!=selection_binding['sha256']:raise ValueError('Selection document changed')
        self.selection=json.loads(selection_raw)
        if selection_raw!=canonical(self.selection):raise ValueError('Canonical selection encoding required')
        self.selection_binding=dict(selection_binding)
        if canonical(declaration)!=canonical(plan(6)):raise ValueError('Exact six-group declaration required')
        self.domains={d['id']:(ordinal,d) for ordinal,d in enumerate(declaration['domains'])}
        self.bindings={};self.manifests={}
        for key,value in bindings.items():
            if type(value) is not dict or set(value)!={'path','sha256'}:raise ValueError('Manifest binding schema differs')
            self.bindings[key]=dict(value)
            self.manifests[key]=self._load_record(value,key)
            if self.manifests[key]['selection_sha256']!=selection_binding['sha256']:raise ValueError('Domain belongs to another selected slate')
        validate_manifest_grid(declaration,self.manifests,self.selection,recovery_admission=recovery_admission)

    def _load_record(self,binding,domain_id):
        require_root_freeze()
        raw=Path(binding['path']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=binding['sha256']:raise ValueError('Frozen domain record changed')
        value=json.loads(raw)
        if raw!=canonical(value):raise ValueError('Canonical domain encoding required')
        if value.get('status')!='FAILED_INPUT':return physical._manifest(binding['path'],binding['sha256'])
        ordinal,domain=self.domains[domain_id]
        validate_input_failure(value,domain,ordinal)
        if value['source']!=physical.source_identity(value['repo']):raise ValueError('Failure record executable closure changed')
        physical.base.verify_inputs(value['input_directory'],value['inputs'])
        return value

    def preflight(self,domain,context):
        current,_=self._manifest(domain)
        if current['status']=='FAILED_INPUT':
            return dict(status='FAILED_INPUT',reason_code=current['reason_code'],
                failure_stage='input_generation',frozen_record_sha256=self.bindings[domain['id']]['sha256'])
        return None

    def _manifest(self,domain):
        binding=self.bindings[domain['id']]
        current=self._load_record(binding,domain['id'])
        raw=Path(self.selection_binding['path']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=self.selection_binding['sha256']:raise ValueError('Selection changed after grid admission')
        if canonical(current)!=canonical(self.manifests[domain['id']]):raise ValueError('Manifest changed after grid admission')
        return current,binding

    def command(self,domain,row,context):
        manifest,binding=self._manifest(domain);operation=row['operation'];method=row['method']
        if operation=='ref':
            module='experiments.m6h_manifest_v1.reference';opargs=[]
        else:
            module='experiments.m6h_manifest_v1.physical'
            opargs=['--worker',{'prepare':'prepare','search':'arm','replay':'verify'}[operation]]
        argv=[sys.executable,'-m',module,*opargs,'--manifest',binding['path'],
            '--manifest-sha256',binding['sha256'],'--case',manifest['case_id']]
        common=context['common']
        if operation!='prepare':
            argv+=['--common',common['path'],'--common-sha256',common['sha256']]
        if method:argv+=['--strategy',method]
        if operation=='replay':
            search=context['search'][method];directory=Path(search['directory'])
            argv+=['--search-directory',str(directory),'--search-receipt-sha256',physical.base.file_hash(directory/'receipt.json')]
        command=dict(argv=argv,cwd=manifest['repo'])
        if operation=='search':
            identity=physical.phase_identity(manifest,binding['sha256'],method,common['sha256'])
            command['phase_budget']=PhaseBudget(seconds=1200,identity=dict(identity,nonce=secrets.token_hex(16)))
        return command

    def admit(self,domain,row,context,receipt,directory):
        manifest,binding=self._manifest(domain);case=manifest['case_id'];op=row['operation'];method=row['method']
        if receipt.get('cleanup_verified') is not True:raise ValueError('Owned cleanup not verified')
        if op=='prepare':
            value=physical.load_worker_result(directory,receipt,'prepare',case)
            if value['status']=='seed_exhausted_unknown':
                physical.validate_no_seed(value,case,manifest)
                return dict(status='FAILED_NO_SEED',feasibility='unknown')
            physical.validate_common(value,case,manifest)
            path=Path(directory)/'artifacts/prepared/common.json'
            return dict(status='SUCCESS',common=dict(value=value,path=str(path.resolve()),sha256=physical.base.file_hash(path)))
        common=context['common']
        if op=='search':
            physical.require_search_phase(manifest,binding['sha256'],method,common['sha256'],receipt)
            if receipt['status']=='SUCCESS':physical.load_worker_result(directory,receipt,'arm',case,method)
            return dict(status=receipt['status'],replay_required=True)
        if op=='replay':
            value=physical.load_worker_result(directory,receipt,'verify',case,method)
            search=context['search'][method]
            arm=dict(status=value['status'],receipt=search['receipt'],verification=receipt)
            terminal=physical.admit_method(arm,manifest,binding['sha256'],context['domain_directory'],
                domain['method_order'].index(method),common['value'],common['sha256'],context['prepare_receipt'])
            for prior in context['results'].values():
                if terminal is not None and prior.get('canonical_outcome') is not None and canonical(prior['canonical_outcome'])!=canonical(terminal):
                    raise ValueError('Completed FLAT/HIER exact outcomes contradict')
            return dict(status=value['status'],canonical_outcome=terminal,
                authenticated_completion=arm['authenticated_completion'],operational_admission=arm['operational_admission'],
                standalone_charged_wall_seconds=arm['standalone_charged_wall_seconds'],
                standalone_cost_components=arm['standalone_cost_components'],progress=arm['progress'])
        if op=='ref':
            from . import reference
            return reference.admit_queue_reference(manifest,case,common['value'],receipt,directory,context['results'])
        raise ValueError('Unknown fixed slot operation')
