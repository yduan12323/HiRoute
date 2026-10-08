"""Source/version/loader CLI boundaries, using private tiny Git repositories."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from tools.receipt_epoch import origin as implementation


class OriginTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.tool=self.root/'tool';self.verifier=self.root/'verifier'
        for root in (self.tool,self.verifier):
            root.mkdir();subprocess.run(['git','init','-q',str(root)],check=True)
        for source in Path(implementation.__file__).parent.glob('*.py'):
            target=self.tool/'tools/receipt_epoch'/source.name;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(source.read_bytes())
        for relative,raw in {'validation/__init__.py':b'', 'src/timecut5/__init__.py':b'',
            'src/timecut5/fact.py':b'value=7\n',
            'experiments/time_cut_v2/recorded_real/plan.py':
                b'from pathlib import Path\nROOT=Path(__file__).resolve().parents[3]\n'}.items():
            target=self.verifier/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        self.commits=[]
        for root in (self.tool,self.verifier):
            subprocess.run(['git','-C',str(root),'add','.'],check=True)
            subprocess.run(['git','-C',str(root),'-c','user.name=EpochFixture','-c','user.email=fixture@example.invalid',
                '-c','commit.gpgsign=false','commit','-qm','Synthetic source boundary'],check=True)
            self.commits.append(subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip())
        path=self.tool/'tools/receipt_epoch/origin.py'
        spec=importlib.util.spec_from_file_location('epoch_origin_fixture',path)
        self.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)

    def facts(self):
        import time
        return self.module.inspect(self.tool,self.commits[0],self.verifier,self.commits[1],time.monotonic()+10)

    def command(self):
        return [sys.executable,'-I','-B',str(self.tool/'tools/receipt_epoch/driver.py'),'fingerprint',
            '--tool-root',str(self.tool),'--tool-commit',self.commits[0],
            '--verifier-root',str(self.verifier),'--verifier-commit',self.commits[1]]

    def test_separate_roots_exact_git_source_and_interpreter_fingerprint(self):
        facts,_,_,_=self.facts();bound=self.module.SourceBinding(facts)
        self.assertNotEqual(facts['tool_root'],facts['verifier_root'])
        self.assertTrue(bound.pins);self.assertEqual(facts['python_realpath'],str(Path(sys.executable).resolve()))
        out=subprocess.run(self.command(),capture_output=True,text=True,timeout=15)
        self.assertEqual(out.returncode,0,out.stderr)
        self.assertEqual(json.loads(out.stdout),facts)

    def test_modified_source_new_module_and_symlink_cannot_match_fixed_commit(self):
        path=self.verifier/'src/timecut5/fact.py';original=path.read_bytes()
        for mutation in ('change','add','link'):
            if mutation=='change':path.write_bytes(b'value=8\n')
            elif mutation=='add':(path.parent/'foreign.py').write_bytes(b'bad=True\n')
            else:path.unlink();path.symlink_to(self.verifier/'validation/__init__.py')
            with self.subTest(mutation=mutation),self.assertRaises((ValueError,OSError)):
                self.facts()
            if mutation=='add':(path.parent/'foreign.py').unlink()
            else:
                path.unlink();path.write_bytes(original)

    def test_wrong_commit_digest_binary_and_actual_module_origin_reject(self):
        facts,_,_,_=self.facts()
        for key in ('tool_source_sha','verifier_source_sha','verifier_import_sha','python_sha'):
            bad=dict(facts);bad[key]='0'*64
            with self.subTest(key=key),self.assertRaises(ValueError):self.module.SourceBinding(bad)
        bound=self.module.SourceBinding(facts)
        import time
        with self.assertRaisesRegex(ValueError,'outside reviewed source pins|outside reviewed source namespace|root/origin'):
            bound.phase_check(time.monotonic()+10)
        with self.assertRaises(ValueError):
            self.module.inspect(self.tool,'0'*40,self.verifier,self.commits[1],time.monotonic()+10)

    def test_execute_exact_consumed_bytes_not_a_later_path_reread(self):
        _,_,pins,_=self.facts();path=self.verifier/'src/timecut5/fact.py'
        original=self.module.consume
        def swapped(*args,**kwargs):
            result=original(*args,**kwargs);path.write_bytes(b'value=999\n');return result
        loader=self.module.VerifiedLoader(path,pins['src/timecut5/fact.py'])
        module=types.ModuleType('fixture_fact')
        with patch.object(self.module,'consume',side_effect=swapped):loader.exec_module(module)
        self.assertEqual(module.value,7)
        with self.assertRaises(ValueError):loader.exec_module(types.ModuleType('again'))

    def test_native_unknown_module_and_unattested_direct_cli_reject(self):
        _,_,pins,_=self.facts();finder=self.module.VerifierFinder(self.verifier,pins)
        with self.assertRaises(ImportError):finder.find_spec('timecut5._native')
        command=self.command();command.remove('-I')
        out=subprocess.run(command,capture_output=True,text=True,timeout=15)
        self.assertNotEqual(out.returncode,0);self.assertIn('python -I -B',out.stderr)

    def test_original_root_loader_ignores_shared_bytecode_and_refuses_root_reassignment(self):
        facts,_,_,_=self.facts()
        script = '''
import importlib.util,json,pathlib,py_compile,sys,time
tool,verifier,contract=sys.argv[1:]
path=pathlib.Path(tool)/'tools/receipt_epoch/origin.py'
spec=importlib.util.spec_from_file_location('reviewed_origin',path)
origin=importlib.util.module_from_spec(spec);spec.loader.exec_module(origin)
bound=origin.SourceBinding(json.loads(contract))
source=pathlib.Path(verifier)/'src/timecut5/fact.py'
bad=pathlib.Path(tool)/'bad.py';bad.write_text('value=999\\n')
py_compile.compile(str(bad),cfile=importlib.util.cache_from_source(str(source)),dfile=str(source),doraise=True)
sys.meta_path.insert(0,origin.VerifierFinder(verifier,bound._imported))
from experiments.time_cut_v2.recorded_real import plan
import timecut5.fact,validation
if timecut5.fact.value!=7:raise RuntimeError('shared bytecode consumed')
bound.phase_check(time.monotonic()+10)
for change in ('root','namespace'):
 if change=='root':plan.ROOT=pathlib.Path(tool)
 else:plan.ROOT=pathlib.Path(verifier);validation.__path__=[tool]
 try:bound.phase_check(time.monotonic()+10)
 except ValueError:pass
 else:raise RuntimeError('forged verifier origin accepted')
print('verified original roots and exact source bytes')
'''
        out=subprocess.run([sys.executable,'-I','-B','-c',script,str(self.tool),str(self.verifier),json.dumps(facts)],
                           capture_output=True,text=True,timeout=15)
        self.assertEqual(out.returncode,0,out.stderr)
        self.assertIn('verified original roots',out.stdout)


if __name__=='__main__':unittest.main()
