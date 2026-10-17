"""Experimental production integration; separate verifier provider, no OPEN resume."""
from fractions import Fraction as R
import json

from timecut5.bounded import _replay_problem
from timecut5.durable_incumbent import AtomicIncumbentStore,load_verified
from timecut5.feasible_incumbent import canonical,sha
from timecut5.probe import Event,State,Witness
from timecut5.real_adapter import TableFreeRealProblem,site_catalog_digest
from timecut5.sparse_seed import replay_sparse_seed


def seed_witness(query,catalog,sequence,charges):
    """Reconstruct exact events only after independent selected-edge replay."""
    replay=replay_sparse_seed(query,catalog,sequence,charges)
    time=R(query['start_time_s']);energy=R(query['initial_energy_kwh'])
    anchor=query['origin'];remaining=query.get('initial_remaining_schedule',int(query.get('schedule') is not None))
    events=[Event('initial',anchor,time,time,energy,energy)]
    initial=energy;charge_iter=iter(map(R,charges));total=R(0)
    for site,effect in sequence:
        target=catalog.sites[site].anchor_id
        leg=catalog.leg(anchor,target)
        nt=time+leg.time;ne=energy-leg.actual_length*R(query['consumption_kwh_per_m'])
        events.append(Event('D',target,time,nt,energy,ne));time,energy,anchor=nt,ne,target
        release=time+R(query['overhead_s']);done=[release];ne=energy
        if effect in ('C','CS'):
            amount=next(charge_iter);total+=amount;ne+=amount
            duration=sum((max(R(0),min(ne,R(hi))-max(energy,R(lo)))*R(slope)
                for lo,hi,slope,_ in query['charging_segments']),R(0))
            done.append(release+duration)
        if effect in ('S','CS'):
            schedule=query['schedule'];done.append(max(release,R(schedule['a']))+R(schedule['D']));remaining=0
        nt=max(done);events.append(Event(effect,site,time,nt,energy,ne));time,energy=nt,ne
    if anchor!=query['destination']:
        leg=catalog.leg(anchor,query['destination']);nt=time+leg.time;ne=energy-leg.actual_length*R(query['consumption_kwh_per_m'])
        events.append(Event('D',query['destination'],time,nt,energy,ne));time,energy=nt,ne
    witness=Witness(time,energy,total-energy,tuple(map(tuple,sequence)),State(query['destination'],remaining,len(sequence)),tuple(events))
    problem=TableFreeRealProblem(query,catalog.sites,catalog.provider,origin_anchor=query['origin'],destination_anchor=query['destination'],site_catalog_sha256=catalog.site_catalog_sha256)
    if _replay_problem(problem,witness)!=replay['lex_key']:
        raise ValueError('Reconstructed initial witness differs from independent sparse replay')
    return witness,replay['lex_key'],replay['edge_witnesses']


