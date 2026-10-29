"""Cold optional legacy routing imports do not pull in graph/acquisition dependencies."""
from pathlib import Path
import os
import subprocess
import sys
import unittest


class ImportBoundaryTests(unittest.TestCase):
    def child(self, body):
        # Isolated interpreter: explicitly add only the optional legacy test source.
        legacy_root = Path(os.environ.get(
            'HIROUTE_LEGACY_TEST_SOURCE_ROOT',
            Path(__file__).resolve().parents[2] / 'src')).resolve()
        script = """
import resource
resource.setrlimit(resource.RLIMIT_CPU, (10, 15))
from pathlib import Path
import importlib, importlib.abc, sys
legacy_root = Path(%r)
sys.path.insert(0, str(legacy_root))
class NoGraphDependencies(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'opportunity', 'envelope', 'graph', 'igraph',
                'pyarrow', 'pyproj', 'geopandas', 'shapely', 'pyrosm', 'yaml'}:
            raise ModuleNotFoundError('Blocked unused graph dependency: ' + fullname,
                                      name=fullname)
sys.meta_path.insert(0, NoGraphDependencies())
""" % str(legacy_root)
        script += "\nif sys.flags.optimize != %d: raise RuntimeError('Child optimization differs')\n" % sys.flags.optimize
        script += body
        flags = ['-' + 'O' * sys.flags.optimize] if sys.flags.optimize else []
        result = subprocess.run([sys.executable, '-I', *flags, '-B', '-c', script],
                                text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_cold_optional_routing_and_primitives_without_graph_stack(self):
        self.child("""
import microplan, microplan.models, microplan.routing, timecut5.routing_config
from microplan import Gateway, RegionGateways, Task, PlanBatch
for module in (microplan, microplan.models, microplan.routing, timecut5.routing_config):
    if not Path(module.__file__).resolve().is_relative_to(legacy_root):
        raise RuntimeError('Optional legacy source root differs')
if Gateway(1, True, False, 2).node != 1 or Task('tiny', frozenset()).name != 'tiny':
    raise RuntimeError('Public primitive export differs')
if timecut5.routing_config.RoutingConfig().search_mode != 'full':
    raise RuntimeError('Default routing mode changed')
if 'generate_plans' not in dir(microplan) or 'generate_plans' not in microplan.__all__:
    raise RuntimeError('Public lazy export missing')
if any(name.split('.')[0] in {'opportunity', 'envelope', 'graph'} for name in sys.modules):
    raise RuntimeError('Unused graph stack loaded')
if microplan.models.MicroPlan.__annotations__['opportunity_ids'] != 'tuple[OpportunityId, ...]':
    raise RuntimeError('Postponed type annotation changed')
try:
    microplan.not_a_public_export
except AttributeError:
    pass
else:
    raise RuntimeError('Unknown export must raise AttributeError')
""")

    def test_generation_is_lazy_but_retains_real_runtime_dependency(self):
        self.child("""
import microplan
if 'microplan.generation' in sys.modules:
    raise RuntimeError('Generation loaded eagerly')
for import_kind in ('public', 'submodule'):
    try:
        if import_kind == 'public':
            from microplan import generate_plans
        else:
            importlib.import_module('microplan.generation')
    except ModuleNotFoundError as error:
        if error.name != 'envelope':
            raise RuntimeError('Unexpected generation dependency failure') from error
    else:
        raise RuntimeError('Generation runtime dependency was silently bypassed')
    if 'generate_plans' in microplan.__dict__:
        raise RuntimeError('Failed lazy import must not cache a placeholder')
""")


if __name__ == '__main__':
    unittest.main(verbosity=2)
