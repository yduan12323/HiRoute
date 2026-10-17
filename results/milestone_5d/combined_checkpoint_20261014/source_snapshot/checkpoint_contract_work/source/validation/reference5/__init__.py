"""Independent bounded continuous C/S/CS reference; never a production proof."""
from .model import InvalidInput, normalize_case, replay_witness, selected_legs
from .solver import SCOPE, jsonable, solve_case

__all__ = ["InvalidInput", "normalize_case", "replay_witness", "selected_legs", "SCOPE", "jsonable", "solve_case"]

from .real_input import IndependentLegTable
from .real_solver import estimate_real_regimes, query_from_resolved_state, replay_real_witness, solve_real_case

__all__ += ["IndependentLegTable", "estimate_real_regimes", "query_from_resolved_state",
            "replay_real_witness", "solve_real_case"]
