"""Offline acquisition contract tests; never download OSM or import the geo stack."""
import ast
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest


def acquisition_function(root, download):
    source = Path(__file__).resolve().parents[1] / 'scripts/prepare_regional_data.py'
    tree = ast.parse(source.read_text())
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == 'acquire_sources')
    namespace = dict(ROOT=root, Path=Path, json=json, hashlib=hashlib,
        subprocess=SimpleNamespace(run=download),
        snapshot_timestamp=lambda path: 'frozen-time',
        sha256=lambda path: hashlib.sha256(path.read_bytes()).hexdigest(),
        configs=lambda: ({}, {}), verified_dataset=lambda data: dict(
            source_url='https://download.geofabrik.de/europe/slovenia.osm.pbf',
            sha256='si-sha', size_bytes=2, osm_snapshot_timestamp='frozen-time',
            geofabrik_md5='si-md5'),
        immutable_install=lambda source, destination: source.rename(destination))
    from datetime import datetime, timezone
    namespace.update(datetime=datetime, timezone=timezone)
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), namespace)
    return namespace['acquire_sources']


class RegionalSourcePins(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.payload = b'fake frozen pbf'
        self.url = 'https://download.geofabrik.de/europe/test-260929.osm.pbf'
        self.pin = dict(url=self.url, path='raw/test-260929.osm.pbf',
            sha256=hashlib.sha256(self.payload).hexdigest(), size_bytes=len(self.payload),
            snapshot_timestamp='frozen-time', publisher_md5=hashlib.md5(self.payload).hexdigest())
        self.pins = dict(sources=[self.pin, dict(
            url='https://download.geofabrik.de/europe/slovenia.osm.pbf',
            sha256='si-sha', size_bytes=2, snapshot_timestamp='frozen-time')])
        self.config = dict(source_pins='pins.json', source_dir='raw', results_dir='results',
            sources=['europe/test-260929.osm.pbf'],
            source_sizes_bytes={'test-260929.osm.pbf':len(self.payload)},
            snapshot_timestamp='frozen-time', slovenia_source='raw/slovenia.osm.pbf')
        self.calls = []
        self.write_pins()

    def write_pins(self):
        (self.root/'pins.json').write_text(json.dumps(self.pins))

    def download(self, command, check):
        self.calls.append(command)
        if command[-1].endswith('.md5'):
            Path(command[command.index('-o')+1]).write_text(hashlib.md5(self.payload).hexdigest())
        else:
            Path(command[command.index('--output')+1]).write_bytes(self.payload)

    def run_acquire(self):
        acquisition_function(self.root, self.download)(self.config)

    def test_missing_pins_rejected_before_network(self):
        (self.root/'pins.json').unlink()
        with self.assertRaises(FileNotFoundError): self.run_acquire()
        self.assertFalse(self.calls)

    def test_config_mismatch_rejected_before_network(self):
        self.config['snapshot_timestamp'] = 'different'
        with self.assertRaisesRegex(ValueError, 'configuration'): self.run_acquire()
        self.assertFalse(self.calls)

    def test_receipt_cannot_replace_input_pin(self):
        (self.root/'results').mkdir()
        row = dict(self.pin, sha256='0'*64)
        (self.root/'results/sources.json').write_text(json.dumps(dict(sources=[row])))
        with self.assertRaisesRegex(ValueError, 'receipt'): self.run_acquire()
        self.assertFalse(self.calls)

    def test_publisher_md5_cannot_replace_sha_pin(self):
        self.pin['sha256'] = '0'*64
        self.write_pins()
        with self.assertRaisesRegex(ValueError, 'SHA256'): self.run_acquire()
        self.assertFalse((self.root/self.pin['path']).exists())

    def test_exact_download_and_repeat(self):
        self.run_acquire()
        self.assertEqual((self.root/self.pin['path']).read_bytes(), self.payload)
        count = len(self.calls)
        self.run_acquire()
        self.assertEqual(len(self.calls), count)

    def test_exact_restored_file_without_receipt(self):
        path = self.root/self.pin['path']; path.parent.mkdir()
        path.write_bytes(self.payload)
        self.run_acquire()
        self.assertFalse(self.calls)
        receipt = json.loads((self.root/'results/sources.json').read_text())
        self.assertEqual(receipt['sources'][0]['sha256'], self.pin['sha256'])

    def test_forged_restored_file_rejected(self):
        path = self.root/self.pin['path']; path.parent.mkdir()
        path.write_bytes(b'wrong')
        with self.assertRaisesRegex(ValueError, 'Unverified'): self.run_acquire()
        self.assertFalse(self.calls)


if __name__ == '__main__':
    unittest.main()
