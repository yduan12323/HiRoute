"""Read-only compact case import and query fingerprint report; no optimization."""
import argparse
import hashlib
import json
from pathlib import Path
import time

from timecut5.real_export_input import load_exported_case


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export',required=True,type=Path)
    parser.add_argument('--manifest-sha256',required=True)
    parser.add_argument('--selection',required=True,type=Path)
    parser.add_argument('--selection-sha256',required=True)
    parser.add_argument('--original-hierarchy',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    start=time.monotonic()
    # Even the outer enumeration is bound to the caller's reviewed manifest.
    manifest_bytes=(args.export/'export_manifest.json').read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest()!=args.manifest_sha256:
        raise ValueError('Export manifest hash mismatch')
    manifest=json.loads(manifest_bytes)
    state_bytes=(args.export/'query_states_resolved.json').read_bytes()
    if hashlib.sha256(state_bytes).hexdigest()!=manifest['query_states_resolved_sha256']:
        raise ValueError('Resolved state hash mismatch')
    states=json.loads(state_bytes);records=[]
    for state in states:
        prepared=load_exported_case(args.export,state['state_id'],args.manifest_sha256,
          selection_path=args.selection,expected_selection_sha256=args.selection_sha256,
          original_hierarchy_path=args.original_hierarchy)
        query_bytes=json.dumps(prepared.query,sort_keys=True,separators=(',',':')).encode()
        records.append(dict(state_id=prepared.state_id,query_sha256=hashlib.sha256(query_bytes).hexdigest(),
          site_count=len(prepared.table.sites),anchor_count=len(prepared.table.anchors),
          region_count=len(prepared.restriction.regions),table_sha256=prepared.table.payload_sha256,
          onward_time_lower_bound='0',optimization_run=False))
    result=dict(scope='read_only_compact_input_preparation',optimization_run=False,
      export_manifest_sha256=args.manifest_sha256,selection_sha256=args.selection_sha256,
      elapsed_seconds=time.monotonic()-start,states=records)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
    print(json.dumps(dict(state_count=len(records),optimization_run=False,elapsed_seconds=result['elapsed_seconds'])))


if __name__=='__main__':main()
