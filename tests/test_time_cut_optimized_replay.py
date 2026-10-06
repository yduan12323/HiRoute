"""Unconditional incumbent verification, including optimized Python runtimes."""
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
PROGRAM='''
from timecut5.bounded import replay_witness
from timecut5.hierarchy import solve_hierarchical
from timecut5.probe import Event,State,Witness
case=dict(H_ref=1,origin='o',destination='z',start_time_s=0,
 initial_energy_kwh=2,capacity_kwh=5,minimum_energy_kwh=0,reserve_kwh=0,
 consumption_kwh_per_m=1,overhead_s=1,lambda_stop_s=0,schedule=None,
 sites={'x':['C']},charging_segments=[[0,5,1,0]],edges=[
 dict(source='o',target='z',time_s=1,length_m=5),
 dict(source='o',target='x',time_s=1,length_m=1),
 dict(source='x',target='z',time_s=1,length_m=1)])
forged=Witness(0,2,-2,(),State('z',0,0),(Event('initial','o',0,0,2,2),))
for call in (lambda:replay_witness(case,forged),lambda:solve_hierarchical(case,incumbent=forged)):
 try:call()
 except AssertionError:pass
 else:raise RuntimeError('Forged incumbent accepted')
result=solve_hierarchical(case).canonical()['result']
if result != {'status':'primary_unattained','primary_infimum':3}:
 raise RuntimeError(str(result))
print('rejected forged incumbent; exact primary infimum 3 preserved')
'''


class TestOptimizedReplay(unittest.TestCase):
    def test_verifier_and_hierarchy_normal_optimized_and_double_optimized(self):
        for flags in ([],['-O'],['-OO']):
            with self.subTest(flags=flags):
                env=dict(os.environ,PYTHONPATH=str(ROOT/'src'))
                result=subprocess.run([sys.executable,*flags,'-c',PROGRAM],env=env,text=True,capture_output=True)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertIn('rejected forged incumbent',result.stdout)


if __name__=='__main__':unittest.main()
