"""Tiny schema probes and optional metadata-only original-population checks.

Tiny rows are validator fixtures, never replacement A/B cases or solver inputs.
Set HIROUTE_FROZEN_AB_ROOT to the extracted original relative-path tree.
"""
from copy import deepcopy
from dataclasses import FrozenInstanceError
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from timecut5.frozen_ab_registry import (
    MAX_SOURCE_BYTES, SOURCE_PINS, FrozenCase, HierVariant, SourceArtifact,
    SourcePin, _case_rows, _expectation, _historical_rows, _read_source,
    load_frozen_ab_registry,
)


def blob(value):
    return (json.dumps(value, sort_keys=True) + "\n").encode()


def tiny_case():
    return dict(case_id="schema_fixture_only", H_ref=4, origin="o", destination="z",
                start_time_s="0", initial_energy_kwh=2, capacity_kwh=5,
                minimum_energy_kwh=0, reserve_kwh=0, consumption_kwh_per_m="1/2",
                overhead_s=1, lambda_stop_s=0, schedule=None, sites={"x": ["C"]},
                charging_segments=[[0, 5, 2, 0]],
                edges=[dict(source="o", target="z", time_s=1, length_m=1)],
                independent_expected=dict(status="attained_optimum", J="1", Q_total="0",
                                          H=0, site_action_tuple=[]))


def artifact(value, population="A", count=1):
    raw = blob(value)
    return SourceArtifact(SourcePin("tiny.json", hashlib.sha256(raw).hexdigest(), population, count), raw)


