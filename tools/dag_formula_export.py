"""Compatibility import; independent implementation lives in hiroute_compare."""
import sys
from hiroute_compare import dag_formula_export as _implementation

def __getattr__(name):
    return getattr(_implementation, name)

sys.modules[__name__] = _implementation
