"""Safe bounded-detour graph infrastructure; structural guarantees only."""
from .safe_detour import (
    DetourDistances, EnvelopeGraph, NumericalTolerance, SafeDetourEnvelope,
    build_envelope_from_precomputed, compute_safe_detour_envelope,
    iter_progressive_envelopes, precompute_detour_distances,
)

__all__ = ["DetourDistances", "EnvelopeGraph", "NumericalTolerance", "SafeDetourEnvelope",
           "build_envelope_from_precomputed", "compute_safe_detour_envelope",
           "iter_progressive_envelopes", "precompute_detour_distances"]
