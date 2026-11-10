"""Frozen query identity shared by preparation and audit tools."""
import hashlib
import json

def domain_digest(query,n,scenario):
    value=dict(endpoints=query['endpoints'],
        candidates=query['scenario_candidate_domains'][scenario][str(n)])
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
