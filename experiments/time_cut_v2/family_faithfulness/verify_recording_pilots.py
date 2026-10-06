"""Optimizer-free family checking, exact callback replay and receipt sealing."""
import argparse, gzip, hashlib, json, resource, shutil, sys, time
from fractions import Fraction as F
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'validation'))
from family5.checker import verify_bundle, check_witness, reconstruct, digest, rational, check_receipt, require, wire_equal


def write_row(stream,row):
    stream.write((json.dumps(row,sort_keys=True,separators=(',',':'))+'\n').encode())


def reconstruction_requests(payload):
    rows=[]
    for node_id in sorted(payload['bundle']['nodes']):
        node=payload['bundle']['nodes'][node_id]
        piece=node['output'];lo,hi=map(F,piece['domain'][:2]);lc,rc=piece['domain'][2:]
        energies={(lo+hi)/2}
        if lc:energies.add(lo)
        if rc:energies.add(hi)
        for energy in sorted(energies):
            tau=F(piece['m'])*energy+F(piece['b'])
            budget=tau if piece['chi'] else tau+F(1,10**60)
            rows.append((node_id,dict(kind='realize_le',energy=str(energy),budget=str(budget))))
    return rows


def replay(path,ctx,payload,expected_report=None,source_sha256=None):
    actual=payload.get('callback_requests',[]);independent=reconstruction_requests(payload)
    if expected_report is not None:
        require(wire_equal(source_sha256,expected_report['source_sha256']),'source artifact differs from sealed report')
        require(wire_equal(hashlib.sha256(path.read_bytes()).hexdigest(),expected_report['raw_sha256']),'raw receipts differ from sealed report')
    count=0
    with gzip.open(path,'rt') as stream:
        for line in stream:
            row=json.loads(line)
            if count<len(actual):
                expected=actual[count]
                require(row['kind']=='actual_production_callback' and type(row['index']) is int and row['index']==count,'callback kind/index mismatch')
                require(set(row)=={'kind','index','node_id','contract','witness','receipt'},'callback row fields mismatch')
                require(wire_equal({k:row[k] for k in expected},expected),'original callback request mismatch')
            else:
                i=count-len(actual)
                require(i<len(independent),'extra reconstruction receipt')
                node_id,contract=independent[i]
                require(row['kind']=='independent_reconstruction' and row['node_id']==node_id,'reconstruction family/order mismatch')
                require(set(row)=={'kind','node_id','contract','witness','receipt'},'reconstruction row fields mismatch')
                require(wire_equal(row['contract'],contract),'reconstruction energy/budget coverage mismatch')
            check_receipt(ctx,row['node_id'],row['witness'],row['contract'],row['receipt'],
                          require_budgets=row['kind']=='independent_reconstruction')
            count+=1
    require(count==len(actual)+len(independent),'missing callback or reconstruction receipts')
    if expected_report is not None:
        require(wire_equal(count,expected_report['raw_receipts_replayed']),'reported receipt count mismatch')
        require(wire_equal(len(actual),expected_report['actual_production_callbacks_replayed']),'reported callback count mismatch')
        require(wire_equal(len(independent),expected_report['independently_reconstructed_witnesses']),'reported reconstruction count mismatch')
    return count


def verify_seal(path,expected_sha):
    require(wire_equal(hashlib.sha256(path.read_bytes()).hexdigest(),expected_sha),'wrong external evidence-manifest hash')
    manifest=json.loads(path.read_text())
    require(type(manifest) is dict and type(manifest.get('files')) is dict,'invalid evidence manifest')
    for relative,entry in manifest['files'].items():
        require(type(relative) is str and relative and not Path(relative).is_absolute() and '..' not in Path(relative).parts,'invalid manifest relative path')
        require(type(entry) is dict and {'sha256','bytes'}<=set(entry),'invalid manifest file entry')
        target=(path.parent/relative).resolve()
        require(target.is_relative_to(path.parent.resolve()),'manifest path escape')
        require(wire_equal(hashlib.sha256(target.read_bytes()).hexdigest(),entry['sha256']),'manifest file hash mismatch',path=relative)
        require(type(entry['bytes']) is int and entry['bytes']>=0 and target.stat().st_size==entry['bytes'],'manifest byte count mismatch',path=relative)
    return manifest


def sealed_member(path,manifest,base):
    resolved=path.resolve();base=base.resolve()
    require(resolved.is_relative_to(base),'replay input/source is outside sealed artifact root')
    relative=str(resolved.relative_to(base))
    require(relative in manifest['files'],'replay input/source is not in evidence manifest')


