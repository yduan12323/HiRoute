"""Small exact-count/progress checks with the existing evidence accountant."""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from experiments.time_cut_v2.recorded_real.full_progress import FullProgress,expected_files,MAX_RECORDS
from experiments.time_cut_v2.recorded_real.runtime import BoundedEvidenceWriter,verify_manifest
from validation.capture5.query_dag_digest import QueryDagEncoder

class FullCachedProgress(unittest.TestCase):
 def test_bounded_nested_progress_cold_replays_with_exact_manifest(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)/'out'
   with BoundedEvidenceWriter(root,16*1024**2,profile_name='tiny-progress') as writer:
    progress=FullProgress(writer);encoder=QueryDagEncoder([{'ancestry_nodes':{'n':{'x':'a'}}}]*4)
    encoder.measure_lengths();progress.stage('query_digest',encoder=encoder);encoder.progress=progress.tick
    encoder.digest();progress.stage('finalization_returned',metrics=encoder.snapshot())
    def stream():
     for i in progress.rows('callbacks',iter(range(4)),4):yield str(i).encode()
    writer.write('receipts.bin',stream());index=progress.finish()
    self.assertEqual(expected_files(writer),{r['path'] for r in writer.files if r['path'].startswith('progress/')})
    self.assertLess(len(progress.records),MAX_RECORDS);writer.finalize()
   verify_manifest(root,expected_cap_bytes=16*1024**2,expected_profile_name='tiny-progress')
   rows=[json.loads((root/r['path']).read_bytes()) for r in progress.records]
   self.assertEqual(rows[-1]['counters'],{'completed':4,'total':4})
   self.assertEqual(rows[-1]['query_digest']['logical_query_bytes_remaining'],0)
 def test_time_throttle_and_caps(self):
  with tempfile.TemporaryDirectory() as d:
   with BoundedEvidenceWriter(Path(d)/'out',16*1024**2,profile_name='tiny-progress') as writer:
    progress=FullProgress(writer)
    with patch('experiments.time_cut_v2.recorded_real.full_progress.time.monotonic',return_value=1):
     progress.stage('query_digest')
     for _ in range(100):progress.tick()
    self.assertEqual(len(progress.records),1)
    with patch('experiments.time_cut_v2.recorded_real.full_progress.MAX_RECORDS',1),self.assertRaisesRegex(ValueError,'record limit'):progress.stage('other')
 def test_progress_manifest_rejects_noncontiguous_records_and_type_aliases(self):
  with tempfile.TemporaryDirectory() as d:
   with BoundedEvidenceWriter(Path(d)/'out',16*1024**2,profile_name='tiny-progress') as writer:
    progress=FullProgress(writer);progress.stage('query_digest');progress.finish();expected_files(writer)
    from experiments.time_cut_v2.recorded_real import plan
    original=plan.load(writer.root/'progress/index.json');bad=dict(original,record_count=True)
    with patch('experiments.time_cut_v2.recorded_real.full_progress.binding.load',return_value=bad),self.assertRaisesRegex(ValueError,'index changed'):expected_files(writer)
    record=next(r for r in writer.files if r['path']=='progress/000000.json');record['path']='progress/000001.json'
    with self.assertRaisesRegex(ValueError,'sequence changed'):expected_files(writer)

 def test_progress_fits_unchanged_runtime_file_inventory(self):
  from experiments.time_cut_v2.recorded_real.runtime import MAX_FILES
  from experiments.time_cut_v2.recorded_real.parallel_replay import REPLAY_FILES,EXTRA_FILES
  self.assertLessEqual(MAX_RECORDS+len(REPLAY_FILES|EXTRA_FILES)+1,MAX_FILES)

 def test_length_measurement_does_not_change_hash(self):
  rows=[{'ancestry_nodes':{'n':{'parents':['x']*100}}}]*7
  a=QueryDagEncoder(rows);b=QueryDagEncoder(rows);sizes=b.measure_lengths()
  self.assertEqual(a.digest(),b.digest());self.assertEqual(sizes['total_bytes'],b.snapshot()['logical_query_bytes'])
if __name__=='__main__':unittest.main()
