"""Provenance-derived physical location, independent of ambiguous Site text.

A stop writes its Site ID into the wire state, which may also name an unrelated
road anchor. Only a retag consumes that raw Site phase. An own-anchor Site may
also move/stop directly because its raw and physical identities coincide.
"""
from dataclasses import dataclass
from types import MappingProxyType

from validation.family5.checker import require, _validation_api


@dataclass(frozen=True)
class PhysicalState:
    anchor: str
    raw_site: str | None = None


@_validation_api
def verify_physical_states(bundle):
    """Return immutable node phases after exact family verification.

    This extra check is necessary even when the final textual state and every
    content hash match: a label collision must never choose a physical leg.
    """
    nodes, pieces, physics = bundle._data["nodes"], bundle._pieces, bundle._physics
    states, active = {}, set()

    def consistent_inputs(parents):
        locations = {}
        for parent in parents:
            phase, wire_state = visit(parent), pieces[parent].state
            require(wire_state not in locations or locations[wire_state] == phase.anchor,
                    "comparison_crosses_physical_anchors")
            locations[wire_state] = phase.anchor

    def visit(ident):
        if ident in states:
            return states[ident]
        require(ident not in active, "physical_state_cycle")
        active.add(ident)
        node, piece = nodes[ident], pieces[ident]
        kind, parents, params = node["kind"], node["parents"], node["params"]
        inherited = [visit(parent) for parent in parents]
        if kind == "initial":
            phase = PhysicalState(physics.origin)
        elif kind in ("restrict", "select"):
            if kind == "select":
                consistent_inputs(parents)
            phase = inherited[params["chosen"] if kind == "select" else 0]
        elif kind == "guarded_union":
            require(inherited and all(p == inherited[0] for p in inherited),
                    "guarded_union_incompatible_physical_phase")
            phase = inherited[0]
        elif kind == "retag":
            old = inherited[0]
            require(old.raw_site is not None, "retag_requires_unconsumed_raw_site_phase")
            require(pieces[parents[0]].state[0] == old.raw_site, "retag_raw_site_label")
            require(params["anchor"] == old.anchor == physics.anchors[old.raw_site],
                    "retag_wrong_physical_anchor")
            phase = PhysicalState(old.anchor)
        elif kind in ("drive", "stop"):
            old = inherited[0]
            require(pieces[parents[0]].state[0] == old.anchor and
                    (old.raw_site is None or old.raw_site == old.anchor),
                    "physical_action_requires_anchor_phase", kind=kind,
                    physical_anchor=old.anchor, raw_site=old.raw_site)
            if kind == "drive":
                require((old.anchor, params["site"]) in physics.legs, "physical_drive_leg_missing")
                phase = PhysicalState(params["site"])
            else:
                site = params["site"]
                require(old.anchor == physics.anchors[site] != physics.destination,
                        "physical_stop_anchor_or_terminal")
                phase = PhysicalState(old.anchor, site)
        else:
            require(False, "unsupported_physical_phase_node", kind=kind)
        require(piece.state[0] == (phase.raw_site if phase.raw_site is not None else phase.anchor),
                "physical_phase_wire_label_mismatch")
        active.remove(ident)
        states[ident] = phase
        return phase

    for ident in nodes:
        visit(ident)
    # Empty-image batches have no output node; their inputs still carry the
    # same anchor obligation. They cannot smuggle an invalid physical call.
    for batch in bundle._data["batches"]:
        if batch["kind"] in ("union", "reduction"):
            consistent_inputs(batch["parents"])
        elif batch["kind"] in ("drive", "stop"):
            for ident in batch["parents"]:
                phase = states[ident]
                require(pieces[ident].state[0] == phase.anchor and
                        (phase.raw_site is None or phase.raw_site == phase.anchor),
                        "physical_batch_requires_anchor_phase")
    return MappingProxyType(states)
