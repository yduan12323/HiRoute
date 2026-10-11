"""Fail-closed layer-boundary recovery by replaying the same exact engine.

Only hashes of completed layer events are persisted. Resume reconstructs every
piece, incumbent and counter by executing the same solver again, verifies the
recorded prefix, and then continues. Reconstruction consumes full CPU time.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


_EXTERNAL = {"graph_nodes", "graph_edges", "router", "anchors", "sites",
             "query", "hierarchy", "landmark", "seed", "policy", "runtime"}


def source_manifest() -> dict[str, str]:
    root = Path(__file__).resolve().parent
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.glob("*.py"))}


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode()


class LayerCheckpointStop(Exception):
    def __init__(self, checkpoint_bytes: bytes):
        self.checkpoint_bytes = checkpoint_bytes
        super().__init__("Exact search stopped at a complete layer boundary")


class ExactLayerReplay:
    def __init__(self, *, mode: str, domain_sha256: str,
                 external_source_sha256: dict[str, str],
                 previous_checkpoint: bytes | None = None,
                 stop_after_depth: int | None = None):
        if type(external_source_sha256) is not dict or set(external_source_sha256) != _EXTERNAL:
            raise ValueError("Complete external source hashes required")
        if mode not in ("flat", "hier") or any(
                type(value) is not str or len(value) != 64 or
                any(char not in "0123456789abcdef" for char in value)
                for value in (domain_sha256, *external_source_sha256.values())):
            raise ValueError("Exact layer replay requires bound source hashes")
        if (stop_after_depth is not None and
                (type(stop_after_depth) is not int or stop_after_depth < 0)):
            raise ValueError("Invalid exact layer replay policy")
        self.mode, self.domain_sha256 = mode, domain_sha256
        self.external_source_sha256 = dict(external_source_sha256)
        self.search_source_sha256 = source_manifest()
        self.stop_after_depth = stop_after_depth
        self.expected = []
        if previous_checkpoint is not None:
            def unique(pairs):
                value = {}
                for key, item in pairs:
                    if key in value:
                        raise ValueError("Duplicate exact layer checkpoint key")
                    value[key] = item
                return value
            try:
                saved = json.loads(previous_checkpoint, object_pairs_hook=unique,
                    parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite checkpoint")))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ValueError("Invalid exact layer checkpoint") from error
            if (type(saved) is not dict or set(saved) != {"schema", "mode",
                    "domain_sha256", "external_source_sha256", "search_source_sha256",
                    "layers"} or saved["schema"] != "hiroute.m5d.same_engine_layer_replay.v1" or
                    saved["mode"] != mode or saved["domain_sha256"] != domain_sha256 or
                    saved["external_source_sha256"] != external_source_sha256 or
                    saved["search_source_sha256"] != self.search_source_sha256 or
                    type(saved["layers"]) is not list or not saved["layers"] or
                    any(type(row) is not dict or set(row) != {"depth", "state_sha256"} or
                        row["depth"] != index or type(row["state_sha256"]) is not str or
                        len(row["state_sha256"]) != 64 or
                        any(char not in "0123456789abcdef" for char in row["state_sha256"])
                        for index, row in enumerate(saved["layers"]))):
                raise ValueError("Exact layer checkpoint source or sequence mismatch")
            if _canonical(saved) != previous_checkpoint:
                raise ValueError("Noncanonical exact layer checkpoint")
            self.expected = saved["layers"]
        self.layers = []
        self.replayed_restore_layers = 0

    def __call__(self, depth, layer, terminals, incumbent, counters):
        if depth != len(self.layers):
            raise ValueError("Exact engine layer sequence is discontinuous")
        state = (layer, terminals, incumbent, counters)
        row = {"depth": depth,
               "state_sha256": hashlib.sha256(repr(state).encode()).hexdigest()}
        if depth < len(self.expected):
            if row != self.expected[depth]:
                raise ValueError("Replayed exact OPEN, incumbent or counters differ")
            self.replayed_restore_layers += 1
        self.layers.append(row)
        if self.stop_after_depth == depth:
            raise LayerCheckpointStop(self.checkpoint_bytes())

    def finish(self):
        if self.replayed_restore_layers != len(self.expected):
            raise ValueError("Exact search ended before the checkpointed OPEN layer")

    def checkpoint_bytes(self) -> bytes:
        return _canonical({"schema": "hiroute.m5d.same_engine_layer_replay.v1",
            "mode": self.mode, "domain_sha256": self.domain_sha256,
            "external_source_sha256": self.external_source_sha256,
            "search_source_sha256": self.search_source_sha256,
            "layers": self.layers})
