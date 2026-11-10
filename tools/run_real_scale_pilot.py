"""Compatibility import for one transition cycle; use hiroute.execution.pilot."""
import sys
from hiroute.execution import pilot as _implementation

def __getattr__(name):
    return getattr(_implementation, name)

if __name__ == "__main__":
    _implementation.cli()
else:
    sys.modules[__name__] = _implementation
