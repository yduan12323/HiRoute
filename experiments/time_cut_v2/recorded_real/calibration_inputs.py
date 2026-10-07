"""Authenticate the completed fixed preview before selecting any LP workload."""
from dataclasses import asdict
from pathlib import Path
from . import plan as binding,model_preview,suffix_census
from .hot_jobs import read_pinned
from .runtime import BATCH_REPLAY,read_phase_result

def load_preview(args,anchors,index,trusted,summary,deadline,before):
 logical=model_preview.logical_input(args,anchors,index,trusted,summary,deadline,before)
 returned=read_pinned(args.preview_return,args.preview_return_sha,65536)
 accepted=read_phase_result(args.preview_attempt,successful_return=returned,deadline_monotonic=deadline,resource_check=before)
 binding.require(accepted['status']=='completed' and accepted['descendants_reaped'] is True,'preview resource phase incomplete')
 suffix_census.same(accepted['profile'],asdict(BATCH_REPLAY),'preview group profile changed')
 binding.require(accepted['context']['source_sha256']==args.preview_source_sha and
  accepted['context']['plan_sha256']==args.replay_plan_sha,'preview source/plan context changed')
 root=Path(args.preview_attempt)/'evidence'
 manifest=read_pinned(root/'__manifest.json',accepted['verified_manifest_sha256'],1024**2)
 files={r['path']:r for r in manifest['files']}
 binding.require(len(files)==len(manifest['files']) and set(files)==model_preview.FILES,'completed preview file coverage changed')
 binding.require(files['preview-summary.json']['sha256']==args.preview_summary_sha,'preview summary pin changed')
 def read(name,limit=64*1024**2):
  spec=files[name];binding.require(type(spec['size_bytes']) is int and spec['size_bytes']<=limit,'preview file cap')
  result=read_pinned(root/name,spec['sha256'],limit);before();return result
 report=read('preview-summary.json',4*1024**2);run=read('run-binding.json',4*1024**2)
 binding.require(report['schema']=='hiroute-structural-model-payload-preview-v1' and report['model_builder_comparison'] is True and
  type(report['solver_calls']) is int and report['solver_calls']==0 and report['full_population_complete'] is False and
  report['literal_G8_closed'] is False and report['source_sha256']==args.preview_source_sha,'completed preview scope changed')
 binding.require(run['source_sha256']==args.preview_source_sha and report['selected_models']==256 and report['selected_families']==7,
  'fixed preview population/source changed')
 for value in (report,run):
  suffix_census.same(value['completed_replay'],anchors,'preview changed the completed structural source')
  binding.require(value['logical_report_sha256']==args.logical_report_sha,'preview logical source changed')
 for field,name in (('selection','selection.json'),('model_payloads','model-payloads.json'),('task_payloads','task-payloads.json'),('batch_ledger','batch-ledger.json')):
  suffix_census.same(report[field],files[name],'preview payload commitment changed: '+field)
 family=report['family_verification']
 binding.require(family['verified'] is True and family['bundle_sha256']==index['bundle_sha256'] and family['case_sha256']==index['case_sha256'],
  'preview family source changed')
 suffix_census.same(family['real_input_sources'],trusted.source_snapshot(),'preview physical sources changed')
 selection=read('selection.json');models=read('model-payloads.json')
 from validation.suffix5.preview_selection import select_preview
 from validation.suffix5.calibration import select_calibration
 suffix_census.same(selection,select_preview(logical,trusted),'preview static selection changed')
 selected=select_calibration(selection,models)
 selected.update(preview_summary_sha256=args.preview_summary_sha,preview_return_sha256=args.preview_return_sha,
  preview_manifest_sha256=accepted['verified_manifest_sha256'],preview_source_sha256=args.preview_source_sha,
  selection_file=files['selection.json'],model_payloads_file=files['model-payloads.json'])
 before();return selected,models,root/'model-payloads.json'
