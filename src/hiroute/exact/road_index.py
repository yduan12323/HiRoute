"""Compatibility import for one transition cycle; use hiroute.routing.index."""
import sys
from hiroute.routing import index as _implementation
sys.modules[__name__] = _implementation
