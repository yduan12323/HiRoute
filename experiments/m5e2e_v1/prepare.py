"""Independent DEV admission to unchanged Shandong preprocessing functions.

This does not enable, impersonate, or call the held M6-H launch gate. Callers
must supervise the whole preparation process tree under the E2E resource cap.
"""
from __future__ import annotations
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from urllib.request import urlopen
from .selection import canonical, digest, file_hash, validate_frozen_model

RAW_FILES = {'local_pbf':'shandong-261016.osm.pbf', 'local_polygon':'boundary.poly',
             'local_publisher_md5':'publisher.md5'}


def preflight(config, raw_cache):
    """Read-only input-cache identity inspection, with explicit missing entries."""
    cache = Path(raw_cache).resolve()
    source = config['source']; rows = {}; failures = []
    for key, name in RAW_FILES.items():
        path = cache/name
        row = {'present':path.is_file(), 'name':name}
        if path.is_symlink():
            failures.append(name+':symlink'); row['valid']=False
        elif path.is_file():
            row.update(size_bytes=path.stat().st_size,sha256=file_hash(path))
            if key=='local_pbf':
                row['valid'] = row['size_bytes']==source['expected_size_bytes'] and row['sha256']==source['sha256']
            elif key=='local_polygon': row['valid'] = row['sha256']==source['polygon_sha256']
            else:
                fields=path.read_text().split()
                row['valid'] = bool(fields) and fields[0]==source['publisher_md5']
            if not row['valid']: failures.append(name+':identity_mismatch')
        rows[key]=row
    return dict(schema='hiroute.m5e2e.raw_preflight.v1', raw_files=rows,
                status='IDENTITY_MISMATCH' if failures else 'READY' if all(r['present'] for r in rows.values()) else 'NEEDS_ACQUISITION',
                failures=failures, source_sha256=digest(source))


def _acquire(config, raw_cache):
    cache = Path(raw_cache).resolve(); cache.mkdir(parents=True,exist_ok=True)
    source=config['source']
    specs=[('local_pbf',source['url'],source['expected_size_bytes']),
           ('local_polygon',source['polygon_url'],16*1024**2),
           ('local_publisher_md5',source['url']+'.md5',4096)]
    if preflight(config,cache)['status']=='IDENTITY_MISMATCH': raise ValueError('Frozen raw cache identity mismatch')
    for key,url,limit in specs:
        path=cache/RAW_FILES[key]
        if path.exists(): continue
        partial=cache/(RAW_FILES[key]+'.partial')
        with urlopen(url,timeout=30) as response, partial.open('xb') as out:
            if response.url != url: raise ValueError('Raw source redirect requires review')
            count=0
            for block in iter(lambda:response.read(1024**2),b''):
                count+=len(block)
                if count>limit: raise ValueError('Raw source exceeds bound')
                out.write(block)
        # Link is no-clobber; failed partial evidence is never deleted.
        os.link(partial,path); path.chmod(0o444)
    report=preflight(config,cache)
    if report['status']!='READY': raise ValueError('Raw source authentication failed')
    return report


