"""Mock-only reconstruction checks; production is only an evidence producer."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from fractions import Fraction as F
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from validation.family5 import checker as family_base
from validation.family5 import independent_oracle_v2 as oracle
from validation.trace5.checker import CheckedTrace
from validation.real5_v2 import prepare_real_case, verify_bundle, verify_trace, check_witness, reconstruct
from validation.real5_v2.family import _verify_bundle
from validation.real5_v2.input import decode_binary64
from validation.real5_v2.physical_state import verify_physical_states


def blob(value):
    return family_base.canonical(value).encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def prepare(row):
    return prepare_real_case(row["query"], sha(blob(row["query"])), blob(row["table"]),
                             row["table_sha256"], blob(row["original_tree"]), row["original_tree_sha256"])


def repin(row):
    row["original_tree_sha256"] = sha(blob(row["original_tree"]))
    row["table"]["hierarchy_sha256"] = row["original_tree_sha256"]
    row["table_sha256"] = sha(blob(row["table"]))
    return row


def capture(row, dominance):
    # These imports are forbidden in the separate consumer subprocess below.
    from timecut5.real_legs import ImmutableLegTable, restrict_frozen_tree
    from timecut5.real_adapter import solve_hierarchical_real
    from timecut5.provenance import Recorder
    from timecut5.invocation_trace import InvocationTrace
    table = ImmutableLegTable.from_bytes(blob(row["table"]), row["table_sha256"])
    tree = restrict_frozen_tree(blob(row["original_tree"]), row["original_tree_sha256"], list(table.sites))
    with Recorder() as recorder, InvocationTrace(recorder) as trace:
        solve_hierarchical_real(row["query"], table, tree, dominance=dominance)
    wire, bundle = trace.export(), recorder.export()
    bundle["roots"] = wire["events"][-1]["payload"]["terminal_families"]
    return dict(trace=wire, bundle=bundle)


def node(bundle, kind, parents, piece, params):
    value = dict(kind=kind, parents=parents, output=family_base._plain(piece.dump()), params=params)
    ident = family_base.digest(value)
    bundle["nodes"][ident] = value
    return ident


def batch(bundle, kind, parents, outputs, params):
    value = dict(kind=kind, parents=parents, outputs=outputs, params=params)
    bundle["batches"].append(value)
    bundle["batch_ids"].append(family_base.digest(value))


def drive(bundle, parent, target, physics):
    piece = family_base._piece(bundle["nodes"][parent]["output"])
    duration, consumption, *_ = physics.legs[piece.state[0], target]
    params = dict(site=target, duration=str(duration), consumption=str(consumption),
                  floor=str(physics.reserve if target == physics.destination else physics.floor))
    outputs = [node(bundle, "drive", [parent], p, params) for p in oracle.transform([piece], "D", params)]
    batch(bundle, "drive", [parent], outputs, params)
    return outputs


def stop(bundle, parent, site, physics):
    piece = family_base._piece(bundle["nodes"][parent]["output"])
    params = dict(effect="C", site=site, h=str(physics.overhead), a="0", b="0", D="0",
                  curve=family_base._plain(physics.curve))
    outputs = []
    for incoming in physics.curve:
        for outgoing in physics.curve:
            individual = dict(params, in_segment=family_base._plain(incoming), out_segment=family_base._plain(outgoing))
            outputs.extend(node(bundle, "stop", [parent], p, individual)
                           for p in family_base._regime(piece, individual))
    batch(bundle, "stop", [parent], outputs, params)
    return outputs


class RecoveredRealFamily(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = json.loads((ROOT/"results/milestone_5_real_leg_contract/mock_solver_cases.json").read_text())
        cls.captures = {(row["case_id"], d): capture(row, d) for row in cls.rows for d in (False, True)}

    def test_published_mock_cases_both_dominance_modes_and_class_identity(self):
        for row in self.rows:
            for dominance in (False, True):
                with self.subTest(case=row["case_id"], dominance=dominance):
                    data = self.captures[row["case_id"], dominance]
                    checked = verify_trace(data["trace"], data["bundle"], prepare(row))
                    self.assertIs(type(checked), CheckedTrace)
                    self.assertIs(type(checked.bundle), family_base.CheckedBundle)
                    self.assertTrue(checked.summary["verified"])
                    result = family_base._plain(checked.summary["canonical"])["result"]
                    for key, value in row["independent_expected"].items():
                        self.assertEqual(result[key], value)
                    self.assertFalse(checked.summary["literal_G8_closed"])

    def test_separately_pinned_sources_and_binary64_provenance(self):
        row = self.rows[0]
        args = [row["query"], sha(blob(row["query"])), blob(row["table"]), row["table_sha256"],
                blob(row["original_tree"]), row["original_tree_sha256"]]
        for index in (1, 3, 5):
            changed = list(args)
            changed[index] = "0"*64
            with self.subTest(pin=index), self.assertRaises(ValueError):
                prepare_real_case(*changed)
        record = {"hex": (0.1).hex(), "ratio": [str(v) for v in (0.1).as_integer_ratio()]}
        self.assertEqual(decode_binary64(record), (F(*(.1).as_integer_ratio()), (.1).hex()))
        record["ratio"] = ["1", "10"]
        with self.assertRaisesRegex(ValueError, "mismatch"):
            decode_binary64(record)

    def test_detached_immutable_trusted_case_and_checked_snapshot(self):
        row = deepcopy(self.rows[0])
        trusted = prepare(row)
        row["query"]["initial_energy_kwh"] = 999
        trusted.case_snapshot()["sites"].clear()
        trusted.source_snapshot()["provenance"].clear()
        self.assertNotEqual(trusted.physics.initial, 999)
        self.assertTrue(trusted.physics.sites)
        with self.assertRaises(TypeError):
            trusted.regions["id"] = 9
        with self.assertRaises(FrozenInstanceError):
            trusted.table.origin_anchor = "elsewhere"
        data = deepcopy(self.captures[self.rows[0]["case_id"], True])
        checked = verify_trace(data["trace"], data["bundle"], trusted)
        data["bundle"]["nodes"].clear()
        checked.snapshot()["events"].clear()
        self.assertTrue(checked.bundle.snapshot()["nodes"])
        self.assertTrue(checked.snapshot()["events"])

    def test_original_tree_order_empty_children_and_partition_negatives(self):
        row = deepcopy(self.rows[0])
        ids = row["original_tree"]["site_ids"]
        row["original_tree"] = dict(site_ids=ids, regions=[
            dict(parent=-1, children=[2, 1], members=[1, 0]),
            dict(parent=0, children=[], members=[]),
            dict(parent=0, children=[], members=[0, 1])])
        repin(row)
        trusted = prepare(row)
        self.assertEqual(list(trusted.regions["members"]), [ids[1], ids[0]])
        self.assertEqual([x["id"] for x in trusted.regions["children"]], [2, 1])
        for d in (False, True):
            data = capture(row, d)
            verify_trace(data["trace"], data["bundle"], trusted)
        for mutation in ("overlap", "missing", "parent", "disconnected", "bool"):
            changed = deepcopy(row)
            regions = changed["original_tree"]["regions"]
            if mutation == "overlap":
                regions[1]["members"] = [0]
            elif mutation == "missing":
                regions[2]["members"] = [0]
            elif mutation == "parent":
                regions[2]["parent"] = 1
            elif mutation == "disconnected":
                regions.append(dict(parent=-1, children=[], members=[]))
            else:
                regions[0]["members"][0] = True
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                prepare(repin(changed))

    def test_collision_cannot_drive_from_raw_site_as_another_anchor(self):
        row = self.rows[2]
        trusted = prepare(row)
        for kind in ("stop", "select", "restrict"):
            bundle = deepcopy(self.captures[row["case_id"], False]["bundle"])
            raw = next(k for k, n in bundle["nodes"].items() if n["kind"] == ("stop" if kind == "restrict" else kind)
                       and n["output"]["state"][0] == "road:z")
            if kind == "restrict":
                p = family_base._piece(bundle["nodes"][raw]["output"])
                raw = node(bundle, "restrict", [raw], p,
                           dict(domain=family_base._plain(p.dump())["domain"], reason="phase preservation"))
            drive(bundle, raw, trusted.physics.destination, trusted.physics)
            # Hashes, exact PWA algebra and textual states alone accept this attack.
            _verify_bundle(bundle, trusted.case_snapshot(), trusted.physics)
            with self.subTest(inherited_kind=kind), self.assertRaisesRegex(ValueError, "physical_action_requires_anchor_phase"):
                verify_bundle(bundle, trusted)

    def test_collision_cannot_stop_at_another_anchor(self):
        row = deepcopy(self.rows[2])
        row["table"]["sites"][0]["site_id"] = "road:o"
        row["table"]["sites"].append(dict(site_id="B", anchor_id="road:o", effects=["C"]))
        row["original_tree"]["site_ids"] = ["road:o", "B"]
        row["original_tree"]["regions"][0]["members"] = [0, 1]
        row["original_tree"]["regions"][2]["members"] = [0, 1]
        repin(row)
        trusted = prepare(row)
        bundle = capture(row, False)["bundle"]
        sources = [k for k, n in bundle["nodes"].items() if n["kind"] == "stop" and
                   n["params"]["site"] == "road:o" and n["output"]["state"][2] == 1]
        for raw in sources:
            changed = deepcopy(bundle)
            outputs = stop(changed, raw, "B", trusted.physics)
            _verify_bundle(changed, trusted.case_snapshot(), trusted.physics)
            with self.subTest(empty_image=not outputs), self.assertRaisesRegex(ValueError, "physical_(action|batch)_requires_anchor_phase"):
                verify_bundle(changed, trusted)

    def test_no_direct_terminal_leg_does_not_exclude_incoming_action(self):
        row = deepcopy(self.rows[2])
        for leg in row["table"]["legs"]:
            if leg["source_anchor"] != "road:z" and leg["target_anchor"] == "road:z":
                leg.update(reachable=False, time_s=None, actual_length_m=None)
        repin(row)
        trusted = prepare(row)
        for d in (False, True):
            data = capture(row, d)
            checked = verify_trace(data["trace"], data["bundle"], trusted)
            self.assertTrue(checked.node_queries)
            for query in checked.node_queries:
                self.assertEqual(query["classification"], "queued")
                self.assertEqual(query["onward_travel_lower_bound"], "0")
                self.assertFalse(query["leg_context"][0]["onward"]["reachable"])

    def test_own_anchor_zero_identity_allowed_but_retag_consumed_once(self):
        row = deepcopy(self.rows[2])
        row["table"]["sites"][0]["site_id"] = "road:x"
        row["original_tree"]["site_ids"] = ["road:x"]
        repin(row)
        trusted = prepare(row)
        data = capture(row, True)
        verify_trace(data["trace"], data["bundle"], trusted)
        bundle = data["bundle"]
        raw = next(k for k, n in bundle["nodes"].items() if n["kind"] == "stop")
        piece = family_base._piece(bundle["nodes"][raw]["output"])
        first = node(bundle, "retag", [raw], piece, dict(anchor="road:x"))
        verify_bundle(bundle, trusted)
        node(bundle, "retag", [first], piece, dict(anchor="road:x"))
        _verify_bundle(bundle, trusted.case_snapshot(), trusted.physics)
        with self.assertRaisesRegex(ValueError, "unconsumed_raw_site_phase"):
            verify_bundle(bundle, trusted)

    def test_comparison_rejects_equal_wire_state_at_different_anchors(self):
        from validation.trace5.checker import _dispatch_cells
        row = self.rows[2]
        trusted = prepare(row)
        bundle = deepcopy(self.captures[row["case_id"], False]["bundle"])
        raw = next(k for k,n in bundle["nodes"].items() if n["kind"] == "stop" and n["output"]["state"][0] == "road:z")
        p = family_base._piece(bundle["nodes"][raw]["output"])
        normalized = node(bundle, "retag", [raw], replace(p, state=("road:x", *p.state[1:])), dict(anchor="road:x"))
        terminal = drive(bundle, normalized, "road:z", trusted.physics)[0]
        parents = [raw, terminal]
        pieces = [family_base._piece(bundle["nodes"][ident]["output"]) for ident in parents]
        outputs = []
        for lo, hi, energy in _dispatch_cells(pieces):
            eligible = [i for i,piece in enumerate(pieces) if piece.contains(energy)]
            retained = []
            for i in eligible:
                if any(oracle.dominates(pieces[j], pieces[i], energy) for j in retained):
                    continue
                retained = [j for j in retained if not oracle.dominates(pieces[i], pieces[j], energy)]
                retained.append(i)
            for i in retained:
                piece = replace(pieces[i], lo=lo, hi=hi, lc=lo==hi, rc=lo==hi)
                outputs.append(node(bundle, "select", parents, piece, dict(domain=[str(lo),str(hi),lo==hi,lo==hi], chosen=i, mode="reduction")))
        batch(bundle, "reduction", parents, outputs, {})
        _verify_bundle(bundle, trusted.case_snapshot(), trusted.physics)
        with self.assertRaisesRegex(ValueError, "comparison_crosses_physical_anchors"):
            verify_bundle(bundle, trusted)

    def test_comparison_allows_different_phases_at_same_anchor(self):
        row = deepcopy(self.rows[2])
        row["table"]["sites"][0]["site_id"] = "road:x"
        row["original_tree"]["site_ids"] = ["road:x"]
        repin(row)
        trusted = prepare(row)
        bundle = capture(row, False)["bundle"]
        raw = next(k for k,n in bundle["nodes"].items() if n["kind"] == "stop")
        piece = family_base._piece(bundle["nodes"][raw]["output"])
        normalized = node(bundle, "retag", [raw], piece, dict(anchor="road:x"))
        output = node(bundle, "select", [raw, normalized], piece,
                      dict(domain=family_base._plain(piece.dump())["domain"], chosen=1, mode="union"))
        batch(bundle, "union", [raw, normalized], [output], {})
        verify_bundle(bundle, trusted)

    def test_guarded_union_requires_compatible_phase(self):
        row = deepcopy(self.rows[2])
        row["table"]["sites"][0]["site_id"] = "road:x"
        row["original_tree"]["site_ids"] = ["road:x"]
        repin(row)
        trusted = prepare(row)
        bundle = capture(row, False)["bundle"]
        raw = next(k for k, n in bundle["nodes"].items() if n["kind"] == "stop")
        piece = family_base._piece(bundle["nodes"][raw]["output"])
        normalized = node(bundle, "retag", [raw], piece, dict(anchor="road:x"))
        guards = [deepcopy(bundle["nodes"][p]["output"]["domain"]) for p in (raw, normalized)]
        node(bundle, "guarded_union", [raw, normalized], piece, dict(guards=guards))
        _verify_bundle(bundle, trusted.case_snapshot(), trusted.physics)
        with self.assertRaisesRegex(ValueError, "incompatible_physical_phase"):
            verify_bundle(bundle, trusted)

    def test_ancestor_guard_rejects_physically_valid_same_final_key(self):
        row = self.rows[2]
        trusted = prepare(row)
        bundle = deepcopy(self.captures[row["case_id"], False]["bundle"])
        raw = next(k for k, n in bundle["nodes"].items() if n["kind"] == "stop" and
                   F(n["output"]["domain"][0]) < 2 < 3 < F(n["output"]["domain"][1]))
        p = family_base._piece(bundle["nodes"][raw]["output"])
        guard = ["2", "3", True, True]
        restricted = node(bundle, "restrict", [raw], replace(p, lo=F(2), hi=F(3), lc=True, rc=True),
                          dict(domain=guard, reason="independent inherited-guard regression"))
        rp = family_base._piece(bundle["nodes"][restricted]["output"])
        normalized = node(bundle, "retag", [restricted], replace(rp, state=("road:x", *rp.state[1:])), dict(anchor="road:x"))
        incoming = drive(bundle, normalized, "road:x", trusted.physics)[0]
        outputs = stop(bundle, incoming, "road:z", trusted.physics)
        chosen = next(k for k in outputs if family_base._piece(bundle["nodes"][k]["output"]).contains(F(4)))
        checked = verify_bundle(bundle, trusted)
        result = reconstruct(checked, chosen, "4", "100")
        check_witness(checked, chosen, result["witness"], dict(kind="membership", energy="4"))
        forged = deepcopy(result["witness"])
        events = forged["events"]
        events[2].update(departure_energy="3/2", departure_time="5/2")
        events[3].update(arrival_energy="3/2", departure_energy="3/2", arrival_time="5/2", departure_time="5/2")
        events[4].update(arrival_energy="3/2", arrival_time="5/2")
        with self.assertRaisesRegex(ValueError, "inherited_energy_guard"):
            check_witness(checked, chosen, forged, dict(kind="membership", energy="4"))

    def test_consumer_replay_blocks_production_reference_and_lp_imports(self):
        payload = [dict(row=row, evidence=self.captures[row["case_id"], d])
                   for row in self.rows for d in (False, True)]
        script = r'''
import importlib.abc, json, pathlib, sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if (fullname.split('.')[0] in {'timecut5', 'scipy', 'numpy'} or
            fullname.startswith(('validation.reference5', 'reference5', 'validation.suffix5'))):
            raise AssertionError('Forbidden consumer import: '+fullname)
sys.meta_path.insert(0, Block())
from validation.real5_v2 import prepare_real_case, verify_trace
from validation.family5.checker import canonical, digest
rows = json.loads(pathlib.Path(sys.argv[1]).read_text())
for value in rows:
    row, evidence = value['row'], value['evidence']
    trusted = prepare_real_case(row['query'], digest(row['query']), canonical(row['table']).encode(),
        row['table_sha256'], canonical(row['original_tree']).encode(), row['original_tree_sha256'])
    checked = verify_trace(evidence['trace'], evidence['bundle'], trusted)
    assert checked.summary['verified']
assert not any(x.split('.')[0] in {'timecut5', 'scipy', 'numpy'} for x in sys.modules)
print('independent replay:', len(rows))
'''
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/"mock_evidence.json"
            path.write_text(json.dumps(payload))
            env = dict(os.environ, PYTHONPATH=str(ROOT))
            result = subprocess.run([sys.executable, "-c", script, str(path)], cwd=ROOT, env=env,
                                    text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertIn("independent replay: 10", result.stdout)


if __name__ == "__main__":
    unittest.main()