def main():
    p=argparse.ArgumentParser();p.add_argument('--inputs-dir',type=Path,required=True)
    p.add_argument('--case-files',nargs='+',required=True);p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--reuse-receipts-dir',type=Path);p.add_argument('--replay-only',action='store_true');p.add_argument('--evidence-manifest',type=Path);p.add_argument('--manifest-sha');args=p.parse_args()
    if args.replay_only:
        require(args.evidence_manifest is not None and bool(args.manifest_sha),'sealed replay requires externally anchored evidence manifest')
        manifest=verify_seal(args.evidence_manifest,args.manifest_sha)
        seal_root=args.evidence_manifest.parent
        for source_path in (Path(__file__),Path(sys.modules['family5.checker'].__file__),
                            Path(sys.modules['family5.independent_oracle_v2'].__file__)):
            sealed_member(source_path,manifest,seal_root)
    trusted={c['case_id']:c for f in args.case_files for c in json.loads(Path(f).read_text())}
    args.output_dir.mkdir(parents=True,exist_ok=True);reports=[]
    sources=[source for source in sorted(args.inputs_dir.glob('*.json')) if source.name!='summary.json']
    require(bool(sources),'empty replay population')
    if args.replay_only:
        population=manifest.get('replay_population')
        require(type(population) is dict,'manifest lacks explicit replay population')
        require(args.inputs_dir.resolve()==(seal_root/population['inputs_directory']).resolve(),'wrong replay input population')
        require(args.output_dir.resolve()==(seal_root/population['receipts_directory']).resolve(),'wrong replay receipt population')
        expected_files=population['input_files']
        require(type(expected_files) is list and wire_equal([p.name for p in sources],expected_files),'replay case coverage mismatch')
    for source in sources:
        payload=json.loads(source.read_text());case_id=payload['case']['case_id']
        require(wire_equal(payload['case'],trusted[case_id]),'trusted case mismatch')
        start=time.perf_counter();ctx=verify_bundle(payload['bundle'],trusted[case_id])
        path=args.output_dir/(case_id+'.receipts.jsonl.gz')
        if args.replay_only:
            report_path=args.output_dir/(case_id+'.json')
            for selected_path in (source,path,report_path):sealed_member(selected_path,manifest,seal_root)
            expected=json.loads(report_path.read_text())
            count=replay(path,ctx,payload,expected,hashlib.sha256(source.read_bytes()).hexdigest())
            print(json.dumps(dict(case_id=case_id,replayed=count,seal_verified=True)),flush=True);continue
        if args.reuse_receipts_dir:
            origin=args.reuse_receipts_dir/path.name
            shutil.copyfile(origin,path)
            actual=len(payload.get('callback_requests',[]))
            generated=len(reconstruction_requests(payload))
            winner_bindings=[r['node_id'] for r in payload.get('callback_requests',[])
                             if wire_equal(payload.get('witness'),r['witness']) and r['node_id'] in payload['bundle']['roots']]
        else:
            generated=actual=0;winner_bindings=[]
            with path.open('wb') as raw,gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0) as stream:
                for index,request in enumerate(payload.get('callback_requests',())):
                    receipt=check_witness(ctx,request['node_id'],request['witness'],request['contract'])
                    write_row(stream,dict(kind='actual_production_callback',index=index,**request,receipt=receipt))
                    if wire_equal(payload.get('witness'),request['witness']) and request['node_id'] in payload['bundle']['roots']:
                        winner_bindings.append(request['node_id'])
                    actual+=1
                for node_id,contract in reconstruction_requests(payload):
                    result=reconstruct(ctx,node_id,contract['energy'],contract['budget'])
                    check_receipt(ctx,node_id,result['witness'],contract,result['receipt'],require_budgets=True)
                    write_row(stream,dict(kind='independent_reconstruction',node_id=node_id,
                              witness=result['witness'],contract=contract,receipt=result['receipt']))
                    generated+=1
        if payload.get('witness') is not None:require(bool(winner_bindings),'attained winner lacks original family binding')
        total=replay(path,ctx,payload);require(total==actual+generated,'generated receipt count mismatch')
        row=dict(case_id=case_id,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                 verification=dict(ctx.summary),actual_production_callbacks_replayed=actual,
                 independently_reconstructed_witnesses=generated,attained_winner_family_ids=sorted(set(winner_bindings)),
                 raw_receipts_replayed=total,raw_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),raw_bytes=path.stat().st_size,
                 elapsed_s=time.perf_counter()-start,process_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                 literal_G8_closed=False,
                 reused_raw_receipts=bool(args.reuse_receipts_dir),
                 raw_origin_directory=str(args.reuse_receipts_dir) if args.reuse_receipts_dir else None,
                 budget_annotations_and_source_coverage_replayed=True)
        reports.append(row);print(json.dumps(row),flush=True)
        (args.output_dir/(case_id+'.json')).write_text(json.dumps(row,sort_keys=True,indent=2)+'\n')
    if not args.replay_only:
        (args.output_dir/'summary.json').write_text(json.dumps(reports,sort_keys=True,indent=2)+'\n')

if __name__=='__main__':main()
