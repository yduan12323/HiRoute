#!/usr/bin/env python3
"""Descriptive original-main outcomes only; no inferred speed or exactness."""
import argparse, collections, hashlib, html, json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--rows',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
raw=a.rows.read_bytes(); rows=[json.loads(x) for x in raw.splitlines() if x.strip()]
if len(rows)!=192 or len({x['row_id'] for x in rows})!=192: raise SystemExit('Expected exactly 192 unique original-main rows')
if any(x.get('denominator_included') is not True for x in rows): raise SystemExit('Excluded denominator row')
c=collections.Counter(x['status'] for x in rows)
expected={'time_limit':148,'incumbent_search_failed':44}
if dict(c)!=expected: raise SystemExit('Pinned main-outcome distribution changed; review before plotting')
a.output.mkdir(parents=True,exist_ok=False)
items=[('time_limit','Timeout',148,'#de8d31'),('incumbent_search_failed','Initial-solution search failed',44,'#8264b4'),('infrastructure_unknown','Infrastructure unknown',0,'#737373'),('exact_completion','Exact completion',0,'#348a67')]
svg=['<svg xmlns="http://www.w3.org/2000/svg" width="900" height="350" viewBox="0 0 900 350"><rect width="900" height="350" fill="white"/><g font-family="sans-serif" fill="#222">','<text x="24" y="35" font-size="22">M5-D original main: all 192 rows retained</text>','<text x="24" y="63" font-size="14">Descriptive status counts. No completed exact pairs; speedup is unavailable.</text>']
for i,(_,label,n,color) in enumerate(items):
 y=104+i*49
 svg += [f'<text x="24" y="{y+19}" font-size="16">{html.escape(label)}</text>',f'<rect x="285" y="{y}" width="{n/192*510:.3f}" height="28" fill="{color}"/>',f'<text x="{295+n/192*510:.3f}" y="{y+20}" font-size="16">{n}</text>']
svg += ['<text x="24" y="326" font-size="13">The fixed 24-row supplement is a separate population and is not included here.</text></g></svg>']
(a.output/'original_main_status.svg').write_text('\n'.join(svg)+'\n')
(a.output/'original_main_status.data.json').write_text(json.dumps({'denominator':192,'population':'original_main_only','input_sha256':hashlib.sha256(raw).hexdigest(),'counts':dict(c),'exact_pairs':0,'paired_speedup':None,'supplement_included':False},indent=2)+'\n')
