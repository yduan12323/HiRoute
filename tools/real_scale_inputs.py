"""Compatibility import for one transition cycle; use hiroute.data.queries."""
import sys
from hiroute.data import queries as _implementation

def __getattr__(name):
    return getattr(_implementation, name)

if __name__ == "__main__":
    _implementation.main()
else:
    sys.modules[__name__] = _implementation
