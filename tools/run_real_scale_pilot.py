"""Compatibility import for one transition cycle; use hiroute.execution.pilot."""
import sys
from hiroute.execution import pilot as _implementation
if __name__ == "__main__":
    _implementation.cli()
else:
    sys.modules[__name__] = _implementation