def prepare_inputs(config, raw_cache, output_root, *, osmium, compiler, config_root=None):
    """Generate source/graph/inventory/Sites/hierarchy in a new run directory.

    The orchestrator owns the enclosing budget, phase ledger and aggregate
    supervisor. A mandatory capability argument is not a substitute for those
    controls: the worker verifies its configured admission before this call.
    """
    if config.get('schema')!='hiroute.m5e2e.config.v1' or config.get('exposure_class')!='DEV_E2E':
        raise ValueError('Explicit E2E configuration required')
    validate_frozen_model(config)
    if platform.system()!='Linux' or platform.machine()!='x86_64' or sys.version_info[:2]!=(3,11):
        raise RuntimeError('BLOCKED_SOURCE_OR_ENVIRONMENT: supported Linux x86-64 / Python 3.11 required')
    # Preserve >=10 GiB host headroom and old 5 GiB sampled-tree admission.
    mem={line.split(':')[0]:int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines() if line.split()[1].isdigit()}
    if mem['MemAvailable'] < 15*2**30:
        raise RuntimeError('BLOCKED_INPUT_OR_ENVIRONMENT: insufficient preprocessing headroom')
    from experiments.shandong_preprocessing_v1 import phases
    package_root=Path(phases.__file__).resolve().parents[2]
    config_root=Path(config_root or package_root).resolve()
    for line in (package_root/'experiments/shandong_preprocessing_v1/installed.txt').read_text().splitlines():
        name,version=line.split('==')
        if importlib.metadata.version(name)!=version: raise RuntimeError('Pinned preprocessing dependency mismatch: '+name)
    phases._require_osmium_version(phases.native(osmium,'--version'))
    tools=phases.toolchain_identity(sys.executable,osmium,compiler)
    os.environ['HIROUTE_TOOLCHAIN_IDENTITY']=json.dumps(tools,sort_keys=True)
    root=Path(output_root).resolve(); root.mkdir(parents=True,exist_ok=False)
    raw_report=_acquire(config,raw_cache)
    runtime_config=dict(source=dict(config['source']),geometry=config['geometry'],config_root=str(config_root))
    runtime_config['source'].update({k:str(Path(raw_cache).resolve()/v) for k,v in RAW_FILES.items()})
    prior={}
    for name in ('source','graph','inventory','sites','hierarchy'):
        out=root/name; out.mkdir(); scratch=out/'scratch'; scratch.mkdir(mode=0o700)
        for key in ('TMPDIR','TMP','TEMP'): os.environ[key]=str(scratch)
        # Core functions are the same real implementation. No old launcher/gate
        # is called, patched, or given a fabricated recovery/root admission.
        phases.PHASES[name](out,prior,runtime_config,osmium,False)
        files={str(p.relative_to(out)):dict(sha256=file_hash(p),size_bytes=p.stat().st_size)
               for p in sorted(out.rglob('*')) if p.is_file()}
        manifest=dict(schema='hiroute.m5e2e.preparation_stage.v1',phase=name,synthetic=False,
                      config_sha256=digest(config),files=files,prior=prior.copy())
        with (out/'artifact_manifest.json').open('xb') as stream: stream.write(canonical(manifest))
        prior[name]=dict(path=str(out),manifest_sha256=file_hash(out/'artifact_manifest.json'),phase=name,synthetic=False)
    consumed=[root/'graph'/n for n in ('nodes.parquet','edges.parquet','metadata.json')]
    consumed += [root/'sites/stop_sites.parquet',root/'hierarchy/hierarchy.json']
    receipt=dict(schema='hiroute.m5e2e.prepared.v1',status='PREPARED',config_sha256=digest(config),
                 graph_directory=str(root/'graph'),sites_path=str(root/'sites/stop_sites.parquet'),
                 hierarchy_path=str(root/'hierarchy/hierarchy.json'),raw_report=raw_report,
                 toolchain=tools,stages=prior,canonical_content={
                     'nodes':canonical_parquet_digest(root/'graph/nodes.parquet'),
                     'edges':canonical_parquet_digest(root/'graph/edges.parquet'),
                     'sites':canonical_parquet_digest(root/'sites/stop_sites.parquet'),
                     'hierarchy_sha256':file_hash(root/'hierarchy/hierarchy.json')},consumed_files={str(p):dict(sha256=file_hash(p),size_bytes=p.stat().st_size) for p in consumed})
    with (root/'prepared.json').open('xb') as stream: stream.write(canonical(receipt))
    return receipt


# Stable orchestration aliases; no alternative behavior or historical entry.
prepare = prepare_inputs


def canonical_parquet_digest(path):
    """Hash ordered semantic rows independent of Parquet container metadata.

    The preprocessing contract already fixes row and column identities. Floats
    are canonical binary64 hex, nulls remain null, and bytes become hex strings.
    Record batch boundaries and compression do not enter this digest.
    """
    import hashlib
    import math
    import pyarrow.parquet as pq
    def value(item):
        if isinstance(item,float):
            if math.isnan(item): return {'float':'nan'}
            if not math.isfinite(item): return {'float':item.hex()}
            return {'binary64':item.hex()}
        if isinstance(item,bytes): return {'bytes_hex':item.hex()}
        if isinstance(item,(list,tuple)): return [value(x) for x in item]
        if isinstance(item,dict): return {str(k):value(v) for k,v in sorted(item.items())}
        return item
    parquet=pq.ParquetFile(path); h=hashlib.sha256(); count=0
    h.update(canonical({'columns':sorted(parquet.schema_arrow.names)})); h.update(b'\n')
    for batch in parquet.iter_batches(batch_size=4096,use_threads=False):
        for row in batch.to_pylist():
            h.update(canonical(value(row))); h.update(b'\n'); count+=1
    return dict(schema='hiroute.canonical_parquet_rows.v1',sha256=h.hexdigest(),row_count=count,
                columns=sorted(parquet.schema_arrow.names),row_order='producer-defined stable order')
