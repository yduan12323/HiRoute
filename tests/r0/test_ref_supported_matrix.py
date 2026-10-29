import copy
import hashlib
import json
from pathlib import Path
import unittest

from hiroute_ref.cli import snapshot_case

ROOT = Path(__file__).resolve().parents[2]


def reidentify(snapshot):
    identity = {key: value for key, value in snapshot.items() if key != "semantic_problem_id"}
    snapshot["semantic_problem_id"] = hashlib.sha256(
        (json.dumps(identity, ensure_ascii=False, sort_keys=True,
                    separators=(",", ":")) + "\n").encode()).hexdigest()
    return snapshot


class IndependentRefAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = reidentify(
            json.loads((ROOT / "tests/r0/c01_zero_stop_snapshot.json").read_text()))

    def test_ref_admits_its_declared_bounded_contract(self):
        case, semantic_id = snapshot_case(copy.deepcopy(self.snapshot))
        self.assertEqual(case["case_id"], semantic_id)
        self.assertEqual(case["H_ref"], self.snapshot["depth_limit"])

    def test_ref_computes_case_identity_without_a_caller_supplied_digest(self):
        snapshot = copy.deepcopy(self.snapshot)
        expected = snapshot.pop("semantic_problem_id")
        case, semantic_id = snapshot_case(snapshot)
        self.assertEqual(semantic_id, expected)
        self.assertEqual(case["case_id"], expected)
        snapshot["semantic_problem_id"] = "0" * 64
        _, recomputed = snapshot_case(snapshot)
        self.assertEqual(recomputed, expected)

    def test_ref_rejects_unknown_model_numeric_leg_and_seed_depth(self):
        for field, value in (
            ("model_contract_id", "future_model"),
            ("numerical_contract_id", "binary_float_v2"),
            ("selected_leg_contract", "unknown_path_semantics"),
            ("depth_mode", "seed_derived"),
        ):
            with self.subTest(field=field):
                mutated = copy.deepcopy(self.snapshot)
                mutated[field] = value
                reidentify(mutated)
                with self.assertRaisesRegex(ValueError, "unsupported REF input"):
                    snapshot_case(mutated)


if __name__ == "__main__":
    unittest.main()
