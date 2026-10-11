"""Replay-verified symbolic OPEN checkpoint for small M5-D exact domains.

Each OPEN entry is a semantic Site/effect prefix. On resume, all completed
steps are deterministically replayed against the same byte-bound domain and
the reconstructed OPEN queue must match the checkpoint. This deliberately
charges replay work; it never trusts stored terminal JSON as an optimum.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Mapping

from .bounded import prefix_primary_lower_bound
from .deployable import (QueryDomain, RegionBoundProvider, SearchOutcome,
                         SeedDepthCertificate, SolveStatus, _independent_attained_replay,
                         _outcome_from_terminal, construct_verified_seed,
                         prepared_checkpoint_bytes)
from .probe import terminal
from .real_adapter import RealProblem, original_region_view
from .real_legs import restrict_frozen_tree


_SEARCH_SOURCES = ("resumable.py", "bounded.py", "deployable.py", "hierarchy.py",
                   "probe.py", "pwa.py", "real_adapter.py", "real_legs.py",
                   "provenance.py", "road_provider.py", "road_landmark.py")


def _search_source_manifest() -> dict[str, str]:
    root = Path(__file__).resolve().parent
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in _SEARCH_SOURCES}


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode()


def _decode_prefix(value):
    if type(value) is not list or any(type(event) is not list or len(event) != 2 or
                                      any(type(x) is not str for x in event) for event in value):
        raise ValueError("Checkpoint prefix has invalid action shape")
    return tuple(tuple(event) for event in value)


@dataclass(frozen=True)
class SearchStepReceipt:
    status: SolveStatus
    stop_reason: str
    outcome: SearchOutcome
    checkpoint_bytes: bytes
    processed_prefixes: int
    open_prefixes: int
    replayed_restore_prefixes: int
    region_queries: int
    online_internal_member_accesses: int


class ResumableExactSearch:
    """Complete prefix enumeration with optional indexed Region strict pruning.

    No dominance or heuristic depth cap is used. This engine is intentionally
    a correctness/checkpoint prototype; a full 32/128 Site workload still
    needs the separately specified resource and routing implementation.
    """

    def __init__(self, certificate: SeedDepthCertificate, hierarchy_bytes: bytes,
                 verifier_source_sha256: Mapping[str, str], *, mode: str,
                 checkpoint_bytes: bytes | None = None):
        if mode not in ("flat", "hier"):
            raise ValueError("Exact search mode must be flat or hier")
        fresh = construct_verified_seed(certificate.domain, verifier_source_sha256)
        if not isinstance(fresh, SeedDepthCertificate) or fresh != certificate:
            raise ValueError("Seed certificate failed independent replay on restart")
        if hashlib.sha256(hierarchy_bytes).hexdigest() != certificate.domain.binding.hierarchy_sha256:
            raise ValueError("Original hierarchy bytes differ from bound domain")
        self.certificate = fresh
        self.mode = mode
        self.domain: QueryDomain = fresh.domain
        query, table = self.domain.open()
        self.table = table
        self.problem = RealProblem(dict(query, H_ref=fresh.max_depth), table)
        restriction = restrict_frozen_tree(hierarchy_bytes,
            self.domain.binding.hierarchy_sha256, list(table.sites))
        self.root = original_region_view(table, restriction)
        self.provider = RegionBoundProvider(self.domain, self.root)
        self.prepared_sha256 = hashlib.sha256(prepared_checkpoint_bytes(
            fresh, hierarchy_bytes)).hexdigest()
        self.search_source_manifest = _search_source_manifest()
        self.open = [()]
        self.closed = []
        self.terminals = []
        self.restore_replayed_prefixes = 0
        self._frozen_open_limit = None
        if checkpoint_bytes is not None:
            self._restore(checkpoint_bytes)

    def _pieces(self, prefix):
        pieces = (self.problem.initial_piece(),)
        for site, effect in prefix:
            pieces = self.problem.advance(pieces, site, effect)
            if not pieces:
                break
        return pieces

    def _actions(self, pieces):
        if (not pieces or len(pieces[0].pi) >= self.certificate.max_depth or
                pieces[0].state.anchor == self.problem.destination or
                prefix_primary_lower_bound(self.problem, pieces) > self.certificate.seed.primary_j):
            return ()
        remaining = pieces[0].state.remaining_schedule
        if self.mode == "flat":
            return tuple((site, effect) for site in sorted(self.table.sites)
                         if self.table.site(site).anchor_id != self.problem.destination
                         for effect in sorted(self.table.site(site).effects)
                         if effect not in ("S", "CS") or remaining)
        accepted = []
        def visit(region, effect):
            if not self.provider.action_mask(region, effect, remaining):
                return
            bound, _ = self.provider.bound(self.problem, pieces, region, effect)
            if bound is None or bound > self.certificate.seed.primary_j:
                return
            if region.children:
                for child in region.children:
                    visit(child, effect)
            else:
                accepted.extend(self.provider.leaf_actions(region, effect, remaining))
        for effect in ("C", "S", "CS"):
            visit(self.root, effect)
        if len(accepted) != len(set(accepted)):
            raise ValueError("Indexed Region repeats a next action")
        return tuple(sorted(accepted))

    def _step(self):
        prefix = self.open.pop(0)
        pieces = self._pieces(prefix)
        self.terminals.extend(self.problem.finish(pieces))
        children = []
        for action in self._actions(pieces):
            if self.problem.advance(pieces, *action):
                children.append(prefix + (action,))
        self.closed.append(prefix)
        self.open.extend(children)

    def checkpoint(self) -> bytes:
        return _canonical({"schema": "hiroute.m5d.symbolic_open.v2",
                           "prepared_sha256": self.prepared_sha256,
                           "search_source_manifest": self.search_source_manifest,
                           "mode": self.mode,
                           "closed": self.closed,
                           "open": self.open,
                           "terminal_piece_count": len(self.terminals),
                           "max_open_prefixes": self._frozen_open_limit,
                           "complete": not self.open})

    def _restore(self, data: bytes):
        try:
            saved = json.loads(data)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("Invalid symbolic OPEN checkpoint bytes") from error
        if (type(saved) is not dict or set(saved) != {"schema", "prepared_sha256",
                "search_source_manifest",
                "mode", "closed", "open", "terminal_piece_count", "complete",
                "max_open_prefixes"} or
                saved["schema"] != "hiroute.m5d.symbolic_open.v2" or
                saved["prepared_sha256"] != self.prepared_sha256 or
                saved["search_source_manifest"] != self.search_source_manifest or
                saved["mode"] != self.mode or type(saved["closed"]) is not list or
                type(saved["open"]) is not list or
                type(saved["max_open_prefixes"]) is not int or
                saved["max_open_prefixes"] < 1):
            raise ValueError("Checkpoint source, mode or schema mismatch")
        claimed_closed = tuple(_decode_prefix(value) for value in saved["closed"])
        for prefix in claimed_closed:
            if not self.open or self.open[0] != prefix:
                raise ValueError("Checkpoint OPEN sequence differs from replay")
            self._step()
            self.restore_replayed_prefixes += 1
        self._frozen_open_limit = saved["max_open_prefixes"]
        if self.checkpoint() != data:
            raise ValueError("Checkpoint OPEN, terminal count or completion differs from replay")

    def run(self, *, max_steps: int, max_open_prefixes: int) -> SearchStepReceipt:
        if type(max_steps) is not int or max_steps < 0 or type(max_open_prefixes) is not int or max_open_prefixes < 1:
            raise ValueError("Finite nonnegative step and positive OPEN limits required")
        if self._frozen_open_limit is not None and self._frozen_open_limit != max_open_prefixes:
            raise ValueError("OPEN memory policy changed across checkpoint")
        self._frozen_open_limit = max_open_prefixes
        status = (SolveStatus.MEMORY_LIMIT if len(self.open) > max_open_prefixes
                  else SolveStatus.TIME_LIMIT)
        for _ in range(0 if status is SolveStatus.MEMORY_LIMIT else max_steps):
            if not self.open:
                break
            self._step()
            if len(self.open) > max_open_prefixes:
                status = SolveStatus.MEMORY_LIMIT
                break
        if self.open:
            outcome = SearchOutcome(self.domain.binding, status)
        else:
            exact = terminal(self.terminals, self.problem.destination,
                             self.problem.reserve, self.problem.start, self.problem.penalty)
            outcome = _outcome_from_terminal(self.domain.binding, SimpleNamespace(result=exact))
            _independent_attained_replay(self.domain, SimpleNamespace(result=exact),
                                         outcome, self.certificate.max_depth)
            status = outcome.status
        reason = ("symbolic_open_count_limit" if status is SolveStatus.MEMORY_LIMIT else
                  "step_budget_exhausted" if status is SolveStatus.TIME_LIMIT else
                  "complete_exact_search")
        return SearchStepReceipt(status, reason, outcome, self.checkpoint(), len(self.closed),
                                 len(self.open), self.restore_replayed_prefixes,
                                 self.provider.online_queries,
                                 self.provider.online_internal_member_accesses)