class TestFrozenABSchema(unittest.TestCase):
    def test_tiny_exact_types_and_metadata_are_preserved(self):
        row = tiny_case()
        row["metadata"] = {"kept": True}
        self.assertEqual(_case_rows(blob([row])), [row])
        self.assertIs(type(_case_rows(blob([row]))[0]["initial_energy_kwh"]), int)

    def test_duplicate_case_and_json_keys(self):
        row = tiny_case()
        with self.assertRaisesRegex(ValueError, "Duplicate case ID"):
            _case_rows(blob([row, row]))
        with self.assertRaisesRegex(ValueError, "Duplicate JSON key"):
            _case_rows(b'[{"case_id":"one","case_id":"two"}]')

    def test_malformed_missing_and_nonfinite_json(self):
        for raw in (b'{', b'{}', b'[null]', b'[{"x":NaN}]', b'[{"x":Infinity}]', b'[{"x":1e999}]'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                _case_rows(raw)
        for key in tiny_case():
            row = tiny_case()
            del row[key]
            with self.subTest(missing=key), self.assertRaisesRegex(ValueError, "Missing required case fields"):
                _case_rows(blob([row]))

    def test_type_aliases_are_rejected(self):
        for value in (True, False, 4.0, "4", None):
            row = tiny_case()
            row["H_ref"] = value
            with self.subTest(H_ref=value), self.assertRaisesRegex(ValueError, "H_ref=4"):
                _case_rows(blob([row]))
        for value in (True, False, 1.5, "1/0", "not-a-rational"):
            row = tiny_case()
            row["start_time_s"] = value
            with self.subTest(scalar=value), self.assertRaises(ValueError):
                _case_rows(blob([row]))
        for value in (False, 0.0, "0"):
            row = tiny_case()
            row["independent_expected"]["H"] = value
            with self.subTest(H=value), self.assertRaisesRegex(ValueError, "integer H"):
                _case_rows(blob([row]))

    def test_bad_nested_shapes_capabilities_and_edge_ids(self):
        for key, value in (("sites", {"x": ["C", "C"]}), ("sites", {"x": [True]}),
                           ("schedule", {"a": 0, "b": 1}), ("charging_segments", [[0, 1, 2]]),
                           ("edges", [None]), ("edges", [{"source": True}])):
            row = tiny_case()
            row[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                _case_rows(blob([row]))
        row = tiny_case()
        row["edges"][0]["edge_id"] = "same"
        row["edges"].append(deepcopy(row["edges"][0]))
        with self.assertRaisesRegex(ValueError, "Duplicate edge ID"):
            _case_rows(blob([row]))

    def test_all_historical_statuses_and_strict_key_shapes(self):
        for value in (tiny_case()["independent_expected"],
                      dict(status="primary_unattained", primary_infimum="4"),
                      dict(status="secondary_unattained", J="14", secondary_infimum="0"),
                      dict(status="infeasible_within_H_ref")):
            self.assertEqual(_expectation(value)["status"], value["status"])
        for value in ({}, {"status": []}, {"status": "PASS"},
                      {"status": "attained_optimum"},
                      {"status": "infeasible_within_H_ref", "J": 1}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                _expectation(value)

    def test_historical_duplicate_missing_and_alias_rows(self):
        row = dict(case_id="schema_fixture_only", H_ref=4, population="h4", status="attained_optimum",
                   key_or_infimum=tiny_case()["independent_expected"])
        with self.assertRaisesRegex(ValueError, "Duplicate historical case ID"):
            _historical_rows(artifact(dict(case_rows=[row, row]), count=2))
        for name in ("case_id", "H_ref", "key_or_infimum"):
            modified = deepcopy(row)
            del modified[name]
            with self.subTest(missing=name), self.assertRaises(ValueError):
                _historical_rows(artifact(dict(case_rows=[modified])))
        for h_ref in (True, 4.0, "4"):
            with self.subTest(H_ref=h_ref), self.assertRaises(ValueError):
                _historical_rows(artifact(dict(case_rows=[dict(row, H_ref=h_ref)])))
        b_row = dict(case_id="schema_fixture_only", status="attained_optimum", key=["1", "0", False, []])
        with self.assertRaisesRegex(ValueError, "integer H"):
            _historical_rows(artifact(dict(cases=[b_row]), population="B"))
        del b_row["key"]
        with self.assertRaisesRegex(ValueError, "Missing historical B key"):
            _historical_rows(artifact(dict(cases=[b_row]), population="B"))

    def test_case_bytes_and_historical_expected_are_separate_and_immutable(self):
        source = artifact([tiny_case()])
        historical = artifact(dict(case_rows=[]))
        # Deliberate mismatch proves registry expectations do not substitute embedded metadata.
        expected = _expectation(dict(status="primary_unattained", primary_infimum="4"))
        case = FrozenCase("schema_fixture_only", "A", 4, source, 0, historical, expected)
        self.assertEqual(case.historical_expected["status"], "primary_unattained")
        self.assertEqual(case.original_case()["independent_expected"]["status"], "attained_optimum")
        changed = case.original_case()
        changed["H_ref"] = 99
        self.assertEqual(case.original_case()["H_ref"], 4)
        with self.assertRaises(TypeError):
            case.historical_expected["status"] = "PASS"
        with self.assertRaises(FrozenInstanceError):
            case.H_ref = 99
        self.assertEqual(HierVariant(case, False).variant_id, "schema_fixture_only::HIER::D-off")
        for value in (0, 1, "off", None):
            with self.subTest(dominance=value), self.assertRaisesRegex(ValueError, "boolean dominance"):
                HierVariant(case, value)
        with self.assertRaisesRegex(ValueError, "HIER-only"):
            HierVariant(case, False, "FLAT")


class TestFrozenABFileBoundary(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = artifact([tiny_case()])

    def test_reads_and_hashes_original_bytes_without_rewriting(self):
        path = self.root / self.source.pin.path
        path.write_bytes(self.source.raw_bytes)
        self.assertEqual(_read_source(self.root, self.source.pin), self.source)
        self.assertEqual(path.read_bytes(), self.source.raw_bytes)
        path.write_bytes(self.source.raw_bytes + b" ")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            _read_source(self.root, self.source.pin)

    def test_missing_file_and_missing_original_population_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "Missing"):
            _read_source(self.root, self.source.pin)
        with self.assertRaisesRegex(ValueError, "Missing"):
            load_frozen_ab_registry(self.root)

    def test_leaf_and_directory_symlinks_are_rejected(self):
        target = self.root / "target.json"
        target.write_bytes(self.source.raw_bytes)
        (self.root / "tiny.json").symlink_to(target)
        with self.assertRaisesRegex(ValueError, "symlinked"):
            _read_source(self.root, self.source.pin)
        (self.root / "linked").symlink_to(self.root, target_is_directory=True)
        pin = SourcePin("linked/target.json", self.source.pin.sha256, "A", 1)
        with self.assertRaisesRegex(ValueError, "symlinked"):
            _read_source(self.root, pin)
        with self.assertRaisesRegex(ValueError, "symlinked"):
            _read_source(self.root / "linked", self.source.pin)

    def test_nonregular_and_oversized_sources_are_rejected(self):
        path = self.root / "tiny.json"
        os.mkfifo(path)
        with self.assertRaisesRegex(ValueError, "Regular nonsymlink"):
            _read_source(self.root, self.source.pin)
        path.unlink()
        with path.open("wb") as stream:
            stream.truncate(MAX_SOURCE_BYTES + 1)
        with self.assertRaisesRegex(ValueError, "byte limit"):
            _read_source(self.root, self.source.pin)

    def test_input_root_ancestor_symlink_is_rejected(self):
        actual = self.root / "actual"
        nested = actual / "nested"
        nested.mkdir(parents=True)
        (nested / "tiny.json").write_bytes(self.source.raw_bytes)
        link = self.root / "ancestor-link"
        link.symlink_to(actual, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlinked"):
            _read_source(link / "nested", self.source.pin)
        self.assertEqual(_read_source(nested, self.source.pin), self.source)


@unittest.skipUnless(os.environ.get("HIROUTE_FROZEN_AB_ROOT"), "Set HIROUTE_FROZEN_AB_ROOT to recovered original files")
class TestOriginalFrozenABRegistry(unittest.TestCase):
    def test_original_92_cases_and_184_variants_metadata_only(self):
        root = Path(os.environ["HIROUTE_FROZEN_AB_ROOT"])
        before = {p.path: (root / p.path).read_bytes() for p in SOURCE_PINS}
        registry = load_frozen_ab_registry(root)
        summary = registry.summary()
        self.assertEqual(summary["populations"], {"A": 28, "B": 64})
        self.assertEqual(len(registry.variants), 184)
        self.assertEqual(len({v.variant_id for v in registry.variants}), 184)
        self.assertEqual(summary["historical_expected_status_counts"], {
            "attained_optimum": 72, "infeasible_within_H_ref": 18,
            "primary_unattained": 1, "secondary_unattained": 1,
        })
        for case in registry.cases:
            self.assertEqual(case.H_ref, 4)
            self.assertIs(type(case.H_ref), int)
            self.assertEqual(case.original_case()["case_id"], case.case_id)
            variants = [v for v in registry.variants if v.case.case_id == case.case_id]
            self.assertEqual([(v.mode, v.dominance) for v in variants], [("HIER", False), ("HIER", True)])
        self.assertFalse(any(c.case_id.startswith("A04") for c in registry.cases))
        a15 = next(c for c in registry.cases if c.case_id == "A15_waiting_erases_prefix_time_advantage")
        self.assertEqual(a15.historical_expected["J"], "44950")
        self.assertEqual(a15.historical_expected["site_action_tuple"], (
            ("4r:node/2", "C"), ("4r:node/3", "C"), ("4r:node/4", "S")))
        self.assertFalse(summary["solver_executed"])
        self.assertFalse(summary["current_acceptance_established"])
        self.assertEqual(before, {p.path: (root / p.path).read_bytes() for p in SOURCE_PINS})
        self.assertEqual(before, {s.pin.path: s.raw_bytes for s in registry.sources})

    def test_full_registry_load_with_solver_imports_forbidden(self):
        script = '''
import builtins, sys
original_import = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.startswith(('scipy', 'validation')) or name in (
        'bounded', 'hierarchy', 'coalesced_solver', 'pwa', 'probe',
        'timecut5.bounded', 'timecut5.hierarchy', 'timecut5.coalesced_solver',
        'timecut5.pwa', 'timecut5.probe'):
        raise RuntimeError('Forbidden solver import: ' + name)
    return original_import(name, *args, **kwargs)
builtins.__import__ = guarded
from timecut5.frozen_ab_registry import load_frozen_ab_registry
registry = load_frozen_ab_registry(sys.argv[1])
assert len(registry.cases) == 92 and len(registry.variants) == 184
print('metadata-only original registry loaded; solver imports forbidden')
'''
        result = subprocess.run([sys.executable, "-c", script, os.environ["HIROUTE_FROZEN_AB_ROOT"]],
                                capture_output=True, text=True, check=True)
        self.assertIn("solver imports forbidden", result.stdout)


if __name__ == "__main__":
    unittest.main()
