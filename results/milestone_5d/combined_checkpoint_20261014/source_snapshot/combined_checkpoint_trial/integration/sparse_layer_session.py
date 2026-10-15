"""Source-bound table-free dispatch integration for completed-layer envelopes.

Experimental launcher adapter. Production admission remains the caller's
existing native/graph/landmark gate; tiny dispatch tests do not bypass that gate.
"""
from contextlib import nullcontext
import json
import math
from pathlib import Path

import timecut5
from timecut5.feasible_incumbent import canonical,sha,_file_sha
from timecut5.layer_envelope import run_layer_envelope
from timecut5.real_adapter import TableFreeRealProblem,site_catalog_digest,_TableFreeRealLegs
from timecut5.road_provider import TIE_POLICY,TableFreeRegionBoundProvider
from timecut5.sparse_feasible_execution import _tree
from timecut5.hierarchy import build_regions
from timecut5.deployable import RegionLandmarkSummary,member_set_digest
from sparse_durable_session import seed_witness


class SparseLayerSession:
    def __init__(self,output_path,*,method,exact_query,admission,search_provider,
                 verifier_catalog,source_paths,policy_check,
                 previous_checkpoint=None,stop_after_depth=None):
        self.path=Path(output_path);self.method=method
        self.query=json.loads(canonical(exact_query));self.catalog=verifier_catalog
        self.search=search_provider;self.policy_check=policy_check
        self.previous=previous_checkpoint;self.stop_after_depth=stop_after_depth
        self.policy=bytes(admission.policy_bytes)
        self.paths={k:Path(v) for k,v in source_paths.items()}
        if not {'nodes','edges','router'}<=set(self.paths):
            raise ValueError('Actual graph and router source paths required')
        # Automatically bind the full Python solver closure and the three
        # integration modules, rather than relying on a caller's subset.
        directory=Path(timecut5.__file__).resolve().parent
        self.paths.update({'timecut5:'+p.name:p for p in directory.glob('*.py')})
        here=Path(__file__).resolve().parent
        self.paths.update({'integration:'+name:here/name for name in
            ('production_boundary.py','sparse_layer_session.py','sparse_durable_session.py')})
        if verifier_catalog.provider is search_provider or verifier_catalog.provider.router is search_provider.router:
            raise ValueError('Independent verifier provider and router required')
        expected=dict(json.loads(admission.incumbent.query_bytes),H_ref=admission.incumbent.max_depth)
        if (canonical(self.query)!=canonical(expected) or
                admission.incumbent.domain_sha256!=verifier_catalog.domain_sha256 or
                sha(self.policy)!=admission.policy_sha256):
            raise ValueError('Admitted exact query/domain/policy differs')
        if dict(search_provider.source_sha256)!=dict(verifier_catalog.provider.source_sha256):
            raise ValueError('Search and verifier physical sources differ')
        self.source=self.sources()
        for key,value in verifier_catalog.provider.source_sha256.items():
            if self.source.get(key)!=value:
                raise ValueError('Actual verification source differs: '+key)
        self.domain=self.domain_digest()
        self.bindings()
        initial=json.loads(admission.incumbent.witness_bytes)
        self.witness,self.initial_key,edges=seed_witness(self.query,self.catalog,initial['sequence'],initial['charges'])
        if (canonical(edges)!=canonical(initial['edge_witnesses']) or
                canonical(self.initial_key)!=canonical(initial['lex_key']) or
                self.initial_key[0]!=admission.incumbent.primary_upper):
            raise ValueError('Original independently replayed admitted seed differs')
        self.bindings()

    def sources(self):
        result={name:_file_sha(path) for name,path in self.paths.items()}
        result.update(anchors=sha(canonical(self.catalog.provider.anchor_nodes)),
                      tie_policy=sha(TIE_POLICY.encode()))
        return result

    def domain_digest(self):
        return sha(canonical(dict(effective_query=self.query,
            sparse_domain_sha256=self.catalog.domain_sha256,
            candidate_sha256=self.catalog.candidate_sha256,
            site_catalog_sha256=site_catalog_digest(self.catalog.sites),
            policy_sha256=sha(self.policy))))

    def bindings(self):
        self.policy_check()
        if self.domain_digest()!=self.domain or self.sources()!=self.source:
            raise ValueError('Live exact domain or transitive sources changed')
        if (dict(self.search.source_sha256)!=dict(self.catalog.provider.source_sha256) or
                sha(canonical(self.search.anchor_nodes))!=self.source['anchors']):
            raise ValueError('Live search/verifier source identities differ')
        return dict(domain_sha256=self.domain,source_sha256=self.source)

    def verifier_problem(self):
        self.bindings()
        return TableFreeRealProblem(self.query,self.catalog.sites,self.catalog.provider,
            origin_anchor=self.query['origin'],destination_anchor=self.query['destination'],
            site_catalog_sha256=self.catalog.site_catalog_sha256)

    def validate_bound_derivations(self,bound,root):
        """Charged preparation scan; no change to online Region query costs."""
        regions={}
        def visit(region):
            if region.identifier in regions:raise ValueError('Duplicate bound Region')
            regions[region.identifier]=region
            for child in region.children:visit(child)
        visit(root)
        graph_digest=sha((self.search.source_sha256['nodes']+self.search.source_sha256['edges']).encode())
        if (bound.graph_sha256!=graph_digest or set(bound._regions)!=set(regions) or
                any(bound._regions[k] is not region for k,region in regions.items())):
            raise ValueError('Actual Region identity or graph binding differs')
        labels=bound.landmarks[0];summaries={};members={}
        for key,region in regions.items():
            if region.members:
                members[key]=member_set_digest(region.members)
                summaries[key]=RegionLandmarkSummary(members[key],graph_digest,bound.landmark_sha256,
                    (min(labels.from_landmark[self.catalog.sites[s].anchor_id] for s in region.members),),
                    (max(labels.to_landmark[self.catalog.sites[s].anchor_id] for s in region.members),))
        bits={action:1<<index for index,action in enumerate(
            (site,effect) for site in sorted(self.catalog.sites)
            for effect in sorted(self.catalog.sites[site].effects)
            if self.catalog.sites[site].anchor_id!=self.query['destination'])}
        actions={};masks={}
        for key,region in regions.items():
            for remaining in (0,1):
                for effect in ('C','S','CS'):
                    selected=(() if effect in ('S','CS') and not remaining else
                              tuple((site,effect) for site in region.members if (site,effect) in bits))
                    actions[key,effect,remaining]=selected
                    masks[key,effect,remaining]=sum(bits[action] for action in selected)
        if (bound._summary!=summaries or bound._member_hash!=members or bound._action_bits!=bits or
                bound._actions!=actions or bound._action_masks!=masks):
            raise ValueError('Live bound summaries or action coverage differ')

    def run(self,*,problem,bound,root,progress_hook=None):
        self.bindings()
        expected=self.verifier_problem()
        expected_root=build_regions(self.catalog.sites,leaf_size=1)
        attributes=('bound','start','initial','capacity','floor','reserve','overhead','penalty','rate',
                    'schedule','origin','destination','sites','initial_remaining')
        if (type(problem) is not TableFreeRealProblem or
                type(problem.legs) is not _TableFreeRealLegs or
                type(bound) is not TableFreeRegionBoundProvider or
                any(callable(v) for v in vars(problem).values()) or
                any(callable(v) for v in vars(bound).values()) or
                any(canonical(getattr(problem,k))!=canonical(getattr(expected,k)) for k in attributes) or
                type(problem.curve) is not type(expected.curve) or
                canonical(None if problem.curve is None else problem.curve.segments)!=
                    canonical(None if expected.curve is None else expected.curve.segments) or
                problem.legs.provider is not self.search or problem.legs.rate!=expected.rate):
            raise ValueError('Effective production query fields or runtime class differs')
        certificate=json.loads(bound.landmark_certificate)
        if len(bound.landmarks)!=1:
            raise ValueError('Unexpected landmark count')
        labels={name:[None if math.isinf(bound.landmarks[0].from_landmark[name]) else bound.landmarks[0].from_landmark[name],
                      None if math.isinf(bound.landmarks[0].to_landmark[name]) else bound.landmarks[0].to_landmark[name]]
                for name in sorted(self.search.anchor_nodes)}
        if (certificate.get('anchor_labels')!=labels or
                certificate.get('graph_nodes_sha256')!=self.search.source_sha256['nodes'] or
                certificate.get('graph_edges_sha256')!=self.search.source_sha256['edges'] or
                certificate.get('router_source_sha256')!=self.search.source_sha256['router'] or
                certificate.get('root_anchor')!=self.catalog.origin_anchor):
            raise ValueError('Live landmark labels or physical certificate binding differs')
        if (problem.provider is not self.search or canonical(problem.case)!=canonical(expected.case) or
                canonical(_tree(root))!=canonical(_tree(expected_root)) or
                bound.leg_provider is not self.search or
                canonical(_tree(bound.root))!=canonical(_tree(root)) or
                site_catalog_digest(bound.sites)!=self.catalog.site_catalog_sha256 or
                problem.site_catalog_sha256!=self.catalog.site_catalog_sha256 or
                dict(problem.site_anchors)!=dict(expected.site_anchors) or
                sha(bound.landmark_certificate)!=bound.landmark_sha256):
            raise ValueError('Actual production search factory or Region policy differs')
        self.validate_bound_derivations(bound,root)
        bound_policy=sha(canonical(dict(admission_policy_sha256=sha(self.policy),
            region_tree_sha256=sha(canonical(_tree(root))),landmark_sha256=bound.landmark_sha256,
            lower_bound_policy='existing_tablefree_indexed_region_v1')))
        # Preserve the existing optional observer's context without changing the
        # reviewed envelope core or adding a second nested solver observer.
        with progress_hook if progress_hook is not None else nullcontext():
            result=run_layer_envelope(problem_factory=lambda:problem,
                verifier_factory=self.verifier_problem,binding_supplier=self.bindings,
                initial_witness=self.witness,method=self.method,output_path=self.path,
                bound_policy_sha256=bound_policy,root=root if self.method=='hier' else None,
                bound_provider=bound if self.method=='hier' else None,
                singleton_bound=bound.singleton_bound if self.method=='flat' else None,
                previous_checkpoint=self.previous,stop_after_depth=self.stop_after_depth)
        self.bindings()
        return result
