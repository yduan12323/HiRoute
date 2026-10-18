"""Derive a new sparse-domain identity from a pinned complete policy proposal.
No graph is loaded and no route is admitted here. The production caller must
first authenticate the proposal worker, graph/native closure and eligibility.
"""
from .portable_candidate_policy import PortableResult,ProposalStatus,canonical,digest
from timecut5.real_legs import RealSite
from timecut5.real_adapter import site_catalog_digest
from timecut5.sparse_seed import sparse_domain_digest

def derive_binding(*,proposal,expected_payload_sha256,baseline_query,baseline_sites,baseline_provider_sources):
 if type(proposal) is not PortableResult or proposal.status is not ProposalStatus.PROPOSED_COMPLETE:
  raise ValueError('Only a completed proposed union can derive a domain')
 if digest(proposal.payload_bytes)!=expected_payload_sha256:raise ValueError('Pinned proposal differs')
 p=proposal.as_dict();b=p['bindings'];d=p['descriptor']
 if p['status']!='proposed_complete' or p['complete'] is not True or p['launchable'] is not False or p['runtime_admission_complete'] is not False:
  raise ValueError('Invalid proposal claims')
 if p['unchanged_query']!=baseline_query or b['query_sha256']!=digest(canonical(baseline_query)) or b['baseline_sites_sha256']!=digest(canonical(baseline_sites)) or b['source_sha256']!=baseline_provider_sources:
  raise ValueError('Original query/catalog/source identity differs')
 baseline={x['site_id']:x for x in baseline_sites}
 if len(baseline)!=len(baseline_sites):raise ValueError('Duplicate baseline ID')
 def catalog(rows):return {x['site_id']:RealSite(x['site_id'],x['anchor_id'],tuple(x['effects'])) for x in rows}
 old_candidate=digest(canonical(sorted(baseline)))
 old_domain=sparse_domain_digest(baseline_provider_sources,site_catalog_digest(catalog(baseline_sites)),old_candidate,baseline_query['hierarchy_sha256'],baseline_query['origin'],baseline_query['destination'])
 if old_domain!=baseline_query['sparse_domain_sha256'] or b['baseline_domain_sha256']!=old_domain or b['baseline_candidate_sha256']!=old_candidate:
  raise ValueError('Original loaded-domain semantics differ')
 sites=p['sites'];ids=[x['site_id'] for x in sites];byid={x['site_id']:x for x in sites}
 if ids!=sorted(set(ids)) or ids!=p['candidate_ids'] or any(byid.get(k)!=v for k,v in baseline.items()):raise ValueError('Baseline preservation or sorted union differs')
 if p['candidate_sha256']!=digest(canonical(ids)) or p['domain_sha256']!=digest(canonical(d)) or d['candidate_ids']!=ids or d['complete_site_rows_sha256']!=digest(canonical(sites)) or d['bindings']!=b:
  raise ValueError('Descriptor content differs')
 anchors={a:int(a.removeprefix('road:')) for a in dict.fromkeys([baseline_query['origin']]+[x['anchor_id'] for x in sites]+[baseline_query['destination']])}
 sources=dict(baseline_provider_sources,anchors=digest(canonical(anchors)))
 site_sha=site_catalog_digest(catalog(sites));domain=sparse_domain_digest(sources,site_sha,p['candidate_sha256'],baseline_query['hierarchy_sha256'],baseline_query['origin'],baseline_query['destination'])
 query=dict(baseline_query,sparse_domain_sha256=domain)
 return dict(schema='hiroute.portable_reachable_sparse_binding.v1',launchable=False,runtime_admission_complete=False,policy_version=d['rule_version'],proposal_sha256=expected_payload_sha256,proposal_descriptor_sha256=p['domain_sha256'],original_domain_sha256=old_domain,original_query_sha256=b['query_sha256'],candidate_count=len(ids),candidate_site_ids=ids,candidate_sha256=p['candidate_sha256'],site_catalog_sha256=site_sha,anchor_catalog_sha256=sources['anchors'],provider_source_sha256=sources,sparse_domain_sha256=domain,query=query,query_sha256=digest(canonical(query)),sites=sites)
