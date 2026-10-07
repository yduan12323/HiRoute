"""Lossless immutable capture input; storage checks confer no mathematical claim."""
from .reader import (
    CaptureError,
    CaptureFormatError,
    CaptureIntegrityError,
    CaptureLimits,
    CaptureResourceError,
    LoadedCapture,
    load_capture,
)

__all__ = [
    'CaptureError', 'CaptureFormatError', 'CaptureIntegrityError',
    'CaptureLimits', 'CaptureResourceError', 'LoadedCapture', 'load_capture',
]