class SparseDurableSession:
    """Bind a reviewed policy and seed, then persist independently verified updates.

    source_supplier must rehash current source inputs and implementation closure,
    including nodes/edges/router keys matching the independent provider. Its
    values are not copied from the witness file. The separate verifier provider
    may reuse only its own source-bound selected-leg cache. All work is sync.
    """
    def __init__(self,path,*,method,exact_query,admission,search_provider,verifier_catalog,source_supplier,policy_check):
        if verifier_catalog.provider is search_provider or verifier_catalog.provider.router is search_provider.router:
            raise ValueError('Independent verifier provider and router required')
        expected=dict(json.loads(admission.incumbent.query_bytes),H_ref=admission.incumbent.max_depth)
        if canonical(exact_query)!=canonical(expected) or admission.incumbent.domain_sha256!=verifier_catalog.domain_sha256:
            raise ValueError('Effective admitted query or sparse domain differs')
        self.query=json.loads(canonical(exact_query));self.catalog=verifier_catalog
        self.policy_check=policy_check;self.source_supplier=source_supplier
        self.source=dict(source_supplier());self.policy=bytes(admission.policy_bytes)
        for key,digest in verifier_catalog.provider.source_sha256.items():
            if self.source.get(key)!=digest:raise ValueError('Verifier source binding differs')
        self.domain=self.domain_digest()
        def fresh_problem():
            return TableFreeRealProblem(self.query,self.catalog.sites,self.catalog.provider,
                origin_anchor=self.query['origin'],destination_anchor=self.query['destination'],
                site_catalog_sha256=self.catalog.site_catalog_sha256)
        self.problem_factory=fresh_problem
        self.store=AtomicIncumbentStore(path,method=method,problem_factory=fresh_problem,binding_supplier=self.bindings)
        initial=json.loads(admission.incumbent.witness_bytes)
        witness,key,edges=seed_witness(self.query,self.catalog,initial['sequence'],initial['charges'])
        if canonical(edges)!=canonical(initial['edge_witnesses']):
            raise ValueError('Initial independently selected edge witness differs')
        if canonical(key)!=canonical(initial['lex_key']) or key[0]!=admission.incumbent.primary_upper:
            raise ValueError('Initial admitted witness key differs')
        self.initial_key=key
        self.store(witness,key)

    def domain_digest(self):
        return sha(canonical(dict(effective_query=self.query,sparse_domain_sha256=self.catalog.domain_sha256,
            candidate_sha256=self.catalog.candidate_sha256,site_catalog_sha256=site_catalog_digest(self.catalog.sites),
            policy_sha256=sha(self.policy))))

    def bindings(self):
        self.policy_check()
        if self.domain_digest()!=self.domain:raise ValueError('Current exact domain changed')
        current=dict(self.source_supplier())
        if current!=self.source:raise ValueError('Live verification sources changed')
        return dict(domain_sha256=self.domain,source_sha256=current)

    def __call__(self,witness,key):
        self.bindings()
        charges=[e.departure_energy-e.arrival_energy for e in witness.events if e.effect in ('C','CS')]
        replay=replay_sparse_seed(self.query,self.catalog,witness.pi,charges)
        if canonical(replay['lex_key'])!=canonical(key):
            raise ValueError('Improved selected-edge replay differs')
        self.store(witness,key)

    def recover(self):
        witness,key=load_verified(self.store.path,problem_factory=self.problem_factory,binding_supplier=self.bindings)
        charges=[e.departure_energy-e.arrival_energy for e in witness.events if e.effect in ('C','CS')]
        if canonical(replay_sparse_seed(self.query,self.catalog,witness.pi,charges)['lex_key'])!=canonical(key):
            raise ValueError('Recovered selected-edge replay differs')
        self.bindings()
        return witness,key


def recover_sparse_record(path,*,exact_query,policy_bytes,verifier_catalog,source_supplier,policy_check):
    """Fresh-process recovery entry, with no store creation or seed overwrite.

    Caller supplies a newly admitted immutable policy and separately loaded
    verifier catalog. Returns only replayed witness and feasible objective.
    """
    query=json.loads(canonical(exact_query));policy=bytes(policy_bytes)
    source=dict(source_supplier())
    for name,digest in verifier_catalog.provider.source_sha256.items():
        if source.get(name)!=digest:raise ValueError('Fresh recovery source differs')
    def bindings():
        policy_check()
        current=dict(source_supplier())
        if current!=source:raise ValueError('Live recovery sources changed')
        domain=sha(canonical(dict(effective_query=query,sparse_domain_sha256=verifier_catalog.domain_sha256,
            candidate_sha256=verifier_catalog.candidate_sha256,site_catalog_sha256=site_catalog_digest(verifier_catalog.sites),
            policy_sha256=sha(policy))))
        return dict(domain_sha256=domain,source_sha256=current)
    def factory():
        return TableFreeRealProblem(query,verifier_catalog.sites,verifier_catalog.provider,
            origin_anchor=query['origin'],destination_anchor=query['destination'],
            site_catalog_sha256=verifier_catalog.site_catalog_sha256)
    witness,key=load_verified(path,problem_factory=factory,binding_supplier=bindings)
    charges=[e.departure_energy-e.arrival_energy for e in witness.events if e.effect in ('C','CS')]
    replay=replay_sparse_seed(query,verifier_catalog,witness.pi,charges)
    if canonical(replay['lex_key'])!=canonical(key):raise ValueError('Recovered selected-edge key differs')
    bindings()
    return witness,key
